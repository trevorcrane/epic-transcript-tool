#!/usr/bin/env python3
"""Verify and optionally extract a hosted-staging seed package.

Run this on the selected persistent host before starting the container. It checks
that the tarball manifest matches the packaged transcripts.db, verifies required
cached media IDs are present, and can extract the database into the mounted data
directory expected by the EPIC Transcript Machine container.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tarfile
import tempfile
from pathlib import Path

REQUIRED_MEMBERS = {"transcripts.db", "manifest.json"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract_member(tar: tarfile.TarFile, member_name: str, target_dir: Path) -> Path:
    member = tar.getmember(member_name)
    if member.isdir() or member_name.startswith("/") or ".." in Path(member_name).parts:
        raise SystemExit(f"unsafe seed package member: {member_name}")
    tar.extract(member, target_dir)
    return target_dir / member_name


def inspect_db(db_path: Path, required_media_ids: list[str]) -> tuple[int, dict[str, int]]:
    conn = sqlite3.connect(db_path)
    try:
        transcript_count = int(conn.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0])
        required = {
            media_id: int(
                conn.execute(
                    "SELECT COUNT(*) FROM transcripts WHERE media_id=?", (media_id,)
                ).fetchone()[0]
            )
            for media_id in required_media_ids
        }
    finally:
        conn.close()
    return transcript_count, required


def verify_package(package: Path, extract_to: Path | None = None) -> dict:
    package = package.expanduser().resolve()
    if not package.exists():
        raise SystemExit(f"seed package not found: {package}")

    with tempfile.TemporaryDirectory(prefix="epic-staging-verify-") as td:
        tmp = Path(td)
        with tarfile.open(package, "r:gz") as tar:
            names = set(tar.getnames())
            missing = sorted(REQUIRED_MEMBERS - names)
            if missing:
                raise SystemExit(f"seed package missing members: {', '.join(missing)}")
            db_path = safe_extract_member(tar, "transcripts.db", tmp)
            manifest_path = safe_extract_member(tar, "manifest.json", tmp)

        manifest = json.loads(manifest_path.read_text())
        actual_sha = sha256_file(db_path)
        expected_sha = manifest.get("sha256")
        required_ids = list((manifest.get("required_media_ids") or {}).keys())
        transcript_count, required_counts = inspect_db(db_path, required_ids)
        sha_ok = actual_sha == expected_sha
        count_ok = transcript_count == int(manifest.get("transcript_count", -1))
        required_ok = all(count > 0 for count in required_counts.values())
        ok = bool(manifest.get("ok")) and sha_ok and count_ok and required_ok

        extracted_db = None
        if extract_to is not None:
            extract_to = extract_to.expanduser().resolve()
            extract_to.mkdir(parents=True, exist_ok=True)
            extracted_db_path = extract_to / "transcripts.db"
            shutil.copy2(db_path, extracted_db_path)
            extracted_db = str(extracted_db_path)

        return {
            "ok": ok,
            "package": str(package),
            "package_size_bytes": package.stat().st_size,
            "sha256": actual_sha,
            "sha256_verified": sha_ok,
            "transcript_count": transcript_count,
            "transcript_count_verified": count_ok,
            "required_media_ids": required_counts,
            "required_media_ids_verified": required_ok,
            "target_path": manifest.get("target_path", "/data/transcripts.db"),
            "extracted_db": extracted_db,
            "next_smokes": manifest.get("verify_commands", []),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="Path to hosted-staging-seed.tar.gz")
    parser.add_argument(
        "--extract-to",
        type=Path,
        default=None,
        help="Optional host data directory where transcripts.db should be copied",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = verify_package(args.package, args.extract_to)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
