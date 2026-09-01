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
    assert "gpuType" in source
    assert "mobileWasm" in source
    assert "desktopWebgpu" in source


def test_webgpu_proof_script_records_true_no_webgpu_fallback_without_force_param():
    source = SCRIPT.read_text()

    assert "noWebgpuMobileFallback" in source
    assert "webkit.launch" in source
    assert "label === 'no-webgpu-mobile-fallback'" in source
    assert "forceBrowserWasm=1" in source
    no_webgpu_section = source.split("label === 'no-webgpu-mobile-fallback'", 1)[1]
    assert "base + '/'" in no_webgpu_section
