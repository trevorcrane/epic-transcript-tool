#!/usr/bin/env python3
"""EPIC Transcript Machine health check.

Runs stable transcript checks against a deployed/public URL or local API.
Does not print secrets.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from urllib import request, parse

BASE_URL = os.getenv("EPIC_TRANSCRIPT_BASE_URL", "http://localhost:8090").rstrip("/")

@dataclass
class Case:
    name: str
    url: str
    min_segments: int
    min_words: int

CASES = [
    Case("regression", "https://youtu.be/v34Eg12mhDM?si=lqfq-8bhlxADDZdD", 700, 5000),
    Case("manual-caption-control", "https://youtu.be/dQw4w9WgXcQ", 20, 100),
]


PUBLIC_HEADERS = {
    # Cloudflare can reject Python's default urllib user agent with 1010.
    # Keep the release checker public/no-login, but make it look like a normal browser request.
    "User-Agent": "Mozilla/5.0 Hermes EPIC Transcript release checker",
    "Accept": "application/json,text/plain,*/*",
}


def post_form(url: str, data: dict, timeout: int = 180) -> tuple[int, str]:
    body = parse.urlencode(data).encode()
    req = request.Request(url, data=body, headers={**PUBLIC_HEADERS, "Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except Exception as e:
        return getattr(e, "code", 0) or 0, getattr(e, "read", lambda: str(e).encode())().decode("utf-8", "replace")


def check_case(case: Case) -> dict:
    started = time.monotonic()
    status, text = post_form(f"{BASE_URL}/api/transcribe-url", {"url": case.url})
    duration = round(time.monotonic() - started, 3)
    result = {"case": case.name, "http_status": status, "processing_duration": duration, "ok": False}
    try:
        payload = json.loads(text)
        rec = payload.get("record", {})
        attempts = rec.get("provider_attempts", [])
        result.update({
            "provider_attempted": [a.get("provider") for a in attempts],
            "provider_succeeded": rec.get("method"),
            "segment_count": len(rec.get("segments", [])),
            "word_count": rec.get("word_count"),
            "language": rec.get("language"),
            "cache_status": "hit" if rec.get("cache_hit") else "miss",
            "error_category": None,
            "title": rec.get("title") or rec.get("source"),
        })
        result["ok"] = status == 200 and result["segment_count"] >= case.min_segments and (result["word_count"] or 0) >= case.min_words
    except Exception as e:
        result.update({"error_category": "parse_or_pipeline_failure", "error": str(e), "body_preview": text[:500]})
    return result


def main() -> int:
    results = [check_case(c) for c in CASES]
    print(json.dumps({"base_url": BASE_URL, "results": results}, indent=2))
    return 0 if all(r.get("ok") for r in results) else 1

if __name__ == "__main__":
    raise SystemExit(main())
