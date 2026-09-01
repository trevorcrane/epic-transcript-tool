from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "phase2_public_browser_whisper_dual_smoke.py"


def test_webgpu_proof_script_enables_real_webgpu_adapter_flags():
    source = SCRIPT.read_text()

    assert "--enable-unsafe-webgpu" in source
    assert "--use-angle=metal" in source
    assert "--ignore-gpu-blocklist" in source


def test_webgpu_proof_script_records_adapter_device_and_mobile_wasm_artifact():
    source = SCRIPT.read_text()

    assert "gpuProof" in source
    assert "requestAdapter" in source
    assert "requestDevice" in source
    assert "adapterFeatures" in source
    assert "userAgent" in source
    assert "mobileWasm" in source
    assert "desktopWebgpu" in source
