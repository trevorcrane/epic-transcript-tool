#!/usr/bin/env python3
"""EPIC Transcript Machine health check.

Runs stable transcript checks against a deployed/public URL or local API.
Does not print secrets.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from urllib import request, parse

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else os.getenv("EPIC_TRANSCRIPT_BASE_URL", "http://localhost:8090")).rstrip("/")

@dataclass
class Case:
    name: str
    url: str
    min_segments: int
    min_words: int
    expected_method: str

CASES = [
    Case("regression", "https://youtu.be/v34Eg12mhDM?si=lqfq-8bhlxADDZdD", 701, 5001, "native-caption-automatic_captions"),
    Case("manual-caption-control", "https://youtu.be/dQw4w9WgXcQ", 21, 101, "native-caption-subtitles"),
    Case("automatic-caption-control", "https://www.youtube.com/shorts/SXHMnicI6Pg", 2, 3, "native-caption-automatic_captions"),
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


def video_id_from_url(url: str) -> str:
    patterns = [
        r"youtu\.be/([^?&#/]+)",
        r"youtube\.com/(?:watch\?v=|shorts/|embed/|live/)([^?&#/]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return url


def segment_text(segment: dict) -> str:
    return (segment.get("text") or segment.get("content") or "").strip()


def segment_start(segment: dict) -> float:
    value = segment.get("start")
    if value is None:
        value = segment.get("start_time")
    return float(value or 0)


def timestamps_are_increasing(segments: list[dict]) -> bool:
    starts = [segment_start(segment) for segment in segments]
    return bool(starts) and all(curr >= prev for prev, curr in zip(starts, starts[1:]))


def check_case(case: Case) -> dict:
    started = time.monotonic()
    status, text = post_form(f"{BASE_URL}/api/transcribe-url", {"url": case.url})
    duration = round(time.monotonic() - started, 3)
    expected_video_id = video_id_from_url(case.url)
    result = {"case": case.name, "url": case.url, "video_id": expected_video_id, "http_status": status, "processing_duration": duration, "ok": False}
    try:
        payload = json.loads(text)
        rec = payload.get("record", {})
        attempts = rec.get("provider_attempts", [])
        segments = rec.get("segments", []) or []
        beginning = segment_text(segments[0]) if segments else ""
        ending = segment_text(segments[-1]) if segments else ""
        title = (rec.get("title") or rec.get("source") or "").strip()
        provider_succeeded = rec.get("method")
        segment_count = len(segments)
        word_count = rec.get("word_count") or 0
        quality_checks = {
            "http_200": status == 200,
            "video_id": (rec.get("media_id") or expected_video_id) == expected_video_id,
            "method": provider_succeeded == case.expected_method,
            "segment_count": segment_count >= case.min_segments,
            "word_count": word_count >= case.min_words,
            "nonempty_title": bool(title),
            "nonempty_beginning_end": bool(beginning and ending),
            "timestamps_increasing": timestamps_are_increasing(segments),
            "required_fields": bool(provider_succeeded and rec.get("language") and rec.get("word_count") is not None and attempts),
        }
        result.update({
            "provider_attempted": [a.get("provider") for a in attempts],
            "provider_succeeded": provider_succeeded,
            "segment_count": segment_count,
            "word_count": rec.get("word_count"),
            "language": rec.get("language"),
            "cache_status": "hit" if rec.get("cache_hit") else "miss",
            "error_category": None,
            "title": title,
            "beginning": beginning,
            "end": ending,
            "timestamps_increasing": quality_checks["timestamps_increasing"],
            "quality_checks": quality_checks,
        })
        result["ok"] = all(quality_checks.values())
    except Exception as e:
        result.update({"error_category": "parse_or_pipeline_failure", "error": str(e), "body_preview": text[:500]})
    return result


def main() -> int:
    results = [check_case(c) for c in CASES]
    video_ids = [r.get("video_id") for r in results]
    unique_ids_ok = len(set(video_ids)) == len(video_ids)
    print(json.dumps({"base_url": BASE_URL, "unique_video_ids_ok": unique_ids_ok, "results": results}, indent=2))
    return 0 if unique_ids_ok and all(r.get("ok") for r in results) else 1

if __name__ == "__main__":
    raise SystemExit(main())
