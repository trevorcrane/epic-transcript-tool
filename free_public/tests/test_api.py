"""Job API: transcript survives a screenshot failure, and frames are downloadable."""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import free_public.app as app
from free_public.captions import PUBLIC_BOT, CaptionError
from free_public.screenshots import capture_from_video

FAKE_RECORD = {
    "id": "rec-test",
    "source": "https://www.youtube.com/watch?v=tTruM2VB9C0",
    "transcript": "hello from captions",
    "method": "native-caption-yt-dlp",
    "duration_seconds": 10,
    "word_count": 3,
}


def _wait_job(client: TestClient, job_id: str, attempts: int = 80, pause: float = 0.05) -> dict:
    job = {}
    for _ in range(attempts):
        res = client.get(f"/api/jobs/{job_id}")
        assert res.status_code == 200
        job = res.json()["job"]
        if job.get("status") in {"done", "error"}:
            return job
        time.sleep(pause)
    raise AssertionError(f"job did not finish: {job}")


def test_health_is_caption_only_and_not_whisper():
    client = TestClient(app.app)
    body = client.get("/health").json()
    assert body["transcription"] == "captions-only"
    assert body["whisper"] is False
    assert body["paid_providers"] == []
    assert body["runtime"] == "free-public"
    assert body["ffmpeg"] is True


def test_page_has_two_buttons():
    client = TestClient(app.app)
    html = client.get("/").text
    assert "Transcript only" in html
    assert "Transcript with screenshots" in html
    assert 'id="grab"' in html
    assert 'id="grabShots"' in html
    assert "Copy transcript" in html
    assert "Download transcript" in html
    assert "Download all screenshots" in html
    assert "paid transcription" in html


def test_non_youtube_url_is_rejected():
    client = TestClient(app.app)
    res = client.post("/api/transcribe-url-job", data={"url": "https://example.com/video.mp4"})
    assert res.status_code == 422
    assert "YouTube" in res.json()["error"]


def test_screenshot_failure_still_returns_transcript():
    with patch.object(app, "transcribe_youtube_url_to_record", return_value=dict(FAKE_RECORD)), \
         patch.object(app, "capture_from_url", side_effect=RuntimeError("ffmpeg exploded /tmp/secret-path")):
        client = TestClient(app.app)
        started = client.post(
            "/api/transcribe-url-job",
            data={"url": "https://youtu.be/tTruM2VB9C0", "include_screenshots": "1"},
        )
        assert started.status_code == 202
        job = _wait_job(client, started.json()["job"]["id"])
        assert job["status"] == "done"
        assert job["record"]["transcript"] == "hello from captions"
        shots = job.get("screenshots") or job["record"].get("screenshots")
        assert shots["status"] == "error"
        assert shots["error"] == "Screenshots could not be captured."
        blob = str(job)
        assert "ffmpeg exploded" not in blob
        assert "/tmp/secret-path" not in blob
        download = client.get(f"/api/jobs/{job['id']}/transcript.txt")
        assert download.status_code == 200
        assert "hello from captions" in download.text


def test_transcript_only_skips_capture():
    with patch.object(app, "transcribe_youtube_url_to_record", return_value=dict(FAKE_RECORD)) as transcribed, \
         patch.object(app, "capture_from_url") as capture:
        client = TestClient(app.app)
        started = client.post("/api/transcribe-url-job", data={"url": "https://youtu.be/tTruM2VB9C0"})
        assert started.status_code == 202
        job = _wait_job(client, started.json()["job"]["id"])
        assert job["status"] == "done"
        assert job["record"]["transcript"] == "hello from captions"
        assert job.get("screenshots") in (None, {})
        capture.assert_not_called()
        transcribed.assert_called()


def test_bot_wall_is_a_public_error_without_workaround_steps():
    def blocked(url: str, work_dir=None):
        raise CaptionError(PUBLIC_BOT, "ERROR: [youtube] tTruM2VB9C0: Sign in to confirm you’re not a bot")

    with patch.object(app, "transcribe_youtube_url_to_record", side_effect=blocked):
        client = TestClient(app.app)
        started = client.post(
            "/api/transcribe-url-job",
            data={"url": "https://youtu.be/tTruM2VB9C0", "include_screenshots": "1"},
        )
        job = _wait_job(client, started.json()["job"]["id"])
        assert job["status"] == "error"
        assert "Sign in to confirm you're not a bot" in job["error"]
        assert "cookies" in job["error"]
        assert "tTruM2VB9C0:" not in job["error"]
        assert "/tmp/" not in job["error"]


def test_screenshot_routes_reject_bad_names():
    client = TestClient(app.app)
    missing = client.get("/api/jobs/abcdabcdabcd/screenshots/not-a-frame.jpg")
    assert missing.status_code == 404
    odd = client.get("/api/jobs/not-a-job/screenshots.zip")
    assert odd.status_code == 404


def test_real_frames_are_listed_and_zipped(tmp_path: Path):
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg
    video = tmp_path / "clip.mp4"
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "smptebars=size=640x360:rate=24:duration=4",
         "-pix_fmt", "yuv420p", "-y", str(video)],
        check=True, timeout=30,
    )

    def capture(url, out_dir, yt_dlp_bin, ffmpeg_bin, work_dir=None, progress=None):
        if progress:
            progress("Saving extra frames")
        return capture_from_video(Path(video), Path(out_dir), ffmpeg_bin)

    with patch.object(app, "transcribe_youtube_url_to_record", return_value=dict(FAKE_RECORD)), \
         patch.object(app, "capture_from_url", side_effect=capture):
        client = TestClient(app.app)
        started = client.post(
            "/api/transcribe-url-job",
            data={"url": "https://youtu.be/tTruM2VB9C0", "include_screenshots": "1"},
        )
        job = _wait_job(client, started.json()["job"]["id"], attempts=200, pause=0.25)
        assert job["status"] == "done"
        shots = job["screenshots"]
        assert shots["status"] == "done"
        assert shots["count"] >= 1
        assert shots["frames"][0]["timestamp"]
        frame = client.get(shots["frames"][0]["url"])
        assert frame.status_code == 200
        assert frame.content[:2] == b"\xff\xd8"
        archive = client.get(shots["zip_url"])
        assert archive.status_code == 200
        assert archive.content[:2] == b"PK"
