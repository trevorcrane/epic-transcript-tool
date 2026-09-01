from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "phase2_public_browser_whisper_dual_smoke.py"


def test_webgpu_proof_script_enables_real_webgpu_adapter_flags():
    source = SCRIPT.read_text()

    assert "--enable-unsafe-webgpu" in source
    assert "--use-angle=metal" in source
    assert "--ignore-gpu-blocklist" in source
