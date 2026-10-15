// Inspect actual masked browser exports; this is not a contest technical report.
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';

const base=process.env.OPENGUARD_TEST_URL||'http://127.0.0.1:8217';
const scanId=process.env.OPENGUARD_REPORT_SCAN_ID;
const output=process.env.OPENGUARD_EXPORT_DIR;
assert.ok(scanId,'Set OPENGUARD_REPORT_SCAN_ID to an actual test scan');
assert.ok(output,'Set OPENGUARD_EXPORT_DIR for downloadable test artifacts');
const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||(process.platform==='win32'?'C:/Program Files/Google/Chrome/Application/chrome.exe':undefined),headless:true});
const context=await browser.newContext({acceptDownloads:true,viewport:{width:1280,height:900}});
const page=await context.newPage();
page.setDefaultTimeout(90000);
const errors=[];
page.on('pageerror',error=>errors.push(error.message));
try {
  await fs.mkdir(output,{recursive:true});
  const response=await page.request.get(`${base}/api/scans/${scanId}/report`);
  assert.equal(response.status(),200);
  const expected=await response.json();
  await page.goto(`${base}/app/#/scan/${scanId}/report?mode=project`);
  await page.locator('.report-paper').waitFor();
  const text=await page.locator('.report-paper').innerText();
  assert.match(text,/方法与使用边界/);
  assert.match(text,/声明与能力关系/);
  const jsonPending=page.waitForEvent('download');
  await page.getByRole('link',{name:'导出 JSON',exact:true}).click();
  const jsonDownload=await jsonPending;
  assert.equal(await jsonDownload.failure(),null);
  const jsonPath=path.join(output,'synthetic-security-report.json');
  await jsonDownload.saveAs(jsonPath);
  const serialized=await fs.readFile(jsonPath,'utf8');
  assert.deepEqual(JSON.parse(serialized),expected);
  for(const forbidden of ['sk-liveDemoOnly_1234567890abcdef','mcp_demo_8zX91Kp2Lm4Q7Rt6','source_path','fingerprint']){
    assert.ok(!serialized.includes(forbidden),`Public report must not expose ${forbidden}`);
  }
  const componentResponse=await page.request.get(`${base}/api/scans/${scanId}/component-security`);
  assert.equal(componentResponse.status(),200);
  const component=await componentResponse.json();
  const assessments=component.components.flatMap(item=>item.result.assessments);
  const modelUsed=assessments.filter(item=>item.model?.used===true).length;
  assert.ok(modelUsed>0,'Selected export test must include actual local-model participation');
  assert.match(text,/工具暴露评分方法/);
  assert.match(text,/实际参与的本地语义模型/);
  for(const assessment of assessments.filter(item=>item.model?.used===true)){
    assert.ok(text.includes(assessment.model.name),'Rendered report must identify actual participating model');
    assert.ok(text.includes(String(assessment.model.version).slice(0,8)),'Rendered report must identify actual model revision');
  }
  await fs.writeFile(path.join(output,'synthetic-component-security.json'),JSON.stringify(component,null,2)+'\n');
  const pdfPending=page.waitForEvent('download');
  await page.getByRole('button',{name:'下载 PDF',exact:true}).click();
  const pdfDownload=await pdfPending;
  assert.equal(await pdfDownload.failure(),null);
  const pdfPath=path.join(output,'synthetic-security-report.pdf');
  await pdfDownload.saveAs(pdfPath);
  const bytes=await fs.readFile(pdfPath);
  assert.equal(bytes.subarray(0,5).toString(),'%PDF-');
  assert.ok(bytes.length>10000,'PDF must contain actual rendered content');
  await page.getByRole('status').filter({hasText:'PDF 已生成'}).waitFor();
  await page.screenshot({path:path.join(output,'report-browser.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  const evidence={passed:true,scanId,synthetic:true,findings:expected.findings.length,
    componentAssessments:assessments.length,modelUsed,pdfBytes:bytes.length,
    pdfPagesRequireVisualReview:true,pageErrors:errors};
  await fs.writeFile(path.join(output,'export-check.json'),JSON.stringify(evidence,null,2)+'\n');
  console.log(JSON.stringify(evidence));
} finally { await context.close();await browser.close(); }
