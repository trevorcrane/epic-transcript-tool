#!/usr/bin/env python3
"""Public Phase 2 non-English upload smoke test.

Generates a short French spoken fixture locally with macOS `say`, converts it to
WAV, uploads it through the public no-login API, and verifies that the free local
Whisper path returns a credible French transcript without a paid provider.
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
TEXT = (
    "Bonjour, ceci est un test français pour Epic Transcript Machine. "
    "La transcription doit reconnaître des mots simples en français sans fournisseur payant."
)
EXPECTED_WORDS = {"bonjour", "ceci", "test", "français", "transcription", "mots", "simples", "payant"}
OWNER = "phase2-french-smoke-" + secrets.token_urlsafe(24).replace("-", "_")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)


def make_french_wav(work: Path) -> Path:
    if not shutil.which("say"):
        raise SystemExit("macOS 'say' command is required to generate the French speech fixture")
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required to generate the upload fixture")
    aiff = work / "phase2-french.aiff"
    wav = work / "phase2-french.wav"
    run(["say", "-v", "Thomas", "-o", str(aiff), TEXT])
    run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(wav)])
    return wav


def upload(path: Path) -> dict:
    cmd = [
        "curl", "-sS", "-L", "-X", "POST", f"{BASE}/api/transcribe-upload",
        "-F", f"owner={OWNER}", "-F", f"file=@{path}", "-w", "\n%{http_code} %{time_total}\n",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    output = proc.stdout.strip().splitlines()
    body = "\n".join(output[:-1]) if len(output) > 1 else proc.stdout
    status_line = output[-1] if output else "0 0"
    parts = status_line.split()
    status = int(parts[0]) if parts else 0
    elapsed = float(parts[1]) if len(parts) > 1 else None
    row = {"file": path.name, "http_status": status, "elapsed_seconds": elapsed, "ok": False}
    try:
        data = json.loads(body)
        rec = data.get("record", {})
        transcript = (rec.get("transcript") or "").lower().replace("é", "e").replace("è", "e").replace("ç", "c")
        normalized_expected = {w.replace("é", "e").replace("è", "e").replace("ç", "c") for w in EXPECTED_WORDS}
        credible = len([w for w in normalized_expected if w in transcript]) >= 5
        row.update(
            api_ok=data.get("ok"), id=rec.get("id"), method=rec.get("method"), source_kind=rec.get("source_kind"),
            language=rec.get("language"), segment_count=len(rec.get("segments") or []), word_count=rec.get("word_count"),
            cache_hit=rec.get("cache_hit"), first=(rec.get("segments") or [{}])[0].get("text", "")[:180],
            transcript_excerpt=(rec.get("transcript") or "")[:260],
        )
        row["ok"] = (
            status == 200 and data.get("ok") is True and rec.get("method") == "local-whisper"
            and (rec.get("word_count") or 0) >= 8 and credible and (rec.get("language") or "").startswith("fr")
        )
    except Exception as exc:
        row.update(error=str(exc), body=body[:400], stderr=proc.stderr[:400])
    return row


def verify_download(record_id: str) -> dict:
    link_cmd = [
        "curl", "-sS", "-L", "-X", "POST", f"{BASE}/api/transcripts/{record_id}/download-link?format=txt",
        "-H", f"X-Transcript-Owner: {OWNER}", "-w", "\n%{http_code}\n",
    ]
    link_proc = subprocess.run(link_cmd, capture_output=True, text=True, timeout=60)
    lines = link_proc.stdout.strip().splitlines()
    body = "\n".join(lines[:-1]) if len(lines) > 1 else link_proc.stdout
    link_status = int(lines[-1]) if lines and lines[-1].isdigit() else 0
    check = {"format": "txt", "link_status": link_status, "ok": False}
    try:
        url = json.loads(body).get("url") or ""
        if url.startswith("/"):
            url = urljoin(BASE + "/", url.lstrip("/"))
        get = subprocess.run(["curl", "-sS", "-L", url, "-w", "\n%{http_code} %{size_download}\n"], capture_output=True, text=True, timeout=60)
        got_lines = get.stdout.splitlines()
        status_line = got_lines[-1] if got_lines else "0 0"
        content = "\n".join(got_lines[:-1])
        parts = status_line.split()
        get_status = int(parts[0]) if parts else 0
        size = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else len(content)
        check.update(download_status=get_status, bytes=size, marker_present="bonjour" in content.lower())
        check["ok"] = link_status == 200 and get_status == 200 and size > 20 and check["marker_present"]
    except Exception as exc:
        check.update(error=str(exc), body=body[:300], stderr=link_proc.stderr[:300])
    return check


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="epic-phase2-french-") as tmp:
        wav = make_french_wav(Path(tmp))
        result = upload(wav)
    download = verify_download(result["id"]) if result.get("id") else {"ok": False}
    payload = {"base_url": BASE, "owner_header_used": True, "result": result, "download": download, "all_ok": result.get("ok") and download.get("ok")}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
