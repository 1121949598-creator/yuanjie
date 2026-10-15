import test from 'node:test';
import assert from 'node:assert/strict';
import { journeys, journeyKey, rememberJourney, scanJourney, historyResultPath } from '../src/journeys.js';
test('three audiences retain the two frozen backend scene values', () => {
  assert.equal(journeys.download.scene, 'install_precheck');
  assert.equal(journeys.project.scene, 'release_precheck');
  assert.equal(journeys.agent.scene, 'release_precheck');
  assert.equal(journeys.agent.result, 'agents');
  assert.equal(journeys.download.result, 'components');
  assert.equal(journeyKey('unexpected'), 'project');
});
test('audience survives later visits to a scan and tolerates blocked storage', () => {
  const values = new Map();
  globalThis.localStorage = {setItem: (k,v) => values.set(k,v), getItem: k => values.get(k)};
  rememberJourney('agent-scan', 'agent');
  assert.equal(scanJourney('agent-scan'), 'agent');
  assert.equal(scanJourney('new-scan', 'download'), 'download');
  globalThis.localStorage = {getItem: () => {throw new Error('blocked');}};
  assert.equal(scanJourney('unknown', 'download'), 'download');
  delete globalThis.localStorage;
});
test('history opens the correct result and retains its journey', () => {
  assert.equal(historyResultPath({id: 'tool', metadata: {component_security_scene: 'install_precheck'}}, 'project'), '/scan/tool/components?mode=download');
  assert.equal(historyResultPath({id: 'release', metadata: {component_security_scene: 'release_precheck'}}, 'download'), '/scan/release/workspace?mode=project');
  assert.equal(historyResultPath({id: 'agent'}, 'agent'), '/scan/agent/agents?mode=agent');
  globalThis.localStorage = {getItem: () => 'agent'};
  assert.equal(historyResultPath({id: 'remembered', metadata: {component_security_scene: 'release_precheck'}}, 'project'), '/scan/remembered/agents?mode=agent');
  globalThis.localStorage = {getItem: () => {throw new Error('blocked');}};
  assert.equal(historyResultPath({id: 'blocked', metadata: {component_security_scene: 'install_precheck'}}, 'project'), '/scan/blocked/components?mode=download');
  delete globalThis.localStorage;
});
test('example history remembers its specific result page with safe fallback', () => {
  const values = new Map();
  globalThis.localStorage = {setItem: (k,v) => values.set(k,v), getItem: k => values.get(k)};
  rememberJourney('credentials-example', 'project', 'secrets');
  assert.equal(historyResultPath({id: 'credentials-example'}, 'agent'), '/scan/credentials-example/secrets?mode=project');
  rememberJourney('future-example', 'project', 'invalid-section');
  assert.equal(historyResultPath({id: 'future-example'}, 'agent'), '/scan/future-example/workspace?mode=project');
  delete globalThis.localStorage;
});
