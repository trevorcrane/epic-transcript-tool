"""Restart during screenshot capture must show the saved transcript and not download again."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOB_ID = "0788fe2f219e"
TRANSCRIPT = "[00:00] Hello fixture line"

FIXTURE = r"""
import json
import os
import sys
from pathlib import Path

os.environ["TRANSCRIPT_DATA_DIR"] = sys.argv[1]
sys.path.insert(0, sys.argv[2])
mode = sys.argv[3]
port = int(sys.argv[4])
marker = Path(sys.argv[1]) / "download_attempts.txt"

if mode == "settle":
    import screenshots

    def refuse_download(*args, **kwargs):
        marker.write_text("called\n", encoding="utf-8")
        raise RuntimeError("screenshot download was started after restart")

    screenshots.download_360p = refuse_download
    screenshots.capture_from_url = refuse_download

import app

if mode == "plant":
    record = {
        "id": "rec-restart",
        "transcript": "[00:00] Hello fixture line",
        "source": "https://www.youtube.com/watch?v=abcdefghijk",
        "method": "captions",
    }
    with app.URL_JOBS_LOCK:
        app.URL_JOBS["0788fe2f219e"] = {
            "id": "0788fe2f219e",
            "status": "running",
            "stage": "screenshots",
            "message": "Grabbing screenshots",
            "percent": 90,
            "url": "https://www.youtube.com/watch?v=abcdefghijk",
            "include_screenshots": True,
            "record": record,
        }
        app.save_url_jobs_locked()

import uvicorn
uvicorn.run(app.app, host="127.0.0.1", port=port, log_level="error")
"""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start(data: Path, mode: str) -> tuple[subprocess.Popen, int]:
    port = _free_port()
    script = data / "restart_fixture.py"
    script.write_text(FIXTURE, encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(script), str(data), str(ROOT), mode, str(port)],
        stdout=open(data / f"{mode}.out", "wb"),
        stderr=open(data / f"{mode}.err", "wb"),
        start_new_session=True,
    )
    deadline = time.time() + 15
    last = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            err = (data / f"{mode}.err").read_text(encoding="utf-8", errors="replace")
            raise AssertionError(f"{mode} process exited {proc.returncode}: {err}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
                if response.status == 200:
                    return proc, port
        except Exception as exc:
            last = str(exc)
            time.sleep(0.1)
    proc.kill()
    err = (data / f"{mode}.err").read_text(encoding="utf-8", errors="replace")
    raise AssertionError(f"{mode} server did not answer: {last}; stderr={err}")


def _get(port: int) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/jobs/{JOB_ID}", timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))["job"]


def _stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _page_accepts(job: dict) -> bool:
    record = job.get("record") if isinstance(job.get("record"), dict) else {}
    saved = str(record.get("transcript") or "").strip()
    return bool(saved and (job.get("status") == "done" or job.get("interrupted")))


def test_restart_during_screenshots_surfaces_transcript_without_download(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    first, port = _start(data, "plant")
    try:
        before = _get(port)
        assert before["status"] == "running"
        assert before["stage"] == "screenshots"
        assert before["record"]["transcript"] == TRANSCRIPT
        assert _page_accepts(before) is False
        on_disk = json.loads((data / "url_jobs.json").read_text(encoding="utf-8"))
        assert on_disk[JOB_ID]["status"] == "running"
    finally:
        _stop(first)
    assert first.poll() is not None

    second, port2 = _start(data, "settle")
    try:
        after = _get(port2)
        assert after["status"] == "done"
        assert after["interrupted"] is True
        assert after["record"]["transcript"] == TRANSCRIPT
        assert after["screenshots"]["status"] == "error"
        assert after["screenshots"]["error"] == "Screenshots could not be captured."
        assert after["screenshots"]["frames"] == []
        assert _page_accepts(after) is True
        saved = json.loads((data / "url_jobs.json").read_text(encoding="utf-8"))
        assert saved[JOB_ID]["status"] == "done"
        assert not (data / "download_attempts.txt").exists()
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        assert "attempt < 150" in html
        assert "job.interrupted" in html
        assert "include_screenshots" not in after.get("message", "")
    finally:
        _stop(second)


def test_restart_without_a_transcript_stops_instead_of_downloading(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "url_jobs.json").write_text(json.dumps({
        "abc123abc123": {
            "id": "abc123abc123",
            "status": "running",
            "stage": "transcribing",
            "url": "https://www.youtube.com/watch?v=abcdefghijk",
            "include_screenshots": True,
        }
    }), encoding="utf-8")
    proc, port = _start(data, "settle")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/jobs/abc123abc123", timeout=2) as response:
            job = json.loads(response.read().decode("utf-8"))["job"]
        assert job["status"] == "error"
        assert job["interrupted"] is True
        assert "interrupted" in job["error"]
        assert "record" not in job
        assert not (data / "download_attempts.txt").exists()
    finally:
        _stop(proc)
