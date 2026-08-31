import re

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


def test_phase3_each_output_uses_timestamped_transcript_citations(monkeypatch, tmp_path):
    rec = seed_record(tmp_path, monkeypatch)
    client = TestClient(app.app)
    transcript_stamps = {int(seg["start"]) for seg in rec["segments"]}
    stamp_re = re.compile(r"\[(\d{2}):(\d{2})(?::(\d{2}))?\]")

    def to_seconds(match):
        a, b, c = match.groups()
        return int(a) * 60 + int(b) if c is None else int(a) * 3600 + int(b) * 60 + int(c)

    for output_type in app.ANALYSIS_OUTPUTS:
        res = client.post(
            f"/api/analyze/{rec['id']}",
            data={"output_type": output_type, "question": "What should Trevor do?"},
            headers={"X-Transcript-Owner":"owner-token-phase3-abcdefghijklmnopqrstuvwxyz"},
        )
        assert res.status_code == 200, output_type
        text = res.json()["analysis"]
        citations = [to_seconds(match) for match in stamp_re.finditer(text)]
        assert citations, output_type
        assert any(ts in transcript_stamps for ts in citations), output_type
        assert "AI-generated from the transcript" in text, output_type


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
    for forbidden in ["use `", " use [", " to create:", "create a ", "turn the moment into", "brief a creator", "lead with", "use this as", "shape this", "shape the source", "the story starts with", "fix that moment", "lead with this transcript moment", "use this as the main point", "open by repeating", "teach this moment", "summarize this moment", "play this timestamp", "headline from source", "source idea"]:
        assert forbidden not in lower
    unique_bodies = {line.split(" - ", 1)[-1] for line in numbered}
    assert len(unique_bodies) >= 90
    bodies = [line.split(" - ", 1)[-1] for line in numbered]
    for label in ["Hook", "Short post", "Reel script", "Carousel slide", "CTA", "Objection reply", "Repurpose prompt"]:
        subset = [line.split(" - ", 1)[-1] for line in numbered if f"**{label}" in line]
        stems = {" ".join(body.lower().split()[:7]) for body in subset}
        assert len(stems) == len(subset)
    repeated_sentence_frames = {}
    for body in bodies:
        first_sentence = body.split(".", 1)[0].lower().strip(" “”\"")
        repeated_sentence_frames[first_sentence] = repeated_sentence_frames.get(first_sentence, 0) + 1
    assert max(repeated_sentence_frames.values()) <= 3
    timestamps = []
    for line in numbered:
        for match in __import__("re").finditer(r"\[(\d{2}):(\d{2})(?::(\d{2}))?\]", line):
            a, b, c = match.groups()
            timestamps.append(int(a) * 60 + int(b) if c is None else int(a) * 3600 + int(b) * 60 + int(c))
    assert len(timestamps) == 100
    assert sum(1 for ts in timestamps if ts <= 900) >= 10
    assert sum(1 for ts in timestamps if 1800 <= ts <= 3600) >= 10
    assert sum(1 for ts in timestamps if ts >= 4500) >= 10
    assert "Source excerpt:" in text
    assert "Strategy lesson" in text
    assert "Email subject" in text and "Subject:" in text
    assert "CTA" in text and "Get" in text
    assert "Objection reply" in text and "Reply:" in text
    quote_cards = [line for line in numbered if "**Quote card" in line]
    assert quote_cards
    assert all("“" not in line and "”" not in line for line in quote_cards)
    repurpose = [line for line in numbered if "**Repurpose prompt" in line]
    assert repurpose
    assert all("LinkedIn" in line and "Email" in line and "Clip" in line for line in repurpose)
    hooks = [line for line in numbered if "**Hook" in line]
    hook_stems = {line.split(":", 1)[0] for line in hooks}
    assert len(hook_stems) == 10
    subjects = [line for line in numbered if "**Email subject" in line]
    subject_stems = {line.split("Subject:", 1)[1].split(" - ", 1)[0].strip() for line in subjects}
    assert len(subject_stems) == 10
    assert all(len(line.split("Subject:", 1)[1].split("Source excerpt:", 1)[0].strip().split()) >= 6 for line in subjects)
    hooks = [line for line in numbered if "**Hook" in line]
    assert all("Source excerpt:" in line and line.split(" - ", 1)[1].split("Source excerpt:", 1)[0].strip().endswith((".", "?", "!")) for line in hooks)
    repeated_shells = [
        "stop losing the lesson hiding in plain sight",
        "the practical takeaway is this",
        "fix that moment before adding another layer",
        "the part worth fixing now",
        "the story starts with this proof point",
        "start with the visible proof point",
        "apply this lesson before adding another disconnected step",
        "make the operating lesson clear in one visual step",
    ]
    for shell in repeated_shells:
        assert lower.count(shell) <= 2
    for label in ["Hook", "Short post", "Email subject", "Newsletter angle", "Reel script", "Carousel slide", "Quote card", "CTA", "Objection reply", "Repurpose prompt"]:
        subset = [line.split(" - ", 1)[-1] for line in numbered if f"**{label}" in line]
        openings = {}
        endings = {}
        for body in subset:
            asset_prose = body.split("Source excerpt:", 1)[0].strip().lower()
            normalized_words = __import__("re").sub(r"[^a-z0-9 ]+", " ", asset_prose).split()
            opening = " ".join(normalized_words[:5])
            ending = " ".join(normalized_words[-7:])
            openings[opening] = openings.get(opening, 0) + 1
            endings[ending] = endings.get(ending, 0) + 1
            assert len(normalized_words) >= 8
            assert asset_prose.endswith((".", "?", "!"))
        assert max(openings.values()) == 1
        assert max(endings.values()) <= 2


def test_phase3_100_assets_do_not_attach_unrelated_claims_to_citations(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "transcripts.db")
    app.init_db()
    segments = [
        {"start": i * 15, "end": i * 15 + 10, "text": f"Segment {i} says zebra alpha {i} and orchard beta {i} only."}
        for i in range(120)
    ]
    transcript = "\n".join(f"[{app.seconds_to_timestamp(s['start'])}] {s['text']}" for s in segments)
    rec = app.save_transcript(
        source="Grounding Test",
        source_kind="youtube",
        method="native-caption-automatic_captions",
        transcript=transcript,
        duration_seconds=1800,
        processing_seconds=0,
        media_id="grounding-assets-123",
        source_url="https://youtu.be/grounding123",
        title="Grounding Test",
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
    forbidden_unrelated = ["local business", "speed-to-lead", "follow-up machine", "enterprise value", "missed leads", "valuation"]
    assert not any(term in text.lower() for term in forbidden_unrelated)
    for line in numbered:
        assert "zebra alpha" in line and "orchard beta" in line
        assert "Source excerpt:" in line


def test_phase3_analysis_can_be_downloaded(monkeypatch, tmp_path):
    rec = seed_record(tmp_path, monkeypatch)
    client = TestClient(app.app)
    made = client.post(f"/api/analyze/{rec['id']}", data={"output_type":"action_items"}, headers={"X-Transcript-Owner":"owner-token-phase3-abcdefghijklmnopqrstuvwxyz"}).json()
    unauth = client.get(f"/api/analysis/{made['analysis_id']}/download")
    assert unauth.status_code == 403
    res = client.get(f"/api/analysis/{made['analysis_id']}/download", headers={"X-Transcript-Owner":"owner-token-phase3-abcdefghijklmnopqrstuvwxyz"})
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
    res = client.get(f"/api/analysis/{data['analysis_id']}/download", headers={"X-Transcript-Owner":"owner-token-phase3-abcdefghijklmnopqrstuvwxyz"})
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
