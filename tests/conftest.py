import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app


@pytest.fixture(autouse=True)
def isolate_url_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "URL_JOBS_PATH", tmp_path / "url_jobs.json")
    with app.URL_JOBS_LOCK:
        app.URL_JOBS.clear()
    yield
    with app.URL_JOBS_LOCK:
        app.URL_JOBS.clear()
