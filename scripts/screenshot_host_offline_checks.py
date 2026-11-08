#!/usr/bin/env python3
"""Read-only checks for the conditional offline install. Not a service."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path


# The rollback allowlist. Four c943 files must match. The other five, including
# the manifest, are absent on c943 and must stay absent after a restore.
ROLLBACK_RELS = (
    "app.py",
    "static/index.html",
    "Dockerfile",
    "README.md",
    "screenshots.py",
    "docs/SCREENSHOT_DEPLOY.md",
    "docs/screenshot-install-manifest.json",
    "scripts/screenshot_host_preflight.py",
    "scripts/screenshot_host_apply.py",
)
BASELINE_RELS = ROLLBACK_RELS[:4]
ADDED_RELS = ROLLBACK_RELS[4:]
RUN_ID_RE = re.compile(r"^screenshot-run-[1-9][0-9]*-[0-9a-f]{16}$")
TRANSACTION_NAME = ".screenshot-transaction"


def _plist_program(path: Path) -> str:
    with path.open("rb") as handle:
        data = plistlib.load(handle)
    program = data.get("Program") or ""
    arguments = data.get("ProgramArguments") or []
    if not program and arguments:
        program = arguments[0]
    return program if isinstance(program, str) else ""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inside(path: Path, root: Path) -> bool:
    path = path.resolve()
    root = root.resolve()
    return path == root or root in path.parents


def write_identity(args: argparse.Namespace) -> int:
    plist = Path(args.plist)
    out = Path(args.out)
    if not plist.is_file():
        return 14
    program = _plist_program(plist)
    if not program or program != args.program:
        return 11
    if not os.access(program, os.X_OK):
        return 15
    if _inside(out, Path(args.root)):
        return 13
    fields = {
        "label": args.label,
        "program": args.program,
        "plist": str(plist),
        "pid": args.pid,
        "pgid": args.pgid,
        "plist_sha256": _sha256(plist),
    }
    for value in fields.values():
        if value == "" or "\n" in value or "\t" in value:
            return 12
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}\t{value}" for key, value in fields.items()]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


def read_identity(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "\t" not in line:
            continue
        key, value = line.split("\t", 1)
        fields[key] = value
    return fields


def check_identity(args: argparse.Namespace) -> int:
    identity = Path(args.identity)
    if not identity.is_file() or _inside(identity, Path(args.root)):
        return 13
    fields = read_identity(identity)
    required = ("label", "program", "plist", "pid", "pgid", "plist_sha256")
    if any(not fields.get(key) for key in required):
        return 12
    if fields["label"] != args.label:
        return 12
    plist = Path(fields["plist"])
    if not plist.is_file():
        return 14
    if _sha256(plist) != fields["plist_sha256"]:
        return 10
    if _plist_program(plist) != fields["program"] or not os.access(fields["program"], os.X_OK):
        return 11
    print(fields["program"])
    print(fields["plist"])
    print(fields["pid"])
    print(fields["pgid"])
    return 0


def port_free(args: argparse.Namespace) -> int:
    """IPv4 127.0.0.1 only. Connection refused is free. Timeout and other errors are not."""
    probe = socket.socket(socket.AF_INET)
    probe.settimeout(0.3)
    try:
        probe.connect(("127.0.0.1", args.port))
    except ConnectionRefusedError:
        return 0
    except OSError:
        return 20
    else:
        return 20
    finally:
        probe.close()


def processes_gone(args: argparse.Namespace) -> int:
    listing = subprocess.check_output(["ps", "-ax", "-o", "pid=,ppid=,pgid="], text=True)
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        pid, ppid, pgid = parts[:3]
        if pid == args.pid or ppid == args.pid:
            return 21
        if pgid == args.pgid:
            return 22
    return 0


def exclusive(args: argparse.Namespace) -> int:
    """Kept for callers that only probe. The offline copy uses guard instead."""
    db = Path(args.db)
    if not db.is_file():
        return 23
    conn = sqlite3.connect(db, timeout=0.4)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("COMMIT")
    except sqlite3.OperationalError:
        return 23
    finally:
        conn.close()
    return 0


def guard_section(args: argparse.Namespace) -> int:
    """Hold BEGIN IMMEDIATE across the given command.

    The read-only backup connection can still copy. Another writer cannot
    commit until this connection closes. Closing it can checkpoint WAL into
    the main database file and remove the WAL and SHM files. Rows stay.
    """
    db = Path(args.db)
    if not db.is_file():
        return 23
    cmd = list(args.cmd)
    if cmd[:1] == ["--"]:
        cmd = cmd[1:]
    if not cmd:
        return 1
    conn = sqlite3.connect(db, timeout=0.4)
    ready = Path(args.ready)
    try:
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError:
        conn.close()
        return 23
    ready.parent.mkdir(parents=True, exist_ok=True)
    ready.write_text(
        "lock=BEGIN IMMEDIATE\n"
        "held_across=backup,verify,preflight,dry-run,apply\n"
        "blocks=other sqlite writers\n"
        "backup_uses=a separate read-only connection\n"
        "close_may_checkpoint=true\n",
        encoding="utf-8",
    )
    try:
        proc = subprocess.run(cmd)
        return proc.returncode
    finally:
        ready.unlink(missing_ok=True)
        try:
            conn.commit()
        except sqlite3.Error:
            pass
        conn.close()


def create_run_dir(home: Path, names=None) -> Path:
    """Create a new run directory. mkdir is the exclusive step. `%N` is not used.

    BSD `date +%s%N` prints a literal N, so a second run would reuse one folder.
    A name that already exists is skipped. The caller never receives that folder.
    """
    home_real = Path(os.path.realpath(home))
    if not home_real.is_dir():
        raise OSError("home is not a directory")
    if names is None:
        def _default():
            while True:
                yield f"screenshot-run-{os.getpid()}-{secrets.token_hex(8)}"
        source = _default()
    elif callable(names):
        source = names()
    else:
        source = iter(names)
    for _ in range(100):
        try:
            name = next(source)
        except StopIteration:
            break
        if not isinstance(name, str) or RUN_ID_RE.fullmatch(name) is None:
            continue
        path = home_real / name
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            continue
        return path
    raise OSError("could not create an exclusive run directory")


def write_durable(path: Path, data: bytes) -> None:
    """Write a file and flush it before the caller replaces any source file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        try:
            os.fsync(directory)
        except OSError:
            pass
    finally:
        os.close(directory)


def _symlink_component(root: Path, rel: str) -> bool:
    cursor = root
    for part in Path(rel).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return True
        if not cursor.exists():
            return False
    return False


def baseline_problem(root: Path, manifest_path: Path) -> str | None:
    """Return the first of the nine rollback paths that is not the c943 baseline.

    The manifest's install map does not hash the manifest file itself. That
    file is still one of the nine and must be absent. A tree that matches the
    other eight is not baseline.
    """
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "manifest"
    baseline = manifest.get("baseline") if isinstance(manifest, dict) else None
    if not isinstance(baseline, dict):
        return "manifest"
    for rel in BASELINE_RELS:
        digest = baseline.get(rel)
        path = root / rel
        if not isinstance(digest, str) or len(digest) != 64:
            return rel
        if _symlink_component(root, rel) or path.is_symlink() or not path.is_file():
            return rel
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            return rel
    for rel in ADDED_RELS:
        path = root / rel
        if _symlink_component(root, rel) or path.is_symlink() or path.exists():
            return rel
    return None


def confine_backup(root: Path, candidate: str) -> Path | None:
    """Return the real backup directory only when it cannot leave root/backups.

    A string prefix accepts `backups/../../../outside` and a symlink under
    `backups/`. Both are rejected. The bytes at the far end can still be the
    c943 baseline; this check is path confinement, not a hash check.
    """
    if not isinstance(candidate, str) or candidate == "" or "\x00" in candidate:
        return None
    raw = Path(candidate)
    if not raw.is_absolute():
        return None
    root_real = Path(os.path.realpath(root))
    backups = root_real / "backups"
    normalized = Path(os.path.normpath(candidate))
    try:
        relative = normalized.relative_to(backups)
    except ValueError:
        return None
    if relative == Path(".") or ".." in relative.parts or "." in relative.parts:
        return None
    cursor = root_real
    for part in Path("backups").joinpath(relative).parts:
        if part in {"", ".", ".."}:
            return None
        cursor = cursor / part
        if cursor.is_symlink() or not cursor.exists():
            return None
    if not cursor.is_dir() or cursor.is_symlink():
        return None
    resolved = Path(os.path.realpath(cursor))
    backups_real = Path(os.path.realpath(backups))
    try:
        resolved.relative_to(backups_real)
    except ValueError:
        return None
    if resolved == backups_real:
        return None
    return resolved


def recovery_backup_path(intent_path: Path, run_dir: Path, root: Path, manifest_path: Path, receipt_path: Path | None) -> Path | None:
    """Backup for this run only. A different valid c943 directory is not eligible."""
    try:
        intent = json.loads(intent_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(intent, dict) or intent.get("phase") != "replacing":
        return None
    run_id = intent.get("run_id")
    if not isinstance(run_id, str) or RUN_ID_RE.fullmatch(run_id) is None:
        return None
    run_real = Path(os.path.realpath(run_dir))
    root_real = Path(os.path.realpath(root))
    if run_real.name != run_id:
        return None
    if intent.get("run_dir") != str(run_real) or intent.get("root") != str(root_real):
        return None
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError:
        return None
    if intent.get("manifest_sha256") != hashlib.sha256(manifest_bytes).hexdigest():
        return None
    backup_text = intent.get("backup")
    if not isinstance(backup_text, str):
        return None
    confined = confine_backup(root_real, backup_text)
    if confined is None or confined.name != f"screenshots-{run_id}":
        return None
    marker = confined / TRANSACTION_NAME
    if marker.is_symlink() or not marker.is_file():
        return None
    if marker.read_text(encoding="utf-8") != run_id + "\n":
        return None
    if baseline_problem(confined, manifest_path) is not None:
        return None
    if receipt_path is not None and receipt_path.is_file():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(receipt, dict) and receipt.get("backup"):
            other = confine_backup(root_real, str(receipt.get("backup")))
            if other != confined:
                return None
    return confined


def source_matches_baseline(args: argparse.Namespace) -> int:
    """Exit 0 only when all nine rollback paths match the c943 baseline."""
    problem = baseline_problem(Path(args.root), Path(args.manifest))
    if problem is not None:
        print(problem)
        return 40
    return 0


def _cmd_create_run(args: argparse.Namespace) -> int:
    try:
        print(create_run_dir(Path(args.home)))
    except OSError:
        return 1
    return 0


def _cmd_confine_backup(args: argparse.Namespace) -> int:
    confined = confine_backup(Path(args.root), args.backup)
    if confined is None:
        return 41
    print(confined)
    return 0


def _cmd_recovery_backup(args: argparse.Namespace) -> int:
    receipt = Path(args.receipt) if args.receipt else None
    confined = recovery_backup_path(Path(args.intent), Path(args.run_dir), Path(args.root), Path(args.manifest), receipt)
    if confined is None:
        return 42
    print(confined)
    return 0


def interrupted(args: argparse.Namespace) -> int:
    source = Path(args.jobs)
    before = source.read_bytes() if source.is_file() else None
    jobs = []
    if before is not None:
        data = json.loads(before.decode("utf-8"))
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict) and value.get("status") in {"queued", "running"}:
                    jobs.append({"id": str(key), "status": value.get("status"), "stage": value.get("stage")})
    payload = {
        "old_process_can_resume": False,
        "live_jobs_rewritten": False,
        "note": "Read-only list. The old process cannot resume these jobs. The live url_jobs.json was not modified.",
        "jobs": jobs,
    }
    out = Path(args.out)
    if _inside(out, Path(args.root)):
        return 13
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    after = source.read_bytes() if source.is_file() else None
    if after != before:
        return 24
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline install checks. Does not stop or start launchd.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    write = sub.add_parser("write-identity")
    write.add_argument("--root", type=Path, required=True)
    write.add_argument("--plist", required=True)
    write.add_argument("--program", required=True)
    write.add_argument("--pid", required=True)
    write.add_argument("--pgid", required=True)
    write.add_argument("--label", required=True)
    write.add_argument("--out", type=Path, required=True)
    write.set_defaults(func=write_identity)

    check = sub.add_parser("check-identity")
    check.add_argument("--root", type=Path, required=True)
    check.add_argument("--identity", type=Path, required=True)
    check.add_argument("--label", required=True)
    check.set_defaults(func=check_identity)

    port = sub.add_parser("port")
    port.add_argument("--port", type=int, required=True)
    port.set_defaults(func=port_free)

    proc = sub.add_parser("processes")
    proc.add_argument("--pid", required=True)
    proc.add_argument("--pgid", required=True)
    proc.set_defaults(func=processes_gone)

    lock = sub.add_parser("exclusive")
    lock.add_argument("--db", required=True)
    lock.set_defaults(func=exclusive)

    guard = sub.add_parser("guard")
    guard.add_argument("--db", required=True)
    guard.add_argument("--ready", required=True)
    guard.add_argument("cmd", nargs=argparse.REMAINDER)
    guard.set_defaults(func=guard_section)

    baseline = sub.add_parser("source-baseline")
    baseline.add_argument("--root", type=Path, required=True)
    baseline.add_argument("--manifest", type=Path, required=True)
    baseline.set_defaults(func=source_matches_baseline)

    create = sub.add_parser("create-run")
    create.add_argument("--home", type=Path, required=True)
    create.set_defaults(func=_cmd_create_run)

    confine = sub.add_parser("confine-backup")
    confine.add_argument("--root", type=Path, required=True)
    confine.add_argument("--backup", required=True)
    confine.set_defaults(func=_cmd_confine_backup)

    recover = sub.add_parser("recovery-backup")
    recover.add_argument("--intent", type=Path, required=True)
    recover.add_argument("--run-dir", type=Path, required=True)
    recover.add_argument("--root", type=Path, required=True)
    recover.add_argument("--manifest", type=Path, required=True)
    recover.add_argument("--receipt", type=Path)
    recover.set_defaults(func=_cmd_recovery_backup)

    jobs = sub.add_parser("interrupted")
    jobs.add_argument("--root", type=Path, required=True)
    jobs.add_argument("--jobs", required=True)
    jobs.add_argument("--out", type=Path, required=True)
    jobs.set_defaults(func=interrupted)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
