#!/usr/bin/env python3
"""Public Phase 3 citation coverage smoke.

Verifies every public Phase 3 output remains grounded in timestamped transcript
evidence, and the 100-content-assets output covers the beginning, middle, and
end of the source instead of recycling one small evidence window.
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
VIDEO = sys.argv[2] if len(sys.argv) > 2 else "https://youtu.be/v34Eg12mhDM?si=lqfq-8bhlxADDZdD"
OWNER = "phase3-citation-coverage-" + secrets.token_hex(12)
UA = "Mozilla/5.0 Epic Transcript Phase3 Citation Coverage Smoke"
OUT = Path("evidence/phase3-citation-coverage-report.json")
STAMP_RE = re.compile(r"\[(\d{2}):(\d{2})(?::(\d{2}))?\]")
NUMBERED_ASSET_RE = re.compile(r"^\d+\. \*\*.+?\*\*", re.MULTILINE)


def request(path: str, *, method: str = "GET", data: dict[str, str] | None = None, headers: dict[str, str] | None = None, timeout: int = 120) -> tuple[int, bytes, dict[str, str]]:
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


def stamp_to_seconds(match: re.Match[str]) -> int:
    a, b, c = match.groups()
    if c is None:
        return int(a) * 60 + int(b)
    return int(a) * 3600 + int(b) * 60 + int(c)


def stamps(text: str) -> list[int]:
    return [stamp_to_seconds(match) for match in STAMP_RE.finditer(text)]


def complete_transcript() -> dict[str, Any]:
    start = as_json("/api/transcribe-url-job", method="POST", data={"url": VIDEO, "owner": OWNER})
    require(start.get("_http_status") == 202 and start.get("job", {}).get("id"), f"job start failed: {start}")
    job_id = start["job"]["id"]
    job = start["job"]
    for _ in range(180):
        if job.get("status") in {"done", "error"}:
            break
        time.sleep(1)
        job = as_json(f"/api/jobs/{job_id}").get("job", {})
    require(job.get("status") == "done", f"transcript job did not finish: {job}")
    rec = dict(job.get("record") or {})
    require(bool(rec.get("id")), f"missing record: {job}")
    require((rec.get("word_count") or 0) >= 5000, f"transcript too small for coverage gate: {rec.get('word_count')}")
    require(len(rec.get("segments") or []) >= 100, f"not enough segments for coverage gate: {len(rec.get('segments') or [])}")
    return rec


def main() -> int:
    started = time.monotonic()
    rec = complete_transcript()
    owner = rec.get("owner_token") or OWNER
    outputs = as_json("/api/analysis-outputs")
    output_ids = [item["id"] for item in outputs.get("outputs") or []]
    require(len(output_ids) == 17 and "ask_question" in output_ids, f"unexpected outputs: {output_ids}")

    transcript_stamps = {int(float(seg.get("start", 0))) for seg in rec.get("segments") or []}
    duration = int(rec.get("duration_seconds") or max(transcript_stamps or {0}))
    checked_outputs: dict[str, Any] = {}

    for output_type in output_ids:
        payload = {"output_type": output_type}
        if output_type == "ask_question":
            payload["question"] = "What should Trevor use from this transcript?"
        analysis = as_json(
            f"/api/analyze/{rec['id']}",
            method="POST",
            data=payload,
            headers={"X-Transcript-Owner": owner},
            timeout=120,
        )
        require(analysis.get("_http_status") == 200 and analysis.get("ok") is True, f"analysis failed for {output_type}: {analysis}")
        text = str(analysis.get("analysis") or "")
        found = stamps(text)
        require("AI-generated from the transcript" in text, f"{output_type} missing AI-generated disclaimer")
        require(bool(found), f"{output_type} missing timestamp evidence")
        matched = [ts for ts in found if ts in transcript_stamps]
        require(bool(matched), f"{output_type} has no timestamps matching transcript segments")
        checked_outputs[output_type] = {
            "analysis_id": analysis.get("analysis_id"),
            "timestamp_count": len(found),
            "unique_timestamps": len(set(found)),
            "matching_transcript_timestamps": len(set(matched)),
        }

        if output_type == "content_assets_100":
            numbered_assets = NUMBERED_ASSET_RE.findall(text)
            unique = sorted(set(found))
            early_cutoff = duration * 0.25
            late_cutoff = duration * 0.75
            require(len(numbered_assets) == 100, f"content_assets_100 expected 100 assets, got {len(numbered_assets)}")
            require(len(found) >= 100, f"content_assets_100 expected at least 100 timestamps, got {len(found)}")
            require(len(set(found)) >= 50, f"content_assets_100 recycled too few timestamps: {len(set(found))}")
            require(any(ts <= early_cutoff for ts in unique), "content_assets_100 missing early transcript coverage")
            require(any(early_cutoff < ts < late_cutoff for ts in unique), "content_assets_100 missing middle transcript coverage")
            require(any(ts >= late_cutoff for ts in unique), "content_assets_100 missing late transcript coverage")
            checked_outputs[output_type].update({
                "asset_count": len(numbered_assets),
                "duration_seconds": duration,
                "earliest_timestamp": min(unique),
                "latest_timestamp": max(unique),
                "early_middle_late_coverage": True,
            })

    combined = as_json(
        f"/api/analyze-all/{rec['id']}",
        method="POST",
        headers={"X-Transcript-Owner": owner},
        timeout=120,
    )
    require(combined.get("_http_status") == 200 and combined.get("ok") is True, f"combined analysis failed: {combined}")
    combined_text = str(combined.get("analysis") or "")
    require(combined_text.count("AI-generated from the transcript") >= 16, "combined output missing safety disclaimers")
    require(len(stamps(combined_text)) >= 150, "combined output has too few timestamp citations")
    status, body, headers = request(f"/api/analysis/{combined['analysis_id']}/download", headers={"X-Transcript-Owner": owner})
    require(status == 200 and b"# Executive summary" in body and b"# Create 100 content assets" in body, "combined download missing expected sections")

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
            "duration_seconds": rec.get("duration_seconds"),
        },
        "outputs_checked": checked_outputs,
        "combined": {
            "analysis_id": combined.get("analysis_id"),
            "timestamp_count": len(stamps(combined_text)),
            "download_status": status,
            "download_bytes": len(body),
            "download_content_type": headers.get("Content-Type") or headers.get("content-type"),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
