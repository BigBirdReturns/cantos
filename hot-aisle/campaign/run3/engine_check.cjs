'use strict';
// Load the actual page engine, exactly as campaign/engine_table.cjs does.
// Invoked by selftest.py; can also inspect retained detailed/evaluation files.
const fs=require('node:fs'), path=require('node:path'), vm=require('node:vm');
const crypto=require('node:crypto'), assert=require('node:assert/strict');
const html=fs.readFileSync(path.join(__dirname,'../../index.html'),'utf8');
const sb={module:{exports:{}},TextEncoder,Uint8Array,Uint32Array,DataView};
vm.runInNewContext(html.match(/<script id="report-engine">([\s\S]*?)<\/script>/)[1],sb);
const H=sb.module.exports;
const [detail,quality,mode]=process.argv.slice(2);
const bytes=fs.readFileSync(detail), raw=JSON.parse(bytes);
const run=H.normalize(raw,{sha256:crypto.createHash('sha256').update(bytes).digest('hex'),record_index:0,bytes:bytes.length});
const q=JSON.parse(fs.readFileSync(quality));
const result=H.aggregate([H.attachQuality(run,q)],{ttft:1000,e2e:60000,queue:true,quality:true});
assert.equal(result.holds.length,0);
assert.equal(result.attempted,raw.errors.length);
if(mode==='--fixture'){
  assert.equal(result.attempted,6);
  assert.equal(result.completed,5);
  assert.equal(result.accepted,2); // correct + queue-inclusive TTFT/E2E intersection
  assert.equal(result.synthetic,true);
  assert.throws(()=>H.attachQuality(run,{...q,source_sha256:'0'.repeat(64)}));
  assert.throws(()=>H.attachQuality(run,{...q,passed:raw.errors.map(()=>true)}));
}
console.log(JSON.stringify({engine:H.VERSION,attempted:result.attempted,completed:result.completed,accepted:result.accepted,holds:result.holds}));
