import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app


def pytest_configure(config):
    config.addinivalue_line("markers", "auth_enforce: run the test with TRANSCRIPT_AUTH_MODE=enforce")


@pytest.fixture(autouse=True)
def isolate_url_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "URL_JOBS_PATH", tmp_path / "url_jobs.json")
    with app.URL_JOBS_LOCK:
        app.URL_JOBS.clear()
    yield
    with app.URL_JOBS_LOCK:
        app.URL_JOBS.clear()


@pytest.fixture(autouse=True)
def auth_mode_for_legacy_tests(request, monkeypatch):
    """Existing tests call guarded routes without credentials: run them in log mode.
    Tests marked auth_enforce get the production default (enforce)."""
    if request.node.get_closest_marker("auth_enforce"):
        monkeypatch.setenv("TRANSCRIPT_AUTH_MODE", "enforce")
    else:
        monkeypatch.setenv("TRANSCRIPT_AUTH_MODE", "log")
    monkeypatch.delenv("TRANSCRIPT_API_TOKENS", raising=False)
    yield
