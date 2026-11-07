"""Guards: this runtime stays small, and the existing public page is not edited."""
from __future__ import annotations

from pathlib import Path

from free_public.captions import PUBLIC_BOT, extract_video_id, is_bot_wall, public_transcription_error

REPO = Path(__file__).resolve().parents[2]
RUNTIME = REPO / "free_public"
SECRET_MARKERS = (
    "sk-",
    "BEGIN PRIVATE",
    "AKIA",
    "ghp_",
    "xoxb-",
    "OPENAI_API_KEY=",
    "GEMINI_API_KEY=",
    "RENDER_API_KEY=",
)


def test_existing_public_page_is_unchanged():
    html = (REPO / "static" / "index.html").read_text(encoding="utf-8")
    assert ">Get Transcript<" in html
    assert "Transcript with screenshots" not in html
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    assert "openai-whisper" in dockerfile


def test_free_runtime_does_not_install_whisper_or_paid_sdks():
    requirements = (RUNTIME / "requirements.txt").read_text(encoding="utf-8").lower()
    dockerfile = (RUNTIME / "Dockerfile").read_text(encoding="utf-8").lower()
    for banned in ("openai", "whisper", "torch", "gemini", "anthropic"):
        assert banned not in requirements
        assert banned not in dockerfile
    assert "ffmpeg" in dockerfile
    assert "nodejs" in dockerfile


def test_runtime_tree_has_no_secret_markers():
    paths = [
        RUNTIME / "Dockerfile",
        RUNTIME / "requirements.txt",
        RUNTIME / "README.md",
        RUNTIME / "DEPLOY.md",
        RUNTIME / "eric_proof.py",
        REPO / "render.yaml",
    ]
    paths.extend((RUNTIME / "src").rglob("*"))
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in SECRET_MARKERS:
            assert marker not in text, f"{marker} found in {path}"


def test_youtube_id_and_bot_wall_classification():
    assert extract_video_id("https://youtu.be/tTruM2VB9C0") == "tTruM2VB9C0"
    assert extract_video_id("https://www.youtube.com/shorts/tTruM2VB9C0") == "tTruM2VB9C0"
    upstream = "ERROR: [youtube] tTruM2VB9C0: Sign in to confirm you’re not a bot"
    assert is_bot_wall(upstream)
    assert public_transcription_error(upstream) == PUBLIC_BOT
