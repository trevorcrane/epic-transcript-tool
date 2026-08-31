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
    seen_bodies = set()
    for output_type in app.ANALYSIS_OUTPUTS:
        res = client.post(f"/api/analyze/{rec['id']}", data={"output_type": output_type, "question":"What should Trevor do?"}, headers={"X-Transcript-Owner":"owner-token-phase3-abcdefghijklmnopqrstuvwxyz"})
        assert res.status_code == 200, output_type
        text = res.json()["analysis"]
        assert len(text) > 40, output_type
        assert "Transcript evidence" in text or "timestamp" in text.lower() or "[00:" in text, output_type
        body = text.split("## Transcript evidence", 1)[-1]
        assert body not in seen_bodies, output_type
        seen_bodies.add(body)


def test_phase3_create_100_content_assets_returns_100_assets(monkeypatch, tmp_path):
    rec = seed_record(tmp_path, monkeypatch)
    client = TestClient(app.app)
    res = client.post(
        f"/api/analyze/{rec['id']}",
        data={"output_type": "content_assets_100"},
        headers={"X-Transcript-Owner":"owner-token-phase3-abcdefghijklmnopqrstuvwxyz"},
    )
    assert res.status_code == 200
    text = res.json()["analysis"]
    assert "starter map" not in text.lower()
    numbered = [line for line in text.splitlines() if line[:1].isdigit() and ". **" in line]
    assert len(numbered) == 100
    for label in ["Hook", "Short post", "Email subject", "Newsletter angle", "Reel script", "Carousel slide", "Quote card", "CTA", "Objection reply", "Repurpose prompt"]:
        assert label in text


def test_phase3_100_assets_are_finished_diverse_and_cover_long_transcript(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    segments = [
        {
            "start": i * 60,
            "end": i * 60 + 20,
            "text": f"Strategy lesson {i}: build system {i} before selling service {i}, then prove result {i} with a client story.",
        }
        for i in range(90)
    ]
    transcript = "\n".join(f"[{app.seconds_to_timestamp(s['start'])}] {s['text']}" for s in segments)
    rec = app.save_transcript(
        source="Long Sales System Training",
        source_kind="youtube",
        method="native-caption-automatic_captions",
        transcript=transcript,
        duration_seconds=5400,
        processing_seconds=0,
        media_id="long-assets-123",
        source_url="https://youtu.be/longassets123",
        title="Long Sales System Training",
        creator="Tester",
        language="en",
        segments=segments,
        provider_attempts=[],
        owner_token="owner-token-phase3-abcdefghijklmnopqrstuvwxyz",
    )
    client = TestClient(app.app)
    res = client.post(
        f"/api/analyze/{rec['id']}",
        data={"output_type": "content_assets_100"},
        headers={"X-Transcript-Owner":"owner-token-phase3-abcdefghijklmnopqrstuvwxyz"},
    )
    assert res.status_code == 200
    text = res.json()["analysis"]
    numbered = [line for line in text.splitlines() if line[:1].isdigit() and ". **" in line]
    assert len(numbered) == 100
    lower = text.lower()
    for forbidden in ["use `", " use [", " to create:", "create a ", "turn the moment into", "brief a creator"]:
        assert forbidden not in lower
    unique_bodies = {line.split(" - ", 1)[-1] for line in numbered}
    assert len(unique_bodies) >= 90
    covered_indexes = {
        int(match.group(1))
        for line in numbered
        for match in [__import__("re").search(r"Strategy lesson (\d+)", line)]
        if match
    }
    assert len(covered_indexes) >= 45
    assert any(i <= 10 for i in covered_indexes)
    assert any(35 <= i <= 55 for i in covered_indexes)
    assert any(i >= 79 for i in covered_indexes)
    assert "Email subject" in text and "Subject:" in text
    assert "CTA" in text and "Get" in text
    assert "Objection reply" in text and "Reply:" in text


def test_phase3_analysis_can_be_downloaded(monkeypatch, tmp_path):
    rec = seed_record(tmp_path, monkeypatch)
    client = TestClient(app.app)
    made = client.post(f"/api/analyze/{rec['id']}", data={"output_type":"action_items"}, headers={"X-Transcript-Owner":"owner-token-phase3-abcdefghijklmnopqrstuvwxyz"}).json()
    res = client.get(f"/api/analysis/{made['analysis_id']}/download")
    assert res.status_code == 200
    assert "Action" in res.text or "proposal" in res.text


def test_phase3_combined_outputs_can_be_saved_copied_and_downloaded(monkeypatch, tmp_path):
    rec = seed_record(tmp_path, monkeypatch)
    client = TestClient(app.app)
    made = client.post(f"/api/analyze-all/{rec['id']}", headers={"X-Transcript-Owner":"owner-token-phase3-abcdefghijklmnopqrstuvwxyz"})
    assert made.status_code == 200
    data = made.json()
    assert data["output_type"] == "all_outputs"
    assert "# Executive summary" in data["analysis"]
    assert "# Create 100 content assets" in data["analysis"]
    assert "Ask the video" not in data["analysis"]
    assert data["analysis"].count("AI-generated from the transcript") >= 10
    res = client.get(f"/api/analysis/{data['analysis_id']}/download")
    assert res.status_code == 200
    assert "# Executive summary" in res.text
    assert "# Create 100 content assets" in res.text


def test_phase3_long_transcripts_use_beginning_middle_and_end_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    segments = [
        {"start": i * 60, "end": i * 60 + 20, "text": f"Long transcript evidence segment {i}"}
        for i in range(90)
    ]
    transcript = "\n".join(f"[{app.seconds_to_timestamp(s['start'])}] {s['text']}" for s in segments)
    rec = app.save_transcript(
        source="Two Hour Strategy Session",
        source_kind="youtube",
        method="queued-chunked-local-whisper",
        transcript=transcript,
        duration_seconds=5400,
        processing_seconds=0,
        media_id="long-analysis-123",
        source_url="https://youtu.be/longproof123",
        title="Two Hour Strategy Session",
        creator="Tester",
        language="en",
        segments=segments,
        provider_attempts=[],
        owner_token="owner-token-phase3-abcdefghijklmnopqrstuvwxyz",
    )
    client = TestClient(app.app)
    res = client.post(f"/api/analyze/{rec['id']}", data={"output_type":"executive_summary"}, headers={"X-Transcript-Owner":"owner-token-phase3-abcdefghijklmnopqrstuvwxyz"})
    assert res.status_code == 200
    text = res.json()["analysis"]
    assert "Long transcript evidence segment 0" in text
    assert "Long transcript evidence segment 44" in text or "Long transcript evidence segment 45" in text
    assert "Long transcript evidence segment 89" in text


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
