import json
import subprocess
import time
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient
from urllib.parse import urlparse
import pytest

import app


def test_normalize_youtube_video_id_supports_required_url_shapes():
    cases = {
        "https://www.youtube.com/watch?v=v34Eg12mhDM&si=abc": "v34Eg12mhDM",
        "https://youtu.be/v34Eg12mhDM?si=abc": "v34Eg12mhDM",
        "https://www.youtube.com/shorts/v34Eg12mhDM?feature=share": "v34Eg12mhDM",
        "https://www.youtube.com/embed/v34Eg12mhDM": "v34Eg12mhDM",
        "https://www.youtube.com/live/v34Eg12mhDM?si=abc": "v34Eg12mhDM",
        "dQw4w9WgXcQ": "dQw4w9WgXcQ",
    }
    for url, video_id in cases.items():
        assert app.normalize_youtube_video_id(url) == video_id


def test_invalid_youtube_id_returns_none():
    assert app.normalize_youtube_video_id("https://example.com/not-youtube") is None
    assert app.normalize_youtube_video_id("https://youtu.be/too-short") is None


def test_parse_vtt_segments_preserves_timestamps_and_text():
    raw = """WEBVTT\n\n00:00:01.000 --> 00:00:03.500\nHello <c>world</c>\n\n00:00:04.000 --> 00:00:07.000\nSecond line &amp; more\n"""
    segments = app.parse_vtt_segments(raw)
    assert segments == [
        {"start": 1.0, "end": 3.5, "text": "Hello world"},
        {"start": 4.0, "end": 7.0, "text": "Second line & more"},
    ]
    assert app.timestamps_increase(segments)


def test_cache_hit_returns_existing_youtube_record(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    rec = app.save_transcript(
        source="Test Video",
        source_kind="youtube",
        method="youtube-transcript-api",
        transcript="[00:00] hello world",
        duration_seconds=10,
        processing_seconds=0.1,
        media_id="dQw4w9WgXcQ",
        source_url="https://youtu.be/dQw4w9WgXcQ",
        title="Test Video",
        creator="Tester",
        language="en",
        segments=[{"start": 0, "end": 2, "text": "hello world"}],
        provider_attempts=[{"provider": "seed", "ok": True}],
        cache_hit=False,
    )
    cached = app.get_cached_transcript("dQw4w9WgXcQ")
    assert cached["id"] == rec["id"]
    assert cached["cache_hit"] is True
    assert cached["word_count"] == 2
    assert cached["segments"][0]["text"] == "hello world"


def test_youtube_route_uses_cache_before_providers(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    app.save_transcript(
        source="Cached",
        source_kind="youtube",
        method="seed",
        transcript="[00:00] cached transcript",
        duration_seconds=1,
        processing_seconds=0,
        media_id="dQw4w9WgXcQ",
        source_url="https://youtu.be/dQw4w9WgXcQ",
        title="Cached",
        creator="Tester",
        language="en",
        segments=[{"start": 0, "end": 1, "text": "cached transcript"}],
        provider_attempts=[],
        cache_hit=False,
    )

    def should_not_run(*args, **kwargs):
        raise AssertionError("provider should not run on cache hit")

    monkeypatch.setattr(app, "transcribe_youtube_uncached", should_not_run)
    client = TestClient(app.app)
    res = client.post("/api/transcribe-url", data={"url": "https://youtu.be/dQw4w9WgXcQ?si=tracking"})
    assert res.status_code == 200
    data = res.json()["record"]
    assert data["cache_hit"] is True
    assert data["media_id"] == "dQw4w9WgXcQ"
    assert data["segments"][0]["text"] == "cached transcript"


def test_download_formats_are_available_for_saved_record(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    rec = app.save_transcript(
        source="Format Test",
        source_kind="youtube",
        method="seed",
        transcript="[00:00] hello\n[00:02] world",
        duration_seconds=2,
        processing_seconds=0,
        media_id="fmt12345678",
        source_url="https://youtu.be/fmt12345678",
        title="Format Test",
        creator="Tester",
        language="en",
        segments=[{"start": 0, "end": 1, "text": "hello"}, {"start": 2, "end": 3, "text": "world"}],
        provider_attempts=[],
        cache_hit=False,
        owner_token="owner-token-123456789012345678901234",
    )
    client = TestClient(app.app)
    for fmt, marker in [("txt", "[00:00] hello"), ("md", "# Format Test"), ("srt", "1\n00:00:00,000"), ("vtt", "WEBVTT\n\n00:00:00.000 --> 00:00:01.000")]:
        link = client.post(f"/api/transcripts/{rec['id']}/download-link?format={fmt}", headers={"X-Transcript-Owner": "owner-token-123456789012345678901234"})
        assert link.status_code == 200
        path = urlparse(link.json()["url"]).path
        res = client.get(path)
        assert res.status_code == 200
        assert marker in res.text



def test_recent_does_not_expose_global_transcripts_without_owner(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    app.save_transcript(
        source="Private Video",
        source_kind="youtube",
        method="seed",
        transcript="[00:00] secret transcript body",
        duration_seconds=2,
        processing_seconds=0,
        media_id="priv1234567",
        source_url="https://youtu.be/priv1234567",
        title="Private Video",
        creator="Tester",
        language="en",
        segments=[{"start": 0, "end": 1, "text": "secret transcript body"}],
        provider_attempts=[],
        cache_hit=False,
        owner_token="owner-token-aaaaaaaaaaaaaaaaaaaaaaaa",
    )
    client = TestClient(app.app)

    res = client.get("/api/recent?limit=5")

    assert res.status_code == 200
    assert res.json() == {"items": []}
    assert "secret transcript body" not in res.text


def test_transcript_reads_downloads_and_deletes_require_owner_capability(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    rec = app.save_transcript(
        source="Private Video",
        source_kind="youtube",
        method="seed",
        transcript="[00:00] secret transcript body",
        duration_seconds=2,
        processing_seconds=0,
        media_id="priv1234567",
        source_url="https://youtu.be/priv1234567",
        title="Private Video",
        creator="Tester",
        language="en",
        segments=[{"start": 0, "end": 1, "text": "secret transcript body"}],
        provider_attempts=[],
        cache_hit=False,
        owner_token="owner-token-bbbbbbbbbbbbbbbbbbbbbbbb",
    )
    client = TestClient(app.app)

    assert client.get(f"/api/transcripts/{rec['id']}").status_code == 403
    assert client.post(f"/api/transcripts/{rec['id']}/download-link?format=txt").status_code == 403
    assert client.delete(f"/api/transcripts/{rec['id']}").status_code == 403

    ok = client.get(f"/api/transcripts/{rec['id']}", headers={"X-Transcript-Owner": "owner-token-bbbbbbbbbbbbbbbbbbbbbbbb"})
    assert ok.status_code == 200
    assert ok.json()["transcript"] == "[00:00] secret transcript body"
    link = client.post(f"/api/transcripts/{rec['id']}/download-link?format=txt", headers={"X-Transcript-Owner": "owner-token-bbbbbbbbbbbbbbbbbbbbbbbb"})
    assert link.status_code == 200
    assert "owner-token" not in link.json()["url"]
    assert client.get(urlparse(link.json()["url"]).path).status_code == 200
    assert client.delete(f"/api/transcripts/{rec['id']}", headers={"X-Transcript-Owner": "owner-token-bbbbbbbbbbbbbbbbbbbbbbbb"}).status_code == 200


def test_caption_candidates_prefer_source_language_and_normalize_metadata():
    meta = {
        "language": "ko",
        "subtitles": {},
        "automatic_captions": {
            "en-US-njLgzgtehjs": [{"url":"https://example.invalid/en.vtt", "ext":"vtt"}],
            "ko-orig": [{"url":"https://example.invalid/ko.vtt", "ext":"vtt"}],
        },
    }
    tracks = app._caption_candidates(meta)
    assert tracks[0]["lang"] == "ko"
    assert app.normalize_caption_language("en-US-njLgzgtehjs") == "en-US"


def test_owned_recent_includes_record_id_but_not_transcript(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    rec = app.save_transcript(
        source="Private Video", source_kind="youtube", method="seed",
        transcript="[00:00] secret transcript body", duration_seconds=2, processing_seconds=0,
        media_id="priv1234567", source_url="https://youtu.be/priv1234567", title="Private Video",
        creator="Tester", language="en", segments=[{"start": 0, "end": 1, "text": "secret transcript body"}],
        provider_attempts=[], owner_token="owner-token-cccccccccccccccccccccccc",
    )
    client = TestClient(app.app)
    res = client.get("/api/recent?limit=5", headers={"X-Transcript-Owner": "owner-token-cccccccccccccccccccccccc"})
    assert res.status_code == 200
    item = res.json()["items"][0]
    assert item["id"] == rec["id"]
    assert "transcript" not in item
    assert "owner_token" not in item


def test_stale_language_cache_is_bypassed_for_original_language(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    app.save_transcript(
        source="Spanish Video", source_kind="youtube", method="seed",
        transcript="[00:00] english translation", duration_seconds=2, processing_seconds=0,
        media_id="spanish1234", source_url="https://youtu.be/spanish1234", title="Spanish Video",
        creator="Tester", language="en-US", segments=[{"start": 0, "end": 1, "text": "english translation"}],
        provider_attempts=[], owner_token="owner-token-dddddddddddddddddddddddd",
    )
    monkeypatch.setattr(app, "yt_dlp_metadata", lambda url: {"title": "Spanish Video", "webpage_url": url, "subtitles": {"en-US-njLgzgtehjs": [{"url":"https://example.invalid/en.vtt", "ext":"vtt"}], "es": [{"url":"https://example.invalid/es.vtt", "ext":"vtt"}]}})
    def fresh(url, video_id, started, work_dir, owner_token=None, meta=None):
        return app.save_transcript(
            source="Spanish Video", source_kind="youtube", method="native-caption-automatic_captions",
            transcript="[00:00] hola mundo", duration_seconds=2, processing_seconds=0,
            media_id=video_id, source_url=url, title="Spanish Video", creator="Tester", language="es",
            segments=[{"start": 0, "end": 1, "text": "hola mundo"}], provider_attempts=[],
            owner_token=owner_token,
        )
    monkeypatch.setattr(app, "transcribe_youtube_uncached", fresh)
    client = TestClient(app.app)
    res = client.post("/api/transcribe-url", data={"url": "https://youtu.be/spanish1234", "owner": "owner-token-dddddddddddddddddddddddd"})
    assert res.status_code == 200
    record = res.json()["record"]
    assert record["cache_hit"] is False
    assert record["language"] == "es"
    assert "hola mundo" in record["transcript"]


def test_caption_candidates_prefer_clean_non_english_manual_when_source_unknown():
    meta = {
        "subtitles": {
            "en-US-njLgzgtehjs": [{"url":"https://example.invalid/en.vtt", "ext":"vtt"}],
            "es": [{"url":"https://example.invalid/es.vtt", "ext":"vtt"}],
        },
        "automatic_captions": {},
    }
    tracks = app._caption_candidates(meta)
    assert tracks[0]["lang"] == "es"
    assert app.infer_expected_language(meta) == "es"


def test_resolve_binary_uses_known_absolute_paths_when_launchd_path_is_minimal(monkeypatch, tmp_path):
    fallback = tmp_path / "whisper"
    fallback.write_text("#!/bin/sh\n")
    monkeypatch.setattr(app.shutil, "which", lambda name: None)
    monkeypatch.setattr(app, "WHISPER_BINARY_CANDIDATES", [fallback])

    assert app.resolve_whisper_binary() == str(fallback)


def test_setup_status_uses_absolute_tool_fallbacks_when_launchd_path_is_minimal(monkeypatch, tmp_path):
    yt_dlp = tmp_path / "yt-dlp"
    ffmpeg = tmp_path / "ffmpeg"
    whisper = tmp_path / "whisper"
    for binary in (yt_dlp, ffmpeg, whisper):
        binary.write_text("#!/bin/sh\n")
    monkeypatch.setattr(app.shutil, "which", lambda name: None)
    monkeypatch.setattr(app, "YT_DLP_BINARY_CANDIDATES", [yt_dlp])
    monkeypatch.setattr(app, "FFMPEG_BINARY_CANDIDATES", [ffmpeg])
    monkeypatch.setattr(app, "WHISPER_BINARY_CANDIDATES", [whisper])

    status = app.setup_status()

    assert status["ready"] is True
    assert status["missing"] == []
    assert status["local_whisper"] is True


def test_long_youtube_video_returns_bounded_helpful_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    calls = {"transcribe": 0}
    monkeypatch.setattr(app, "yt_dlp_metadata", lambda url: {"id":"longvid1234", "title":"Two Hour Fixture", "duration": 7200, "webpage_url": url})
    monkeypatch.setattr(app, "transcribe_youtube_uncached", lambda *a, **k: calls.__setitem__("transcribe", calls["transcribe"] + 1))
    client = TestClient(app.app)
    res = client.post("/api/transcribe-url", data={"url":"https://youtu.be/longvid1234", "owner":"owner-token-longvideo-abcdefghijklmnop"})
    assert res.status_code == 422
    assert "too long" in res.json()["detail"].lower() or "upload" in res.json()["detail"].lower()
    assert calls["transcribe"] == 0


def test_upload_reuses_file_hash_cache_for_identical_media(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    calls = {"whisper": 0}
    def fake_whisper(path, language=None):
        calls["whisper"] += 1
        return ([{"start":0,"end":2,"text":"bonjour tout le monde"}], "fr")
    monkeypatch.setattr(app, "transcribe_with_local_whisper", fake_whisper)
    client = TestClient(app.app)
    owner = "owner-token-uploadcache-abcdefghijklmnop"
    payload = b"fake wav bytes that represent the same media"
    first = client.post("/api/transcribe-upload", data={"owner": owner}, files={"file": ("same.wav", payload, "audio/wav")})
    second = client.post("/api/transcribe-upload", data={"owner": owner}, files={"file": ("same.wav", payload, "audio/wav")})
    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["whisper"] == 1
    assert first.json()["record"]["cache_hit"] is False
    assert second.json()["record"]["cache_hit"] is True
    assert second.json()["record"]["media_id"] == first.json()["record"]["media_id"]
    assert second.json()["record"]["language"] == "fr"


def test_local_whisper_reports_detected_language_from_output(monkeypatch, tmp_path):
    audio = tmp_path / "french.wav"
    audio.write_bytes(b"fake")
    fake_bin = tmp_path / "whisper"
    fake_bin.write_text("#!/bin/sh\nexit 0\n")
    fake_bin.chmod(0o755)
    def fake_run(cmd, capture_output, text, timeout, env=None):
        out_dir = Path(cmd[cmd.index("--output_dir") + 1])
        (out_dir / "french.vtt").write_text("WEBVTT\n\n00:00.000 --> 00:02.000\nBonjour tout le monde\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="Detected language: French\n", stderr="")
    monkeypatch.setattr(app, "resolve_whisper_binary", lambda: str(fake_bin))
    monkeypatch.setattr(app.subprocess, "run", fake_run)
    segs, lang = app.transcribe_with_local_whisper(audio)
    assert lang == "fr"
    assert segs[0]["text"] == "Bonjour tout le monde"


def test_youtube_audio_download_retries_android_client_after_403(monkeypatch, tmp_path):
    attempts = []
    def fake_run(cmd, capture_output, text, timeout, env=None):
        attempts.append(cmd)
        if len(attempts) == 1:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="ERROR: HTTP Error 403: Forbidden")
        (tmp_path / "audio.mp3").write_bytes(b"audio")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    monkeypatch.setattr(app.subprocess, "run", fake_run)
    out = app.yt_dlp_download_audio("https://www.youtube.com/watch?v=EXa5OWG4XeY", tmp_path)
    assert out.name == "audio.mp3"
    assert len(attempts) == 2
    assert "youtube:player_client=android" in attempts[1]


def test_cached_long_youtube_can_return_before_duration_guard(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    app.save_transcript(source="Cached long", source_kind="youtube", method="seed", transcript="[00:00] cached", duration_seconds=5000, processing_seconds=1, media_id="cachedlong1", source_url="https://youtu.be/cachedlong1", title="Cached long", creator="Tester", language="en", segments=[{"start":0,"end":1,"text":"cached"}], provider_attempts=[], owner_token="owner-token-cachedlong-abcdefghijkl")
    monkeypatch.setattr(app, "yt_dlp_metadata", lambda url: {"id":"cachedlong1", "title":"Cached long", "duration": 5000, "language":"en", "webpage_url": url})
    client = TestClient(app.app)
    res = client.post("/api/transcribe-url", data={"url":"https://youtu.be/cachedlong1", "owner":"owner-token-cachedlong-abcdefghijkl"})
    assert res.status_code == 200
    assert res.json()["record"]["cache_hit"] is True


def test_local_whisper_falls_back_to_stdout_when_vtt_missing(monkeypatch, tmp_path):
    audio = tmp_path / "french.wav"
    audio.write_bytes(b"fake")
    fake_bin = tmp_path / "whisper"
    fake_bin.write_text("#!/bin/sh\nexit 0\n")
    fake_bin.chmod(0o755)
    def fake_run(cmd, capture_output, text, timeout, env=None):
        return subprocess.CompletedProcess(cmd, 0, stdout="Detected language: French\n[00:00.000 --> 00:02.000] Bonjour depuis stdout\n", stderr="")
    monkeypatch.setattr(app, "resolve_whisper_binary", lambda: str(fake_bin))
    monkeypatch.setattr(app.subprocess, "run", fake_run)
    segs, lang = app.transcribe_with_local_whisper(audio)
    assert lang == "fr"
    assert segs == [{"start": 0.0, "end": 2.0, "text": "Bonjour depuis stdout"}]


def test_youtube_audio_fallback_passes_language_hint_and_tiny_model(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    calls = {}
    monkeypatch.setattr(app, "yt_dlp_metadata", lambda url: {"id":"french12345", "title":"French short", "duration": 95, "language":"fr", "webpage_url": url})
    monkeypatch.setattr(app, "fetch_caption_url_segments", lambda meta: (_ for _ in ()).throw(RuntimeError("captions blocked")))
    monkeypatch.setattr(app, "youtube_transcript_api_segments", lambda video_id: (_ for _ in ()).throw(RuntimeError("transcript api blocked")))
    monkeypatch.setattr(app, "yt_dlp_grab_caption_segments", lambda url, work_dir, language=None: (_ for _ in ()).throw(RuntimeError(f"yt-dlp captions blocked {language}")))
    monkeypatch.setattr(app, "yt_dlp_download_audio", lambda url, work_dir: tmp_path / "audio.mp3")
    def fake_whisper(path, language=None, model=None, timeout=None):
        calls.update({"language": language, "model": model, "timeout": timeout})
        return [{"start": 0, "end": 2, "text": "Bonjour le monde"}], "fr"
    monkeypatch.setattr(app, "transcribe_with_local_whisper", fake_whisper)
    client = TestClient(app.app)
    res = client.post("/api/transcribe-url", data={"url":"https://youtu.be/french12345", "owner":"owner-token-french12345-abcdefghijkl"})
    assert res.status_code == 200
    rec = res.json()["record"]
    assert rec["language"] == "fr"
    assert rec["method"] == "local-whisper"
    assert calls["language"] == "fr"
    assert calls["model"] == "tiny"
    assert calls["timeout"] == 190
    assert any(a["provider"] == "yt-dlp-subtitles" and "fr" in a["error"] for a in rec["provider_attempts"])


def test_local_whisper_passes_threads_when_configured(monkeypatch, tmp_path):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"fake")
    fake_bin = tmp_path / "whisper"
    fake_bin.write_text("#!/bin/sh\nexit 0\n")
    fake_bin.chmod(0o755)
    def fake_run(cmd, capture_output, text, timeout, env=None):
        assert "--threads" in cmd
        assert cmd[cmd.index("--threads") + 1] == "4"
        out_dir = Path(cmd[cmd.index("--output_dir") + 1])
        (out_dir / "audio.vtt").write_text("WEBVTT\n\n00:00.000 --> 00:01.000\nHello\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="Detected language: English\n", stderr="")
    monkeypatch.setenv("LOCAL_WHISPER_THREADS", "4")
    monkeypatch.setattr(app, "resolve_whisper_binary", lambda: str(fake_bin))
    monkeypatch.setattr(app.subprocess, "run", fake_run)
    segs, lang = app.transcribe_with_local_whisper(audio)
    assert lang == "en"
    assert segs[0]["text"] == "Hello"


def test_transcribe_url_job_returns_accepted_and_can_complete(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    def fake_record(url, owner_token, started=None, allow_long=False, job_id=None):
        return {"id":"rec1", "title":"French", "language":"fr", "provider_attempts":[{"provider":"local-whisper", "ok": True}]}
    monkeypatch.setattr(app, "transcribe_youtube_url_to_record", fake_record)
    client = TestClient(app.app)
    res = client.post("/api/transcribe-url-job", data={"url":"https://youtu.be/vgIle-XrvQI", "owner":"owner-token-job-abcdefghijkl"})
    assert res.status_code == 202
    job_id = res.json()["job"]["id"]
    for _ in range(20):
        got = client.get(f"/api/jobs/{job_id}").json()["job"]
        if got["status"] == "done":
            break
        time.sleep(0.01)
    assert got["status"] == "done"
    assert got["record"]["language"] == "fr"


def test_local_whisper_falls_back_to_stdout_when_vtt_file_is_empty(monkeypatch, tmp_path):
    audio = tmp_path / "jane.wav"
    audio.write_bytes(b"fake")
    fake_bin = tmp_path / "whisper"
    fake_bin.write_text("#!/bin/sh\nexit 0\n")
    fake_bin.chmod(0o755)
    def fake_run(cmd, capture_output, text, timeout, env=None):
        out_dir = Path(cmd[cmd.index("--output_dir") + 1])
        (out_dir / "jane.vtt").write_text("WEBVTT\n\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="Detected language: English\n[00:00.000 --> 00:02.000] Real spoken words from stdout\n", stderr="")
    monkeypatch.setattr(app, "resolve_whisper_binary", lambda: str(fake_bin))
    monkeypatch.setattr(app.subprocess, "run", fake_run)
    segs, lang = app.transcribe_with_local_whisper(audio)
    assert lang == "en"
    assert segs == [{"start": 0.0, "end": 2.0, "text": "Real spoken words from stdout"}]


def test_local_whisper_adds_ffmpeg_dir_to_subprocess_path(monkeypatch, tmp_path):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"fake")
    fake_bin = tmp_path / "whisper"
    fake_bin.write_text("#!/bin/sh\nexit 0\n")
    fake_bin.chmod(0o755)
    fake_ffmpeg = tmp_path / "ffmpeg"
    fake_ffmpeg.write_text("#!/bin/sh\nexit 0\n")
    fake_ffmpeg.chmod(0o755)
    def fake_resolve(name, env_var, candidates):
        return str(fake_ffmpeg if name == "ffmpeg" else fake_bin)
    def fake_run(cmd, capture_output, text, timeout, env=None):
        assert str(tmp_path) in (env or {}).get("PATH", "").split(":")
        out_dir = Path(cmd[cmd.index("--output_dir") + 1])
        (out_dir / "audio.vtt").write_text("WEBVTT\n\n00:00.000 --> 00:01.000\nHello path\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="Detected language: English\n", stderr="")
    monkeypatch.setattr(app, "resolve_whisper_binary", lambda: str(fake_bin))
    monkeypatch.setattr(app, "resolve_binary", fake_resolve)
    monkeypatch.setattr(app.subprocess, "run", fake_run)
    segs, lang = app.transcribe_with_local_whisper(audio)
    assert lang == "en"
    assert segs[0]["text"] == "Hello path"


def test_non_youtube_media_url_falls_back_to_local_whisper(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    calls = {"downloaded": False}
    media = tmp_path / "downloaded.mp3"
    media.write_bytes(b"audio")
    monkeypatch.setattr(app, "yt_dlp_metadata", lambda url: {"id": "public-mp3", "title": "Public MP3", "webpage_url": url, "duration": 8})
    monkeypatch.setattr(app, "fetch_caption_url_segments", lambda meta: (_ for _ in ()).throw(RuntimeError("No usable native caption track found")))
    def fake_download(url, work_dir):
        calls["downloaded"] = True
        return media
    monkeypatch.setattr(app, "yt_dlp_download_audio", fake_download)
    monkeypatch.setattr(app, "transcribe_with_local_whisper", lambda path: ([{"start": 0, "end": 4, "text": "epic transcript public url spoken words"}], "en"))
    client = TestClient(app.app)

    res = client.post("/api/transcribe-url", data={"url": "https://media.example.com/public.mp3", "owner": "owner-token-public-url-aaaaaaaa"})

    assert res.status_code == 200
    rec = res.json()["record"]
    assert calls["downloaded"] is True
    assert rec["source_kind"] == "url"
    assert rec["method"] == "local-whisper"
    assert rec["language"] == "en"
    assert rec["word_count"] == 6
    assert rec["provider_attempts"][0]["provider"] == "captions"


def test_upload_records_media_duration_for_long_recordings(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    monkeypatch.setattr(app, "transcribe_with_local_whisper", lambda path: ([{"start": 0, "end": 3, "text": "long upload spoken words"}], "en"))
    monkeypatch.setattr(app, "media_duration_seconds", lambda path: 1862.4)
    client = TestClient(app.app)

    res = client.post(
        "/api/transcribe-upload",
        data={"owner": "owner-token-long-upload-aaaaaaaa"},
        files={"file": ("long-recording.mp3", b"fake audio", "audio/mpeg")},
    )

    assert res.status_code == 200
    rec = res.json()["record"]
    assert rec["source_kind"] == "upload"
    assert rec["duration_seconds"] == 1862.4
    assert rec["word_count"] == 4


def test_sync_route_still_rejects_long_video_but_async_job_allows_queued_chunks(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    long_meta = {"id": "lgvid1234AB", "title": "Two Hour Test", "duration": 7205, "webpage_url": "https://youtu.be/lgvid1234AB", "subtitles": {}, "automatic_captions": {}}
    monkeypatch.setattr(app, "yt_dlp_metadata", lambda url: long_meta)
    def fake_captions(meta):
        return ([{"start": 0, "end": 5, "text": "start words here"}, {"start": 601, "end": 606, "text": "middle words here"}, {"start": 7190, "end": 7198, "text": "ending words here now"}], "en", "native-caption-manual")
    monkeypatch.setattr(app, "fetch_caption_url_segments", fake_captions)
    client = TestClient(app.app)
    sync = client.post("/api/transcribe-url", data={"url": "https://youtu.be/lgvid1234AB", "owner": "owner-token-long-sync-aaaaaaaa"})
    assert sync.status_code == 422
    assert "too long" in sync.json()["detail"]
    job = client.post("/api/transcribe-url-job", data={"url": "https://youtu.be/lgvid1234AB", "owner": "owner-token-long-async-aaaaaaaa"})
    assert job.status_code == 202
    job_id = job.json()["job"]["id"]
    deadline = time.time() + 5
    while time.time() < deadline:
        got = client.get(f"/api/jobs/{job_id}").json()["job"]
        if got["status"] == "done":
            break
        time.sleep(0.05)
    assert got["status"] == "done"
    rec = got["record"]
    assert rec["duration_seconds"] == 7205
    assert rec["method"] == "queued-chunked-captions"
    assert rec["provider_attempts"][-1]["chunks"] >= 2
    assert "ending words here now" in rec["transcript"]


def test_chunked_whisper_offsets_audio_chunks(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    meta = {"id": "longwhisp1A", "title": "Chunk Whisper", "duration": 1250, "webpage_url": "https://youtu.be/longwhisp1A"}
    for name in ("fetch_caption_url_segments", "youtube_transcript_api_segments", "yt_dlp_grab_caption_segments"):
        monkeypatch.setattr(app, name, lambda *a, **k: (_ for _ in ()).throw(RuntimeError("provider down")))
    audio = tmp_path / "audio.mp3"; audio.write_bytes(b"audio")
    chunks = [tmp_path / "chunk-0000.wav", tmp_path / "chunk-0001.wav"]
    for c in chunks: c.write_bytes(b"chunk")
    monkeypatch.setattr(app, "yt_dlp_download_audio", lambda url, work_dir: audio)
    monkeypatch.setattr(app, "split_audio_for_long_transcription", lambda audio_path, work_dir, chunk_seconds: chunks)
    def fake_whisper(path, language=None, model=None, timeout=None):
        idx = chunks.index(path)
        return ([{"start": 1, "end": 3, "text": f"chunk {idx} spoken words with enough credible text"}], "en")
    monkeypatch.setattr(app, "transcribe_with_local_whisper", fake_whisper)
    rec = app.transcribe_long_youtube_queued("https://youtu.be/longwhisp1A", "longwhisp1A", time.monotonic(), tmp_path, "owner-token-long-whisper-aaaa", meta)
    assert rec["method"] == "queued-chunked-local-whisper"
    assert rec["segments"][1]["start"] == 601
    assert rec["provider_attempts"][-1]["chunks"] == 2


def test_chunked_whisper_total_failure_returns_helpful_public_message_and_keeps_private_trail(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    meta = {"id": "nocaptfail1", "title": "No Captions", "duration": 850, "webpage_url": "https://youtu.be/nocaptfail1"}
    for name in ("fetch_caption_url_segments", "youtube_transcript_api_segments", "yt_dlp_grab_caption_segments"):
        monkeypatch.setattr(app, name, lambda *a, **k: (_ for _ in ()).throw(RuntimeError("provider blocked details")))
    audio = tmp_path / "audio.mp3"; audio.write_bytes(b"audio")
    chunk = tmp_path / "chunk-0000.wav"; chunk.write_bytes(b"chunk")
    monkeypatch.setattr(app, "yt_dlp_download_audio", lambda url, work_dir: audio)
    monkeypatch.setattr(app, "split_audio_for_long_transcription", lambda audio_path, work_dir, chunk_seconds: [chunk])
    monkeypatch.setattr(app, "transcribe_with_local_whisper", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Command '['/usr/local/bin/whisper'] timed out with raw subprocess args")))
    with app.URL_JOBS_LOCK:
        app.URL_JOBS["job1"] = {"id": "job1", "status": "running"}

    with pytest.raises(RuntimeError) as err:
        app.transcribe_long_youtube_queued("https://youtu.be/nocaptfail1", "nocaptfail1", time.monotonic(), tmp_path, "owner-token-fail-aaaa", meta, job_id="job1")

    public_message = str(err.value)
    assert public_message == app.BLOCKED_MESSAGE
    assert "Provider trail" not in public_message
    assert "subprocess" not in public_message
    assert app.URL_JOBS["job1"]["private_error_detail"]
    assert "chunked-local-whisper" in app.URL_JOBS["job1"]["private_error_detail"]


def test_async_job_masks_provider_details_from_visitors(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    monkeypatch.setattr(app, "transcribe_youtube_url_to_record", lambda *a, **k: (_ for _ in ()).throw(HTTPException(422, f"{app.BLOCKED_MESSAGE} Provider trail: raw subprocess details")))
    client = TestClient(app.app)

    res = client.post("/api/transcribe-url-job", data={"url":"https://youtu.be/nocaptfail1", "owner":"owner-token-mask-aaaa"})
    assert res.status_code == 202
    job_id = res.json()["job"]["id"]
    deadline = time.time() + 5
    while time.time() < deadline:
        got = client.get(f"/api/jobs/{job_id}").json()["job"]
        if got["status"] == "error":
            break
        time.sleep(0.05)
    assert got["status"] == "error"
    assert got["error"] == app.BLOCKED_MESSAGE
    assert "Provider trail" not in got["error"]
    assert "private_error_detail" not in got


def test_url_job_state_survives_memory_reset_and_hides_private_detail(monkeypatch, tmp_path):
    jobs_path = tmp_path / "url_jobs.json"
    monkeypatch.setattr(app, "URL_JOBS_PATH", jobs_path)
    with app.URL_JOBS_LOCK:
        app.URL_JOBS.clear()
        app.URL_JOBS["persist123456"] = {
            "id": "persist123456",
            "status": "error",
            "url": "https://youtu.be/kJQP7kiw5Fk",
            "error": app.BLOCKED_MESSAGE,
            "private_error_detail": "Provider trail: raw subprocess details",
        }
        app.save_url_jobs_locked()
        app.URL_JOBS.clear()

    res = TestClient(app.app).get("/api/jobs/persist123456")

    assert res.status_code == 200
    job = res.json()["job"]
    assert job["status"] == "error"
    assert job["error"] == app.BLOCKED_MESSAGE
    assert "private_error_detail" not in job


def test_qc_forced_failure_job_skips_providers_persists_and_hides_detail(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    monkeypatch.setattr(app, "URL_JOBS_PATH", tmp_path / "url_jobs.json")
    called = {"youtube": 0, "media": 0}
    monkeypatch.setattr(app, "transcribe_youtube_url_to_record", lambda *a, **k: called.__setitem__("youtube", 1))
    monkeypatch.setattr(app, "transcribe_public_media_url_to_record", lambda *a, **k: called.__setitem__("media", 1))
    client = TestClient(app.app)

    res = client.post("/api/transcribe-url-job", data={"url":"https://example.com/hermes-forced-failure.mp3", "owner":"phase1-forced-failure-owner", "phase1_qc_force_failure":"true"})
    assert res.status_code == 202
    job_id = res.json()["job"]["id"]

    deadline = time.time() + 5
    while time.time() < deadline:
        got = client.get(f"/api/jobs/{job_id}").json()["job"]
        if got["status"] == "error":
            break
        time.sleep(0.05)
    assert got["status"] == "error"
    assert got["error"] == app.BLOCKED_MESSAGE
    assert "private_error_detail" not in got
    assert called == {"youtube": 0, "media": 0}
    with app.URL_JOBS_LOCK:
        private = app.URL_JOBS[job_id].get("private_error_detail")
        app.URL_JOBS.clear()
    reread = client.get(f"/api/jobs/{job_id}")
    assert reread.status_code == 200
    assert reread.json()["job"]["error"] == app.BLOCKED_MESSAGE
    assert "private_error_detail" not in reread.json()["job"]
    assert "forced backend transcription failure" in private


def test_async_medium_video_uses_single_audio_route_before_chunking(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    monkeypatch.setattr(app, "yt_dlp_metadata", lambda url: {"id": "mediumvid12", "title": "Medium", "duration": 281, "webpage_url": url})
    monkeypatch.setattr(app, "get_cached_transcript", lambda *a, **k: None)
    monkeypatch.setenv("YOUTUBE_JOB_SINGLE_AUDIO_MAX_SECONDS", "360")
    calls = []

    def fake_uncached(url, video_id, started, work_dir, owner_token=None, meta=None):
        calls.append((url, video_id, meta["duration"]))
        return {"id": "rec1", "transcript": "hola mundo", "segments": [{"start": 0, "end": 1, "text": "hola mundo"}], "method": "local-whisper"}

    monkeypatch.setattr(app, "transcribe_youtube_uncached", fake_uncached)
    monkeypatch.setattr(app, "transcribe_long_youtube_queued", lambda *a, **k: (_ for _ in ()).throw(AssertionError("chunked route should not run for medium video")))

    rec = app.transcribe_youtube_url_to_record("https://youtu.be/mediumvid12", "owner-token-medium-aaaa", allow_long=True, job_id="job-medium")

    assert rec["id"] == "rec1"
    assert calls == [("https://youtu.be/mediumvid12", "mediumvid12", 281)]


def test_uncached_spanish_audio_gets_duration_scaled_whisper_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    meta = {"id": "kJQP7kiw5Fk", "title": "Spanish", "duration": 282, "webpage_url": "https://youtu.be/kJQP7kiw5Fk", "language": "es"}
    audio = tmp_path / "audio.mp3"; audio.write_bytes(b"audio")
    monkeypatch.setattr(app, "fetch_caption_url_segments", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("caption blocked")))
    monkeypatch.setattr(app, "youtube_transcript_api_segments", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("caption blocked")))
    monkeypatch.setattr(app, "yt_dlp_grab_caption_segments", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("caption blocked")))
    monkeypatch.setattr(app, "yt_dlp_download_audio", lambda *a, **k: audio)
    seen = {}

    def fake_whisper(input_path, language=None, model=None, timeout=None):
        seen.update({"language": language, "model": model, "timeout": timeout})
        return ([{"start": 0, "end": 1, "text": "hola mundo prueba"}], "es")

    monkeypatch.setattr(app, "transcribe_with_local_whisper", fake_whisper)
    rec = app.transcribe_youtube_uncached("https://youtu.be/kJQP7kiw5Fk", "kJQP7kiw5Fk", time.monotonic(), tmp_path, "owner-token-spanish-aaaa", meta)

    assert rec["language"] == "es"
    assert seen["language"] == "es"
    assert seen["model"] == "tiny"
    assert seen["timeout"] >= 564


def test_unsupported_upload_returns_helpful_exact_supported_formats(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    client = TestClient(app.app)

    res = client.post(
        "/api/transcribe-upload",
        data={"owner": "owner-token-unsupported-upload-aaaa"},
        files={"file": ("not-media.exe", b"not media", "application/octet-stream")},
    )

    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "Unsupported file type: .exe" in detail
    assert "Upload one of:" in detail
    for ext in [".aac", ".avi", ".flac", ".m4a", ".md", ".mkv", ".mov", ".mp3", ".mp4", ".ogg", ".opus", ".srt", ".txt", ".vtt", ".wav", ".webm"]:
        assert ext in detail


def test_upload_temp_directory_is_removed_after_processing(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    upload_tmp = tmp_path / "upload-work-dir"
    def fake_mkdtemp(prefix=""):
        upload_tmp.mkdir(parents=True, exist_ok=False)
        return str(upload_tmp)
    monkeypatch.setattr(app.tempfile, "mkdtemp", fake_mkdtemp)
    monkeypatch.setattr(app, "transcribe_with_local_whisper", lambda path: ([{"start": 0, "end": 2, "text": "temporary upload cleanup proof"}], "en"))
    monkeypatch.setattr(app, "media_duration_seconds", lambda path: 2.0)
    client = TestClient(app.app)

    res = client.post(
        "/api/transcribe-upload",
        data={"owner": "owner-token-cleanup-upload-aaaa"},
        files={"file": ("cleanup.wav", b"fake spoken audio", "audio/wav")},
    )

    assert res.status_code == 200
    assert res.json()["record"]["word_count"] == 4
    assert not upload_tmp.exists()


def test_delete_transcript_removes_saved_analysis_for_retention(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    owner = "owner-token-delete-retention-aaaa"
    rec = app.save_transcript(
        source="Retention Test",
        source_kind="upload",
        method="seed",
        transcript="[00:00] retention cleanup words",
        duration_seconds=2,
        processing_seconds=0,
        media_id="upload:retention",
        source_url=None,
        title="Retention Test",
        creator=None,
        language="en",
        segments=[{"start": 0, "end": 2, "text": "retention cleanup words"}],
        provider_attempts=[],
        owner_token=owner,
    )
    analysis = app.save_analysis(
        transcript_id=rec["id"],
        output_type="executive_summary",
        question=None,
        analysis="## Executive summary\nRetention cleanup proof.",
        owner_token=owner,
    )
    client = TestClient(app.app)

    res = client.delete(f"/api/transcripts/{rec['id']}", headers={"X-Transcript-Owner": owner})

    assert res.status_code == 200
    with app.db() as conn:
        assert conn.execute("SELECT 1 FROM transcripts WHERE id=?", (rec["id"],)).fetchone() is None
        assert conn.execute("SELECT 1 FROM analyses WHERE id=?", (analysis["id"],)).fetchone() is None
