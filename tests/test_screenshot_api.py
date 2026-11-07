"""Screenshot jobs stay attached to the existing transcript API."""
from __future__ import annotations

import io
import shutil
import subprocess
import threading
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
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
    assert path, "ffmpeg is required for the screenshot file test"
    return path


def _wait_job(client: TestClient, job_id: str, headers: dict | None = None) -> dict:
    job = {}
    for _ in range(80):
        res = client.get(f"/api/jobs/{job_id}", headers=headers or {})
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


def test_screenshot_failure_keeps_transcript_and_hides_the_internal_error():
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
    shots = job["screenshots"]
    assert shots["status"] == "error"
    assert shots["error"] == "Screenshots could not be captured."
    assert shots["zip_url"] is None
    blob = str(job)
    assert "ffmpeg exploded" not in blob
    assert "/tmp/secret-path" not in blob
    assert job["record"]["screenshots"]["status"] == "error"


def test_screenshot_success_serves_timestamped_jpeg_and_zip(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
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
    assert shots["status"] == "done"
    assert shots["frames"][0]["timestamp"] == "0:01"
    assert shots["frames"][0]["time"] == 1.0
    image = client.get(shots["frames"][0]["url"])
    archive = client.get(shots["zip_url"])
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/jpeg")
    assert image.content[:3] == b"\xff\xd8\xff"
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as zf:
        names = zf.namelist()
        assert shots["frames"][0]["filename"] in names
        assert "manifest.csv" in names
        assert "0:01" in zf.read("manifest.csv").decode()
    assert b"/tmp/" not in archive.content
    assert client.get(f"/api/jobs/{job['id']}/screenshots/../app.py").status_code == 404


def test_empty_capture_is_not_reported_as_success(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)

    def empty_capture(*args, **kwargs):
        return {"status": "done", "error": None, "count": 0, "frames": []}

    with patch.object(app, "transcribe_youtube_url_to_record", return_value=dict(FAKE_RECORD)), \
         patch.object(app, "capture_from_url", side_effect=empty_capture):
        client = TestClient(app.app)
        started = client.post(
            "/api/transcribe-url-job",
            data={"url": "https://youtu.be/abcdefghijk", "include_screenshots": "1"},
        )
        job = _wait_job(client, started.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["record"]["transcript"] == "hello from captions"
    assert job["screenshots"]["status"] == "error"


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
    payload = app._attach_screenshots("abc123abc123", "https://cdn.example/video.mp4")
    assert payload["status"] == "error"
    assert payload["error"] == "Screenshots could not be captured."
    assert "cdn.example" not in payload["error"]
    assert called == []
    assert looked_up == []


def test_smuggled_youtube_url_downloads_only_the_canonical_watch_link(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app, "resolve_binary", lambda *args, **kwargs: "/usr/bin/ffmpeg")
    monkeypatch.setattr(screenshots, "public_http_url", lambda url: url)
    seen = []

    def stop(url, *args, **kwargs):
        seen.append(url)
        raise RuntimeError("stop before any provider call")

    monkeypatch.setattr(screenshots, "download_360p", stop)
    payload = app._attach_screenshots(
        "abc123abc123",
        "https://youtu.be/abcdefghijk?q=http://127.0.0.1/latest/meta-data",
    )
    assert seen == ["https://www.youtube.com/watch?v=abcdefghijk"]
    assert payload["status"] == "error"
    assert "127.0.0.1" not in str(payload)


def test_private_screenshot_url_does_not_download(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app, "resolve_binary", lambda *args, **kwargs: "ffmpeg")
    called = []
    monkeypatch.setattr(screenshots, "download_360p", lambda *args, **kwargs: called.append(args))
    payload = app._attach_screenshots("abc123abc123", "http://127.0.0.1/latest/meta-data")
    assert payload["status"] == "error"
    assert payload["error"] == "Screenshots could not be captured."
    assert called == []
    assert "127.0.0.1" not in payload["error"]
    assert "meta-data" not in payload["error"]


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
    assert job["record"]["transcript"] == "hello from captions"
    assert job["screenshots"]["status"] == "error"
    capture.assert_not_called()
    sem.release()


def test_restart_during_screenshots_keeps_finished_transcript():
    shot_job = "abc123abc123"
    plain_job = "def456def456"
    with app.URL_JOBS_LOCK:
        app.URL_JOBS[shot_job] = {
            "id": shot_job,
            "status": "running",
            "include_screenshots": True,
            "record": {"id": "r1", "transcript": "kept text"},
        }
        app.URL_JOBS[plain_job] = {"id": plain_job, "status": "running", "include_screenshots": False}
        app.recover_interrupted_jobs_locked()
        kept = dict(app.URL_JOBS[shot_job])
        plain = dict(app.URL_JOBS[plain_job])
    assert kept["status"] == "done"
    assert kept["record"]["transcript"] == "kept text"
    assert kept["screenshots"]["status"] == "error"
    assert plain["status"] == "error"
    assert plain["error"] == app.RESTART_MESSAGE


def test_prune_removes_only_expired_screenshot_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    db_file = tmp_path / "transcripts.db"
    db_file.write_text("keep-me")
    old = tmp_path / "screenshots" / "abc123abc123"
    old.mkdir(parents=True)
    (old / "frame.jpg").write_bytes(b"x")
    old_time = time.time() - (30 * 3600)
    import os
    os.utime(old, (old_time, old_time))
    fresh = tmp_path / "screenshots" / "def456def456"
    fresh.mkdir()
    note = tmp_path / "screenshots" / "host-notes"
    note.mkdir()
    assert app.prune_screenshot_dirs() == 1
    assert not old.exists()
    assert fresh.exists()
    assert note.exists()
    assert db_file.read_text() == "keep-me"


def test_screenshot_columns_are_not_added_to_the_transcript_table():
    with app.db() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(transcripts)")}
    assert "screenshots" not in columns


@pytest.mark.auth_enforce
def test_screenshot_files_require_the_job_principal(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    with patch.object(app, "transcribe_youtube_url_to_record", return_value=dict(FAKE_RECORD)), \
         patch.object(app, "capture_from_url", side_effect=_write_capture):
        client = TestClient(app.app)
        owner = {"X-Transcript-Session": client.post("/api/session").json()["session"]}
        other = {"X-Transcript-Session": client.post("/api/session").json()["session"]}
        started = client.post(
            "/api/transcribe-url-job",
            data={"url": "https://youtu.be/abcdefghijk", "include_screenshots": "1"},
            headers=owner,
        )
        assert started.status_code == 202
        job = _wait_job(client, started.json()["job"]["id"], owner)
    frame = job["screenshots"]["frames"][0]["url"]
    archive = job["screenshots"]["zip_url"]
    assert client.get(frame).status_code == 401
    assert client.get(archive).status_code == 401
    assert client.get(frame, headers=other).status_code == 404
    assert client.get(archive, headers=other).status_code == 404
    assert client.get(f"/api/jobs/{job['id']}", headers=other).status_code == 404
    owned = client.get(frame, headers=owner)
    assert owned.status_code == 200
    assert owned.content[:3] == b"\xff\xd8\xff"


def test_page_offers_both_modes_and_does_not_treat_screenshot_errors_as_success():
    html = Path(app.STATIC_DIR, "index.html").read_text()
    assert '>Transcript only</button>' in html
    assert '>Transcript with screenshots</button>' in html
    assert "id=\"copyTranscriptBtn\"" in html
    assert "Copy image" in html
    assert "Download ZIP" in html
    assert "if (includeScreenshots) fd.append('include_screenshots', '1');" in html
    assert "Transcript ready." in html
    assert "sessionFetch(path)" in html
    assert "async function sessionFetch(path, opts = {})" in html
    assert "/api/transcribe-url-job" in html
    result = html[html.index('id="result"'):html.index('id="transcript"')]
    assert "shotsGallery" in result
    assert "VTT" not in result
