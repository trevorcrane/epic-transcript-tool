"""Record the real executables visible to this process. Does not stub PATH."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _version(path: str | None) -> str:
    if not path:
        return ""
    try:
        proc = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unavailable: {exc}"
    text = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
    return text[0] if text else f"exit {proc.returncode}"


def test_toolchain_provenance_uses_this_process_path(tmp_path, monkeypatch):
    """Fail closed if a test stub is what `which` finds. Do not invent a pass."""
    monkeypatch.delenv("YT_DLP_BIN", raising=False)
    monkeypatch.delenv("FFMPEG_BIN", raising=False)
    report = {
        "PATH": os.environ.get("PATH", ""),
        "python": sys.executable,
        "python_version": sys.version.split()[0],
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "yt_dlp": shutil.which("yt-dlp"),
    }
    report["ffmpeg_version"] = _version(report["ffmpeg"])
    report["ffprobe_version"] = _version(report["ffprobe"])
    report["yt_dlp_version"] = _version(report["yt_dlp"])
    out = tmp_path / "toolchain.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("TOOLCHAIN " + json.dumps(report))
    for name in ("ffmpeg", "ffprobe"):
        resolved = report[name]
        assert resolved, f"{name} is not on PATH"
        assert "pytest-" not in resolved
        assert resolved == shutil.which(name)
    if report["yt_dlp"]:
        assert "pytest-" not in report["yt_dlp"]
        assert Path(report["yt_dlp"]).is_file()
    else:
        # Honest absence. Screenshot fault tests pass a local stub path and do not use PATH.
        assert report["yt_dlp"] is None
