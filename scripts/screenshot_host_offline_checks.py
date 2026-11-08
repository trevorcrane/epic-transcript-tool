#!/usr/bin/env python3
"""Read-only checks for the conditional offline install. Not a service."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path


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


def source_matches_baseline(args: argparse.Namespace) -> int:
    """Exit 0 only when every c943 baseline file matches and added install files are absent."""
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    baseline = manifest.get("baseline") or {}
    install = list((manifest.get("install") or {}).keys())
    root = Path(args.root)
    if not isinstance(baseline, dict) or not baseline or not install:
        return 40
    for rel, digest in baseline.items():
        path = root / rel
        if not path.is_file() or path.is_symlink():
            print(rel)
            return 40
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            print(rel)
            return 40
    for rel in install:
        if rel in baseline:
            continue
        if (root / rel).exists() or (root / rel).is_symlink():
            print(rel)
            return 40
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

    jobs = sub.add_parser("interrupted")
    jobs.add_argument("--root", type=Path, required=True)
    jobs.add_argument("--jobs", required=True)
    jobs.add_argument("--out", type=Path, required=True)
    jobs.set_defaults(func=interrupted)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
