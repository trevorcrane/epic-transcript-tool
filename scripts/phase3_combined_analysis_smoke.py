#!/usr/bin/env python3
"""Public Phase 3 combined-output copy/download smoke.

Creates or reuses a known cached transcript, calls the public combined output API,
verifies the returned text is large enough to copy, and verifies the Markdown
analysis download endpoint.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "https://epic-transcript.robyncrane.com"
OWNER = "phase3-combined-smoke-owner-token-abcdefghijklmnopqrstuvwxyz"
VIDEO = "https://youtu.be/dQw4w9WgXcQ"
UA = "Mozilla/5.0 Epic Transcript Phase3 Combined Smoke"


@dataclass
class HttpResult:
    status: int
    body: bytes
    headers: object


def request(path: str, *, method: str = "GET", data: dict[str, str] | None = None, headers: dict[str, str] | None = None) -> HttpResult:
    body = None
    all_headers = {"User-Agent": UA}
    if headers:
        all_headers.update(headers)
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        all_headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(BASE + path, data=body, headers=all_headers, method=method)
    with urllib.request.urlopen(req, timeout=90) as res:
        return HttpResult(res.status, res.read(), res.headers)


def as_json(result: HttpResult) -> dict:
    return json.loads(result.body.decode())


def main() -> int:
    started = time.monotonic()
    tx = as_json(request("/api/transcribe-url", method="POST", data={"url": VIDEO, "owner": OWNER}))
    rec = dict(tx["record"])
    if rec.get("word_count", 0) < 100 or not str(rec.get("transcript", "")).strip():
        raise SystemExit(f"Transcript proof failed: words={rec.get('word_count')}")

    combined = as_json(request(f"/api/analyze-all/{rec['id']}", method="POST", headers={"X-Transcript-Owner": OWNER}))
    text = str(combined.get("analysis", ""))
    required = ["# Executive summary", "# Main ideas", "# Create 100 content assets", "AI-generated from the transcript", "Transcript evidence"]
    missing = [m for m in required if m not in text]
    if missing:
        raise SystemExit(f"Combined analysis missing markers: {missing}")
    if text.count("AI-generated from the transcript") < 10 or len(text) < 3000:
        raise SystemExit(f"Combined analysis too thin: chars={len(text)} markers={text.count('AI-generated from the transcript')}")

    dl = request(f"/api/analysis/{combined['analysis_id']}/download")
    download_text = dl.body.decode(errors="replace")
    if dl.status != 200 or "text/markdown" not in dl.headers.get("content-type", ""):
        raise SystemExit(f"Download failed: status={dl.status} content-type={dl.headers.get('content-type')}")
    if "# Executive summary" not in download_text or "# Create 100 content assets" not in download_text:
        raise SystemExit("Downloaded Markdown missing combined output markers")

    print(json.dumps({
        "ok": True,
        "base": BASE,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "record_id": rec["id"],
        "transcript_words": rec.get("word_count"),
        "transcript_method": rec.get("method"),
        "cache_hit": rec.get("cache_hit"),
        "analysis_id": combined["analysis_id"],
        "combined_chars": len(text),
        "combined_outputs": text.count("AI-generated from the transcript"),
        "download_status": dl.status,
        "download_bytes": len(dl.body),
        "copy_ready": bool(text.strip()),
        "download_content_type": dl.headers.get("content-type", ""),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
