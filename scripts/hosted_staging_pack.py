#!/usr/bin/env python3
"""Create the hosted-staging seed package for EPIC Transcript Machine.

The first hosted deployment must start with the current transcript cache. This
script builds a small tarball containing transcripts.db plus a manifest so the
staging host can verify the seed before Phase 1/2/3 smoke tests run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DB = ROOT / "data" / "transcripts.db"
DEFAULT_OUT = ROOT / "evidence" / "hosted-staging-seed.tar.gz"
REQUIRED_MEDIA_IDS = (
    "v34Eg12mhDM",  # Phase 1 regression automatic-caption video
    "dQw4w9WgXcQ",  # manual-caption control
    "SXHMnicI6Pg",  # bounded Shorts fixture in phase1_matrix.py
    "aircAruvnKk",  # moderate long cached video
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def count_for_media_id(conn: sqlite3.Connection, media_id: str) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM transcripts WHERE media_id=?", (media_id,)
        ).fetchone()[0]
    )


def inspect_db(db_path: Path) -> dict:
    if not db_path.exists():
        raise SystemExit(f"source db not found: {db_path}")
    conn = sqlite3.connect(db_path)
    try:
        if not table_exists(conn, "transcripts"):
            raise SystemExit(f"source db has no transcripts table: {db_path}")
        transcript_count = int(conn.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0])
        required = {media_id: count_for_media_id(conn, media_id) for media_id in REQUIRED_MEDIA_IDS}
    finally:
        conn.close()
    return {
        "source_db": str(db_path.resolve()),
        "size_bytes": db_path.stat().st_size,
        "sha256": sha256_file(db_path),
        "transcript_count": transcript_count,
        "required_media_ids": required,
    }


def build_manifest(db_path: Path) -> dict:
    details = inspect_db(db_path)
    ok = details["transcript_count"] > 0 and all(count > 0 for count in details["required_media_ids"].values())
    manifest = {
        "ok": ok,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **details,
        "target_path": "/data/transcripts.db",
        "verify_commands": [
            'docker run --rm -p 8090:8090 -v "$PWD/data-hosted-test:/data" epic-transcript-machine',
            "docker exec <container> python - <<'PY'\nimport os, sqlite3\np='/data/transcripts.db'\nprint(os.path.exists(p), os.stat(p).st_size)\ncon=sqlite3.connect(p)\nprint(con.execute('select count(*) from transcripts').fetchone()[0])\nPY",
            "./.venv/bin/python scripts/hosted_staging_smoke.py http://<staging-host> --out evidence/hosted-staging-smoke-report.json",
        ],
    }
    return manifest


def create_package(source_db: Path, out: Path) -> dict:
    source_db = source_db.expanduser().resolve()
    out = out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(source_db)
    with tempfile.TemporaryDirectory(prefix="epic-staging-seed-") as td:
        tmp = Path(td)
        db_copy = tmp / "transcripts.db"
        manifest_path = tmp / "manifest.json"
        shutil.copy2(source_db, db_copy)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        with tarfile.open(out, "w:gz") as tar:
            tar.add(db_copy, arcname="transcripts.db")
            tar.add(manifest_path, arcname="manifest.json")
    return {**manifest, "package": str(out), "package_size_bytes": out.stat().st_size}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = create_package(args.source_db, args.out)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
