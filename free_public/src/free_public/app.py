"""Two-button public transcriber for a 512MB free container.

Transcript only reads YouTube captions. Transcript with screenshots does that
first, then grabs timestamped frames with ffmpeg. A screenshot failure keeps
the transcript. This process does not load Whisper and does not call a paid API.
"""
from __future__ import annotations

import logging
import os
import secrets
import shutil
import threading
import time
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from free_public.captions import (
    PUBLIC_GENERIC,
    PUBLIC_TOOL_MISSING,
    CaptionError,
    normalize_youtube_url,
    resolve_binary,
    transcribe_youtube_url,
)
from free_public.screenshots import (
    capture_from_url,
    public_payload,
    safe_frame_path,
    safe_job_dir,
    screenshot_error_payload,
)

LOGGER = logging.getLogger("free-public-transcriber")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

JOBS: dict[str, dict] = {}
LOCK = threading.Lock()
PACKAGE_DIR = Path(__file__).resolve().parent


def data_dir() -> Path:
    path = Path(os.environ.get("TRANSCRIPT_DATA_DIR", "/tmp/free-public-transcript"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def static_dir() -> Path:
    configured = os.environ.get("TRANSCRIPT_STATIC_DIR", "").strip()
    path = Path(configured) if configured else PACKAGE_DIR / "static"
    return path


def tool_status() -> dict:
    ffmpeg = resolve_binary("ffmpeg", "FFMPEG_BIN")
    yt_dlp = resolve_binary("yt-dlp", "YT_DLP_BIN")
    missing = []
    if not ffmpeg:
        missing.append("ffmpeg")
    if not yt_dlp:
        missing.append("yt-dlp")
    return {
        "ffmpeg": bool(ffmpeg),
        "yt_dlp": bool(yt_dlp),
        "node": bool(shutil.which("node")),
        "missing": missing,
        "ready": not missing,
    }


app = FastAPI(title="Free public transcriber", docs_url=None, redoc_url=None)
if static_dir().is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir())), name="static")


def _active_jobs() -> int:
    return sum(1 for job in JOBS.values() if job.get("status") in {"queued", "running"})


def _public_job(job: dict) -> dict:
    shown = {
        "id": job.get("id"),
        "status": job.get("status"),
        "url": job.get("url"),
        "created_at": job.get("created_at"),
        "message": job.get("message"),
        "percent": job.get("percent"),
    }
    if job.get("record") is not None:
        shown["record"] = job["record"]
    if job.get("screenshots") is not None:
        shown["screenshots"] = job["screenshots"]
    if job.get("error"):
        shown["error"] = job["error"]
    return shown


def transcribe_youtube_url_to_record(url: str, work_dir: Optional[Path] = None) -> dict:
    scratch = work_dir or (data_dir() / "captions" / secrets.token_hex(8))
    record = transcribe_youtube_url(url, scratch)
    record["id"] = secrets.token_hex(6)
    record.pop("segments", None)
    return record


def _attach_screenshots(job_id: str, url: str) -> dict:
    """Capture screenshots after a transcript. Failures never fail the job."""
    try:
        out_dir = safe_job_dir(data_dir() / "screenshots", job_id)
        ffmpeg = resolve_binary("ffmpeg", "FFMPEG_BIN")
        yt_dlp = resolve_binary("yt-dlp", "YT_DLP_BIN")
        if not ffmpeg or not yt_dlp:
            raise RuntimeError("screenshot tools missing")

        def progress(message: str) -> None:
            with LOCK:
                current = JOBS.get(job_id)
                if current and current.get("status") == "running":
                    current["message"] = message
                    current["percent"] = 90

        result = capture_from_url(url, out_dir, yt_dlp, ffmpeg, progress=progress)
        return public_payload(job_id, result)
    except Exception:
        LOGGER.exception("screenshot capture failed for job %s", job_id)
        return screenshot_error_payload()


def run_url_job(job_id: str, url: str, include_screenshots: bool) -> None:
    try:
        with LOCK:
            JOBS[job_id].update({"status": "running", "message": "Checking captions", "percent": 15})
        record = transcribe_youtube_url_to_record(url, data_dir() / "captions" / job_id)
        screenshots = None
        if include_screenshots:
            with LOCK:
                JOBS[job_id].update({"message": "Grabbing screenshots", "percent": 80})
            screenshots = _attach_screenshots(job_id, record.get("source") or url)
            record["screenshots"] = screenshots
        with LOCK:
            JOBS[job_id].update({
                "status": "done",
                "message": "Ready",
                "percent": 100,
                "record": record,
                "screenshots": screenshots,
                "error": None,
            })
    except CaptionError as exc:
        LOGGER.info("caption job %s failed: %s", job_id, exc.public)
        with LOCK:
            JOBS[job_id].update({
                "status": "error",
                "error": exc.public,
                "message": exc.public,
                "percent": 100,
            })
    except Exception:
        LOGGER.exception("job %s failed", job_id)
        with LOCK:
            JOBS[job_id].update({
                "status": "error",
                "error": PUBLIC_GENERIC,
                "message": PUBLIC_GENERIC,
                "percent": 100,
            })


@app.get("/health")
def health() -> dict:
    tools = tool_status()
    return {
        "ok": True,
        "ready": tools["ready"],
        "runtime": "free-public",
        "transcription": "captions-only",
        "whisper": False,
        "paid_providers": [],
        "ffmpeg": tools["ffmpeg"],
        "yt_dlp": tools["yt_dlp"],
        "node": tools["node"],
        "missing": tools["missing"],
        "memory_budget_mb": 512,
    }


@app.get("/", response_model=None)
def index() -> Response:
    page = static_dir() / "index.html"
    if not page.is_file():
        return JSONResponse({"ok": False, "error": "UI is not bundled."}, status_code=500)
    return FileResponse(page, media_type="text/html")


@app.post("/api/transcribe-url-job")
def api_transcribe_url_job(
    url: str = Form(...),
    include_screenshots: Optional[str] = Form(None),
) -> JSONResponse:
    want_shots = str(include_screenshots or "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        normalized = normalize_youtube_url(url)
    except CaptionError as exc:
        return JSONResponse({"ok": False, "error": exc.public}, status_code=422)
    tools = tool_status()
    if not tools["ready"]:
        return JSONResponse({"ok": False, "error": PUBLIC_TOOL_MISSING, "missing": tools["missing"]}, status_code=503)
    with LOCK:
        if _active_jobs() >= 1:
            return JSONResponse(
                {"ok": False, "error": "This free server can run one video at a time. Try again shortly."},
                status_code=429,
            )
        job_id = secrets.token_hex(6)
        JOBS[job_id] = {
            "id": job_id,
            "status": "queued",
            "url": normalized,
            "created_at": time.time(),
            "include_screenshots": want_shots,
            "message": "Queued",
            "percent": 0,
        }
        queued = _public_job(JOBS[job_id])
    threading.Thread(
        target=run_url_job,
        args=(job_id, normalized, want_shots),
        name=f"free-public-{job_id}",
        daemon=False,
    ).start()
    return JSONResponse({"ok": True, "job": queued}, status_code=202)


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str) -> JSONResponse:
    try:
        safe_job_dir(data_dir() / "screenshots", job_id)
    except ValueError:
        return JSONResponse({"ok": False, "error": "Unknown job."}, status_code=404)
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            return JSONResponse({"ok": False, "error": "Unknown job."}, status_code=404)
        return JSONResponse({"ok": True, "job": _public_job(job)})


@app.get("/api/jobs/{job_id}/transcript.txt", response_model=None)
def api_transcript_download(job_id: str) -> PlainTextResponse:
    with LOCK:
        job = JOBS.get(job_id)
    record = (job or {}).get("record") or {}
    text = record.get("transcript") or ""
    if not job or job.get("status") != "done" or not text:
        return PlainTextResponse("Transcript is not ready.", status_code=404)
    return PlainTextResponse(
        text + "\n",
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=transcript.txt"},
    )


@app.get("/api/jobs/{job_id}/screenshots.zip", response_model=None)
def api_job_screenshots_zip(job_id: str) -> Response:
    try:
        job_dir = safe_job_dir(data_dir() / "screenshots", job_id)
    except ValueError:
        return JSONResponse({"ok": False, "error": "Unknown job."}, status_code=404)
    archive = job_dir / "screenshots.zip"
    if not archive.is_file():
        return JSONResponse({"ok": False, "error": "Screenshots are not available."}, status_code=404)
    return FileResponse(archive, media_type="application/zip", filename="screenshots.zip")


@app.get("/api/jobs/{job_id}/screenshots/{filename}", response_model=None)
def api_job_screenshot(job_id: str, filename: str) -> Response:
    try:
        job_dir = safe_job_dir(data_dir() / "screenshots", job_id)
        path = safe_frame_path(job_dir, filename)
    except ValueError:
        return JSONResponse({"ok": False, "error": "Unknown screenshot."}, status_code=404)
    if not path.is_file():
        return JSONResponse({"ok": False, "error": "Unknown screenshot."}, status_code=404)
    return FileResponse(path, media_type="image/jpeg")


def main() -> None:
    port = int(os.environ.get("PORT", "8090"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
