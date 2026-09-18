"""Gemini primary -> Groq backup -> labeled template fallback."""
import app
from fastapi.testclient import TestClient
from tests.test_phase3 import seed_record, OWNER


def _clear(monkeypatch):
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "PHASE3_AI_PROVIDERS", "PHASE3_AI_ALL_SOURCES"):
        monkeypatch.delenv(k, raising=False)


def test_provider_order_reflects_configured_keys(monkeypatch):
    _clear(monkeypatch)
    assert app.phase3_ai_provider_order() == []
    monkeypatch.setenv("GROQ_API_KEY", "g")
    assert app.phase3_ai_provider_order() == ["groq"]
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert app.phase3_ai_provider_order() == ["gemini", "groq"]
    monkeypatch.setenv("PHASE3_AI_PROVIDERS", "groq,gemini")
    assert app.phase3_ai_provider_order() == ["groq", "gemini"]


def test_gemini_failure_falls_through_to_groq(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("PHASE3_GEMINI_DAILY_LIMIT", "0")  # forces 429 on Gemini
    monkeypatch.setattr(app, "call_groq_text", lambda prompt: "# Groq output\n\nbackup worked")
    assert "Groq output" in app.call_ai_text("hello")


def test_groq_only_setup_works(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setattr(app, "call_groq_text", lambda prompt: "# Groq output")
    assert app.call_ai_text("hi") == "# Groq output"


def test_no_keys_returns_labeled_template(monkeypatch, tmp_path):
    _clear(monkeypatch)
    rec = seed_record(tmp_path, monkeypatch)
    client = TestClient(app.app)
    res = client.post(f"/api/analyze/{rec['id']}", data={"output_type": "executive_summary"}, headers={"X-Transcript-Owner": OWNER})
    assert res.status_code == 200
    assert "Basic template result" in res.json()["analysis"]


def test_health_reports_ai_providers(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "g")
    client = TestClient(app.app)
    body = client.get("/health").json()["setup"]
    assert body["ai_configured"] is True
    assert body["ai_providers"] == ["groq"]
    assert body["groq_configured"] is True


def test_default_gemini_model_is_not_retired():
    assert "1.5" not in app.PHASE3_GEMINI_DEFAULT_MODEL


class _Resp:
    def __init__(self, status, payload, text=""):
        self.status_code = status; self._p = payload; self.text = text or ""
    def json(self):
        return self._p


def test_gemini_discovery_picks_newest_flash(monkeypatch):
    _clear(monkeypatch); app.PHASE3_MODEL_CACHE.clear()
    payload = {"models": [
        {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.6-flash-lite", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.6-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.6-flash-image", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.6-pro", "supportedGenerationMethods": ["generateContent"]},
    ]}
    monkeypatch.setattr(app.requests, "get", lambda *a, **k: _Resp(200, payload))
    assert app.discover_gemini_model("k") == "gemini-3.6-flash"
    assert app._cached_model("gemini") == "gemini-3.6-flash"


def test_groq_discovery_prefers_gpt_oss_120b_and_skips_guards(monkeypatch):
    _clear(monkeypatch); app.PHASE3_MODEL_CACHE.clear()
    payload = {"data": [{"id": "meta-llama/llama-prompt-guard-2-86m"}, {"id": "openai/gpt-oss-20b"}, {"id": "openai/gpt-oss-120b"}, {"id": "whisper-large-v3"}]}
    monkeypatch.setattr(app.requests, "get", lambda *a, **k: _Resp(200, payload))
    assert app.discover_groq_model("g") == "openai/gpt-oss-120b"


def test_env_override_beats_discovery(monkeypatch):
    _clear(monkeypatch); app.PHASE3_MODEL_CACHE.clear()
    monkeypatch.setenv("PHASE3_GROQ_MODEL", "custom/model")
    monkeypatch.setattr(app.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call")))
    assert app.discover_groq_model("g") == "custom/model"


def test_discovery_failure_falls_back_to_default(monkeypatch):
    _clear(monkeypatch); app.PHASE3_MODEL_CACHE.clear()
    monkeypatch.setattr(app.requests, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert app.discover_gemini_model("k") == app.PHASE3_GEMINI_DEFAULT_MODEL
    assert app.discover_groq_model("g") == app.PHASE3_GROQ_DEFAULT_MODEL


def test_gemini_404_rediscovers_once(monkeypatch):
    _clear(monkeypatch); app.PHASE3_MODEL_CACHE.clear()
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    app._remember_model("gemini", "gemini-old-flash")
    calls = []
    def fake_post(url, **k):
        calls.append(url)
        if "gemini-old-flash" in url:
            return _Resp(404, {"error": {"message": "gone"}})
        return _Resp(200, {"candidates": [{"content": {"parts": [{"text": "fresh"}]}}]})
    monkeypatch.setattr(app.requests, "post", fake_post)
    monkeypatch.setattr(app.requests, "get", lambda *a, **k: _Resp(200, {"models": [{"name": "models/gemini-9.9-flash", "supportedGenerationMethods": ["generateContent"]}]}))
    assert app.call_gemini_text("hi") == "fresh"
    assert len(calls) == 2 and "gemini-9.9-flash" in calls[1]
