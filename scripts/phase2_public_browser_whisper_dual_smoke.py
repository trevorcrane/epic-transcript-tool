#!/usr/bin/env python3
"""Public browser Whisper proof for WebGPU and forced WASM paths."""
from __future__ import annotations

import json, os, subprocess, sys, tempfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence" / "phase2-public-browser-whisper-dual-report.json"
BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://epic-transcript.robyncrane.com").rstrip("/")


def require(cond: bool, msg: str):
    if not cond: raise AssertionError(msg)


def make_wav() -> tuple[Path, dict[str, object]]:
    wav = Path(tempfile.gettempdir()) / "epic-browser-dual-whisper.wav"
    aiff = Path(tempfile.gettempdir()) / "epic-browser-dual-whisper.aiff"
    phrase = "Browser whisper multilingual timestamp proof for Epic transcript machine."
    subprocess.run(["say", "-o", str(aiff), phrase], check=True, timeout=30)
    subprocess.run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(wav)], check=True, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    probe = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(wav)], text=True)
    duration = float(json.loads(probe)["format"]["duration"])
    return wav, {"path": str(wav), "type": "wav", "duration_seconds": round(duration, 3), "language": "en", "expected_phrase": phrase}

NODE = r'''
const { chromium } = require('playwright');
const fs = require('fs');
const [base, wavPath, outPath] = process.argv.slice(2);
function increasing(segments){
  return Array.isArray(segments) && segments.length > 0 && segments.every((s,i)=>Number.isFinite(s.start) && Number.isFinite(s.end) && s.end > s.start && (i === 0 || s.start >= segments[i-1].start));
}
async function clickDownload(page, format, outPath, mode){
  const ids = {txt:'#downloadTxtBtn', md:'#downloadMdBtn', srt:'#downloadSrtBtn', vtt:'#downloadVttBtn'};
  const p = page.waitForEvent('download', {timeout:15000});
  await page.click(ids[format]);
  const d = await p;
  const file = outPath.replace('.json', `-${mode}.${format}`);
  await d.saveAs(file);
  const text = fs.readFileSync(file, 'utf8');
  return {format, path:file, filename:d.suggestedFilename(), bytes:Buffer.byteLength(text), hasTranscript:/Browser Whisper|browser whisper|Epic transcript/i.test(text), hasTimestamp:/00:00:00[,.]000 --> 00:00:/.test(text) || format === 'txt' || format === 'md', hasWebVtt:format !== 'vtt' || text.includes('WEBVTT')};
}
async function runOne(browser, mode){
  const url = base + '/?phase2-browser-proof=' + mode + (mode === 'wasm' ? '&forceBrowserWasm=1' : '');
  const context = await browser.newContext({ viewport:{width:390,height:844}, isMobile:true, acceptDownloads:true });
  const page = await context.newPage();
  const browserVersion = await browser.version();
  const errors=[]; const consoleMessages=[]; const statuses=[]; const requests=[];
  page.on('console', msg => { consoleMessages.push(`${msg.type()}: ${msg.text()}`); if (msg.type()==='error') errors.push(msg.text()); });
  page.on('pageerror', err => errors.push(String(err)));
  page.on('request', req => { if (req.url().includes('/api/') || req.url().includes('huggingface.co')) requests.push(req.method()+' '+req.url()); });
  await page.route('**/api/transcribe-upload', route => route.fulfill({status:503, contentType:'application/json', body:JSON.stringify({error:'forced server failure so browser model must run'})}));
  await page.goto(url, { waitUntil:'domcontentloaded', timeout:60000 });
  await page.evaluate(() => { localStorage.removeItem('epicTranscriptHistory'); });
  const selectedDevice = await page.evaluate(() => (new URLSearchParams(location.search).has('forceBrowserWasm') ? 'wasm' : (navigator.gpu ? 'webgpu' : 'wasm')));
  await page.setInputFiles('#file', wavPath);
  const started=Date.now(); let state={};
  for(let i=0;i<420;i++){
    await page.waitForTimeout(1000);
    state=await page.evaluate(() => {
      const hist = JSON.parse(localStorage.getItem('epicTranscriptHistory')||'[]');
      const rec = hist[0] || {};
      return {
        status:document.querySelector('#statusText')?.textContent||'',
        visible:document.querySelector('#result')?.classList.contains('show')||false,
        method:document.querySelector('#resultMethod')?.textContent||'',
        transcript:document.querySelector('#transcript')?.textContent||'',
        historyCount:hist.length,
        historyTranscript:rec.transcript || '',
        segments:Array.isArray(rec.segments) ? rec.segments : [],
        language:rec.language || '',
      };
    });
    if(state.status && !statuses.includes(state.status)) statuses.push(state.status);
    if(state.visible || state.status.startsWith('Error:')) break;
  }
  const screenshot = outPath.replace('.json', `-${mode}.png`);
  await page.screenshot({ path:screenshot, fullPage:true });
  const wordCount = (state.transcript || '').trim().split(/\s+/).filter(Boolean).length;
  const baseResult = {mode,url,browserVersion,selectedDevice,ok:false, elapsedSeconds:(Date.now()-started)/1000, statuses, requests, consoleMessages, errors, state:{...state, wordCount, segmentCount:state.segments.length, increasingTimestamps:increasing(state.segments)}, downloads:[], screenshot};
  if (!(state.visible && wordCount > 5 && state.method.includes('browser-whisper-'+mode) && increasing(state.segments))) {
    await context.close();
    return baseResult;
  }
  for (const fmt of ['txt','md','srt','vtt']) {
    try { baseResult.downloads.push(await clickDownload(page, fmt, outPath, mode)); }
    catch (e) { baseResult.errors.push(`download ${fmt}: ${e}`); }
  }
  await context.close();
  baseResult.ok = baseResult.downloads.length === 4 && baseResult.downloads.every(d => d.bytes > 20 && d.hasTranscript && d.hasTimestamp && d.hasWebVtt);
  return baseResult;
}
(async()=>{
  const browser=await chromium.launch({headless:true});
  const webgpu=await runOne(browser,'webgpu');
  const wasm=await runOne(browser,'wasm');
  await browser.close();
  const report={base, ok:webgpu.ok && wasm.ok, webgpu, wasm, preservesOriginalTranscriptIfOneRunFails:Boolean(webgpu.state?.transcript || wasm.state?.transcript)};
  fs.writeFileSync(outPath, JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
  process.exit(report.ok ? 0 : 2);
})().catch(e=>{ console.error(e); process.exit(1); });
'''

def main():
    req = Request(BASE + '/', headers={'User-Agent':'Mozilla/5.0 phase2-public-browser-whisper'})
    with urlopen(req, timeout=30) as res:
        html = res.read().decode('utf-8', errors='ignore')
    require(res.status == 200, f'public root {res.status}')
    for marker in ['@huggingface/transformers@3.7.2','Xenova/whisper-small','shouldPreferBrowserWhisper(file)','return_timestamps: true','chunks.map','forceBrowserWasm','actualDevice']:
        require(marker in html, f'missing public marker {marker}')
    require('@xenova/transformers@2.17.2' not in html, 'old Transformers.js v2 import still present')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wav, fixture = make_wav()
    js = Path(tempfile.gettempdir()) / 'phase2_public_browser_whisper_dual.js'
    js.write_text(NODE, encoding='utf-8')
    env = dict(os.environ); env['NODE_PATH'] = str(ROOT / 'node_modules')
    proc = subprocess.run(['node', str(js), BASE, str(wav), str(OUT)], cwd=str(ROOT), env=env, text=True, capture_output=True, timeout=900)
    if OUT.exists():
        report = json.loads(OUT.read_text())
        report['fixture'] = fixture
        OUT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    sys.stdout.write(proc.stdout)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)

if __name__ == '__main__':
    main()
