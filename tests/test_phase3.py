import re
import sqlite3

import pytest
from fastapi.testclient import TestClient

import app

OWNER = "owner-token-phase3-abcdefghijklmnopqrstuvwxyz"


def seed_record(tmp_path, monkeypatch, *, source_kind="youtube", source_url="https://youtu.be/analysis123", media_id="analysis123"):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    return app.save_transcript(
        source="Strategy Call",
        source_kind=source_kind,
        method="native-caption-automatic_captions" if source_kind == "youtube" else "seed",
        transcript="[00:00] We need to launch the offer next week.\n[00:10] Trevor should call Len about the client follow up.\n[00:20] The main idea is to turn transcripts into content assets.\n[00:30] Customers object that they do not have time.\n[00:40] Action item: send the proposal by Friday.",
        duration_seconds=45,
        processing_seconds=0,
        media_id=media_id,
        source_url=source_url,
        title="Strategy Call",
        creator="Tester",
        language="en",
        segments=[
            {"start": 0, "end": 9, "text": "We need to launch the offer next week."},
            {"start": 10, "end": 19, "text": "Trevor should call Len about the client follow up."},
            {"start": 20, "end": 29, "text": "The main idea is to turn transcripts into content assets."},
            {"start": 30, "end": 39, "text": "Customers object that they do not have time."},
            {"start": 40, "end": 45, "text": "Action item: send the proposal by Friday."},
        ],
        provider_attempts=[],
        owner_token=OWNER,
    )


def test_phase3_scope_is_streamlined_to_summary_action_items_and_ask():
    assert app.ANALYSIS_OUTPUTS == ["executive_summary", "action_items", "ask_question"]
    assert app.ANALYSIS_LABELS == {
        "executive_summary": "Executive summary",
        "action_items": "Action items",
        "ask_question": "Ask the video",
    }


def test_phase3_streamlined_outputs_do_not_hide_original_transcript(monkeypatch, tmp_path):
    rec = seed_record(tmp_path, monkeypatch)
    client = TestClient(app.app)
    for output_type in app.ANALYSIS_OUTPUTS:
        res = client.post(
            f"/api/analyze/{rec['id']}",
            data={"output_type": output_type, "question": "What quotes should Trevor use?"},
            headers={"X-Transcript-Owner": OWNER},
        )
        assert res.status_code == 200, output_type
        data = res.json()
        assert data["ok"] is True
        assert data["output_type"] == output_type
        assert "AI-generated" not in data["analysis"]
        assert "## Source notes" in data["analysis"]
        assert re.search(r"\[00:\d{2}\]", data["analysis"]), output_type
    reread = client.get(f"/api/transcripts/{rec['id']}", headers={"X-Transcript-Owner": OWNER})
    assert reread.status_code == 200
    assert reread.json()["transcript"].startswith("[00:00] We need")


def test_phase3_retired_outputs_are_not_supported(monkeypatch, tmp_path):
    rec = seed_record(tmp_path, monkeypatch)
    client = TestClient(app.app)
    for output_type in ["main_ideas", "chapters", "best_quotes", "faq", "content_assets_100", "trevor_use"]:
        res = client.post(f"/api/analyze/{rec['id']}", data={"output_type": output_type}, headers={"X-Transcript-Owner": OWNER})
        assert res.status_code == 400
        assert "Unsupported analysis output type" in res.text


def test_phase3_analysis_can_be_downloaded(monkeypatch, tmp_path):
    rec = seed_record(tmp_path, monkeypatch)
    client = TestClient(app.app)
    made = client.post(f"/api/analyze/{rec['id']}", data={"output_type": "action_items"}, headers={"X-Transcript-Owner": OWNER}).json()
    unauth = client.get(f"/api/analysis/{made['analysis_id']}/download")
    assert unauth.status_code == 403
    res = client.get(f"/api/analysis/{made['analysis_id']}/download", headers={"X-Transcript-Owner": OWNER})
    assert res.status_code == 200
    assert "Action" in res.text or "proposal" in res.text


def test_phase3_gemini_only_runs_for_public_youtube_and_never_for_uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    monkeypatch.setenv("GEMINI_API_KEY", "secret-test-key")
    app.init_db()
    called = []

    def fake_gemini(rec, output_type, question=None):
        called.append((rec["source_kind"], output_type, question))
        return "# Gemini output\n\nAI-generated from the transcript with Gemini.\n\n## Transcript evidence\n- [00:00] Public YouTube evidence\n\n## Summary\nUseful Gemini result.\n"

    monkeypatch.setattr(app, "build_gemini_analysis_text", fake_gemini)
    youtube = seed_record(tmp_path, monkeypatch)
    upload = app.save_transcript(
        source="Private Upload",
        source_kind="upload",
        method="seed",
        transcript="[00:00] Private upload evidence",
        duration_seconds=5,
        processing_seconds=0,
        media_id="upload123",
        source_url="upload",
        title="Private Upload",
        creator="Tester",
        language="en",
        segments=[{"start": 0, "end": 5, "text": "Private upload evidence"}],
        provider_attempts=[],
        owner_token=OWNER,
    )
    client = TestClient(app.app)

    for output_type in app.ANALYSIS_OUTPUTS:
        data = {"output_type": output_type}
        if output_type == "ask_question":
            data["question"] = "Quotes?"
        res = client.post(f"/api/analyze/{youtube['id']}", data=data, headers={"X-Transcript-Owner": OWNER})
        assert res.status_code == 200
        assert "Gemini" in res.json()["analysis"]

    ures = client.post(f"/api/analyze/{upload['id']}", data={"output_type": "executive_summary"}, headers={"X-Transcript-Owner": OWNER})
    assert ures.status_code == 200
    assert "Gemini output" not in ures.json()["analysis"]
    assert [row[1] for row in called] == app.ANALYSIS_OUTPUTS
    assert all(row[0] == "youtube" for row in called)


def test_phase3_gemini_quota_and_errors_do_not_expose_key(monkeypatch, tmp_path):
    rec = seed_record(tmp_path, monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "secret-test-key")
    monkeypatch.setenv("PHASE3_GEMINI_DAILY_LIMIT", "0")

    with pytest.raises(app.HTTPException) as exc:
        app.build_gemini_analysis_text(rec, "executive_summary")

    assert exc.value.status_code == 429
    assert "secret-test-key" not in str(exc.value.detail)


def test_phase3_analysis_schema_migrates_existing_partial_table(monkeypatch, tmp_path):
    db_path = tmp_path / "transcripts.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE analyses (id TEXT PRIMARY KEY, created_at TEXT)")
    monkeypatch.setattr(app, "DB_PATH", db_path)

    app.init_db()

    with sqlite3.connect(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(analyses)").fetchall()}
    assert {"transcript_id", "output_type", "question", "analysis", "owner_token"}.issubset(cols)
