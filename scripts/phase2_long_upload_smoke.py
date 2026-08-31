#!/usr/bin/env python3
"""Public Phase 2 proof for a 30+ minute uploaded recording.

Creates a free local speech fixture, pads it to more than 30 minutes with
silence, uploads it to the public no-login API, and verifies the saved record
preserves duration metadata plus credible transcript text.
"""
from __future__ import annotations

import json
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8090"
TEXT = "Epic transcript machine long upload proof. This recording is longer than thirty minutes and should transcribe without a paid provider."
EXPECTED_WORDS = {"epic", "transcript", "machine", "long", "upload", "thirty", "minutes", "provider"}
OWNER = "phase2-long-upload-" + secrets.token_urlsafe(24).replace("-", "_")
MIN_DURATION_SECONDS = 30 * 60


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)


def make_long_fixture(work: Path) -> Path:
    if not shutil.which("say"):
        raise SystemExit("macOS 'say' command is required to generate the speech fixture")
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required to generate the long upload fixture")
    aiff = work / "spoken.aiff"
    speech_wav = work / "speech.wav"
    long_mp3 = work / "phase2-long-upload-31min.mp3"
    run(["say", "-o", str(aiff), TEXT])
    run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(speech_wav)])
    # apad extends with silence. Low bitrate keeps the public upload small while
    # still forcing the server to handle long-duration media metadata.
    run([
        "ffmpeg", "-y", "-i", str(speech_wav), "-af", "apad=whole_dur=1862",
        "-t", "1862", "-ar", "16000", "-ac", "1", "-b:a", "32k", str(long_mp3),
    ], timeout=240)
    return long_mp3


def upload(path: Path) -> dict:
    cmd = [
        "curl", "-sS", "-L", "-X", "POST", f"{BASE}/api/transcribe-upload",
        "-F", f"owner={OWNER}", "-F", f"file=@{path}", "-w", "\n%{http_code} %{time_total}\n",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    output = proc.stdout.strip().splitlines()
    body = "\n".join(output[:-1]) if len(output) > 1 else proc.stdout
    status_line = output[-1] if output else "0 0"
    parts = status_line.split()
    status = int(parts[0]) if parts else 0
    elapsed = float(parts[1]) if len(parts) > 1 else None
    row = {"file": path.name, "bytes": path.stat().st_size, "http_status": status, "elapsed_seconds": elapsed, "ok": False}
    try:
        data = json.loads(body)
        rec = data.get("record", {})
        text = (rec.get("transcript") or "").lower()
        credible = len(EXPECTED_WORDS & set(text.replace(",", "").replace(".", "").split())) >= 6
        row.update(
            api_ok=data.get("ok"), id=rec.get("id"), method=rec.get("method"),
            source_kind=rec.get("source_kind"), duration_seconds=rec.get("duration_seconds"),
            segment_count=rec.get("segment_count"), word_count=rec.get("word_count"),
            language=rec.get("language"), cache_hit=rec.get("cache_hit"),
            transcript_excerpt=(rec.get("transcript") or "")[:220],
        )
        row["ok"] = (
            status == 200 and data.get("ok") is True and rec.get("method") == "local-whisper"
            and (rec.get("duration_seconds") or 0) >= MIN_DURATION_SECONDS
            and (rec.get("word_count") or 0) >= 8 and credible
        )
    except Exception as exc:
        row.update(error=str(exc), body=body[:500], stderr=proc.stderr[:500])
    return row


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="epic-phase2-long-upload-") as tmp:
        fixture = make_long_fixture(Path(tmp))
        result = upload(fixture)
    payload = {"base_url": BASE, "owner_header_used": True, "min_duration_seconds": MIN_DURATION_SECONDS, "result": result, "all_ok": result["ok"]}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
