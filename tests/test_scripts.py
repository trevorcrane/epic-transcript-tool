from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

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
