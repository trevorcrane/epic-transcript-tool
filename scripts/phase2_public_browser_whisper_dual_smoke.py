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


def make_wav() -> Path:
    wav = Path(tempfile.gettempdir()) / "epic-browser-dual-whisper.wav"
    aiff = Path(tempfile.gettempdir()) / "epic-browser-dual-whisper.aiff"
    phrase = "Browser whisper multilingual timestamp proof for Epic transcript machine."
    subprocess.run(["say", "-o", str(aiff), phrase], check=True, timeout=30)
    subprocess.run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(wav)], check=True, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return wav

NODE = r'''
const { chromium } = require('playwright');
const fs = require('fs');
const [base, wavPath, outPath] = process.argv.slice(2);
async function runOne(browser, mode){
  const url = base + '/?phase2-browser-proof=' + mode + (mode === 'wasm' ? '&forceBrowserWasm=1' : '');
  const context = await browser.newContext({ viewport:{width:390,height:844}, isMobile:true, acceptDownloads:true });
  const page = await context.newPage();
  const errors=[]; const statuses=[]; const requests=[];
  page.on('console', msg => { if (msg.type()==='error') errors.push(msg.text()); });
  page.on('pageerror', err => errors.push(String(err)));
  page.on('request', req => { if (req.url().includes('/api/')) requests.push(req.method()+' '+req.url()); });
  await page.route('**/api/transcribe-upload', route => route.fulfill({status:503, contentType:'application/json', body:JSON.stringify({error:'forced server failure so browser model must run'})}));
  await page.goto(url, { waitUntil:'domcontentloaded', timeout:60000 });
  await page.setInputFiles('#file', wavPath);
  const started=Date.now(); let state={};
  for(let i=0;i<420;i++){
    await page.waitForTimeout(1000);
    state=await page.evaluate(() => ({
      status:document.querySelector('#statusText')?.textContent||'',
      visible:document.querySelector('#result')?.classList.contains('show')||false,
      method:document.querySelector('#resultMethod')?.textContent||'',
      transcript:document.querySelector('#transcript')?.textContent||'',
      historyCount:JSON.parse(localStorage.getItem('epicTranscriptHistory')||'[]').length,
      segments:JSON.parse(localStorage.getItem('epicTranscriptHistory')||'[]')[0]?.segments?.length||0
    }));
    if(state.status && !statuses.includes(state.status)) statuses.push(state.status);
    if(state.visible || state.status.startsWith('Error:')) break;
  }
  const downloadPromise = page.waitForEvent('download', {timeout:15000});
  await page.click('#downloadVttBtn');
  const download = await downloadPromise;
  const vttPath = outPath.replace('.json', `-${mode}.vtt`);
  await download.saveAs(vttPath);
  const vtt = fs.readFileSync(vttPath, 'utf8');
  const screenshot = outPath.replace('.json', `-${mode}.png`);
  await page.screenshot({ path:screenshot, fullPage:true });
  await context.close();
  return {mode,url,ok:Boolean(state.visible && state.transcript.length>20 && state.method.includes('browser-whisper-'+mode)), elapsedSeconds:(Date.now()-started)/1000, statuses, requests, errors, state, vtt:{path:vttPath, bytes:Buffer.byteLength(vtt), hasWebVtt:vtt.includes('WEBVTT'), hasTimestamp:/00:00:00\.000 --> 00:00:/.test(vtt)}, screenshot};
}
(async()=>{
  const browser=await chromium.launch({headless:true});
  const webgpu=await runOne(browser,'webgpu');
  const wasm=await runOne(browser,'wasm');
  await browser.close();
  const report={base, ok:webgpu.ok && wasm.ok && webgpu.vtt.hasWebVtt && wasm.vtt.hasWebVtt && webgpu.vtt.hasTimestamp && wasm.vtt.hasTimestamp, webgpu, wasm};
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
    for marker in ['Xenova/whisper-small','shouldPreferBrowserWhisper(file)','return_timestamps: true','chunks.map','forceBrowserWasm']:
        require(marker in html, f'missing public marker {marker}')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wav = make_wav()
    js = Path(tempfile.gettempdir()) / 'phase2_public_browser_whisper_dual.js'
    js.write_text(NODE, encoding='utf-8')
    env = dict(os.environ); env['NODE_PATH'] = str(ROOT / 'node_modules')
    proc = subprocess.run(['node', str(js), BASE, str(wav), str(OUT)], cwd=str(ROOT), env=env, text=True, capture_output=True, timeout=900)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout)

if __name__ == '__main__':
    main()
