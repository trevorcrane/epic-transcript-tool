#!/usr/bin/env python3
"""Long-podcast end-to-end gate (PR fix/long-media-jobs, PR-PLAN section 6).

Starts a background job for a 1h+ podcast, polls it to the end, checks the
transcript, saves an evidence JSON, and deletes the test record.

Usage:
  python scripts/long_podcast_e2e.py BASE_URL [--url U] [--expect-duration S]
      [--min-words N] [--baseline-words N] [--reference FILE] [--out FILE]

Auth: TRANSCRIPT_API_TOKEN from the environment (Bearer). Without it the script
mints a page session via POST /api/session, the same way the public page does.
The token is never printed or written to the evidence file.

Quality gate thresholds mirror the fleet gate in
/workspace/mentor-machine/roast-room/deepen/whisper_common.py:15 (box only):
wpm >= 100, 6-gram loop < 15, token run < 25, glued < 7 per 1k, U+FFFD < 0.5 per 1k.
The non-word ratio needs the box word list, so it is re-checked on the box.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path
from urllib import error, parse, request

DEFAULT_URL = "https://cdn.changelog.com/uploads/podcast/600/the-changelog-600.mp3"
GATE = dict(min_wpm=100, max_loop6=15, max_token_run=25, max_glued_per_k=7.0, max_repl_per_k=0.5, min_words=50)
UA = {"User-Agent": "EPIC long-podcast e2e gate", "Accept": "application/json"}


def _norm(w: str) -> str:
    return re.sub(r"[^a-z']", "", w.lower()).strip("'")


def text_metrics(txt: str, audio_secs: float) -> dict:
    ws = txt.split(); n = len(ws)
    nw = [x for x in (_norm(w) for w in ws) if x]
    grams = collections.Counter(tuple(nw[i:i + 6]) for i in range(len(nw) - 5))
    run = best = 0; prev = None
    for w in nw:
        run = run + 1 if w == prev else 1; best = max(best, run); prev = w
    glued = sum(1 for w in ws if re.search(r"[a-z]{2,}[A-Z][a-z]|[a-zA-Z]\d|\d[a-zA-Z]{2,}", w) and not re.search(r"\d+(st|nd|rd|th|s|k|m|x|K|M|B|am|pm)\b", w))
    return dict(words=n, wpm=round(n / (audio_secs / 60), 1) if audio_secs else None,
                loop6=max(grams.values()) if grams else 0, max_token_run=best,
                glued_per_k=round(1000 * glued / max(1, n), 2), repl_per_k=round(1000 * txt.count("\ufffd") / max(1, n), 2))


def gate_failures(m: dict, audio_secs: float) -> list[str]:
    r = []
    if m["words"] < GATE["min_words"]: r.append(f"only {m['words']} words")
    if audio_secs and audio_secs > 120 and (m["wpm"] or 0) < GATE["min_wpm"]: r.append(f"wpm {m['wpm']} < {GATE['min_wpm']}")
    if m["loop6"] >= GATE["max_loop6"] or m["max_token_run"] >= GATE["max_token_run"]: r.append("hallucination loop")
    if m["glued_per_k"] >= GATE["max_glued_per_k"]: r.append("glued tokens")
    if m["repl_per_k"] >= GATE["max_repl_per_k"]: r.append("U+FFFD chars")
    return r


def recall(txt: str, reference: str) -> tuple[float, int]:
    reference = re.sub(r"\*\*[^*]+:\*\*", "", reference)
    tok = lambda s: re.findall(r"[a-z']+", s.lower())
    counts = collections.Counter(w for w in tok(reference) if len(w) >= 6)
    keys = {w for w, c in counts.items() if c >= 3}
    have = set(tok(txt))
    return (round(len(keys & have) / len(keys), 3) if keys else 0.0), len(keys)


def segment_checks(segs: list[dict], duration: float) -> dict:
    starts = [float(s.get("start", 0)) for s in segs]
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    return dict(segments=len(segs), last_segment_start=round(starts[-1], 1) if starts else None,
                max_gap_seconds=round(max(gaps), 1) if gaps else None,
                timestamps_increase=all(g >= 0 for g in gaps))


def evaluate(job: dict, *, expect_duration: float | None, min_words: int, min_last_start: float | None,
             max_gap: float, reference: str | None, min_recall: float, baseline_words: int | None) -> dict:
    rec = job.get("record") or {}
    txt = re.sub(r"^\[\d{1,2}:\d{2}(?::\d{2})?\]\s*", "", rec.get("transcript") or "", flags=re.M)
    duration = float(rec.get("duration_seconds") or expect_duration or 0)
    m = text_metrics(txt, duration)
    seg = segment_checks(rec.get("segments") or [], duration)
    checks = {
        "job_done": job.get("status") == "done",
        "method_chunked": rec.get("method") == "chunked-local-whisper",
        "duration_matches": (expect_duration is None) or abs(duration - expect_duration) <= 5,
        "min_words": m["words"] >= min_words,
        "quality_gate": not gate_failures(m, duration),
        "reaches_end": seg["last_segment_start"] is not None and seg["last_segment_start"] >= (min_last_start if min_last_start is not None else duration - 150),
        "no_long_gaps": seg["max_gap_seconds"] is not None and seg["max_gap_seconds"] <= max_gap,
        "timestamps_increase": seg["timestamps_increase"],
    }
    out = {"metrics": m, "gate_failures": gate_failures(m, duration), "segments": seg, "duration_seconds": duration}
    if reference:
        r, keys = recall(txt, reference)
        out["recall"] = r; out["recall_keys"] = keys
        checks["recall"] = r >= min_recall
    if baseline_words:
        out["baseline_words"] = baseline_words
        out["words_vs_baseline"] = round(m["words"] / baseline_words, 3)
    out["checks"] = checks
    out["pass"] = all(checks.values())
    return out


def http(method: str, url: str, headers: dict, data: dict | None = None, timeout: int = 60) -> tuple[int, dict]:
    body = parse.urlencode(data).encode() if data is not None else None
    h = {**UA, **headers}
    if data is not None:
        h["Content-Type"] = "application/x-www-form-urlencoded"
    req = request.Request(url, data=body, headers=h, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except Exception:
            return exc.code, {}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--expect-duration", type=float, default=4323.9)
    ap.add_argument("--min-words", type=int, default=11900)
    ap.add_argument("--baseline-words", type=int, default=14892)
    ap.add_argument("--min-last-start", type=float, default=None)
    ap.add_argument("--max-gap", type=float, default=120)
    ap.add_argument("--reference", default=None)
    ap.add_argument("--min-recall", type=float, default=0.90)
    ap.add_argument("--max-wait", type=int, default=14400)
    ap.add_argument("--out", default=None)
    ap.add_argument("--keep-record", action="store_true")
    a = ap.parse_args(argv)
    base = a.base.rstrip("/")
    token = (os.getenv("TRANSCRIPT_API_TOKEN") or "").strip()
    if token:
        headers = {"Authorization": f"Bearer {token}"}; auth = "token"
    else:
        st, data = http("POST", f"{base}/api/session", {})
        if st != 200:
            print(json.dumps({"event": "session_failed", "status": st})); return 1
        headers = {"X-Transcript-Session": data["session"]}; auth = "page-session"
    owner = "e2e-" + secrets.token_hex(20)
    t0 = time.time()
    st, data = http("POST", f"{base}/api/transcribe-url-job", headers, {"url": a.url, "owner": owner})
    if st != 202:
        print(json.dumps({"event": "start_failed", "status": st, "detail": data.get("detail")})); return 1
    job_id = data["job"]["id"]
    print(json.dumps({"event": "started", "job_id": job_id, "auth": auth}), flush=True)
    job, last_msg = {}, None
    while time.time() - t0 < a.max_wait:
        time.sleep(3 if time.time() - t0 < 60 else 10)
        st, data = http("GET", f"{base}/api/jobs/{job_id}", headers, timeout=30)
        if st != 200:
            continue
        job = data.get("job") or {}
        if job.get("message") != last_msg:
            last_msg = job.get("message")
            print(json.dumps({"event": "progress", "elapsed_s": round(time.time() - t0), "status": job.get("status"), "message": last_msg}), flush=True)
        if job.get("status") in {"done", "error"}:
            break
    wall = round(time.time() - t0, 1)
    reference = Path(a.reference).read_text(encoding="utf-8", errors="ignore") if a.reference else None
    result = evaluate(job, expect_duration=a.expect_duration, min_words=a.min_words, min_last_start=a.min_last_start,
                      max_gap=a.max_gap, reference=reference, min_recall=a.min_recall, baseline_words=a.baseline_words)
    rec = job.get("record") or {}
    evidence = {
        "base_url": base, "source_url": a.url, "job_id": job_id, "auth": auth,
        "status": job.get("status"), "error": job.get("error"),
        "record_id": rec.get("id"), "method": rec.get("method"), "title": rec.get("title"),
        "processing_seconds": rec.get("processing_seconds"), "wall_seconds": wall,
        "started_at_epoch": round(t0, 1), **result,
    }
    if rec.get("id") and not a.keep_record:
        st, _ = http("DELETE", f"{base}/api/transcripts/{rec['id']}", {"X-Transcript-Owner": owner})
        evidence["test_record_deleted"] = st == 200
    text = json.dumps(evidence, indent=1, ensure_ascii=False)
    if token:
        text = text.replace(token, "[redacted]")
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
