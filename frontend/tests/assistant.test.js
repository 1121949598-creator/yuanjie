import test from 'node:test';
import assert from 'node:assert/strict';
import { taskHint } from '../src/assistant.js';
test('task hints follow actual phases without invented progress', () => {
  assert.equal(taskHint({ phase:'uploading',path:'/new' }).mood,'thinking');
  assert.equal(taskHint({ phase:'analyzing',path:'/new' }).mood,'analyzing');
  assert.equal(taskHint({ error:'bad file',path:'/new' }).mood,'warning');
});
test('incomplete coverage never celebrates zero findings', () => {
  const input={ path:'/scan/1/report',scan:{findings:[]},complete:false };
  assert.equal(taskHint(input).mood,'warning');
  assert.equal(taskHint({...input,complete:true}).mood,'success');
  assert.equal(taskHint({...input,complete:true,scan:{findings:[{}]}}).mood,'warning');
});
