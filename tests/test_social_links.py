"""X and TikTok links go through the normal yt-dlp path (Trevor, 2026-10-18 2:17 AM ET).

Offline: yt-dlp, captions, download and Whisper are faked.
"""
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

import app

TOKEN = "test-token-" + "s" * 32
X_URL = "https://x.com/NASA/status/2107095768821576019"
TIKTOK_URL = "https://www.tiktok.com/@scout2015/video/6718335390845095173"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    monkeypatch.setenv("TRANSCRIPT_API_TOKENS", TOKEN)
    return tmp_path


def wait_job(client, job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}", headers=BEARER).json()["job"]
        if job["status"] in {"done", "error"}:
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def fake_pipeline(monkeypatch, tmp_path, *, meta_error=None, duration=13.3):
    seen = {"meta": [], "download": [], "whisper": 0}
    audio = tmp_path / "a.m4a"; audio.write_bytes(b"a")

    def meta(url):
        seen["meta"].append(url)
        if meta_error:
            raise RuntimeError(meta_error)
        return {"id": "p1", "title": "Post", "webpage_url": url, "duration": duration, "uploader": "someone"}
    monkeypatch.setattr(app, "yt_dlp_metadata", meta)
    monkeypatch.setattr(app, "fetch_caption_url_segments", lambda m: (_ for _ in ()).throw(RuntimeError("No usable native caption track found")))

    def download(url, work_dir):
        seen["download"].append(url); return audio
    monkeypatch.setattr(app, "yt_dlp_download_audio", download)
    monkeypatch.setattr(app, "media_duration_seconds", lambda p: duration)

    def whisper(path, language=None, model=None, timeout=None):
        seen["whisper"] += 1
        return [{"start": 0.0, "end": 5.0, "text": "it is world space week and this year's theme is"}], "en"
    monkeypatch.setattr(app, "transcribe_with_local_whisper", whisper)
    return seen


@pytest.mark.parametrize("url", [X_URL, "https://twitter.com/NASA/status/2107095768821576019", TIKTOK_URL, "https://vm.tiktok.com/ZMabc123/"])
def test_x_and_tiktok_are_not_refused_up_front(url):
    assert app.social_url_guidance(url) is None


@pytest.mark.parametrize("url", ["https://www.instagram.com/reel/abc/", "https://www.facebook.com/watch/?v=1"])
def test_instagram_and_facebook_still_get_guidance(url):
    assert "upload it here" in app.social_url_guidance(url)


@pytest.mark.auth_enforce
@pytest.mark.parametrize("url", [X_URL, TIKTOK_URL], ids=["x", "tiktok"])
def test_x_and_tiktok_jobs_are_queued_and_transcribed(db, monkeypatch, url):
    seen = fake_pipeline(monkeypatch, db)
    client = TestClient(app.app)
    res = client.post("/api/transcribe-url-job", data={"url": url}, headers=BEARER)
    assert res.status_code == 202
    assert res.json()["job"]["status"] in {"queued", "running"}
    job = wait_job(client, res.json()["job"]["id"])
    assert job["status"] == "done", job
    assert job["record"]["method"] == "local-whisper"
    assert "world space week" in job["record"]["transcript"]
    assert seen["meta"] == [url] and seen["download"] == [url] and seen["whisper"] == 1


@pytest.mark.auth_enforce
@pytest.mark.parametrize("url,err,reason", [
    (TIKTOK_URL, "ERROR: [TikTok] 6718335390845095173: Your IP address is blocked from accessing this post", "blocked our server"),
    (X_URL, "ERROR: [twitter] 2107095768821576019: NSFW tweet requires authentication. Use --cookies", "needs a login"),
    (X_URL, "ERROR: [twitter] 1: No video could be found in this tweet", "no video or audio"),
    (TIKTOK_URL, "ERROR: [TikTok] 1: This post may not be comfortable for some audiences. Log in for access", "needs a login"),
    (X_URL, "ERROR: [twitter] 1: something new and unexpected", None),
], ids=["tiktok-ip-blocked", "x-login", "x-no-video", "tiktok-login", "x-unknown"])
def test_ytdlp_failure_gives_friendly_upload_error(db, monkeypatch, url, err, reason):
    fake_pipeline(monkeypatch, db, meta_error=err)
    client = TestClient(app.app)
    res = client.post("/api/transcribe-url-job", data={"url": url}, headers=BEARER)
    assert res.status_code == 202
    job = wait_job(client, res.json()["job"]["id"])
    assert job["status"] == "error"
    msg = job["error"]
    label = "TikTok" if "tiktok" in url else "X/Twitter"
    assert label in msg and "upload it here" in msg
    if reason:
        assert reason in msg
    assert "ERROR:" not in msg and "--cookies" not in msg and "[twitter]" not in msg   # raw yt-dlp text stays private


def test_failure_message_for_other_hosts_keeps_upload_route():
    msg = app.ytdlp_failure_message("https://vimeo.com/76979871", "ERROR: [vimeo] 76979871: The web client only works when logged-in. Use --cookies")
    assert msg.startswith("That site") and "needs a login" in msg and "upload it here" in msg
    assert app.ytdlp_failure_message("https://example.com/a.mp3", "weird") == app.GENERIC_LINK_FAILURE_MESSAGE


def test_yt_dlp_metadata_null_output_is_a_clean_error(monkeypatch):
    monkeypatch.setattr(app.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="null", stderr="ERROR: [TikTok] 1: Your IP address is blocked from accessing this post\n"))
    with pytest.raises(RuntimeError, match="IP address is blocked"):
        app.yt_dlp_metadata(TIKTOK_URL)
