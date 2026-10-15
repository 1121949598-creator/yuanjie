// Read-only browser regression over previously scanned synthetic records.
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';

const base = process.env.OPENGUARD_TEST_URL || 'http://127.0.0.1:8217';
const source = process.env.OPENGUARD_PROFILE_EVIDENCE_FILE;
const output = process.env.OPENGUARD_SIDEBAR_EVIDENCE_DIR;
assert.ok(source && output, 'Provide saved profile evidence and output directory');
const cases = JSON.parse(await fs.readFile(source, 'utf8')).cases;
const browser = await chromium.launch({executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true});
const context = await browser.newContext({viewport: {width: 1063, height: 704}, reducedMotion: 'reduce'});
const page = await context.newPage();
const errors = [], tested = [];
page.on('pageerror', error => errors.push(error.message));
const common = ['结果概览', '敏感凭据', '许可证与依赖'];
const expected = {
  project: [...common, '风险清单', '检测报告'],
  download: [...common, '工具能力', '风险清单', '检测报告'],
  agent: [...common, '任务与权限', '声明与能力', '风险清单', '检测报告'],
};
try {
  await fs.mkdir(output, {recursive: true});
  for (const mode of ['download', 'project', 'agent']) {
    await page.goto(`${base}/app/#/entry`);
    await page.locator(`input[value="${mode}"]`).check();
    await page.getByRole('link', {name: '进入检查工作台', exact: true}).click();
    await page.locator('.download-guide').waitFor();
    assert.deepEqual(await page.locator('.sidebar-group-label').allTextContents(), ['开始检查', '本次结果', '示例与记录']);
    assert.equal(await page.locator('.sidebar nav a, .nav-disabled, .nav-count').count(), 0);
    assert.match(await page.locator('.sidebar-result-empty').innerText(), /上传源码或运行示例/);
  }
  await page.screenshot({path: path.join(output, 'sidebar-new-1063.png')});
  for (const item of cases) {
    const {profile, scanId} = item;
    // Deliberately conflicting query must not reveal unrequested modules.
    await page.goto(`${base}/app/#/scan/${scanId}/workspace?mode=agent&professional=1`);
    await page.locator('.scan-context').waitFor();
    assert.deepEqual(await page.locator('.sidebar nav a > span:first-of-type').allTextContents(), expected[profile]);
    assert.equal(await page.locator('.breadcrumbs b').innerText(), '结果概览');
    const report = await page.request.get(`${base}/api/scans/${scanId}/report`).then(response => response.json());
    assert.equal(await page.locator('.sidebar-current-project').innerText(), report.project_name);
    assert.equal(await page.locator('.sidebar nav [aria-current="page"]').count(), 1);
    for (const label of expected[profile]) {
      await page.getByRole('link', {name: '已有示例', exact: true}).click();
      await page.locator('.example-card').first().waitFor();
      const link = page.locator('.sidebar nav a').filter({has: page.getByText(label, {exact: true})});
      assert.match(await link.getAttribute('href'), new RegExp(`/scan/${scanId}/`));
      await link.click();
      await page.locator('.scan-context').waitFor();
      assert.equal(await page.locator('.breadcrumbs b').innerText(), label);
    }
    await page.goto(`${base}/app/#/scan/${scanId}/workspace`);
    await page.locator('.scan-context').waitFor();
    await page.screenshot({path: path.join(output, `sidebar-${profile}-1063.png`)});
    await page.setViewportSize({width: 390, height: 844});
    await page.getByRole('button', {name: '切换导航', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('.sidebar').getBoundingClientRect().x >= -1);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    const reportLink = page.locator('.sidebar nav a').filter({has: page.getByText('检测报告', {exact: true})});
    await reportLink.scrollIntoViewIfNeeded();
    await page.screenshot({path: path.join(output, `sidebar-${profile}-390.png`)});
    await reportLink.click();
    await page.waitForURL(new RegExp(`/scan/${scanId}/report`));
    await page.waitForFunction(() => document.querySelector('.sidebar').getBoundingClientRect().right <= 1);
    await page.setViewportSize({width: 1063, height: 704});
    tested.push({profile, scanId, labels: expected[profile], savedScope: true, allLinksReachable: true, mobile: true});
  }
  // An unavailable record has an actionable message, not dead links or old badges.
  await page.route('**/api/scans/sidebar-missing/report', route => route.fulfill({status: 404, json: {detail: 'QA missing record'}}));
  await page.route('**/api/scans/sidebar-missing/component-security', route => route.fulfill({status: 404, json: {detail: 'QA missing record'}}));
  await page.goto(`${base}/app/#/scan/sidebar-missing/workspace`);
  await page.getByRole('heading', {name: '暂时无法读取这次扫描', exact: true}).waitFor();
  assert.match(await page.locator('.sidebar-result-empty').innerText(), /读取失败/);
  assert.equal(await page.locator('.sidebar nav a, .nav-count').count(), 0);
  assert.deepEqual(errors, []);
  const evidence = {passed: true, readOnly: true, groups: ['开始检查', '本次结果', '示例与记录'], tested, emptyAndErrorStates: true, pageErrors: errors};
  await fs.writeFile(path.join(output, 'sidebar-classification.json'), JSON.stringify(evidence, null, 2) + '\n');
  console.log(JSON.stringify(evidence));
} finally {await context.close(); await browser.close();}
