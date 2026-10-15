import test from 'node:test';
import assert from 'node:assert/strict';
import { sidebarRiskCounts } from '../src/sidebar-risk.js';
test('sidebar counts actual findings by category rather than summary/inventory totals', () => {
  const scan = {id: 'current', summary: {secrets: 999}, findings: [
    {category: 'secret'}, {category: 'secret'}, {category: 'license'},
    {category: 'agent_security'}, {category: 'tool_exposure'}, {category: 'unresolved'},
  ], metadata: {module_data: {license: {summary: {packages: 500, dependencies: 900}}}}};
  assert.deepEqual(sidebarRiskCounts(scan), {workspace:6, overview:6, report:6, secrets:2, licenses:1, agents:3, components:0});
});
test('ordinary secret findings do not create Agent or license alerts', () => {
  const counts = sidebarRiskCounts({findings:[{category:'secret'}]});
  assert.equal(counts.agents,0);
  assert.equal(counts.licenses,0);
  assert.equal(counts.secrets,1);
});
test('pending relations and stale scans do not produce inconsistency alerts', () => {
  const data={scan_id:'current',components:[{result:{assessments:[{relation:'needs_review'},{relation:'insufficient_evidence'},{relation:'inconsistent'}]}}]};
  assert.equal(sidebarRiskCounts({id:'current'},data).components,1);
  assert.equal(sidebarRiskCounts({id:'other'},data).components,0);
  assert.equal(sidebarRiskCounts(null,data).components,0);
  assert.equal(sidebarRiskCounts({id:'current'}, {...data,components:[]}).components,0);
});
