"""Real-browser proof that the page sends X-Transcript-Session on every guarded call.

Runs scripts/page_session_header_proof.cjs (Playwright + Chrome) against a live local
server in enforce mode. Skips when node, Chrome or playwright-core is missing.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib import request

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHROME = os.getenv("CHROME_PATH", "/usr/bin/google-chrome")


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.mark.skipif(not (shutil.which("node") and Path(CHROME).exists() and (ROOT / "node_modules" / "playwright-core").exists()),
                    reason="needs node, Chrome and node_modules/playwright-core")
def test_page_sends_session_header_in_real_browser(tmp_path):
    port = _free_port()
    env = {**os.environ, "PORT": str(port), "TRANSCRIPT_DATA_DIR": str(tmp_path), "TRANSCRIPT_AUTH_MODE": "enforce",
           "TRANSCRIPT_API_TOKENS": "browser-test-token-" + "k" * 24, "GEMINI_API_KEY": "", "GROQ_API_KEY": "", "GOOGLE_API_KEY": ""}
    server = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1); break
            except Exception:
                time.sleep(0.1)
        proc = subprocess.run(["node", "scripts/page_session_header_proof.cjs", f"http://127.0.0.1:{port}", CHROME],
                              cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        result = json.loads(proc.stdout)
        assert result["all_have_session"] and result["retried_after_401"]
        health = json.loads(request.urlopen(f"http://127.0.0.1:{port}/health").read())
        assert health["auth"]["auth_missing"] == 0, health["auth"]   # deploy step 8.3-4 rule
    finally:
        server.terminate(); server.wait(10)
