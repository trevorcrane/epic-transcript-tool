const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const base = (process.argv[2] || 'https://epic-transcript.robyncrane.com').replace(/\/$/, '');
const outDir = process.argv[3] || 'evidence';
fs.mkdirSync(outDir, { recursive: true });

async function capture(viewport, name) {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => localStorage.setItem('epicTranscriptTheme', 'light'));
  const page = await ctx.newPage();
  await page.goto(`${base}/?v5-light-full-layout=${Date.now()}-${viewport.width}`, { waitUntil: 'networkidle', timeout: 60000 });
  await page.evaluate(() => {
    localStorage.setItem('epicTranscriptTheme', 'light');
    document.body.dataset.theme = 'light';
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(800);
  const file = path.join(outDir, name);
  await page.screenshot({ path: file, fullPage: true });
  const proof = await page.evaluate(() => {
    const title = document.querySelector('.title');
    const pseudo = getComputedStyle(title, '::before');
    const machineBand = document.querySelector('.machine-band');
    const faqStage = document.querySelector('.faq-stage');
    const footer = document.querySelector('footer');
    const rect = (el) => { const r = el.getBoundingClientRect(); return {top:r.top + scrollY, bottom:r.bottom + scrollY, height:r.height}; };
    return {
      theme: document.body.dataset.theme,
      epicPseudoContent: pseudo.content,
      epicPseudoColor: pseudo.color,
      machineHeading: machineBand?.querySelector('h2')?.textContent.trim(),
      machineCards: [...document.querySelectorAll('.machine-card h3')].map(el => el.textContent.trim()),
      faqHeading: faqStage?.querySelector('h2')?.textContent.trim(),
      faqs: [...document.querySelectorAll('.faq-q span:first-child')].map(el => el.textContent.trim()),
      footerText: footer?.textContent.trim(),
      release: document.querySelector('#releaseVersion')?.textContent || '',
      docHeight: document.documentElement.scrollHeight,
      docWidth: document.documentElement.scrollWidth,
      machineBandRect: rect(machineBand),
      faqStageRect: rect(faqStage),
      footerRect: rect(footer)
    };
  });
  await browser.close();
  return { file, viewport, ...proof };
}

(async () => {
  const desktop = await capture({ width: 1440, height: 1100 }, 'v5-light-full-layout-desktop.png');
  const mobile = await capture({ width: 390, height: 844 }, 'v5-light-full-layout-mobile-390.png');
  const ok = [desktop, mobile].every(p =>
    p.theme === 'light' &&
    p.epicPseudoContent.includes('EPIC') &&
    p.epicPseudoColor === 'rgba(23, 23, 25, 0.62)' &&
    p.machineHeading === 'Unlock All EPIC Machines' &&
    p.machineCards.length === 6 &&
    p.faqHeading && p.faqHeading.startsWith('Frequently Asked Questions') &&
    p.faqs.length >= 7 &&
    p.footerText.includes('v5.0.0') &&
    p.footerRect.bottom <= p.docHeight + 2
  );
  const report = { base, ok, desktop, mobile };
  fs.writeFileSync(path.join(outDir, 'v5-light-full-layout-capture-report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  process.exit(ok ? 0 : 2);
})().catch(err => { console.error(err); process.exit(1); });
