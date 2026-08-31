from fastapi.testclient import TestClient

import app


def seed_record(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    return app.save_transcript(
        source="Strategy Call",
        source_kind="upload",
        method="seed",
        transcript="[00:00] We need to launch the offer next week.\n[00:10] Trevor should call Len about the client follow up.\n[00:20] The main idea is to turn transcripts into content assets.\n[00:30] Customers object that they do not have time.\n[00:40] Action item: send the proposal by Friday.",
        duration_seconds=45,
        processing_seconds=0,
        media_id="analysis123",
        source_url="upload",
        title="Strategy Call",
        creator="Tester",
        language="en",
        segments=[
            {"start":0,"end":9,"text":"We need to launch the offer next week."},
            {"start":10,"end":19,"text":"Trevor should call Len about the client follow up."},
            {"start":20,"end":29,"text":"The main idea is to turn transcripts into content assets."},
            {"start":30,"end":39,"text":"Customers object that they do not have time."},
            {"start":40,"end":45,"text":"Action item: send the proposal by Friday."},
        ],
        provider_attempts=[],
        owner_token="owner-token-phase3-abcdefghijklmnopqrstuvwxyz",
    )


def test_phase3_analysis_outputs_do_not_hide_original_transcript(monkeypatch, tmp_path):
    rec = seed_record(tmp_path, monkeypatch)
    client = TestClient(app.app)
    res = client.post(f"/api/analyze/{rec['id']}", data={"output_type":"executive_summary"}, headers={"X-Transcript-Owner":"owner-token-phase3-abcdefghijklmnopqrstuvwxyz"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["output_type"] == "executive_summary"
    assert "[00:00]" in data["analysis"]
    assert "AI-generated" in data["analysis"]
    reread = client.get(f"/api/transcripts/{rec['id']}", headers={"X-Transcript-Owner":"owner-token-phase3-abcdefghijklmnopqrstuvwxyz"})
    assert reread.status_code == 200
    assert reread.json()["transcript"].startswith("[00:00] We need")


def test_phase3_all_declared_outputs_return_useful_text(monkeypatch, tmp_path):
    rec = seed_record(tmp_path, monkeypatch)
    client = TestClient(app.app)
    for output_type in app.ANALYSIS_OUTPUTS:
        res = client.post(f"/api/analyze/{rec['id']}", data={"output_type": output_type, "question":"What should Trevor do?"}, headers={"X-Transcript-Owner":"owner-token-phase3-abcdefghijklmnopqrstuvwxyz"})
        assert res.status_code == 200, output_type
        text = res.json()["analysis"]
        assert len(text) > 40, output_type
        assert "Transcript evidence" in text or "timestamp" in text.lower() or "[00:" in text, output_type


def test_phase3_analysis_can_be_downloaded(monkeypatch, tmp_path):
    rec = seed_record(tmp_path, monkeypatch)
    client = TestClient(app.app)
    made = client.post(f"/api/analyze/{rec['id']}", data={"output_type":"action_items"}, headers={"X-Transcript-Owner":"owner-token-phase3-abcdefghijklmnopqrstuvwxyz"}).json()
    res = client.get(f"/api/analysis/{made['analysis_id']}/download")
    assert res.status_code == 200
    assert "Action" in res.text or "proposal" in res.text


def test_phase3_analysis_schema_migrates_existing_partial_table(monkeypatch, tmp_path):
    import sqlite3
    db_path = tmp_path / "transcripts.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE analyses (id TEXT PRIMARY KEY, created_at TEXT)")
    monkeypatch.setattr(app, "DB_PATH", db_path)

    app.init_db()

    with sqlite3.connect(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(analyses)").fetchall()}
    assert {"transcript_id", "output_type", "question", "analysis", "owner_token"}.issubset(cols)
