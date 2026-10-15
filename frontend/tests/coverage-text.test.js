import test from 'node:test';
import assert from 'node:assert/strict';
import { relationshipCoverageText } from '../src/component-security.js';
test('empty capability list is distinguished from model non-participation', () => {
  const message = relationshipCoverageText({status:'partial',components:[{capabilities:[],result:{assessments:[]}}]});
  assert.match(message,/未提取到/);
  assert.match(message,/没有生成关系判断/);
  assert.doesNotMatch(message,/0 \/ 0/);
});
test('available capabilities without assessments show algorithm coverage gap', () => {
  assert.match(relationshipCoverageText({components:[{capabilities:[{}],result:{assessments:[]}}]}),/1 项能力，但尚未生成关系判断/);
});
test('existing rule-only assessment is not called a zero-assessment result', () => {
  assert.match(relationshipCoverageText({components:[{result:{assessments:[{model:{used:false}}]}}]}),/已生成 1 项关系判断，其中 0 项使用语义模型/);
});
