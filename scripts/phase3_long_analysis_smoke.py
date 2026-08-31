#!/usr/bin/env python3
"""Public Phase 3 long-transcript intelligence smoke.

Uses the known two-hour public fixture through the async URL job endpoint,
verifies the public API returns the cached long transcript for the current owner,
then verifies combined analysis includes beginning, middle, and end timestamp
coverage plus a downloadable Markdown result.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "https://epic-transcript.robyncrane.com"
OWNER = "phase3-long-smoke-owner-token-abcdefghijklmnopqrstuvwxyz"
VIDEO = "https://www.youtube.com/watch?v=rwfk91ya81s"
UA = "Mozilla/5.0 Epic Transcript Phase3 Long Smoke"


@dataclass
class HttpResult:
    status: int
    body: bytes
    headers: dict[str, str]


def request(path: str, *, method: str = "GET", data: dict[str, str] | None = None, headers: dict[str, str] | None = None, timeout: int = 120) -> HttpResult:
    body = None
    all_headers = {"User-Agent": UA}
    if headers:
        all_headers.update(headers)
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        all_headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(BASE + path, data=body, headers=all_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return HttpResult(res.status, res.read(), dict(res.headers))
    except urllib.error.HTTPError as exc:
        return HttpResult(exc.code, exc.read(), dict(exc.headers))


def as_json(result: HttpResult) -> dict:
    return json.loads(result.body.decode())


def timestamp_seconds(value: str) -> int:
    parts = [int(p) for p in value.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def header_value(headers: dict[str, str], name: str) -> str:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return ""


def verify_analysis_download(analysis_id: str, owner: str) -> dict[str, object]:
    """Verify long combined-analysis Markdown is private and owner-downloadable."""
    unauth = request(f"/api/analysis/{analysis_id}/download")
    if unauth.status != 403:
        raise SystemExit(f"Unauthenticated long-analysis download returned {unauth.status}, expected 403")

    owner_download = request(f"/api/analysis/{analysis_id}/download", headers={"X-Transcript-Owner": owner})
    download_text = owner_download.body.decode(errors="replace")
    download_content_type = header_value(owner_download.headers, "content-type")
    if owner_download.status != 200 or "text/markdown" not in download_content_type:
        raise SystemExit(f"Download failed: status={owner_download.status} content-type={download_content_type}")
    if "# Executive summary" not in download_text or "# Create 100 content assets" not in download_text:
        raise SystemExit("Downloaded long-analysis Markdown missing combined output markers")
    if "AI-generated" not in download_text or "Transcript evidence" not in download_text:
        raise SystemExit("Downloaded long-analysis Markdown missing AI/evidence markers")

    return {
        "unauthenticated_download_status": unauth.status,
        "owner_download_status": owner_download.status,
        "owner_download_bytes": len(owner_download.body),
        "owner_download_content_type": download_content_type,
    }


def main() -> int:
    started = time.monotonic()
    start = as_json(request("/api/transcribe-url-job", method="POST", data={"url": VIDEO, "owner": OWNER}))
    if start.get("ok") is not True:
        raise SystemExit(f"Job start failed: {start}")
    job_id = start["job"]["id"]
    job = start["job"]
    for _ in range(60):
        time.sleep(1)
        job = as_json(request(f"/api/jobs/{job_id}")).get("job", {})
        if job.get("status") in {"done", "error"}:
            break
    if job.get("status") != "done":
        raise SystemExit(f"Long transcript job did not finish from cache: {job}")
    rec = dict(job["record"])
    if rec.get("word_count", 0) < 5000 or rec.get("segment_count", 0) < 700:
        raise SystemExit(f"Long transcript proof failed: words={rec.get('word_count')} segments={rec.get('segment_count')}")
    if rec.get("duration_seconds", 0) < 3600:
        raise SystemExit(f"Long transcript duration proof failed: {rec.get('duration_seconds')}")

    combined = as_json(request(f"/api/analyze-all/{rec['id']}", method="POST", headers={"X-Transcript-Owner": OWNER}))
    text = str(combined.get("analysis", ""))
    required = ["# Executive summary", "# Chapters", "# Create 100 content assets", "AI-generated from the transcript", "Transcript evidence"]
    missing = [m for m in required if m not in text]
    if missing:
        raise SystemExit(f"Combined long analysis missing markers: {missing}")
    stamps = [timestamp_seconds(m.group(1)) for m in re.finditer(r"\[(\d{2}:\d{2}(?::\d{2})?)\]", text)]
    if not stamps or max(stamps) < 5400:
        raise SystemExit(f"Combined long analysis lacks late-transcript evidence: max_timestamp={max(stamps) if stamps else None}")
    if len(text) < 5000 or text.count("AI-generated from the transcript") < 10:
        raise SystemExit(f"Combined long analysis too thin: chars={len(text)} markers={text.count('AI-generated from the transcript')}")

    download_detail = verify_analysis_download(combined["analysis_id"], OWNER)

    print(json.dumps({
        "ok": True,
        "base": BASE,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "job_id": job_id,
        "record_id": rec["id"],
        "title": rec.get("title"),
        "transcript_words": rec.get("word_count"),
        "transcript_segments": rec.get("segment_count"),
        "duration_seconds": rec.get("duration_seconds"),
        "transcript_method": rec.get("method"),
        "cache_hit": rec.get("cache_hit"),
        "analysis_id": combined["analysis_id"],
        "combined_chars": len(text),
        "combined_outputs": text.count("AI-generated from the transcript"),
        "latest_analysis_timestamp_seconds": max(stamps),
        "download_status": download_detail["owner_download_status"],
        "download_bytes": download_detail["owner_download_bytes"],
        "download_content_type": download_detail["owner_download_content_type"],
        "unauthenticated_download_status": download_detail["unauthenticated_download_status"],
        "analysis_download_privacy": "owner-required",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
