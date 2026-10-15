import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';

const base = process.env.OPENGUARD_TEST_URL || 'http://127.0.0.1:8201';
const id = process.env.OPENGUARD_COMPONENT_SCAN_ID || 'dfa830d4e82a4700';
const output = process.env.OPENGUARD_SCREENSHOT_DIR;
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || (process.platform === 'win32' ? 'C:/Program Files/Google/Chrome/Application/chrome.exe' : undefined), headless: true });
const page = await browser.newPage({ viewport: { width: 1063, height: 704 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  const report = await page.request.get(`${base}/api/scans/${id}/report`).then(r => r.json());
  for (const mode of ['download', 'project', 'agent']) {
    await page.goto(`${base}/app/#/scan/${id}/components?mode=${mode}`);
    await page.locator('.component-coverage').waitFor();
    assert.equal(await page.locator('main h1').count(), 1);
    assert.equal(await page.locator('.result-journey h1').innerText(), mode === 'download' ? '工具能做什么？' : '声明与能力是否一致？');
    assert.equal(await page.locator('.component-security .page-heading').count(), 0);
    assert.equal(await page.locator('.component-disclaimer').count(), 0);
    assert.match(await page.locator('.context-project').innerText(), /扫描编号：/);
    assert.equal(await page.locator('.context-project code').getAttribute('title'), id);
    assert.equal(await page.locator('.context-project b').innerText(), report.project_name);
    const ring = page.locator('.sidebar .brand-ring');
    assert.equal(await ring.evaluate(el => getComputedStyle(el).animationDuration), '12s');
    const before = await ring.evaluate(el => getComputedStyle(el).transform);
    await page.waitForTimeout(400);
    assert.notEqual(await ring.evaluate(el => getComputedStyle(el).transform), before);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    assert.equal(await ring.evaluate(el => getComputedStyle(el).animationName), 'none');
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    for (const width of [1063, 390]) {
      await page.setViewportSize({ width, height: 704 });
      if (width === 390) await page.waitForFunction(() => document.querySelector('.sidebar').getBoundingClientRect().right <= 1);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
      if (output) {
        await page.waitForFunction(() => Number(getComputedStyle(document.querySelector('.workspace-page')).opacity) > .99);
        await fs.mkdir(output, { recursive: true });
        await page.screenshot({ path: path.join(output, `components-${mode}-${width}.png`), fullPage: true });
      }
    }
    await page.setViewportSize({ width: 1063, height: 704 });
  }
  assert.deepEqual(errors, []);
  console.log('PASS: combined heading across journeys, labeled scan ID, rotating sidebar arc, reduced motion, desktop/mobile, no page errors.');
} finally { await browser.close(); }
