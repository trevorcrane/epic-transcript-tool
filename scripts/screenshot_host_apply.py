#!/usr/bin/env python3
"""Copy the reviewed screenshot files only after the preflight gate passes.

Default mode prints the plan and writes nothing. --apply copies files and
makes a backup. It does not restart the server, touch .env, or touch the
transcript database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

from screenshot_host_preflight import DO_NOT_TOUCH, inspect_tree, load_new_hashes, sha256, write_path_symlink


INSTALL_PATHS = (
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
MANIFEST_REL = "docs/screenshot-install-manifest.json"
# Paths this installer creates or appends, besides INSTALL_PATHS.
EXTRA_WRITE_PATHS = (".gitignore", "backups")


def required_manifest_paths() -> list[str]:
    return [rel for rel in INSTALL_PATHS if rel != MANIFEST_REL]


def _read_nofollow(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        chunks = []
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
        return b"".join(chunks)
    finally:
        os.close(fd)


def fingerprint(path: Path) -> dict:
    """Hash a protected file without following a symlink."""
    if path.is_symlink():
        return {"kind": "symlink", "target": os.readlink(path)}
    if not path.exists():
        return {"kind": "missing"}
    mode = path.lstat().st_mode
    if not stat.S_ISREG(mode):
        return {"kind": "other", "mode": stat.S_IFMT(mode)}
    data = _read_nofollow(path)
    return {"kind": "file", "sha256": hashlib.sha256(data).hexdigest()}


def protected_rels(root: Path) -> list[str]:
    """Every named protected file plus every file already under data/."""
    rels: list[str] = []
    seen: set[str] = set()

    def add(rel: str) -> None:
        if rel not in seen:
            seen.add(rel)
            rels.append(rel)

    for rel in DO_NOT_TOUCH:
        add(rel)
    data = root / "data"
    if data.is_symlink():
        add("data")
        return rels
    if data.is_dir():
        for path in sorted(data.rglob("*")):
            if path.is_symlink() or path.is_file():
                add(path.relative_to(root).as_posix())
    return rels


def protected_fingerprints(root: Path) -> dict[str, dict]:
    return {rel: fingerprint(root / rel) for rel in protected_rels(root)}


def symlink_blocks(root: Path) -> list[str]:
    found = []
    for rel in tuple(INSTALL_PATHS) + EXTRA_WRITE_PATHS:
        link = write_path_symlink(root, rel)
        if link and link not in found:
            found.append(link)
    return found


def _write_bytes(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".rollback-tmp")
    with tmp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, dest)


def _restore(host: Path, originals: dict[str, bytes | None], gitignore_existed: bool, gitignore_bytes: bytes | None) -> None:
    for rel, data in originals.items():
        dest = host / rel
        if data is None:
            if dest.is_symlink() or dest.exists():
                if dest.is_dir() and not dest.is_symlink():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            continue
        _write_bytes(dest, data)
    gitignore = host / ".gitignore"
    if gitignore_existed:
        if gitignore_bytes is not None:
            _write_bytes(gitignore, gitignore_bytes)
    elif gitignore.is_symlink() or gitignore.exists():
        gitignore.unlink()


def apply_tree(host: Path, source: Path, manifest: Path | None, apply: bool) -> dict:
    new_hashes = load_new_hashes(manifest)
    report = inspect_tree(host, new_hashes)
    report["apply"] = apply
    report["wrote"] = False
    report["restart"] = False
    missing_source = [rel for rel in INSTALL_PATHS if not (source / rel).is_file()]
    if missing_source:
        report["ok"] = False
        report["error"] = "Artifact is missing install files."
        report["missing_source"] = missing_source
        return report
    missing_hashes = [rel for rel in required_manifest_paths() if rel not in new_hashes]
    if missing_hashes:
        report["ok"] = False
        report["error"] = "Install manifest is missing required file hashes."
        report["missing_hashes"] = missing_hashes
        report["restart"] = False
        return report
    mismatches = []
    for rel in required_manifest_paths():
        actual = sha256(source / rel)
        if actual != new_hashes[rel]:
            mismatches.append({"path": rel, "sha256": actual, "expected": new_hashes[rel]})
    if mismatches:
        report["ok"] = False
        report["error"] = "Artifact bytes do not match the install manifest."
        report["source_mismatches"] = mismatches
        report["restart"] = False
        return report
    blocked = symlink_blocks(host)
    protected_before = protected_fingerprints(host)
    report["protected_before"] = protected_before
    report["restart"] = False
    if blocked:
        report["ok"] = False
        report["error"] = "Refusing to write through a symlink. Nothing was copied."
        report["symlink_blocked"] = blocked
        report["protected_after"] = protected_fingerprints(host)
        report["protected_unchanged"] = report["protected_before"] == report["protected_after"]
        return report
    if not report["ok"]:
        report["error"] = "Host files do not match the reviewed baseline. Nothing was copied."
        report["protected_after"] = protected_fingerprints(host)
        report["protected_unchanged"] = report["protected_before"] == report["protected_after"]
        return report
    if not apply:
        report["plan"] = [f"backup then replace {rel}" if (host / rel).exists() else f"add {rel}" for rel in INSTALL_PATHS]
        report["protected_after"] = protected_fingerprints(host)
        report["protected_unchanged"] = report["protected_before"] == report["protected_after"]
        return report
    originals: dict[str, bytes | None] = {}
    for rel in INSTALL_PATHS:
        path = host / rel
        originals[rel] = _read_nofollow(path) if path.is_file() and not path.is_symlink() else None
    gitignore = host / ".gitignore"
    gitignore_existed = gitignore.is_file() and not gitignore.is_symlink()
    gitignore_bytes = _read_nofollow(gitignore) if gitignore_existed else None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = host / "backups" / f"screenshots-{stamp}"
    try:
        blocked_again = symlink_blocks(host)
        if blocked_again:
            raise OSError("symlink appeared before write")
        backup.mkdir(parents=True, exist_ok=False)
        for rel in INSTALL_PATHS:
            dest = host / rel
            if originals[rel] is not None:
                target = backup / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, target)
        for rel in INSTALL_PATHS:
            dest = host / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / rel, dest)
        existing = gitignore_bytes.decode("utf-8") if gitignore_bytes is not None else ""
        lines = existing.splitlines()
        added = [line for line in ("data/screenshots/", "backups/") if line not in lines]
        if added:
            prefix = "" if not existing or existing.endswith("\n") else "\n"
            payload = (prefix + "\n".join(added) + "\n").encode("utf-8")
            flags = os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW
            if not gitignore.exists():
                flags |= os.O_CREAT
            fd = os.open(gitignore, flags, 0o644)
            try:
                os.write(fd, payload)
            finally:
                os.close(fd)
        protected_after = protected_fingerprints(host)
        if protected_after != protected_before:
            _restore(host, originals, gitignore_existed, gitignore_bytes)
            report["ok"] = False
            report["wrote"] = False
            report["restored"] = True
            report["error"] = "Protected files changed during install. The tree was restored. Do not restart."
            report["protected_after"] = protected_fingerprints(host)
            report["protected_unchanged"] = report["protected_before"] == report["protected_after"]
            return report
    except Exception:
        _restore(host, originals, gitignore_existed, gitignore_bytes)
        raise
    report["wrote"] = True
    report["backup"] = str(backup)
    report["gitignore_lines_added"] = added
    report["protected_after"] = protected_after
    report["protected_unchanged"] = True
    report["untouched_confirmed"] = [
        {"path": rel, "before": protected_before.get(rel), "after": protected_after.get(rel)}
        for rel in DO_NOT_TOUCH
    ]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Install screenshot files onto a checked host tree.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True, help="Unpacked artifact directory")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--apply", action="store_true", help="Copy files. Without this, print the plan only.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    host = args.root.expanduser().resolve()
    source = args.source.expanduser().resolve()
    manifest = args.manifest or (source / "docs" / "screenshot-install-manifest.json")
    try:
        report = apply_tree(host, source, manifest, args.apply)
    except Exception as exc:
        payload = {
            "ok": False,
            "wrote": False,
            "restart": False,
            "restored": True,
            "error": f"{type(exc).__name__}: {exc}. Install was rolled back. Do not restart.",
        }
        text = json.dumps(payload, indent=2)
        print(text)
        if args.out:
            args.out.write_text(text + "\n", encoding="utf-8")
        return 3
    report["restart"] = False
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0 if report["ok"] else 3


if __name__ == "__main__":
    sys.exit(main())
