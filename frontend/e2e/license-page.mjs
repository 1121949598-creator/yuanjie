import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';

const base = process.env.OPENGUARD_TEST_URL || 'http://127.0.0.1:8201';
const scanId = process.env.OPENGUARD_LICENSE_SCAN_ID;
assert.ok(scanId, 'Set OPENGUARD_LICENSE_SCAN_ID to a NEW real-ScanCode scan');
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || (process.platform === 'win32' ? 'C:/Program Files/Google/Chrome/Application/chrome.exe' : undefined), headless: true });
const page = await browser.newPage({ viewport: { width: 1063, height: 900 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  const system = await page.request.get(base + '/api/system').then(r => r.json());
  assert.equal(system.license_provider_configured, true);
  await page.goto(`${base}/app/#/new?mode=download`);
  await page.locator('.download-guide details').click();
  await page.getByText('当前服务已配置许可证工具，执行情况以本次扫描的模块状态为准。', { exact: true }).waitFor();
  await page.goto(`${base}/app/#/examples?mode=download`);
  await page.locator('.example-card').first().waitFor();
  assert.equal(await page.locator('.nav-caption').count(), 0);
  await page.goto(`${base}/app/#/scan/${scanId}/licenses?mode=download`);
  await page.locator('.provider-item').first().waitFor();
  const provider = page.locator('.provider-item').filter({ hasText: 'scancode' });
  assert.match(await provider.innerText(), /32\.5\.0/);
  const overview = await page.request.get(`${base}/api/scans/${scanId}/licenses`).then(r => r.json());
  assert.equal(overview.providers.find(p => p.name === 'scancode').status, 'success');
  assert.ok(overview.summary.assessments > 0);
  assert.equal(await page.getByText('许可证检测当前不可用', { exact: true }).count(), 0);
  assert.equal(await page.locator('.nav-caption').innerText(), '我的检查结果');
  await page.getByRole('button', { name: '查看许可证详情', exact: true }).first().click();
  await page.locator('.detail-drawer .drawer-body').waitFor();
  await page.waitForFunction(() => Number(getComputedStyle(document.querySelector('.workspace-page')).opacity) > .99);
  for (const width of [1063, 390]) {
    await page.setViewportSize({width,height:900});
    await page.waitForFunction(() => {
      const rect=document.querySelector('.detail-drawer').getBoundingClientRect();
      return rect.left>=-1 && rect.right<=innerWidth+1;
    });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth>innerWidth+1), false);
    if (process.env.OPENGUARD_SCREENSHOT_DIR) {
      await fs.mkdir(process.env.OPENGUARD_SCREENSHOT_DIR, { recursive: true });
      // Fixed overlays must be captured in the viewport, after their entrance animation.
      await page.screenshot({ path: path.join(process.env.OPENGUARD_SCREENSHOT_DIR, `license-real-detail-${width}.png`), fullPage: false });
    }
  }
  assert.deepEqual(errors, []);
  console.log('PASS: configured guide, examples without result caption, real license inventory and detail drawer, no page errors.');
} finally { await browser.close(); }
