#!/usr/bin/env python3
"""Public EPIC Transcript Machine recovery watchdog.

Checks the public no-login health and a tiny async transcript job. If the API
returns the known transient SQLite open failure, the watchdog can kickstart the
launchd API agent and verify recovery without exposing secrets.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from typing import Any
from urllib import error, parse, request

PUBLIC_HEADERS = {
    "User-Agent": "Mozilla/5.0 Hermes EPIC Transcript recovery watchdog",
    "Accept": "application/json,text/plain,*/*",
}
DEFAULT_BASE_URL = "https://epic-transcript.robyncrane.com"
DEFAULT_VIDEO_URL = "https://youtu.be/dQw4w9WgXcQ"
LAUNCHD_LABEL = "com.epic.transcript-api"


def http_request(method: str, url: str, data: dict[str, str] | None = None, timeout: int = 120) -> tuple[int, str]:
    body = None
    headers = dict(PUBLIC_HEADERS)
    if data is not None:
        body = parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # network failures are reportable watchdog failures
        return 0, str(exc)


def parse_json(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {"value": payload}
    except Exception:
        return {"raw": text[:500]}


def scrub_secrets(value: Any) -> Any:
    """Remove per-record owner tokens before watchdog JSON is printed or saved."""
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in {"owner_token", "token", "authorization"}:
                scrubbed[key] = "[redacted]"
            else:
                scrubbed[key] = scrub_secrets(item)
        return scrubbed
    if isinstance(value, list):
        return [scrub_secrets(item) for item in value]
    return value


def classify_failure(status: int, text: str) -> str | None:
    lowered = text.lower()
    if "unable to open database file" in lowered:
        return "sqlite_open_failure"
    if status == 0:
        return "network_failure"
    if 500 <= status <= 599:
        return "server_failure"
    return None


def health_check(base_url: str) -> dict[str, Any]:
    status, text = http_request("GET", f"{base_url}/health", timeout=30)
    payload = parse_json(text)
    return {
        "status": status,
        "ok": status == 200 and payload.get("ok") is True and payload.get("setup", {}).get("ready") is True,
        "failure": classify_failure(status, text),
        "payload": payload,
    }


def unwrap_job(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the actual job object from either start or poll API shapes."""
    job = payload.get("job")
    return job if isinstance(job, dict) else payload


def compact_job_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep watchdog evidence useful without storing transcripts or tokens."""
    job = unwrap_job(payload)
    compact: dict[str, Any] = {"ok": payload.get("ok")}
    if job:
        compact_job = {key: job.get(key) for key in ("id", "status", "percent", "url", "created_at", "started_at", "finished_at") if key in job}
        record = job.get("record")
        if isinstance(record, dict):
            compact_job["record"] = {
                "id": record.get("id"),
                "method": record.get("method"),
                "language": record.get("language"),
                "word_count": record.get("word_count"),
                "segment_count": record.get("segment_count") or len(record.get("segments", [])),
                "cache_hit": record.get("cache_hit"),
            }
        compact["job"] = compact_job
    return compact


def start_async_job(base_url: str, video_url: str, poll_seconds: int = 75, poll_interval: float = 1.0) -> dict[str, Any]:
    status, text = http_request("POST", f"{base_url}/api/transcribe-url-job", {"url": video_url}, timeout=60)
    payload = parse_json(text)
    job = unwrap_job(payload)
    result: dict[str, Any] = {"start_status": status, "failure": classify_failure(status, text), "payload": compact_job_payload(payload)}
    job_id = payload.get("job_id") or job.get("id")
    if status != 202 or not job_id:
        result["ok"] = False
        return result
    result["job_id"] = job_id
    deadline = time.monotonic() + poll_seconds
    while time.monotonic() <= deadline:
        time.sleep(poll_interval)
        poll_status, poll_text = http_request("GET", f"{base_url}/api/jobs/{job_id}", timeout=30)
        poll_payload = parse_json(poll_text)
        poll_job = unwrap_job(poll_payload)
        result["poll_status"] = poll_status
        result["poll_payload"] = compact_job_payload(poll_payload)
        result["job_status"] = poll_job.get("status")
        result["failure"] = classify_failure(poll_status, poll_text)
        if poll_job.get("status") in {"done", "error", "failed"}:
            break
    poll_job = unwrap_job(result.get("poll_payload", {})) if isinstance(result.get("poll_payload"), dict) else {}
    record = poll_job.get("record", {}) if isinstance(poll_job, dict) else {}
    result["ok"] = (
        result.get("poll_status") == 200
        and poll_job.get("status") == "done"
        and record.get("word_count", 0) >= 100
        and (record.get("segment_count") or len(record.get("segments", []))) >= 20
    )
    if not result["ok"] and result.get("failure") is None:
        result["failure"] = classify_failure(result.get("poll_status", 0), json.dumps(result.get("poll_payload", {})))
        if result.get("failure") is None and result.get("job_status") not in {"done", "error", "failed"}:
            result["failure"] = "job_timeout"
    if record:
        result["record"] = {
            "id": record.get("id"),
            "method": record.get("method"),
            "word_count": record.get("word_count"),
            "segment_count": record.get("segment_count") or len(record.get("segments", [])),
            "cache_hit": record.get("cache_hit"),
        }
    return result


def kickstart_api(label: str = LAUNCHD_LABEL) -> dict[str, Any]:
    domain = f"gui/{os.getuid()}/{label}"
    cmd = ["launchctl", "kickstart", "-k", domain]
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=30)
    return {"command": cmd, "returncode": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def run_watchdog(base_url: str, video_url: str, no_restart: bool = False) -> dict[str, Any]:
    started = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    report: dict[str, Any] = {"base_url": base_url, "video_url": video_url, "started": started, "restarted": False}
    report["health_before"] = health_check(base_url)
    report["async_before"] = start_async_job(base_url, video_url)
    needs_restart = any(
        part.get("failure") in {"sqlite_open_failure", "server_failure", "network_failure"}
        for part in (report["health_before"], report["async_before"])
    )
    if needs_restart and not no_restart:
        report["restart"] = kickstart_api()
        report["restarted"] = True
        time.sleep(4)
        report["health_after"] = health_check(base_url)
        report["async_after"] = start_async_job(base_url, video_url)
    final_health = report.get("health_after", report["health_before"])
    final_async = report.get("async_after", report["async_before"])
    report["ok"] = bool(final_health.get("ok") and final_async.get("ok"))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Check and recover EPIC Transcript public API health.")
    parser.add_argument("base_url", nargs="?", default=DEFAULT_BASE_URL)
    parser.add_argument("--video-url", default=DEFAULT_VIDEO_URL)
    parser.add_argument("--no-restart", action="store_true", help="Report only. Do not kickstart launchd on failure.")
    parser.add_argument("--out", help="Write JSON report to this path.")
    args = parser.parse_args()
    report = run_watchdog(args.base_url.rstrip("/"), args.video_url, args.no_restart)
    report = scrub_secrets(report)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
