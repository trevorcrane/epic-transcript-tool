#!/usr/bin/env python3
"""Public Phase 2 URL matrix smoke.

Proves the clickable async URL path supports direct public media URLs and gives
fast, honest guidance for social URLs that usually block public downloads.
"""
from __future__ import annotations

import json
import secrets
import sys
import time
from pathlib import Path

import requests

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://epic-transcript.robyncrane.com").rstrip("/")
OWNER = "phase2-url-matrix-" + secrets.token_hex(12)
HEADERS = {"User-Agent": "Mozilla/5.0 Phase2UrlMatrixSmoke/1.0", "X-Transcript-Owner": OWNER}
OUT = Path(__file__).resolve().parents[1] / "evidence" / "phase2-url-matrix-report.json"
DIRECT_URL = f"{BASE}/static/phase2-public-url.mp3"
SOCIAL_CASES = [
    ("tiktok", "https://www.tiktok.com/@creator/video/1234567890", "TikTok"),
    ("instagram", "https://www.instagram.com/reel/example/", "Instagram"),
    ("facebook", "https://www.facebook.com/watch/?v=1234567890", "Facebook"),
    ("x_twitter", "https://x.com/user/status/1234567890", "X/Twitter"),
]


def wait_job(job_id: str, timeout: int = 90) -> dict:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        r = requests.get(f"{BASE}/api/jobs/{job_id}", headers=HEADERS, timeout=20)
        r.raise_for_status()
        job = r.json()["job"]
        if job.get("status") in {"done", "error"}:
            return job
        time.sleep(1)
    raise TimeoutError(job_id)


def main() -> int:
    report = {"base": BASE, "owner_header_used": True}
    probe = requests.get(DIRECT_URL, headers=HEADERS, timeout=30)
    report["direct_probe"] = {"status": probe.status_code, "content_type": probe.headers.get("content-type", ""), "bytes": len(probe.content)}
    start = requests.post(f"{BASE}/api/transcribe-url-job", data={"url": DIRECT_URL, "owner": OWNER}, headers=HEADERS, timeout=30)
    report["direct_async_start"] = {"status": start.status_code, "body": start.text[:300]}
    start.raise_for_status()
    job_id = start.json()["job"]["id"]
    job = wait_job(job_id)
    rec = job.get("record") or {}
    report["direct_async_result"] = {
        "job_id": job_id,
        "status": job.get("status"),
        "record_id": rec.get("id"),
        "method": rec.get("method"),
        "source_kind": rec.get("source_kind"),
        "language": rec.get("language"),
        "word_count": rec.get("word_count"),
        "segment_count": len(rec.get("segments") or []),
        "cache_hit": rec.get("cache_hit"),
        "first": ((rec.get("segments") or [{}])[0].get("text") or "")[:120] if rec.get("segments") else "",
    }
    social = []
    for name, url, label in SOCIAL_CASES:
        r = requests.post(f"{BASE}/api/transcribe-url", data={"url": url, "owner": OWNER}, headers=HEADERS, timeout=30)
        detail = ""
        try:
            detail = r.json().get("detail", "")
        except Exception:
            detail = r.text[:300]
        social.append({"case": name, "status": r.status_code, "ok": r.status_code == 422 and label in detail and "upload it here" in detail, "detail": detail[:240]})
    report["social_guidance"] = social
    report["all_ok"] = (
        report["direct_probe"]["status"] in {200, 206}
        and report["direct_async_start"]["status"] == 202
        and report["direct_async_result"]["status"] == "done"
        and report["direct_async_result"]["source_kind"] == "url"
        and all(row["ok"] for row in social)
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
