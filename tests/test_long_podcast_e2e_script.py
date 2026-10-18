"""Offline checks of scripts/long_podcast_e2e.py pass rules (no network)."""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "long_podcast_e2e.py"
spec = importlib.util.spec_from_file_location("long_podcast_e2e", SCRIPT)
e2e = importlib.util.module_from_spec(spec); spec.loader.exec_module(e2e)


import random

VOCAB = "we talked about the release and how team ships code every week with small careful steps then tested open source data people build tools write ideas listen music change learn".split()
_rng = random.Random(600)
WORDS = [_rng.choice(VOCAB) for _ in range(20000)]  # random order: no 6-gram loops


def job(words, last_start, method="chunked-local-whisper", duration=4323.9, gap=30):
    n = max(1, int(last_start // gap) + 1)
    per = max(1, words // n)
    segs = [{"start": i * gap, "end": i * gap + gap, "text": " ".join(WORDS[(i * per + k) % len(WORDS)] for k in range(per))} for i in range(n)]
    text = "\n".join(s["text"] for s in segs)
    return {"status": "done", "record": {"method": method, "duration_seconds": duration, "segments": segs, "transcript": text}}


def kw(**over):
    base = dict(expect_duration=4323.9, min_words=11900, min_last_start=4200, max_gap=120, reference=None, min_recall=0.9, baseline_words=14892)
    base.update(over); return base


def test_full_transcript_passes():
    out = e2e.evaluate(job(14000, 4290), **kw())
    assert out["pass"], out["checks"]
    assert out["words_vs_baseline"] > 0.9


def test_truncated_transcript_fails_reach_end_and_words():
    out = e2e.evaluate(job(6000, 2000), **kw())
    assert not out["checks"]["reaches_end"] and not out["checks"]["min_words"] and not out["pass"]


def test_wrong_method_and_gap_fail():
    out = e2e.evaluate(job(14000, 4290, method="local-whisper", gap=200), **kw())
    assert not out["checks"]["method_chunked"] and not out["checks"]["no_long_gaps"]


def test_recall_against_reference():
    ref = "**Host:** " + " ".join(["transcription", "podcast", "changelog"] * 5)
    good = {"status": "done", "record": {"method": "chunked-local-whisper", "duration_seconds": 100, "segments": [{"start": 0}], "transcript": "transcription podcast changelog"}}
    r, keys = e2e.recall(good["record"]["transcript"], ref)
    assert keys == 3 and r == 1.0
    assert e2e.recall("nothing here", ref)[0] == 0.0


def test_loop_is_caught_by_gate():
    m = e2e.text_metrics(" ".join(["same six words in a loop"] * 40), 600)
    assert "hallucination loop" in e2e.gate_failures(m, 600)


def test_main_saves_transcript_and_commit(tmp_path, monkeypatch):
    """Reviewer PR-BUILT fix 1: --transcript-out keeps the text and the JSON names the commit."""
    j = job(14000, 4290)
    j["record"]["transcript"] = "\n".join(f"[{i // 60:02d}:{i % 60:02d}] {s['text']}" for i, s in enumerate(j["record"]["segments"]))
    j["record"]["id"] = "rec1"
    calls = []

    def fake_http(method, url, headers, data=None, timeout=60):
        calls.append((method, url))
        if url.endswith("/api/session"):
            return 200, {"session": "s"}
        if url.endswith("/api/transcribe-url-job"):
            return 202, {"job": {"id": "j1"}}
        if "/api/jobs/" in url:
            return 200, {"job": j}
        return 200, {}
    monkeypatch.setattr(e2e, "http", fake_http)
    monkeypatch.setattr(e2e.time, "sleep", lambda s: None)
    monkeypatch.delenv("TRANSCRIPT_API_TOKEN", raising=False)
    out, txt = tmp_path / "ev.json", tmp_path / "t.txt"
    rc = e2e.main(["http://x", "--out", str(out), "--transcript-out", str(txt), "--commit", "abc123", "--min-last-start", "4200"])
    assert rc == 0
    ev = __import__("json").loads(out.read_text())
    assert ev["commit"] == "abc123" and ev["transcript_file"] == str(txt) and ev["pass"]
    plain = txt.read_text()
    assert "[00:" not in plain and len(plain.split()) == ev["metrics"]["words"]
    assert (tmp_path / "t.txt.timestamped.txt").read_text().startswith("[00:00]")
