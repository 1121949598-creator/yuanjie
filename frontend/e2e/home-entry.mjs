import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';

const base = process.env.OPENGUARD_TEST_URL || 'http://127.0.0.1:8201';
const output = process.env.OPENGUARD_SCREENSHOT_DIR;
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || (process.platform === 'win32' ? 'C:/Program Files/Google/Chrome/Application/chrome.exe' : undefined), headless: true });
const page = await browser.newPage({ viewport: { width: 1000, height: 704 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const water = () => page.locator('.river-flow feTurbulence').getAttribute('baseFrequency');
const ring = () => page.locator('.brand-ring').first().evaluate(el => getComputedStyle(el).transform);
const boat = () => page.locator('[data-testid="river-boat"]').getAttribute('transform');
async function screenshot(name) {
  if (!output) return;
  await page.waitForFunction(() => [...document.querySelectorAll('.entry-card, .river-copy')].every(el => Number(getComputedStyle(el).opacity) > .99));
  await fs.mkdir(output, { recursive: true });
  await page.screenshot({ path: path.join(output, name), fullPage: true, style: '.motion-feedback { visibility: hidden; }' });
}
try {
  await page.goto(`${base}/app/#/`);
  const system = await page.request.get(`${base}/api/system`).then(r => r.json());
  await page.locator('.river-flow feTurbulence').waitFor({ state: 'attached' });
  assert.equal(await page.locator('.river-header nav a').count(), 0);
  assert.equal(await page.getByRole('link', { name: '开始使用' }).count(), 1);
  assert.equal(await page.locator('a[href*="/new"], a[href*="/history"], .welcome-boundary, .motion-control').count(), 0);
  const first = [await water(), await ring(), await boat()];
  await page.waitForTimeout(700);
  assert.notEqual(await water(), first[0], 'River surface changes independently of boat');
  assert.notEqual(await ring(), first[1], 'Only blue arc rotates');
  assert.notEqual(await boat(), first[2]);
  assert.equal(await page.locator('.motion-preference').count(), 0);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.waitForTimeout(100);
  const stopped = [await water(), await ring(), await boat()];
  await page.waitForTimeout(400);
  assert.deepEqual([await water(), await ring(), await boat()], stopped);
  await page.evaluate(() => localStorage.setItem('openguard.motion', 'off'));
  await page.reload();
  await page.locator('.river-flow').waitFor({ state: 'attached' });
  assert.equal(await page.locator('html').getAttribute('data-motion'), 'on');
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  for (const width of [1000, 1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`${base}/app/#/`);
    await page.locator('.river-header').waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    await screenshot(`home-${width}.png`);
    await page.locator('.hero-actions a').click();
    await page.waitForURL(/\/entry$/);
    await page.locator('.entry-card').waitFor();
    assert.equal(await page.getByRole('radio').count(), 3);
    assert.equal(await page.locator('.entry-local').innerText(), '本地版');
    if (width > 760) {
      const card = await page.locator('.entry-card').boundingBox();
      const story = await page.locator('.entry-story').boundingBox();
      assert.ok(card.x + card.width <= story.x, 'Choice card on left, story on right');
      // Across the full route, the boat remains outside the left selection card.
      const overlap = await page.evaluate(() => {
        const card = document.querySelector('.entry-card').getBoundingClientRect();
        const svg = document.querySelector('.river-voyage svg').getBoundingClientRect();
        const path = document.querySelector('.river-voyage path');
        const length = path.getTotalLength();
        return Array.from({ length: 21 }, (_, i) => path.getPointAtLength(length * i / 20)).some(p => svg.x + (p.x - 90) * svg.width / 1536 < card.right);
      });
      assert.equal(overlap, false);
    }
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    await screenshot(`entry-${width}.png`);
  }
  await page.setViewportSize({ width: 1000, height: 704 });
  for (const mode of ['download', 'project', 'agent']) {
    await page.goto(`${base}/app/#/entry`);
    await page.locator(`input[value="${mode}"]`).check();
    await page.getByRole('link', { name: '进入检查工作台' }).click();
    await page.waitForURL(new RegExp(`/new\\?mode=${mode}`));
    await page.locator('.project-import').waitFor();
    assert.equal(await page.locator('.import-recent, .project-import .page-heading a').count(), 0);
    assert.equal(await page.locator('.import-notes, .motion-preference').count(), 0);
    const expected = { download: '下载工具怎么检查？', project: '自己的项目怎么检查？', agent: 'Agent 专项怎么检查？' };
    assert.equal(await page.locator('.download-guide h2').innerText(), expected[mode]);
    const guide = await page.locator('.download-guide').boundingBox();
    const upload = await page.locator('.upload-panel').boundingBox();
    assert.ok(guide.y + guide.height < upload.y);
    await page.getByText('检测范围与结果说明', { exact: true }).click();
    await page.getByText(system.license_provider_configured ? '当前服务已配置许可证工具，执行情况以本次扫描的模块状态为准。' : '当前服务未配置许可证工具；许可证模块会明确显示不可用，其他模块以实际覆盖情况为准。', { exact: true }).waitFor();
    await screenshot(`upload-${mode}-1000.png`);
    await page.setViewportSize({ width: 390, height: 900 });
    await page.waitForFunction(() => document.querySelector('.sidebar').getBoundingClientRect().right <= 1);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    await screenshot(`upload-${mode}-390.png`);
    await page.setViewportSize({ width: 1000, height: 704 });
    await page.getByRole('link', { name: '扫描历史', exact: true }).click();
    await page.waitForURL(new RegExp(`/history\\?mode=${mode}`));
  }
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${base}/app/#/`);
  await page.locator('.river-flow').waitFor({ state: 'attached' });
  const reduced = [await water(), await ring(), await boat()];
  await page.waitForTimeout(400);
  assert.deepEqual([await water(), await ring(), await boat()], reduced);
  assert.deepEqual(errors, []);
  console.log('PASS: homepage/entry layout, three journey guides, sidebar-only history, flowing water, rotating logo, removed floating switch, reduced motion, mobile, no page errors.');
} finally { await browser.close(); }
