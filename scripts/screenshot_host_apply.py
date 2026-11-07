#!/usr/bin/env python3
"""Copy the reviewed screenshot files only after the preflight gate passes.

Default mode prints the plan and writes nothing. --apply copies files and
makes a backup. It does not restart the server, touch .env, or touch the
transcript database.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from screenshot_host_preflight import DO_NOT_TOUCH, inspect_tree, load_new_hashes, sha256


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


def apply_tree(host: Path, source: Path, manifest: Path | None, apply: bool) -> dict:
    new_hashes = load_new_hashes(manifest)
    report = inspect_tree(host, new_hashes)
    report["apply"] = apply
    report["wrote"] = False
    if not report["ok"]:
        report["error"] = "Host files do not match the reviewed baseline. Nothing was copied."
        return report
    missing_source = [rel for rel in INSTALL_PATHS if not (source / rel).is_file()]
    if missing_source:
        report["ok"] = False
        report["error"] = "Artifact is missing install files."
        report["missing_source"] = missing_source
        return report
    mismatches = []
    for rel, expected in new_hashes.items():
        if rel not in INSTALL_PATHS:
            continue
        actual = sha256(source / rel)
        if actual != expected:
            mismatches.append({"path": rel, "sha256": actual, "expected": expected})
    if mismatches:
        report["ok"] = False
        report["error"] = "Artifact bytes do not match the install manifest."
        report["source_mismatches"] = mismatches
        return report
    if not apply:
        report["plan"] = [f"backup then replace {rel}" if (host / rel).exists() else f"add {rel}" for rel in INSTALL_PATHS]
        return report
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = host / "backups" / f"screenshots-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    for rel in INSTALL_PATHS:
        dest = host / rel
        if dest.exists():
            target = backup / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, target)
    for rel in INSTALL_PATHS:
        dest = host / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, dest)
    gitignore = host / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    lines = existing.splitlines()
    added = []
    for line in ("data/screenshots/", "backups/"):
        if line not in lines:
            added.append(line)
    if added:
        prefix = "" if not existing or existing.endswith("\n") else "\n"
        with gitignore.open("a", encoding="utf-8") as handle:
            handle.write(prefix + "\n".join(added) + "\n")
    report["wrote"] = True
    report["backup"] = str(backup)
    report["gitignore_lines_added"] = added
    report["untouched_confirmed"] = []
    for rel in DO_NOT_TOUCH:
        path = host / rel
        report["untouched_confirmed"].append({"path": rel, "exists": path.exists(), "sha256": sha256(path) if path.is_file() else None})
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
    report = apply_tree(host, source, manifest, args.apply)
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0 if report["ok"] else 3


if __name__ == "__main__":
    sys.exit(main())
