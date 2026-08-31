#!/usr/bin/env python3
"""Phase 1 public DOM/click/mobile/accessibility smoke without Chrome/CDP.

This harness exists for release evidence when browser remote debugging is flaky.
It does not claim pixel-perfect visual QA; it verifies the public no-login DOM,
JavaScript click wiring, public transcript path, copy/download contracts, mobile CSS
breakpoints/touch sizing, and static contrast ratios for critical controls.
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
VIDEO_URL = sys.argv[2] if len(sys.argv) > 2 else "https://www.youtube.com/shorts/1WW76Rz4nqM"
OWNER = "phase1-dom-click-" + secrets.token_hex(12)
OUT = Path("evidence/phase1-dom-click-mobile-a11y-report.json")
HEADERS = {"User-Agent": "Mozilla/5.0 Phase1DomClickMobileA11ySmoke/1.0", "X-Transcript-Owner": OWNER}


class PublicHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.buttons: dict[str, str] = {}
        self.inputs: dict[str, dict[str, str]] = {}
        self.labels: dict[str, str] = {}
        self._button_id: str | None = None
        self._button_text: list[str] = []
        self._label_id: str | None = None
        self._label_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: v or "" for k, v in attrs}
        if attr.get("id"):
            self.ids.add(attr["id"])
        if tag == "button" and attr.get("id"):
            self._button_id = attr["id"]
            self._button_text = []
        if tag == "input" and attr.get("id"):
            self.inputs[attr["id"]] = attr
        if tag == "label" and attr.get("id"):
            self._label_id = attr["id"]
            self._label_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "button" and self._button_id:
            self.buttons[self._button_id] = " ".join("".join(self._button_text).split())
            self._button_id = None
            self._button_text = []
        if tag == "label" and self._label_id:
            self.labels[self._label_id] = " ".join("".join(self._label_text).split())
            self._label_id = None
            self._label_text = []

    def handle_data(self, data: str) -> None:
        if self._button_id:
            self._button_text.append(data)
        if self._label_id:
            self._label_text.append(data)


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def request_get(path_or_url: str, *, owner: str | None = OWNER, timeout: int = 30) -> requests.Response:
    url = path_or_url if path_or_url.startswith("http") else BASE + path_or_url
    headers = dict(HEADERS)
    if owner:
        headers["X-Transcript-Owner"] = owner
    return requests.get(url, headers=headers, timeout=timeout)


def request_post(path: str, data: dict[str, str] | None = None, *, owner: str | None = OWNER, timeout: int = 60) -> requests.Response:
    headers = dict(HEADERS)
    if owner:
        headers["X-Transcript-Owner"] = owner
    return requests.post(BASE + path, data=data or {}, headers=headers, timeout=timeout)


def hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def channel(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str) -> float:
    a, b = luminance(hex_to_rgb(fg)), luminance(hex_to_rgb(bg))
    lighter, darker = max(a, b), min(a, b)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def poll_job(job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 240
    last_job: dict[str, Any] = {}
    while time.monotonic() < deadline:
        jr = request_get(f"/api/jobs/{job_id}")
        require(jr.status_code == 200, f"job poll returned {jr.status_code}: {jr.text[:300]}")
        last_job = (jr.json().get("job") or {})
        if last_job.get("status") in {"done", "error"}:
            break
        time.sleep(1)
    require(last_job.get("status") == "done", f"job did not complete: {last_job}")
    return last_job


report: dict[str, Any] = {"base": BASE, "video_url": VIDEO_URL, "owner": OWNER}

root = request_get("/", owner=None)
report["root"] = {"status": root.status_code, "bytes": len(root.text), "url": root.url}
require(root.status_code == 200, f"root returned {root.status_code}")
require("login" not in root.url.lower(), f"root redirected to {root.url}")

parser = PublicHtmlParser()
parser.feed(root.text)
required_ids = ["form", "url", "grab", "file", "drop", "result", "transcript", "copyBtn", "downloadBtn", "downloadMdBtn", "downloadSrtBtn", "downloadVttBtn", "toast", "status", "statusText"]
missing_ids = [item for item in required_ids if item not in parser.ids]
report["dom"] = {
    "missing_ids": missing_ids,
    "button_text": {k: parser.buttons.get(k) for k in ["grab", "copyBtn", "downloadBtn", "downloadMdBtn", "downloadSrtBtn", "downloadVttBtn"]},
    "url_input": parser.inputs.get("url"),
    "file_input_accept": (parser.inputs.get("file") or {}).get("accept"),
    "drop_label_text": parser.labels.get("drop"),
}
require(not missing_ids, f"missing DOM IDs: {missing_ids}")
require(parser.buttons.get("grab") == "Get Transcript", "primary button text changed")
require(parser.inputs.get("url", {}).get("type") == "url", "URL input is not type=url")
require(parser.inputs.get("url", {}).get("inputmode") == "url", "URL input lacks mobile url inputmode")
for fmt in [".mp4", ".mov", ".webm", ".mp3", ".m4a", ".wav", ".txt", ".md", ".srt", ".vtt"]:
    require(fmt in (report["dom"]["file_input_accept"] or ""), f"file accept missing {fmt}")

script_contracts = {
    "form_submit_prevents_default": "els.form.addEventListener('submit'" in root.text and "e.preventDefault()" in root.text,
    "async_job_path": "/api/transcribe-url-job" in root.text and "/api/jobs/" in root.text,
    "old_sync_url_submit_absent": "'/api/transcribe-url'" not in root.text and '"/api/transcribe-url"' not in root.text,
    "copy_button_clipboard": "els.copyBtn.addEventListener('click'" in root.text and "navigator.clipboard.writeText(currentRecord.transcript" in root.text,
    "auto_copy_after_result": "autoCopy(rec.transcript" in root.text and "Copied to clipboard ✓" in root.text,
    "txt_download_click": "els.downloadBtn.addEventListener('click', () => downloadCurrent('txt'))" in root.text,
    "md_download_click": "els.downloadMdBtn.addEventListener('click', () => downloadCurrent('md'))" in root.text,
    "srt_download_click": "els.downloadSrtBtn.addEventListener('click', () => downloadCurrent('srt'))" in root.text,
    "vtt_download_click": "els.downloadVttBtn.addEventListener('click', () => downloadCurrent('vtt'))" in root.text,
    "download_link_api": "/api/transcripts/' + currentRecord.id + '/download-link?format=" in root.text,
    "touch_drop_click": "els.drop.addEventListener('click'" in root.text and "els.file.click()" in root.text,
}
report["script_contracts"] = script_contracts
require(all(script_contracts.values()), f"script contracts failed: {[k for k, v in script_contracts.items() if not v]}")

mobile_contracts = {
    "viewport_meta": 'name="viewport" content="width=device-width, initial-scale=1.0"' in root.text,
    "mobile_breakpoint_760": "@media (max-width: 760px)" in root.text,
    "narrow_breakpoint_420": "@media (max-width: 420px)" in root.text,
    "mobile_single_column_url_row": ".url-row { grid-template-columns:1fr; }" in root.text,
    "mobile_grab_full_width": ".grab-btn { width:100%; height:56px; }" in root.text,
    "touch_target_grab_height": ".grab-btn { height:58px;" in root.text,
    "touch_target_url_height": ".url-input { min-width:0; width:100%; height:58px;" in root.text,
    "body_overflow_x_hidden": "overflow-x:hidden" in root.text,
    "reduced_motion_supported": "prefers-reduced-motion: reduce" in root.text,
    "visible_focus_ring": ":focus-visible { outline:3px solid #ff77bf" in root.text,
}
report["mobile_accessibility_contracts"] = mobile_contracts
require(all(mobile_contracts.values()), f"mobile/a11y contracts failed: {[k for k, v in mobile_contracts.items() if not v]}")

contrast_checks = {
    "body_white_on_dark": {"fg": "#ffffff", "bg": "#09090b", "ratio": contrast("#ffffff", "#09090b"), "required": 4.5},
    "result_text_on_light": {"fg": "#3f3f46", "bg": "#fbfaf8", "ratio": contrast("#3f3f46", "#fbfaf8"), "required": 4.5},
    "dark_button_text_on_purple": {"fg": "#ffffff", "bg": "#7b2ff7", "ratio": contrast("#ffffff", "#7b2ff7"), "required": 4.5},
    "plain_button_text_on_white": {"fg": "#171719", "bg": "#ffffff", "ratio": contrast("#171719", "#ffffff"), "required": 4.5},
    "faq_text_on_light": {"fg": "#171719", "bg": "#f7f6f3", "ratio": contrast("#171719", "#f7f6f3"), "required": 4.5},
    "toast_text_on_dark_success": {"fg": "#bbf7d0", "bg": "#09090b", "ratio": contrast("#bbf7d0", "#09090b"), "required": 4.5},
}
report["contrast"] = contrast_checks
failed_contrast = {k: v for k, v in contrast_checks.items() if v["ratio"] < v["required"]}
require(not failed_contrast, f"contrast checks failed: {failed_contrast}")

start = request_post("/api/transcribe-url-job", {"url": VIDEO_URL, "owner": OWNER}, timeout=60)
report["transcribe_start"] = {"status": start.status_code, "body_head": start.text[:200]}
require(start.status_code == 202, f"job start returned {start.status_code}: {start.text[:300]}")
job_id = start.json()["job"]["id"]
job = poll_job(job_id)
record = job["record"]
effective_owner = record.get("owner_token") or OWNER
segs = record.get("segments") or []
report["record"] = {
    "job_id": job_id,
    "id": record.get("id"),
    "title": record.get("title") or record.get("source"),
    "method": record.get("method"),
    "language": record.get("language"),
    "word_count": record.get("word_count"),
    "segment_count": len(segs),
    "transcript_chars": len(record.get("transcript") or ""),
    "cache_hit": record.get("cache_hit"),
    "first": (segs[0].get("text") if segs else "")[:120],
    "last": (segs[-1].get("text") if segs else "")[:120],
}
require(report["record"]["transcript_chars"] > 500, "transcript too short for copy proof")
require(len(segs) >= 1 and all(float(segs[i].get("start", -1)) <= float(segs[i + 1].get("start", -1)) for i in range(len(segs) - 1)), "timestamps missing or not increasing")

# Non-browser copy proof: the DOM click handler writes currentRecord.transcript to clipboard;
# here we verify the exact copy source is populated by the public job payload.
report["copy_contract"] = {
    "clipboard_handler_writes_transcript": script_contracts["copy_button_clipboard"],
    "toast_success_text_present": "Copied to clipboard ✓" in root.text,
    "copy_source_chars": len(record.get("transcript") or ""),
    "copy_source_head": (record.get("transcript") or "")[:180],
}

report["downloads"] = {}
for fmt, min_bytes in {"txt": 500, "md": 600, "srt": 500, "vtt": 500}.items():
    dl_start = request_post(
        f"/api/transcripts/{record['id']}/download-link?format={fmt}",
        owner=effective_owner,
        timeout=30,
    )
    require(dl_start.status_code == 200, f"download-link {fmt} returned {dl_start.status_code}: {dl_start.text[:300]}")
    url = dl_start.json().get("url")
    require(url, f"download-link {fmt} missing signed url")
    dl = request_get(url, owner=effective_owner, timeout=30)
    report["downloads"][fmt] = {"link_status": dl_start.status_code, "download_status": dl.status_code, "bytes": len(dl.content), "content_type": dl.headers.get("content-type")}
    require(dl.status_code == 200, f"download {fmt} returned {dl.status_code}")
    require(len(dl.content) >= min_bytes, f"download {fmt} too small: {len(dl.content)} bytes")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(report, indent=2, ensure_ascii=False))
