import test from 'node:test';
import assert from 'node:assert/strict';
import { coverageSummary, agentFindings } from '../src/domain.js';
import { scanJourney, historyResultPath } from '../src/journeys.js';
import { relationshipCoverageText } from '../src/component-security.js';

test('project coverage only counts its two requested modules', () => {
  const c=coverageSummary({metadata:{scan_profile:{id:'project',requested_modules:['secret','license']},scanners:{secret:{status:'success'},license:{status:'success'},agent_security:{status:'disabled'}}}});
  assert.equal(c.complete,true);assert.equal(c.available,2);assert.equal(c.total,2);
  assert.deepEqual(Object.keys(c.modules),['secret','license']);
});
test('not-applicable is not an executed success and partial still limits coverage', () => {
  const scan={metadata:{scan_profile:{requested_modules:['secret','agent_security']},scanners:{secret:{status:'success'},agent_security:{status:'not_applicable'}}}};
  assert.equal(coverageSummary(scan).total,1);assert.equal(coverageSummary(scan).available,1);
  scan.metadata.scanners.agent_security.status='partial';
  assert.equal(coverageSummary(scan).complete,false);
});
test('saved server profile overrides misleading URL or browser preference', () => {
  globalThis.localStorage={getItem:()=> 'agent'};
  const scan={id:'saved',metadata:{scan_profile:{id:'project'}}};
  assert.equal(scanJourney('saved','download',scan),'project');
  assert.equal(historyResultPath(scan,'agent'),'/scan/saved/workspace?mode=project');
  delete globalThis.localStorage;
  assert.equal(historyResultPath({id:'saved',scan_profile:{id:'agent'}},'project'),'/scan/saved/agents?mode=agent');
});
test('ordinary tool risks do not become Agent risks', () => {
  assert.equal(agentFindings([{category:'tool_capability'}]).length,0);
  assert.match(relationshipCoverageText({status:'disabled'}),/未执行/);
  assert.match(relationshipCoverageText({status:'not_applicable'}),/没有识别到受支持/);
});
