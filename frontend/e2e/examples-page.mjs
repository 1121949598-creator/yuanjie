import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';

const base=process.env.OPENGUARD_TEST_URL||'http://127.0.0.1:8201';
const output=process.env.OPENGUARD_SCREENSHOT_DIR;
const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||(process.platform==='win32'?'C:/Program Files/Google/Chrome/Application/chrome.exe':undefined),headless:true});
const page=await browser.newPage({viewport:{width:1063,height:704}});
page.setDefaultTimeout(360000); // Real license scans may take up to the provider timeout.
const errors=[], tested=[];
page.on('pageerror',e=>errors.push(e.message));
try {
  for(const [incoming,title,mode,scene,section] of [
    ['agent','开源发布前的基础检查','project','release_precheck','workspace'],
    ['agent','代码里的敏感凭据','project','release_precheck','secrets'],
    ['download','研究助手的过度授权','agent','release_precheck','agents'],
    ['project','无法确定的动态绑定','agent','release_precheck','agents'],
    ['agent','MCP 工具的能力边界','download','install_precheck','components'],
  ]) {
    await page.goto(`${base}/app/#/new?mode=${incoming}`);
    await page.locator('.project-import').waitFor();
    assert.equal(await page.locator('.examples-section').count(),0);
    await page.getByRole('link',{name:'已有示例',exact:true}).click();
    await page.waitForURL(new RegExp(`/examples\\?mode=${incoming}`));
    await page.locator('.example-card').first().waitFor();
    assert.equal(await page.locator('.nav-caption').count(),0);
    assert.equal(await page.locator('.breadcrumbs b').innerText(),'已有示例');
    assert.equal(await page.getByLabel('示例检查方式').count(),0);
    await page.getByLabel('搜索合成示例').fill('不存在的例子-qa');
    assert.equal(await page.locator('.example-card').count(),0);
    await page.getByText('没找到这个例子。试试“凭据”“研究”或“MCP”。').waitFor();
    await page.getByLabel('搜索合成示例').fill('');
    const download=await page.locator('.example-card a').first().getAttribute('href');
    const archive=await page.request.get(base+download);
    assert.equal(archive.status(),200);
    assert.equal((await archive.body()).subarray(0,2).toString(),'PK');
    const pending=page.waitForResponse(r=>r.url()===base+'/api/scans'&&r.request().method()==='POST');
    await page.locator('.example-card').filter({has:page.getByRole('heading',{name:title,exact:true})}).getByRole('button',{name:'运行示例'}).click();
    const response=await pending;
    assert.equal(response.status(),201);
    const result=await response.json();
    await page.waitForURL(new RegExp(`/scan/${result.scan_id}/${section}\\?mode=${mode}`));
    await page.locator('.scan-context').waitFor();
    const scan=await page.request.get(`${base}/api/scans/${result.scan_id}`).then(r=>r.json());
    assert.equal(scan.metadata.component_security_scene,scene);
    assert.equal(scan.metadata.scan_profile.id,mode);
    tested.push({incoming,title,mode,scene,result:section,scanId:result.scan_id,realScan:true});
  }
  await page.goto(`${base}/app/#/new?examples=1&mode=download`);
  await page.waitForURL(/\/examples\?mode=download/);
  await page.locator('.example-card').first().waitFor();
  await page.goto(`${base}/app/#/examples?mode=agent`);
  await page.waitForURL(/\/examples\?mode=agent/);
  await page.locator('.example-card').first().waitFor();
  assert.equal(await page.locator('.sidebar-journeys .selected').innerText(),'Agent 专项审查');
  assert.equal(await page.getByRole('link',{name:'上传自己的源码'}).count(),0);
  assert.equal(await page.locator('.sidebar-note').count(),0);
  await page.locator('.sidebar-journeys').getByRole('link',{name:'Agent 专项审查',exact:true}).click();
  await page.waitForURL(/\/new\?mode=agent/);
  for(const width of [1063,390]){
    await page.setViewportSize({width,height:900});
    await page.goto(`${base}/app/#/examples?mode=download`);
    await page.locator('.example-card').first().waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
    await page.waitForFunction(()=>Number(getComputedStyle(document.querySelector('.workspace-page')).opacity)>.99);
    if(width===390)await page.waitForFunction(()=>document.querySelector('.sidebar').getBoundingClientRect().right<=1);
    await page.mouse.move(width-10,5);
    if(output){await fs.mkdir(output,{recursive:true});await page.screenshot({path:path.join(output,`examples-${width}.png`),fullPage:true});}
  }
  await page.setViewportSize({width:1063,height:704});
  await page.goto(`${base}/app/#/examples?mode=download`);
  await page.locator('.example-card').first().waitFor();
  assert.equal(await page.locator('.motion-preference').count(),0);
  assert.equal(await page.locator('.current-streams').evaluate(el=>getComputedStyle(el).animationName),'river-current');
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await page.locator('.current-streams').evaluate(el=>getComputedStyle(el).animationName),'none');
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.route('**/api/examples',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'QA temporary error'})}));
  await page.reload();
  await page.getByRole('alert').waitFor();
  await page.unroute('**/api/examples');
  await page.getByRole('button',{name:'重新读取示例'}).click();
  await page.locator('.example-card').first().waitFor();
  assert.deepEqual(errors,[]);
  const evidence={passed:true,tested,searchDownloadRetry:true,legacyLink:true,featureRouting:true,responsive:true,noFloatingMotionControl:true,systemReducedMotion:true,pageErrors:errors};
  if(process.env.OPENGUARD_EVIDENCE_FILE){const target=process.env.OPENGUARD_EVIDENCE_FILE;await fs.mkdir(path.dirname(target),{recursive:true});await fs.writeFile(target,JSON.stringify(evidence,null,2)+'\n');}
  console.log(JSON.stringify(evidence));
} finally {await browser.close();}
