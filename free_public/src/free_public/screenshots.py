"""Free local screenshot capture for transcript jobs (yt-dlp + ffmpeg only).

Defaults follow /workspace/merlin/ideas/yt-tTruM2VB9C0/VISUAL-OPTIONS-PLAN-2026-11-05.md
and frames/PROOF-NOTES.md: 360p download, scene threshold 0.30, forced opener at
t=1s, 2s min-gap that ignores fades, hybrid grab every 9s on static screens, and
conservative perceptual dedupe that keeps same-template slides (10 vs 11).
"""
from __future__ import annotations

import csv
import logging
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Callable, Optional

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
SAFE_FRAME_NAME = re.compile(r"^frame_\d{4}_\d+\.\d{2}s\.jpg$")
SHOWINFO_TIME = re.compile(r"pts_time:([0-9.]+)")
PUBLIC_SCREENSHOT_ERROR = "Screenshots could not be captured."


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


def yt_dlp_prefix(yt_dlp_bin: str, ffmpeg_bin: str) -> list[str]:
    """yt-dlp invocation that ignores local config and enables Node when present.

    ``--ignore-config`` keeps cookies, proxies, and netrc files out of a public process.
    Node is the documented YouTube JS runtime for current yt-dlp. It does not bypass a bot wall.
    """
    cmd = [
        yt_dlp_bin,
        "--ignore-config",
        "--no-warnings",
        "--ffmpeg-location", str(Path(ffmpeg_bin).parent),
    ]
    node = shutil.which("node")
    if node:
        cmd.extend(["--js-runtimes", f"node:{node}"])
    return cmd


def _timeout_seconds(env_name: str, default: int) -> int:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def download_360p(url: str, work_dir: Path, yt_dlp_bin: str, ffmpeg_bin: str, timeout: int = 300) -> Path:
    timeout = _timeout_seconds("SCREENSHOT_DOWNLOAD_TIMEOUT", timeout)
    dest = work_dir / "video-360p.mp4"
    attempts = [
        {"extractor": None, "fmt": YT_DLP_FORMAT},
        {"extractor": "youtube:player_client=android", "fmt": YT_DLP_FORMAT + "/18"},
    ]
    for attempt in attempts:
        if dest.exists():
            dest.unlink()
        cmd = yt_dlp_prefix(yt_dlp_bin, ffmpeg_bin)
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
        capture_output=True, text=True, timeout=_timeout_seconds("SCREENSHOT_SCENE_TIMEOUT", 180),
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
        capture_output=True, text=True, timeout=_timeout_seconds("SCREENSHOT_SCENE_TIMEOUT", 180),
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
    raw_dir = out_dir / "_raw"
    if progress:
        progress("Detecting scene changes")
    scene_frames = extract_scene_frames(ffmpeg_bin, video, raw_dir, threshold)
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
    return (root / job_id).resolve()


def safe_frame_path(job_dir: Path, filename: str) -> Path:
    name = Path(filename or "").name
    if not SAFE_FRAME_NAME.match(name):
        raise ValueError("invalid screenshot name")
    path = (job_dir / name).resolve()
    if path.parent != job_dir.resolve():
        raise ValueError("invalid screenshot path")
    return path
