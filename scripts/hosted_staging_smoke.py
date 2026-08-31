#!/usr/bin/env python3
"""Run the hosted-staging release smoke sequence.

This is the host-side command to run after `hosted_staging_verify.py` has
seeded the persistent `/data` volume and the staging container is reachable.
It executes the Phase 1, Phase 2, and Phase 3 public-style smokes against the
same staging base URL and emits a machine-readable report.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def build_steps(base_url: str) -> list[dict[str, Any]]:
    python = sys.executable
    return [
        {
            "phase": "phase1",
            "label": "Version 1 / Phase 1: Bulletproof YouTube transcripts",
            "command": [python, "scripts/phase1_matrix.py", base_url],
        },
        {
            "phase": "phase2",
            "label": "Version 2 / Phase 2: Any video or audio",
            "command": [python, "scripts/phase2_upload_smoke.py", base_url],
        },
        {
            "phase": "phase3",
            "label": "Version 3 / Phase 3: Video intelligence",
            "command": [python, "scripts/phase3_ui_contract_smoke.py", base_url],
        },
    ]


def run_step(step: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    result = subprocess.run(
        step["command"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed = round(time.time() - started, 2)
    return {
        **step,
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "elapsed_seconds": elapsed,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def run_smokes(base_url: str) -> dict[str, Any]:
    steps = [run_step(step) for step in build_steps(base_url)]
    return {
        "ok": all(step["ok"] for step in steps),
        "base_url": base_url,
        "steps": steps,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="Public or staging base URL to smoke test")
    parser.add_argument(
        "--print-plan",
        action="store_true",
        help="Print the smoke sequence without running network/API tests",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional JSON report path for host-side proof collection",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.print_plan:
        payload = {"ok": True, "base_url": args.base_url, "steps": build_steps(args.base_url)}
    else:
        payload = run_smokes(args.base_url)
    output = json.dumps(payload, indent=2, sort_keys=True)
    if args.out:
        args.out.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + "\n")
    print(output)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
