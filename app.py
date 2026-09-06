"""Epic Transcript Machine - FastAPI backend.

Public, no-login transcript pipeline with YouTube cache, caption fallbacks,
timestamped segments, and downloadable transcript formats.
"""
from __future__ import annotations

import hashlib
import html
import json
import mimetypes
import os
import re
import shutil
import smtplib
import sqlite3
import subprocess
import tempfile
import threading
import time
import secrets
import uuid
from email.message import EmailMessage
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def configured_path(env_name: str, default: Path) -> Path:
    """Return an absolute path from env, preserving safe local defaults."""
    configured = os.getenv(env_name)
    if configured:
        return Path(configured).expanduser().resolve()
    return default


DATA_DIR = configured_path("TRANSCRIPT_DATA_DIR", ROOT / "data")
STATIC_DIR = configured_path("TRANSCRIPT_STATIC_DIR", ROOT / "static")
DB_PATH = DATA_DIR / "transcripts.db"
URL_JOBS_PATH = DATA_DIR / "url_jobs.json"
PHASE3_GEMINI_USAGE_PATH = DATA_DIR / "phase3_gemini_usage.json"
URL_JOBS: dict[str, dict] = {}
URL_JOBS_LOCK = threading.Lock()
PHASE3_GEMINI_USAGE_LOCK = threading.Lock()

DATA_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
TEXT_EXTS = {".txt", ".md"}
SUBTITLE_EXTS = {".srt", ".vtt"}
ALLOWED_EXTS = AUDIO_EXTS | VIDEO_EXTS | TEXT_EXTS | SUBTITLE_EXTS
SUPPORTED_UPLOAD_FORMATS = ", ".join(sorted(ALLOWED_EXTS))
YT_DLP_BINARY_CANDIDATES = [
    Path("/usr/local/bin/yt-dlp"),
    Path("/opt/homebrew/bin/yt-dlp"),
    Path.home() / ".local/bin/yt-dlp",
]
FFMPEG_BINARY_CANDIDATES = [
    Path("/usr/local/bin/ffmpeg"),
    Path("/opt/homebrew/bin/ffmpeg"),
]
WHISPER_BINARY_CANDIDATES = [
    Path("/usr/local/bin/whisper"),
    Path("/opt/homebrew/bin/whisper"),
    Path.home() / ".local/bin/whisper",
]

BLOCKED_MESSAGE = "That video is blocking automatic transcription. If you have the video or audio file, upload it here and we’ll take another route."
PHASE3_GEMINI_PUBLIC_ERROR = "Gemini is not configured for Phase 3 yet. The transcript is safe; ask Trevor to add the server-side Gemini key and retry."
MAX_SYNC_YOUTUBE_DURATION_SECONDS = 2 * 60
LONG_VIDEO_MESSAGE = "That video is too long for this synchronous public request. Upload the file or use the next async processing version so it can run without timing out."
ANALYSIS_OUTPUTS = [
    "executive_summary", "action_items", "ask_question",
]
ANALYSIS_LABELS = {
    "executive_summary": "Executive summary",
    "action_items": "Action items",
    "ask_question": "Ask the video",
}

app = FastAPI(title="Epic Transcript Machine", docs_url=None, redoc_url=None)
DOWNLOAD_TOKENS: dict[str, dict] = {}
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://epic-transcript.robyncrane.com",
        "https://epic-transcript-machine-review.netlify.app",
        "http://localhost:8080",
        "http://localhost:8090",
    ],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-Transcript-Owner"],
)


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _columns(conn: sqlite3.Connection, table: str = "transcripts") -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transcripts (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                source TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                method TEXT NOT NULL,
                transcript TEXT NOT NULL,
                duration_seconds REAL,
                processing_seconds REAL
            )
            """
        )
        needed = {
            "media_id": "TEXT",
            "source_url": "TEXT",
            "title": "TEXT",
            "creator": "TEXT",
            "language": "TEXT",
            "segments_json": "TEXT",
            "word_count": "INTEGER",
            "provider_attempts_json": "TEXT",
            "owner_token": "TEXT",
        }
        existing = _columns(conn)
        for name, ddl in needed.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE transcripts ADD COLUMN {name} {ddl}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_media_id ON transcripts(media_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                transcript_id TEXT NOT NULL,
                output_type TEXT NOT NULL,
                question TEXT,
                analysis TEXT NOT NULL,
                owner_token TEXT NOT NULL,
                FOREIGN KEY(transcript_id) REFERENCES transcripts(id) ON DELETE CASCADE
            )
            """
        )
        analysis_needed = {
            "transcript_id": "TEXT",
            "output_type": "TEXT",
            "question": "TEXT",
            "analysis": "TEXT",
            "owner_token": "TEXT",
        }
        analysis_existing = _columns(conn, "analyses")
        for name, ddl in analysis_needed.items():
            if name not in analysis_existing:
                conn.execute(f"ALTER TABLE analyses ADD COLUMN {name} {ddl}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_analyses_transcript_id ON analyses(transcript_id)")


init_db()


def resolve_binary(name: str, env_name: str, candidates: list[Path]) -> str:
    configured = os.getenv(env_name)
    if configured and Path(configured).exists():
        return configured
    found = shutil.which(name)
    if found:
        return found
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise RuntimeError(f"{name} is not installed on this server/browser path")


def has_binary(name: str, env_name: str, candidates: list[Path]) -> bool:
    try:
        resolve_binary(name, env_name, candidates)
        return True
    except RuntimeError:
        return False


def setup_status() -> dict:
    missing = []
    optional_missing = []
    if not has_binary("yt-dlp", "YT_DLP_BIN", YT_DLP_BINARY_CANDIDATES):
        missing.append("yt-dlp")
    if not has_binary("ffmpeg", "FFMPEG_BIN", FFMPEG_BINARY_CANDIDATES):
        missing.append("ffmpeg")
    # Gemini, SMTP, and local Whisper are optional fallbacks. Missing keys do not block public caption flow.
    smtp_keys = ("OWNER_EMAIL", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS")
    if any(not os.getenv(k) for k in smtp_keys):
        optional_missing.append("SMTP config (Email to Me)")
    if not os.getenv("GEMINI_API_KEY"):
        optional_missing.append("GEMINI_API_KEY")
    return {
        "ready": not missing,
        "missing": missing,
        "optional_missing": optional_missing,
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "local_whisper": has_binary("whisper", "WHISPER_BIN", WHISPER_BINARY_CANDIDATES),
        "owner_email": os.getenv("OWNER_EMAIL", ""),
    }


def clean_whitespace(text: str) -> str:
    text = html.unescape((text or "").replace("\r\n", "\n").replace("\r", "\n"))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_youtube_video_id(value: str) -> Optional[str]:
    value = (value or "").strip()
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", value):
        return value
    try:
        parsed = urlparse(value)
    except Exception:
        return None
    host = (parsed.netloc or "").lower().removeprefix("www.").removeprefix("m.")
    if host in {"youtube.com", "music.youtube.com"}:
        qs = parse_qs(parsed.query)
        if qs.get("v") and re.fullmatch(r"[0-9A-Za-z_-]{11}", qs["v"][0]):
            return qs["v"][0]
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"} and re.fullmatch(r"[0-9A-Za-z_-]{11}", parts[1]):
            return parts[1]
    if host == "youtu.be":
        part = parsed.path.strip("/").split("/")[0]
        if re.fullmatch(r"[0-9A-Za-z_-]{11}", part):
            return part
    return None


def seconds_to_timestamp(seconds: float, comma: bool = False) -> str:
    ms = int(round((float(seconds) - int(float(seconds))) * 1000))
    total = int(float(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    sep = "," if comma else "."
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}" if comma else (f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}")


def parse_timestamp(ts: str) -> float:
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
    else:
        h, m, s = "0", parts[0], parts[1]
    return int(h) * 3600 + int(m) * 60 + float(s)


def _clean_caption_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\{\\.*?\}", "", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_vtt_segments(raw: str) -> list[dict]:
    lines = (raw or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    segments = []
    i = 0
    ts_re = re.compile(r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[\.,]\d{3})\s*-->\s*(?P<end>\d{1,2}:\d{2}(?::\d{2})?[\.,]\d{3})")
    while i < len(lines):
        m = ts_re.search(lines[i])
        if not m and i + 1 < len(lines):
            m = ts_re.search(lines[i + 1])
            if m:
                i += 1
        if not m:
            i += 1
            continue
        start = parse_timestamp(m.group("start"))
        end = parse_timestamp(m.group("end"))
        i += 1
        text_lines = []
        while i < len(lines) and lines[i].strip():
            text_lines.append(lines[i])
            i += 1
        text = _clean_caption_text(" ".join(text_lines))
        if text and (not segments or text != segments[-1]["text"] or start != segments[-1]["start"]):
            segments.append({"start": start, "end": end, "text": text})
        i += 1
    return segments


def parse_srt_segments(raw: str) -> list[dict]:
    blocks = re.split(r"\n\s*\n", (raw or "").replace("\r\n", "\n"))
    out = []
    ts_re = re.compile(r"(?P<start>\d{1,2}:\d{2}:\d{2}[\.,]\d{3})\s*-->\s*(?P<end>\d{1,2}:\d{2}:\d{2}[\.,]\d{3})")
    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        idx = 1 if lines[0].strip().isdigit() and len(lines) > 1 else 0
        m = ts_re.search(lines[idx]) if idx < len(lines) else None
        if not m:
            continue
        text = _clean_caption_text(" ".join(lines[idx + 1:]))
        if text:
            out.append({"start": parse_timestamp(m.group("start")), "end": parse_timestamp(m.group("end")), "text": text})
    return out


def strip_vtt_srt(raw: str) -> str:
    segs = parse_vtt_segments(raw) or parse_srt_segments(raw)
    if segs:
        return "\n".join(s["text"] for s in segs)
    text = re.sub(r"^WEBVTT.*?\n", "", raw or "", flags=re.IGNORECASE)
    text = re.sub(r"\d{1,2}:\d{2}:\d{2}[\.,]\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[\.,]\d{3}.*", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"^\d+\s*$", "", text, flags=re.MULTILINE)
    return clean_whitespace(text)


def remove_leading_word_overlap(previous_text: str, next_text: str, max_words: int = 20) -> str:
    """Trim repeated leading caption words caused by rolling auto-caption windows."""
    prev_words = clean_whitespace(previous_text).split()
    next_words = clean_whitespace(next_text).split()
    if not prev_words or not next_words:
        return clean_whitespace(next_text)
    def norm(words):
        return [w.lower().strip(",.?!;:\"'()[]") for w in words]
    prev_norm = norm(prev_words)
    next_norm = norm(next_words)
    overlap = 0
    for size in range(min(len(prev_norm), len(next_norm), max_words), 0, -1):
        if prev_norm[-size:] == next_norm[:size]:
            overlap = size
            break
    trimmed = next_words[overlap:]
    return clean_whitespace(" ".join(trimmed))


def segments_to_transcript(segments: list[dict]) -> str:
    lines = []
    previous_text = ""
    for seg in segments:
        raw_text = clean_whitespace(seg.get("text", ""))
        if not raw_text:
            continue
        text = remove_leading_word_overlap(previous_text, raw_text)
        previous_text = clean_whitespace((previous_text + " " + text).strip())[-1200:]
        if text:
            lines.append(f"[{seconds_to_timestamp(seg.get('start', 0))}] {text}")
    return "\n".join(lines)


def transcript_word_count(text: str) -> int:
    body = re.sub(r"\[\d{1,2}:\d{2}(?::\d{2})?\]", " ", text or "")
    return len(re.findall(r"\b[\w'’-]+\b", body))


def timestamps_increase(segments: list[dict]) -> bool:
    last = -1.0
    for seg in segments:
        start = float(seg.get("start", -1))
        if start < last:
            return False
        last = start
    return True


def row_to_record(row: sqlite3.Row | dict, cache_hit: bool = False, include_owner_token: bool = True) -> dict:
    r = dict(row)
    segments = json.loads(r.pop("segments_json", "[]") or "[]")
    attempts = json.loads(r.pop("provider_attempts_json", "[]") or "[]")
    if not include_owner_token:
        r.pop("owner_token", None)
    r["segments"] = segments
    if segments:
        rebuilt_transcript = segments_to_transcript(segments)
        if rebuilt_transcript:
            r["transcript"] = rebuilt_transcript
    r["provider_attempts"] = attempts
    r["cache_hit"] = cache_hit
    r["word_count"] = transcript_word_count(r.get("transcript", ""))
    r["segment_count"] = len(segments)
    return r


def public_video_cache_summary(row: sqlite3.Row | dict) -> dict:
    rec = row_to_record(row, include_owner_token=False)
    return {k: rec.get(k) for k in ("id", "created_at", "source", "source_kind", "method", "title", "creator", "language", "word_count", "segment_count", "duration_seconds", "processing_seconds", "media_id", "source_url", "cache_hit")}


def valid_owner_token(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    if len(value) >= 32 and re.fullmatch(r"[0-9A-Za-z._:-]+", value):
        return value
    return None


def require_owner(row: sqlite3.Row | dict, owner: Optional[str]) -> None:
    stored = (dict(row).get("owner_token") or "").strip()
    supplied = valid_owner_token(owner)
    if not stored or not supplied or not secrets.compare_digest(stored, supplied):
        raise HTTPException(403, "This transcript requires its owner link.")


def header_owner(value: Optional[str]) -> Optional[str]:
    return valid_owner_token(value)


def language_base(value: Optional[str]) -> str:
    lang = normalize_caption_language(value)
    return "" if lang == "unknown" else lang.split("-", 1)[0]


def cache_matches_language(row: sqlite3.Row | dict, expected_language: Optional[str]) -> bool:
    expected_base = language_base(expected_language)
    if not expected_base:
        return True
    cached_base = language_base(dict(row).get("language"))
    return cached_base == expected_base


def get_cached_transcript(media_id: str, expected_language: Optional[str] = None) -> Optional[dict]:
    if not media_id:
        return None
    with db() as conn:
        rows = conn.execute("SELECT * FROM transcripts WHERE media_id=? ORDER BY created_at DESC LIMIT 10", (media_id,)).fetchall()
    for row in rows:
        if cache_matches_language(row, expected_language):
            return row_to_record(row, cache_hit=True)
    return None


def record_for_owner(rec: dict, owner_token: str) -> dict:
    if rec.get("owner_token") == owner_token:
        return rec
    return save_transcript(
        source=rec.get("source") or rec.get("title") or "Transcript",
        source_kind=rec.get("source_kind") or "youtube",
        method=rec.get("method") or "cache-copy",
        transcript=rec.get("transcript") or "",
        duration_seconds=rec.get("duration_seconds"),
        processing_seconds=0,
        media_id=rec.get("media_id"),
        source_url=rec.get("source_url"),
        title=rec.get("title") or rec.get("source"),
        creator=rec.get("creator"),
        language=rec.get("language"),
        segments=rec.get("segments") or [],
        provider_attempts=rec.get("provider_attempts") or [],
        cache_hit=True,
        owner_token=owner_token,
    )


def save_transcript(*, source: str, source_kind: str, method: str, transcript: str,
                    duration_seconds: Optional[float], processing_seconds: float,
                    media_id: Optional[str] = None, source_url: Optional[str] = None,
                    title: Optional[str] = None, creator: Optional[str] = None,
                    language: Optional[str] = None, segments: Optional[list[dict]] = None,
                    provider_attempts: Optional[list[dict]] = None, cache_hit: bool = False,
                    owner_token: Optional[str] = None) -> dict:
    init_db()
    rec_id = uuid.uuid4().hex[:12]
    owner_token = valid_owner_token(owner_token) or secrets.token_urlsafe(32)
    segments = segments or []
    word_count = transcript_word_count(transcript)
    with db() as conn:
        conn.execute(
            """
            INSERT INTO transcripts (id, source, source_kind, method, transcript,
                duration_seconds, processing_seconds, media_id, source_url, title,
                creator, language, segments_json, word_count, provider_attempts_json, owner_token)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (rec_id, source, source_kind, method, transcript, duration_seconds,
             processing_seconds, media_id, source_url, title or source, creator,
             normalize_caption_language(language), json.dumps(segments), word_count, json.dumps(provider_attempts or []), owner_token),
        )
        row = conn.execute("SELECT * FROM transcripts WHERE id=?", (rec_id,)).fetchone()
    return row_to_record(row, cache_hit=cache_hit)


def yt_dlp_metadata(url: str) -> dict:
    proc = subprocess.run([resolve_binary("yt-dlp", "YT_DLP_BIN", YT_DLP_BINARY_CANDIDATES), "--dump-single-json", "--no-warnings", url], capture_output=True, text=True, timeout=90)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip().splitlines()[-1] if proc.stderr else "yt-dlp failed")
    return json.loads(proc.stdout)


WHISPER_LANGUAGE_NAMES = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de", "italian": "it",
    "portuguese": "pt", "korean": "ko", "japanese": "ja", "chinese": "zh", "dutch": "nl",
}

def detected_whisper_language(stdout: str, stderr: str = "") -> Optional[str]:
    text = f"{stdout or ''}\n{stderr or ''}"
    match = re.search(r"Detected language:\s*([^\n]+)", text, re.IGNORECASE)
    if not match:
        return None
    name = match.group(1).strip().lower()
    return WHISPER_LANGUAGE_NAMES.get(name, normalize_caption_language(name))

def normalize_caption_language(lang: Optional[str]) -> str:
    lang = (lang or "unknown").strip()
    if not lang:
        return "unknown"
    lang = lang.replace("_", "-")
    if lang.endswith("-orig"):
        lang = lang[:-5]
    parts = lang.split("-")
    if len(parts) >= 2 and len(parts[1]) == 2 and parts[1].isalpha():
        return f"{parts[0].lower()}-{parts[1].upper()}"
    return parts[0].lower()


def _caption_candidates(meta: dict) -> list[dict]:
    source_lang = normalize_caption_language(meta.get("language") or meta.get("original_language") or meta.get("default_language"))
    source_base = source_lang.split("-", 1)[0] if source_lang != "unknown" else ""
    tracks = []
    for kind in ("subtitles", "automatic_captions"):
        for lang, entries in (meta.get(kind) or {}).items():
            clean_lang = normalize_caption_language(lang)
            base = clean_lang.split("-", 1)[0]
            raw_is_clean = lang == clean_lang or lang == base
            for entry in entries or []:
                if entry.get("url") and (entry.get("ext") in {"vtt", "srt", "json3"}):
                    score = 0
                    if source_base and base == source_base:
                        score -= 100
                    elif not source_base and kind == "subtitles" and base != "en" and raw_is_clean:
                        score -= 25
                    elif base == "en":
                        score -= 10
                    if kind == "subtitles":
                        score -= 5
                    if lang.endswith("-orig"):
                        score -= 2
                    tracks.append({"kind": kind, "lang": clean_lang, "raw_lang": lang, "url": entry["url"], "ext": entry.get("ext"), "score": score})
    return sorted(tracks, key=lambda x: (x["score"], x["lang"], x["ext"] != "vtt"))


def infer_expected_language(meta: dict) -> Optional[str]:
    explicit = meta.get("language") or meta.get("original_language") or meta.get("default_language")
    if explicit:
        return normalize_caption_language(explicit)
    candidates = _caption_candidates(meta)
    return candidates[0]["lang"] if candidates else None


def fetch_caption_url_segments(meta: dict) -> tuple[list[dict], str, str]:
    import requests
    for track in _caption_candidates(meta)[:6]:
        try:
            resp = requests.get(track["url"], timeout=8)
            if resp.status_code != 200 or not resp.text.strip():
                continue
            if track["ext"] == "srt":
                segs = parse_srt_segments(resp.text)
            else:
                segs = parse_vtt_segments(resp.text)
            if segs:
                return segs, track["lang"], f"native-caption-{track['kind']}"
        except Exception:
            continue
    raise RuntimeError("No usable native caption track found")


def youtube_transcript_api_segments(video_id: str) -> tuple[list[dict], str]:
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    fetched = api.fetch(video_id)
    segments = []
    for item in fetched:
        start = float(getattr(item, "start", item.get("start", 0) if isinstance(item, dict) else 0))
        dur = float(getattr(item, "duration", item.get("duration", 0) if isinstance(item, dict) else 0))
        text = getattr(item, "text", item.get("text", "") if isinstance(item, dict) else "")
        clean = _clean_caption_text(text)
        if clean:
            segments.append({"start": start, "end": start + dur, "text": clean})
    return segments, getattr(fetched, "language_code", None) or "unknown"


def yt_dlp_grab_caption_segments(url: str, work_dir: Path, language: Optional[str] = None) -> tuple[list[dict], str]:
    out_template = str(work_dir / "captions.%(ext)s")
    base = language_base(language)
    sub_langs = f"{base}-orig,{base}" if base else "all"
    cmd = [resolve_binary("yt-dlp", "YT_DLP_BIN", YT_DLP_BINARY_CANDIDATES), "--no-warnings", "--skip-download", "--write-sub", "--write-auto-sub", "--sub-format", "vtt/srt/best", "--sub-langs", sub_langs, "-o", out_template, url]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=12)
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp subtitle extraction timed out")
    candidates = list(work_dir.glob("captions*.vtt")) + list(work_dir.glob("captions*.srt"))
    if not candidates:
        raise RuntimeError("yt-dlp found no captions")
    def rank(p: Path) -> tuple:
        n = p.name
        return (0 if ".en" in n else 1, 0 if n.endswith(".vtt") else 1, len(n))
    candidates.sort(key=rank)
    raw = candidates[0].read_text(errors="ignore")
    segs = parse_vtt_segments(raw) if candidates[0].suffix == ".vtt" else parse_srt_segments(raw)
    if not segs:
        raise RuntimeError("yt-dlp captions parsed empty")
    lang_match = re.search(r"captions\.([^.]+)", candidates[0].name)
    return segs, (lang_match.group(1) if lang_match else "unknown")


def transcribe_with_gemini_youtube(url: str) -> tuple[list[dict], str]:
    # Optional hook. Kept off unless key is configured, and only used after free caption providers fail.
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY not configured")
    raise RuntimeError("Gemini YouTube transcription hook not enabled in this build")


def yt_dlp_download_audio(url: str, work_dir: Path) -> Path:
    out_template = str(work_dir / "audio.%(ext)s")
    base_cmd = [resolve_binary("yt-dlp", "YT_DLP_BIN", YT_DLP_BINARY_CANDIDATES), "--ffmpeg-location", str(Path(resolve_binary("ffmpeg", "FFMPEG_BIN", FFMPEG_BINARY_CANDIDATES)).parent), "--no-warnings", "-f", "bestaudio/best", "-x", "--audio-format", "mp3", "--audio-quality", "5", "-o", out_template]
    variants = [[], ["--extractor-args", "youtube:player_client=android"]]
    errors = []
    for extra in variants:
        for old in work_dir.glob("audio.*"):
            old.unlink(missing_ok=True)
        cmd = base_cmd + extra + [url]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=int(os.getenv("YT_DLP_AUDIO_TIMEOUT_SECONDS", "45")))
        except subprocess.TimeoutExpired:
            errors.append("audio download timed out")
            continue
        if proc.returncode == 0:
            matches = sorted(work_dir.glob("audio.*"))
            if matches:
                return matches[0]
            errors.append("Audio download completed but no file was created.")
        else:
            errors.append(proc.stderr.strip().splitlines()[-1] if proc.stderr else "Audio download failed.")
    raise RuntimeError(errors[-1] if errors else "Audio download failed.")


def resolve_whisper_binary() -> str:
    return resolve_binary("whisper", "WHISPER_BIN", WHISPER_BINARY_CANDIDATES)


def media_duration_seconds(path: Path) -> Optional[float]:
    """Return media duration via ffprobe when available, without blocking upload transcription."""
    try:
        ffmpeg_path = Path(resolve_binary("ffmpeg", "FFMPEG_BIN", FFMPEG_BINARY_CANDIDATES))
        ffprobe = ffmpeg_path.with_name("ffprobe")
        ffprobe_bin = str(ffprobe if ffprobe.exists() else "ffprobe")
        proc = subprocess.run(
            [ffprobe_bin, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode != 0:
            return None
        duration = float((proc.stdout or "").strip().splitlines()[0])
        return round(duration, 3) if duration > 0 else None
    except Exception:
        return None


def parse_whisper_stdout_segments(text: str) -> list[dict]:
    segments = []
    for line in (text or "").splitlines():
        match = re.match(r"\[(\d{2}:\d{2}(?::\d{2})?\.\d{3})\s+-->\s+(\d{2}:\d{2}(?::\d{2})?\.\d{3})\]\s*(.+)", line.strip())
        if not match:
            continue
        start, end, body = match.groups()
        clean = _clean_caption_text(body)
        if clean:
            segments.append({"start": parse_timestamp(start), "end": parse_timestamp(end), "text": clean})
    return segments


def transcribe_with_local_whisper(input_path: Path, language: Optional[str] = None, model: Optional[str] = None, timeout: Optional[int] = None) -> tuple[list[dict], str]:
    whisper_bin = resolve_whisper_binary()
    out_dir = Path(tempfile.mkdtemp(prefix="epic-whisper-out-"))
    cmd = [whisper_bin, str(input_path), "--model", model or os.getenv("LOCAL_WHISPER_MODEL", "base"), "--task", "transcribe", "--output_format", "vtt", "--output_dir", str(out_dir), "--fp16", "False"]
    threads = os.getenv("LOCAL_WHISPER_THREADS")
    if threads:
        cmd += ["--threads", threads]
    if language:
        cmd += ["--language", language]
    env = os.environ.copy()
    ffmpeg_dir = str(Path(resolve_binary("ffmpeg", "FFMPEG_BIN", FFMPEG_BINARY_CANDIDATES)).parent)
    env["PATH"] = ffmpeg_dir + os.pathsep + env.get("PATH", "")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout or int(os.getenv("LOCAL_WHISPER_TIMEOUT_SECONDS", "90")), env=env)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "Local Whisper transcription failed")
    files = list(out_dir.glob("*.vtt"))
    if files:
        segs = parse_vtt_segments(files[0].read_text(errors="ignore"))
        if not segs:
            segs = parse_whisper_stdout_segments(proc.stdout)
    else:
        segs = parse_whisper_stdout_segments(proc.stdout)
    shutil.rmtree(out_dir, ignore_errors=True)
    if not segs:
        file_info = ", ".join(f"{f.name}:{f.stat().st_size}" for f in files[:3]) if files else "no transcript files"
        stdout_hint = (proc.stdout or "").strip().replace("\n", " ")[:180]
        stderr_hint = (proc.stderr or "").strip().replace("\n", " ")[:180]
        raise RuntimeError(f"Local Whisper transcript came back empty ({file_info}; stdout={stdout_hint!r}; stderr={stderr_hint!r})")
    detected_lang = detected_whisper_language(proc.stdout, proc.stderr)
    return segs, language or detected_lang or "unknown"


def youtube_whisper_timeout_seconds(duration: Optional[float]) -> int:
    configured = os.getenv("YOUTUBE_WHISPER_TIMEOUT_SECONDS")
    duration_scaled = max(120, min(1200, int(duration * 2))) if duration and duration > 0 else None
    if configured:
        configured_timeout = int(configured)
        return max(configured_timeout, duration_scaled) if duration_scaled else configured_timeout
    if duration_scaled:
        return duration_scaled
    return int(os.getenv("LOCAL_WHISPER_TIMEOUT_SECONDS", "90"))



def update_url_job(job_id: Optional[str], **fields) -> None:
    if not job_id:
        return
    with URL_JOBS_LOCK:
        if job_id in URL_JOBS:
            URL_JOBS[job_id].update(fields)
            save_url_jobs_locked()


def save_url_jobs_locked() -> None:
    URL_JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = URL_JOBS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(URL_JOBS, ensure_ascii=False), encoding="utf-8")
    tmp.replace(URL_JOBS_PATH)


def load_url_jobs_locked() -> None:
    if not URL_JOBS_PATH.exists():
        return
    try:
        data = json.loads(URL_JOBS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    if isinstance(data, dict):
        URL_JOBS.update({str(k): v for k, v in data.items() if isinstance(v, dict)})


with URL_JOBS_LOCK:
    load_url_jobs_locked()


def visitor_safe_transcription_error(detail: object) -> str:
    text = str(detail or "")
    if BLOCKED_MESSAGE in text:
        return BLOCKED_MESSAGE
    if "Provider trail" in text or "subprocess" in text or "Command '['" in text or "Long-video queued transcription failed" in text:
        return BLOCKED_MESSAGE
    return text


def chunk_segments_by_time(segs: list[dict], chunk_seconds: int = 600) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    for seg in segs:
        idx = int(float(seg.get("start", 0)) // chunk_seconds)
        while len(chunks) <= idx:
            chunks.append([])
        chunks[idx].append(seg)
    return [chunk for chunk in chunks if chunk]


def offset_segments(segs: list[dict], offset: float) -> list[dict]:
    shifted = []
    for seg in segs:
        shifted.append({"start": float(seg.get("start", 0)) + offset, "end": float(seg.get("end", seg.get("start", 0))) + offset, "text": seg.get("text", "")})
    return shifted


def split_audio_for_long_transcription(audio_path: Path, work_dir: Path, chunk_seconds: int) -> list[Path]:
    chunks_dir = work_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    out_template = chunks_dir / "chunk-%04d.wav"
    cmd = [resolve_binary("ffmpeg", "FFMPEG_BIN", FFMPEG_BINARY_CANDIDATES), "-y", "-i", str(audio_path), "-ac", "1", "-ar", "16000", "-f", "segment", "-segment_time", str(chunk_seconds), "-reset_timestamps", "1", str(out_template)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=int(os.getenv("LONG_VIDEO_SPLIT_TIMEOUT_SECONDS", "300")))
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "Audio chunking failed")
    chunks = sorted(chunks_dir.glob("chunk-*.wav"))
    if not chunks:
        raise RuntimeError("Audio chunking produced no chunks")
    return chunks


def transcribe_long_youtube_queued(url: str, video_id: str, started: float, work_dir: Path, owner_token: Optional[str], meta: dict, job_id: Optional[str] = None) -> dict:
    attempts = [{"provider": "metadata", "ok": True, "duration_seconds": meta.get("duration")}]
    title = meta.get("title") or f"YouTube {video_id}"
    creator = meta.get("uploader") or meta.get("channel")
    duration = meta.get("duration")
    canonical = meta.get("webpage_url") or f"https://youtu.be/{video_id}"
    expected_language = infer_expected_language(meta)
    update_url_job(job_id, stage="captions", message="Checking captions for long video", percent=5, duration_seconds=duration)
    providers = [
        ("native-caption-extractor", lambda: fetch_caption_url_segments(meta)),
        ("youtube-transcript-api", lambda: youtube_transcript_api_segments(video_id)),
        ("yt-dlp-subtitles", lambda: yt_dlp_grab_caption_segments(url, work_dir, expected_language)),
    ]
    for name, fn in providers:
        try:
            segs, lang, *rest = fn()
            if not segs or not timestamps_increase(segs):
                raise RuntimeError("empty or invalid timestamps")
            chunks = chunk_segments_by_time(segs, int(os.getenv("LONG_VIDEO_CHUNK_SECONDS", "600")))
            transcript = segments_to_transcript(segs)
            if transcript_word_count(transcript) < 10:
                raise RuntimeError("transcript not credible")
            attempts.append({"provider": name, "ok": True, "segments": len(segs), "words": transcript_word_count(transcript), "chunks": len(chunks)})
            update_url_job(job_id, stage="saving", message=f"Saving long transcript from {len(chunks)} queued caption chunks", percent=95, chunks_total=len(chunks), chunks_done=len(chunks))
            method = "queued-chunked-captions" if name != "youtube-transcript-api" else "queued-chunked-transcript-api"
            return save_transcript(source=title, source_kind="youtube", method=method, transcript=transcript,
                                   duration_seconds=duration, processing_seconds=time.monotonic() - started,
                                   media_id=video_id, source_url=canonical, title=title, creator=creator,
                                   language=lang, segments=segs, provider_attempts=attempts, cache_hit=False,
                                   owner_token=owner_token)
        except Exception as e:
            attempts.append({"provider": name, "ok": False, "error": str(e)[:240]})
    update_url_job(job_id, stage="download", message="Downloading long-video audio for chunked Whisper", percent=10)
    try:
        old_timeout = os.environ.get("YT_DLP_AUDIO_TIMEOUT_SECONDS")
        os.environ["YT_DLP_AUDIO_TIMEOUT_SECONDS"] = os.getenv("LONG_VIDEO_DOWNLOAD_TIMEOUT_SECONDS", "300")
        try:
            audio = yt_dlp_download_audio(url, work_dir)
        finally:
            if old_timeout is None:
                os.environ.pop("YT_DLP_AUDIO_TIMEOUT_SECONDS", None)
            else:
                os.environ["YT_DLP_AUDIO_TIMEOUT_SECONDS"] = old_timeout
        chunk_seconds = int(os.getenv("LONG_VIDEO_CHUNK_SECONDS", "600"))
        chunks = split_audio_for_long_transcription(audio, work_dir, chunk_seconds)
        all_segs: list[dict] = []
        expected_lang = infer_expected_language(meta)
        for idx, chunk in enumerate(chunks, 1):
            update_url_job(job_id, stage="transcribing", message=f"Transcribing chunk {idx} of {len(chunks)}", percent=min(90, 10 + int(80 * idx / max(len(chunks), 1))), chunks_total=len(chunks), chunks_done=idx - 1)
            segs, lang = transcribe_with_local_whisper(chunk, language=expected_lang, model=os.getenv("LONG_VIDEO_WHISPER_MODEL", os.getenv("YOUTUBE_WHISPER_MODEL", "tiny")), timeout=int(os.getenv("LONG_VIDEO_CHUNK_TIMEOUT_SECONDS", "300")))
            all_segs.extend(offset_segments(segs, (idx - 1) * chunk_seconds))
        transcript = segments_to_transcript(all_segs)
        if transcript_word_count(transcript) < 10:
            raise RuntimeError("chunked Whisper transcript not credible")
        attempts.append({"provider": "chunked-local-whisper", "ok": True, "segments": len(all_segs), "words": transcript_word_count(transcript), "chunks": len(chunks)})
        update_url_job(job_id, stage="saving", message=f"Saving long transcript from {len(chunks)} audio chunks", percent=95, chunks_total=len(chunks), chunks_done=len(chunks))
        return save_transcript(source=title, source_kind="youtube", method="queued-chunked-local-whisper", transcript=transcript,
                               duration_seconds=duration, processing_seconds=time.monotonic() - started,
                               media_id=video_id, source_url=canonical, title=title, creator=creator,
                               language=lang, segments=all_segs, provider_attempts=attempts, cache_hit=False,
                               owner_token=owner_token)
    except Exception as e:
        attempts.append({"provider": "chunked-local-whisper", "ok": False, "error": str(e)[:240]})
        detail = json.dumps(attempts[-4:], ensure_ascii=False)
        update_url_job(job_id, private_error_detail=f"Long-video queued transcription failed. Provider trail: {detail}")
        raise RuntimeError(BLOCKED_MESSAGE)

def transcribe_youtube_uncached(url: str, video_id: str, started: float, work_dir: Path, owner_token: Optional[str] = None, meta: Optional[dict] = None) -> dict:
    attempts = []
    meta = meta or {}
    if meta:
        attempts.append({"provider": "metadata", "ok": True})
    else:
        try:
            meta = yt_dlp_metadata(url)
            attempts.append({"provider": "metadata", "ok": True})
        except Exception as e:
            attempts.append({"provider": "metadata", "ok": False, "error": str(e)[:240]})
    title = meta.get("title") or f"YouTube {video_id}"
    creator = meta.get("uploader") or meta.get("channel")
    duration = meta.get("duration")
    canonical = meta.get("webpage_url") or f"https://youtu.be/{video_id}"

    expected_language = infer_expected_language(meta)
    expected_base = language_base(expected_language)
    if expected_base and expected_base != "en":
        providers = [
            ("yt-dlp-subtitles", lambda: yt_dlp_grab_caption_segments(url, work_dir, expected_language)),
        ]
        attempts.append({"provider": "native-caption-extractor", "ok": False, "error": "skipped to keep non-English public request bounded after YouTube timedtext 429s"})
        attempts.append({"provider": "youtube-transcript-api", "ok": False, "error": "skipped for original-language non-English route; default transcript API can return English or stall under IP blocking"})
    else:
        providers = [
            ("native-caption-extractor", lambda: fetch_caption_url_segments(meta)),
            ("youtube-transcript-api", lambda: youtube_transcript_api_segments(video_id)),
            ("yt-dlp-subtitles", lambda: yt_dlp_grab_caption_segments(url, work_dir, expected_language)),
        ]
    providers.append(("gemini-youtube", lambda: transcribe_with_gemini_youtube(url)))
    for name, fn in providers:
        try:
            if name == "native-caption-extractor" and not meta:
                raise RuntimeError("metadata unavailable")
            segs, lang, *rest = fn()
            if not segs or not timestamps_increase(segs):
                raise RuntimeError("empty or invalid timestamps")
            transcript = segments_to_transcript(segs)
            if not transcript.strip() or transcript_word_count(transcript) < 3:
                raise RuntimeError("transcript not credible")
            method = rest[0] if rest else name
            attempts.append({"provider": name, "ok": True, "segments": len(segs), "words": transcript_word_count(transcript)})
            return save_transcript(source=title, source_kind="youtube", method=method, transcript=transcript,
                                   duration_seconds=duration, processing_seconds=time.monotonic() - started,
                                   media_id=video_id, source_url=canonical, title=title, creator=creator,
                                   language=lang, segments=segs, provider_attempts=attempts, cache_hit=False,
                                   owner_token=owner_token)
        except Exception as e:
            attempts.append({"provider": name, "ok": False, "error": str(e)[:240]})

    try:
        audio_path = yt_dlp_download_audio(url, work_dir)
        expected_lang = infer_expected_language(meta)
        whisper_model = os.getenv("YOUTUBE_WHISPER_MODEL", "tiny") if expected_lang else None
        segs, lang = transcribe_with_local_whisper(audio_path, language=expected_lang, model=whisper_model, timeout=youtube_whisper_timeout_seconds(duration))
        transcript = segments_to_transcript(segs)
        attempts.append({"provider": "local-whisper", "ok": True, "segments": len(segs), "words": transcript_word_count(transcript)})
        return save_transcript(source=title, source_kind="youtube", method="local-whisper", transcript=transcript,
                               duration_seconds=duration, processing_seconds=time.monotonic() - started,
                               media_id=video_id, source_url=canonical, title=title, creator=creator,
                               language=lang, segments=segs, provider_attempts=attempts, cache_hit=False,
                               owner_token=owner_token)
    except Exception as e:
        attempts.append({"provider": "local-whisper", "ok": False, "error": str(e)[:240]})
        detail = json.dumps(attempts[-3:], ensure_ascii=False)
        raise RuntimeError(f"{BLOCKED_MESSAGE} Provider trail: {detail}")



def _segment_lines(rec: dict, limit: int = 8) -> list[str]:
    segs = rec.get("segments") or []
    lines = []
    if len(segs) > limit:
        # Long recordings need evidence from the beginning, middle, and end so
        # Phase 3 outputs prove they did not only inspect the opening minutes.
        first_count = max(1, limit // 3)
        middle_count = max(1, limit // 3)
        last_count = max(1, limit - first_count - middle_count)
        middle_start = max(first_count, (len(segs) // 2) - (middle_count // 2))
        selected = segs[:first_count] + segs[middle_start:middle_start + middle_count] + segs[-last_count:]
    else:
        selected = segs[:limit]
    for seg in selected:
        text = clean_whitespace(seg.get("text", ""))
        if text:
            lines.append(f"[{seconds_to_timestamp(seg.get('start', 0))}] {text}")
    if not lines:
        for line in (rec.get("transcript") or "").splitlines()[:limit]:
            line = clean_whitespace(line)
            if line:
                lines.append(line)
    return lines


def is_public_youtube_record(rec: dict) -> bool:
    if rec.get("source_kind") != "youtube":
        return False
    source_url = rec.get("source_url") or ""
    media_id = rec.get("media_id") or ""
    parsed = urlparse(source_url)
    host = (parsed.netloc or "").lower()
    return bool(media_id and ("youtube.com" in host or "youtu.be" in host))


def phase3_gemini_daily_limit() -> int:
    return max(0, int(os.getenv("PHASE3_GEMINI_DAILY_LIMIT", "20")))


def phase3_gemini_usage_key() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def reserve_phase3_gemini_call() -> int:
    limit = phase3_gemini_daily_limit()
    if limit <= 0:
        raise HTTPException(429, "Phase 3 Gemini free-quota limit reached. No key or provider detail was exposed.")
    key = phase3_gemini_usage_key()
    with PHASE3_GEMINI_USAGE_LOCK:
        try:
            usage = json.loads(PHASE3_GEMINI_USAGE_PATH.read_text()) if PHASE3_GEMINI_USAGE_PATH.exists() else {}
        except Exception:
            usage = {}
        used = int(usage.get(key, 0))
        if used >= limit:
            raise HTTPException(429, "Phase 3 Gemini free-quota limit reached. No key or provider detail was exposed.")
        usage = {key: used + 1}
        PHASE3_GEMINI_USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PHASE3_GEMINI_USAGE_PATH.write_text(json.dumps(usage), encoding="utf-8")
        return used + 1


def build_gemini_prompt(rec: dict, output_type: str, question: Optional[str] = None) -> str:
    title = rec.get("title") or rec.get("source") or "Transcript"
    word_count = rec.get("word_count") or transcript_word_count(rec.get("transcript", ""))
    evidence_lines = _segment_lines(rec, 36)
    evidence = "\n".join(f"- {line}" for line in evidence_lines)
    if output_type == "executive_summary":
        task = """Create a sharp, useful summary for a busy operator.
Return exactly these sections:
## Quick summary
3-5 bullets. Plain English. Capture the actual point, not generic filler.
## Why this matters
2-3 bullets explaining stakes, leverage, or consequence.
## Use this next
3 practical ways to use the transcript.
## Source notes
3 short timestamped citations only. Put timestamps here, not randomly in every bullet."""
    elif output_type == "action_items":
        task = """Create an action-item breakdown someone can execute immediately.
Return exactly these sections:
## Action plan
5-8 bullets. Each bullet must include Owner, Outcome, First step, and Done when.
## Priority order
Top 3 actions in order.
## Source notes
3 short timestamped citations only. Put timestamps here, not randomly in every action."""
    else:
        task = f"Answer the user's question clearly and directly. Question: {question or 'What should I know from this transcript?'} Include a short Source notes section with timestamped citations."
    return f"""You are the EPIC Transcript Machine assistant.

Goal: turn a transcript into useful, publishable business output fast.

Rules:
- Use only the transcript evidence below.
- Do not invent facts, quotes, names, numbers, or promises.
- Be specific to this transcript. Avoid generic advice.
- Keep timestamps only in the final Source notes section unless a timestamp is essential to the answer.
- No process disclaimers. No provider mentions. No random metadata.
- Make the copy compelling enough that someone knows what to do next.

Output type: {ANALYSIS_LABELS.get(output_type, output_type)}
Source title: {title}
Words reviewed: {word_count}

Task:
{task}

Transcript evidence:
{evidence}
""".strip()


def call_gemini_text(prompt: str) -> str:
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise HTTPException(503, PHASE3_GEMINI_PUBLIC_ERROR)
    model = os.getenv("PHASE3_GEMINI_MODEL", "gemini-1.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    try:
        response = requests.post(
            url,
            params={"key": key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.4, "maxOutputTokens": int(os.getenv("PHASE3_GEMINI_MAX_OUTPUT_TOKENS", "8192"))},
            },
            timeout=int(os.getenv("PHASE3_GEMINI_TIMEOUT_SECONDS", "45")),
        )
    except Exception:
        raise HTTPException(502, "Phase 3 Gemini request failed safely. No key or provider detail was exposed.")
    if response.status_code != 200:
        raise HTTPException(502, "Phase 3 Gemini returned a safe upstream error. No key or provider detail was exposed.")
    try:
        data = response.json()
        parts = data["candidates"][0]["content"]["parts"]
        text = "\n".join(part.get("text", "") for part in parts).strip()
    except Exception:
        text = ""
    if not text:
        raise HTTPException(502, "Phase 3 Gemini returned empty output. No key or provider detail was exposed.")
    return text


def build_gemini_analysis_text(rec: dict, output_type: str, question: Optional[str] = None) -> str:
    if output_type not in ANALYSIS_OUTPUTS:
        raise HTTPException(400, "Unsupported analysis output type.")
    if not is_public_youtube_record(rec):
        raise HTTPException(400, "Gemini Phase 3 is limited to public YouTube transcripts only.")
    reserve_phase3_gemini_call()
    return call_gemini_text(build_gemini_prompt(rec, output_type, question=question))


def _evidence_cycle(evidence: list[str], count: int) -> list[str]:
    if not evidence:
        evidence = ["[00:00] Transcript evidence unavailable."]
    return [evidence[i % len(evidence)] for i in range(count)]


def _strip_timestamp(line: str) -> str:
    return re.sub(r"^\[[0-9:,]+\]\s*", "", line).strip() or line


def _asset_evidence_points(rec: dict, count: int = 100) -> list[dict]:
    """Pick broad timestamped evidence across the whole transcript."""
    segs = rec.get("segments") or []
    points: list[dict] = []
    usable = [seg for seg in segs if clean_whitespace(seg.get("text", ""))]
    if usable:
        selected_indexes: list[int] = []
        if len(usable) <= count:
            selected = usable[:]
            i = 0
            while len(selected) < count:
                selected.append(usable[i % len(usable)])
                i += 1
        else:
            selected_indexes = []
            seen = set()
            for i in range(count):
                idx = round(i * (len(usable) - 1) / (count - 1))
                while idx in seen and idx + 1 < len(usable):
                    idx += 1
                seen.add(idx)
                selected_indexes.append(idx)
            selected = [usable[idx] for idx in selected_indexes]
        if len(usable) <= count:
            selected_indexes = [usable.index(seg) for seg in selected]
        for idx, seg in zip(selected_indexes, selected):
            window = usable[max(0, idx - 1):idx + 7] or [seg]
            text = _merge_caption_window(clean_whitespace(item.get("text", "")) for item in window)
            points.append({"timestamp": seconds_to_timestamp(seg.get("start", 0)), "text": text})
    if points:
        return points[:count]

    fallback = []
    for line in (rec.get("transcript") or "").splitlines():
        line = clean_whitespace(line)
        if not line:
            continue
        match = re.match(r"^\[([^\]]+)\]\s*(.*)$", line)
        fallback.append({"timestamp": match.group(1) if match else "00:00", "text": match.group(2) if match else line})
    if not fallback:
        fallback = [{"timestamp": "00:00", "text": "The transcript did not include enough readable text for detailed assets."}]
    selected = []
    for i in range(count):
        idx = round(i * (len(fallback) - 1) / max(1, count - 1)) if len(fallback) > 1 else 0
        selected.append(fallback[idx])
    return selected


def _asset_phrase(text: str, max_words: int = 18) -> str:
    clean = _strip_timestamp(clean_whitespace(text)).strip(" -–—:;,.\"")
    words = clean.split()
    if len(words) > max_words:
        clean = " ".join(words[:max_words]).rstrip(" ,;:")
    return clean or "the most important transcript moment"


def _merge_caption_window(parts) -> str:
    """Merge caption snippets while removing adjacent overlap/repetition."""
    words: list[str] = []
    for part in parts:
        next_words = clean_whitespace(part).split()
        if not next_words:
            continue
        max_overlap = min(len(words), len(next_words), 12)
        overlap = 0
        for size in range(max_overlap, 0, -1):
            if [w.lower().strip(",.?!;:") for w in words[-size:]] == [w.lower().strip(",.?!;:") for w in next_words[:size]]:
                overlap = size
                break
        words.extend(next_words[overlap:])
    # Remove immediate duplicate words left by auto-caption overlap.
    deduped: list[str] = []
    for word in words:
        if deduped and word.lower().strip(",.?!;:") == deduped[-1].lower().strip(",.?!;:"):
            continue
        deduped.append(word)
    return clean_whitespace(" ".join(deduped))


def _asset_sentence(text: str, max_words: int = 26) -> str:
    clean = _asset_phrase(text, max_words=max_words).strip()
    if clean and clean[-1] not in ".!?":
        clean += "."
    return clean[:1].upper() + clean[1:] if clean else "The transcript points to a clear next action."


def _asset_takeaway(text: str, index: int) -> str:
    """Convert rough transcript evidence into a finished, readable takeaway."""
    lower = text.lower()
    rules = [
        (("valuation", "worth", "sde", "multiple"), "Enterprise value is the stronger story. The system matters when it increases what the business is worth, not just what the software can do."),
        (("retain", "retention", "close", "higher rate"), "Position the system as retention and closing leverage. Buyers stay longer when the process keeps producing measurable outcomes."),
        (("local business", "local businesses", "gym", "fitness"), "Local businesses need a follow-up machine. The opportunity is speed, consistency, and proof after every lead comes in."),
        (("follow up", "lead", "leads", "customer"), "Speed-to-lead is the wedge. A simple response system can turn missed demand into booked conversations."),
        (("paid ads", "landing page", "website", "traffic"), "Traffic is only the first step. The offer becomes valuable when the landing page, follow-up, and conversion path work together."),
        (("referral", "referrals"), "Referrals can become a built-in growth loop. The system should ask, track, and follow up without waiting on manual reminders."),
        (("portfolio", "agency owners", "roll", "sell"), "Build assets that can survive outside one owner. Repeatable systems make a service business easier to combine, scale, and sell."),
        (("ai agent", "ai agents", "automation", "automated"), "Do not sell an AI agent as a novelty. Sell the business system it powers and the outcome it can repeat."),
        (("process", "system", "framework"), "Turn the process into the product. A documented system is easier to sell, fulfill, improve, and delegate."),
        (("case study", "study", "harvard", "proof"), "Proof sharpens the offer. Use evidence to show why the system matters and why delay costs money."),
        (("appointment", "meet", "friday", "schedule"), "Make the next step automatic. Confirmations, reminders, and booked appointments protect the revenue path."),
        (("team", "train", "training"), "The team needs the playbook, not just the tool. Training turns the system from a demo into daily execution."),
        (("market", "competitor", "competitive"), "Differentiate with the complete operating system. Competitors can copy tools faster than they can copy execution."),
        (("offer", "service", "sell"), "Sell the outcome package. The offer should make the buyer see the result, the process, and the proof in one motion."),
    ]
    for needles, takeaway in rules:
        if any(n in lower for n in needles):
            return takeaway
    fallbacks = [
        "Package one clear insight into one repeatable action. The asset should make the viewer know what to do next.",
        "A simple operating principle makes the lesson easier to remember and apply.",
        "Connect the lesson to a measurable business result. Useful content should move from idea to action quickly.",
        "Make the invisible system visible. The content should show the mechanism behind the result, not just the outcome.",
        "A clear buyer decision reduces confusion and points toward action.",
        "Frame the lesson as a practical upgrade. The point is not more information, it is a better way to execute.",
    ]
    return fallbacks[index % len(fallbacks)]


def _asset_complete_context(text: str, max_words: int = 60) -> str:
    """Return a complete, readable context window without dangling clipped endings."""
    clean = _strip_timestamp(clean_whitespace(text)).strip(" -–—:;,.\"")
    if not clean:
        return "The transcript gives a concrete business moment to act on."
    # Prefer complete transcript sentences from the context window.
    sentences = re.findall(r"[^.!?]+[.!?]", clean)
    if sentences:
        chosen = clean_whitespace(" ".join(sentences[:2]))
    else:
        chosen = clean
    words = chosen.split()
    if len(words) > max_words:
        words = words[:max_words]
        while words and words[-1].lower().strip(",;:") in {"and", "or", "but", "to", "for", "with", "that", "because", "the", "a", "an", "of", "in", "on", "by", "from"}:
            words.pop()
        chosen = " ".join(words)
    chosen = chosen.strip(" ,;:")
    if chosen and chosen[-1] not in ".!?":
        chosen += "."
    return chosen[:1].upper() + chosen[1:]


def build_100_content_assets(rec: dict) -> list[str]:
    """Return 100 finished, distinct asset drafts grounded in complete context windows."""
    categories = [
        "Hook", "Short post", "Email subject", "Newsletter angle", "Reel script",
        "Carousel slide", "Quote card", "CTA", "Objection reply", "Repurpose prompt",
    ]
    hooks = [
        "The money leak usually starts before anyone sees it",
        "The system becomes valuable when the handoff is no longer random",
        "A missed follow-up is not a small detail; it is the sale slipping away",
        "The offer gets stronger when the proof is operational, not theoretical",
        "The simplest process gap can become the biggest growth constraint",
        "The next tool will not matter if this moment still breaks",
        "A business looks more valuable when the process repeats without the owner",
        "A lead is only useful when the response path is already built",
        "The proof lives in the operating detail, not the promise",
        "The system is not finished until this moment has a clear next move",
    ]
    short_posts = [
        "Good systems are built around the moments customers actually experience",
        "The useful improvement is the one that makes the next handoff obvious",
        "Growth gets easier when the business can repeat the important step without guessing",
        "A transcript moment becomes valuable when it turns into a specific operating behavior",
        "The difference between a tool and a system is whether the result repeats",
        "Better follow-through turns the same attention into a cleaner business outcome",
        "Software gets easier to sell when the business process around it is clear",
        "The next action should be obvious before the customer has time to drift",
        "Proof makes the offer easier to trust because the mechanism is visible",
        "A sharper system removes friction instead of adding another disconnected step",
    ]
    subjects = [
        "The process gap costing the next result",
        "Where the system needs to get sharper",
        "A better follow-through starts here",
        "The moment your offer has to prove itself",
        "What the transcript says to tighten next",
        "The handoff that deserves attention now",
        "A clearer system from one real moment",
        "The proof point behind the next improvement",
        "What to clean up before adding tools",
        "The operating detail worth acting on",
    ]
    newsletter_openers = [
        "There is a practical operating lesson inside this section",
        "The useful story is not bigger tech; it is cleaner execution",
        "This example shows where the business can become easier to run",
        "The next improvement starts with a specific customer-facing moment",
        "A system becomes more valuable when the team can see the exact gap",
        "This proof point turns the lesson from theory into something actionable",
        "The transcript gives a concrete example of what should happen next",
        "A practical upgrade is hiding inside this small section",
        "The strongest takeaway is the repeatable behavior behind the result",
        "This detail makes the service easier to package and explain",
    ]
    reel_lines = [
        "Show the moment and make the business consequence impossible to miss",
        "Put the timestamp on screen and explain why this handoff matters",
        "Make one fix feel obvious, immediate, and measurable",
        "Open on the problem and let the transcript prove it exists",
        "Make the viewer see the gap before the solution appears",
        "Turn the section into a before-and-after business lesson",
        "Anchor the reel in the evidence and connect it to the operating system",
        "Let the source line carry the credibility, then add one practical takeaway",
        "Make the clip a quick lesson about the step that cannot be left to chance",
        "Close with the next action this evidence makes clear",
    ]
    carousel_heads = [
        "The gap", "The proof", "The fix", "The handoff", "The risk",
        "The system", "The next step", "The leverage", "The lesson", "The action",
    ]
    closers = [
        "Make that the first checkpoint",
        "Turn that into the next operating standard",
        "Keep the team accountable to that detail",
        "Build the follow-up around that proof",
        "Use that evidence to tighten the offer",
        "Make the next handoff visible",
        "Protect that step before scaling traffic",
        "Connect that detail to the buyer outcome",
        "Document the behavior before automating it",
        "Review that point before changing the system",
    ]
    support_lines = [
        "show the operating lesson in one clear visual step",
        "turn the proof point into a simple before-and-after frame",
        "name the risk and show the better handoff",
        "connect the excerpt to the result the buyer wants",
        "make the missing step visible before the solution appears",
        "show how the process protects the next conversion",
        "translate the lesson into one repeatable behavior",
        "tie the proof to a measurable business outcome",
        "make the system easier to understand at a glance",
        "end with the action the viewer should take next",
    ]
    email_blurbs = [
        "turn this into one practical improvement the team can own",
        "make the handoff clearer before more traffic is added",
        "connect the proof point to the buyer's next decision",
        "show why the process matters more than another standalone tool",
        "translate the evidence into one sharper sales conversation",
        "document the behavior that should repeat after this moment",
        "remove the friction this excerpt makes visible",
        "tie the lesson to the outcome the customer already wants",
        "make the mechanism behind the result easier to trust",
        "convert the transcript evidence into a simple next step",
    ]
    ctas = [
        "Get the broken handoff written down before another tool is added",
        "Get one measurable follow-up step assigned from this evidence today",
        "Get the next action into the operating checklist",
        "Get the proof point into the sales story so the buyer sees the mechanism",
        "Get the team aligned on what happens immediately after this moment",
        "Get the repeatable step documented while the evidence is clear",
        "Get the offer tightened around the result this excerpt supports",
        "Get the friction removed before it becomes another missed opportunity",
        "Get the source-backed lesson turned into one owner and one deadline",
        "Get the clip, caption, and follow-up built around this evidence",
    ]
    replies = [
        "The evidence shows why this should be handled directly instead of treated as optional",
        "This is not a theory; the transcript gives a concrete place to improve",
        "The safest answer is to stay with the source and fix the step it exposes",
        "The point is stronger when the team can show the exact moment and outcome",
        "A tool alone will not solve this unless the handoff around it is clear",
        "The response should focus on the process gap the transcript makes visible",
        "The objection gets weaker when the operating detail is shown plainly",
        "The right response is to make the evidence easier to act on",
        "If the buyer questions the value, connect it back to this proof",
        "The transcript supports action because it names a concrete place to tighten execution",
    ]
    points = _asset_evidence_points(rec, 100)
    assets = [
        "## Create 100 content assets",
        "Each item is finished audience-ready prose built from a complete cited context window. The exact source excerpt appears after the asset for verification.",
    ]
    for i, point in enumerate(points, 1):
        kind = categories[(i - 1) // 10]
        slot = ((i - 1) % 10) + 1
        idx = slot - 1
        timestamp = point["timestamp"]
        excerpt = _asset_complete_context(point["text"], max_words=64)
        takeaway = _asset_takeaway(point["text"], i)
        if kind == "Hook":
            body = f"{hooks[idx]}. {takeaway} {closers[idx]}. Source excerpt: {excerpt} [{timestamp}]"
        elif kind == "Short post":
            body = f"{short_posts[idx]}. {takeaway} {closers[idx]}. Source excerpt: {excerpt} [{timestamp}]"
        elif kind == "Email subject":
            body = f"Subject: {subjects[idx]} for a stronger system. {closers[idx]}. Source excerpt: {excerpt} [{timestamp}]"
        elif kind == "Newsletter angle":
            body = f"Newsletter angle {slot}: {newsletter_openers[idx]}. {takeaway} {closers[idx]}. Source excerpt: {excerpt} [{timestamp}]"
        elif kind == "Reel script":
            body = f"Reel script {slot}: {reel_lines[idx]}. Say: {takeaway} {closers[idx]}. Source excerpt: {excerpt} [{timestamp}]"
        elif kind == "Carousel slide":
            body = f"Carousel slide {slot}: {carousel_heads[idx]}: {takeaway} Supporting copy: {support_lines[idx]}. {closers[idx]}. Source excerpt: {excerpt} [{timestamp}]"
        elif kind == "Quote card":
            body = f"Quote-card takeaway {slot}: {takeaway} Evidence line: {excerpt} {closers[idx]}. Source excerpt: {excerpt} [{timestamp}]"
        elif kind == "CTA":
            body = f"CTA {slot}: {ctas[idx]}. {closers[idx]}. Source excerpt: {excerpt} [{timestamp}]"
        elif kind == "Objection reply":
            body = f"Reply: {slot}: {replies[idx]}. {closers[idx]}. Source excerpt: {excerpt} [{timestamp}]"
        else:
            body = f"Repurpose bundle {slot}: LinkedIn post: {takeaway} Email blurb: {email_blurbs[idx]}. Clip caption: {carousel_heads[idx]} at {timestamp}. {closers[idx]}. Source excerpt: {excerpt} [{timestamp}]"
        assets.append(f"{i}. **{kind} {slot}** - {body}")
    return assets

def build_analysis_text(rec: dict, output_type: str, question: Optional[str] = None) -> str:
    if output_type not in ANALYSIS_OUTPUTS:
        raise HTTPException(400, "Unsupported analysis output type.")
    evidence = _segment_lines(rec, 12)
    samples = _evidence_cycle(evidence, 8)
    first, second, third, fourth = samples[:4]
    p1, p2, p3, p4 = (_strip_timestamp(first), _strip_timestamp(second), _strip_timestamp(third), _strip_timestamp(fourth))

    if output_type == "executive_summary":
        return "\n".join([
            "# Summary", "",
            "## Quick summary",
            f"- {p1}",
            f"- {p2}",
            f"- {p3}",
            "- The useful move is to turn the strongest transcript moments into a clear message, a follow-up asset, and a next-step checklist.",
            "", "## Why this matters",
            "- The transcript gives raw language that can become sharper content, offers, or internal follow-up.",
            "- The best output is not more transcript text. It is a shorter explanation of what matters and what to do next.",
            "", "## Use this next",
            "- Pull the strongest point into a short post or email.",
            "- Turn one concrete lesson into a checklist or SOP.",
            "- Use the source notes below to verify the summary before publishing.",
            "", "## Source notes",
            f"- {first}", f"- {second}", f"- {third}",
        ]).strip() + "\n"

    if output_type == "action_items":
        return "\n".join([
            "# Action Items", "",
            "## Action plan",
            f"- Owner: Content lead. Outcome: create the first usable summary asset. First step: turn this point into 3 bullets: {p1}. Done when: the asset is ready to paste into a post or email.",
            f"- Owner: Operations. Outcome: capture the repeatable process. First step: convert this section into a checklist: {p2}. Done when: the checklist has clear steps and a pass/fail standard.",
            f"- Owner: Editor. Outcome: find the strongest clip or quote. First step: review this moment: {p3}. Done when: one timestamped quote or clip candidate is selected.",
            f"- Owner: Follow-up. Outcome: create a next-action message. First step: write one follow-up from this idea: {p4}. Done when: the message has a clear CTA.",
            "- Owner: Reviewer. Outcome: prevent weak AI output from shipping. First step: compare every deliverable against the source notes. Done when: unsupported claims are removed.",
            "", "## Priority order",
            "1. Create the short summary asset.",
            "2. Pull the best quote or clip candidate.",
            "3. Turn the repeatable lesson into a checklist.",
            "", "## Source notes",
            f"- {first}", f"- {second}", f"- {third}",
        ]).strip() + "\n"

    if output_type == "ask_question":
        return "\n".join([
            "# Answer", "",
            f"Question: {question or 'What should I know from this transcript?'}", "",
            f"Short answer: {p1} {p2}", "",
            "## Source notes", f"- {first}", f"- {second}", f"- {third}",
        ]).strip() + "\n"

    if output_type == "content_assets_100":
        return "\n".join(["# Create 100 content assets", ""] + build_100_content_assets(rec)).strip() + "\n"

    label = ANALYSIS_LABELS.get(output_type, output_type.replace("_", " ").title())
    return "\n".join([f"# {label}", "", f"- {p1}", f"- {p2}", f"- {p3}", "", "## Source notes", f"- {first}", f"- {second}", f"- {third}"]).strip() + "\n"


def build_phase3_analysis_text(rec: dict, output_type: str, question: Optional[str] = None) -> str:
    if is_public_youtube_record(rec) and (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        return build_gemini_analysis_text(rec, output_type, question=question)
    return build_analysis_text(rec, output_type, question=question)


def save_analysis(*, transcript_id: str, output_type: str, question: Optional[str], analysis: str, owner_token: str) -> dict:
    init_db()
    analysis_id = uuid.uuid4().hex[:12]
    with db() as conn:
        conn.execute(
            "INSERT INTO analyses (id, transcript_id, output_type, question, analysis, owner_token) VALUES (?, ?, ?, ?, ?, ?)",
            (analysis_id, transcript_id, output_type, question, analysis, owner_token),
        )
        row = conn.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
    return dict(row)


def build_combined_analysis_text(rec: dict) -> str:
    parts = []
    for output_type in ANALYSIS_OUTPUTS:
        if output_type == "ask_question":
            continue
        parts.append(build_phase3_analysis_text(rec, output_type))
    return "\n\n---\n\n".join(parts).strip() + "\n"

def make_markdown(row: dict) -> str:
    title = row.get("title") or row.get("source") or "Transcript"
    lines = [f"# {title}", "", f"Source: {row.get('source_url') or row.get('source') or ''}", f"Method: {row.get('method','')}", f"Language: {row.get('language') or 'unknown'}", f"Words: {row.get('word_count') or transcript_word_count(row.get('transcript',''))}", "", "## Transcript", ""]
    for seg in row.get("segments") or []:
        lines.append(f"**[{seconds_to_timestamp(seg.get('start', 0))}]** {seg.get('text','')}")
    if not row.get("segments"):
        lines.append(row.get("transcript", ""))
    return "\n".join(lines).strip() + "\n"


def make_srt(row: dict) -> str:
    lines = []
    for i, seg in enumerate(row.get("segments") or [], 1):
        start = seconds_to_timestamp(seg.get("start", 0), comma=True)
        end = seconds_to_timestamp(seg.get("end", seg.get("start", 0) + 2), comma=True)
        lines += [str(i), f"{start} --> {end}", seg.get("text", ""), ""]
    return "\n".join(lines).strip() + "\n"


def make_vtt(row: dict) -> str:
    lines = ["WEBVTT", ""]
    for seg in row.get("segments") or []:
        start = seconds_to_timestamp(seg.get("start", 0), comma=True).replace(",", ".")
        end = seconds_to_timestamp(seg.get("end", seg.get("start", 0) + 2), comma=True).replace(",", ".")
        lines += [f"{start} --> {end}", seg.get("text", ""), ""]
    if not row.get("segments") and row.get("transcript"):
        lines += ["00:00:00.000 --> 00:00:02.000", row.get("transcript", ""), ""]
    return "\n".join(lines).strip() + "\n"


@app.get("/", include_in_schema=False)
def root_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "setup": setup_status()}


@app.get("/api/setup")
def api_setup() -> dict:
    return setup_status()


def transcribe_youtube_url_to_record(url: str, owner_token: str, started: Optional[float] = None, allow_long: bool = False, job_id: Optional[str] = None) -> dict:
    started = started or time.monotonic()
    video_id = normalize_youtube_video_id(url)
    if not video_id:
        raise HTTPException(400, "URL is not a supported YouTube link")
    meta_probe = {}
    expected_language = None
    try:
        meta_probe = yt_dlp_metadata(url)
        expected_language = infer_expected_language(meta_probe)
    except Exception:
        meta_probe = {}
    cached = get_cached_transcript(video_id, expected_language=expected_language)
    if cached:
        return record_for_owner(cached, owner_token)
    is_long = (meta_probe.get("duration") or 0) > MAX_SYNC_YOUTUBE_DURATION_SECONDS
    if is_long and not allow_long:
        raise HTTPException(422, LONG_VIDEO_MESSAGE)
    work_dir = Path(tempfile.mkdtemp(prefix="epic-youtube-"))
    try:
        if is_long:
            single_audio_max = int(os.getenv("YOUTUBE_JOB_SINGLE_AUDIO_MAX_SECONDS", "360"))
            if allow_long and (meta_probe.get("duration") or 0) <= single_audio_max:
                return transcribe_youtube_uncached(url, video_id, started, work_dir, owner_token=owner_token, meta=meta_probe)
            return transcribe_long_youtube_queued(url, video_id, started, work_dir, owner_token=owner_token, meta=meta_probe, job_id=job_id)
        return transcribe_youtube_uncached(url, video_id, started, work_dir, owner_token=owner_token, meta=meta_probe)
    except RuntimeError as e:
        update_url_job(job_id, private_error_detail=str(e))
        raise HTTPException(422, visitor_safe_transcription_error(e))
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


SOCIAL_URL_HOSTS = {
    "tiktok.com": "TikTok",
    "instagram.com": "Instagram",
    "facebook.com": "Facebook",
    "fb.watch": "Facebook",
    "x.com": "X/Twitter",
    "twitter.com": "X/Twitter",
}


def social_url_guidance(url: str) -> Optional[str]:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    for domain, label in SOCIAL_URL_HOSTS.items():
        if host == domain or host.endswith("." + domain):
            return f"{label} links often block automatic public downloads. If you have the audio or video file, upload it here and we’ll transcribe it directly. Direct MP3, WAV, M4A, MP4, MOV, WebM, and other public media file URLs are supported when the source allows downloads."
    return None


def transcribe_public_media_url_to_record(url: str, owner_token: str, started: Optional[float] = None) -> dict:
    started = started or time.monotonic()
    guidance = social_url_guidance(url)
    if guidance:
        raise HTTPException(422, guidance)

    # Phase 2-compatible non-YouTube route. Free only: captions first, then local Whisper if installed.
    work_dir = Path(tempfile.mkdtemp(prefix="epic-url-"))
    attempts = []
    try:
        meta = yt_dlp_metadata(url)
        title = meta.get("title") or url
        try:
            segs, lang, method = fetch_caption_url_segments(meta)
            transcript = segments_to_transcript(segs)
        except Exception as e:
            attempts.append({"provider": "captions", "ok": False, "error": str(e)[:240]})
            audio = yt_dlp_download_audio(url, work_dir)
            segs, lang = transcribe_with_local_whisper(audio)
            transcript = segments_to_transcript(segs)
            method = "local-whisper"
        return save_transcript(source=title, source_kind="url", method=method, transcript=transcript,
                               duration_seconds=meta.get("duration"), processing_seconds=time.monotonic() - started,
                               media_id=meta.get("id"), source_url=meta.get("webpage_url") or url,
                               title=title, creator=meta.get("uploader") or meta.get("channel"), language=lang,
                               segments=segs, provider_attempts=attempts, owner_token=owner_token)
    except RuntimeError:
        # Non-YouTube sources are Phase 2 territory. Keep the error helpful for visitors.
        raise HTTPException(422, "That link is not available for automatic transcription yet. If you have the video or audio file, upload it here and we’ll take another route.")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def run_url_job(job_id: str, url: str, owner_token: str, phase1_qc_force_failure: bool = False) -> None:
    with URL_JOBS_LOCK:
        URL_JOBS[job_id].update({"status": "running", "started_at": time.time()})
        save_url_jobs_locked()
    try:
        started = time.monotonic()
        if phase1_qc_force_failure:
            raise HTTPException(422, "forced backend transcription failure. Provider trail: forced before provider work; no Whisper execution")
        if normalize_youtube_video_id(url):
            rec = transcribe_youtube_url_to_record(url, owner_token, started=started, allow_long=True, job_id=job_id)
        else:
            with URL_JOBS_LOCK:
                URL_JOBS[job_id].update({"stage": "media_url", "message": "Checking public media URL for captions or audio fallback", "percent": 10})
            rec = transcribe_public_media_url_to_record(url, owner_token, started=started)
        with URL_JOBS_LOCK:
            URL_JOBS[job_id].update({"status": "done", "record": rec, "finished_at": time.time(), "percent": 100})
            save_url_jobs_locked()
    except HTTPException as e:
        with URL_JOBS_LOCK:
            safe_error = visitor_safe_transcription_error(e.detail)
            updates = {"status": "error", "error": safe_error, "status_code": e.status_code, "finished_at": time.time()}
            if safe_error != str(e.detail):
                updates["private_error_detail"] = str(e.detail)
            URL_JOBS[job_id].update(updates)
            save_url_jobs_locked()
    except Exception as e:
        with URL_JOBS_LOCK:
            URL_JOBS[job_id].update({"status": "error", "error": str(e), "status_code": 500, "finished_at": time.time()})
            save_url_jobs_locked()


@app.post("/api/transcribe-url-job")
def api_transcribe_url_job(url: str = Form(...), owner: Optional[str] = Form(None), phase1_qc_force_failure: Optional[str] = Form(None)) -> JSONResponse:
    url = (url or "").strip()
    owner_token = valid_owner_token(owner) or secrets.token_urlsafe(32)
    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise HTTPException(400, "URL must start with http:// or https://")
    job_id = uuid.uuid4().hex[:12]
    with URL_JOBS_LOCK:
        URL_JOBS[job_id] = {"id": job_id, "status": "queued", "url": url, "created_at": time.time()}
        save_url_jobs_locked()
    force_failure = (phase1_qc_force_failure or "").lower() in {"1", "true", "yes"} and url == "https://example.com/hermes-forced-failure.mp3"
    thread = threading.Thread(target=run_url_job, args=(job_id, url, owner_token, force_failure), daemon=True)
    thread.start()
    return JSONResponse({"ok": True, "job": URL_JOBS[job_id]}, status_code=202)


@app.get("/api/jobs/{job_id}")
def api_get_job(job_id: str) -> JSONResponse:
    with URL_JOBS_LOCK:
        if job_id not in URL_JOBS:
            load_url_jobs_locked()
        job = dict(URL_JOBS.get(job_id) or {})
    if not job:
        raise HTTPException(404, "Job not found")
    job.pop("private_error_detail", None)
    return JSONResponse({"ok": True, "job": job})


@app.post("/api/transcribe-url")
def api_transcribe_url(url: str = Form(...), owner: Optional[str] = Form(None)) -> JSONResponse:
    url = (url or "").strip()
    owner_token = valid_owner_token(owner) or secrets.token_urlsafe(32)
    if not url:
        raise HTTPException(400, "URL is required.")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise HTTPException(400, "URL must start with http:// or https://")
    started = time.monotonic()
    video_id = normalize_youtube_video_id(url)
    if video_id:
        return JSONResponse({"ok": True, "record": transcribe_youtube_url_to_record(url, owner_token, started=started)})

    return JSONResponse({"ok": True, "record": transcribe_public_media_url_to_record(url, owner_token, started=started)})


@app.post("/api/transcribe-upload")
def api_transcribe_upload(file: UploadFile = File(...), owner: Optional[str] = Form(None)) -> JSONResponse:
    name = file.filename or "upload"
    owner_token = valid_owner_token(owner) or secrets.token_urlsafe(32)
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(400, f"Unsupported file type: {ext or '(none)'}. Upload one of: {SUPPORTED_UPLOAD_FORMATS}.")
    started = time.monotonic()
    work_dir = Path(tempfile.mkdtemp(prefix="epic-upload-"))
    saved = work_dir / f"upload{ext}"
    try:
        with saved.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        file_hash = "upload:" + hashlib.sha256(saved.read_bytes()).hexdigest()
        cached_upload = get_cached_transcript(file_hash)
        if cached_upload:
            return JSONResponse({"ok": True, "record": record_for_owner(cached_upload, owner_token)})
        if ext in TEXT_EXTS:
            transcript = clean_whitespace(saved.read_text(errors="ignore")); method = "passthrough"; segments = []; lang = None
        elif ext in SUBTITLE_EXTS:
            raw = saved.read_text(errors="ignore")
            segments = parse_vtt_segments(raw) if ext == ".vtt" else parse_srt_segments(raw)
            transcript = segments_to_transcript(segments) if segments else strip_vtt_srt(raw)
            method = "captions"; lang = None
        else:
            segments, lang = transcribe_with_local_whisper(saved)
            transcript = segments_to_transcript(segments); method = "local-whisper"
        if not transcript.strip():
            raise RuntimeError("Transcript came back empty.")
        rec = save_transcript(source=name, source_kind="upload", method=method, transcript=transcript,
                              duration_seconds=media_duration_seconds(saved), processing_seconds=time.monotonic() - started,
                              media_id=file_hash, source_url=None, title=name, creator=None,
                              language=lang, segments=segments, owner_token=owner_token)
        return JSONResponse({"ok": True, "record": rec})
    except RuntimeError as e:
        raise HTTPException(422, str(e))
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

@app.get("/api/recent")
def api_recent(limit: int = 20, x_transcript_owner: Optional[str] = Header(None)) -> dict:
    owner_token = header_owner(x_transcript_owner)
    if not owner_token:
        return {"items": []}
    limit = max(1, min(int(limit), 100))
    with db() as conn:
        rows = conn.execute("SELECT * FROM transcripts WHERE owner_token=? ORDER BY created_at DESC LIMIT ?", (owner_token, limit)).fetchall()
    return {"items": [public_video_cache_summary(r) for r in rows]}


@app.get("/api/transcripts/{rec_id}")
def api_get_transcript(rec_id: str, x_transcript_owner: Optional[str] = Header(None)) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM transcripts WHERE id=?", (rec_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Not found.")
    require_owner(row, x_transcript_owner)
    return row_to_record(row)


def transcript_download_response(rec: dict, format: str) -> PlainTextResponse:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", (rec.get("source") or "transcript"))[:60] or "transcript"
    if format == "md":
        body, media, ext = make_markdown(rec), "text/markdown", "md"
    elif format == "srt":
        body, media, ext = make_srt(rec), "application/x-subrip", "srt"
    elif format == "vtt":
        body, media, ext = make_vtt(rec), "text/vtt", "vtt"
    else:
        body, media, ext = rec.get("transcript", ""), "text/plain", "txt"
    return PlainTextResponse(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{safe}.{ext}"'})


@app.post("/api/transcripts/{rec_id}/download-link")
def api_download_link(request: Request, rec_id: str, format: str = Query("txt", pattern="^(txt|md|srt|vtt)$"), x_transcript_owner: Optional[str] = Header(None)) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM transcripts WHERE id=?", (rec_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Not found.")
    require_owner(row, x_transcript_owner)
    token = secrets.token_urlsafe(32)
    DOWNLOAD_TOKENS[token] = {"rec_id": rec_id, "format": format, "expires": time.time() + 300}
    return {"ok": True, "url": str(request.url_for("api_signed_download", token=token)), "expires_seconds": 300}


@app.get("/api/download/{token}")
def api_signed_download(token: str) -> PlainTextResponse:
    entry = DOWNLOAD_TOKENS.pop(token, None)
    if not entry or entry.get("expires", 0) < time.time():
        raise HTTPException(403, "Download link expired.")
    with db() as conn:
        row = conn.execute("SELECT * FROM transcripts WHERE id=?", (entry["rec_id"],)).fetchone()
    if not row:
        raise HTTPException(404, "Not found.")
    return transcript_download_response(row_to_record(row), entry["format"])


@app.delete("/api/transcripts/{rec_id}")
def api_delete(rec_id: str, x_transcript_owner: Optional[str] = Header(None)) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM transcripts WHERE id=?", (rec_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Not found.")
        require_owner(row, x_transcript_owner)
        conn.execute("DELETE FROM analyses WHERE transcript_id=?", (rec_id,))
        conn.execute("DELETE FROM transcripts WHERE id=?", (rec_id,))
    return {"ok": True}


@app.get("/api/analysis-outputs")
def api_analysis_outputs() -> dict:
    return {"ok": True, "outputs": [{"id": key, "label": ANALYSIS_LABELS[key]} for key in ANALYSIS_OUTPUTS]}


@app.post("/api/analyze/{rec_id}")
def api_analyze(rec_id: str, output_type: str = Form(...), question: Optional[str] = Form(None), x_transcript_owner: Optional[str] = Header(None)) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM transcripts WHERE id=?", (rec_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Transcript not found.")
    require_owner(row, x_transcript_owner)
    rec = row_to_record(row)
    analysis = build_phase3_analysis_text(rec, output_type, question=question)
    saved = save_analysis(
        transcript_id=rec_id,
        output_type=output_type,
        question=question,
        analysis=analysis,
        owner_token=dict(row).get("owner_token") or "",
    )
    return {"ok": True, "analysis_id": saved["id"], "transcript_id": rec_id, "output_type": output_type, "analysis": analysis}


@app.post("/api/analyze-all/{rec_id}")
def api_analyze_all(rec_id: str, x_transcript_owner: Optional[str] = Header(None)) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM transcripts WHERE id=?", (rec_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Transcript not found.")
    require_owner(row, x_transcript_owner)
    rec = row_to_record(row)
    analysis = build_combined_analysis_text(rec)
    saved = save_analysis(
        transcript_id=rec_id,
        output_type="all_outputs",
        question=None,
        analysis=analysis,
        owner_token=dict(row).get("owner_token") or "",
    )
    return {"ok": True, "analysis_id": saved["id"], "transcript_id": rec_id, "output_type": "all_outputs", "analysis": analysis}


@app.get("/api/analysis/{analysis_id}/download")
def api_analysis_download(analysis_id: str, x_transcript_owner: Optional[str] = Header(None)) -> PlainTextResponse:
    with db() as conn:
        row = conn.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Analysis not found.")
    require_owner(row, x_transcript_owner)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", row["output_type"])[:60] or "analysis"
    return PlainTextResponse(row["analysis"], media_type="text/markdown", headers={"Content-Disposition": f'attachment; filename="{safe}.md"'})


@app.post("/api/email/{rec_id}")
def api_email(rec_id: str, x_transcript_owner: Optional[str] = Header(None)) -> dict:
    smtp_host, smtp_port_raw, smtp_user, smtp_pass, owner_email = (os.getenv(k) for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "OWNER_EMAIL"))
    if not all([smtp_host, smtp_port_raw, smtp_user, smtp_pass, owner_email]):
        raise HTTPException(400, "SMTP is not configured. Add SMTP_* and OWNER_EMAIL to .env.")
    with db() as conn:
        row = conn.execute("SELECT * FROM transcripts WHERE id=?", (rec_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Not found.")
    require_owner(row, x_transcript_owner)
    rec = row_to_record(row)
    msg = EmailMessage(); msg["Subject"] = f"[Epic Transcript] {(rec.get('source') or '')[:80]}"; msg["From"] = smtp_user; msg["To"] = owner_email
    msg.set_content(f"Source : {rec.get('source')}\nMethod : {rec.get('method')}\nSaved  : {rec.get('created_at')}\n\n{rec.get('transcript','')}")
    try:
        port = int(smtp_port_raw)
        if port == 465:
            with smtplib.SMTP_SSL(smtp_host, port, timeout=30) as s: s.login(smtp_user, smtp_pass); s.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, port, timeout=30) as s: s.starttls(); s.login(smtp_user, smtp_pass); s.send_message(msg)
    except Exception as e:
        raise HTTPException(502, f"SMTP send failed: {e}")
    return {"ok": True, "to": owner_email}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8090"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
