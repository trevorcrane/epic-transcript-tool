#!/usr/bin/env python3
"""Public Phase 2 upload smoke test using local macOS speech fixtures.

This verifies that the deployed API can process uploaded media through the
free local Whisper path. It intentionally avoids paid providers and secrets.
It also proves upload cache reuse and signed transcript downloads for one
public upload record, which are Phase 2 release-gate requirements.
"""
from __future__ import annotations

import json
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8090"
TEXT = "Epic transcript machine phase two public upload test. Local whisper should transcribe this audio without a paid provider."
EXPECTED_WORDS = {"epic", "transcript", "machine", "phase", "upload", "test", "whisper", "transcribe"}
OWNER = "phase2-smoke-" + secrets.token_urlsafe(24).replace("-", "_")


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
    m4a = work / "phase2.m4a"
    mp4 = work / "phase2.mp4"
    mov = work / "phase2.mov"
    webm = work / "phase2.webm"
    run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(wav)])
    run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(mp3)])
    run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1", "-c:a", "aac", str(m4a)])
    for target in (mp4, mov):
        run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:d=5",
            "-i", str(aiff), "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", str(target)
        ])
    run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:d=5",
        "-i", str(aiff), "-shortest", "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p",
        "-c:a", "libopus", str(webm)
    ])
    return [wav, mp3, m4a, mp4, mov, webm]


def upload(path: Path, label: str | None = None) -> dict:
    cmd = [
        "curl", "-sS", "-L", "-X", "POST", f"{BASE}/api/transcribe-upload",
        "-F", f"owner={OWNER}", "-F", f"file=@{path}", "-w", "\n%{http_code} %{time_total}\n",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    output = proc.stdout.strip().splitlines()
    body = "\n".join(output[:-1]) if len(output) > 1 else proc.stdout
    status_line = output[-1] if output else "0 0"
    status = int(status_line.split()[0]) if status_line.split() else 0
    elapsed = float(status_line.split()[1]) if len(status_line.split()) > 1 else None
    row = {"file": path.name, "label": label or "first", "http_status": status, "elapsed_seconds": elapsed, "ok": False}
    try:
        data = json.loads(body)
        rec = data.get("record", {})
        segs = rec.get("segments") or []
        first = (segs[0].get("text") if segs else "") or ""
        words = set(first.lower().replace(",", "").replace(".", "").split())
        credible = len(EXPECTED_WORDS & words) >= 5
        row.update(
            api_ok=data.get("ok"), id=rec.get("id"), method=rec.get("method"), source_kind=rec.get("source_kind"),
            segment_count=len(segs), word_count=rec.get("word_count"), language=rec.get("language"),
            cache_hit=rec.get("cache_hit"), first=first[:160],
        )
        row["ok"] = status == 200 and data.get("ok") is True and rec.get("method") == "local-whisper" and credible and (rec.get("word_count") or 0) >= 8
    except Exception as exc:
        row.update(error=str(exc), body=body[:300], stderr=proc.stderr[:300])
    return row


def verify_downloads(record_id: str) -> list[dict]:
    checks: list[dict] = []
    for fmt, marker in [("txt", "Epic transcript"), ("md", "# phase2"), ("srt", "00:00:")]:
        link_cmd = [
            "curl", "-sS", "-L", "-X", "POST", f"{BASE}/api/transcripts/{record_id}/download-link?format={fmt}",
            "-H", f"X-Transcript-Owner: {OWNER}", "-w", "\n%{http_code}\n",
        ]
        link_proc = subprocess.run(link_cmd, capture_output=True, text=True, timeout=60)
        lines = link_proc.stdout.strip().splitlines()
        body = "\n".join(lines[:-1]) if len(lines) > 1 else link_proc.stdout
        status = int(lines[-1]) if lines and lines[-1].isdigit() else 0
        check = {"format": fmt, "link_status": status, "ok": False}
        try:
            data = json.loads(body)
            url = data.get("url") or ""
            if url.startswith("/"):
                url = urljoin(BASE + "/", url.lstrip("/"))
            get_cmd = ["curl", "-sS", "-L", url, "-w", "\n%{http_code} %{size_download}\n"]
            get_proc = subprocess.run(get_cmd, capture_output=True, text=True, timeout=60)
            get_lines = get_proc.stdout.splitlines()
            status_line = get_lines[-1] if get_lines else "0 0"
            content = "\n".join(get_lines[:-1])
            parts = status_line.split()
            get_status = int(parts[0]) if parts else 0
            size = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else len(content)
            check.update(download_status=get_status, bytes=size, marker_present=marker.lower() in content.lower())
            check["ok"] = status == 200 and get_status == 200 and size > 20 and check["marker_present"]
        except Exception as exc:
            check.update(error=str(exc), body=body[:300], stderr=link_proc.stderr[:300])
        checks.append(check)
    return checks


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="epic-phase2-upload-") as tmp:
        fixtures = make_fixtures(Path(tmp))
        results = [upload(path) for path in fixtures]
        repeat = upload(fixtures[0], label="repeat-cache-check")
    downloads = verify_downloads(results[0]["id"]) if results and results[0].get("id") else []
    cache_ok = repeat.get("ok") and repeat.get("cache_hit") is True and repeat.get("word_count") == results[0].get("word_count")
    payload = {
        "base_url": BASE,
        "owner_header_used": True,
        "results": results,
        "repeat_cache_check": repeat,
        "downloads": downloads,
        "all_ok": all(r["ok"] for r in results) and bool(cache_ok) and bool(downloads) and all(d["ok"] for d in downloads),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
