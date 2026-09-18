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
  await page.goto(`${base}/?v5-fullpage-qc=${Date.now()}-${theme}-${viewport.width}`, { waitUntil: 'networkidle', timeout: 60000 });
  await page.evaluate((theme) => { localStorage.setItem('epicTranscriptTheme', theme); document.body.dataset.theme = theme; window.scrollTo(0, 0); }, theme);
  await page.waitForTimeout(500);
  const file = path.join(outDir, name);
  await page.screenshot({ path: file, fullPage: true });
  const proof = await page.evaluate(() => {
    const title = document.querySelector('.title');
    const pseudo = getComputedStyle(title, '::before');
    const cards = [...document.querySelectorAll('.machine-card h3')].map(el => el.textContent.trim());
    const faqs = [...document.querySelectorAll('.faq-q span:first-child')].map(el => el.textContent.trim());
    const footer = document.querySelector('footer');
    const footerRect = footer.getBoundingClientRect();
    const machine = document.querySelector('.machine-band');
    const faq = document.querySelector('.faq-stage');
    return {
      theme: document.body.dataset.theme,
      epicPseudoContent: pseudo.content,
      epicPseudoColor: pseudo.color,
      titleText: title.textContent.trim(),
      cards,
      faqs,
      footerText: footer.textContent.trim(),
      release: document.querySelector('#releaseVersion')?.textContent || '',
      documentHeight: document.documentElement.scrollHeight,
      documentWidth: document.documentElement.scrollWidth,
      viewportHeight: innerHeight,
      viewportWidth: innerWidth,
      machineTop: machine.getBoundingClientRect().top + scrollY,
      faqTop: faq.getBoundingClientRect().top + scrollY,
      footerBottom: footerRect.bottom + scrollY,
    };
  });
  await browser.close();
  return { file, viewport, ...proof };
}

(async () => {
  const shots = {
    desktopDark: await capture('dark', { width: 1440, height: 1100 }, 'v5-qc-fullpage-desktop-dark.png'),
    desktopLight: await capture('light', { width: 1440, height: 1100 }, 'v5-qc-fullpage-desktop-light.png'),
    mobileDark: await capture('dark', { width: 390, height: 844 }, 'v5-qc-fullpage-mobile-390-dark.png'),
    mobileLight: await capture('light', { width: 390, height: 844 }, 'v5-qc-fullpage-mobile-390-light.png'),
  };
  function valid(p) {
    return p.epicPseudoContent.includes('EPIC') && p.cards.length === 6 && p.faqs.length >= 7 && p.footerText.includes('v5.0.0') && p.footerBottom <= p.documentHeight + 2;
  }
  const report = { base, shots, ok: Object.values(shots).every(valid) && shots.desktopLight.epicPseudoColor === 'rgba(23, 23, 25, 0.62)' && shots.mobileLight.epicPseudoColor === 'rgba(23, 23, 25, 0.62)' };
  fs.writeFileSync(path.join(outDir, 'v5-qc-fullpage-capture-report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  process.exit(report.ok ? 0 : 2);
})().catch(err => { console.error(err); process.exit(1); });
