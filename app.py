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
import time
import secrets
import uuid
from email.message import EmailMessage
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "static"
DB_PATH = DATA_DIR / "transcripts.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env")

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
TEXT_EXTS = {".txt", ".md"}
SUBTITLE_EXTS = {".srt", ".vtt"}
ALLOWED_EXTS = AUDIO_EXTS | VIDEO_EXTS | TEXT_EXTS | SUBTITLE_EXTS
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
MAX_SYNC_YOUTUBE_DURATION_SECONDS = 2 * 60
LONG_VIDEO_MESSAGE = "That video is too long for this synchronous public request. Upload the file or use the next async processing version so it can run without timing out."

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
    return conn


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(transcripts)").fetchall()}


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


def segments_to_transcript(segments: list[dict]) -> str:
    return "\n".join(f"[{seconds_to_timestamp(s.get('start', 0))}] {s.get('text','').strip()}" for s in segments if s.get("text"))


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
    r["provider_attempts"] = attempts
    r["cache_hit"] = cache_hit
    if not r.get("word_count"):
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
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
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
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout or int(os.getenv("LOCAL_WHISPER_TIMEOUT_SECONDS", "90")))
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "Local Whisper transcription failed")
    files = list(out_dir.glob("*.vtt"))
    if files:
        segs = parse_vtt_segments(files[0].read_text(errors="ignore"))
    else:
        segs = parse_whisper_stdout_segments(proc.stdout)
    shutil.rmtree(out_dir, ignore_errors=True)
    if not segs:
        raise RuntimeError("Local Whisper transcript came back empty")
    detected_lang = detected_whisper_language(proc.stdout, proc.stderr)
    return segs, language or detected_lang or "unknown"


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
        segs, lang = transcribe_with_local_whisper(audio_path, language=expected_lang, model=whisper_model, timeout=int(os.getenv("YOUTUBE_WHISPER_TIMEOUT_SECONDS", "35")))
        transcript = segments_to_transcript(segs)
        attempts.append({"provider": "local-whisper", "ok": True, "segments": len(segs), "words": transcript_word_count(transcript)})
        return save_transcript(source=title, source_kind="youtube", method="local-whisper", transcript=transcript,
                               duration_seconds=duration, processing_seconds=time.monotonic() - started,
                               media_id=video_id, source_url=canonical, title=title, creator=creator,
                               language=lang, segments=segs, provider_attempts=attempts, cache_hit=False,
                               owner_token=owner_token)
    except Exception as e:
        attempts.append({"provider": "local-whisper", "ok": False, "error": str(e)[:240]})
        raise RuntimeError(BLOCKED_MESSAGE)


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


@app.get("/", include_in_schema=False)
def root_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "setup": setup_status()}


@app.get("/api/setup")
def api_setup() -> dict:
    return setup_status()


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
        meta_probe = {}
        expected_language = None
        try:
            meta_probe = yt_dlp_metadata(url)
            expected_language = infer_expected_language(meta_probe)
        except Exception:
            meta_probe = {}
        cached = get_cached_transcript(video_id, expected_language=expected_language)
        if cached:
            return JSONResponse({"ok": True, "record": record_for_owner(cached, owner_token)})
        if (meta_probe.get("duration") or 0) > MAX_SYNC_YOUTUBE_DURATION_SECONDS:
            raise HTTPException(422, LONG_VIDEO_MESSAGE)
        work_dir = Path(tempfile.mkdtemp(prefix="epic-youtube-"))
        try:
            return JSONResponse({"ok": True, "record": transcribe_youtube_uncached(url, video_id, started, work_dir, owner_token=owner_token, meta=meta_probe)})
        except RuntimeError as e:
            raise HTTPException(422, str(e))
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

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
        rec = save_transcript(source=title, source_kind="url", method=method, transcript=transcript,
                              duration_seconds=meta.get("duration"), processing_seconds=time.monotonic() - started,
                              media_id=meta.get("id"), source_url=meta.get("webpage_url") or url,
                              title=title, creator=meta.get("uploader") or meta.get("channel"), language=lang,
                              segments=segs, provider_attempts=attempts, owner_token=owner_token)
        return JSONResponse({"ok": True, "record": rec})
    except RuntimeError:
        # Non-YouTube sources are Phase 2 territory. Keep the error helpful for visitors.
        raise HTTPException(422, "That link is not available for automatic transcription yet. If you have the video or audio file, upload it here and we’ll take another route.")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

@app.post("/api/transcribe-upload")
def api_transcribe_upload(file: UploadFile = File(...), owner: Optional[str] = Form(None)) -> JSONResponse:
    name = file.filename or "upload"
    owner_token = valid_owner_token(owner) or secrets.token_urlsafe(32)
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(400, f"Unsupported file type: {ext or '(none)'}")
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
                              duration_seconds=None, processing_seconds=time.monotonic() - started,
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
    else:
        body, media, ext = rec.get("transcript", ""), "text/plain", "txt"
    return PlainTextResponse(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{safe}.{ext}"'})


@app.post("/api/transcripts/{rec_id}/download-link")
def api_download_link(request: Request, rec_id: str, format: str = Query("txt", pattern="^(txt|md|srt)$"), x_transcript_owner: Optional[str] = Header(None)) -> dict:
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
        conn.execute("DELETE FROM transcripts WHERE id=?", (rec_id,))
    return {"ok": True}

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
