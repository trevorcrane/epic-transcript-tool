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
    assert "scripts/hosted_staging_smoke.py" in manifest["verify_commands"][-1]
    assert "--out evidence/hosted-staging-smoke-report.json" in manifest["verify_commands"][-1]


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


def test_hosted_staging_smoke_print_plan_lists_all_release_lanes(tmp_path):
    report_path = tmp_path / "hosted-staging-smoke-report.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hosted_staging_smoke.py"),
            "https://staging.example.test",
            "--print-plan",
            "--out",
            str(report_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    saved_payload = json.loads(report_path.read_text())
    assert saved_payload == payload
    assert payload["ok"] is True
    assert payload["base_url"] == "https://staging.example.test"
    assert [step["phase"] for step in payload["steps"]] == ["phase1", "phase2", "phase3"]
    assert payload["steps"][0]["command"][-2:] == ["scripts/phase1_matrix.py", "https://staging.example.test"]
    assert payload["steps"][1]["command"][-2:] == ["scripts/phase2_upload_smoke.py", "https://staging.example.test"]
    assert payload["steps"][2]["command"][-2:] == ["scripts/phase3_ui_contract_smoke.py", "https://staging.example.test"]


def make_transfer_bundle(tmp_path: Path) -> tuple[Path, Path, Path]:
    seed_db = tmp_path / "transcripts.db"
    seed_package = tmp_path / "hosted-staging-seed.tar.gz"
    bundle = tmp_path / "hosted-staging-transfer-bundle.tar.gz"
    make_seed_db(seed_db)
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hosted_staging_pack.py"),
            "--source-db",
            str(seed_db),
            "--out",
            str(seed_package),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hosted_staging_bundle.py"),
            "--seed-package",
            str(seed_package),
            "--out",
            str(bundle),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return seed_db, seed_package, bundle


def test_hosted_staging_bundle_includes_seed_scripts_and_manifest(tmp_path):
    _seed_db, seed_package, bundle = make_transfer_bundle(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hosted_staging_bundle.py"),
            "--seed-package",
            str(seed_package),
            "--out",
            str(bundle),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["bundle"] == str(bundle.resolve())
    assert payload["seed_package"] == str(seed_package.resolve())
    assert payload["next_steps"][0].startswith("tar -xzf")
    assert "scripts/hosted_staging_verify.py" in payload["members"]
    assert "scripts/hosted_staging_bundle_verify.py" in payload["members"]
    assert "scripts/hosted_staging_runbook.py" in payload["members"]
    assert "scripts/hosted_staging_smoke.py" in payload["members"]
    assert "Dockerfile" in payload["members"]
    assert "docs/HOSTED_BACKEND_MIGRATION.md" in payload["members"]
    assert "evidence/hosted-staging-seed.tar.gz" in payload["members"]
    assert "transfer-manifest.json" in payload["members"]

    with tarfile.open(bundle, "r:gz") as tar:
        names = tar.getnames()
        assert names == payload["members"]
        manifest_file = tar.extractfile("transfer-manifest.json")
        assert manifest_file is not None
        manifest = json.loads(manifest_file.read().decode())

    assert manifest["seed_package_sha256"] == payload["seed_package_sha256"]
    assert manifest["verify_command"] == "python3 scripts/hosted_staging_verify.py evidence/hosted-staging-seed.tar.gz --extract-to <persistent-data-dir>"
    assert "scripts/hosted_staging_runbook.py" in manifest["runbook_command"]


def test_hosted_staging_bundle_verify_extracts_embedded_seed(tmp_path):
    _seed_db, _seed_package, bundle = make_transfer_bundle(tmp_path)
    target = tmp_path / "verified-host-data"
    report = tmp_path / "transfer-verify-report.json"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hosted_staging_bundle_verify.py"),
            str(bundle),
            "--extract-to",
            str(target),
            "--out",
            str(report),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    saved_payload = json.loads(report.read_text())
    assert saved_payload == payload
    assert payload["ok"] is True
    assert payload["manifest_members_verified"] is True
    assert payload["seed_package_sha256_verified"] is True
    assert payload["seed_verify"]["ok"] is True
    assert payload["seed_verify"]["transcript_count"] == 4
    assert payload["seed_verify"]["required_media_ids"]["v34Eg12mhDM"] == 1
    assert Path(payload["seed_verify"]["extracted_db"]).exists()
    assert "scripts/hosted_staging_runbook.py" in payload["runbook_command"]
    assert "scripts/hosted_staging_smoke.py" in payload["smoke_command"]


def test_hosted_staging_runbook_prints_verifiable_host_plan(tmp_path):
    data_dir = tmp_path / "persistent-data"
    report = tmp_path / "hosted-staging-smoke-report.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hosted_staging_runbook.py"),
            "http://staging.example.test",
            "--data-dir",
            str(data_dir),
            "--out",
            str(report),
            "--print-plan",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["staging_url"] == "http://staging.example.test"
    assert payload["data_dir"] == str(data_dir.resolve())
    assert payload["smoke_report"] == str(report.resolve())
    assert [step["name"] for step in payload["steps"]] == [
        "verify_seed_into_persistent_data",
        "docker_build",
        "docker_run_detached",
        "wait_for_health",
        "phase_1_2_3_smoke",
    ]
    assert payload["steps"][0]["command"][-2:] == ["--extract-to", str(data_dir.resolve())]
    assert payload["steps"][-1]["command"][-2:] == ["--out", str(report.resolve())]
