from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def make_seed_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE transcripts (
            id TEXT PRIMARY KEY,
            media_id TEXT,
            title TEXT,
            word_count INTEGER,
            segment_count INTEGER
        )
        """
    )
    rows = [
        ("regression", "v34Eg12mhDM", "Regression", 15744, 1460),
        ("manual", "dQw4w9WgXcQ", "Manual Caption", 366, 61),
        ("shorts", "SXHMnicI6Pg", "Shorts", 3, 2),
        ("moderate", "aircAruvnKk", "Moderate Long", 3360, 286),
    ]
    conn.executemany("INSERT INTO transcripts VALUES (?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()


def test_hosted_staging_pack_copies_seed_db_and_writes_manifest(tmp_path):
    seed_db = tmp_path / "transcripts.db"
    out = tmp_path / "hosted-staging-seed.tar.gz"
    make_seed_db(seed_db)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hosted_staging_pack.py"),
            "--source-db",
            str(seed_db),
            "--out",
            str(out),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["transcript_count"] == 4
    assert payload["required_media_ids"]["v34Eg12mhDM"] == 1
    assert payload["required_media_ids"]["dQw4w9WgXcQ"] == 1
    assert payload["required_media_ids"]["SXHMnicI6Pg"] == 1
    assert payload["required_media_ids"]["aircAruvnKk"] == 1
    assert len(payload["sha256"]) == 64
    assert out.exists()

    with tarfile.open(out, "r:gz") as tar:
        names = tar.getnames()
        assert "transcripts.db" in names
        assert "manifest.json" in names
        manifest_file = tar.extractfile("manifest.json")
        assert manifest_file is not None
        manifest = json.loads(manifest_file.read().decode())

    assert manifest["sha256"] == payload["sha256"]
    assert manifest["transcript_count"] == 4
    assert "docker run" in manifest["verify_commands"][0]


def test_hosted_staging_verify_validates_and_extracts_seed_package(tmp_path):
    seed_db = tmp_path / "transcripts.db"
    out = tmp_path / "hosted-staging-seed.tar.gz"
    target = tmp_path / "staging-data"
    make_seed_db(seed_db)
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hosted_staging_pack.py"),
            "--source-db",
            str(seed_db),
            "--out",
            str(out),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hosted_staging_verify.py"),
            str(out),
            "--extract-to",
            str(target),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["extracted_db"] == str((target / "transcripts.db").resolve())
    assert payload["transcript_count"] == 4
    assert payload["required_media_ids"]["v34Eg12mhDM"] == 1
    assert payload["sha256_verified"] is True

    extracted = target / "transcripts.db"
    assert extracted.exists()
    conn = sqlite3.connect(extracted)
    try:
        assert conn.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0] == 4
    finally:
        conn.close()
