import test from 'node:test';
import assert from 'node:assert/strict';
import { resultNavigation } from '../src/result-navigation.js';
const record = (id, modules) => ({id: 'scan', metadata: {scan_profile: {id, requested_modules: modules}}});
const keys = (scan, options) => resultNavigation(scan, options).map(row => row[0]);

test('no selected scan produces no misleading disabled result links', () => {
  assert.deepEqual(resultNavigation(null, {mode: 'agent', professional: true}), []);
});
test('project navigation follows saved scope even with Agent URL and stale component data', () => {
  assert.deepEqual(keys(record('project', ['secret', 'license']), {
    mode: 'agent', professional: true,
    componentSecurity: {scan_id: 'scan', components: [{}]},
  }), ['workspace', 'secrets', 'licenses', 'overview', 'report']);
});
test('tool capability risks keep tool navigation and never create an Agent menu', () => {
  const scan = {...record('download', ['secret', 'license', 'tool_capability']), findings: [{category: 'tool_capability'}]};
  const nav = resultNavigation(scan, {mode: 'agent', professional: true});
  assert.equal(nav.find(row => row[0] === 'components')[2], '工具能力');
  assert.equal(nav.some(row => row[0] === 'agents'), false);
});
test('requested Agent modules remain inspectable with zero findings or incomplete execution', () => {
  const scan = record('agent', ['secret', 'license', 'agent_security', 'component_security']);
  scan.metadata.scanners = {agent_security: {status: 'not_applicable'}};
  assert.deepEqual(keys(scan, {mode: 'project'}), ['workspace', 'secrets', 'licenses', 'agents', 'components', 'overview', 'report']);
});
test('historic Agent structure and assessments stay reachable without invented new profile', () => {
  const scan = {id: 'old', agents: [{}], findings: []};
  assert.ok(keys(scan).includes('agents'));
  assert.ok(keys(scan, {componentSecurity: {scan_id: 'old', components: [{}]}}).includes('components'));
  assert.equal(keys(scan, {componentSecurity: {scan_id: 'different', components: [{}]}}).includes('components'), false);
});
