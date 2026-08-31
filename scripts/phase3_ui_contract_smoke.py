#!/usr/bin/env python3
"""Public Phase 3 UI contract smoke without Chrome/CDP.

This does not replace browser visual QC. It protects the clickable public
contract while Chrome remote debugging is unavailable or flaky:
- public root exposes the visible analysis controls.
- root JavaScript wires those controls to the async transcript and analysis APIs.
- public API can complete a transcript, all-outputs analysis, ask-question output,
  and Markdown analysis download with one owner token.
"""
from __future__ import annotations

import json
import re
import secrets
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import requests

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://epic-transcript.robyncrane.com").rstrip("/")
VIDEO_URL = sys.argv[2] if len(sys.argv) > 2 else "https://youtu.be/dQw4w9WgXcQ"
OWNER = "phase3-ui-contract-" + secrets.token_hex(12)
OUT = Path("evidence/phase3-ui-contract-report.json")


class IdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.buttons: dict[str, str] = {}
        self._current_button: str | None = None
        self._button_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if attr.get("id"):
            self.ids.add(attr["id"] or "")
        if tag == "button" and attr.get("id"):
            self._current_button = attr["id"]
            self._button_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "button" and self._current_button:
            self.buttons[self._current_button] = " ".join("".join(self._button_text).split())
            self._current_button = None
            self._button_text = []

    def handle_data(self, data: str) -> None:
        if self._current_button:
            self._button_text.append(data)


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def post_form(path: str, data: dict[str, str], timeout: int = 30) -> requests.Response:
    return requests.post(
        BASE + path,
        data=data,
        headers={"User-Agent": "Mozilla/5.0 Phase3ContractSmoke/1.0", "X-Transcript-Owner": OWNER},
        timeout=timeout,
    )


def get(path_or_url: str, timeout: int = 30, owner: str | None = None) -> requests.Response:
    url = path_or_url if path_or_url.startswith("http") else BASE + path_or_url
    return requests.get(url, headers={"User-Agent": "Mozilla/5.0 Phase3ContractSmoke/1.0", "X-Transcript-Owner": owner or OWNER}, timeout=timeout)


report: dict[str, Any] = {"base": BASE, "video_url": VIDEO_URL}

root = get("/")
report["root_status"] = root.status_code
report["root_bytes"] = len(root.text)
require(root.status_code == 200, f"root returned {root.status_code}")
require("login" not in root.url.lower(), f"root redirected to {root.url}")

parser = IdParser()
parser.feed(root.text)
required_ids = [
    "form", "url", "grab", "file", "drop", "result", "transcript", "copyBtn",
    "downloadBtn", "downloadMdBtn", "downloadSrtBtn", "allAnalysisBtn", "analysisCopyBtn",
    "analysisDownloadBtn", "analysisPanel", "analysisMenu", "questionInput", "askBtn", "analysisBox",
]
missing_ids = [x for x in required_ids if x not in parser.ids]
report["missing_ids"] = missing_ids
require(not missing_ids, f"missing public UI ids: {missing_ids}")

expected_button_text = {
    "grab": "Get Video Transcript",
    "allAnalysisBtn": "All Outputs",
    "analysisCopyBtn": "Copy Analysis",
    "analysisDownloadBtn": "Download Analysis",
    "askBtn": "Ask",
}
report["button_text"] = {k: parser.buttons.get(k) for k in expected_button_text}
for bid, label in expected_button_text.items():
    require(parser.buttons.get(bid) == label, f"button {bid} text changed: {parser.buttons.get(bid)!r}")

contracts = {
    "async_submit": "/api/transcribe-url-job" in root.text and "/api/jobs/" in root.text,
    "old_sync_submit_absent": "/api/transcribe-url'," not in root.text and '"/api/transcribe-url"' not in root.text,
    "all_outputs_wired": "runAllStarterOutputs" in root.text and "/api/analyze-all/" in root.text,
    "single_analysis_wired": "analyzeCurrent" in root.text and "/api/analyze/" in root.text,
    "analysis_copy_wired": "navigator.clipboard.writeText(text)" in root.text and "Analysis copied" in root.text,
    "analysis_download_wired": "/api/analysis/" in root.text and "/download" in root.text,
}
report["contracts"] = contracts
require(all(contracts.values()), f"UI contract failed: {[k for k, v in contracts.items() if not v]}")

start = post_form("/api/transcribe-url-job", {"url": VIDEO_URL, "owner": OWNER})
report["start_status"] = start.status_code
require(start.status_code == 202, f"start returned {start.status_code}: {start.text[:300]}")
job_id = start.json()["job"]["id"]
report["job_id"] = job_id

job = None
for _ in range(90):
    jr = get(f"/api/jobs/{job_id}")
    require(jr.status_code == 200, f"job poll returned {jr.status_code}: {jr.text[:300]}")
    job = jr.json()["job"]
    if job.get("status") in {"done", "error"}:
        break
    time.sleep(1)
require(job is not None and job.get("status") == "done", f"job did not complete: {job}")
assert job is not None
record = job["record"]
effective_owner = valid_owner = record.get("owner_token") or OWNER
report["owner_token_returned"] = bool(record.get("owner_token"))
report["record"] = {
    "id": record.get("id"),
    "title": record.get("title") or record.get("source"),
    "method": record.get("method"),
    "language": record.get("language"),
    "word_count": record.get("word_count"),
    "segment_count": len(record.get("segments") or []),
    "cache_hit": record.get("cache_hit"),
    "transcript_chars": len(record.get("transcript") or ""),
}
require(report["record"]["transcript_chars"] > 500, "transcript is too short for UI proof")

all_resp = requests.post(
    f"{BASE}/api/analyze-all/{record['id']}",
    headers={"User-Agent": "Mozilla/5.0 Phase3ContractSmoke/1.0", "X-Transcript-Owner": effective_owner},
    timeout=60,
)
report["all_outputs_status"] = all_resp.status_code
require(all_resp.status_code == 200, f"all outputs returned {all_resp.status_code}: {all_resp.text[:300]}")
all_data = all_resp.json()
analysis = all_data.get("analysis") or ""
section_count = len(re.findall(r"^# ", analysis, flags=re.MULTILINE))
report["all_outputs"] = {
    "analysis_id": all_data.get("analysis_id"),
    "section_count": section_count,
    "analysis_chars": len(analysis),
    "has_disclaimer": "AI-generated" in analysis,
    "has_timestamp": bool(re.search(r"\[\d{2}:\d{2}", analysis)),
}
require(section_count >= 16, f"expected at least 16 combined output sections, got {section_count}")
require(report["all_outputs"]["analysis_chars"] > 5000, "combined analysis too short")
require(report["all_outputs"]["has_disclaimer"], "analysis disclaimer missing")
require(report["all_outputs"]["analysis_id"], "combined analysis id missing")

dl = get(f"/api/analysis/{all_data['analysis_id']}/download", owner=effective_owner)
report["download"] = {"status": dl.status_code, "content_type": dl.headers.get("content-type"), "bytes": len(dl.content)}
require(dl.status_code == 200, f"analysis download returned {dl.status_code}")
require(len(dl.content) > 5000, "analysis download too small")

ask = requests.post(
    f"{BASE}/api/analyze/{record['id']}",
    data={"output_type": "ask_question", "question": "What should Trevor do with this video?"},
    headers={"User-Agent": "Mozilla/5.0 Phase3ContractSmoke/1.0", "X-Transcript-Owner": effective_owner},
    timeout=60,
)
report["ask_status"] = ask.status_code
require(ask.status_code == 200, f"ask returned {ask.status_code}: {ask.text[:300]}")
ask_data = ask.json()
ask_text = ask_data.get("analysis") or ""
report["ask"] = {"analysis_id": ask_data.get("analysis_id"), "chars": len(ask_text), "has_question_context": "Trevor" in ask_text or "video" in ask_text.lower()}
require(len(ask_text) > 500, "ask-question analysis too short")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
