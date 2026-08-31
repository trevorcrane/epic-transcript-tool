from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_smoke():
    spec = importlib.util.spec_from_file_location(
        "phase3_citation_coverage_smoke_under_test",
        ROOT / "scripts" / "phase3_citation_coverage_smoke.py",
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_args_accepts_output_report_path(tmp_path):
    module = load_smoke()
    out = tmp_path / "phase3-citation-report.json"

    args = module.parse_args([
        "https://example.test/",
        "https://youtu.be/example12345",
        "--out",
        str(out),
    ])

    assert args.base == "https://example.test/"
    assert args.video == "https://youtu.be/example12345"
    assert args.out == out


def test_write_report_persists_same_json_that_is_printed(tmp_path, capsys):
    module = load_smoke()
    report = {"ok": True, "outputs_checked": {"executive_summary": {"timestamp_count": 2}}}
    out = tmp_path / "phase3-citation-report.json"

    module.write_report(report, out)

    expected = '{\n  "ok": true,\n  "outputs_checked": {\n    "executive_summary": {\n      "timestamp_count": 2\n    }\n  }\n}\n'
    assert out.read_text() == expected
    assert capsys.readouterr().out == expected
