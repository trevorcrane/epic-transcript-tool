#!/usr/bin/env python3
"""Public Phase 2 non-YouTube media URL smoke test.

The release gate requires a supported public non-YouTube media URL, not only
uploads. This script creates a small spoken MP3 fixture under the app's public
/static folder, verifies it is reachable through the durable public hostname,
then submits that public MP3 URL to /api/transcribe-url. It uses only local
macOS speech generation, ffmpeg, yt-dlp direct media handling, and local Whisper.
"""
from __future__ import annotations

import json
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8090"
ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
TEXT = "Epic transcript machine phase two public URL test. Local whisper should transcribe this hosted MP3 without paid providers."
EXPECTED_WORDS = {"epic", "transcript", "machine", "phase", "public", "url", "hosted", "provider"}
OWNER = "phase2-url-smoke-" + secrets.token_urlsafe(24).replace("-", "_")
FIXTURE_NAME = "phase2-public-url.mp3"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)


def make_public_fixture() -> Path:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    if not shutil.which("say"):
        raise SystemExit("macOS 'say' command is required to generate the speech fixture")
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required to generate the public MP3 fixture")
    aiff = STATIC_DIR / "phase2-public-url.aiff"
    mp3 = STATIC_DIR / FIXTURE_NAME
    run(["say", "-o", str(aiff), TEXT])
    run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(mp3)])
    aiff.unlink(missing_ok=True)
    return mp3


def verify_fixture_url(url: str) -> dict:
    proc = subprocess.run(
        ["curl", "-sS", "-L", "-r", "0-255", "-o", "/tmp/epic-phase2-public-url-head.bin", "-w", "%{http_code} %{size_download} %{content_type}\n", url],
        capture_output=True,
        text=True,
        timeout=60,
    )
    parts = proc.stdout.strip().split()
    status = int(parts[0]) if parts and parts[0].isdigit() else 0
    size = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    content_type = parts[2] if len(parts) > 2 else ""
    return {"url": url, "http_status": status, "bytes": size, "content_type": content_type, "ok": status in {200, 206} and size > 0 and "audio" in content_type}


def transcribe_url(url: str) -> dict:
    proc = subprocess.run(
        ["curl", "-sS", "-L", "-X", "POST", f"{BASE}/api/transcribe-url", "-F", f"owner={OWNER}", "-F", f"url={url}", "-w", "\n%{http_code} %{time_total}\n"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    lines = proc.stdout.strip().splitlines()
    body = "\n".join(lines[:-1]) if len(lines) > 1 else proc.stdout
    status_line = lines[-1] if lines else "0 0"
    status_parts = status_line.split()
    status = int(status_parts[0]) if status_parts and status_parts[0].isdigit() else 0
    elapsed = float(status_parts[1]) if len(status_parts) > 1 else None
    row = {"http_status": status, "elapsed_seconds": elapsed, "ok": False}
    try:
        data = json.loads(body)
        rec = data.get("record", {})
        segs = rec.get("segments") or []
        transcript_words = set((rec.get("transcript") or "").lower().replace(",", "").replace(".", "").split())
        credible = len(EXPECTED_WORDS & transcript_words) >= 5
        row.update(
            api_ok=data.get("ok"), id=rec.get("id"), method=rec.get("method"), source_kind=rec.get("source_kind"),
            source_url=rec.get("source_url"), segment_count=len(segs), word_count=rec.get("word_count"),
            language=rec.get("language"), cache_hit=rec.get("cache_hit"), first=(segs[0].get("text") if segs else "")[:180],
            provider_attempts=rec.get("provider_attempts") or [],
        )
        row["ok"] = status == 200 and data.get("ok") is True and rec.get("source_kind") == "url" and rec.get("method") == "local-whisper" and credible and (rec.get("word_count") or 0) >= 8
    except Exception as exc:
        row.update(error=str(exc), body=body[:500], stderr=proc.stderr[:500])
    return row


def main() -> int:
    fixture = make_public_fixture()
    public_url = f"{BASE}/static/{FIXTURE_NAME}"
    fixture_check = verify_fixture_url(public_url)
    result = transcribe_url(public_url) if fixture_check["ok"] else {"ok": False, "skipped": "fixture URL was not publicly reachable"}
    payload = {
        "base_url": BASE,
        "fixture_path": str(fixture),
        "fixture_size": fixture.stat().st_size,
        "fixture_url_check": fixture_check,
        "result": result,
        "all_ok": fixture_check["ok"] and result.get("ok") is True,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
