import { chromium } from 'playwright';
import assert from 'node:assert/strict';
const base = process.env.OPENGUARD_TEST_URL || 'http://127.0.0.1:8201';
const first = process.env.OPENGUARD_NAV_SCAN_ID || 'd3bb0d6033574626';
const second = process.env.OPENGUARD_NAV_AGENT_ID || 'f40666aef2c64960';
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
const page = await browser.newPage();
const errors=[];
page.on('pageerror', e => errors.push(e.message));
try {
  await page.goto(`${base}/app/#/examples?mode=project`);
  await page.locator('.example-card').first().waitFor();
  assert.equal(await page.locator('.sidebar nav a').count(), 0, 'No scan selected in fresh session');
  await page.goto(`${base}/app/#/scan/${first}/workspace?mode=project`);
  await page.locator('.scan-context').waitFor();
  for (const [name, section] of [['结果概览','workspace'],['敏感凭据','secrets'],['许可证与依赖','licenses'],['风险清单','overview'],['检测报告','report']]) {
    await page.getByRole('link', { name:'已有示例', exact:true }).click();
    await page.locator('.example-card').first().waitFor();
    assert.equal(await page.locator('.sidebar nav a.active').count(), 0);
    const link = page.locator('.sidebar nav').getByRole('link', { name:new RegExp(`^${name}`) });
    assert.match(await link.getAttribute('href'), new RegExp(`/scan/${first}/${section}`));
    await link.click();
    await page.waitForURL(new RegExp(`/scan/${first}/${section}\\?mode=project`));
    await page.locator('.scan-context').waitFor();
  }
  await page.getByRole('link',{name:'扫描历史',exact:true}).click();
  assert.match(await page.locator('.sidebar nav a').first().getAttribute('href'), new RegExp(first));
  await page.locator('.sidebar-journeys').getByRole('link',{name:'检查下载的工具',exact:true}).click();
  await page.locator('.download-guide').waitFor();
  assert.equal(await page.locator('.sidebar-journeys .selected').innerText(),'检查下载的工具');
  assert.match(await page.locator('.sidebar nav a').first().getAttribute('href'), new RegExp(first));
  await page.goto(`${base}/app/#/scan/${second}/agents?mode=agent`);
  await page.locator('.scan-context').waitFor();
  await page.getByRole('link',{name:'已有示例',exact:true}).click();
  // Actual risks add a count to the link's accessible name.
  const agentLink=page.locator('.sidebar nav').getByRole('link',{name:/^任务与权限(?:\s*\d+ 项风险发现)?$/});
  assert.match(await agentLink.getAttribute('href'),new RegExp(`/scan/${second}/agents`));
  await agentLink.click();
  await page.waitForURL(new RegExp(`/scan/${second}/agents\\?mode=agent`));
  await page.locator('.scan-context').waitFor();
  // Returning home starts a fresh session, without deleting the saved scan.
  await page.locator('.sidebar a.brand').click();
  await page.waitForURL(/#\/$/);
  await page.getByRole('link', {name:/开始使用/}).click();
  await page.waitForURL(/#\/entry$/);
  await page.getByRole('link', {name:'进入检查工作台',exact:true}).click();
  await page.locator('.download-guide').waitFor();
  assert.equal(await page.locator('.sidebar nav a').count(), 0, 'New homepage session has no old result links');
  assert.equal(await page.locator('.nav-count').count(), 0, 'No stale risk badges');
  assert.equal(await page.evaluate(() => localStorage.getItem('yuanjian.lastScan')), null);
  const saved = await page.request.get(`${base}/api/scans/${second}/report`);
  assert.equal(saved.status(), 200, 'Session reset does not delete stored reports');
  await page.getByRole('link',{name:'扫描历史',exact:true}).click();
  await page.locator('.sidebar-result-empty').waitFor();
  assert.equal(await page.locator('.sidebar nav a').count(), 0);
  await page.goto(`${base}/app/#/scan/${first}/workspace?mode=project`);
  await page.locator('.scan-context').waitFor();
  assert.ok(await page.locator('.sidebar nav a').count() > 0, 'Reopening saved scan restores context');
  // A late report response must not revive a session cleared while it was loading.
  await page.route(`**/api/scans/${second}/report`, async route => {
    const response = await route.fetch();
    await new Promise(resolve => setTimeout(resolve, 1200));
    await route.fulfill({response});
  });
  await page.evaluate(id => { location.hash = `/scan/${id}/agents?mode=agent`; }, second);
  await page.waitForURL(new RegExp(`/scan/${second}/agents`));
  await page.locator('.sidebar a.brand').click();
  await page.waitForURL(/#\/$/);
  await page.getByRole('link', {name:/开始使用/}).click();
  await page.getByRole('link', {name:'进入检查工作台',exact:true}).click();
  await page.locator('.download-guide').waitFor();
  await page.waitForTimeout(1500);
  assert.equal(await page.locator('.sidebar nav a').count(), 0, 'Late response cannot restore stale result links');
  assert.equal(await page.locator('.nav-count').count(), 0);
  assert.deepEqual(errors,[]);
  console.log('PASS: session navigation retained, home resets selection/badges, stored reports remain, late requests invalidated, no page errors.');
} finally { await browser.close(); }
