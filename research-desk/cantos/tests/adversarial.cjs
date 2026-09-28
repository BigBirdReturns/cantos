'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../../..');
vm.runInThisContext(fs.readFileSync(path.join(root,'research-desk/app.html'),'utf8').match(/<script id="research-core">([\s\S]*?)<\/script>/)[1]);
const C=globalThis.ResearchCore,K=require(path.join(root,'compute/engine.cjs'));
const F=require('../foundation.js');
const finalSeed=path.join(__dirname,'../data/seed.json');
const seed=JSON.parse(fs.readFileSync(fs.existsSync(finalSeed)?finalSeed:path.join(__dirname,'../scripts/provisional-seed.json'),'utf8').replace(/^\uFEFF/,''));
(async()=>{
 const results=[];
 async function check(name,fn){try{await fn();results.push({name,status:'PASS'});}catch(e){results.push({name,status:'FAIL',error:e.message});}}
 async function desk(){const d=F.createDesk({core:C,compute:K,seed});await d.ready();return d;}
 await check('invalid numeric price rejected atomically',async()=>{
  const d=await desk(),before=await d.exportPacket();
  const r=await d.priceScenario({rate:-1,actor:'Independent adversarial test'});
  assert.equal(r.ok,false); assert.equal((await d.exportPacket()).text,before.text);
 });
 await check('invalid price shape revision rejected atomically',async()=>{
  const d=await desk(),before=await d.exportPacket();
  const price=d.view().records.find(r=>r.role==='price');
  const r=await d.revise({id:price.id,patch:{data:{offer:null}},actor:'Independent adversarial test'});
  assert.equal(r.ok,false,'Unsupported price shape accepted');
  assert.equal((await d.exportPacket()).text,before.text,'Rejected mutation changed workspace');
 });
 await check('hash-consistent unsupported price packet rejected atomically',async()=>{
  const d=await desk(),before=await d.exportPacket(),w=await C.verifyPacket(JSON.parse(before.text));
  const price=d.view().records.find(r=>r.role==='price');
  const original=C.latest(C.state(w),price.id);
  await C.put(w,{...C.clone(original),data:{...C.clone(original.data),offer:null}},'Independent adversarial test');
  const malformed=JSON.stringify(await C.pack(w));
  const r=await d.importPacket(malformed);
  assert.equal(r.ok,false,'Unsupported packet admitted');
  assert.equal((await d.exportPacket()).text,before.text,'Rejected import changed workspace');
 });
 await check('measurement edit refused',async()=>{
  const d=await desk(),before=await d.exportPacket();
  const measurement=d.view().records.find(r=>r.role==='measurement');
  const r=await d.revise({id:measurement.id,patch:{data:{metrics:{accepted:1}}},actor:'Independent adversarial test'});
  assert.equal(r.ok,false);assert.equal((await d.exportPacket()).text,before.text);
 });
 const report={status:results.every(r=>r.status==='PASS')?'PASS':'FAIL',seed:seed.provisional?'provisional, behavioral test only':'Sol final seed',checks:results};
 console.log(JSON.stringify(report,null,2));if(report.status==='FAIL')process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1;});
