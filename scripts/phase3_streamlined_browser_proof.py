#!/usr/bin/env python3
"""Browser proof for the streamlined Phase 3 UI."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = sys.argv[1] if len(sys.argv) > 1 else "https://epic-transcript.robyncrane.com/?v=7e02e50"
OUT = ROOT / "evidence" / "phase3-streamlined-browser-proof.json"
DESKTOP = ROOT / "evidence" / "phase3-streamlined-desktop.png"
MOBILE = ROOT / "evidence" / "phase3-streamlined-mobile.png"

NODE = r'''
const { chromium } = require('playwright');
const fs = require('fs');
const crypto = require('crypto');
const url = process.argv[2];
const outPath = process.argv[3];
const desktopShot = process.argv[4];
const mobileShot = process.argv[5];
function sha(path) { return crypto.createHash('sha256').update(fs.readFileSync(path)).digest('hex'); }
async function runViewport(browser, viewport, shotPath) {
  const context = await browser.newContext({ viewport, isMobile: viewport.width < 600, acceptDownloads: true });
  const page = await context.newPage();
  const network = [];
  page.on('request', req => { if (req.url().includes('/api/')) network.push({method:req.method(), url:req.url()}); });
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.fill('#url', 'https://youtu.be/dQw4w9WgXcQ');
  await page.click('#grab');
  await page.waitForFunction(() => document.querySelector('#result')?.classList.contains('show') && (document.querySelector('#transcript')?.textContent || '').length > 100, null, { timeout: 120000 });
  await page.click('#copyBtn');
  const downloads = {};
  for (const fmt of ['txt','md','srt']) {
    await page.selectOption('#downloadFormat', fmt);
    const d = await Promise.all([page.waitForEvent('download', { timeout: 30000 }), page.click('#downloadBtn')]).then(x => x[0]);
    downloads[fmt] = { suggestedFilename: d.suggestedFilename() };
  }
  await page.click('#summaryBtn');
  await page.waitForFunction(() => (document.querySelector('#analysisBox')?.textContent || '').length > 120, null, { timeout: 90000 });
  const summary = await page.textContent('#analysisBox');
  await page.click('#actionsBtn');
  await page.waitForFunction(old => (document.querySelector('#analysisBox')?.textContent || '') !== old && (document.querySelector('#analysisBox')?.textContent || '').length > 120, summary, { timeout: 90000 });
  const actions = await page.textContent('#analysisBox');
  await page.fill('#questionInput', 'Give me quotes, chapters, hooks, and FAQ ideas.');
  await page.click('#askBtn');
  await page.waitForFunction(old => (document.querySelector('#analysisBox')?.textContent || '') !== old && (document.querySelector('#analysisBox')?.textContent || '').length > 120, actions, { timeout: 90000 });
  const ask = await page.textContent('#analysisBox');
  await page.click('#drawerHead');
  await page.screenshot({ path: shotPath, fullPage: true });
  const proof = await page.evaluate(() => {
    const required = ['transcript','copyBtn','downloadFormat','downloadBtn','summaryBtn','actionsBtn','questionInput','askBtn','drawerHead'];
    const retired = ['allAnalysisBtn','analysisMenu','downloadVttBtn','downloadMdBtn','downloadSrtBtn','analysisCopyBtn','analysisDownloadBtn','emailBtn'];
    return {
      requiredPresent: Object.fromEntries(required.map(id => [id, !!document.getElementById(id)])),
      retiredAbsent: Object.fromEntries(retired.map(id => [id, !document.getElementById(id)])),
      downloadOptions: [...document.querySelectorAll('#downloadFormat option')].map(o => o.value),
      transcriptChars: (document.querySelector('#transcript')?.textContent || '').length,
      historyOpen: document.querySelector('#drawer')?.classList.contains('open'),
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      visibleButtonText: [...document.querySelectorAll('button')].map(b => b.textContent.trim()).filter(Boolean),
    };
  });
  await context.close();
  return { viewport, proof, downloads, outputs: { summary: summary.slice(0, 700), action_items: actions.slice(0,700), ask: ask.slice(0,700)}, network };
}
(async () => {
  const browser = await chromium.launch({ headless: true });
  const desktop = await runViewport(browser, { width: 1440, height: 1100 }, desktopShot);
  const mobile = await runViewport(browser, { width: 390, height: 844 }, mobileShot);
  await browser.close();
  const report = { ok: true, url, desktop, mobile, screenshots: { desktop: desktopShot, desktop_sha256: sha(desktopShot), mobile: mobileShot, mobile_sha256: sha(mobileShot) } };
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ ok: true, screenshots: report.screenshots, desktop: desktop.proof, mobile: mobile.proof }, null, 2));
})().catch(err => { console.error(err); process.exit(1); });
'''

def main() -> None:
    node_modules = ROOT / "node_modules"
    env = dict(os.environ)
    env["NODE_PATH"] = str(node_modules)
    js_path = Path("/tmp/phase3_streamlined_browser_proof.js")
    js_path.write_text(NODE)
    proc = subprocess.run(["node", str(js_path), BASE, str(OUT), str(DESKTOP), str(MOBILE)], cwd=ROOT, env=env, text=True, capture_output=True, timeout=600)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    raise SystemExit(proc.returncode)

if __name__ == "__main__":
    main()
