"""v8.2: owner-only transcript and screenshot reads, plus no-store on /api and /r."""
from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

import app

OWNER = "owner-token-v82-aaaaaaaaaaaaaaaa"
OTHER = "owner-token-v82-bbbbbbbbbbbbbbbb"
SECRET = "[00:00] secret transcript body stays private"
FRAME = "frame_0000_0001.00s.jpg"


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    return TestClient(app.app)


def _record(owner: str = OWNER, text: str = SECRET, media_id: str = "privytid1234") -> dict:
    return app.save_transcript(
        source="Private Video",
        source_kind="youtube",
        method="seed",
        transcript=text,
        duration_seconds=2,
        processing_seconds=0,
        media_id=media_id,
        source_url="https://youtu.be/privytid1234",
        title="Private Video",
        creator="Tester",
        language="en",
        segments=[{"start": 0, "end": 1, "text": "secret transcript body stays private"}],
        provider_attempts=[],
        owner_token=owner,
    )


def _store_job(rec: dict, owner: str = OWNER, *, shots: bool = False, tmp_path: Path | None = None, extra: dict | None = None) -> str:
    job_id = uuid.uuid4().hex[:12]
    record = dict(rec)
    job = {
        "id": job_id,
        "status": "done",
        "url": "https://youtu.be/privytid1234",
        "created_at": 1,
        "include_screenshots": shots,
        "owner_token": owner,
        "record": record,
        "percent": 100,
    }
    if extra:
        job.update(extra)
    if shots:
        if tmp_path is None:
            raise AssertionError("screenshot jobs need tmp_path")
        job_dir = tmp_path / "screenshots" / job_id
        job_dir.mkdir(parents=True)
        (job_dir / FRAME).write_bytes(b"\xff\xd8\xff\xd9")
        with zipfile.ZipFile(job_dir / "screenshots.zip", "w") as zf:
            zf.writestr(FRAME, b"\xff\xd8\xff\xd9")
            zf.writestr("manifest.csv", "timestamp\n0:01\n")
        payload = {
            "status": "done",
            "error": None,
            "count": 1,
            "shown": 1,
            "frames": [{
                "time": 1.0,
                "timestamp": "0:01",
                "filename": FRAME,
                "url": f"/api/jobs/{job_id}/screenshots/{FRAME}",
            }],
            "zip_url": f"/api/jobs/{job_id}/screenshots.zip",
        }
        job["screenshots"] = payload
        record["screenshots"] = payload
        job["record"] = record
    with app.URL_JOBS_LOCK:
        app.URL_JOBS[job_id] = job
        app.save_url_jobs_locked()
    return job_id


def _nostore(response) -> None:
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["cdn-cache-control"] == "no-store"
    assert "X-Transcript-Owner" in response.headers["vary"]


def _no_secrets(payload, *secrets: str) -> None:
    blob = json.dumps(payload)
    for secret in secrets:
        assert secret not in blob

    def walk(node) -> None:
        if isinstance(node, dict):
            assert "owner_token" not in node
            assert "private_error_detail" not in node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)


def _headers(owner: str | None) -> dict:
    return {"X-Transcript-Owner": owner} if owner else {}


def test_api_routes_send_private_no_store_and_public_pages_do_not(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    for path in ("/api/analysis-outputs", "/api/recent", "/api/jobs/missingmissi"):
        response = client.get(path)
        _nostore(response)
    home = client.get("/")
    health = client.get("/health")
    assert home.headers.get("cdn-cache-control") != "no-store"
    assert health.headers.get("cdn-cache-control") != "no-store"
    assert home.headers.get("cache-control") != "private, no-store"
    assert health.headers.get("cache-control") != "private, no-store"


def test_share_page_and_share_api_send_private_no_store(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    job_id = _store_job(_record(), shots=True, tmp_path=tmp_path)
    created = client.post(f"/api/jobs/{job_id}/share", headers=_headers(OWNER))
    assert created.status_code == 200
    _nostore(created)
    token = created.json()["token"]

    share = client.get(f"/api/share/{token}")
    page = client.get(f"/r/{token}")
    image = client.get(f"/api/share/{token}/screenshots/{FRAME}")
    download = client.get(f"/api/share/{token}/download/transcript.txt")
    for response in (share, page, image, download):
        _nostore(response)
        assert response.headers["referrer-policy"] == "no-referrer"
    assert page.status_code == 200
    missing = client.get("/r/not-a-valid-share-token-but-long-enough-ok")
    assert missing.status_code == 404
    _nostore(missing)


def test_job_get_hides_transcript_token_and_private_error_without_owner(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    job_id = _store_job(_record(), extra={"private_error_detail": "Provider trail: raw subprocess details"})
    plain = client.get(f"/api/jobs/{job_id}")
    wrong = client.get(f"/api/jobs/{job_id}", headers=_headers(OTHER))
    short = client.get(f"/api/jobs/{job_id}", headers=_headers("too-short"))
    assert plain.status_code == wrong.status_code == short.status_code == 200
    for response in (plain, wrong, short):
        _nostore(response)
        body = response.json()
        assert body["job"]["status"] == "done"
        _no_secrets(body, OWNER, SECRET, "Provider trail")
        record = body["job"].get("record") or {}
        assert "transcript" not in record
        assert "segments" not in record


def test_job_get_with_owner_returns_transcript(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    def fake_record(url, owner_token, started=None, allow_long=False, job_id=None):
        return _record(owner_token, media_id="abcdefghijk")

    monkeypatch.setattr(app, "transcribe_youtube_url_to_record", fake_record)
    created = client.post("/api/transcribe-url-job", data={"url": "https://youtu.be/abcdefghijk", "owner": OWNER})
    assert created.status_code == 202
    _nostore(created)
    created_job = created.json()["job"]
    assert created_job["owner_token"] == OWNER
    job_id = created_job["id"]

    revealed = {}
    for _ in range(50):
        revealed = client.get(f"/api/jobs/{job_id}", headers=_headers(OWNER)).json()["job"]
        if revealed.get("status") in {"done", "error"}:
            break
    assert revealed["status"] == "done"
    assert SECRET in revealed["record"]["transcript"]
    assert revealed["record"]["owner_token"] == OWNER
    assert "private_error_detail" not in revealed


def test_screenshot_bytes_and_zip_require_owner(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    job_id = _store_job(_record(), shots=True, tmp_path=tmp_path)
    image = f"/api/jobs/{job_id}/screenshots/{FRAME}"
    archive = f"/api/jobs/{job_id}/screenshots.zip"
    for path in (image, archive):
        assert client.get(path).status_code == 403
        assert client.get(path, headers=_headers(OTHER)).status_code == 403
        _nostore(client.get(path))
    owned_image = client.get(image, headers=_headers(OWNER))
    owned_zip = client.get(archive, headers=_headers(OWNER))
    assert owned_image.status_code == 200
    assert owned_image.content[:3] == b"\xff\xd8\xff"
    assert owned_zip.status_code == 200
    assert owned_zip.content[:2] == b"PK"
    _nostore(owned_image)
    _nostore(owned_zip)


def test_job_downloads_require_owner(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    job_id = _store_job(_record(), shots=True, tmp_path=tmp_path)
    for kind in ("transcript.txt", "transcript.md", "everything.zip"):
        path = f"/api/jobs/{job_id}/download/{kind}"
        blocked = client.get(path)
        assert blocked.status_code == 403
        assert SECRET not in blocked.text
        _nostore(blocked)
        owned = client.get(path, headers=_headers(OWNER))
        assert owned.status_code == 200, kind
        _nostore(owned)
        if kind == "everything.zip":
            assert owned.content[:2] == b"PK"
        else:
            assert "secret transcript body stays private" in owned.text


def test_share_link_is_readable_without_owner_and_omits_secrets(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    job_id = _store_job(_record(), shots=True, tmp_path=tmp_path)
    assert client.post(f"/api/jobs/{job_id}/share").status_code == 403
    assert client.post(f"/api/jobs/{job_id}/share", headers=_headers(OTHER)).status_code == 403
    created = client.post(f"/api/jobs/{job_id}/share", headers=_headers(OWNER))
    assert created.status_code == 200
    token = created.json()["token"]
    assert created.json()["path"] == f"/r/{token}"
    assert job_id not in created.text

    share = client.get(f"/api/share/{token}")
    assert share.status_code == 200
    body = share.json()["share"]
    assert SECRET in body["transcript"]
    assert body["screenshots"]["frames"][0]["url"].startswith(f"/api/share/{token}/")
    _no_secrets(body, OWNER, job_id)
    assert job_id not in share.text
    text = client.get(f"/api/share/{token}/download/transcript.txt")
    assert text.status_code == 200
    assert SECRET in text.text
    assert OWNER not in text.text
    image = client.get(f"/api/share/{token}/screenshots/{FRAME}")
    assert image.status_code == 200
    assert image.content[:3] == b"\xff\xd8\xff"


def test_wrong_owner_cannot_revoke_and_revoked_share_is_gone(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    job_id = _store_job(_record())
    token = client.post(f"/api/jobs/{job_id}/share", headers=_headers(OWNER)).json()["token"]
    assert client.delete(f"/api/jobs/{job_id}/share", headers=_headers(OTHER)).status_code == 403
    assert client.get(f"/api/share/{token}").status_code == 200
    revoked = client.delete(f"/api/jobs/{job_id}/share", headers=_headers(OWNER))
    assert revoked.status_code == 200
    assert revoked.json()["revoked"] == 1
    _nostore(revoked)
    assert client.get(f"/api/share/{token}").status_code == 404
    assert client.get(f"/api/share/{token}/download/transcript.txt").status_code == 404
    page = client.get(f"/r/{token}")
    assert page.status_code == 404
    _nostore(page)
    assert client.get(f"/api/jobs/{job_id}/download/transcript.txt").status_code == 403
    assert SECRET in client.get(f"/api/jobs/{job_id}/download/transcript.txt", headers=_headers(OWNER)).text


def test_deleting_transcript_revokes_share_and_strips_the_job(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    rec = _record()
    job_id = _store_job(rec, shots=True, tmp_path=tmp_path)
    token = client.post(f"/api/jobs/{job_id}/share", headers=_headers(OWNER)).json()["token"]
    assert client.delete(f"/api/transcripts/{rec['id']}").status_code == 403
    assert client.get(f"/api/share/{token}").status_code == 200
    deleted = client.delete(f"/api/transcripts/{rec['id']}", headers=_headers(OWNER))
    assert deleted.status_code == 200
    _nostore(deleted)
    assert client.get(f"/api/share/{token}").status_code == 404
    assert client.get(f"/r/{token}").status_code == 404
    owned = client.get(f"/api/jobs/{job_id}", headers=_headers(OWNER))
    assert owned.status_code == 200
    assert SECRET not in owned.text
    record = owned.json()["job"].get("record") or {}
    assert "transcript" not in record
    assert client.get(f"/api/jobs/{job_id}/screenshots/{FRAME}", headers=_headers(OWNER)).status_code == 404
    assert not (tmp_path / "screenshots" / job_id).exists()


def test_another_owner_gets_a_copy_not_the_original_record(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "phase3_ai_configured", lambda: False)
    client = _client(monkeypatch, tmp_path)
    original = _record()
    copied = app.record_for_owner(original, OTHER)
    assert copied["id"] != original["id"]
    assert copied["owner_token"] == OTHER
    assert copied["transcript"] == original["transcript"]
    assert client.get(f"/api/transcripts/{original['id']}").status_code == 403
    assert client.get(f"/api/transcripts/{original['id']}", headers=_headers(OTHER)).status_code == 403
    assert client.get(f"/api/transcripts/{original['id']}", headers=_headers("short-token")).status_code == 403
    owned = client.get(f"/api/transcripts/{original['id']}", headers=_headers(OWNER))
    assert owned.status_code == 200
    assert SECRET in owned.json()["transcript"]
    _nostore(owned)
    other = client.get(f"/api/transcripts/{copied['id']}", headers=_headers(OTHER))
    assert other.status_code == 200
    assert other.json()["owner_token"] == OTHER
    recent = client.get("/api/recent", headers=_headers(OTHER))
    assert recent.status_code == 200
    _nostore(recent)
    assert recent.json()["items"]
    assert SECRET not in recent.text
    assert "owner_token" not in json.dumps(recent.json())
    assert client.get("/api/recent").json() == {"items": []}
    made = client.post(
        f"/api/analyze/{original['id']}",
        data={"output_type": "executive_summary"},
        headers=_headers(OWNER),
    )
    assert made.status_code == 200
    analysis_id = made.json()["analysis_id"]
    assert client.get(f"/api/analysis/{analysis_id}/download").status_code == 403
    assert client.get(f"/api/analysis/{analysis_id}/download", headers=_headers(OTHER)).status_code == 403
    downloaded = client.get(f"/api/analysis/{analysis_id}/download", headers=_headers(OWNER))
    assert downloaded.status_code == 200
    _nostore(downloaded)
