#!/usr/bin/env python3
"""Public Phase 3 quote integrity smoke.

Verifies the public best-quotes analysis is not inventing verbatim quotes:
every quoted line must exactly match the timestamped Source text returned in the
same analysis response, and that source text must appear in the public transcript
record.
"""
from __future__ import annotations

import json
import re
import secrets
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "https://epic-transcript.robyncrane.com"
VIDEO = sys.argv[2] if len(sys.argv) > 2 else "https://youtu.be/dQw4w9WgXcQ"
OWNER = "phase3-quote-integrity-" + secrets.token_hex(12)
UA = "Mozilla/5.0 Epic Transcript Phase3 Quote Integrity Smoke"
OUT = Path("evidence/phase3-quote-integrity-report.json")
QUOTE_LINE_RE = re.compile(r'^- "(?P<quote>.+?)" - Source (?P<source>\[\d{2}:\d{2}(?::\d{2})?\] .+)$')


def request(path: str, *, method: str = "GET", data: dict[str, str] | None = None, headers: dict[str, str] | None = None, timeout: int = 90) -> tuple[int, bytes, dict[str, str]]:
    body = None
    all_headers = {"User-Agent": UA}
    if headers:
        all_headers.update(headers)
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        all_headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(BASE + path, data=body, headers=all_headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.status, res.read(), dict(res.headers)


def as_json(path: str, **kwargs: Any) -> dict[str, Any]:
    status, body, _ = request(path, **kwargs)
    payload = json.loads(body.decode())
    payload["_http_status"] = status
    return payload


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def strip_timestamp(line: str) -> str:
    return re.sub(r"^\[\d{2}:\d{2}(?::\d{2})?\]\s*", "", line).strip()


def normalize(text: str) -> str:
    return " ".join(text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"').split())


def complete_transcript() -> dict[str, Any]:
    start = as_json("/api/transcribe-url-job", method="POST", data={"url": VIDEO, "owner": OWNER})
    require(start.get("_http_status") == 202 and start.get("job", {}).get("id"), f"job start failed: {start}")
    job_id = start["job"]["id"]
    job = start["job"]
    for _ in range(90):
        if job.get("status") in {"done", "error"}:
            break
        time.sleep(1)
        job = as_json(f"/api/jobs/{job_id}").get("job", {})
    require(job.get("status") == "done", f"transcript job did not finish: {job}")
    rec = dict(job.get("record") or {})
    require(bool(rec.get("id")), f"missing record: {job}")
    require((rec.get("word_count") or 0) >= 100, f"transcript too small: {rec.get('word_count')}")
    return rec


def main() -> int:
    started = time.monotonic()
    rec = complete_transcript()
    owner = rec.get("owner_token") or OWNER
    analysis = as_json(
        f"/api/analyze/{rec['id']}",
        method="POST",
        data={"output_type": "best_quotes"},
        headers={"X-Transcript-Owner": owner},
        timeout=90,
    )
    require(analysis.get("_http_status") == 200 and analysis.get("ok") is True, f"best_quotes failed: {analysis}")
    text = str(analysis.get("analysis") or "")
    require("AI-generated" in text and "Transcript evidence" in text, "analysis missing safety/evidence markers")
    quote_lines = []
    for line in text.splitlines():
        match = QUOTE_LINE_RE.match(line.strip())
        if match:
            quote_lines.append(match.groupdict())
    require(len(quote_lines) >= 3, f"expected at least 3 quote lines, got {len(quote_lines)}")

    transcript_blob = normalize("\n".join([rec.get("transcript") or ""] + [str(seg.get("text", "")) for seg in rec.get("segments") or []]))
    checked = []
    for item in quote_lines:
        quote = normalize(item["quote"])
        source_text = normalize(strip_timestamp(item["source"]))
        require(quote == source_text, f"quote/source mismatch: quote={item['quote']!r} source={item['source']!r}")
        require(source_text in transcript_blob, f"source not found in transcript: {item['source']!r}")
        checked.append({"quote": item["quote"], "source": item["source"]})

    status, body, headers = request(f"/api/analysis/{analysis['analysis_id']}/download", headers={"X-Transcript-Owner": owner})
    download_text = body.decode(errors="replace")
    require(status == 200 and "Best quotes" in download_text and "AI-generated" in download_text, "best-quotes download missing expected markers")

    report = {
        "ok": True,
        "base": BASE,
        "video_url": VIDEO,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "record": {
            "id": rec.get("id"),
            "title": rec.get("title"),
            "method": rec.get("method"),
            "language": rec.get("language"),
            "word_count": rec.get("word_count"),
            "segment_count": rec.get("segment_count") or len(rec.get("segments") or []),
            "cache_hit": rec.get("cache_hit"),
        },
        "analysis_id": analysis.get("analysis_id"),
        "quote_count_checked": len(checked),
        "all_quotes_exact_source_matches": True,
        "all_sources_found_in_transcript": True,
        "download": {"status": status, "bytes": len(body), "content_type": headers.get("Content-Type") or headers.get("content-type")},
        "checked_quotes": checked,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
