"""Synthetic + proof-frame tests for screenshot capture (no paid APIs)."""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from screenshots import (  # noqa: E402
    BODY_HASH_MAX_DISTANCE,
    apply_min_gap,
    average_hash,
    body_hash,
    cap_frames,
    canonical_youtube_watch_url,
    capture_from_url,
    capture_from_video,
    dedupe_frames,
    download_360p,
    format_timestamp,
    grab_frame_at,
    hamming,
    hybrid_sample_times,
    public_http_url,
    safe_frame_path,
    safe_job_dir,
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
        pytest.skip("proof slides are not in this checkout")
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
        pytest.skip("proof frames are not in this checkout: " + ", ".join(missing))
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


def test_public_http_url_rejects_local_and_private_targets():
    for url in (
        "file:///etc/passwd",
        "http://127.0.0.1/latest/meta-data",
        "http://169.254.169.254/",
        "http://10.1.2.3/video.mp4",
        "http://localhost/video.mp4",
        "http://printer.local/video.mp4",
        "http://user:pass@example.com/video.mp4",
        "https://example.com:8080/video.mp4",
        "http://2130706433/",
    ):
        try:
            public_http_url(url)
        except ValueError:
            continue
        raise AssertionError(f"accepted unsafe screenshot URL {url}")


def test_public_http_url_allows_public_resolution(monkeypatch):
    monkeypatch.setattr(
        "screenshots.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    assert public_http_url("https://example.com/watch") == "https://example.com/watch"


def test_public_http_url_rejects_private_resolution(monkeypatch):
    monkeypatch.setattr(
        "screenshots.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("10.1.2.3", 443))],
    )
    try:
        public_http_url("https://evil.example/video")
    except ValueError:
        return
    raise AssertionError("accepted a hostname that resolves to a private address")


def test_download_360p_blocks_private_url_before_subprocess(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr("screenshots.subprocess.run", lambda *args, **kwargs: called.append(args))
    try:
        download_360p("http://127.0.0.1/secret", tmp_path, "yt-dlp", "ffmpeg")
    except ValueError:
        assert called == []
        return
    raise AssertionError("private download was attempted")


CANONICAL = "https://www.youtube.com/watch?v=abcdefghijk"


def _public_youtube_dns(monkeypatch):
    def fake(host, *args, **kwargs):
        if host != "www.youtube.com":
            raise AssertionError(f"screenshot DNS looked up {host}")
        return [(2, 1, 6, "", ("142.250.190.14", 443))]

    monkeypatch.setattr("screenshots.socket.getaddrinfo", fake)


def test_canonical_youtube_url_strips_smuggled_targets():
    smuggled = (
        "https://youtu.be/abcdefghijk?q=http://127.0.0.1",
        "https://www.youtube.com/watch?v=abcdefghijk&next=http://169.254.169.254/",
        "https://m.youtube.com/shorts/abcdefghijk",
        "https://music.youtube.com/watch?v=abcdefghijk&list=PL123",
        "https://www.youtube.com/embed/abcdefghijk",
        "https://www.youtube.com/live/abcdefghijk",
        "https://www.youtube.com:443/watch?v=abcdefghijk",
    )
    for url in smuggled:
        assert canonical_youtube_watch_url(url) == CANONICAL, url


def test_screenshot_url_rejects_bypass_hosts():
    rejected = (
        "https://evil.example/watch?v=abcdefghijk",
        "https://www.youtube.com.evil.example/watch?v=abcdefghijk",
        "https://notyoutube.com/watch?v=abcdefghijk",
        "https://youtube.com.evil.example/watch?v=abcdefghijk",
        "https://www.youtube.com/redirect?q=http://127.0.0.1/latest/meta-data",
        "https://www.youtube.com/redirect?q=http://169.254.169.254/",
        "http://127.0.0.1/watch?v=abcdefghijk",
        "http://169.254.169.254/latest/meta-data",
        "https://user:pass@www.youtube.com/watch?v=abcdefghijk",
        "https://www.youtube.com@evil.example/watch?v=abcdefghijk",
        "https://evil.example@www.youtube.com/watch?v=abcdefghijk",
        "https://www.youtube.com:8080/watch?v=abcdefghijk",
        "https://www.youtube.com/watch/extra?v=abcdefghijk",
        "https://youtu.be/abcdefghijk/extra",
        "https://youtu.be/abcdefghij",
        "https://www.youtube.com/watch?v=abcdefghijk%0d%0a",
        "file:///etc/passwd",
        "https://www.youtube.com/watch?v=../etc/passwd",
        "//www.youtube.com/watch?v=abcdefghijk",
        "https://evil.example#@www.youtube.com/watch?v=abcdefghijk",
        "javascript:https://www.youtube.com/watch?v=abcdefghijk",
    )
    for url in rejected:
        try:
            canonical_youtube_watch_url(url)
        except ValueError:
            continue
        raise AssertionError(f"accepted screenshot URL {url}")


def test_untrusted_host_is_not_resolved_or_downloaded(monkeypatch, tmp_path):
    def boom(*args, **kwargs):
        raise AssertionError(f"DNS or network call {args}")

    monkeypatch.setattr("screenshots.socket.getaddrinfo", boom)
    monkeypatch.setattr("screenshots.subprocess.run", boom)
    try:
        capture_from_url("https://evil.example/video.mp4", tmp_path, "yt-dlp", "ffmpeg")
    except ValueError:
        return
    raise AssertionError("untrusted URL reached download")


def test_download_360p_sets_bounds_for_canonical_youtube_url(monkeypatch, tmp_path):
    called = []

    class Proc:
        returncode = 1
        stdout = ""
        stderr = "nope"

    _public_youtube_dns(monkeypatch)

    def fake_bounded(cmd, *, timeout, text=False):
        called.append(list(cmd))
        return Proc()

    monkeypatch.setattr("screenshots.run_bounded", fake_bounded)
    try:
        download_360p(
            "https://youtu.be/abcdefghijk?next=http://127.0.0.1/latest/meta-data",
            tmp_path, "yt-dlp", "ffmpeg",
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected the failed download to raise")
    assert called
    command = called[0]
    assert "--no-playlist" in command
    assert "--max-filesize" in command
    assert "--use-extractors" in command
    assert command[command.index("--use-extractors") + 1] == "youtube"
    assert command[-1] == CANONICAL
    assert "127.0.0.1" not in " ".join(command)
    assert "169.254.169.254" not in " ".join(command)
    assert "evil.example" not in " ".join(command)


def test_safe_paths_reject_traversal(tmp_path):
    job = safe_job_dir(tmp_path, "abc123abc123")
    job.mkdir()
    try:
        safe_frame_path(job, "../secrets.jpg")
    except ValueError:
        pass
    else:
        raise AssertionError("traversal filename was accepted")
    try:
        safe_job_dir(tmp_path, "../etc")
    except ValueError:
        return
    raise AssertionError("traversal job id was accepted")


def _spawn_marker(path: Path, marker: str) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(45)  # {marker}'])\n"
        "time.sleep(45)\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _marked_processes(marker: str) -> list[str]:
    import subprocess
    listing = subprocess.check_output(["ps", "-ww", "-eo", "pid,cmd"], text=True)
    return [line for line in listing.splitlines() if marker in line and "ps -ww" not in line]


def _kill_marked(marker: str) -> None:
    import os
    import signal
    for line in _marked_processes(marker):
        pid = int(line.split()[0])
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def test_download_360p_timeout_leaves_no_descendants(tmp_path, monkeypatch):
    marker = f"epic-shot-yt-{tmp_path.name}"
    stub = tmp_path / "yt-dlp"
    _spawn_marker(stub, marker)
    _public_youtube_dns(monkeypatch)
    try:
        download_360p("https://www.youtube.com/watch?v=abcdefghijk", tmp_path, str(stub), "ffmpeg", timeout=1)
        raised = False
    except subprocess.TimeoutExpired:
        raised = True
        time.sleep(0.3)
    finally:
        survivors = _marked_processes(marker)
        _kill_marked(marker)
    assert raised
    assert survivors == []


def test_ffmpeg_frame_timeout_leaves_no_descendants(tmp_path, monkeypatch):
    marker = f"epic-shot-ff-{tmp_path.name}"
    stub = tmp_path / "ffmpeg"
    _spawn_marker(stub, marker)
    monkeypatch.setattr("screenshots.FRAME_TIMEOUT_SECONDS", 1)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"not a real video")
    try:
        grab_frame_at(str(stub), video, 1.0, tmp_path / "frame.jpg")
        raised = False
    except subprocess.TimeoutExpired:
        raised = True
        time.sleep(0.3)
    finally:
        survivors = _marked_processes(marker)
        _kill_marked(marker)
    assert raised
    assert survivors == []


def _ignore_sigterm_stub(path: Path, marker: str) -> None:
    """Leader dies on SIGTERM. Grandchild ignores SIGTERM and stays in the group."""
    child = path.with_name(f"{marker}.py")
    child.write_text(
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, {str(child)!r}])\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _setsid_stub(path: Path, marker: str, pidfile: Path) -> None:
    """Grandchild calls setsid and leaves the launcher process group."""
    child = path.with_name(f"{marker}.py")
    child.write_text(
        "import os, time\n"
        "os.setsid()\n"
        f"open({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, {str(child)!r}])\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_m3_sigterm_ignoring_grandchild_also_reaped(tmp_path, monkeypatch):
    """Same-group grandchild that ignores SIGTERM must die after the leader exits."""
    monkeypatch.setattr("screenshots.FRAME_TIMEOUT_SECONDS", 1)
    _public_youtube_dns(monkeypatch)
    unrelated = f"m3-unrelated-{tmp_path.name}"
    unrelated_script = tmp_path / f"{unrelated}.py"
    unrelated_script.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    unrelated_proc = subprocess.Popen([sys.executable, str(unrelated_script)])
    try:
        for kind in ("grab", "download"):
            marker = f"m3-ignore-{kind}-{tmp_path.name}"
            stub = tmp_path / f"{kind}-stub"
            _ignore_sigterm_stub(stub, marker)
            try:
                if kind == "grab":
                    grab_frame_at(str(stub), tmp_path / "clip.mp4", 1.0, tmp_path / f"{kind}.jpg")
                else:
                    download_360p(
                        "https://www.youtube.com/watch?v=abcdefghijk",
                        tmp_path / kind, str(stub), "ffmpeg", timeout=1,
                    )
                raised = False
            except subprocess.TimeoutExpired:
                raised = True
                time.sleep(0.4)
            finally:
                survivors = _marked_processes(marker)
                _kill_marked(marker)
            assert raised, kind
            assert survivors == [], (kind, survivors)
            assert _marked_processes(unrelated), "unrelated process was killed"
    finally:
        unrelated_proc.kill()
        unrelated_proc.wait(timeout=2)


def test_setsid_descendant_is_outside_portable_group_cleanup(tmp_path, monkeypatch):
    """setsid() leaves the group. Cleanup must not search the machine to kill it."""
    monkeypatch.setattr("screenshots.FRAME_TIMEOUT_SECONDS", 1)
    marker = f"m3-setsid-{tmp_path.name}"
    pidfile = tmp_path / "escaped.pid"
    stub = tmp_path / "ffmpeg"
    _setsid_stub(stub, marker, pidfile)
    unrelated = f"m3-unrelated-setsid-{tmp_path.name}"
    unrelated_script = tmp_path / f"{unrelated}.py"
    unrelated_script.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    unrelated_proc = subprocess.Popen([sys.executable, str(unrelated_script)])
    escaped = None
    try:
        try:
            grab_frame_at(str(stub), tmp_path / "clip.mp4", 1.0, tmp_path / "frame.jpg")
        except subprocess.TimeoutExpired:
            time.sleep(0.4)
        assert pidfile.is_file(), "setsid child did not record its pid"
        escaped = int(pidfile.read_text().strip())
        os.kill(escaped, 0)  # still alive: not in the launcher group
        assert _marked_processes(unrelated), "unrelated process was killed"
    finally:
        if escaped is not None:
            try:
                os.kill(escaped, signal.SIGKILL)
            except OSError:
                pass
        unrelated_proc.kill()
        unrelated_proc.wait(timeout=2)
        _kill_marked(marker)


def test_cap_frames_keeps_ends_and_deletes_the_rest(tmp_path):
    frames = []
    for idx in range(5):
        path = tmp_path / f"{idx}.jpg"
        path.write_bytes(b"jpeg")
        frames.append({"time": float(idx), "path": path})
    kept = cap_frames(frames, 3)
    assert [frame["time"] for frame in kept] == [0.0, 2.0, 4.0]
    assert not (tmp_path / "1.jpg").exists()
    assert (tmp_path / "0.jpg").exists()


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
