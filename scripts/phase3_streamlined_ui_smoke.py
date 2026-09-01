#!/usr/bin/env python3
"""Public Phase 3 streamlined UI/API smoke.

Verifies the replacement scope: transcript, Copy, one Download menu (TXT,
Markdown, SRT), Summary, Action Items, one Ask field/button, and Transcript
History. It also proves retired 17-button/100-assets controls are absent.
"""
from __future__ import annotations

import hashlib
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
OWNER = "phase3-streamlined-" + secrets.token_hex(12)
UA = "Mozilla/5.0 Epic Transcript Phase3 Streamlined Smoke"
OUT = Path("evidence/phase3-streamlined-ui-report.json")
EXPECTED_OUTPUTS = ["executive_summary", "action_items", "ask_question"]
REQUIRED_MARKERS = [
    'id="transcript"',
    'id="copyBtn"',
    'id="downloadFormat"',
    '<option value="txt">TXT</option>',
    '<option value="md">Markdown</option>',
    '<option value="srt">SRT</option>',
    'id="downloadBtn"',
    'id="summaryBtn"',
    'id="actionsBtn"',
    'id="questionInput"',
    'Quotes · Chapters · Hooks · FAQ',
    'id="askBtn"',
    'Your Transcript History',
]
RETIRED_MARKERS = [
    'id="allAnalysisBtn"', 'id="analysisMenu"', 'id="downloadVttBtn"',
    'id="downloadMdBtn"', 'id="downloadSrtBtn"', 'id="analysisCopyBtn"',
    'id="analysisDownloadBtn"', 'id="emailBtn"', 'All Outputs', 'AI Summary',
    'Main ideas', 'Best quotes', 'Blog post', 'Create 100 content assets',
    'content_assets_100', '/api/analyze-all/',
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
    require((rec.get("segment_count") or len(rec.get("segments") or [])) >= 10, "not enough timestamped segments")
    return rec


def validate_analysis(output_type: str, text: str) -> dict[str, Any]:
    has_timestamp = bool(re.search(r"\[\d{2}:\d{2}", text))
    has_disclaimer = "AI-generated" in text
    has_evidence = "Transcript evidence" in text or has_timestamp
    require(len(text.strip()) > 120, f"{output_type} too short: {len(text)} chars")
    require(has_disclaimer, f"{output_type} missing AI-generated disclaimer")
    require(has_evidence, f"{output_type} missing transcript evidence/timestamp")
    if output_type == "ask_question":
        require("quote" in text.lower() or "chapter" in text.lower() or "hook" in text.lower() or "faq" in text.lower() or "video" in text.lower(), "ask output did not address helper-style question")
    return {"chars": len(text), "has_timestamp": has_timestamp, "has_disclaimer": has_disclaimer, "has_evidence": has_evidence, "sha256": hashlib.sha256(text.encode()).hexdigest(), "preview": text[:260]}


def main() -> int:
    started = time.monotonic()
    root = request("/")
    require(root.status == 200, f"root returned {root.status}")
    html = root.body.decode(errors="replace")
    required = {marker: marker in html for marker in REQUIRED_MARKERS}
    retired = {marker: marker not in html for marker in RETIRED_MARKERS}
    require(all(required.values()), f"missing required UI markers: {[k for k, v in required.items() if not v]}")
    require(all(retired.values()), f"retired UI markers still present: {[k for k, v in retired.items() if not v]}")
    require(not any(secret in html for secret in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "generativelanguage.googleapis.com"]), "provider secret/API marker reached client HTML")

    outputs_resp = as_json(request("/api/analysis-outputs"))
    ids = [item.get("id") for item in outputs_resp.get("outputs", [])]
    require(ids == EXPECTED_OUTPUTS, f"unexpected output scope: {ids}")

    rec = complete_transcript()
    owner = rec.get("owner_token") or OWNER
    analyses: dict[str, Any] = {}
    analysis_ids: dict[str, str] = {}
    for output_type in EXPECTED_OUTPUTS:
        payload = {"output_type": output_type}
        if output_type == "ask_question":
            payload["question"] = "Give me quotes, chapters, hooks, and FAQ ideas."
        res = request(f"/api/analyze/{rec['id']}", method="POST", data=payload, headers={"X-Transcript-Owner": owner}, timeout=120)
        require(res.status == 200, f"{output_type} analysis HTTP {res.status}: {res.body[:200]!r}")
        data = as_json(res)
        require(data.get("ok") is True and data.get("output_type") == output_type, f"bad {output_type} response: {data}")
        text = str(data.get("analysis") or "")
        analyses[output_type] = validate_analysis(output_type, text)
        analysis_ids[output_type] = str(data.get("analysis_id") or "")

    for retired in ["main_ideas", "chapters", "best_quotes", "faq", "content_assets_100"]:
        blocked = request(f"/api/analyze/{rec['id']}", method="POST", data={"output_type": retired}, headers={"X-Transcript-Owner": owner})
        require(blocked.status == 400, f"retired output {retired} returned {blocked.status}, expected 400")

    report = {
        "ok": True,
        "base": BASE,
        "video_url": VIDEO,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "ui": {"required_present": required, "retired_absent": retired, "client_secret_markers_absent": True},
        "record": {"id": rec.get("id"), "title": rec.get("title"), "method": rec.get("method"), "language": rec.get("language"), "word_count": rec.get("word_count"), "segment_count": rec.get("segment_count") or len(rec.get("segments") or []), "cache_hit": rec.get("cache_hit")},
        "declared_outputs": ids,
        "analyses": analyses,
        "analysis_ids": analysis_ids,
        "gemini_marker_present": any("Gemini" in row["preview"] for row in analyses.values()),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
