#!/usr/bin/env python3
"""Consistent outside-tree backup for the screenshot install.

This is not the installer. It does not restart the service and it does not
write under the live tree. The database copy is one sqlite3 backup snapshot.
Live WAL and SHM files are not copied next to that snapshot.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
import sys
from pathlib import Path


LIVE_SQLITE_SIDECARS = {"transcripts.db-wal", "transcripts.db-shm"}
SNAPSHOT_DB = "transcripts.db"
SUMS_NAME = "SHA256SUMS"


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_payload_files(root: Path) -> list[Path]:
    """Regular files under root, not this script's sum files and not symlink targets."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        kept: list[str] = []
        for name in sorted(dirnames):
            child = current / name
            if child.is_symlink():
                _fail(f"refusing symlink in backup: {child}")
            kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            if name in {SUMS_NAME, SUMS_NAME + ".tmp"}:
                continue
            path = current / name
            if path.is_symlink() or not path.is_file():
                _fail(f"refusing non-regular file in backup: {path}")
            found.append(path)
    return found


def hash_listing(root: Path) -> str:
    lines = []
    for path in iter_payload_files(root):
        rel = path.relative_to(root).as_posix()
        lines.append(f"{_sha256(path)}  {rel}")
    if not lines:
        _fail("hash listing is empty")
    return "\n".join(lines) + "\n"


def write_verified_sums(dest: Path) -> str:
    listing = hash_listing(dest)
    tmp = dest / (SUMS_NAME + ".tmp")
    sums = dest / SUMS_NAME
    if sums.exists() or tmp.exists():
        _fail("refusing to replace an existing hash listing")
    tmp.write_text(listing, encoding="utf-8")
    reread = tmp.read_text(encoding="utf-8")
    if reread != listing or not reread.strip():
        tmp.unlink(missing_ok=True)
        _fail("hash listing was empty or did not read back")
    for line in reread.splitlines():
        digest, rel = line.split("  ", 1)
        actual = _sha256(dest / rel)
        if actual != digest:
            tmp.unlink(missing_ok=True)
            _fail(f"hash mismatch before publish: {rel}")
    os.replace(tmp, sums)
    confirmed = verify_sums(dest)
    if confirmed != listing:
        sums.unlink(missing_ok=True)
        _fail("published hash listing did not verify")
    return confirmed


def verify_sums(dest: Path) -> str:
    sums = dest / SUMS_NAME
    if not sums.is_file() or sums.is_symlink():
        _fail("SHA256SUMS is missing")
    text = sums.read_text(encoding="utf-8")
    if not text.strip():
        _fail("SHA256SUMS is empty")
    listed: set[str] = set()
    for line in text.splitlines():
        if "  " not in line:
            _fail("SHA256SUMS line is not 'digest  path'")
        digest, rel = line.split("  ", 1)
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            _fail(f"SHA256SUMS path is not inside the backup: {rel}")
        path = dest / rel
        if not path.is_file() or path.is_symlink():
            _fail(f"SHA256SUMS names a missing file: {rel}")
        if _sha256(path) != digest:
            _fail(f"SHA256SUMS mismatch: {rel}")
        listed.add(rel)
    for path in iter_payload_files(dest):
        rel = path.relative_to(dest).as_posix()
        if rel not in listed:
            _fail(f"SHA256SUMS does not list {rel}")
    return text


def _copy_regular_tree(source: Path, dest: Path, skip_names: set[str]) -> None:
    for dirpath, dirnames, filenames in os.walk(source, followlinks=False):
        current = Path(dirpath)
        kept: list[str] = []
        for name in sorted(dirnames):
            child = current / name
            if child.is_symlink():
                _fail(f"refusing to follow symlink: {child}")
            kept.append(name)
        dirnames[:] = kept
        target = dest / current.relative_to(source)
        target.mkdir(parents=True, exist_ok=True)
        for name in sorted(filenames):
            child = current / name
            if child.is_symlink() or not child.is_file():
                _fail(f"refusing to copy non-regular file: {child}")
            if name in skip_names:
                continue
            shutil.copy2(child, target / name)


def snapshot_sqlite(source_db: Path, dest_db: Path) -> None:
    """Write one consistent database file. Do not copy the live WAL or SHM."""
    if not source_db.is_file() or source_db.is_symlink():
        _fail(f"live database is not a regular file: {source_db}")
    dest_db.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    target = sqlite3.connect(dest_db)
    try:
        source.backup(target)
        # The snapshot is one file. Leave the live database in WAL mode.
        target.execute("PRAGMA journal_mode=DELETE")
        target.commit()
    finally:
        target.close()
        source.close()
    for suffix in ("-wal", "-shm"):
        sidecar = dest_db.parent / (SNAPSHOT_DB + suffix)
        if sidecar.exists() or sidecar.is_symlink():
            sidecar.unlink()
    if (dest_db.parent / (SNAPSHOT_DB + "-wal")).exists() or (dest_db.parent / (SNAPSHOT_DB + "-shm")).exists():
        _fail("snapshot directory received a live WAL or SHM sidecar")


def backup_tree(root: Path, dest: Path, plist: Path) -> str:
    root = root.resolve()
    dest = dest.resolve()
    plist = plist.resolve()
    if dest == root or root in dest.parents:
        _fail("backup destination must be outside the live tree")
    if dest.exists() and any(dest.iterdir()):
        _fail("backup destination is not empty")
    data = root / "data"
    env = root / ".env"
    db = data / SNAPSHOT_DB
    if not data.is_dir() or data.is_symlink():
        _fail("live data directory is missing or is a symlink")
    if not env.is_file() or env.is_symlink():
        _fail("live .env is missing or is a symlink")
    if not plist.is_file() or plist.is_symlink():
        _fail("launchd configuration is missing or is a symlink")
    dest.mkdir(parents=True, exist_ok=True)
    try:
        _copy_regular_tree(data, dest / "data", skip_names={SNAPSHOT_DB, *LIVE_SQLITE_SIDECARS})
        snapshot_sqlite(db, dest / "data" / SNAPSHOT_DB)
        shutil.copy2(env, dest / ".env")
        shutil.copy2(plist, dest / "launchd.plist")
        for sidecar in LIVE_SQLITE_SIDECARS:
            if (dest / "data" / sidecar).exists():
                _fail(f"backup must not contain {sidecar}")
        listing = write_verified_sums(dest)
    except Exception:
        partial = dest / SUMS_NAME
        if partial.exists():
            partial.unlink()
        raise
    sys.stdout.write(listing)
    return listing


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy a consistent outside-tree backup and hash it.")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--dest", type=Path)
    parser.add_argument("--plist", type=Path)
    parser.add_argument("--verify", type=Path, help="Re-check an existing backup directory.")
    args = parser.parse_args()
    try:
        if args.verify:
            sys.stdout.write(verify_sums(args.verify.resolve()))
            return 0
        if not args.root or not args.dest or not args.plist:
            _fail("backup requires --root, --dest, and --plist")
        backup_tree(args.root, args.dest, args.plist)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
