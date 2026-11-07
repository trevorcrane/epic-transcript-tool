"""Synthetic screenshot tests. Proof frames from another machine are skipped when absent."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from free_public.screenshots import (
    BODY_HASH_MAX_DISTANCE,
    apply_min_gap,
    average_hash,
    body_hash,
    capture_from_video,
    dedupe_frames,
    format_timestamp,
    hamming,
    hybrid_sample_times,
)


def ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    assert path, "ffmpeg must be installed for screenshot tests"
    return path


def write_color_clip(path: Path, color: str, seconds: float, size: str = "640x360") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c={color}:s={size}:d={seconds}:r=24",
         "-vf", "drawbox=x=40:y=40:w=560:h=280:color=white:t=fill,drawbox=x=80:y=80:w=200:h=140:color=black:t=fill",
         "-pix_fmt", "yuv420p", "-y", str(path)],
        check=True, timeout=30,
    )


def write_pattern_clip(path: Path, source: str, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"{source}=size=640x360:rate=24:duration={seconds}",
         "-pix_fmt", "yuv420p", "-y", str(path)],
        check=True, timeout=30,
    )


def concat_clips(clips: list[Path], dest: Path) -> None:
    listing = dest.with_suffix(".txt")
    listing.write_text("".join(f"file '{clip}'\n" for clip in clips))
    subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c", "copy", "-y", str(dest)],
        check=True, timeout=30,
    )


def write_slide(path: Path, header: str, body: str, layout: str = "a") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Shared cream header; different body bar layouts stand in for different slide text.
    if layout == "a":
        bars = "drawbox=x=60:y=160:w=420:h=22:color=white:t=fill,drawbox=x=60:y=200:w=280:h=18:color=white:t=fill"
    else:
        bars = "drawbox=x=90:y=150:w=180:h=26:color=white:t=fill,drawbox=x=90:y=200:w=460:h=20:color=white:t=fill,drawbox=x=90:y=250:w=220:h=16:color=black:t=fill"
    subprocess.run(
        [
            ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={header}:s=640x360:d=1",
            "-vf", (
                "drawbox=x=0:y=0:w=640:h=90:color=0xF5E6C8:t=fill,"
                f"drawbox=x=40:y=130:w=560:h=170:color={body}:t=fill,"
                + bars
            ),
            "-frames:v", "1", "-update", "1", "-q:v", "3", "-y", str(path),
        ],
        check=True, timeout=20,
    )


def test_format_timestamp():
    assert format_timestamp(1) == "0:01"
    assert format_timestamp(977.88) == "16:17"
    assert format_timestamp(3601) == "1:00:01"


def test_hybrid_samples_static_stretch():
    extras = hybrid_sample_times([1.0, 3.0], duration=30.0, interval=9.0)
    assert 12.0 in extras  # 3 + 9
    assert 21.0 in extras  # 3 + 18
    assert 1.0 not in extras


def test_min_gap_skips_blanks_not_next_slide(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    fade = tmp_path / "fade.jpg"
    slide = tmp_path / "slide.jpg"
    # Solid white fade stays tiny / near-white. The next slide is a detailed card.
    subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=white:s=640x360:d=0.2",
         "-frames:v", "1", "-update", "1", "-q:v", "3", "-y", str(fade)],
        check=True,
    )
    write_slide(slide, "0xF5E6C8", "0x3366CC")
    frames = [
        {"time": 111.67, "timestamp": "1:51", "path": fade},
        {"time": 113.25, "timestamp": "1:53", "path": slide},
    ]
    kept = apply_min_gap(frames, ffmpeg_bin(), min_gap=2.0)
    times = [frame["time"] for frame in kept]
    assert 111.67 not in times  # near-white fade dropped
    assert 113.25 in times      # next content kept even though it is <2s after the fade



def test_min_gap_keeps_later_slide_in_cluster(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    outgoing = tmp_path / "outgoing.jpg"
    incoming = tmp_path / "incoming.jpg"
    write_slide(outgoing, "0xF5E6C8", "0x2244AA", "a")
    write_slide(incoming, "0xF5E6C8", "0x228844", "b")
    frames = [
        {"time": 976.88, "timestamp": "16:16", "path": outgoing},
        {"time": 977.88, "timestamp": "16:17", "path": incoming},
    ]
    kept = apply_min_gap(frames, ffmpeg_bin(), min_gap=2.0)
    times = [frame["time"] for frame in kept]
    assert times == [977.88], f"later slide in a 1s cluster must be kept, got {times}"


def test_same_template_slides_are_kept(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    slide_a = tmp_path / "slide10.jpg"
    slide_b = tmp_path / "slide11.jpg"
    write_slide(slide_a, "0xF5E6C8", "0x2244AA", "a")
    write_slide(slide_b, "0xF5E6C8", "0x228844", "b")
    full_dist = hamming(average_hash(ffmpeg_bin(), slide_a), average_hash(ffmpeg_bin(), slide_b))
    body_dist = hamming(body_hash(ffmpeg_bin(), slide_a), body_hash(ffmpeg_bin(), slide_b))
    frames = [
        {"time": 977.88, "timestamp": "16:17", "path": slide_a},
        {"time": 1005.04, "timestamp": "16:45", "path": slide_b},
    ]
    kept = dedupe_frames(frames, ffmpeg_bin())
    assert len(kept) == 2, f"expected both slides; full={full_dist} body={body_dist}"
    assert body_dist > BODY_HASH_MAX_DISTANCE


def test_proof_slides_10_and_11_not_merged():
    frames_dir = Path("/workspace/merlin/ideas/yt-tTruM2VB9C0/frames")
    slide10 = frames_dir / "frame_0235_0977.88s.jpg"
    slide11 = frames_dir / "frame_0240_1005.04s.jpg"
    if not (slide10.exists() and slide11.exists()):
        pytest.skip("local proof slides are not in this checkout")
    with tempfile.TemporaryDirectory() as tmp:
        a = Path(tmp) / "a.jpg"
        b = Path(tmp) / "b.jpg"
        shutil.copy(slide10, a)
        shutil.copy(slide11, b)
        kept = dedupe_frames(
            [{"time": 977.88, "timestamp": "16:17", "path": a},
             {"time": 1005.04, "timestamp": "16:45", "path": b}],
            ffmpeg_bin(),
        )
        assert len(kept) == 2, "proof slides 10 and 11 must not merge"



def test_proof_min_gap_keeps_slide_05_and_slide_10(tmp_path: Path):
    frames_dir = Path("/workspace/merlin/ideas/yt-tTruM2VB9C0/frames")
    pairs = [
        ("frame_0035_0111.75s.jpg", "frame_0037_0113.25s.jpg", 111.75, 113.25),
        ("frame_0234_0976.88s.jpg", "frame_0235_0977.88s.jpg", 976.88, 977.88),
    ]
    missing = [name for pair in pairs for name in pair[:2] if not (frames_dir / name).exists()]
    if missing:
        pytest.skip("local proof slides are not in this checkout")
    tmp_path.mkdir(parents=True, exist_ok=True)
    for earlier_name, later_name, earlier_t, later_t in pairs:
        earlier = tmp_path / f"{later_t}_earlier.jpg"
        later = tmp_path / f"{later_t}_later.jpg"
        shutil.copy(frames_dir / earlier_name, earlier)
        shutil.copy(frames_dir / later_name, later)
        kept = apply_min_gap(
            [{"time": earlier_t, "timestamp": str(earlier_t), "path": earlier},
             {"time": later_t, "timestamp": str(later_t), "path": later}],
            ffmpeg_bin(),
            min_gap=2.0,
        )
        times = [frame["time"] for frame in kept]
        assert times == [later_t], f"expected later frame {later_t} kept, got {times}"


def test_capture_synthetic_video(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    clips = []
    # Distinct detailed scenes so JPEGs stay above the blank-file cutoff.
    # 0-3s bars, 3-8s rgb test, 8-28s paletted static field (hybrid should fire).
    for name, source, dur in [
        ("a.mp4", "smptebars", 3),
        ("b.mp4", "rgbtestsrc", 5),
        ("c.mp4", "yuvtestsrc", 20),
    ]:
        clip = tmp_path / name
        write_pattern_clip(clip, source, dur)
        clips.append(clip)
    video = tmp_path / "synth.mp4"
    concat_clips(clips, video)
    out = tmp_path / "shots"
    result = capture_from_video(video, out, ffmpeg_bin())
    times = [frame["time"] for frame in result["frames"]]
    assert result["status"] == "done"
    assert result["count"] >= 3
    assert any(abs(t - 1.0) < 0.15 for t in times), f"missing opener near 1s: {times}"
    # Scene cuts at 3s and 8s should survive. Later hybrid grabs of the same
    # static third scene are expected to dedupe against the 8s frame.
    assert any(abs(t - 3.0) < 0.3 for t in times), f"missing first scene cut: {times}"
    assert any(t >= 7.5 for t in times), f"missing later scene: {times}"
    assert (out / "screenshots.zip").exists()
    assert (out / "manifest.csv").exists()


def test_identical_frames_are_deduped(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    write_slide(a, "0xF5E6C8", "0x2244AA")
    shutil.copy(a, b)
    kept = dedupe_frames(
        [{"time": 1.0, "timestamp": "0:01", "path": a},
         {"time": 4.0, "timestamp": "0:04", "path": b}],
        ffmpeg_bin(),
    )
    assert len(kept) == 1


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        test_format_timestamp()
        test_hybrid_samples_static_stretch()
        test_min_gap_skips_blanks_not_next_slide(Path(tmp) / "gap")
        test_min_gap_keeps_later_slide_in_cluster(Path(tmp) / "later")
        test_same_template_slides_are_kept(Path(tmp) / "slides")
        test_proof_slides_10_and_11_not_merged()
        test_proof_min_gap_keeps_slide_05_and_slide_10(Path(tmp) / "proofgap")
        test_capture_synthetic_video(Path(tmp) / "synth")
        test_identical_frames_are_deduped(Path(tmp) / "dup")
    print("all screenshot tests passed")
