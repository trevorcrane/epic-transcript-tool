import json
import sqlite3
import time
import uuid
from pathlib import Path

import requests

BASE = "https://epic-transcript.robyncrane.com"
VIDEO_ID = "rwfk91ya81s"
URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
OWNER = "long-proof-" + uuid.uuid4().hex
DB = Path(__file__).resolve().parents[1] / "data" / "transcripts.db"

with sqlite3.connect(DB) as conn:
    conn.execute("DELETE FROM transcripts WHERE media_id=?", (VIDEO_ID,))

started = time.time()
r = requests.post(f"{BASE}/api/transcribe-url-job", data={"url": URL, "owner": OWNER}, timeout=20)
print(json.dumps({"event": "start", "status_code": r.status_code, "elapsed_seconds": round(time.time()-started, 2), "body": r.text[:500]}, ensure_ascii=False), flush=True)
r.raise_for_status()
job_id = r.json()["job"]["id"]
last = None
while True:
    time.sleep(30)
    j = requests.get(f"{BASE}/api/jobs/{job_id}", timeout=20).json()["job"]
    snap = {k: j.get(k) for k in ["status", "stage", "message", "percent", "chunks_done", "chunks_total", "error"] if k in j}
    if snap != last:
        print(json.dumps({"event": "poll", "elapsed_seconds": round(time.time()-started, 2), "job": snap}, ensure_ascii=False), flush=True)
        last = snap
    if j.get("status") in {"done", "error"}:
        rec = j.get("record") or {}
        result = {
            "event": "final",
            "elapsed_seconds": round(time.time()-started, 2),
            "job_status": j.get("status"),
            "job_id": job_id,
            "url": URL,
            "error": j.get("error"),
            "record": {k: rec.get(k) for k in ["id", "title", "method", "language", "duration_seconds", "processing_seconds", "word_count", "segment_count", "cache_hit"]},
            "provider_attempts": rec.get("provider_attempts"),
            "transcript_head": (rec.get("transcript") or "")[:700],
            "transcript_tail": (rec.get("transcript") or "")[-700:],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        raise SystemExit(0 if j.get("status") == "done" else 2)
    if time.time() - started > 7200:
        print(json.dumps({"event": "timeout", "job_id": job_id, "elapsed_seconds": round(time.time()-started, 2)}, ensure_ascii=False), flush=True)
        raise SystemExit(3)
