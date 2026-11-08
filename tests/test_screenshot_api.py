"""Screenshot jobs on the production c943233 app. No session-auth backport."""
from __future__ import annotations

import io
import shutil
import subprocess
import threading
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app
import screenshots


FAKE_RECORD = {
    "id": "rec-test",
    "source": "https://youtu.be/abcdefghijk",
    "transcript": "hello from captions",
    "method": "captions",
    "duration_seconds": 10,
}


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    assert path, "ffmpeg is not on PATH; this file test needs the real binary"
    return path


def _wait_job(client: TestClient, job_id: str) -> dict:
    job = {}
    for _ in range(80):
        res = client.get(f"/api/jobs/{job_id}")
        assert res.status_code == 200, res.text
        job = res.json()["job"]
        if job.get("status") in {"done", "error"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {job}")


def _write_capture(url, out_dir, yt_bin, ffmpeg_bin, work_dir=None, progress=None):
    del url, yt_bin, work_dir, progress
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "frame_0000_0001.00s.jpg"
    subprocess.run(
        [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x36:d=1",
         "-frames:v", "1", "-update", "1", "-q:v", "3", "-y", str(dest)],
        check=True, timeout=20,
    )
    frame = {"time": 1.0, "timestamp": "0:01", "path": dest, "filename": dest.name}
    screenshots.write_manifest([frame], out_dir / "manifest.csv")
    screenshots.build_zip([frame], out_dir / "screenshots.zip")
    return {"status": "done", "error": None, "count": 1, "frames": [frame], "zip_path": out_dir / "screenshots.zip", "duration": 2.0}


def test_transcript_only_does_not_capture_screenshots():
    with patch.object(app, "transcribe_youtube_url_to_record", return_value=dict(FAKE_RECORD)) as transcribed, \
         patch.object(app, "capture_from_url") as capture:
        client = TestClient(app.app)
        started = client.post("/api/transcribe-url-job", data={"url": "https://youtu.be/abcdefghijk"})
        assert started.status_code == 202
        assert started.json()["job"]["include_screenshots"] is False
        job = _wait_job(client, started.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["record"]["transcript"] == "hello from captions"
    assert job.get("screenshots") in (None, {})
    capture.assert_not_called()
    transcribed.assert_called()


def test_screenshot_failure_keeps_transcript_and_hides_internal_error():
    with patch.object(app, "transcribe_youtube_url_to_record", return_value=dict(FAKE_RECORD)), \
         patch.object(app, "capture_from_url", side_effect=RuntimeError("ffmpeg exploded /tmp/secret-path")):
        client = TestClient(app.app)
        started = client.post(
            "/api/transcribe-url-job",
            data={"url": "https://youtu.be/abcdefghijk", "include_screenshots": "1"},
        )
        assert started.status_code == 202
        job = _wait_job(client, started.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["record"]["transcript"] == "hello from captions"
    assert job["screenshots"]["status"] == "error"
    assert job["screenshots"]["error"] == "Screenshots could not be captured."
    blob = str(job)
    assert "ffmpeg exploded" not in blob
    assert "/tmp/secret-path" not in blob


def test_screenshot_success_serves_jpeg_and_zip(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app, "resolve_binary", lambda *args, **kwargs: "ffmpeg")
    with patch.object(app, "transcribe_youtube_url_to_record", return_value=dict(FAKE_RECORD)), \
         patch.object(app, "capture_from_url", side_effect=_write_capture):
        client = TestClient(app.app)
        started = client.post(
            "/api/transcribe-url-job",
            data={"url": "https://youtu.be/abcdefghijk", "include_screenshots": "1"},
        )
        job = _wait_job(client, started.json()["job"]["id"])
    assert job["status"] == "done"
    shots = job["screenshots"]
    assert shots["frames"][0]["timestamp"] == "0:01"
    image = client.get(shots["frames"][0]["url"])
    archive = client.get(shots["zip_url"])
    assert image.status_code == 200
    assert image.content[:3] == b"\xff\xd8\xff"
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as zf:
        assert shots["frames"][0]["filename"] in zf.namelist()
        assert "0:01" in zf.read("manifest.csv").decode()


def test_downloader_failure_keeps_transcript_without_a_second_attempt(tmp_path, monkeypatch):
    """Ordinary YouTube downloader failure. The stub is an explicit function, not PATH."""
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app, "resolve_binary", lambda *args, **kwargs: "ffmpeg")
    calls = []

    def fail_download(*args, **kwargs):
        calls.append(args[0] if args else "")
        raise RuntimeError("yt-dlp exited 1")

    monkeypatch.setattr(screenshots, "public_http_url", lambda url: url)
    monkeypatch.setattr(screenshots, "download_360p", fail_download)
    with patch.object(app, "transcribe_youtube_url_to_record", return_value=dict(FAKE_RECORD)):
        client = TestClient(app.app)
        started = client.post(
            "/api/transcribe-url-job",
            data={"url": "https://youtu.be/abcdefghijk", "include_screenshots": "1"},
        )
        job = _wait_job(client, started.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["record"]["transcript"] == "hello from captions"
    assert job["screenshots"]["status"] == "error"
    assert job["screenshots"]["error"] == "Screenshots could not be captured."
    assert calls == ["https://www.youtube.com/watch?v=abcdefghijk"]


def test_non_youtube_screenshot_does_not_resolve_or_download(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app, "resolve_binary", lambda *args, **kwargs: "ffmpeg")
    looked_up = []

    def dns(*args, **kwargs):
        looked_up.append(args)
        raise AssertionError(f"DNS lookup {args}")

    monkeypatch.setattr(screenshots.socket, "getaddrinfo", dns)
    called = []
    monkeypatch.setattr(screenshots, "download_360p", lambda *args, **kwargs: called.append(args))
    with patch.object(app, "transcribe_public_media_url_to_record", return_value=dict(FAKE_RECORD)):
        client = TestClient(app.app)
        started = client.post(
            "/api/transcribe-url-job",
            data={"url": "https://cdn.example/video.mp4", "include_screenshots": "1"},
        )
        job = _wait_job(client, started.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["record"]["transcript"] == "hello from captions"
    assert job["screenshots"]["status"] == "error"
    assert called == []
    assert looked_up == []


def test_x_and_tiktok_stay_blocked_on_this_production_base():
    called = []
    monkeypatch_target = patch.object(screenshots, "download_360p", side_effect=lambda *a, **k: called.append(a))
    with monkeypatch_target:
        client = TestClient(app.app)
        started = client.post(
            "/api/transcribe-url-job",
            data={"url": "https://x.com/someone/status/1", "include_screenshots": "1"},
        )
        job = _wait_job(client, started.json()["job"]["id"])
    assert job["status"] == "error"
    assert "X/Twitter" in job["error"]
    assert called == []
    assert "tiktok.com" in app.SOCIAL_URL_HOSTS
    assert "x.com" in app.SOCIAL_URL_HOSTS


def test_page_has_both_buttons_and_no_session_header():
    html = Path(app.STATIC_DIR, "index.html").read_text(encoding="utf-8")
    source = Path(app.ROOT, "app.py").read_text(encoding="utf-8") if hasattr(app, "ROOT") else Path("app.py").read_text(encoding="utf-8")
    assert ">Transcript only</button>" in html
    assert ">Transcript with screenshots</button>" in html
    assert "if (includeScreenshots) fd.append('include_screenshots', '1');" in html
    assert "X-Transcript-Session" not in html
    assert "require_api_access" not in source
    assert "TRANSCRIPT_AUTH_MODE" not in source


def test_busy_screenshot_slot_keeps_the_transcript(monkeypatch):
    monkeypatch.setenv("SCREENSHOT_SLOT_WAIT_SECONDS", "0")
    sem = threading.BoundedSemaphore(1)
    assert sem.acquire(blocking=False)
    monkeypatch.setattr(app, "SCREENSHOT_SLOTS", sem)
    with patch.object(app, "transcribe_youtube_url_to_record", return_value=dict(FAKE_RECORD)), \
         patch.object(app, "capture_from_url") as capture:
        client = TestClient(app.app)
        started = client.post(
            "/api/transcribe-url-job",
            data={"url": "https://youtu.be/abcdefghijk", "include_screenshots": "1"},
        )
        job = _wait_job(client, started.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["screenshots"]["status"] == "error"
    capture.assert_not_called()
    sem.release()
