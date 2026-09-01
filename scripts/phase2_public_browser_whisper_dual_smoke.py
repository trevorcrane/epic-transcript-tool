#!/usr/bin/env python3
"""Public browser Whisper proof for WebGPU hardware and WASM fallback paths."""
from __future__ import annotations

import hashlib, json, os, platform, subprocess, sys, tempfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence" / "phase2-public-browser-whisper-dual-report.json"
BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://epic-transcript.robyncrane.com").rstrip("/")


def require(cond: bool, msg: str):
    if not cond: raise AssertionError(msg)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_hash() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def make_wav() -> tuple[Path, dict[str, object]]:
    wav = Path(tempfile.gettempdir()) / "epic-browser-dual-whisper.wav"
    aiff = Path(tempfile.gettempdir()) / "epic-browser-dual-whisper.aiff"
    phrase = "Browser whisper multilingual timestamp proof for Epic transcript machine."
    subprocess.run(["say", "-o", str(aiff), phrase], check=True, timeout=30)
    subprocess.run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(wav)], check=True, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    probe = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(wav)], text=True)
    duration = float(json.loads(probe)["format"]["duration"])
    return wav, {"filename": wav.name, "sha256": sha256_file(wav), "type": "wav", "sample_rate_hz": 16000, "channels": 1, "duration_seconds": round(duration, 3), "language": "en", "expected_phrase": phrase}

NODE = r'''
const { chromium, webkit } = require('playwright');
const fs = require('fs');
const [base, wavPath, outPath] = process.argv.slice(2);
function increasing(segments){
  return Array.isArray(segments) && segments.length > 0 && segments.every((s,i)=>Number.isFinite(s.start) && Number.isFinite(s.end) && s.end > s.start && (i === 0 || s.start >= segments[i-1].start));
}
async function gpuProbe(page){
  return await page.evaluate(async()=>{
    const proof={hasNavigatorGpu:!!navigator.gpu, adapterRequested:false, adapterAvailable:false, requestDeviceOk:false, adapterFeatures:[], wgslLanguageFeatures:[], error:null};
    proof.userAgent = navigator.userAgent;
    proof.platform = navigator.platform;
    proof.hardwareConcurrency = navigator.hardwareConcurrency;
    proof.deviceMemory = navigator.deviceMemory || null;
    try{
      proof.wgslLanguageFeatures = navigator.gpu?.wgslLanguageFeatures ? [...navigator.gpu.wgslLanguageFeatures] : [];
      if(navigator.gpu){
        proof.adapterRequested = true;
        const adapter = await navigator.gpu.requestAdapter({powerPreference:'high-performance'});
        proof.adapterAvailable = !!adapter;
        if(adapter){
          proof.adapterFeatures = [...adapter.features].sort();
          if(adapter.limits){
            proof.adapterLimits = {
              maxTextureDimension2D: adapter.limits.maxTextureDimension2D,
              maxBufferSize: adapter.limits.maxBufferSize,
              maxComputeWorkgroupSizeX: adapter.limits.maxComputeWorkgroupSizeX,
              maxComputeInvocationsPerWorkgroup: adapter.limits.maxComputeInvocationsPerWorkgroup
            };
          }
          if(adapter.requestAdapterInfo){
            try{ proof.adapterInfo = await adapter.requestAdapterInfo(); } catch(e){ proof.adapterInfoError = String(e); }
          }
          const device = await adapter.requestDevice();
          proof.requestDeviceOk = !!device;
          if(device){
            const buffer = device.createBuffer({size:4, usage:GPUBufferUsage.COPY_DST | GPUBufferUsage.COPY_SRC});
            device.queue.writeBuffer(buffer, 0, new Uint32Array([42]));
            proof.deviceQueueWriteOk = true;
            device.destroy();
          }
        }
      }
    }catch(e){ proof.error = String(e); }
    return proof;
  });
}
async function clickDownload(page, format, outPath, label){
  const ids = {txt:'#downloadBtn', md:'#downloadMdBtn', srt:'#downloadSrtBtn', vtt:'#downloadVttBtn'};
  const p = page.waitForEvent('download', {timeout:15000});
  await page.click(ids[format]);
  const d = await p;
  const file = outPath.replace('.json', `-${label}.${format}`);
  await d.saveAs(file);
  const text = fs.readFileSync(file, 'utf8');
  return {format, path:file, filename:d.suggestedFilename(), bytes:Buffer.byteLength(text), sha256:require('crypto').createHash('sha256').update(text).digest('hex'), hasTranscript:/Browser Whisper|browser whisper|Epic transcript/i.test(text), hasTimestamp:/00:00:00[,.]000 --> 00:00:/.test(text) || format === 'txt' || format === 'md', hasWebVtt:format !== 'vtt' || text.includes('WEBVTT'), head:text.slice(0,180)};
}
async function runOne(browser, label, mode, viewport, isMobile){
  const url = label === 'no-webgpu-mobile-fallback'
    ? base + '/'
    : base + '/?phase2-browser-proof=' + label + (mode === 'wasm' ? '&forceBrowserWasm=1' : '');
  const context = await browser.newContext({ viewport, isMobile, acceptDownloads:true });
  const page = await context.newPage();
  const browserVersion = await browser.version();
  const errors=[]; const consoleMessages=[]; const statuses=[]; const requests=[]; const responses=[];
  page.on('console', msg => { consoleMessages.push(`${msg.type()}: ${msg.text()}`); if (msg.type()==='error') errors.push(msg.text()); });
  page.on('pageerror', err => errors.push(String(err)));
  page.on('request', req => { if (req.url().includes('/api/') || req.url().includes('huggingface.co')) requests.push(req.method()+' '+req.url()); });
  page.on('response', res => { if (res.url().includes('/api/') || res.url().includes('huggingface.co')) responses.push({status:res.status(), url:res.url()}); });
  await page.route('**/api/transcribe-upload', route => route.fulfill({status:503, contentType:'application/json', body:JSON.stringify({error:'forced server failure so browser model must run'})}));
  await page.goto(url, { waitUntil:'domcontentloaded', timeout:60000 });
  await page.evaluate(() => { localStorage.removeItem('epicTranscriptHistory'); });
  const gpuProof = await gpuProbe(page);
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
  const screenshot = outPath.replace('.json', `-${label}.png`);
  await page.screenshot({ path:screenshot, fullPage:true });
  const wordCount = (state.transcript || '').trim().split(/\s+/).filter(Boolean).length;
  const baseResult = {label, mode, url, viewport, isMobile, browserVersion, selectedDevice, gpuProof, ok:false, elapsedSeconds:(Date.now()-started)/1000, statuses, requests, responses, consoleMessages, errors, state:{...state, wordCount, segmentCount:state.segments.length, increasingTimestamps:increasing(state.segments)}, downloads:[], screenshot};
  const gpuRequirementOk = mode === 'wasm' || (gpuProof.hasNavigatorGpu && gpuProof.adapterRequested && gpuProof.adapterAvailable && gpuProof.requestDeviceOk && gpuProof.deviceQueueWriteOk);
  if (!(gpuRequirementOk && state.visible && wordCount > 5 && state.method.includes('browser-whisper-'+mode) && increasing(state.segments))) {
    await context.close();
    return baseResult;
  }
  for (const fmt of ['txt','md','srt','vtt']) {
    try { baseResult.downloads.push(await clickDownload(page, fmt, outPath, label)); }
    catch (e) { baseResult.errors.push(`download ${fmt}: ${e}`); }
  }
  await context.close();
  baseResult.ok = baseResult.downloads.length === 4 && baseResult.downloads.every(d => d.bytes > 20 && d.hasTranscript && d.hasTimestamp && d.hasWebVtt);
  return baseResult;
}
(async()=>{
  const browser=await chromium.launch({
    headless:true,
    args:['--enable-unsafe-webgpu','--use-angle=metal','--ignore-gpu-blocklist']
  });
  const desktopWebgpu=await runOne(browser,'desktop-webgpu','webgpu',{width:1440,height:900},false);
  const mobileWebgpu=await runOne(browser,'mobile-webgpu','webgpu',{width:390,height:844},true);
  const mobileWasm=await runOne(browser,'mobile-wasm','wasm',{width:390,height:844},true);
  await browser.close();
  const noGpuBrowser=await webkit.launch({headless:true});
  const noWebgpuMobileFallback=await runOne(noGpuBrowser,'no-webgpu-mobile-fallback','wasm',{width:390,height:844},true);
  await noGpuBrowser.close();
  const report={base, ok:desktopWebgpu.ok && mobileWebgpu.ok && mobileWasm.ok && noWebgpuMobileFallback.ok && noWebgpuMobileFallback.gpuProof.hasNavigatorGpu === false && noWebgpuMobileFallback.selectedDevice === 'wasm' && !noWebgpuMobileFallback.url.includes('forceBrowserWasm'), desktopWebgpu, mobileWebgpu, mobileWasm, noWebgpuMobileFallback, preservesOriginalTranscriptIfOneRunFails:Boolean(desktopWebgpu.state?.transcript || mobileWebgpu.state?.transcript || mobileWasm.state?.transcript || noWebgpuMobileFallback.state?.transcript)};
  fs.writeFileSync(outPath, JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
  process.exit(report.ok ? 0 : 2);
})().catch(e=>{ console.error(e); process.exit(1); });
'''

def main():
    req = Request(BASE + '/', headers={'User-Agent':'Mozilla/5.0 phase2-public-browser-whisper'})
    with urlopen(req, timeout=30) as res:
        html_bytes = res.read()
    html = html_bytes.decode('utf-8', errors='ignore')
    require(res.status == 200, f'public root {res.status}')
    for marker in ['@huggingface/transformers@3.7.2','onnx-community/whisper-tiny','shouldPreferBrowserWhisper(file)','return_timestamps: true','chunks.map','forceBrowserWasm','actualDevice','withBrowserWhisperTimeout','browserWhisperDtype']:
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
        report['production'] = {'url': BASE + '/', 'cache_busted_url': BASE + '/?phase2-webgpu-proof=' + git_hash()[:7], 'html_sha256': hashlib.sha256(html_bytes).hexdigest(), 'git_head': git_hash()}
        report['runner'] = {'system': platform.system(), 'release': platform.release(), 'machine': platform.machine(), 'python': platform.python_version(), 'node': subprocess.check_output(['node','-v'], text=True).strip()}
        OUT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    sys.stdout.write(proc.stdout)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)

if __name__ == '__main__':
    main()
