from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_smoke():
    spec = importlib.util.spec_from_file_location(
        "phase3_all_outputs_smoke_under_test",
        ROOT / "scripts" / "phase3_all_outputs_smoke.py",
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_assets_text(latest_timestamp: str) -> str:
    labels = [
        "Hook",
        "Short post",
        "Email subject",
        "Newsletter angle",
        "Reel script",
        "Carousel slide",
        "Quote card",
        "CTA",
        "Objection reply",
        "Repurpose prompt",
    ]
    lines = ["AI-generated from the transcript"]
    for i in range(1, 101):
        label = labels[(i - 1) % len(labels)]
        timestamp = "[00:05]" if i == 1 else latest_timestamp
        if label == "Email subject":
            body = f"Subject: angle {i} - distinct body {i}"
        elif label == "Objection reply":
            body = f"Reply: distinct body {i}"
        elif label == "CTA":
            body = f"Get distinct body {i}"
        else:
            body = f"distinct body {i}"
        lines.append(f"{i}. **{label}** {timestamp} - {body}")
    return "\n".join(lines)


def test_content_assets_short_transcript_uses_relative_late_coverage():
    module = load_smoke()

    detail = module.validate_analysis(
        "content_assets_100",
        make_assets_text("[03:27]"),
        transcript_duration_seconds=212,
    )

    assert detail["asset_count"] == 100
    assert detail["latest_timestamp_seconds"] == 207


def test_content_assets_long_transcript_requires_real_middle_and_late_coverage():
    module = load_smoke()

    text = make_assets_text("[21:00]").replace("2. **Short post** [21:00]", "2. **Short post** [12:00]")
    detail = module.validate_analysis(
        "content_assets_100",
        text,
        transcript_duration_seconds=1800,
    )

    assert detail["has_middle_coverage"] is True
    assert detail["latest_timestamp_seconds"] >= 20 * 60
