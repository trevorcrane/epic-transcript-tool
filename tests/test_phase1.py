import json

from fastapi.testclient import TestClient

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
    )
    client = TestClient(app.app)
    for fmt, marker in [("txt", "[00:00] hello"), ("md", "# Format Test"), ("srt", "1\n00:00:00,000")]:
        res = client.get(f"/api/transcripts/{rec['id']}/download?format={fmt}")
        assert res.status_code == 200
        assert marker in res.text
