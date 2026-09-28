'use strict';
// Replays the controller's observed async lost-update defect against the final seed.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../../..');
vm.runInThisContext(fs.readFileSync(path.join(root,'research-desk/app.html'),'utf8').match(/<script id="research-core">([\s\S]*?)<\/script>/)[1]);
const C=globalThis.ResearchCore,K=require(path.join(root,'compute/engine.cjs')),F=require('../foundation.js');
const seed=JSON.parse(fs.readFileSync(path.join(__dirname,'../data/seed.json'),'utf8'));
(async()=>{
 const d=F.createDesk({core:C,compute:K,seed});await d.ready();
 const count=d.workspace().events.length,base=d.view().scenario.rate;
 const result=await Promise.all([d.priceScenario({rate:base+1,actor:'Controller test A'}),d.priceScenario({rate:base+2,actor:'Controller test B'})]);
 assert.equal(result.filter(x=>x.ok).length,2);
 assert.equal(d.workspace().events.length-count,2,'A successful concurrent edit was lost');
 assert.deepEqual(d.workspace().events.slice(-2).map(e=>e.actor),['Controller test A','Controller test B']);
 const packet=await d.exportPacket();await C.verifyPacket(JSON.parse(packet.text));
 const before=packet.text,price=d.view().records.find(r=>r.role==='price');
 assert.equal((await d.revise({id:price.id,patch:{data:{offer:null}},actor:'Controller invalid-shape test'})).ok,false);
 assert.equal((await d.exportPacket()).text,before);
 console.log(JSON.stringify({status:'PASS',checks:['two successful concurrent edits retain both ordered events','concurrent journal verifies through original ResearchCore','rejected shape preserves the complete exported packet'],seed:'final source-bound case; software mutation tests only'},null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
