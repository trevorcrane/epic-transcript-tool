#!/usr/bin/env python3
"""Read-only check before copying the screenshot files onto an existing host.

This does not deploy, restart, delete, or merge anything. Exit 0 means every
file this change would replace matches the reviewed baseline (or is already the
reviewed new bytes). Exit 3 means stop: the host copy differs and must not be
overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# main @ 28707a2, the parent of this change. These are the bytes Hermes may replace.
BASELINE = {
    "app.py": "763dfca680c0e1382d1eaae456bc981138174a36c58d6624a09ed5a96fc91a39",
    "static/index.html": "e71cba1071a4ec5b192fd41eea24f3e5323c2d78f1cb607e534281a59edd251e",
    "Dockerfile": "8530f77533423bd1e75833d934f9eef1a23e177fda7fcdc39e5ebd45ad836e24",
    "README.md": "ebcec1f13a0f3461346f787912ddbfbcbbca4b91579a513a08b15bf5fde2cbc0",
}
NEW_FILES = (
    "screenshots.py",
    "docs/SCREENSHOT_DEPLOY.md",
    "scripts/screenshot_host_preflight.py",
    "scripts/screenshot_host_apply.py",
)
DO_NOT_TOUCH = (
    ".env",
    "cloudflared.yml",
    "requirements.txt",
    "data/transcripts.db",
    "data/url_jobs.json",
    "data/phase3_gemini_usage.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify(exists: bool, current: str | None, baseline: str | None, new: str | None) -> str:
    if not exists:
        if baseline:
            return "missing"
        return "ready_to_add"
    if new and current == new:
        return "already_installed"
    if baseline and current == baseline:
        return "ready_to_replace"
    return "drift"


def git_report(root: Path) -> dict:
    if not (root / ".git").exists():
        return {"is_git": False, "head": None, "porcelain": [], "note": "Not a git checkout. The byte comparison is the gate."}
    def run(args: list[str]) -> str:
        return subprocess.check_output(args, cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
    try:
        head = run(["git", "rev-parse", "HEAD"])
        porcelain = [line for line in run(["git", "status", "--porcelain"]).splitlines() if line]
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        return {"is_git": True, "head": None, "porcelain": [], "note": f"git status failed: {exc}"}
    return {"is_git": True, "head": head, "expected_baseline_commit": "28707a2", "porcelain": porcelain}


def process_report(port: int) -> dict:
    listen = ""
    try:
        listen = subprocess.check_output(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        listen = ""
    processes = []
    try:
        ps = subprocess.check_output(["ps", "aux"], text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        ps = ""
    for line in ps.splitlines():
        if "app.py" in line and "grep" not in line and "screenshot_host_" not in line:
            processes.append(line)
    return {"port": port, "listen": listen, "app_py_processes": processes}


def tool_report() -> dict:
    return {
        "python": sys.version.split()[0],
        "ffmpeg": shutil.which("ffmpeg") or "",
        "ffprobe": shutil.which("ffprobe") or "",
        "yt_dlp": shutil.which("yt-dlp") or "",
    }


def load_new_hashes(manifest: Path | None) -> dict[str, str]:
    if manifest is None:
        candidate = ROOT / "docs" / "screenshot-install-manifest.json"
        manifest = candidate if candidate.is_file() else None
    if manifest is None or not manifest.is_file():
        return {}
    data = json.loads(manifest.read_text(encoding="utf-8"))
    install = data.get("install") or {}
    if not isinstance(install, dict):
        raise SystemExit("install manifest is not an object")
    return {str(k): str(v) for k, v in install.items()}


def inspect_tree(root: Path, new_hashes: dict[str, str] | None = None) -> dict:
    new_hashes = new_hashes or {}
    files = []
    blocking = []
    for rel, baseline in BASELINE.items():
        path = root / rel
        exists = path.is_file()
        current = sha256(path) if exists else None
        state = classify(exists, current, baseline, new_hashes.get(rel))
        files.append({"path": rel, "state": state, "sha256": current, "baseline": baseline, "new": new_hashes.get(rel)})
        if state in {"drift", "missing"}:
            blocking.append(rel)
    for rel in NEW_FILES:
        path = root / rel
        exists = path.is_file()
        current = sha256(path) if exists else None
        state = classify(exists, current, None, new_hashes.get(rel))
        # A new file with no published hash yet is still safe to add when absent.
        if exists and not new_hashes.get(rel):
            state = "drift"
        files.append({"path": rel, "state": state, "sha256": current, "baseline": None, "new": new_hashes.get(rel)})
        if state == "drift":
            blocking.append(rel)
    untouched = []
    for rel in DO_NOT_TOUCH:
        path = root / rel
        untouched.append({"path": rel, "exists": path.exists(), "sha256": sha256(path) if path.is_file() else None})
    gitignore = root / ".gitignore"
    gitignore_text = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    return {
        "ok": not blocking,
        "root": str(root),
        "blocking": blocking,
        "files": files,
        "do_not_touch": untouched,
        "gitignore_has_screenshot_ignore": "data/screenshots/" in gitignore_text.splitlines(),
        "gitignore_has_backup_ignore": "backups/" in gitignore_text.splitlines(),
        "git": git_report(root),
        "tools": tool_report(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check an existing Transcript Machine tree before screenshot install.")
    parser.add_argument("--root", type=Path, required=True, help="Production folder that already runs app.py")
    parser.add_argument("--manifest", type=Path, help="screenshot-install-manifest.json from the reviewed artifact")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--out", type=Path, help="Write the JSON report here as well as stdout")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(json.dumps({"ok": False, "error": f"root is not a directory: {root}"}))
        return 2
    report = inspect_tree(root, load_new_hashes(args.manifest))
    report["process"] = process_report(args.port)
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0 if report["ok"] else 3


if __name__ == "__main__":
    sys.exit(main())
