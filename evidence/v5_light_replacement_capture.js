const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const base = process.argv[2].replace(/\/$/, '');
const outDir = process.argv[3];
fs.mkdirSync(outDir, { recursive: true });

async function capture(viewport, name) {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport });
  await ctx.addInitScript(() => localStorage.setItem('epicTranscriptTheme', 'light'));
  const page = await ctx.newPage();
  await page.goto(`${base}/?v5-light-proof=${Date.now()}`, { waitUntil: 'networkidle', timeout: 60000 });
  await page.evaluate(() => { localStorage.setItem('epicTranscriptTheme', 'light'); document.body.dataset.theme = 'light'; window.scrollTo(0, 0); });
  await page.waitForTimeout(500);
  const file = path.join(outDir, name);
  await page.screenshot({ path: file, fullPage: true });
  const proof = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('.machine-card h3')].map(el => el.textContent.trim());
    const faqs = [...document.querySelectorAll('.faq-q span:first-child')].map(el => el.textContent.trim());
    const title = document.querySelector('.title');
    const pseudo = getComputedStyle(title, '::before');
    const footer = document.querySelector('footer');
    const footerRect = footer.getBoundingClientRect();
    const all = document.documentElement;
    return {
      bodyTheme: document.body.dataset.theme,
      epicPseudoContent: pseudo.content,
      epicPseudoColor: pseudo.color,
      footerText: footer.textContent.trim(),
      cards,
      faqs,
      documentHeight: all.scrollHeight,
      viewportHeight: innerHeight,
      footerTop: footerRect.top + scrollY,
      footerBottom: footerRect.bottom + scrollY,
      release: document.querySelector('#releaseVersion')?.textContent || '',
    };
  });
  await browser.close();
  return { file, viewport, ...proof };
}

(async () => {
  const desktop = await capture({ width: 1440, height: 1100 }, 'v5-light-replacement-desktop.png');
  const mobile = await capture({ width: 390, height: 844 }, 'v5-light-replacement-mobile-390.png');
  const report = { base, desktop, mobile, ok: false };
  function valid(p) {
    return p.bodyTheme === 'light'
      && p.epicPseudoContent.includes('EPIC')
      && p.epicPseudoColor === 'rgba(23, 23, 25, 0.62)'
      && p.cards.length === 6
      && p.faqs.length >= 7
      && p.footerText.includes('v5.0.0')
      && p.footerBottom <= p.documentHeight + 2;
  }
  report.ok = valid(desktop) && valid(mobile);
  const reportPath = path.join(outDir, 'v5-light-replacement-proof.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  process.exit(report.ok ? 0 : 2);
})().catch(err => { console.error(err); process.exit(1); });
