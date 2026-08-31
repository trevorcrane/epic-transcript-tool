#!/usr/bin/env python3
"""Verify a hosted-staging transfer bundle before handoff.

The transfer bundle is the artifact intended for the first persistent Docker host.
This verifier extracts the bundle safely, validates the manifest/member list,
checks the embedded seed package checksum, then runs the seed-package verifier
against a target data directory. It gives Hermes a one-command preflight that
proves the bundle a host receives is self-contained and extractable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REQUIRED_MEMBERS = {
    "Dockerfile",
    "requirements.txt",
    "app.py",
    "scripts/hosted_staging_verify.py",
    "scripts/hosted_staging_bundle_verify.py",
    "scripts/hosted_staging_runbook.py",
    "scripts/hosted_staging_smoke.py",
    "scripts/phase1_matrix.py",
    "scripts/phase2_upload_smoke.py",
    "scripts/phase3_ui_contract_smoke.py",
    "docs/HOSTED_BACKEND_MIGRATION.md",
    "evidence/hosted-staging-seed.tar.gz",
    "transfer-manifest.json",
}
SEED_ARCNAME = "evidence/hosted-staging-seed.tar.gz"
MANIFEST_ARCNAME = "transfer-manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_safe_members(tar: tarfile.TarFile) -> list[str]:
    names = tar.getnames()
    for name in names:
        parts = Path(name).parts
        if name.startswith("/") or ".." in parts:
            raise SystemExit(f"unsafe transfer bundle member: {name}")
        member = tar.getmember(name)
        if not (member.isfile() or member.isdir()):
            raise SystemExit(f"unsupported transfer bundle member type: {name}")
    missing = sorted(REQUIRED_MEMBERS - set(names))
    if missing:
        raise SystemExit(f"transfer bundle missing members: {', '.join(missing)}")
    return names


def verify_bundle(bundle: Path, extract_to: Path | None = None) -> dict:
    bundle = bundle.expanduser().resolve()
    if not bundle.exists():
        raise SystemExit(f"transfer bundle not found: {bundle}")

    with tempfile.TemporaryDirectory(prefix="epic-transfer-verify-") as td:
        work = Path(td)
        with tarfile.open(bundle, "r:gz") as tar:
            names = assert_safe_members(tar)
            tar.extractall(work)

        manifest_path = work / MANIFEST_ARCNAME
        manifest = json.loads(manifest_path.read_text())
        manifest_members = manifest.get("members") or []
        names_match_manifest = names == manifest_members

        seed_path = work / SEED_ARCNAME
        seed_sha = sha256_file(seed_path)
        seed_sha_expected = manifest.get("seed_package_sha256")
        seed_sha_verified = seed_sha == seed_sha_expected

        target_dir = (extract_to.expanduser().resolve() if extract_to else work / "verified-data")
        verifier = work / "scripts" / "hosted_staging_verify.py"
        result = subprocess.run(
            [sys.executable, str(verifier), str(seed_path), "--extract-to", str(target_dir)],
            cwd=work,
            text=True,
            capture_output=True,
            check=False,
        )
        try:
            seed_report = json.loads(result.stdout)
        except json.JSONDecodeError:
            seed_report = {
                "ok": False,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }

        ok = bool(manifest.get("ok")) and names_match_manifest and seed_sha_verified and result.returncode == 0 and bool(seed_report.get("ok"))
        return {
            "ok": ok,
            "bundle": str(bundle),
            "bundle_size_bytes": bundle.stat().st_size,
            "member_count": len(names),
            "manifest_members_verified": names_match_manifest,
            "required_members_verified": True,
            "seed_package_sha256": seed_sha,
            "seed_package_sha256_verified": seed_sha_verified,
            "extract_to": str(target_dir),
            "seed_verify_returncode": result.returncode,
            "seed_verify": seed_report,
            "next_steps": manifest.get("next_steps", []),
            "runbook_command": manifest.get("runbook_command"),
            "smoke_command": manifest.get("smoke_command"),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="Path to hosted-staging-transfer-bundle.tar.gz")
    parser.add_argument(
        "--extract-to",
        type=Path,
        default=None,
        help="Optional data directory where the embedded seed DB should be verified/extracted",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional path to save the JSON verification report",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = verify_bundle(args.bundle, args.extract_to)
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.out:
        args.out.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        args.out.expanduser().resolve().write_text(text + "\n")
    print(text)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
