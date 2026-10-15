import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {sidebarRiskCounts} from '../src/sidebar-risk.js';
const base=process.env.OPENGUARD_TEST_URL||'http://127.0.0.1:8201';
const output=process.env.OPENGUARD_SCREENSHOT_DIR;
const scanIds=(process.env.OPENGUARD_RISK_SCAN_IDS||'278225415aef496e,d3bb0d6033574626').split(',').map(id=>id.trim()).filter(Boolean);
assert.ok(scanIds.length>0,'Provide actual scan IDs for this test server');
const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const page=await browser.newPage({viewport:{width:1063,height:704}});
const errors=[];
page.on('pageerror',e=>errors.push(e.message));
try {
  let savedReport;
  for(const id of scanIds) {
    const mode='project';
    const report=await page.request.get(`${base}/api/scans/${id}/report`).then(r=>r.json());
    savedReport=report;
    const component=await page.request.get(`${base}/api/scans/${id}/component-security`).then(r=>r.json());
    const expected=sidebarRiskCounts(report,component);
    await page.goto(`${base}/app/#/scan/${id}/workspace?mode=${mode}`);
    await page.locator('.scan-context').waitFor();
    for(const [section,count] of Object.entries(expected)) {
      const badge=page.locator(`[data-risk-section="${section}"]`);
      assert.equal(await badge.count(),count>0?1:0,`${section}: zero counts stay hidden`);
      if(count>0) {
        assert.equal(await badge.innerText(),String(count));
        assert.deepEqual(await badge.evaluate(el=>{const s=getComputedStyle(el);return [s.backgroundColor,s.color,s.borderRadius,s.width===s.height];}),['rgb(23, 106, 192)','rgb(255, 255, 255)','50%',true]);
      }
    }
    if(output) {
      await page.waitForFunction(()=>Number(getComputedStyle(document.querySelector('.workspace-page')).opacity)>.99);
      await fs.mkdir(output,{recursive:true});
      await page.screenshot({path:path.join(output,`risk-${id}.png`),fullPage:true});
    }
    await page.getByRole('link',{name:'已有示例',exact:true}).click();
    assert.equal(await page.locator('[data-risk-section="report"]').count(),expected.report>0?1:0);
    if(expected.report>0)assert.equal(await page.locator('[data-risk-section="report"]').innerText(),String(expected.report));
  }
  // UI-only fixture: verify three-digit layout and no invented Agent/license badges.
  const fixture={...savedReport,id:'badge-fixture',findings:Array.from({length:125},(_,i)=>({...savedReport.findings[0],id:`f${i}`,category:'secret'}))};
  await page.route('**/api/scans/badge-fixture/report',r=>r.fulfill({json:fixture}));
  await page.route('**/api/scans/badge-fixture/component-security',r=>r.fulfill({json:{scan_id:'badge-fixture',status:'success',components:[],warnings:[]}}));
  await page.goto(`${base}/app/#/scan/badge-fixture/workspace?mode=project`);
  await page.locator('.scan-context').waitFor();
  assert.equal(await page.locator('[data-risk-section="secrets"]').innerText(),'125');
  assert.equal(await page.locator('[data-risk-section="licenses"], [data-risk-section="agents"]').count(),0);
  await page.setViewportSize({width:390,height:704});
  await page.getByRole('button',{name:'切换导航'}).click();
  await page.waitForFunction(()=>document.querySelector('.sidebar').getBoundingClientRect().x>=-1);
  const badge=await page.locator('[data-risk-section="secrets"]').boundingBox();
  assert.equal(badge.width,badge.height);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  assert.deepEqual(errors,[]);
  console.log('PASS: real per-module risk counts, round blue badges, hidden zeros, retained scan context, three-digit/mobile layout, no page errors.');
} finally {await browser.close();}
