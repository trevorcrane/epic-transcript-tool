#!/usr/bin/env python3
"""Build a transfer bundle for the first hosted staging deployment.

The seed package alone is not enough for the selected persistent host. This
script creates one tarball containing the cache seed, host verification scripts,
release smoke runner, Dockerfile, and migration instructions so the host can be
seeded and smoked without relying on repo checkout state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED_PACKAGE = ROOT / "evidence" / "hosted-staging-seed.tar.gz"
DEFAULT_OUT = ROOT / "evidence" / "hosted-staging-transfer-bundle.tar.gz"
REQUIRED_PROJECT_FILES = (
    "Dockerfile",
    "requirements.txt",
    "app.py",
    "scripts/hosted_staging_verify.py",
    "scripts/hosted_staging_bundle_verify.py",
    "scripts/hosted_staging_smoke.py",
    "scripts/phase1_matrix.py",
    "scripts/phase2_upload_smoke.py",
    "scripts/phase3_ui_contract_smoke.py",
    "docs/HOSTED_BACKEND_MIGRATION.md",
)
SEED_ARCNAME = "evidence/hosted-staging-seed.tar.gz"
MANIFEST_ARCNAME = "transfer-manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_required_files(paths: Iterable[str]) -> list[str]:
    missing = [rel for rel in paths if not (ROOT / rel).exists()]
    if missing:
        raise SystemExit(f"cannot build hosted transfer bundle; missing: {', '.join(missing)}")
    return list(paths)


def build_transfer_manifest(seed_package: Path, members: list[str]) -> dict:
    seed_sha = sha256_file(seed_package)
    return {
        "ok": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed_package": str(seed_package.resolve()),
        "seed_package_arcname": SEED_ARCNAME,
        "seed_package_size_bytes": seed_package.stat().st_size,
        "seed_package_sha256": seed_sha,
        "members": members,
        "extract_command": "tar -xzf hosted-staging-transfer-bundle.tar.gz",
        "verify_command": "python3 scripts/hosted_staging_verify.py evidence/hosted-staging-seed.tar.gz --extract-to <persistent-data-dir>",
        "smoke_command": "python3 scripts/hosted_staging_smoke.py http://<staging-host> --out evidence/hosted-staging-smoke-report.json",
        "next_steps": [
            "tar -xzf hosted-staging-transfer-bundle.tar.gz",
            "python3 scripts/hosted_staging_verify.py evidence/hosted-staging-seed.tar.gz --extract-to <persistent-data-dir>",
            "docker build -t epic-transcript-machine .",
            "docker run --rm -p 8090:8090 -v <persistent-data-dir>:/data epic-transcript-machine",
            "python3 scripts/hosted_staging_smoke.py http://<staging-host> --out evidence/hosted-staging-smoke-report.json",
        ],
    }


def create_bundle(seed_package: Path, out: Path) -> dict:
    seed_package = seed_package.expanduser().resolve()
    out = out.expanduser().resolve()
    if not seed_package.exists():
        raise SystemExit(f"seed package not found: {seed_package}")

    project_files = validate_required_files(REQUIRED_PROJECT_FILES)
    members = [*project_files, SEED_ARCNAME, MANIFEST_ARCNAME]
    manifest = build_transfer_manifest(seed_package, members)

    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="epic-staging-transfer-") as td:
        manifest_path = Path(td) / "transfer-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        with tarfile.open(out, "w:gz") as tar:
            for rel in project_files:
                tar.add(ROOT / rel, arcname=rel)
            tar.add(seed_package, arcname=SEED_ARCNAME)
            tar.add(manifest_path, arcname=MANIFEST_ARCNAME)

    return {
        **manifest,
        "bundle": str(out),
        "bundle_size_bytes": out.stat().st_size,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-package", type=Path, default=DEFAULT_SEED_PACKAGE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = create_bundle(args.seed_package, args.out)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
