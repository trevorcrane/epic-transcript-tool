#!/usr/bin/env python3
"""Run a real browser Whisper fallback smoke without the localhost test stub.

This uses the local static UI, forces the server upload route to fail, uploads a
tiny generated WAV, lets the actual Transformers.js browser model path run, then
verifies rendered transcript plus local VTT download. It does not call paid
providers and it does not use the guarded test stub.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
OUT = ROOT / "evidence" / "phase2-browser-real-whisper-attempt.json"
PUBLIC_BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://epic-transcript.robyncrane.com").rstrip("/")
MODEL_MARKER = "Xenova/whisper-small"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fetch_public_root() -> dict[str, object]:
    req = Request(PUBLIC_BASE + "/", headers={"User-Agent": "Mozilla/5.0 Phase2RealBrowserWhisper/1.0"})
    with urlopen(req, timeout=30) as response:
        html = response.read().decode("utf-8", errors="ignore")
    report = {
        "status": response.status,
        "bytes": len(html),
        "has_model_marker": MODEL_MARKER in html,
        "has_preferred_browser_route": "shouldPreferBrowserWhisper(file)" in html,
        "has_fallback_wiring": "Server upload failed, trying private browser transcription" in html,
        "has_timestamps": "return_timestamps: true" in html and "chunks.map" in html,
        "has_subtitle_formatter": "formatSubtitleDuration" in html,
    }
    require(report["status"] == 200, f"public root returned {report['status']}")
    require(bool(report["has_model_marker"]), "public root missing browser Whisper model marker")
    require(bool(report["has_preferred_browser_route"]), "public root missing preferred browser route wiring")
    require(bool(report["has_fallback_wiring"]), "public root missing browser fallback wiring")
    require(bool(report["has_timestamps"]), "public root missing real timestamp chunk wiring")
    return report


def make_wav() -> Path:
    wav = Path(tempfile.gettempdir()) / "epic-browser-real-whisper.wav"
    if wav.exists() and wav.stat().st_size > 1000:
        return wav
    aiff = Path(tempfile.gettempdir()) / "epic-browser-real-whisper.aiff"
    phrase = "Browser whisper real model proof for Epic transcript machine."
    try:
        subprocess.run(["say", "-o", str(aiff), phrase], check=True, timeout=30)
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise RuntimeError("macOS say command is required to generate the no-cost browser proof audio")
    subprocess.run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(wav)], check=True, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return wav


NODE_PROOF = r'''
const { chromium } = require('playwright');
const fs = require('fs');
const http = require('http');
const path = require('path');
const [staticDir, wavPath, outPath] = process.argv.slice(2);
const server = http.createServer((req, res) => {
  const cleanPath = req.url === '/' ? '/index.html' : req.url.split('?')[0];
  const file = path.join(staticDir, cleanPath);
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); res.end('not found'); return; }
    res.writeHead(200, { 'content-type': file.endsWith('.html') ? 'text/html' : 'application/octet-stream' });
    res.end(data);
  });
});
server.listen(0, '127.0.0.1', async () => {
  const url = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, acceptDownloads: true });
  const page = await context.newPage();
  const statuses = [];
  const browserErrors = [];
  page.on('console', msg => { if (msg.type() === 'error') browserErrors.push(msg.text()); });
  page.on('pageerror', err => browserErrors.push(String(err)));
  await page.route('**/api/transcribe-upload', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'forced server upload failure for real browser whisper proof' }) }));
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.setInputFiles('#file', wavPath);
  const started = Date.now();
  let state = {};
  for (let i = 0; i < 360; i++) {
    await page.waitForTimeout(1000);
    state = await page.evaluate(() => ({
      status: document.querySelector('#statusText')?.textContent || '',
      visible: document.querySelector('#result')?.classList.contains('show') || false,
      method: document.querySelector('#resultMethod')?.textContent || '',
      transcript: document.querySelector('#transcript')?.textContent || '',
      historyCount: JSON.parse(localStorage.getItem('epicTranscriptHistory') || '[]').length,
    }));
    if (state.status && !statuses.includes(state.status)) statuses.push(state.status);
    if (state.visible || state.status.startsWith('Error:')) break;
  }
  const downloadPromise = page.waitForEvent('download', { timeout: 10000 });
  await page.click('#downloadVttBtn');
  const download = await downloadPromise;
  const vttPath = path.join(path.dirname(outPath), 'phase2-browser-real-whisper.vtt');
  await download.saveAs(vttPath);
  const vtt = fs.readFileSync(vttPath, 'utf8');
  const report = {
    url,
    ok: Boolean(state.visible && state.transcript && state.transcript.length > 10 && state.method.includes('browser-whisper')),
    statuses,
    browserErrors,
    elapsedSeconds: (Date.now() - started) / 1000,
    state,
    vttDownload: {
      suggestedFilename: download.suggestedFilename(),
      bytes: Buffer.byteLength(vtt),
      hasWebVtt: vtt.includes('WEBVTT'),
      hasFullTimestamp: /00:00:00\.000 --> 00:00:0[2-9]\.000/.test(vtt),
    }
  };
  await browser.close();
  server.close();
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  process.exit(report.ok && report.vttDownload.hasWebVtt && report.vttDownload.hasFullTimestamp ? 0 : 2);
});
'''


def run_browser(wav: Path) -> dict[str, object]:
    node_modules = ROOT / "node_modules"
    require((node_modules / "playwright").exists(), "node_modules/playwright is missing")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    js_path = Path(tempfile.gettempdir()) / "phase2_browser_real_whisper_proof.js"
    js_path.write_text(NODE_PROOF, encoding="utf-8")
    env = dict(os.environ)
    env["NODE_PATH"] = str(node_modules)
    proc = subprocess.run(["node", str(js_path), str(STATIC), str(wav), str(OUT)], cwd=str(ROOT), env=env, text=True, capture_output=True, timeout=600)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(proc.returncode)
    return json.loads(OUT.read_text(encoding="utf-8"))


def main() -> None:
    public_root = fetch_public_root()
    wav = make_wav()
    browser = run_browser(wav)
    require(bool(browser.get("ok")), "real browser Whisper fallback did not render a transcript")
    raw_vtt = browser.get("vttDownload")
    vtt = raw_vtt if isinstance(raw_vtt, dict) else {}
    require(bool(vtt.get("hasWebVtt")), "real browser Whisper VTT download missing WEBVTT")
    require(bool(vtt.get("hasFullTimestamp")), "real browser Whisper VTT download missing full timestamps")
    report = {"public_root": public_root, "browser": browser, "evidence": str(OUT)}
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
