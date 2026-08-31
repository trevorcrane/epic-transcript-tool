#!/usr/bin/env python3
"""Phase 2 public release-gate smoke checks.

Covers the pieces that are easy to regress outside the generated-media smoke:
supported upload formats in the public file accept contract, helpful unsupported
file/URL failures, no paid-provider requirement, and public delete/readback cleanup.
"""
from __future__ import annotations

import json
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8090"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence" / "phase2-release-gate-report.json"
SUPPORTED_EXTS = [".aac", ".avi", ".flac", ".m4a", ".md", ".mkv", ".mov", ".mp3", ".mp4", ".ogg", ".opus", ".srt", ".txt", ".vtt", ".wav", ".webm"]
OWNER = "phase2-gate-" + secrets.token_urlsafe(24).replace("-", "_")
UA = "Mozilla/5.0 EpicTranscriptPhase2Gate/1.0"


def curl(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["curl", "-sS", "-L", "-A", UA, *args], capture_output=True, text=True, timeout=timeout)


def split_body_status(stdout: str) -> tuple[str, int]:
    lines = stdout.strip().splitlines()
    if not lines:
        return "", 0
    status = int(lines[-1]) if lines[-1].isdigit() else 0
    return "\n".join(lines[:-1]), status


def check_root() -> dict:
    proc = curl([BASE + "/", "-w", "\n%{http_code}\n"])
    body, status = split_body_status(proc.stdout)
    missing_exts = [ext for ext in SUPPORTED_EXTS if ext not in body]
    markers = ["public media URL", "upload", "TXT", "Markdown", "SRT", "VTT"]
    missing_markers = [m for m in markers if m not in body]
    return {
        "http_status": status,
        "bytes": len(body.encode()),
        "missing_exts": missing_exts,
        "missing_markers": missing_markers,
        "ok": status == 200 and not missing_exts and not missing_markers,
    }


def check_health() -> dict:
    proc = curl([BASE + "/health", "-w", "\n%{http_code}\n"])
    body, status = split_body_status(proc.stdout)
    row = {"http_status": status, "ok": False}
    try:
        data = json.loads(body)
        setup = data.get("setup") or {}
        optional_missing = setup.get("optional_missing") or []
        row.update(ready=setup.get("ready"), missing=setup.get("missing"), optional_missing=optional_missing)
        row["no_paid_provider_required"] = "GEMINI_API_KEY" in optional_missing
        row["ok"] = status == 200 and setup.get("ready") is True and setup.get("missing") == []
    except Exception as exc:
        row.update(error=str(exc), body=body[:500])
    return row


def unsupported_upload() -> dict:
    proc = curl([
        "-X", "POST", f"{BASE}/api/transcribe-upload",
        "-F", f"owner={OWNER}", "-F", "file=@-;filename=unsupported.exe;type=application/octet-stream",
        "-w", "\n%{http_code}\n",
    ], timeout=60)
    # curl cannot combine stdin file content with simple args here, so fall back to temp file if stdin upload failed.
    body, status = split_body_status(proc.stdout)
    if status == 0 or "Failed to open/read" in proc.stderr:
        tmp = ROOT / "evidence" / "unsupported.exe"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(b"not media")
        try:
            proc = curl(["-X", "POST", f"{BASE}/api/transcribe-upload", "-F", f"owner={OWNER}", "-F", f"file=@{tmp};type=application/octet-stream", "-w", "\n%{http_code}\n"], timeout=60)
            body, status = split_body_status(proc.stdout)
        finally:
            tmp.unlink(missing_ok=True)
    row = {"http_status": status, "ok": False}
    try:
        detail = json.loads(body).get("detail", "")
        row.update(detail=detail, missing_exts=[ext for ext in SUPPORTED_EXTS if ext not in detail])
        row["ok"] = status == 400 and "Unsupported file type" in detail and "Upload one of:" in detail and not row["missing_exts"]
    except Exception as exc:
        row.update(error=str(exc), body=body[:500], stderr=proc.stderr[:500])
    return row


def unsupported_url() -> dict:
    proc = curl(["-X", "POST", f"{BASE}/api/transcribe-url", "-F", f"owner={OWNER}", "-F", "url=https://not-a-real.example/video", "-w", "\n%{http_code}\n"], timeout=120)
    body, status = split_body_status(proc.stdout)
    row = {"http_status": status, "ok": False}
    try:
        detail = json.loads(body).get("detail", "")
        row.update(detail=detail)
        row["ok"] = status == 422 and "upload" in detail.lower() and "another route" in detail.lower()
    except Exception as exc:
        row.update(error=str(exc), body=body[:500])
    return row


def upload_text_and_cleanup() -> dict:
    fixture = ROOT / "evidence" / "phase2-cleanup-upload.txt"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text("[00:00] Phase two cleanup upload proof for delete retention.\n", encoding="utf-8")
    try:
        proc = curl(["-X", "POST", f"{BASE}/api/transcribe-upload", "-F", f"owner={OWNER}", "-F", f"file=@{fixture};type=text/plain", "-w", "\n%{http_code}\n"], timeout=120)
        body, upload_status = split_body_status(proc.stdout)
        data = json.loads(body)
        rec = data.get("record") or {}
        rec_id = rec.get("id")
        analysis_id = None
        analysis_status = None
        if rec_id:
            aproc = curl(["-X", "POST", f"{BASE}/api/analyze/{rec_id}", "-H", f"X-Transcript-Owner: {OWNER}", "-F", "output_type=executive_summary", "-w", "\n%{http_code}\n"], timeout=120)
            abody, analysis_status = split_body_status(aproc.stdout)
            analysis_id = (json.loads(abody).get("analysis_id") if analysis_status == 200 else None)
        delete_status = transcript_status = analysis_download_status = 0
        if rec_id:
            dproc = curl(["-X", "DELETE", f"{BASE}/api/transcripts/{rec_id}", "-H", f"X-Transcript-Owner: {OWNER}", "-w", "\n%{http_code}\n"], timeout=60)
            _, delete_status = split_body_status(dproc.stdout)
            gproc = curl([f"{BASE}/api/transcripts/{rec_id}", "-H", f"X-Transcript-Owner: {OWNER}", "-w", "\n%{http_code}\n"], timeout=60)
            _, transcript_status = split_body_status(gproc.stdout)
        if analysis_id:
            dlproc = curl([f"{BASE}/api/analysis/{analysis_id}/download", "-H", f"X-Transcript-Owner: {OWNER}", "-w", "\n%{http_code}\n"], timeout=60)
            _, analysis_download_status = split_body_status(dlproc.stdout)
        return {
            "upload_status": upload_status,
            "record_id": rec_id,
            "method": rec.get("method"),
            "word_count": rec.get("word_count"),
            "analysis_status": analysis_status,
            "analysis_id": analysis_id,
            "delete_status": delete_status,
            "transcript_readback_status": transcript_status,
            "analysis_download_after_delete_status": analysis_download_status,
            "ok": upload_status == 200 and rec.get("method") == "passthrough" and analysis_status == 200 and delete_status == 200 and transcript_status == 404 and analysis_download_status == 404,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        fixture.unlink(missing_ok=True)


def main() -> int:
    payload = {
        "base_url": BASE,
        "supported_formats": SUPPORTED_EXTS,
        "root_format_copy": check_root(),
        "health_no_paid_provider_required": check_health(),
        "unsupported_upload_failure": unsupported_upload(),
        "unsupported_url_failure": unsupported_url(),
        "delete_cleanup_readback": upload_text_and_cleanup(),
    }
    payload["all_ok"] = all(v.get("ok") for k, v in payload.items() if isinstance(v, dict))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
