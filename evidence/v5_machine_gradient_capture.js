const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const base = process.argv[2].replace(/\/$/, '');
const outDir = process.argv[3] || 'evidence';
fs.mkdirSync(outDir, { recursive: true });
async function capture(theme, viewport, name) {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport });
  await ctx.addInitScript((theme) => localStorage.setItem('epicTranscriptTheme', theme), theme);
  const page = await ctx.newPage();
  await page.goto(`${base}/?v5-machine-gradient=${Date.now()}-${theme}-${viewport.width}`, { waitUntil: 'networkidle', timeout: 60000 });
  await page.evaluate((theme) => { localStorage.setItem('epicTranscriptTheme', theme); document.body.dataset.theme = theme; window.scrollTo(0, 0); }, theme);
  await page.waitForTimeout(500);
  const file = path.join(outDir, name);
  await page.screenshot({ path: file, fullPage: false });
  const proof = await page.evaluate(() => {
    const machine = document.querySelector('.accent-machine');
    const cs = getComputedStyle(machine);
    const r = machine.getBoundingClientRect();
    return {
      theme: document.body.dataset.theme,
      h1: document.querySelector('h1')?.textContent.trim(),
      machineText: machine?.textContent.trim(),
      machineBackgroundImage: cs.backgroundImage,
      machineColor: cs.color,
      release: document.querySelector('#releaseVersion')?.textContent || '',
      machineRect: { x: r.x, y: r.y, width: r.width, height: r.height },
      viewport: { width: innerWidth, height: innerHeight }
    };
  });
  await browser.close();
  return { file, ...proof };
}
(async () => {
  const shots = {
    desktopDark: await capture('dark', { width: 1440, height: 900 }, 'v5-machine-gradient-desktop-dark.png'),
    desktopLight: await capture('light', { width: 1440, height: 900 }, 'v5-machine-gradient-desktop-light.png'),
    mobileDark: await capture('dark', { width: 390, height: 844 }, 'v5-machine-gradient-mobile-390-dark.png'),
    mobileLight: await capture('light', { width: 390, height: 844 }, 'v5-machine-gradient-mobile-390-light.png'),
  };
  function ok(s) {
    return s.h1 === 'Free Video Transcript MACHINE'
      && s.machineText === 'MACHINE'
      && s.machineBackgroundImage.includes('rgb(123, 47, 247)')
      && s.machineBackgroundImage.includes('rgb(194, 47, 252)')
      && s.machineBackgroundImage.includes('rgb(241, 7, 163)')
      && !s.machineBackgroundImage.includes('rgb(255, 255, 255)')
      && s.machineRect.y >= 0
      && s.machineRect.y < s.viewport.height;
  }
  const report = { base, shots, ok: Object.values(shots).every(ok) };
  fs.writeFileSync(path.join(outDir, 'v5-machine-gradient-capture-report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  process.exit(report.ok ? 0 : 2);
})().catch(err => { console.error(err); process.exit(1); });
