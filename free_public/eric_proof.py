"""Run one new Eric URL job through the free-public server and record the exact result.

A ZIP already on disk is not this proof. The script starts a fresh process and posts
https://youtu.be/tTruM2VB9C0 with screenshots requested.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "free_public" / "src"
EVIDENCE = REPO / "evidence" / "free-public-eric-url-job.json"
ERIC_URL = "https://youtu.be/tTruM2VB9C0"
PORT = "8766"


def _clip_refusal(text: str) -> str:
    """Keep the source's refusal, not its later cookie or proxy suggestions."""
    cleaned = " ".join((text or "").split())
    for stop in ("Use --cookies", "There are two things you can do", "See https://"):
        index = cleaned.find(stop)
        if index > 0:
            cleaned = cleaned[:index]
    return cleaned.strip()


def _interesting(text: str) -> list[str]:
    keys = ("ERROR:", "playability", "Sign in", "LOGIN_REQUIRED", "RequestBlocked", "blocking requests", "Could not retrieve")
    found = []
    for line in (text or "").splitlines():
        if any(key in line for key in keys):
            cleaned = _clip_refusal(line)
            if cleaned and cleaned not in found:
                found.append(cleaned[:500])
    return found[:12]


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def upstream_reports() -> list[dict]:
    yt_dlp = shutil.which("yt-dlp") or str(Path(sys.executable).with_name("yt-dlp"))
    node = shutil.which("node")
    cmd = [yt_dlp, "--ignore-config", "--no-warnings", "-v", "--skip-download"]
    if node:
        cmd.extend(["--js-runtimes", f"node:{node}"])
    cmd.append(ERIC_URL)
    reports = []
    try:
        proc = _run(cmd, 60)
        text = (proc.stderr or "") + "\n" + (proc.stdout or "")
        reports.append({
            "tool": "yt-dlp",
            "js_runtime": node or None,
            "exit_code": proc.returncode,
            "lines": _interesting(text),
        })
    except Exception as exc:
        reports.append({"tool": "yt-dlp", "error": f"{type(exc).__name__}: {exc}"})
    probe = (
        "import json\n"
        "try:\n"
        "    from youtube_transcript_api import YouTubeTranscriptApi\n"
        "    YouTubeTranscriptApi().fetch('tTruM2VB9C0')\n"
        "    print(json.dumps({'ok': True}))\n"
        "except Exception as exc:\n"
        "    message = str(exc)\n"
        "    for stop in ('There are two things you can do', 'Use proxies'):\n"
        "        index = message.find(stop)\n"
        "        if index > 0:\n"
        "            message = message[:index]\n"
        "    print(json.dumps({'ok': False, 'type': type(exc).__name__, 'error': ' '.join(message.split())[:800]}))\n"
    )
    try:
        proc = _run([sys.executable, "-c", probe], 60)
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        reports.append({"tool": "youtube-transcript-api", **payload, "lines": _interesting(payload.get("error", ""))})
    except Exception as exc:
        reports.append({"tool": "youtube-transcript-api", "error": f"{type(exc).__name__}: {exc}"})
    return reports


def _http(method: str, path: str, body: bytes | None = None, headers: dict | None = None, timeout: int = 30) -> tuple[int, bytes]:
    request = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def main() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    env["PORT"] = PORT
    env["TRANSCRIPT_DATA_DIR"] = "/tmp/free-public-eric-data"
    env.pop("RENDER_API_KEY", None)
    server = subprocess.Popen(
        [sys.executable, "-m", "free_public.app"],
        cwd=str(REPO),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    report: dict = {
        "proves_new_eric_job": True,
        "uses_precaptured_zip": False,
        "url": ERIC_URL,
        "video_id": "tTruM2VB9C0",
        "cookies_used": False,
        "proxy_used": False,
        "paid_provider_used": False,
        "cloudflare_tunnel_7844_used": False,
        "public_url": None,
        "hosting": {
            "render_api_key_present": bool(os.environ.get("RENDER_API_KEY")),
            "render_cli_present": bool(shutil.which("render")),
            "blocker": (
                "No Render API key and no render CLI in this environment. "
                "Composio has no Render connection here. Do not sign up or spend. "
                "A static page is not a running transcriber."
            ),
        },
    }
    try:
        health = None
        for _ in range(40):
            if server.poll() is not None:
                break
            try:
                status, raw = _http("GET", "/health")
                health = json.loads(raw.decode())
                if status == 200:
                    break
            except Exception:
                time.sleep(0.25)
        rss = None
        status_path = Path(f"/proc/{server.pid}/status")
        if status_path.exists():
            for line in status_path.read_text().splitlines():
                if line.startswith("VmRSS:"):
                    rss = int(line.split()[1])
        report["health"] = health
        report["server_rss_kb"] = rss
        form = urllib.parse.urlencode({"url": ERIC_URL, "include_screenshots": "1"}).encode()
        status, raw = _http(
            "POST",
            "/api/transcribe-url-job",
            body=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        started = json.loads(raw.decode())
        report["start_status"] = status
        job_id = ((started.get("job") or {}).get("id"))
        report["job_id"] = job_id
        job = {}
        deadline = time.time() + 120
        while job_id and time.time() < deadline:
            code, body = _http("GET", f"/api/jobs/{job_id}")
            payload = json.loads(body.decode())
            job = payload.get("job") or {}
            if job.get("status") in {"done", "error"}:
                report["poll_status"] = code
                break
            time.sleep(1)
        record = job.get("record") or {}
        shots = job.get("screenshots") or record.get("screenshots") or {}
        transcript = record.get("transcript") or ""
        report["job_status"] = job.get("status")
        report["public_error"] = job.get("error")
        report["method"] = record.get("method")
        report["word_count"] = record.get("word_count")
        report["transcript_present"] = bool(transcript.strip())
        report["transcript_head"] = transcript[:240]
        report["screenshot_status"] = shots.get("status")
        report["screenshot_count"] = shots.get("count")
        report["screenshot_error"] = shots.get("error")
        zip_ok = False
        if job_id and shots.get("zip_url"):
            code, archive = _http("GET", shots["zip_url"])
            zip_ok = code == 200 and archive[:2] == b"PK"
            report["zip_bytes"] = len(archive)
            report["zip_status"] = code
        report["zip_downloaded"] = zip_ok
        report["upstream"] = upstream_reports()
        succeeded = report["job_status"] == "done" and report["transcript_present"] and zip_ok
        report["eric_url_ingestion_succeeded"] = succeeded
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(EVIDENCE)
    print(json.dumps({
        "job_status": report.get("job_status"),
        "public_error": report.get("public_error"),
        "eric_url_ingestion_succeeded": report.get("eric_url_ingestion_succeeded"),
        "zip_downloaded": report.get("zip_downloaded"),
    }, indent=2))
    return 0 if report.get("job_status") in {"done", "error"} else 1


if __name__ == "__main__":
    sys.exit(main())
