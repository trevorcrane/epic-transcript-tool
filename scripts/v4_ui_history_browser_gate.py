#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence' / 'v4-ui-history-browser-gate.json'
BASE = os.environ.get('EPIC_TRANSCRIPT_URL', 'https://epic-transcript.robyncrane.com').rstrip('/')
IMMUTABLE = os.environ.get('EPIC_TRANSCRIPT_IMMUTABLE', '')
REGRESSION_URL = os.environ.get('EPIC_REGRESSION_URL', 'https://youtu.be/v34Eg12mhDM?si=lqfq-8bhlxADDZdD')
NODE = r'''
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const [base, immutable, outPath, regressionUrl] = process.argv.slice(2);
const evidenceDir = path.dirname(outPath);
function wordCount(t){ return String(t||'').trim().split(/\s+/).filter(Boolean).length; }
async function download(page, selector, name){
  const p = page.waitForEvent('download', {timeout:20000});
  await page.click(selector);
  const d = await p;
  const file = path.join(evidenceDir, name);
  await d.saveAs(file);
  const text = fs.readFileSync(file, 'utf8');
  return {name, path:file, bytes:Buffer.byteLength(text), hasText:text.trim().length>0, hasTimestamp:/00:00:/.test(text) || name.endsWith('.txt') || name.endsWith('.md'), hasWebVtt:!name.endsWith('.vtt') || text.includes('WEBVTT')};
}
async function screenshot(page, name){ const file=path.join(evidenceDir, name); await page.screenshot({path:file, fullPage:true}); return file; }
async function waitResult(page){
  for (let i=0;i<180;i++){
    await page.waitForTimeout(i<8?1000:2000);
    const state=await page.evaluate(() => ({
      status:document.querySelector('#statusText')?.textContent||'',
      visible:document.querySelector('#result')?.classList.contains('show')||false,
      transcript:document.querySelector('#transcript')?.textContent||'',
      method:document.querySelector('#resultMethod')?.textContent||'',
      source:document.querySelector('#resultSource')?.textContent||'',
    }));
    if (state.visible && state.transcript.length>50) return state;
    if (state.status.startsWith('Error:')) throw new Error(state.status);
  }
  throw new Error('result timeout');
}
async function main(){
  fs.mkdirSync(evidenceDir,{recursive:true});
  const browser=await chromium.launch({headless:true});
  const report={base, immutable, browserVersion:await browser.version(), ok:false, screenshots:{}, checks:{}, downloads:[], network:[]};
  const ctx=await browser.newContext({viewport:{width:1440,height:1100}, acceptDownloads:true});
  const page=await ctx.newPage();
  page.on('request', req => { if(req.url().includes('/api/')) report.network.push(req.method()+' '+req.url()); });
  await page.goto(base+'/?v4-ui-proof='+Date.now(), {waitUntil:'domcontentloaded', timeout:60000});
  await page.evaluate(() => { localStorage.removeItem('epicTranscriptHistory'); localStorage.setItem('epicTranscriptTheme','dark'); document.body.dataset.theme='dark'; });
  report.checks.noLeakage = await page.evaluate(() => !/Call IQ|crawl|reference|design-version|v5\.0\.0|call-iq/.test(document.documentElement.outerHTML));
  report.checks.footer = await page.locator('footer').innerText();
  report.checks.footerOk = report.checks.footer === 'EPIC Transcript Machine · v4.0.0 · Powered by epic.media';
  report.screenshots.desktopDark = await screenshot(page,'v4-desktop-dark.png');
  await page.click('#themeToggle');
  report.screenshots.desktopLight = await screenshot(page,'v4-desktop-light.png');
  report.checks.lightTextColors = await page.evaluate(() => {
    const ids=['url','transcript','resultMethod'];
    return ids.map(id => { const el=document.getElementById(id); const cs=el?getComputedStyle(el):null; return {id, color:cs&&cs.color, background:cs&&cs.backgroundColor}; });
  });
  report.checks.focus = await page.evaluate(() => {
    const ids=['themeToggle','url','grab','drop','drawerHead'];
    return ids.map(id => { const el=document.getElementById(id); el.focus(); return {id, focused:document.activeElement===el, minW:el.getBoundingClientRect().width, minH:el.getBoundingClientRect().height, aria:el.getAttribute('aria-label')||el.getAttribute('role')||''}; });
  });
  report.checks.reducedMotion = await page.emulateMedia({reducedMotion:'reduce'}).then(()=>page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches));
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(() => { document.body.dataset.theme='dark'; });
  report.checks.mobileOverflowDark = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  report.screenshots.mobileDark = await screenshot(page,'v4-mobile-390-dark.png');
  await page.click('#themeToggle');
  report.checks.mobileOverflowLight = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  report.screenshots.mobileLight = await screenshot(page,'v4-mobile-390-light.png');
  await page.setViewportSize({width:1440,height:1100});
  await page.fill('#url', regressionUrl);
  await page.click('#grab');
  const transcriptState = await waitResult(page);
  report.regressionTranscript = {...transcriptState, wordCount:wordCount(transcriptState.transcript)};
  await page.click('#copyBtn');
  const clip = await page.evaluate(async () => await navigator.clipboard.readText().catch(() => ''));
  report.checks.copyOk = clip && clip.slice(0,80) === transcriptState.transcript.slice(0,80);
  report.downloads.push(await download(page,'#downloadBtn','v4-regression.txt'));
  report.downloads.push(await download(page,'#downloadMdBtn','v4-regression.md'));
  report.downloads.push(await download(page,'#downloadSrtBtn','v4-regression.srt'));
  report.downloads.push(await download(page,'#downloadVttBtn','v4-regression.vtt'));
  await page.click('#drawerHead');
  const histBefore=await page.evaluate(() => ({count:JSON.parse(localStorage.getItem('epicTranscriptHistory')||'[]').length, open:document.querySelector('#drawer').classList.contains('open')}));
  await page.reload({waitUntil:'domcontentloaded'});
  const histReload=await page.evaluate(() => JSON.parse(localStorage.getItem('epicTranscriptHistory')||'[]').length);
  await page.click('#drawerHead');
  await page.click('#clearHistoryBtn');
  const histAfter=await page.evaluate(() => JSON.parse(localStorage.getItem('epicTranscriptHistory')||'[]').length);
  report.history = {before:histBefore, afterReload:histReload, afterClear:histAfter};
  await page.evaluate((rec) => {
    window.localStorage.setItem('epicTranscriptHistory', JSON.stringify([{id:'preserve-proof', source:'Preserved transcript', title:'Preserved transcript', method:'proof', created_at:new Date().toISOString(), transcript:rec.transcript, segments:[{start:0,end:2,text:'Preserved transcript text'}], duration_seconds:2, processing_seconds:1, browser_only:true}]));
    location.reload();
  }, transcriptState);
  await page.waitForLoadState('domcontentloaded');
  await page.click('#drawerHead');
  await page.click('.recent-item');
  await page.route('**/api/transcribe-upload', route => route.fulfill({status:503, contentType:'application/json', body:JSON.stringify({detail:'forced upload failure for preserve proof'})}));
  await page.evaluate(() => { const cb=document.querySelector('#browserLocal'); if(cb) cb.checked=false; });
  const txt=path.join(evidenceDir,'v4-upload-failure.txt'); fs.writeFileSync(txt,'This upload intentionally fails to prove the prior transcript stays visible.');
  await page.setInputFiles('#file', txt);
  await page.waitForTimeout(2500);
  report.failurePreserve = await page.evaluate(() => ({visible:document.querySelector('#result')?.classList.contains('show')||false, transcript:document.querySelector('#transcript')?.textContent||'', status:document.querySelector('#statusText')?.textContent||''}));
  await ctx.close();
  if (immutable) {
    const r = await (await browser.newPage()).goto(immutable, {waitUntil:'domcontentloaded', timeout:60000}).catch(e => null);
  }
  await browser.close();
  report.ok = report.checks.noLeakage && report.checks.footerOk && !report.checks.mobileOverflowDark && !report.checks.mobileOverflowLight && report.regressionTranscript.wordCount > 100 && report.checks.copyOk && report.downloads.length===4 && report.downloads.every(d=>d.bytes>20 && d.hasText && d.hasTimestamp && d.hasWebVtt) && report.history.before.count>=1 && report.history.afterReload>=1 && report.history.afterClear===0 && report.failurePreserve.visible && report.failurePreserve.transcript.includes('transcript');
  fs.writeFileSync(outPath, JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
  process.exit(report.ok ? 0 : 2);
}
main().catch(e=>{ console.error(e); process.exit(1); });
'''

def main():
    js=Path(tempfile.gettempdir())/'v4_ui_history_browser_gate.js'
    js.write_text(NODE)
    env=dict(os.environ); env['NODE_PATH']=str(ROOT/'node_modules')
    proc=subprocess.run(['node',str(js),BASE,IMMUTABLE,str(OUT),REGRESSION_URL],cwd=ROOT,env=env,text=True,capture_output=True,timeout=420)
    print(proc.stdout)
    if proc.returncode:
        print(proc.stderr)
        raise SystemExit(proc.returncode)
if __name__=='__main__': main()
