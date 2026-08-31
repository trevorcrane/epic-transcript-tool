#!/usr/bin/env python3
"""One-command hosted staging runbook for the transfer bundle.

This is intended to run after `hosted-staging-transfer-bundle.tar.gz` is
extracted on the selected persistent Docker host. It can print the exact plan or
execute the seed-verify, Docker build, detached container start, health wait,
and Phase 1/2/3 smoke report steps.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED = ROOT / "evidence" / "hosted-staging-seed.tar.gz"
DEFAULT_REPORT = ROOT / "evidence" / "hosted-staging-smoke-report.json"


def build_plan(args: argparse.Namespace) -> dict:
    data_dir = args.data_dir.expanduser().resolve()
    staging_url = args.staging_url.rstrip("/")
    return {
        "ok": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "staging_url": staging_url,
        "data_dir": str(data_dir),
        "image": args.image,
        "container": args.container,
        "port": args.port,
        "smoke_report": str(args.out.expanduser().resolve()),
        "steps": [
            {
                "name": "verify_seed_into_persistent_data",
                "command": [
                    sys.executable,
                    "scripts/hosted_staging_verify.py",
                    str(args.seed_package),
                    "--extract-to",
                    str(data_dir),
                ],
            },
            {
                "name": "docker_build",
                "command": ["docker", "build", "-t", args.image, "."],
            },
            {
                "name": "docker_run_detached",
                "command": [
                    "docker",
                    "run",
                    "--rm",
                    "--name",
                    args.container,
                    "-p",
                    f"{args.port}:8090",
                    "-v",
                    f"{data_dir}:/data",
                    args.image,
                ],
            },
            {
                "name": "wait_for_health",
                "url": f"{staging_url}/health",
                "timeout_seconds": args.health_timeout,
            },
            {
                "name": "phase_1_2_3_smoke",
                "command": [
                    sys.executable,
                    "scripts/hosted_staging_smoke.py",
                    staging_url,
                    "--out",
                    str(args.out.expanduser().resolve()),
                ],
            },
        ],
    }


def run_command(command: list[str], cwd: Path) -> dict:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "ok": result.returncode == 0,
    }


def wait_for_health(url: str, timeout_seconds: int) -> dict:
    deadline = time.time() + timeout_seconds
    attempts = []
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                body = response.read(4096).decode("utf-8", errors="replace")
                ok = response.status == 200 and '"ready"' in body
                attempts.append({"status": response.status, "ok": ok, "body_head": body[:300]})
                if ok:
                    return {"ok": True, "url": url, "attempts": attempts}
        except Exception as exc:  # noqa: BLE001 - report host readiness failures plainly
            attempts.append({"ok": False, "error": str(exc)})
        time.sleep(2)
    return {"ok": False, "url": url, "attempts": attempts}


def execute_plan(plan: dict, keep_running: bool) -> dict:
    results = []
    container_started = False
    try:
        for step in plan["steps"]:
            if "command" in step:
                command = step["command"]
                if step["name"] == "docker_run_detached":
                    command = [*command[:2], "-d", *command[2:]]
                result = run_command(command, ROOT)
                results.append({"step": step["name"], **result})
                if not result["ok"]:
                    return {"ok": False, "plan": plan, "results": results}
                if step["name"] == "docker_run_detached":
                    container_started = True
            elif step["name"] == "wait_for_health":
                result = wait_for_health(step["url"], step["timeout_seconds"])
                results.append({"step": step["name"], **result})
                if not result["ok"]:
                    return {"ok": False, "plan": plan, "results": results}
    finally:
        if container_started and not keep_running:
            subprocess.run(["docker", "rm", "-f", plan["container"]], cwd=ROOT, text=True, capture_output=True, check=False)
    return {"ok": all(item.get("ok") for item in results), "plan": plan, "results": results}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("staging_url", nargs="?", default="http://127.0.0.1:8090")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data-hosted-staging")
    parser.add_argument("--seed-package", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--image", default="epic-transcript-machine:hosted-staging")
    parser.add_argument("--container", default="epic-transcript-hosted-staging")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--health-timeout", type=int, default=90)
    parser.add_argument("--print-plan", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--keep-running", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = build_plan(args)
    if args.execute:
        payload = execute_plan(plan, args.keep_running)
    else:
        payload = plan
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
