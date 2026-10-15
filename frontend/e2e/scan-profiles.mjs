// Real local HTTP + browser uploads of one synthetic archive into all profiles.
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';

const base=process.env.OPENGUARD_TEST_URL||'http://127.0.0.1:8217';
const output=process.env.OPENGUARD_PROFILE_EVIDENCE_DIR;
assert.ok(output,'Set OPENGUARD_PROFILE_EVIDENCE_DIR');
const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const context=await browser.newContext({viewport:{width:1063,height:704},reducedMotion:'reduce'});
const page=await context.newPage();
page.setDefaultTimeout(120000);
const errors=[],cases=[];
page.on('pageerror',e=>errors.push(e.message));
try {
  await fs.mkdir(output,{recursive:true});
  const response=await page.request.get(base+'/api/examples/research/archive');
  assert.equal(response.status(),200);
  const archive=await response.body();
  for(const [profile,section,title] of [
    ['project','workspace','检查自己的项目'],['download','components','检查下载的工具'],['agent','agents','Agent 专项审查'],
  ]) {
    await page.goto(`${base}/app/#/new?mode=${profile}`);
    await page.locator('.project-import').waitFor();
    await page.locator('input[type=file]').setInputFiles({name:`profile-${profile}.zip`,mimeType:'application/zip',buffer:archive});
    const pending=page.waitForResponse(r=>r.url()===base+'/api/scans'&&r.request().method()==='POST');
    await page.locator('.upload-bottom .button.primary').click();
    const created=await pending;
    assert.equal(created.status(),201);
    const id=(await created.json()).scan_id;
    await page.waitForURL(new RegExp(`/scan/${id}/${section}`));
    await page.locator('.scan-plan-note').waitFor();
    const scan=await page.request.get(`${base}/api/scans/${id}`).then(r=>r.json());
    const plan=scan.metadata.scan_profile;
    assert.equal(plan.id,profile);assert.equal(plan.version,'1.0');
    const component=await page.request.get(`${base}/api/scans/${id}/component-security`).then(r=>r.json());
    const modelUsed=component.components.flatMap(c=>c.result.assessments).filter(a=>a.model.used).length;
    const agentFindings=scan.findings.filter(f=>['agent_security','tool_exposure','unresolved'].includes(f.category));
    if(profile==='project') {
      assert.deepEqual(plan.executed_modules,['secret','license']);
      assert.equal(component.status,'disabled');assert.equal(modelUsed,0);
      assert.equal(agentFindings.length,0);assert.equal(scan.agents.length,0);
      assert.equal(plan.agent_review_recommended,true);
      assert.doesNotMatch(await page.locator('.coverage-modules').innerText(),/Agent 安全|声明与能力/);
      await page.getByRole('link',{name:'提交到 Agent 专项审查 →',exact:true}).waitFor();
    } else if(profile==='download') {
      assert.equal(agentFindings.length,0);assert.equal(scan.agents.length,0);
      assert.ok(plan.executed_modules.includes('tool_capability'));
      assert.ok(component.components.some(c=>c.capabilities.length));
      assert.ok(component.components.every(c=>c.component.component_type!=='agent'));
      assert.match(await page.locator('.coverage-modules').innerText(),/工具能力/);
      assert.doesNotMatch(await page.locator('.coverage-modules').innerText(),/Agent 安全/);
    } else {
      assert.ok(scan.agents.length&&scan.tools.length&&agentFindings.length);
      assert.ok(plan.executed_modules.includes('agent_security'));
      assert.ok(plan.executed_modules.includes('component_security'));
      assert.ok(modelUsed>0,'Actual local model must participate in this Agent fixture');
      assert.match(await page.locator('.coverage-modules').innerText(),/Agent 安全|声明与能力/);
    }
    // A fresh browser with no localStorage and a misleading query still uses the saved plan.
    const fresh=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'});
    const mobile=await fresh.newPage();
    mobile.on('pageerror',e=>errors.push(e.message));
    await mobile.goto(`${base}/app/#/scan/${id}/${section}?mode=${profile==='agent'?'project':'agent'}`);
    await mobile.locator('.scan-plan-note').waitFor();
    assert.ok((await mobile.locator('.result-journey small').innerText()).includes(title));
    assert.ok(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await mobile.screenshot({path:path.join(output,`profile-${profile}-390.png`),fullPage:true});
    await fresh.close();
    await page.screenshot({path:path.join(output,`profile-${profile}-1063.png`),fullPage:true});
    cases.push({profile,scanId:id,requested:plan.requested_modules,executed:plan.executed_modules,
      agentFindings:agentFindings.length,modelUsed,componentStatus:component.status,synthetic:true});
  }
  const project=cases.find(c=>c.profile==='project');
  await page.goto(`${base}/app/#/scan/${project.scanId}/agents?mode=agent&professional=1`);
  await page.getByRole('heading',{name:'本次未执行 Agent 专项',exact:true}).waitFor();
  assert.equal(await page.locator('.view-tabs').count(),0);
  const history=await page.request.get(base+'/api/scans').then(r=>r.json());
  for(const c of cases)assert.equal(history.items.find(item=>item.id===c.scanId).scan_profile.id,c.profile);
  assert.deepEqual(errors,[]);
  const evidence={passed:true,synthetic:true,sameArchive:true,cases,freshBrowserSavedPlan:true,
    noAgentMislabel:true,mobileNoOverflow:true,pageErrors:errors};
  await fs.writeFile(path.join(output,'profile-browser.json'),JSON.stringify(evidence,null,2)+'\n');
  console.log(JSON.stringify(evidence));
} finally {await context.close();await browser.close();}
