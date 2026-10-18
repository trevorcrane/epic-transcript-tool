// Browser proof (PR fix/long-media-jobs): every page call to a guarded route
// carries X-Transcript-Session, and a 401 makes the page re-mint and retry once.
// Usage: node scripts/page_session_header_proof.cjs BASE_URL [CHROME_PATH]
// Real server calls: /api/session, /api/setup, /api/recent, /api/transcribe-upload (txt), /api/analyze.
// Mocked (no network): /api/transcribe-url-job (first call 401, then 202) and /api/jobs/<id> (first poll 502, then done).
const { chromium } = require('playwright-core');
const fs = require('fs'); const os = require('os'); const path = require('path');
const BASE = (process.argv[2] || 'http://127.0.0.1:8090').replace(/\/$/, '');
const CHROME = process.argv[3] || '/usr/bin/google-chrome';
const GUARDED = [/\/api\/transcribe-url-job$/, /\/api\/jobs\//, /\/api\/transcribe-url$/, /\/api\/transcribe-upload$/, /\/api\/analyze\//, /\/api\/analyze-all\//];
(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage();
  const seen = []; const mints = [];
  page.on('request', req => {
    const u = new URL(req.url());
    if (u.pathname === '/api/session') mints.push(u.pathname);
    if (GUARDED.some(rx => rx.test(u.pathname))) seen.push({ method: req.method(), path: u.pathname, session: !!req.headers()['x-transcript-session'] });
  });
  const record = { id: 'mockrec1', title: 'Mock', source: 'Mock', method: 'native-caption-subtitles', transcript: '[00:00] mocked words here', segments: [{ start: 0, end: 1, text: 'mocked words here' }], word_count: 3 };
  let jobPosts = 0;
  await page.route('**/api/transcribe-url-job', route => {
    jobPosts += 1;
    if (jobPosts === 1) return route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'expired' }) });
    return route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ ok: true, job: { id: 'mockjob1', status: 'queued' } }) });
  });
  // First poll returns a Cloudflare-style 502; the page must retry and still finish.
  let jobGets = 0;
  await page.route('**/api/jobs/**', route => {
    jobGets += 1;
    if (jobGets === 1) return route.fulfill({ status: 502, contentType: 'text/html', body: '<html>502 Bad Gateway</html>' });
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, job: { id: 'mockjob1', status: 'done', record } }) });
  });
  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  // 1) URL job (mocked): POST 401 -> re-mint -> POST 202 -> GET job done
  await page.fill('#url', 'https://youtu.be/dQw4w9WgXcQ');
  await page.click('#grab');
  await page.waitForFunction(() => document.getElementById('transcript') && document.getElementById('transcript').textContent.includes('mocked'), null, { timeout: 30000 });
  // 2) Real upload of a small txt file to the real server
  const tmp = path.join(os.tmpdir(), 'page-proof.txt'); fs.writeFileSync(tmp, 'Page session proof upload with several real words.');
  const uploadResp = page.waitForResponse(r => r.url().endsWith('/api/transcribe-upload'), { timeout: 15000 });
  await page.setInputFiles('#file', tmp);
  const up = await uploadResp;
  await page.waitForFunction(() => document.getElementById('transcript').textContent.includes('Page session proof'), null, { timeout: 15000 });
  // 3) Real analyze on the uploaded record
  const analyzeResp = page.waitForResponse(r => r.url().includes('/api/analyze/'), { timeout: 20000 });
  await page.click('#summaryBtn');
  const an = await analyzeResp;
  await browser.close();
  const result = {
    base: BASE, guarded_requests: seen, all_have_session: seen.length > 0 && seen.every(s => s.session),
    session_mints: mints.length, url_job_posts: jobPosts, retried_after_401: jobPosts === 2 && mints.length >= 2,
    job_polls: jobGets, poll_survived_502: jobGets >= 2,
    upload_status: up.status(), analyze_status: an.status(),
  };
  result.pass = result.all_have_session && result.retried_after_401 && result.poll_survived_502 && up.status() === 200 && an.status() === 200
    && ['/api/transcribe-url-job', '/api/transcribe-upload'].every(p => seen.some(s => s.path === p))
    && seen.some(s => s.path.startsWith('/api/jobs/')) && seen.some(s => s.path.startsWith('/api/analyze/'));
  console.log(JSON.stringify(result, null, 1));
  process.exit(result.pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
