import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def isolate_free_public_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSCRIPT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRANSCRIPT_STATIC_DIR", str(SRC / "free_public" / "static"))
    import free_public.app as app

    with app.LOCK:
        app.JOBS.clear()
    yield
    with app.LOCK:
        app.JOBS.clear()
