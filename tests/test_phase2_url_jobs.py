import time

from fastapi import HTTPException
from fastapi.testclient import TestClient

import app


def test_async_url_job_accepts_public_non_youtube_media(monkeypatch):
    app.URL_JOBS.clear()

    def fake_media_record(url, owner_token, started=None):
        return {
            "id": "media123",
            "title": "Public MP3",
            "source": "Public MP3",
            "source_kind": "url",
            "method": "local-whisper",
            "language": "en",
            "word_count": 8,
            "segments": [{"start": 0, "end": 2, "text": "public media url transcript works"}],
            "transcript": "[00:00] public media url transcript works",
            "cache_hit": False,
        }

    monkeypatch.setattr(app, "transcribe_public_media_url_to_record", fake_media_record)
    client = TestClient(app.app)
    res = client.post("/api/transcribe-url-job", data={"url": "https://example.com/file.mp3", "owner": "owner-token-phase2-urljob-abcdefghijklmnop"})
    assert res.status_code == 202
    job_id = res.json()["job"]["id"]
    # The job runs on a background thread; poll briefly instead of racing it
    # (this test was flaky on main c943233 under load).
    deadline = time.time() + 5
    job = client.get(f"/api/jobs/{job_id}").json()["job"]
    while job["status"] not in ("done", "error") and time.time() < deadline:
        time.sleep(0.02)
        job = client.get(f"/api/jobs/{job_id}").json()["job"]
    assert job["status"] == "done"
    assert job["record"]["source_kind"] == "url"
    assert job["record"]["method"] == "local-whisper"


def test_social_url_guidance_is_fast_and_helpful():
    # TikTok and X now go through yt-dlp (Trevor, 2026-10-18); Instagram/Facebook keep the guidance.
    assert app.social_url_guidance("https://www.tiktok.com/@creator/video/1234567890") is None
    message = app.social_url_guidance("https://www.facebook.com/watch/?v=1234567890")
    assert "Facebook links often block automatic public downloads" in message
    assert "upload it here" in message
    assert "Direct MP3" in message

    client = TestClient(app.app)
    res = client.post("/api/transcribe-url", data={"url": "https://www.instagram.com/reel/example/", "owner": "owner-token-phase2-social-abcdefghijklmnop"})
    assert res.status_code == 422
    assert "Instagram links often block automatic public downloads" in res.json()["detail"]
