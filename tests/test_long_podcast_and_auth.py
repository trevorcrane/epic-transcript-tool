"""PR fix/long-media-jobs: long podcasts (chunked Whisper) and job API auth.

Test ids match PR-PLAN.md section 5 (T1..T12). All offline: providers are faked.
"""
import os
import re
import subprocess
import threading
import time

import pytest
from fastapi.testclient import TestClient

import app

TOKEN = "test-token-" + "x" * 32
GUARDED = [
    ("post", "/api/transcribe-url-job", {"data": {"url": "https://example.com/a.mp3"}}),
    ("get", "/api/jobs/nope123", {}),
    ("post", "/api/transcribe-url", {"data": {"url": "https://example.com/a.mp3"}}),
    ("post", "/api/transcribe-upload", {"files": {"file": ("a.txt", b"hello words", "text/plain")}}),
    ("post", "/api/analyze/nope", {"data": {"output_type": "executive_summary"}}),
    ("post", "/api/analyze-all/nope", {}),
]


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    monkeypatch.setenv("TRANSCRIPT_API_TOKENS", TOKEN)
    return tmp_path


def bearer():
    return {"Authorization": f"Bearer {TOKEN}"}


def wait_job(client, job_id, headers, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}", headers=headers).json()["job"]
        if job["status"] in {"done", "error"}:
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def fake_long_media(monkeypatch, tmp_path, duration, chunks=9, whisper=None):
    audio = tmp_path / "audio.mp3"; audio.write_bytes(b"audio")
    calls = {"whisper": [], "download_timeout": [], "split": 0}
    monkeypatch.setattr(app, "yt_dlp_metadata", lambda url: {"id": "pod1", "title": "Podcast", "webpage_url": url})
    monkeypatch.setattr(app, "fetch_caption_url_segments", lambda meta: (_ for _ in ()).throw(RuntimeError("No usable native caption track found")))

    def download(url, work_dir):
        calls["download_timeout"].append(app.DOWNLOAD_TIMEOUT_CTX.get())
        return audio
    monkeypatch.setattr(app, "yt_dlp_download_audio", download)
    monkeypatch.setattr(app, "media_duration_seconds", lambda path: duration)

    def split(audio_path, work_dir, chunk_seconds):
        calls["split"] += 1
        out = []
        for i in range(chunks):
            p = tmp_path / f"chunk-{i:04d}.wav"; p.write_bytes(b"c"); out.append(p)
        return out
    monkeypatch.setattr(app, "split_audio_for_long_transcription", split)

    def default_whisper(path, language=None, model=None, timeout=None):
        calls["whisper"].append(timeout)
        return [{"start": 1.0, "end": 5.0, "text": f"spoken words in chunk {len(calls['whisper'])}"}], "en"
    monkeypatch.setattr(app, "transcribe_with_local_whisper", whisper or default_whisper)
    return calls


# T1 / T1b: long media and unknown duration both take the chunked path
@pytest.mark.auth_enforce
@pytest.mark.parametrize("duration", [5400.0, None], ids=["T1-5400s", "T1b-unknown-duration"])
def test_long_or_unknown_media_job_is_chunked(db, monkeypatch, duration):
    calls = fake_long_media(monkeypatch, db, duration)
    client = TestClient(app.app)
    res = client.post("/api/transcribe-url-job", data={"url": "https://cdn.example.com/pod.mp3", "owner": "o" * 40}, headers=bearer())
    assert res.status_code == 202
    job = wait_job(client, res.json()["job"]["id"], bearer())
    assert job["status"] == "done", job
    rec = job["record"]
    assert rec["method"] == "chunked-local-whisper"
    assert len(calls["whisper"]) == 9
    assert all(t is not None and t >= 1800 for t in calls["whisper"])
    starts = [s["start"] for s in rec["segments"]]
    assert starts == [1.0 + 600 * i for i in range(9)]
    assert rec["duration_seconds"] == duration
    assert job["chunks_done"] == job["chunks_total"] == 9


# T2: job download timeout is 1800 s, set per thread, os.environ untouched
@pytest.mark.auth_enforce
def test_job_download_timeout_is_per_thread_not_env(db, monkeypatch):
    calls = fake_long_media(monkeypatch, db, 5400.0)
    before = dict(os.environ)
    client = TestClient(app.app)
    res = client.post("/api/transcribe-url-job", data={"url": "https://cdn.example.com/pod.mp3"}, headers=bearer())
    wait_job(client, res.json()["job"]["id"], bearer())
    assert calls["download_timeout"] == [1800]
    assert dict(os.environ) == before
    assert app.DOWNLOAD_TIMEOUT_CTX.get() is None


# T3: a Whisper timeout gives a safe public error (no command line)
@pytest.mark.auth_enforce
def test_whisper_timeout_is_visitor_safe(db, monkeypatch):
    state = {"n": 0}

    def whisper(path, language=None, model=None, timeout=None):
        state["n"] += 1
        if state["n"] == 3:
            raise subprocess.TimeoutExpired(cmd=["/usr/local/bin/whisper", str(path), "--threads", "4"], timeout=timeout)
        return [{"start": 0, "end": 1, "text": "words words words"}], "en"
    fake_long_media(monkeypatch, db, 5400.0, whisper=whisper)
    client = TestClient(app.app)
    res = client.post("/api/transcribe-url-job", data={"url": "https://cdn.example.com/pod.mp3"}, headers=bearer())
    job = wait_job(client, res.json()["job"]["id"], bearer())
    assert job["status"] == "error"
    assert job["error"] == app.TIMEOUT_PUBLIC_MESSAGE
    for leak in ("/usr/local/bin/whisper", "--threads", "Command '["):
        assert leak not in str(job)


# T4: auth matrix on the 6 guarded routes; open routes stay open
@pytest.mark.auth_enforce
def test_auth_matrix_enforce(db, monkeypatch):
    monkeypatch.setattr(app, "run_url_job", lambda *a, **k: None)
    client = TestClient(app.app)
    session = client.post("/api/session").json()["session"]
    for method, path, kw in GUARDED:
        assert getattr(client, method)(path, **kw).status_code == 401, path
        assert getattr(client, method)(path, headers={"Authorization": "Bearer wrong-token-" + "y" * 30}, **kw).status_code == 401, path
        assert getattr(client, method)(path, headers=bearer(), **kw).status_code != 401, path
        assert getattr(client, method)(path, headers={"X-Transcript-Api-Token": TOKEN}, **kw).status_code != 401, path
        assert getattr(client, method)(path, headers={"X-Transcript-Session": session}, **kw).status_code != 401, path
    for path in ("/", "/health", "/api/setup", "/api/analysis-outputs"):
        assert client.get(path).status_code == 200, path


def test_auth_log_mode_lets_requests_through_and_counts(db, monkeypatch):
    monkeypatch.setenv("TRANSCRIPT_AUTH_MODE", "log")
    monkeypatch.setattr(app, "run_url_job", lambda *a, **k: None)
    client = TestClient(app.app)
    before = client.get("/health").json()["auth"]["auth_missing"]
    assert client.post("/api/transcribe-url-job", data={"url": "https://example.com/a.mp3"}).status_code == 202
    health = client.get("/health").json()["auth"]
    assert health["mode"] == "log"
    assert health["auth_missing"] == before + 1


# T5: jobs are bound to who created them
@pytest.mark.auth_enforce
def test_job_binding_between_sessions(db, monkeypatch):
    monkeypatch.setattr(app, "transcribe_public_media_url_to_record", lambda url, owner_token, started=None: {"id": "r1", "transcript": "hi", "owner_token": owner_token, "segments": []})
    client = TestClient(app.app)
    a = {"X-Transcript-Session": client.post("/api/session").json()["session"]}
    b = {"X-Transcript-Session": client.post("/api/session").json()["session"]}
    job_id = client.post("/api/transcribe-url-job", data={"url": "https://example.com/a.mp3", "owner": "q" * 40}, headers=a).json()["job"]["id"]
    job = wait_job(client, job_id, a)
    assert job["record"]["owner_token"] == "q" * 40
    assert client.get(f"/api/jobs/{job_id}", headers=b).status_code == 404
    assert "principal" not in job and "ip_key" not in job and "deadline_at" not in job


# T6 / T6b: tampered session rejected; re-mint keeps sid only if expired under 24 h
@pytest.mark.auth_enforce
def test_session_tamper_expiry_and_remint_window(db):
    client = TestClient(app.app)
    good = client.post("/api/session").json()["session"]
    sid, exp, sig = good.split(".")
    tampered = f"{sid}.{int(exp) + 999}.{sig}"
    assert client.get("/api/jobs/x", headers={"X-Transcript-Session": tampered}).status_code == 401
    # expired 1 h ago (under 24 h): job routes refuse it, /api/session re-mints the same sid
    recent = app.mint_session("a" * 24, now=time.time() - app.SESSION_TTL_SECONDS - 3600)
    assert client.get("/api/jobs/x", headers={"X-Transcript-Session": recent}).status_code == 401
    renewed = client.post("/api/session", headers={"X-Transcript-Session": recent}).json()["session"]
    assert renewed.split(".")[0] == "a" * 24
    assert client.get("/api/jobs/x", headers={"X-Transcript-Session": renewed}).status_code == 404
    # T6b: expired 25 h ago: a new sid is issued
    stale = app.mint_session("b" * 24, now=time.time() - app.SESSION_TTL_SECONDS - 25 * 3600)
    fresh = client.post("/api/session", headers={"X-Transcript-Session": stale}).json()["session"]
    assert fresh.split(".")[0] != "b" * 24
    # tampered tokens never keep their sid either
    other = client.post("/api/session", headers={"X-Transcript-Session": tampered}).json()["session"]
    assert other.split(".")[0] != sid


# T7: restart marks interrupted jobs as error so pollers stop
def test_restart_recovery_marks_running_jobs():
    with app.URL_JOBS_LOCK:
        app.URL_JOBS["run1"] = {"id": "run1", "status": "running"}
        app.URL_JOBS["q1"] = {"id": "q1", "status": "queued"}
        app.URL_JOBS["d1"] = {"id": "d1", "status": "done"}
        n = app.recover_interrupted_jobs_locked()
    assert n == 2
    assert app.URL_JOBS["run1"]["status"] == "error" and "restarted" in app.URL_JOBS["run1"]["error"]
    assert app.URL_JOBS["d1"]["status"] == "done"
    # and the server startup hook runs it (TestClient as a context manager fires startup)
    with app.URL_JOBS_LOCK:
        app.URL_JOBS["run2"] = {"id": "run2", "status": "running"}
    with TestClient(app.app):
        pass
    assert app.URL_JOBS["run2"]["status"] == "error"


# T8: one long job at a time; the second waits as queued
def test_long_job_slot_queues_second_job(db, monkeypatch):
    monkeypatch.setattr(app, "split_audio_for_long_transcription", lambda a, w, c: [db / "c0.wav"])
    monkeypatch.setattr(app, "transcribe_with_local_whisper", lambda *a, **k: ([{"start": 0, "end": 1, "text": "ok words here"}], "en"))
    with app.URL_JOBS_LOCK:
        app.URL_JOBS["j2"] = {"id": "j2", "status": "running", "deadline_at": time.time() + 60}
    assert app.LONG_JOB_SLOTS.acquire(timeout=1)
    out = {}
    t = threading.Thread(target=lambda: out.update(r=app.transcribe_audio_chunked(db / "a.mp3", db, job_id="j2")))
    t.start()
    try:
        deadline = time.time() + 5
        while time.time() < deadline and app.URL_JOBS["j2"].get("status") != "queued":
            time.sleep(0.05)
        assert app.URL_JOBS["j2"]["status"] == "queued"
        assert "Waiting for another long transcript" in app.URL_JOBS["j2"]["message"]
    finally:
        app.LONG_JOB_SLOTS.release()
    t.join(10)
    assert out["r"][0] and app.URL_JOBS["j2"]["status"] == "running"


# T8b: max 2 active page jobs per IP, token jobs exempt, global page queue cap
@pytest.mark.auth_enforce
def test_page_tier_limits(db, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(app, "transcribe_public_media_url_to_record", lambda url, owner_token, started=None: (release.wait(10), {"id": "r", "transcript": "x", "segments": []})[1])
    client = TestClient(app.app)
    s1 = {"X-Transcript-Session": client.post("/api/session").json()["session"]}
    s2 = {"X-Transcript-Session": client.post("/api/session").json()["session"]}
    try:
        post = lambda h, ip="1.1.1.1": client.post("/api/transcribe-url-job", data={"url": "https://example.com/a.mp3"}, headers={**h, "CF-Connecting-IP": ip})
        assert post(s1).status_code == 202
        assert post(s2).status_code == 202          # second session, same IP: 2 active
        third = post(s1)
        assert third.status_code == 429 and third.json()["detail"] == app.PAGE_TIER_MESSAGE_PER_IP
        assert post(bearer()).status_code == 202     # token callers are exempt
        monkeypatch.setenv("MAX_QUEUED_PAGE_JOBS", "3")
        assert post(s1, ip="2.2.2.2").status_code == 202
        busy = post(s1, ip="3.3.3.3")
        assert busy.status_code == 429 and busy.json()["detail"] == app.PAGE_TIER_MESSAGE_QUEUE
    finally:
        release.set()
        deadline = time.time() + 10   # let the job threads finish before the fixture clears URL_JOBS
        while time.time() < deadline:
            with app.URL_JOBS_LOCK:
                if not any(j.get("status") in app.ACTIVE_JOB_STATES for j in app.URL_JOBS.values()):
                    break
            time.sleep(0.05)


# T9: page contract: every guarded call goes through jfetch, which always sends the session
def test_page_sends_session_on_every_api_call():
    html = (app.STATIC_DIR / "index.html").read_text()
    assert "attempt < 150" not in html
    assert "maxWaitMs = 4 * 60 * 60 * 1000" in html
    assert "fetch(apiUrl('/api/session')" in html
    raw = re.findall(r"(?<![A-Za-z])fetch\(", html)
    assert len(raw) == 3  # only mintSession + the 2 calls inside sessionFetch use fetch() directly
    assert "const r = await sessionFetch(path, opts);" in html
    assert "'X-Transcript-Session': pageSession" in html
    for route in ("/api/transcribe-url-job", "/api/jobs/", "/api/transcribe-upload", "/api/analyze/"):
        assert f"jfetch('{route}" in html, route
    assert "Bearer" not in html and "TRANSCRIPT_API_TOKEN" not in html
    assert "localStorage.setItem('pageSession" not in html


# T10: the token never appears in responses or logs
@pytest.mark.auth_enforce
def test_token_never_leaks(db, monkeypatch, caplog):
    monkeypatch.setattr(app, "run_url_job", lambda *a, **k: None)
    client = TestClient(app.app)
    bodies = [client.get("/health").text,
              client.post("/api/transcribe-url-job", data={"url": "https://example.com/a.mp3"}, headers=bearer()).text,
              client.post("/api/transcribe-url-job", data={"url": "https://example.com/a.mp3"}, headers={"Authorization": "Bearer " + TOKEN + "z"}).text]
    for text in bodies + [caplog.text]:
        assert TOKEN not in text


# T11: sync route refuses long or unknown-length media before any Whisper call
@pytest.mark.auth_enforce
@pytest.mark.parametrize("probe,meta_duration", [(5400.0, None), (None, None), (None, 5400)], ids=["T11-5400s", "T11-unknown", "T11-meta-long"])
def test_sync_route_refuses_long_media_without_whisper(db, monkeypatch, probe, meta_duration):
    calls = fake_long_media(monkeypatch, db, probe)
    if meta_duration:
        monkeypatch.setattr(app, "yt_dlp_metadata", lambda url: {"id": "pod1", "title": "Podcast", "webpage_url": url, "duration": meta_duration})
    client = TestClient(app.app)
    res = client.post("/api/transcribe-url", data={"url": "https://cdn.example.com/pod.mp3"}, headers=bearer())
    assert res.status_code == 422
    assert res.json()["detail"] == app.SYNC_LONG_MEDIA_MESSAGE
    assert calls["whisper"] == [] and calls["split"] == 0
    if meta_duration:
        assert calls["download_timeout"] == []   # refused before downloading


# T12: YouTube job with unknown duration (metadata failed, no captions) also chunks
def test_youtube_job_unknown_duration_chunks(db, monkeypatch):
    monkeypatch.setattr(app, "yt_dlp_metadata", lambda url: (_ for _ in ()).throw(RuntimeError("meta down")))
    monkeypatch.setattr(app, "get_cached_transcript", lambda *a, **k: None)
    monkeypatch.setattr(app, "youtube_transcript_api_segments", lambda vid: (_ for _ in ()).throw(RuntimeError("blocked")))
    monkeypatch.setattr(app, "yt_dlp_grab_caption_segments", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("none")))
    calls = fake_long_media(monkeypatch, db, None, chunks=3)
    rec = app.transcribe_youtube_url_to_record("https://youtu.be/dQw4w9WgXcQ", "o" * 40, allow_long=True, job_id=None)
    assert rec["method"] == "chunked-local-whisper"
    assert len(calls["whisper"]) == 3 and all(t >= 1800 for t in calls["whisper"])
