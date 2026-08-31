import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
from urllib.parse import urlparse

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
    for fmt, marker in [("txt", "[00:00] hello"), ("md", "# Format Test"), ("srt", "1\n00:00:00,000")]:
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
    def fake_run(cmd, capture_output, text, timeout):
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
    def fake_run(cmd, capture_output, text, timeout):
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
    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="Detected language: French\n[00:00.000 --> 00:02.000] Bonjour depuis stdout\n", stderr="")
    monkeypatch.setattr(app, "resolve_whisper_binary", lambda: str(fake_bin))
    monkeypatch.setattr(app.subprocess, "run", fake_run)
    segs, lang = app.transcribe_with_local_whisper(audio)
    assert lang == "fr"
    assert segs == [{"start": 0.0, "end": 2.0, "text": "Bonjour depuis stdout"}]
