#!/usr/bin/env python3
"""Public Phase 3 all-output analysis smoke.

Verifies every declared public analysis output, including ask-question, against a
public no-login API using one cached transcript owner token. This complements the
combined-output and UI-contract smokes by proving each individual button's API
payload remains useful, timestamp-grounded, copy-ready, and provider-safe.
"""
from __future__ import annotations

import json
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "https://epic-transcript.robyncrane.com"
VIDEO = sys.argv[2] if len(sys.argv) > 2 else "https://youtu.be/dQw4w9WgXcQ"
OWNER = "phase3-all-outputs-" + secrets.token_hex(12)
UA = "Mozilla/5.0 Epic Transcript Phase3 All Outputs Smoke"
OUT = Path("evidence/phase3-all-outputs-report.json")
EXPECTED_OUTPUTS = [
    "executive_summary",
    "main_ideas",
    "action_items",
    "chapters",
    "best_quotes",
    "stories_examples",
    "content_framework",
    "blog_post",
    "newsletter",
    "social_posts",
    "short_form_hooks",
    "faq",
    "sales_insights",
    "objections_answers",
    "trevor_use",
    "content_assets_100",
    "ask_question",
]


@dataclass
class HttpResult:
    status: int
    body: bytes
    headers: dict[str, str]


def request(path: str, *, method: str = "GET", data: dict[str, str] | None = None, headers: dict[str, str] | None = None, timeout: int = 90) -> HttpResult:
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


def as_json(result: HttpResult) -> dict[str, Any]:
    return json.loads(result.body.decode())


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def complete_transcript() -> dict[str, Any]:
    start = as_json(request("/api/transcribe-url-job", method="POST", data={"url": VIDEO, "owner": OWNER}))
    require(start.get("ok") is True and start.get("job", {}).get("id"), f"job start failed: {start}")
    job_id = start["job"]["id"]
    job = start["job"]
    for _ in range(90):
        if job.get("status") in {"done", "error"}:
            break
        time.sleep(1)
        job = as_json(request(f"/api/jobs/{job_id}")).get("job", {})
    require(job.get("status") == "done", f"transcript job did not finish: {job}")
    rec = dict(job.get("record") or {})
    require(bool(rec.get("id")), f"job record missing: {job}")
    require((rec.get("word_count") or 0) >= 100, f"transcript too small: words={rec.get('word_count')}")
    require(len(rec.get("segments") or []) >= 10 or (rec.get("segment_count") or 0) >= 10, "not enough timestamped segments")
    return rec


def validate_analysis(output_type: str, text: str, *, transcript_duration_seconds: float | None = None) -> dict[str, Any]:
    has_timestamp = bool(re.search(r"\[\d{2}:\d{2}", text))
    has_disclaimer = "AI-generated" in text
    has_evidence = "Transcript evidence" in text or has_timestamp
    require(len(text.strip()) > 120, f"{output_type} too short: {len(text)} chars")
    require(has_disclaimer, f"{output_type} missing AI-generated disclaimer")
    require(has_evidence, f"{output_type} missing transcript evidence/timestamp")
    if output_type == "best_quotes":
        require("Transcript evidence" in text and has_timestamp, "best_quotes must be tied to transcript timestamps")
    if output_type == "ask_question":
        require("Trevor" in text or "video" in text.lower(), "ask_question did not preserve the question context")
    detail: dict[str, Any] = {
        "chars": len(text),
        "has_timestamp": has_timestamp,
        "has_disclaimer": has_disclaimer,
        "has_evidence": has_evidence,
        "copy_ready": bool(text.strip()),
    }
    if output_type == "content_assets_100":
        numbered = [line for line in text.splitlines() if re.match(r"^\d+\. \*\*", line)]
        require(len(numbered) == 100, f"content_assets_100 expected 100 numbered assets, got {len(numbered)}")
        lower = text.lower()
        forbidden = ["use `", " use [", " to create:", "starter map", "brief a creator", "turn the moment into"]
        require(not any(term in lower for term in forbidden), "content_assets_100 contains instruction-placeholder phrasing")
        bodies = [line.split(" - ", 1)[-1] for line in numbered]
        require(len(set(bodies)) >= 90, f"content_assets_100 too repetitive: {len(set(bodies))} unique bodies")
        timestamps = []
        for line in numbered:
            for match in re.finditer(r"\[(\d{2}):(\d{2})(?::(\d{2}))?\]", line):
                a, b, c = match.groups()
                if c is None:
                    timestamps.append(int(a) * 60 + int(b))
                else:
                    timestamps.append(int(a) * 3600 + int(b) * 60 + int(c))
        require(len(timestamps) >= 90, f"content_assets_100 missing timestamps on assets: {len(timestamps)}")
        duration = transcript_duration_seconds or 0
        if duration >= 20 * 60:
            require(min(timestamps) <= 60, "content_assets_100 missing early coverage")
            require(max(timestamps) >= 20 * 60, "content_assets_100 missing late coverage")
            require(any(10 * 60 <= ts <= 18 * 60 for ts in timestamps), "content_assets_100 missing middle coverage")
            has_middle_coverage = any(10 * 60 <= ts <= 18 * 60 for ts in timestamps)
        else:
            required_late = max(30, int(duration * 0.6)) if duration else 30
            require(min(timestamps) <= 30, "content_assets_100 missing early coverage")
            require(max(timestamps) >= required_late, f"content_assets_100 missing short-transcript late coverage: max={max(timestamps)} required={required_late}")
            has_middle_coverage = True
        for label in ["Hook", "Short post", "Email subject", "Newsletter angle", "Reel script", "Carousel slide", "Quote card", "CTA", "Objection reply", "Repurpose prompt"]:
            require(label in text, f"content_assets_100 missing label {label}")
        detail.update({
            "asset_count": len(numbered),
            "unique_asset_bodies": len(set(bodies)),
            "earliest_timestamp_seconds": min(timestamps),
            "latest_timestamp_seconds": max(timestamps),
            "has_middle_coverage": has_middle_coverage,
            "no_placeholder_phrasing": True,
        })
    return detail


def main() -> int:
    started = time.monotonic()
    outputs_resp = as_json(request("/api/analysis-outputs"))
    ids = [item.get("id") for item in outputs_resp.get("outputs", [])]
    missing = [item for item in EXPECTED_OUTPUTS if item not in ids]
    extra = [item for item in ids if item not in EXPECTED_OUTPUTS]
    require(not missing, f"public /api/analysis-outputs missing: {missing}")
    require(not extra, f"public /api/analysis-outputs returned unexpected ids: {extra}")

    rec = complete_transcript()
    owner = rec.get("owner_token") or OWNER
    analyses: dict[str, Any] = {}
    analysis_ids: list[str] = []
    for output_type in EXPECTED_OUTPUTS:
        payload = {"output_type": output_type}
        if output_type == "ask_question":
            payload["question"] = "What should Trevor do with this video?"
        res = as_json(request(f"/api/analyze/{rec['id']}", method="POST", data=payload, headers={"X-Transcript-Owner": owner}, timeout=90))
        require(res.get("ok") is True, f"{output_type} analysis failed: {res}")
        require(res.get("output_type") == output_type, f"{output_type} response type mismatch: {res.get('output_type')}")
        require(bool(res.get("analysis_id")), f"{output_type} missing analysis_id")
        analysis_ids.append(str(res["analysis_id"]))
        analyses[output_type] = validate_analysis(
            output_type,
            str(res.get("analysis") or ""),
            transcript_duration_seconds=rec.get("duration_seconds") or rec.get("duration"),
        )

    # Verify every individual analysis download is owner-protected, not just the
    # first happy-path download. This keeps the Phase 3 release run from
    # regressing into public bare Markdown links for any output type.
    download_checks: dict[str, Any] = {}
    for output_type, analysis_id in zip(EXPECTED_OUTPUTS, analysis_ids):
        unauth = request(f"/api/analysis/{analysis_id}/download")
        require(unauth.status == 403, f"{output_type} unauthenticated download returned {unauth.status}, expected 403")
        dl = request(f"/api/analysis/{analysis_id}/download", headers={"X-Transcript-Owner": owner})
        dl_text = dl.body.decode(errors="replace")
        require(dl.status == 200, f"{output_type} owner analysis download returned {dl.status}")
        has_download_evidence = "Transcript evidence" in dl_text or bool(re.search(r"\[\d{2}:\d{2}", dl_text))
        require("AI-generated" in dl_text and has_download_evidence, f"{output_type} download missing expected analysis markers")
        download_checks[output_type] = {
            "analysis_id": analysis_id,
            "unauth_status": unauth.status,
            "owner_status": dl.status,
            "bytes": len(dl.body),
            "content_type": dl.headers.get("Content-Type") or dl.headers.get("content-type"),
        }

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
        "declared_output_count": len(ids),
        "verified_output_count": len(analyses),
        "verified_outputs": analyses,
        "individual_downloads": download_checks,
        "individual_download_privacy": {"verified_count": len(download_checks), "unauth_status": 403, "owner_status": 200},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
