import test from 'node:test';
import assert from 'node:assert/strict';
import { exampleFlow } from '../src/example-flow.js';
import { journeys } from '../src/journeys.js';
test('examples use their own feature and scene regardless of incoming mode', () => {
  for (const [id, mode, section, scene] of [
    ['release', 'project', 'workspace', 'release_precheck'],
    ['secrets', 'project', 'secrets', 'release_precheck'],
    ['research', 'agent', 'agents', 'release_precheck'],
    ['dynamic', 'agent', 'agents', 'release_precheck'],
    ['mcp', 'download', 'components', 'install_precheck'],
  ]) {
    assert.equal(exampleFlow(id).mode, mode);
    assert.equal(exampleFlow(id).section, section);
    assert.equal(journeys[mode].scene, scene);
  }
});
test('unknown examples fall back to the general workbench', () => {
  assert.equal(exampleFlow('future').section, 'workspace');
  assert.equal(exampleFlow('future').mode, 'project');
});
