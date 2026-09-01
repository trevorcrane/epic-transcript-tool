from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "phase2_browser_real_whisper_smoke.py"


def test_phase2_browser_real_whisper_smoke_runs_without_test_stub_and_saves_report():
    script = SCRIPT.read_text()
    assert "__EPIC_BROWSER_WHISPER_TEST_STUB" not in script
    assert "Xenova/whisper-tiny.en" not in script
    assert "onnx-community/whisper-tiny" in script
    assert "Xenova/whisper-small" not in script
    assert "has_preferred_browser_route" in script
    assert "has_timestamps" in script
    assert "phase2-browser-real-whisper-attempt.json" in script
    assert "browser-whisper" in script
    assert "transcribe-upload" in script
    assert "downloadFormat" in script
