#!/usr/bin/env python3
"""Fresh public quality gate for Phase 3 content_assets_100."""
from __future__ import annotations

import json
import re
import secrets
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "https://epic-transcript.robyncrane.com"
VIDEO = sys.argv[2] if len(sys.argv) > 2 else "https://youtu.be/v34Eg12mhDM?si=lqfq-8bhlxADDZdD"
OWNER = "phase3-assets-quality-" + secrets.token_hex(12)
UA = "Mozilla/5.0 Epic Transcript Phase3 Assets Quality Smoke"
OUT = Path("evidence/phase3-100-assets-quality-report.json")
RESPONSE_OUT = Path("evidence/phase3-100-assets-quality-response.md")


def post(path: str, data: dict[str, str], headers: dict[str, str] | None = None, timeout: int = 120):
    h = {"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(BASE + path, data=urllib.parse.urlencode(data).encode(), headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.status, json.loads(res.read().decode())


def get(path: str, headers: dict[str, str] | None = None, timeout: int = 120):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(BASE + path, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.status, res.read(), dict(res.headers)


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def ts_seconds(ts: str) -> int:
    parts = [int(p) for p in ts.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def main() -> int:
    started = time.monotonic()
    status, start = post("/api/transcribe-url-job", {"url": VIDEO, "owner": OWNER})
    require(status == 202 and start.get("job", {}).get("id"), f"job start failed {status}: {start}")
    job_id = start["job"]["id"]
    job = start["job"]
    for _ in range(120):
        if job.get("status") in {"done", "error"}:
            break
        time.sleep(1)
        _, body, _ = get(f"/api/jobs/{job_id}")
        job = json.loads(body.decode()).get("job", {})
    require(job.get("status") == "done", f"transcript job failed: {job}")
    rec = job["record"]
    owner = rec.get("owner_token") or OWNER
    status, analysis = post(
        f"/api/analyze/{rec['id']}",
        {"output_type": "content_assets_100"},
        headers={"X-Transcript-Owner": owner},
        timeout=120,
    )
    require(status == 200 and analysis.get("ok"), f"analysis failed {status}: {analysis}")
    text = analysis.get("analysis") or ""
    numbered = [line for line in text.splitlines() if re.match(r"^\d+\. \*\*", line)]
    require(len(numbered) == 100, f"expected 100 numbered assets, got {len(numbered)}")
    lower = text.lower()
    forbidden = ["use `", " use [", " to create:", "starter map", "brief a creator", "turn the moment into", "lead with", "use this as", "shape this", "shape the source", "the story starts with", "fix that moment", "open by repeating", "teach this moment", "summarize this moment", "play this timestamp", "headline from source"]
    offenders = [term for term in forbidden if term in lower]
    require(not offenders, f"placeholder phrasing present: {offenders}")
    bodies = [line.split(" - ", 1)[-1] for line in numbered]
    unique = len(set(bodies))
    require(unique >= 90, f"too repetitive: {unique} unique bodies")
    duplicate_stems: dict[str, list[str]] = {}
    for label in ["Hook", "Short post", "Reel script", "Carousel slide", "CTA", "Objection reply", "Repurpose prompt"]:
        subset = [line.split(" - ", 1)[-1] for line in numbered if f"**{label}" in line]
        stems: dict[str, int] = {}
        for body in subset:
            stem = " ".join(body.lower().split()[:7])
            stems[stem] = stems.get(stem, 0) + 1
        dup = [stem for stem, count in stems.items() if count > 1]
        if dup:
            duplicate_stems[label] = dup
    require(not duplicate_stems, f"repeated prefix/template stems: {duplicate_stems}")
    first_sentence_counts: dict[str, int] = {}
    for body in bodies:
        first_sentence = body.split(".", 1)[0].lower().strip(" “”\"")
        first_sentence_counts[first_sentence] = first_sentence_counts.get(first_sentence, 0) + 1
    max_sentence_frame_repeat = max(first_sentence_counts.values())
    require(max_sentence_frame_repeat <= 3, f"sentence frame repeated too often: {max_sentence_frame_repeat}")
    repeated_shells = [
        "stop losing the lesson hiding in plain sight",
        "the practical takeaway is this",
        "fix that moment before adding another layer",
        "the part worth fixing now",
        "the story starts with this proof point",
        "start with the visible proof point",
    ]
    shell_counts = {shell: lower.count(shell) for shell in repeated_shells if lower.count(shell) > 2}
    require(not shell_counts, f"repeated live-output shells: {shell_counts}")
    repeated_batch_patterns = {}
    for label in ["Hook", "Short post", "Email subject", "Newsletter angle", "Reel script", "Carousel slide", "Quote card", "CTA", "Objection reply", "Repurpose prompt"]:
        subset = [line.split(" - ", 1)[-1] for line in numbered if f"**{label}" in line]
        openings = {}
        endings = {}
        too_short = 0
        incomplete = 0
        for body in subset:
            asset_prose = body.split("Source excerpt:", 1)[0].strip().lower()
            words = re.sub(r"[^a-z0-9 ]+", " ", asset_prose).split()
            if len(words) < 8:
                too_short += 1
            if not asset_prose.endswith((".", "?", "!")):
                incomplete += 1
            openings[" ".join(words[:5])] = openings.get(" ".join(words[:5]), 0) + 1
            endings[" ".join(words[-7:])] = endings.get(" ".join(words[-7:]), 0) + 1
        bad_openings = {k:v for k,v in openings.items() if v > 1}
        bad_endings = {k:v for k,v in endings.items() if v > 2}
        if bad_openings or bad_endings or too_short or incomplete:
            repeated_batch_patterns[label] = {"openings": bad_openings, "endings": bad_endings, "too_short": too_short, "incomplete": incomplete}
    require(not repeated_batch_patterns, f"batch template repetition/incomplete prose: {repeated_batch_patterns}")
    quote_cards = [line for line in numbered if "**Quote card" in line]
    require(bool(quote_cards) and all("“" not in line and "”" not in line for line in quote_cards), "quote cards contain invented quote formatting")
    repurpose = [line for line in numbered if "**Repurpose prompt" in line]
    require(bool(repurpose) and all("LinkedIn" in line and "Email" in line and "Clip" in line for line in repurpose), "repurpose prompts are not finished multi-channel assets")
    timestamps = [ts_seconds(m.group(1)) for line in numbered for m in re.finditer(r"\[(\d{2}:\d{2}(?::\d{2})?)\]", line)]
    require(len(timestamps) >= 90, f"too few timestamped assets: {len(timestamps)}")
    duration = rec.get("duration_seconds") or max(timestamps)
    early = sum(1 for ts in timestamps if ts <= duration * 0.25)
    middle = sum(1 for ts in timestamps if duration * 0.35 <= ts <= duration * 0.65)
    late = sum(1 for ts in timestamps if ts >= duration * 0.75)
    require(early >= 10 and middle >= 10 and late >= 10, f"coverage too narrow: early={early} middle={middle} late={late} duration={duration}")
    labels = ["Hook", "Short post", "Email subject", "Newsletter angle", "Reel script", "Carousel slide", "Quote card", "CTA", "Objection reply", "Repurpose prompt"]
    missing_labels = [label for label in labels if label not in text]
    require(not missing_labels, f"missing labels: {missing_labels}")
    report = {
        "ok": True,
        "base": BASE,
        "video_url": VIDEO,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "record": {
            "id": rec.get("id"),
            "title": rec.get("title"),
            "method": rec.get("method"),
            "language": rec.get("language"),
            "word_count": rec.get("word_count"),
            "segment_count": rec.get("segment_count") or len(rec.get("segments") or []),
            "duration_seconds": duration,
            "cache_hit": rec.get("cache_hit"),
        },
        "analysis_id": analysis.get("analysis_id"),
        "output_type": analysis.get("output_type"),
        "analysis_chars": len(text),
        "asset_count": len(numbered),
        "unique_asset_bodies": unique,
        "timestamped_asset_count": len(timestamps),
        "max_sentence_frame_repeat": max_sentence_frame_repeat,
        "coverage": {"early": early, "middle": middle, "late": late, "earliest_seconds": min(timestamps), "latest_seconds": max(timestamps)},
        "no_placeholder_phrasing": True,
        "no_invented_quote_cards": True,
        "no_repeated_prefix_stems": True,
        "repurpose_are_finished_multi_channel_assets": True,
        "no_repeated_live_output_shells": True,
        "batch_prefix_suffix_diversity": True,
        "sample_first_10": numbered[:10],
        "sample_middle_10": numbered[45:55],
        "sample_last_10": numbered[-10:],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    RESPONSE_OUT.write_text(text, encoding="utf-8")
    report["full_response_path"] = str(RESPONSE_OUT)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
