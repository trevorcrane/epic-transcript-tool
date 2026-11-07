"""Free local screenshot capture for transcript jobs (yt-dlp + ffmpeg only).

Defaults follow /workspace/merlin/ideas/yt-tTruM2VB9C0/VISUAL-OPTIONS-PLAN-2026-11-05.md
and frames/PROOF-NOTES.md: 360p download, scene threshold 0.30, forced opener at
t=1s, 2s min-gap that ignores fades, hybrid grab every 9s on static screens, and
conservative perceptual dedupe that keeps same-template slides (10 vs 11).
"""
from __future__ import annotations

import csv
import ipaddress
import logging
import os
import re
import socket
import subprocess
import zipfile
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

LOGGER = logging.getLogger("epic-screenshots")

SCENE_THRESHOLD = 0.30
OPENER_SECONDS = 1.0
MIN_GAP_SECONDS = 2.0
HYBRID_GAP_SECONDS = 9.0
MIN_FILE_BYTES = 2500
UI_CAP = 200
HASH_SIZE = 8
# Hamming <= 6 on full-frame average-hash collapsed slide 10 into slide 11.
# Keep a conservative full-frame distance and require the slide body to match too.
FULL_HASH_MAX_DISTANCE = 4
BODY_HASH_MAX_DISTANCE = 4
NEAR_BLACK = 12
NEAR_WHITE = 243
JPEG_QUALITY = 3
YT_DLP_FORMAT = "bestvideo[height<=360][ext=mp4]/134/best[height<=360]"
YOUTUBE_VIDEO_ID = re.compile(r"^[0-9A-Za-z_-]{11}$")
SAFE_FRAME_NAME = re.compile(r"^frame_\d{4}_\d+\.\d{2}s\.jpg$")
SHOWINFO_TIME = re.compile(r"pts_time:([0-9.]+)")
PUBLIC_SCREENSHOT_ERROR = "Screenshots could not be captured."
MAX_RAW_FRAMES = 400
BLOCKED_SCREENSHOT_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata",
    "metadata.google.internal",
}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def screenshot_max_seconds() -> int:
    return max(1, _env_int("SCREENSHOT_MAX_SECONDS", 7200))


def screenshot_max_download_mb() -> int:
    return max(1, _env_int("SCREENSHOT_MAX_DOWNLOAD_MB", 800))


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _reject_public_ip(value: str) -> None:
    ip = ipaddress.ip_address(value)
    if any((
        ip.is_private,
        ip.is_loopback,
        ip.is_link_local,
        ip.is_multicast,
        ip.is_reserved,
        ip.is_unspecified,
    )):
        raise ValueError("screenshot URL resolves to a non-public address")


def public_http_url(url: str) -> str:
    """Accept only http(s) URLs that resolve to public addresses.

    Transcript-only jobs keep the existing URL check. Screenshot download refuses
    credentials, non-web ports, local names, and private, loopback, or link-local
    addresses so a screenshot request cannot be aimed at the machine itself.
    """
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("screenshot URL must be http or https")
    if parsed.username or parsed.password or "@" in parsed.netloc:
        raise ValueError("screenshot URL must not include credentials")
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if (
        not host
        or host in BLOCKED_SCREENSHOT_HOSTS
        or host.endswith(".local")
        or host.endswith(".localhost")
        or host.endswith(".internal")
        or host.isdigit()
    ):
        raise ValueError("screenshot URL host is not public")
    if parsed.port not in (None, 80, 443):
        raise ValueError("screenshot URL port is not allowed")
    if _is_ip_literal(host):
        _reject_public_ip(host)
    else:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError("screenshot URL host did not resolve") from exc
        if not infos:
            raise ValueError("screenshot URL host did not resolve")
        for info in infos:
            _reject_public_ip(info[4][0])
    return (url or "").strip()


def canonical_youtube_watch_url(url: str) -> str:
    """Rebuild a YouTube link as https://www.youtube.com/watch?v=ID.

    Screenshot download is not a general URL fetcher. Visitor query strings,
    open-redirect paths, credentials, and non-YouTube hosts are dropped here,
    before DNS or yt-dlp. Only the 11-character video id is kept.
    """
    raw = (url or "").strip()
    if not raw or any(ord(ch) < 32 or ch in " \t\\" for ch in raw):
        raise ValueError("screenshot download is limited to a YouTube video")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("screenshot download is limited to a YouTube video")
    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        raise ValueError("screenshot URL must not include credentials")
    if parsed.port not in (None, 80, 443):
        raise ValueError("screenshot URL port is not allowed")
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    labels = host.split(".") if host else []
    if labels and labels[0] in {"www", "m"}:
        host = ".".join(labels[1:])
    video_id = None
    if host in {"youtube.com", "music.youtube.com"}:
        path = parsed.path or "/"
        if path.rstrip("/") == "/watch":
            found = parse_qs(parsed.query).get("v") or []
            if len(found) == 1 and YOUTUBE_VIDEO_ID.fullmatch(found[0] or ""):
                video_id = found[0]
        else:
            parts = [part for part in path.split("/") if part]
            if len(parts) == 2 and parts[0] in {"shorts", "embed", "live"} and YOUTUBE_VIDEO_ID.fullmatch(parts[1]):
                video_id = parts[1]
    elif host == "youtu.be":
        parts = [part for part in (parsed.path or "").split("/") if part]
        if len(parts) == 1 and YOUTUBE_VIDEO_ID.fullmatch(parts[0]):
            video_id = parts[0]
    else:
        raise ValueError("screenshot download is limited to YouTube")
    if not video_id:
        raise ValueError("screenshot download is limited to a YouTube video")
    return f"https://www.youtube.com/watch?v={video_id}"


def cap_frames(frames: list[dict], limit: int) -> list[dict]:
    """Keep a bounded, time-spread set and delete the JPEG files that are dropped."""
    if limit < 1 or len(frames) <= limit:
        return frames
    if limit == 1:
        picked_indexes = {0}
    else:
        picked_indexes = {round(i * (len(frames) - 1) / (limit - 1)) for i in range(limit)}
    kept = []
    for idx, frame in enumerate(frames):
        if idx in picked_indexes:
            kept.append(frame)
            continue
        Path(frame["path"]).unlink(missing_ok=True)
    return kept


def format_timestamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    whole = int(seconds)
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def frame_filename(index: int, seconds: float) -> str:
    return f"frame_{index:04d}_{seconds:07.2f}s.jpg"


def media_duration_seconds(ffmpeg_bin: str, video: Path) -> float:
    ffprobe = Path(ffmpeg_bin).with_name("ffprobe")
    probe = str(ffprobe if ffprobe.exists() else "ffprobe")
    proc = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError("could not read video duration")
    return float((proc.stdout or "").strip().splitlines()[0])


def download_360p(url: str, work_dir: Path, yt_dlp_bin: str, ffmpeg_bin: str, timeout: int = 300) -> Path:
    url = canonical_youtube_watch_url(url)
    public_http_url(url)
    dest = work_dir / "video-360p.mp4"
    attempts = [
        {"extractor": None, "fmt": YT_DLP_FORMAT},
        {"extractor": "youtube:player_client=android", "fmt": YT_DLP_FORMAT + "/18"},
    ]
    max_size = f"{screenshot_max_download_mb()}M"
    for attempt in attempts:
        if dest.exists():
            dest.unlink()
        cmd = [
            yt_dlp_bin,
            "--ffmpeg-location", str(Path(ffmpeg_bin).parent),
            "--no-warnings",
            "--use-extractors", "youtube",
            "--no-playlist",
            "--no-progress",
            "--max-filesize", max_size,
            "--socket-timeout", "20",
            "--retries", "2",
            "--fragment-retries", "2",
        ]
        if attempt["extractor"]:
            cmd.extend(["--extractor-args", attempt["extractor"]])
        cmd.extend(["-f", attempt["fmt"], "-o", str(dest), url])
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode == 0 and dest.exists() and dest.stat().st_size >= 1024:
            return dest
        LOGGER.warning("360p download attempt failed (client=%s)", attempt["extractor"] or "default")
    raise RuntimeError("360p video download failed")


def grab_frame_at(ffmpeg_bin: str, video: Path, seconds: float, dest: Path) -> Optional[Path]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-loglevel", "error",
         "-ss", f"{seconds:.3f}", "-i", str(video),
         "-frames:v", "1", "-update", "1", "-q:v", str(JPEG_QUALITY), "-y", str(dest)],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0 or not dest.exists() or dest.stat().st_size < 32:
        return None
    return dest


def extract_scene_frames(ffmpeg_bin: str, video: Path, tmp_dir: Path, threshold: float = SCENE_THRESHOLD) -> list[dict]:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    pattern = tmp_dir / "scene_%04d.jpg"
    vf = f"select='gt(scene\\,{threshold:.2f})',showinfo"
    proc = subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-i", str(video),
         "-vf", vf, "-vsync", "vfr", "-q:v", str(JPEG_QUALITY), str(pattern)],
        capture_output=True, text=True, timeout=180,
    )
    times = [float(match.group(1)) for match in SHOWINFO_TIME.finditer((proc.stderr or "") + (proc.stdout or ""))]
    files = sorted(tmp_dir.glob("scene_*.jpg"))
    if len(times) != len(files):
        LOGGER.warning("scene extract count mismatch: %s times vs %s files", len(times), len(files))
    frames = []
    for seconds, path in zip(times, files):
        frames.append({
            "time": round(seconds, 2),
            "timestamp": format_timestamp(seconds),
            "path": path,
        })
    return frames


def extract_scene_times(ffmpeg_bin: str, video: Path, threshold: float = SCENE_THRESHOLD) -> list[float]:
    vf = f"select='gt(scene\\,{threshold:.2f})',showinfo"
    proc = subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-i", str(video),
         "-vf", vf, "-vsync", "vfr", "-f", "null", "-"],
        capture_output=True, text=True, timeout=180,
    )
    return [float(match.group(1)) for match in SHOWINFO_TIME.finditer((proc.stderr or "") + (proc.stdout or ""))]


def _gray_bytes(ffmpeg_bin: str, image: Path, width: int, height: int, vf: str) -> Optional[bytes]:
    proc = subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-loglevel", "error",
         "-i", str(image), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"],
        capture_output=True, timeout=20,
    )
    expected = width * height
    if proc.returncode != 0 or len(proc.stdout) < expected:
        return None
    return proc.stdout[:expected]


def average_hash(ffmpeg_bin: str, image: Path, hash_size: int = HASH_SIZE, vf: Optional[str] = None) -> Optional[int]:
    filt = vf or f"scale={hash_size}:{hash_size}"
    raw = _gray_bytes(ffmpeg_bin, image, hash_size, hash_size, filt)
    if not raw:
        return None
    avg = sum(raw) / len(raw)
    bits = 0
    for pixel in raw:
        bits = (bits << 1) | (1 if pixel >= avg else 0)
    return bits


def body_hash(ffmpeg_bin: str, image: Path, hash_size: int = HASH_SIZE) -> Optional[int]:
    # Compare the lower 65% so a shared cream header does not collapse two slides.
    vf = f"crop=iw:ih*0.65:0:ih*0.35,scale={hash_size}:{hash_size}"
    return average_hash(ffmpeg_bin, image, hash_size, vf)


def hamming(a: Optional[int], b: Optional[int]) -> int:
    if a is None or b is None:
        return 64
    return (a ^ b).bit_count()


def mean_luminance(ffmpeg_bin: str, image: Path) -> Optional[float]:
    raw = _gray_bytes(ffmpeg_bin, image, 16, 16, "scale=16:16")
    if not raw:
        return None
    return sum(raw) / len(raw)


def is_blank_or_tiny(ffmpeg_bin: str, image: Path) -> bool:
    try:
        size = image.stat().st_size
    except OSError:
        return True
    if size < MIN_FILE_BYTES:
        return True
    mean = mean_luminance(ffmpeg_bin, image)
    if mean is None:
        return False
    return mean <= NEAR_BLACK or mean >= NEAR_WHITE


def hybrid_sample_times(scene_times: list[float], duration: float, interval: float = HYBRID_GAP_SECONDS) -> list[float]:
    points = sorted(scene_times)
    extras: list[float] = []
    boundaries = [0.0] + points + [max(duration, points[-1] if points else 0.0)]
    for start, end in zip(boundaries, boundaries[1:]):
        t = start + interval
        while t < end - 0.25:
            extras.append(round(t, 2))
            t += interval
    return extras


def apply_min_gap(frames: list[dict], ffmpeg_bin: str, min_gap: float = MIN_GAP_SECONDS) -> list[dict]:
    kept: list[dict] = []
    last_content_time: Optional[float] = None
    for frame in sorted(frames, key=lambda item: item["time"]):
        path = Path(frame["path"])
        if not path.exists():
            continue
        blank = is_blank_or_tiny(ffmpeg_bin, path)
        frame = {**frame, "blank": blank}
        if blank:
            path.unlink(missing_ok=True)
            continue
        if last_content_time is not None and (frame["time"] - last_content_time) < min_gap:
            # Prefer the later frame in a tight cluster (new slide after a cut).
            # Keeping the earlier one dropped slide 10 at 977.88s, 1s after 976.88s.
            prev = kept.pop()
            Path(prev["path"]).unlink(missing_ok=True)
            kept.append(frame)
            last_content_time = frame["time"]
            continue
        kept.append(frame)
        last_content_time = frame["time"]
    return kept


def dedupe_frames(frames: list[dict], ffmpeg_bin: str) -> list[dict]:
    kept: list[dict] = []
    for frame in frames:
        path = Path(frame["path"])
        full = average_hash(ffmpeg_bin, path)
        body = body_hash(ffmpeg_bin, path)
        frame = {**frame, "full_hash": full, "body_hash": body}
        duplicate = False
        for prev in kept:
            if (
                hamming(full, prev.get("full_hash")) <= FULL_HASH_MAX_DISTANCE
                and hamming(body, prev.get("body_hash")) <= BODY_HASH_MAX_DISTANCE
            ):
                duplicate = True
                break
        if duplicate:
            path.unlink(missing_ok=True)
            continue
        kept.append(frame)
    return kept


def write_manifest(frames: list[dict], dest: Path) -> None:
    with dest.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["index", "time", "timestamp", "filename"])
        for idx, frame in enumerate(frames, start=1):
            writer.writerow([idx, f"{frame['time']:.2f}", frame["timestamp"], Path(frame["path"]).name])


def build_zip(frames: list[dict], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for frame in frames:
            path = Path(frame["path"])
            if path.exists():
                zf.write(path, arcname=path.name)
        manifest = dest.parent / "manifest.csv"
        if manifest.exists():
            zf.write(manifest, arcname="manifest.csv")
    return dest


def _unique_times(*groups: list[float]) -> list[float]:
    seen = set()
    out = []
    for group in groups:
        for raw in group:
            t = round(float(raw), 2)
            if t < 0 or t in seen:
                continue
            seen.add(t)
            out.append(t)
    return sorted(out)


def capture_from_video(
    video: Path,
    out_dir: Path,
    ffmpeg_bin: str,
    threshold: float = SCENE_THRESHOLD,
    progress: Optional[Callable[[str], None]] = None,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = media_duration_seconds(ffmpeg_bin, video)
    if duration > screenshot_max_seconds():
        raise RuntimeError("video is longer than the screenshot limit")
    raw_dir = out_dir / "_raw"
    if progress:
        progress("Detecting scene changes")
    scene_frames = extract_scene_frames(ffmpeg_bin, video, raw_dir, threshold)
    if len(scene_frames) > MAX_RAW_FRAMES:
        scene_frames = cap_frames(scene_frames, MAX_RAW_FRAMES)
    scene_times = [frame["time"] for frame in scene_frames]
    times = _unique_times(
        [OPENER_SECONDS] if duration >= OPENER_SECONDS else ([0.0] if duration > 0 else []),
        scene_times,
        hybrid_sample_times(scene_times + [OPENER_SECONDS], duration),
    )
    raw_frames = list(scene_frames)
    have = {frame["time"] for frame in raw_frames}
    if progress:
        progress("Saving extra frames")
    for seconds in times:
        if any(abs(seconds - existing) < 0.15 for existing in have):
            continue
        dest = raw_dir / frame_filename(len(raw_frames), seconds)
        saved = grab_frame_at(ffmpeg_bin, video, seconds, dest)
        if saved:
            raw_frames.append({
                "time": seconds,
                "timestamp": format_timestamp(seconds),
                "path": saved,
            })
            have.add(seconds)
    cleaned = apply_min_gap(raw_frames, ffmpeg_bin)
    cleaned = dedupe_frames(cleaned, ffmpeg_bin)
    cleaned = cap_frames(cleaned, UI_CAP)
    # Rename in time order after cleanup so filenames stay sequential.
    renamed = []
    for idx, frame in enumerate(cleaned):
        dest = out_dir / frame_filename(idx, frame["time"])
        src = Path(frame["path"])
        if src.resolve() != dest.resolve():
            if dest.exists():
                dest.unlink()
            src.replace(dest)
        renamed.append({**frame, "path": dest, "filename": dest.name})
    raw_dir = out_dir / "_raw"
    if raw_dir.exists():
        for leftover in raw_dir.glob("*"):
            try:
                leftover.unlink()
            except OSError:
                pass
        raw_dir.rmdir()
    write_manifest(renamed, out_dir / "manifest.csv")
    zip_path = build_zip(renamed, out_dir / "screenshots.zip")
    return {
        "status": "done",
        "error": None,
        "duration": duration,
        "count": len(renamed),
        "frames": renamed,
        "zip_path": zip_path,
        "raw_scene_count": len(scene_times),
    }


def capture_from_url(
    url: str,
    out_dir: Path,
    yt_dlp_bin: str,
    ffmpeg_bin: str,
    work_dir: Optional[Path] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> dict:
    url = canonical_youtube_watch_url(url)
    public_http_url(url)
    scratch = Path(work_dir or out_dir / "_download")
    scratch.mkdir(parents=True, exist_ok=True)
    try:
        if progress:
            progress("Downloading video for screenshots")
        video = download_360p(url, scratch, yt_dlp_bin, ffmpeg_bin)
        return capture_from_video(video, out_dir, ffmpeg_bin, progress=progress)
    finally:
        for leftover in scratch.glob("*"):
            try:
                leftover.unlink()
            except OSError:
                pass


def public_payload(job_id: str, result: dict, ui_cap: int = UI_CAP) -> dict:
    frames = result.get("frames") or []
    shown = []
    for frame in frames[:ui_cap]:
        name = Path(frame["path"]).name if frame.get("path") else frame.get("filename")
        if not name or not SAFE_FRAME_NAME.match(name):
            continue
        shown.append({
            "time": frame["time"],
            "timestamp": frame["timestamp"],
            "filename": name,
            "url": f"/api/jobs/{job_id}/screenshots/{name}",
        })
    payload = {
        "status": result.get("status") or "done",
        "error": result.get("error"),
        "count": result.get("count") or len(frames),
        "shown": len(shown),
        "frames": shown,
        "zip_url": f"/api/jobs/{job_id}/screenshots.zip" if frames else None,
    }
    return payload


def screenshot_error_payload() -> dict:
    return {
        "status": "error",
        "error": PUBLIC_SCREENSHOT_ERROR,
        "count": 0,
        "shown": 0,
        "frames": [],
        "zip_url": None,
    }


def safe_job_dir(root: Path, job_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{12}", job_id or ""):
        raise ValueError("invalid job id")
    root_resolved = root.resolve()
    path = (root_resolved / job_id).resolve()
    if path.parent != root_resolved:
        raise ValueError("invalid job dir")
    return path


def safe_frame_path(job_dir: Path, filename: str) -> Path:
    name = Path(filename or "").name
    if not SAFE_FRAME_NAME.match(name):
        raise ValueError("invalid screenshot name")
    path = (job_dir / name).resolve()
    if path.parent != job_dir.resolve():
        raise ValueError("invalid screenshot path")
    return path
