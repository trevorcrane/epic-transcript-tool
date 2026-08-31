from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_smoke():
    spec = importlib.util.spec_from_file_location(
        "phase3_long_analysis_smoke_under_test",
        ROOT / "scripts" / "phase3_long_analysis_smoke.py",
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_long_analysis_download_verifier_requires_privacy_and_owner_markers(monkeypatch):
    module = load_smoke()
    calls = []

    def fake_request(path, *, headers=None, **kwargs):
        calls.append((path, headers or {}))
        if len(calls) == 1:
            return module.HttpResult(403, b"Forbidden", {"content-type": "application/json"})
        return module.HttpResult(
            200,
            b"# Executive summary\nAI-generated from the transcript\n# Create 100 content assets\nTranscript evidence [00:01] proof",
            {"content-type": "text/markdown; charset=utf-8"},
        )

    monkeypatch.setattr(module, "request", fake_request)

    detail = module.verify_analysis_download("analysis123", "owner123")

    assert calls == [
        ("/api/analysis/analysis123/download", {}),
        ("/api/analysis/analysis123/download", {"X-Transcript-Owner": "owner123"}),
    ]
    assert detail["unauthenticated_download_status"] == 403
    assert detail["owner_download_status"] == 200
    assert detail["owner_download_bytes"] > 50
    assert "text/markdown" in detail["owner_download_content_type"]
