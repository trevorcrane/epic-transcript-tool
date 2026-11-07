const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { chromium } = require('playwright');

const root = path.join(__dirname, '..');
const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'epic-shot-ui-'));
const port = 8766;
const base = `http://127.0.0.1:${port}`;
const jpeg = Buffer.from(
  '/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxISEhUQEhIVFhUVFRUVFRUVFRUVFRUWFxUVFRUYHSggGBolGxUVITEhJSkrLi4uFx8zODMtNygtLisBCgoKDg0OGhAQGy0lHyUtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAAEAAQMBIgACEQEDEQH/xAAbAAABBQEBAAAAAAAAAAAAAAADAAIEBQYBB//EABQBAQAAAAAAAAAAAAAAAAAAAAD/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8Anf/Z',
  'base64'
);

function startServer() {
  const python = path.join(root, '.venv', 'bin', 'python');
  return spawn(python, ['app.py'], {
    cwd: root,
    env: {
      ...process.env,
      PORT: String(port),
      TRANSCRIPT_AUTH_MODE: 'log',
      TRANSCRIPT_DATA_DIR: dataDir,
      TRANSCRIPT_STATIC_DIR: path.join(root, 'static'),
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

async function waitForHealth(proc) {
  const deadline = Date.now() + 20000;
  let stderr = '';
  proc.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${base}/health`);
      if (res.ok) return;
    } catch (err) { /* server still booting */ }
    if (proc.exitCode !== null) throw new Error(`server exited ${proc.exitCode}: ${stderr}`);
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`health timeout: ${stderr}`);
}

function jobBody(mode) {
  const record = { id: 'rec-ui', source: 'Synthetic clip', transcript: 'hello from the fixture', method: 'captions' };
  let screenshots = null;
  if (mode === 'shots') {
    screenshots = {
      status: 'done', error: null, count: 1, shown: 1,
      frames: [{ time: 1, timestamp: '0:01', filename: 'frame_0000_0001.00s.jpg', url: '/api/jobs/abc123abc123/screenshots/frame_0000_0001.00s.jpg' }],
      zip_url: '/api/jobs/abc123abc123/screenshots.zip',
    };
    record.screenshots = screenshots;
  } else if (mode === 'error') {
    screenshots = { status: 'error', error: 'Screenshots could not be captured.', count: 0, shown: 0, frames: [], zip_url: null };
    record.screenshots = screenshots;
  }
  return { ok: true, job: { id: 'abc123abc123', status: 'done', record, screenshots } };
}

async function installRoutes(page, state) {
  await page.route('**/api/transcribe-url-job', async (route) => {
    state.posts.push(route.request().postData() || '');
    await route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, job: { id: 'abc123abc123', status: 'queued' } }),
    });
  });
  await page.route(/\/api\/jobs\//, async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    const session = route.request().headers()['x-transcript-session'] || '';
    if (pathname.endsWith('/screenshots/frame_0000_0001.00s.jpg')) {
      state.imageHits.push(session);
      await route.fulfill({ status: 200, contentType: 'image/jpeg', body: jpeg });
      return;
    }
    if (pathname.endsWith('/screenshots.zip')) {
      state.zipHits.push(session);
      await route.fulfill({ status: 200, contentType: 'application/zip', body: Buffer.from('PK') });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(jobBody(state.mode)),
    });
  });
}

async function runMode(page, state, mode) {
  state.mode = mode;
  state.posts = [];
  state.imageHits = [];
  state.zipHits = [];
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  await page.fill('#url', 'https://example.com/synthetic.mp4');
  const imageResponse = mode === 'shots'
    ? page.waitForResponse((res) => res.url().includes('/screenshots/frame_'))
    : null;
  if (mode === 'only') await page.click('#grab');
  else await page.click('#grabShots');
  await page.waitForFunction(() => (document.querySelector('#transcript') || {}).textContent.includes('hello from the fixture'));
  if (imageResponse) await imageResponse;
  const transcript = await page.locator('#transcript').innerText();
  const galleryHidden = await page.locator('#shotsGallery').getAttribute('hidden');
  const note = await page.locator('#shotsNote').innerText();
  const status = await page.locator('#statusText').innerText();
  const success = await page.locator('#successMessage').evaluate((el) => el.classList.contains('success-ready'));
  let cardText = '';
  if (mode === 'shots') {
    await page.waitForFunction(() => (document.querySelector('.shot-card img') || {}).src.startsWith('blob:'));
    cardText = await page.locator('.shot-card').innerText();
    const zipResponse = page.waitForResponse((res) => res.url().includes('/screenshots.zip'));
    await page.click('button.shots-zip');
    await zipResponse;
    await page.click('button.shot-copy');
  }
  return {
    posts: state.posts.slice(),
    imageHits: state.imageHits.slice(),
    zipHits: state.zipHits.slice(),
    transcript, galleryHidden, note, status, success, cardText, mode,
  };
}

async function main() {
  const proc = startServer();
  const browser = await chromium.launch({
    executablePath: '/usr/local/bin/google-chrome',
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const report = { ok: false, modes: {} };
  try {
    await waitForHealth(proc);
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    page.on('pageerror', (err) => console.error('PAGE', err.message));
    const state = { mode: 'only', posts: [], imageHits: [], zipHits: [] };
    await installRoutes(page, state);
    await page.goto(base, { waitUntil: 'domcontentloaded' });
    report.buttons = {
      only: (await page.locator('#grab').innerText()).trim(),
      shots: (await page.locator('#grabShots').innerText()).trim(),
    };
    if (report.buttons.only !== 'Transcript only' || report.buttons.shots !== 'Transcript with screenshots') {
      throw new Error(`unexpected buttons ${JSON.stringify(report.buttons)}`);
    }
    report.modes.only = await runMode(page, state, 'only');
    report.modes.shots = await runMode(page, state, 'shots');
    report.modes.error = await runMode(page, state, 'error');
    const only = report.modes.only;
    const shots = report.modes.shots;
    const failed = report.modes.error;
    if (only.posts.some((body) => body.includes('include_screenshots'))) throw new Error('transcript only sent include_screenshots');
    if (!shots.posts.some((body) => body.includes('include_screenshots=1'))) throw new Error('screenshot mode did not request screenshots');
    if (only.galleryHidden === null) throw new Error('transcript only showed the gallery');
    if (!only.transcript.includes('hello from the fixture')) throw new Error('missing transcript only text');
    if (shots.galleryHidden !== null) throw new Error('gallery stayed hidden');
    if (!shots.cardText.includes('0:01') || !shots.cardText.includes('Copy image')) {
      throw new Error(`gallery missing timestamp or copy: ${shots.cardText}`);
    }
    if (!shots.imageHits.length || !shots.imageHits[0]) throw new Error('image fetch did not send the page session: ' + JSON.stringify(shots.imageHits));
    if (!shots.zipHits.length || !shots.zipHits[0]) throw new Error('ZIP fetch did not send the page session: ' + JSON.stringify(shots.zipHits));
    if (!failed.transcript.includes('hello from the fixture')) throw new Error('screenshot failure hid the transcript');
    if (failed.galleryHidden === null) throw new Error('screenshot failure showed a gallery');
    if (!failed.status.includes('Screenshots could not be captured.')) throw new Error(`status did not explain the failure: ${failed.status}`);
    if (failed.status.trim() === 'Done') throw new Error('screenshot failure was marked Done');
    if (failed.success) throw new Error('screenshot failure used the success banner');
    report.ok = true;
  } finally {
    await browser.close();
    proc.kill('SIGTERM');
  }
  const out = path.join(root, 'test-results', 'screenshot-ui-browser.json');
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ ok: report.ok, buttons: report.buttons, imageSession: Boolean(report.modes.shots && report.modes.shots.imageHits[0]), zipSession: Boolean(report.modes.shots && report.modes.shots.zipHits[0]), errorStatus: report.modes.error && report.modes.error.status }, null, 2));
  if (!report.ok) process.exit(1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
