"""YouTube captions only. No speech model and no paid transcription API."""
from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi

PUBLIC_BOT = (
    "YouTube refused this server: Sign in to confirm you're not a bot. "
    "This runtime did not use cookies, a proxy, or a paid transcription service."
)
PUBLIC_NO_CAPTIONS = (
    "No captions were available for that video. "
    "This free runtime does not run a speech model and does not call a paid transcription service."
)
PUBLIC_GENERIC = "Could not transcribe that YouTube link."
PUBLIC_TOOL_MISSING = "This server is missing yt-dlp or ffmpeg, so it cannot read that video."

_BOT_MARKERS = (
    "sign in to confirm",
    "not a bot",
    "requestblocked",
    "login_required",
    "blocking requests from your ip",
    "ip has been blocked",
)


class CaptionError(Exception):
    def __init__(self, public: str, upstream: str) -> None:
        super().__init__(public)
        self.public = public
        self.upstream = upstream


def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def is_bot_wall(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _BOT_MARKERS)


def public_transcription_error(upstream: str) -> str:
    if is_bot_wall(upstream):
        return PUBLIC_BOT
    if "yt-dlp" in (upstream or "").lower() and "not found" in (upstream or "").lower():
        return PUBLIC_TOOL_MISSING
    if "no captions" in (upstream or "").lower() or "no usable" in (upstream or "").lower():
        return PUBLIC_NO_CAPTIONS
    return PUBLIC_GENERIC


def extract_video_id(url: str) -> str:
    raw = (url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise CaptionError("Paste an https YouTube link.", "rejected url scheme or userinfo")
    host = (parsed.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        bare = host[4:]
    else:
        bare = host
    allowed = {"youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "youtube-nocookie.com"}
    if host not in allowed and bare not in {"youtube.com", "youtu.be", "youtube-nocookie.com"}:
        raise CaptionError("Paste a YouTube link. Other sites are not accepted by this server.", f"rejected host {host}")
    video_id = ""
    if bare == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    else:
        query = parse_qs(parsed.query)
        if query.get("v"):
            video_id = query["v"][0]
        else:
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live", "v"}:
                video_id = parts[1]
    if not re.fullmatch(r"[0-9A-Za-z_-]{11}", video_id or ""):
        raise CaptionError("That YouTube link has no video id.", "missing video id")
    return video_id


def normalize_youtube_url(url: str) -> str:
    return f"https://www.youtube.com/watch?v={extract_video_id(url)}"


def resolve_binary(name: str, env_name: str) -> Optional[str]:
    override = os.environ.get(env_name, "").strip()
    if override:
        return override
    found = shutil.which(name)
    if found:
        return found
    sibling = Path(sys.executable).with_name(name)
    if sibling.is_file() and os.access(sibling, os.X_OK):
        return str(sibling)
    return None


def parse_timestamp(ts: str) -> float:
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        hours, minutes, seconds = "0", parts[0], parts[1]
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def seconds_to_timestamp(seconds: float) -> str:
    whole = max(0, int(float(seconds)))
    hours, rem = divmod(whole, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _clean_caption_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\{\\.*?\}", "", text)
    text = html.unescape(text)
    return clean_whitespace(text)


def parse_vtt_segments(raw: str) -> list[dict]:
    lines = (raw or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    segments: list[dict] = []
    index = 0
    stamp = re.compile(
        r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[\.,]\d{3})\s*-->\s*(?P<end>\d{1,2}:\d{2}(?::\d{2})?[\.,]\d{3})"
    )
    while index < len(lines):
        match = stamp.search(lines[index])
        if not match and index + 1 < len(lines):
            match = stamp.search(lines[index + 1])
            if match:
                index += 1
        if not match:
            index += 1
            continue
        start = parse_timestamp(match.group("start"))
        end = parse_timestamp(match.group("end"))
        index += 1
        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            text_lines.append(lines[index])
            index += 1
        text = _clean_caption_text(" ".join(text_lines))
        if text and (not segments or text != segments[-1]["text"] or start != segments[-1]["start"]):
            segments.append({"start": start, "end": end, "text": text})
        index += 1
    return segments


def parse_srt_segments(raw: str) -> list[dict]:
    blocks = re.split(r"\n\s*\n", (raw or "").replace("\r\n", "\n"))
    segments: list[dict] = []
    stamp = re.compile(
        r"(?P<start>\d{1,2}:\d{2}:\d{2}[\.,]\d{3})\s*-->\s*(?P<end>\d{1,2}:\d{2}:\d{2}[\.,]\d{3})"
    )
    for block in blocks:
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        offset = 1 if lines[0].strip().isdigit() and len(lines) > 1 else 0
        if offset >= len(lines):
            continue
        match = stamp.search(lines[offset])
        if not match:
            continue
        text = _clean_caption_text(" ".join(lines[offset + 1:]))
        if text:
            segments.append({
                "start": parse_timestamp(match.group("start")),
                "end": parse_timestamp(match.group("end")),
                "text": text,
            })
    return segments


def remove_leading_word_overlap(previous_text: str, next_text: str, max_words: int = 20) -> str:
    prev_words = clean_whitespace(previous_text).split()
    next_words = clean_whitespace(next_text).split()
    if not prev_words or not next_words:
        return clean_whitespace(next_text)

    def norm(words: list[str]) -> list[str]:
        return [word.lower().strip(",.?!;:\"'()[]") for word in words]

    prev_norm = norm(prev_words)
    next_norm = norm(next_words)
    overlap = 0
    for size in range(min(len(prev_norm), len(next_norm), max_words), 0, -1):
        if prev_norm[-size:] == next_norm[:size]:
            overlap = size
            break
    return clean_whitespace(" ".join(next_words[overlap:]))


def segments_to_transcript(segments: list[dict]) -> str:
    lines: list[str] = []
    previous = ""
    for segment in segments:
        raw_text = clean_whitespace(segment.get("text", ""))
        if not raw_text:
            continue
        text = remove_leading_word_overlap(previous, raw_text)
        previous = clean_whitespace((previous + " " + text).strip())[-1200:]
        if text:
            lines.append(f"[{seconds_to_timestamp(segment.get('start', 0))}] {text}")
    return "\n".join(lines)


def transcript_word_count(text: str) -> int:
    body = re.sub(r"\[\d{1,2}:\d{2}(?::\d{2})?\]", " ", text or "")
    return len(re.findall(r"\b[\w'’-]+\b", body))


def _yt_dlp_base(ffmpeg_bin: str) -> list[str]:
    yt_dlp_bin = resolve_binary("yt-dlp", "YT_DLP_BIN")
    if not yt_dlp_bin:
        raise CaptionError(PUBLIC_TOOL_MISSING, "yt-dlp not found")
    cmd = [yt_dlp_bin, "--ignore-config", "--no-warnings", "--ffmpeg-location", str(Path(ffmpeg_bin).parent)]
    node = shutil.which("node")
    if node:
        cmd.extend(["--js-runtimes", f"node:{node}"])
    return cmd


def _caption_timeout() -> int:
    raw = os.environ.get("CAPTION_TIMEOUT_SECONDS", "60").strip()
    try:
        value = int(raw)
    except ValueError:
        return 60
    return value if value > 0 else 60


def yt_dlp_caption_segments(url: str, work_dir: Path, ffmpeg_bin: str) -> tuple[list[dict], str]:
    work_dir.mkdir(parents=True, exist_ok=True)
    template = str(work_dir / "captions.%(ext)s")
    cmd = _yt_dlp_base(ffmpeg_bin) + [
        "--skip-download",
        "--write-sub",
        "--write-auto-sub",
        "--sub-format", "vtt/srt/best",
        "--sub-langs", "en.*,en",
        "-o", template,
        url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_caption_timeout())
    except subprocess.TimeoutExpired as exc:
        raise CaptionError(PUBLIC_GENERIC, "yt-dlp subtitle extraction timed out") from exc
    upstream = "\n".join(part for part in (proc.stderr, proc.stdout) if part).strip()
    candidates = sorted(work_dir.glob("captions*.vtt")) + sorted(work_dir.glob("captions*.srt"))
    if proc.returncode != 0 or not candidates:
        detail = upstream or f"yt-dlp exit {proc.returncode} with no captions"
        if is_bot_wall(detail):
            raise CaptionError(PUBLIC_BOT, detail)
        raise CaptionError(PUBLIC_NO_CAPTIONS, detail)
    raw = candidates[0].read_text(errors="ignore")
    segments = parse_vtt_segments(raw) if candidates[0].suffix == ".vtt" else parse_srt_segments(raw)
    if not segments:
        raise CaptionError(PUBLIC_NO_CAPTIONS, "yt-dlp captions parsed empty")
    return segments, "native-caption-yt-dlp"


def youtube_transcript_api_segments(video_id: str) -> tuple[list[dict], str]:
    try:
        fetched = YouTubeTranscriptApi().fetch(video_id)
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        if is_bot_wall(detail):
            raise CaptionError(PUBLIC_BOT, detail) from exc
        raise CaptionError(PUBLIC_NO_CAPTIONS, detail) from exc
    segments: list[dict] = []
    for item in fetched:
        start = float(getattr(item, "start", 0))
        duration = float(getattr(item, "duration", 0))
        text = _clean_caption_text(getattr(item, "text", ""))
        if text:
            segments.append({"start": start, "end": start + duration, "text": text})
    if not segments:
        raise CaptionError(PUBLIC_NO_CAPTIONS, "youtube-transcript-api returned no text")
    language = getattr(fetched, "language_code", None) or "unknown"
    return segments, f"native-caption-youtube-transcript-api-{language}"


def transcribe_youtube_url(url: str, work_dir: Path, ffmpeg_bin: Optional[str] = None) -> dict:
    normalized = normalize_youtube_url(url)
    video_id = extract_video_id(normalized)
    ffmpeg = ffmpeg_bin or resolve_binary("ffmpeg", "FFMPEG_BIN")
    if not ffmpeg:
        raise CaptionError(PUBLIC_TOOL_MISSING, "ffmpeg not found")
    errors: list[str] = []
    try:
        segments, method = yt_dlp_caption_segments(normalized, work_dir, ffmpeg)
    except CaptionError as exc:
        errors.append(exc.upstream)
        if exc.public == PUBLIC_BOT:
            # A second client will not get past the same IP block. Still try the
            # transcript API once; it uses a different request and sometimes differs.
            pass
        try:
            segments, method = youtube_transcript_api_segments(video_id)
        except CaptionError as second:
            errors.append(second.upstream)
            public = PUBLIC_BOT if any(is_bot_wall(item) for item in errors) else second.public
            if public == PUBLIC_GENERIC and any("no caption" in item.lower() or "parsed empty" in item.lower() for item in errors):
                public = PUBLIC_NO_CAPTIONS
            raise CaptionError(public, "\n".join(errors)) from second
    transcript = segments_to_transcript(segments)
    if not transcript.strip():
        raise CaptionError(PUBLIC_NO_CAPTIONS, "caption segments produced an empty transcript")
    duration = max(float(segment.get("end") or segment.get("start") or 0) for segment in segments)
    return {
        "source": normalized,
        "source_kind": "youtube",
        "video_id": video_id,
        "method": method,
        "transcript": transcript,
        "segments": segments,
        "word_count": transcript_word_count(transcript),
        "duration_seconds": round(duration, 3),
        "language": "en",
    }
