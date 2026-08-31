const { test, expect } = require('@playwright/test');

test('polished public UI has icon-only theme switch and readable light boxes', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto('https://epic-transcript.robyncrane.com/', { waitUntil: 'networkidle' });
  await page.evaluate(() => localStorage.setItem('epicTranscriptTheme', 'dark'));
  await page.reload({ waitUntil: 'networkidle' });
  await expect(page.locator('body')).toContainText('Free Video Transcript');
  await expect(page.locator('body')).toContainText('Machine');
  await expect(page.locator('body')).not.toContainText('FAST · FREE · V3');
  await expect(page.locator('body')).not.toContainText('Fast. Free. V3.');
  await expect(page.locator('#grab')).toHaveText('Get Transcript');
  await expect(page.locator('.phase-strip')).toHaveCount(0);
  await expect(page.locator('.drop-zone')).toContainText('Choose file');
  await expect(page.locator('.drop-zone')).not.toContainText('MP4 · MOV · WebM');
  await page.screenshot({ path: '/tmp/epic-transcript-polish-dark.png', fullPage: false });

  await page.locator('#themeToggle').click();
  await expect(page.locator('body')).toHaveAttribute('data-theme', 'light');
  await page.screenshot({ path: '/tmp/epic-transcript-polish-light.png', fullPage: false });

  const styles = await page.evaluate(() => {
    const read = (selector) => {
      const el = document.querySelector(selector);
      const cs = getComputedStyle(el);
      return { text: el.innerText.trim(), color: cs.color, background: cs.backgroundColor };
    };
    return {
      toggleText: document.querySelector('#themeToggle').innerText.trim(),
      hero: read('.hero-control'),
      drop: read('.drop-zone'),
      button: read('#grab'),
      logoBg: getComputedStyle(document.querySelector('.logo-mark')).backgroundImage,
    };
  });
  expect(styles.toggleText).not.toContain('Light');
  expect(styles.toggleText).not.toContain('Dark');
  const rgba = styles.drop.color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/).slice(1, 4).map(Number);
  expect(rgba[0]).toBeLessThanOrEqual(35);
  expect(rgba[1]).toBeLessThanOrEqual(35);
  expect(rgba[2]).toBeLessThanOrEqual(35);
  expect(styles.logoBg).toContain('linear-gradient');
});
