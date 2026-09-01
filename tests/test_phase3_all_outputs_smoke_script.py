from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_smoke():
    spec = importlib.util.spec_from_file_location(
        "phase3_streamlined_ui_smoke_under_test",
        ROOT / "scripts" / "phase3_streamlined_ui_smoke.py",
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_streamlined_smoke_expected_outputs_match_replaced_scope():
    module = load_smoke()
    assert module.EXPECTED_OUTPUTS == ["executive_summary", "action_items", "ask_question"]
    assert "content_assets_100" in module.RETIRED_MARKERS
    assert 'id="allAnalysisBtn"' in module.RETIRED_MARKERS
    assert 'id="downloadVttBtn"' in module.RETIRED_MARKERS


def test_streamlined_validate_analysis_requires_timestamp_and_disclaimer():
    module = load_smoke()
    detail = module.validate_analysis(
        "ask_question",
        "AI-generated from the transcript with Gemini.\n\n## Transcript evidence\n- [00:00] Quote evidence from source.\n\n## Answer\nQuote and chapter ideas from the video are grounded in [00:00] evidence.",
    )
    assert detail["has_timestamp"] is True
    assert detail["has_disclaimer"] is True
