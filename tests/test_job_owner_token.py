import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

import app

OWNER = "owner-token-job-get-aaaaaaaaaaaa"
OTHER = "owner-token-job-get-bbbbbbbbbbbb"


def _no_owner_token(payload, secret: str) -> None:
    assert secret not in json.dumps(payload)
    def walk(node) -> None:
        if isinstance(node, dict):
            assert "owner_token" not in node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(payload)


def _wait_done(client: TestClient, job_id: str) -> dict:
    deadline = time.time() + 5
    last = {}
    while time.time() < deadline:
        last = client.get(f"/api/jobs/{job_id}").json()["job"]
        if last.get("status") in {"done", "error"}:
            return last
        time.sleep(0.02)
    return last


def test_plain_job_get_hides_owner_token_and_owner_actions_reject_without_it(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    monkeypatch.setenv("SMTP_HOST", "smtp.example")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "mailer")
    monkeypatch.setenv("SMTP_PASS", "secret")
    monkeypatch.setenv("OWNER_EMAIL", "owner@example.com")

    def fake_record(url, owner_token, started=None, allow_long=False, job_id=None):
        return app.save_transcript(
            source="Owned video",
            source_kind="youtube",
            method="seed",
            transcript="[00:00] owned words stay on the job",
            duration_seconds=1,
            processing_seconds=0,
            media_id="ownedjob123",
            source_url=url,
            title="Owned video",
            creator="Tester",
            language="en",
            segments=[{"start": 0, "end": 1, "text": "owned words stay on the job"}],
            provider_attempts=[],
            owner_token=owner_token,
        )

    monkeypatch.setattr(app, "transcribe_youtube_url_to_record", fake_record)
    client = TestClient(app.app)
    created = client.post("/api/transcribe-url-job", data={"url": "https://youtu.be/abcdefghijk", "owner": OWNER})
    assert created.status_code == 202
    created_job = created.json()["job"]
    assert created_job["owner_token"] == OWNER
    job_id = created_job["id"]

    plain = client.get(f"/api/jobs/{job_id}")
    assert plain.status_code == 200
    _no_owner_token(plain.json(), OWNER)

    wrong = client.get(f"/api/jobs/{job_id}", headers={"X-Transcript-Owner": OTHER})
    assert wrong.status_code == 200
    _no_owner_token(wrong.json(), OWNER)

    done = _wait_done(client, job_id)
    assert done["status"] == "done"
    assert "owned words" not in json.dumps(done)
    revealed = client.get(f"/api/jobs/{job_id}")
    _no_owner_token(revealed.json(), OWNER)
    assert "owned words" not in revealed.text
    with_token = client.get(f"/api/jobs/{job_id}", headers={"X-Transcript-Owner": OWNER})
    assert with_token.json()["job"]["record"]["owner_token"] == OWNER
    assert "owned words" in with_token.json()["job"]["record"]["transcript"]

    rec_id = done["record"]["id"]
    assert client.get(f"/api/transcripts/{rec_id}").status_code == 403
    assert client.post(f"/api/transcripts/{rec_id}/download-link?format=txt").status_code == 403
    assert client.delete(f"/api/transcripts/{rec_id}").status_code == 403
    assert client.post(f"/api/analyze/{rec_id}", data={"output_type": "executive_summary"}).status_code == 403
    assert client.post(f"/api/analyze-all/{rec_id}").status_code == 403
    assert client.post(f"/api/email/{rec_id}").status_code == 403
    kept = client.get(f"/api/transcripts/{rec_id}", headers={"X-Transcript-Owner": OWNER})
    assert kept.status_code == 200

    made = client.post(
        f"/api/analyze/{rec_id}",
        data={"output_type": "executive_summary"},
        headers={"X-Transcript-Owner": OWNER},
    )
    assert made.status_code == 200
    assert client.get(f"/api/analysis/{made.json()['analysis_id']}/download").status_code == 403


def test_page_keeps_the_create_response_owner_token():
    html = Path(__file__).resolve().parents[1].joinpath("static", "index.html").read_text(encoding="utf-8")
    assert "rememberOwnerToken(started.job.owner_token)" in html
    assert "sessionStorage.setItem(OWNER_KEY, token)" in html
