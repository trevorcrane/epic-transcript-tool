from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "phase2_browser_fallback_ui_smoke.py"


def test_phase2_browser_fallback_ui_smoke_exists_and_drives_clickable_stubbed_path():
    script = SCRIPT.read_text()
    assert "public_root" in script
    assert "__EPIC_BROWSER_WHISPER_TEST_STUB" in script
    assert "setInputFiles" in script
    assert "/api/transcribe-upload" in script
    assert "browser_fallback" in script
    assert "epicTranscriptHistory" in script
    assert "phase2-browser-fallback-ui-report.json" in script
