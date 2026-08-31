#!/usr/bin/env python3
"""Public Phase 2 upload smoke test using local macOS speech fixtures.

This verifies that the deployed API can process uploaded media through the
free local Whisper path. It intentionally avoids paid providers and secrets.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8090"
TEXT = "Epic transcript machine phase two public upload test. Local whisper should transcribe this audio without a paid provider."
EXPECTED_WORDS = {"epic", "transcript", "machine", "phase", "upload", "test", "whisper", "transcribe"}


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)


def make_fixtures(work: Path) -> list[Path]:
    aiff = work / "phase2.aiff"
    if not shutil.which("say"):
        raise SystemExit("macOS 'say' command is required to generate the speech fixture")
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required to generate upload fixtures")
    run(["say", "-o", str(aiff), TEXT])
    wav = work / "phase2.wav"
    mp3 = work / "phase2.mp3"
    mp4 = work / "phase2.mp4"
    run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(wav)])
    run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(mp3)])
    run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:d=5",
        "-i", str(aiff), "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", str(mp4)
    ])
    return [wav, mp3, mp4]


def upload(path: Path) -> dict:
    cmd = [
        "curl", "-sS", "-L", "-X", "POST", f"{BASE}/api/transcribe-upload",
        "-F", f"file=@{path}", "-w", "\n%{http_code} %{time_total}\n",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    output = proc.stdout.strip().splitlines()
    body = "\n".join(output[:-1]) if len(output) > 1 else proc.stdout
    status_line = output[-1] if output else "0 0"
    status = int(status_line.split()[0]) if status_line.split() else 0
    row = {"file": path.name, "http_status": status, "ok": False}
    try:
        data = json.loads(body)
        rec = data.get("record", {})
        segs = rec.get("segments") or []
        first = (segs[0].get("text") if segs else "") or ""
        words = set(first.lower().replace(",", "").replace(".", "").split())
        credible = len(EXPECTED_WORDS & words) >= 5
        row.update(
            api_ok=data.get("ok"), method=rec.get("method"), source_kind=rec.get("source_kind"),
            segment_count=len(segs), word_count=rec.get("word_count"), first=first[:160],
        )
        row["ok"] = status == 200 and data.get("ok") is True and rec.get("method") == "local-whisper" and credible and (rec.get("word_count") or 0) >= 8
    except Exception as exc:
        row.update(error=str(exc), body=body[:300], stderr=proc.stderr[:300])
    return row


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="epic-phase2-upload-") as tmp:
        fixtures = make_fixtures(Path(tmp))
        results = [upload(path) for path in fixtures]
    payload = {"base_url": BASE, "results": results, "all_ok": all(r["ok"] for r in results)}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
