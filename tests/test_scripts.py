from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def load_phase1_health(monkeypatch, argv, env=None):
    env = env or {}
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.delenv("EPIC_TRANSCRIPT_BASE_URL", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("phase1_health_under_test", ROOT / "scripts" / "phase1_health.py")
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_phase1_health_cli_url_overrides_default_base(monkeypatch):
    module = load_phase1_health(monkeypatch, ["phase1_health.py", "https://example.test/"])

    assert module.BASE_URL == "https://example.test"


def test_phase1_health_env_base_still_works_without_cli_arg(monkeypatch):
    module = load_phase1_health(
        monkeypatch,
        ["phase1_health.py"],
        {"EPIC_TRANSCRIPT_BASE_URL": "https://env.example.test/"},
    )

    assert module.BASE_URL == "https://env.example.test"


def test_phase1_health_uses_three_distinct_stable_video_ids(monkeypatch):
    module = load_phase1_health(monkeypatch, ["phase1_health.py"])

    urls = {case.name: case.url for case in module.CASES}

    assert len(urls) == 3
    assert "v34Eg12mhDM" in urls["regression"]
    assert "dQw4w9WgXcQ" in urls["manual-caption-control"]
    assert "SXHMnicI6Pg" in urls["automatic-caption-control"]
    assert len({case.url.split("?")[0].rstrip("/").split("/")[-1] for case in module.CASES}) == 3


def test_phase1_health_enforces_case_specific_methods_and_transcript_quality(monkeypatch):
    module = load_phase1_health(monkeypatch, ["phase1_health.py"])

    cases = {case.name: case for case in module.CASES}
    assert cases["regression"].expected_method == "native-caption-automatic_captions"
    assert cases["manual-caption-control"].expected_method == "native-caption-subtitles"
    assert cases["automatic-caption-control"].expected_method == "native-caption-automatic_captions"
    assert cases["automatic-caption-control"].min_segments == 2
    assert cases["automatic-caption-control"].min_words == 3

    def fake_post_form(url, data, timeout=180):
        payload = {
            "record": {
                "media_id": "SXHMnicI6Pg",
                "title": "Let's see how many people get Rick rolled",
                "method": "native-caption-automatic_captions",
                "language": "en",
                "word_count": 3,
                "cache_hit": True,
                "provider_attempts": [{"provider": "metadata"}, {"provider": "native-caption-extractor"}],
                "segments": [
                    {"start": 0.0, "end": 1.2, "text": "Never gonna"},
                    {"start": 1.3, "end": 2.8, "text": "give you up"},
                ],
            }
        }
        return 200, json.dumps(payload)

    monkeypatch.setattr(module, "post_form", fake_post_form)
    result = module.check_case(cases["automatic-caption-control"])

    assert result["ok"] is True
    assert result["video_id"] == "SXHMnicI6Pg"
    assert result["beginning"] == "Never gonna"
    assert result["end"] == "give you up"
    assert result["timestamps_increasing"] is True
    assert result["quality_checks"]["method"] is True
    assert result["quality_checks"]["nonempty_beginning_end"] is True
