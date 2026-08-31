from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_watchdog():
    spec = importlib.util.spec_from_file_location(
        "public_recovery_watchdog_under_test",
        ROOT / "scripts" / "public_recovery_watchdog.py",
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_classifies_known_sqlite_database_open_failure():
    module = load_watchdog()

    assert module.classify_failure(500, '{"detail":"unable to open database file"}') == "sqlite_open_failure"


def test_scrub_secrets_redacts_nested_owner_tokens():
    module = load_watchdog()

    scrubbed = module.scrub_secrets({"record": {"owner_token": "secret", "nested": [{"token": "abc"}]}})

    assert scrubbed["record"]["owner_token"] == "[redacted]"
    assert scrubbed["record"]["nested"][0]["token"] == "[redacted]"


def test_compact_job_payload_removes_transcript_and_token_detail():
    module = load_watchdog()

    compact = module.compact_job_payload({
        "ok": True,
        "job": {
            "id": "job-1",
            "status": "done",
            "record": {
                "id": "rec-1",
                "method": "native-caption-subtitles",
                "word_count": 366,
                "segment_count": 61,
                "owner_token": "secret",
                "transcript": "full transcript should not be stored",
                "segments": [{"text": "line"}],
            },
        },
    })

    assert compact["job"]["record"]["id"] == "rec-1"
    assert "owner_token" not in compact["job"]["record"]
    assert "transcript" not in compact["job"]["record"]
    assert "segments" not in compact["job"]["record"]


def test_start_async_job_accepts_wrapped_job_payload(monkeypatch):
    module = load_watchdog()
    responses = iter(
        [
            (202, '{"ok":true,"job":{"id":"job-123","status":"running"}}'),
            (
                200,
                '{"ok":true,"job":{"id":"job-123","status":"done","record":{"id":"rec-1","method":"native-caption-subtitles","word_count":366,"segments":[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20]}}}',
            ),
        ]
    )

    monkeypatch.setattr(module, "http_request", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    result = module.start_async_job("https://epic-transcript.robyncrane.com", "https://youtu.be/dQw4w9WgXcQ", poll_seconds=1, poll_interval=0)

    assert result["ok"] is True
    assert result["job_id"] == "job-123"
    assert result["job_status"] == "done"
    assert result["record"]["id"] == "rec-1"


def test_watchdog_kickstarts_launchd_and_rechecks_after_sqlite_failure(monkeypatch):
    module = load_watchdog()
    calls: list[str] = []

    def fake_health(base_url):
        calls.append("health")
        if calls.count("health") == 1:
            return {"ok": True, "status": 200, "failure": None, "payload": {"ok": True}}
        return {"ok": True, "status": 200, "failure": None, "payload": {"ok": True}}

    def fake_job(base_url, video_url):
        calls.append("job")
        if calls.count("job") == 1:
            return {"ok": False, "start_status": 500, "failure": "sqlite_open_failure"}
        return {
            "ok": True,
            "start_status": 202,
            "poll_status": 200,
            "record": {"id": "abc", "word_count": 366, "segment_count": 61, "method": "native-caption-subtitles"},
        }

    def fake_kickstart(label=module.LAUNCHD_LABEL):
        calls.append(f"kickstart:{label}")
        return {"returncode": 0, "command": ["launchctl", "kickstart", "-k", f"gui/501/{label}"]}

    monkeypatch.setattr(module, "health_check", fake_health)
    monkeypatch.setattr(module, "start_async_job", fake_job)
    monkeypatch.setattr(module, "kickstart_api", fake_kickstart)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    report = module.run_watchdog("https://epic-transcript.robyncrane.com", "https://youtu.be/dQw4w9WgXcQ")

    assert report["ok"] is True
    assert report["restarted"] is True
    assert "kickstart:com.epic.transcript-api" in calls
    assert report["async_after"]["record"]["word_count"] == 366


def test_watchdog_no_restart_leaves_failure_reportable(monkeypatch):
    module = load_watchdog()

    monkeypatch.setattr(module, "health_check", lambda _base: {"ok": True, "failure": None})
    monkeypatch.setattr(module, "start_async_job", lambda _base, _video: {"ok": False, "failure": "server_failure"})
    monkeypatch.setattr(module, "kickstart_api", lambda: (_ for _ in ()).throw(AssertionError("should not restart")))

    report = module.run_watchdog("https://epic-transcript.robyncrane.com", "https://youtu.be/dQw4w9WgXcQ", no_restart=True)

    assert report["ok"] is False
    assert report["restarted"] is False
    assert "async_after" not in report
