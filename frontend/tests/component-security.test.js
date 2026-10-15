import test from 'node:test';
import assert from 'node:assert/strict';
import { relationCounts, assessmentRows, evidenceFor, relativeLocation } from '../src/component-security.js';
import { uploadScan } from '../src/api.js';
test('four relations preserve review and evidence gaps independently of risks', () => {
 const data={components:[{capabilities:[{capability_id:'shell',capability:'shell_execute'}],result:{assessments:[
 {relation:'needs_review',capability_id:'shell'},{relation:'inconsistent'}, {relation:'insufficient_evidence'},{relation:'justified'},
 ]}}]};
 assert.deepEqual(relationCounts(data),{justified:1,needs_review:1,inconsistent:1,insufficient_evidence:1});
 assert.equal(assessmentRows(data)[0].capability.capability,'shell_execute');
 assert.deepEqual(assessmentRows({status:'unavailable'}),[]);
});
test('missing evidence is retained as a gap and absolute paths are not displayed', () => {
 const row={assessment:{evidence_refs:['a','missing'],reasons:[{evidence_refs:['a']}]},entry:{evidence:[{evidence_id:'a',masked_excerpt:'***'}]}};
 assert.equal(evidenceFor(row).length,2);
 assert.equal(evidenceFor(row)[1].item,undefined);
 for(const path of ['C:/private/file.py','/home/private.py','../secret.py','folder/../secret.py']) assert.equal(relativeLocation({path}),'位置不可展示');
 assert.equal(relativeLocation({path:'scripts/check.py',start_line:14}),'scripts/check.py:14');
});
test('upload includes frozen scene in multipart data and preserves real progress', async () => {
 const original=globalThis.XMLHttpRequest;
 let fields;
 globalThis.XMLHttpRequest=class{
  upload={};
  open(method,url){assert.equal(method,'POST');assert.equal(url,'/api/scans');}
  send(form){ fields=form; this.upload.onprogress({lengthComputable:true,loaded:3,total:4}); this.upload.onload();this.status=201;this.responseText='{"scan_id":"abc"}';this.onload();}
 };
 try{
  let progress=0,analyzing=false;
  const result=await uploadScan(new Blob(['archive']),p=>progress=p,()=>analyzing=true,'install_precheck','download');
  assert.equal(fields.get('profile'),'download');
  assert.equal(result.scan_id,'abc');assert.equal(fields.get('scene'),'install_precheck');assert.equal(progress,75);assert.ok(analyzing);
 }finally{globalThis.XMLHttpRequest=original;}
});
