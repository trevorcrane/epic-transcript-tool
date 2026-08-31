#!/usr/bin/env python3
"""Phase 2 browser fallback clickable UI smoke.

This proves the failed-upload recovery path is wired through the actual browser UI
without downloading a Whisper model. The production code only honors the test stub
on localhost/127.0.0.1, so public visitors cannot spoof browser transcripts.
"""
from __future__ import annotations

import http.server
import json
import os
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
OUT = ROOT / "evidence" / "phase2-browser-fallback-ui-report.json"
PUBLIC_BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://epic-transcript.robyncrane.com").rstrip("/")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fetch_text(url: str) -> tuple[int, str]:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 Phase2BrowserFallbackUISmoke/1.0"})
    with urlopen(req, timeout=30) as response:
        return response.status, response.read().decode("utf-8", errors="ignore")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def run_local_server() -> tuple[ReusableTCPServer, str]:
    handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(STATIC), **kwargs)
    server = ReusableTCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


NODE_PROOF = r'''
const { chromium } = require('playwright');
const fs = require('fs');
const [url, outPath] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true });
  const network = [];
  await page.route('**/api/transcribe-upload', async route => {
    network.push(route.request().url());
    await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'forced server upload failure for browser_fallback proof' }) });
  });
  await page.addInitScript(() => {
    window.__EPIC_BROWSER_WHISPER_TEST_STUB = async (file, method) => {
      const transcript = 'Browser fallback proof transcript. This credible local browser transcript was created after the server upload route failed.';
      return { record: {
        id: 'browser-proof-record',
        source: file.name,
        title: file.name,
        method,
        transcript,
        segments: [{ start: 0, end: 2, text: transcript }],
        language: 'en',
        browser_only: true,
        created_at: new Date().toISOString(),
        processing_seconds: 0
      }};
    };
  });
  await page.goto(url, { waitUntil: 'networkidle' });
  const filePath = '/tmp/epic-browser-fallback-proof.wav';
  fs.writeFileSync(filePath, Buffer.from('RIFF$\x00\x00\x00WAVEfmt '));
  await page.setInputFiles('#file', { name: 'browser-fallback-proof.wav', mimeType: 'audio/wav', buffer: fs.readFileSync(filePath) });
  await page.waitForSelector('#result.show', { timeout: 10000 });
  const proof = await page.evaluate(() => {
    const history = JSON.parse(localStorage.getItem('epicTranscriptHistory') || '[]');
    return {
      title: document.querySelector('#title')?.textContent || '',
      method: document.querySelector('#resultMethod')?.textContent || '',
      transcript: document.querySelector('#transcript')?.textContent || '',
      status: document.querySelector('#statusText')?.textContent || '',
      resultVisible: document.querySelector('#result')?.classList.contains('show') || false,
      historyCount: history.length,
      historyFirstMethod: history[0]?.method || '',
      historyFirstBrowserOnly: Boolean(history[0]?.browser_only),
      hasLocalDownloads: document.body.textContent.includes('TXT') && document.body.textContent.includes('VTT'),
      browser_fallback: true,
    };
  });
  proof.network = network;
  proof.viewport = await page.viewportSize();
  await page.screenshot({ path: outPath.replace(/\.json$/, '.png'), fullPage: true });
  await browser.close();
  fs.writeFileSync(outPath, JSON.stringify(proof, null, 2));
})().catch(err => { console.error(err); process.exit(1); });
'''


def run_browser_proof(local_url: str) -> dict[str, object]:
    node_modules = ROOT / "node_modules"
    require((node_modules / "playwright").exists(), "node_modules/playwright is missing")
    with tempfile.TemporaryDirectory() as tmp:
        js_path = Path(tmp) / "browser_fallback_proof.js"
        js_path.write_text(NODE_PROOF, encoding="utf-8")
        tmp_out = Path(tmp) / "phase2-browser-fallback-ui-report.json"
        env = dict(os.environ)
        env["NODE_PATH"] = str(node_modules)
        subprocess.run(["node", str(js_path), local_url, str(tmp_out)], cwd=str(ROOT), env=env, check=True, timeout=60)
        data = json.loads(tmp_out.read_text(encoding="utf-8"))
        image_tmp = tmp_out.with_suffix(".png")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
        if image_tmp.exists():
            (OUT.with_suffix(".png")).write_bytes(image_tmp.read_bytes())
        return data


def main() -> None:
    status, public_root = fetch_text(PUBLIC_BASE + "/")
    public_root_report = {
        "status": status,
        "bytes": len(public_root),
        "has_stub_guard": "window.__EPIC_BROWSER_WHISPER_TEST_STUB" in public_root and "Browser fallback test stub is not active" in public_root,
        "has_browser_fallback_wiring": "Server upload failed, trying private browser transcription" in public_root and "Xenova/whisper-tiny.en" in public_root,
        "has_history_storage": "epicTranscriptHistory" in public_root,
    }
    require(status == 200, f"public root returned {status}")
    require(public_root_report["has_stub_guard"], "public root missing localhost-only test-stub guard")
    require(public_root_report["has_browser_fallback_wiring"], "public root missing browser fallback wiring")

    server, local_base = run_local_server()
    try:
        browser_fallback = run_browser_proof(local_base + "/")
    finally:
        server.shutdown()
        server.server_close()

    result_visible = bool(browser_fallback.get("resultVisible"))
    method = str(browser_fallback.get("method") or "")
    transcript = str(browser_fallback.get("transcript") or "")
    raw_history_count = browser_fallback.get("historyCount")
    history_count = raw_history_count if isinstance(raw_history_count, int) else 0
    history_browser_only = bool(browser_fallback.get("historyFirstBrowserOnly"))
    raw_network = browser_fallback.get("network")
    network = [str(url) for url in raw_network] if isinstance(raw_network, list) else []

    require(result_visible, "browser fallback result was not visible")
    require("browser-whisper" in method, "browser fallback method was not rendered")
    require("Browser fallback proof transcript" in transcript, "browser fallback transcript missing")
    require(history_count >= 1, "browser fallback was not saved to local history")
    require(history_browser_only, "history item was not marked browser-only")
    require(any("/api/transcribe-upload" in url for url in network), "upload route was not attempted before fallback")

    report = {"public_root": public_root_report, "browser_fallback": browser_fallback, "evidence": str(OUT)}
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
