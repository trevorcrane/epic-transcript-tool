const { chromium } = require('playwright');
const fs = require('fs');
const [base, wavPath, outPath] = process.argv.slice(2);
async function main(){
  const browser = await chromium.launch({headless:true});
  const context = await browser.newContext({viewport:{width:390,height:844}, isMobile:true, acceptDownloads:true});
  const page = await context.newPage();
  const errors=[]; const consoleMessages=[]; const statuses=[]; const requests=[];
  page.on('console', msg => { consoleMessages.push(`${msg.type()}: ${msg.text()}`); if (msg.type()==='error') errors.push(msg.text()); });
  page.on('pageerror', err => errors.push(String(err)));
  page.on('request', req => { if (req.url().includes('/api/') || req.url().includes('huggingface.co') || req.url().includes('jsdelivr')) requests.push(req.method()+' '+req.url()); });
  await page.route('**/api/transcribe-upload', route => route.fulfill({status:503, contentType:'application/json', body:JSON.stringify({error:'forced server failure so browser model must run'})}));
  const url = base.replace(/\/$/,'') + '/?phase2-browser-proof=webgpu&debug=' + Date.now();
  await page.goto(url, {waitUntil:'domcontentloaded', timeout:60000});
  await page.evaluate(() => localStorage.removeItem('epicTranscriptHistory'));
  const selectedDevice = await page.evaluate(() => (new URLSearchParams(location.search).has('forceBrowserWasm') ? 'wasm' : (navigator.gpu ? 'webgpu' : 'wasm')));
  await page.setInputFiles('#file', wavPath);
  const started = Date.now();
  let state = {};
  for (let i=0; i<240; i++){
    await page.waitForTimeout(1000);
    state = await page.evaluate(() => {
      const hist = JSON.parse(localStorage.getItem('epicTranscriptHistory')||'[]');
      const rec = hist[0] || {};
      const buttons = ['downloadTxtBtn','downloadMdBtn','downloadSrtBtn','downloadVttBtn'].reduce((acc,id)=>{ const el=document.getElementById(id); acc[id]={exists:!!el, disabled:!!el?.disabled, visible:!!(el && el.offsetParent !== null)}; return acc; },{});
      return {status:document.querySelector('#statusText')?.textContent||'', visible:document.querySelector('#result')?.classList.contains('show')||false, method:document.querySelector('#resultMethod')?.textContent||'', transcript:document.querySelector('#transcript')?.textContent||'', historyCount:hist.length, historyTranscript:rec.transcript||'', segments:Array.isArray(rec.segments)?rec.segments:[], language:rec.language||'', buttons};
    });
    if (state.status && !statuses.includes(state.status)) statuses.push(state.status);
    if (state.visible || state.status.startsWith('Error:')) break;
  }
  const downloads=[];
  for (const [fmt,id] of Object.entries({txt:'#downloadTxtBtn',md:'#downloadMdBtn',srt:'#downloadSrtBtn',vtt:'#downloadVttBtn'})){
    try{
      const p = page.waitForEvent('download', {timeout:5000});
      await page.click(id, {timeout:5000});
      const d = await p;
      const file = outPath.replace('.json', `-${fmt}`);
      await d.saveAs(file);
      const text = fs.readFileSync(file, 'utf8');
      downloads.push({fmt, ok:true, filename:d.suggestedFilename(), bytes:Buffer.byteLength(text), head:text.slice(0,80)});
    } catch(e){ downloads.push({fmt, ok:false, error:String(e)}); }
  }
  const screenshot = outPath.replace('.json','.png');
  await page.screenshot({path:screenshot, fullPage:true});
  const report={ok: state.visible && (state.transcript||'').trim().split(/\s+/).length>5, url, selectedDevice, elapsedSeconds:(Date.now()-started)/1000, statuses, state:{...state, wordCount:(state.transcript||'').trim().split(/\s+/).filter(Boolean).length, segmentCount:state.segments.length}, downloads, errors, consoleMessages, requests, screenshot};
  fs.writeFileSync(outPath, JSON.stringify(report,null,2));
  await context.close(); await browser.close();
  console.log(JSON.stringify(report,null,2));
  process.exit(report.ok ? 0 : 2);
}
main().catch(e=>{ console.error(e); process.exit(1); });
