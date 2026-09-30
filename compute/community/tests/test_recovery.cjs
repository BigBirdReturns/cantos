'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const U=require('../cli.cjs'),C=require('../core.cjs');
function packet(){const metadata={title:'Recovery fixture',provider:'Software fixture',hardware:'No physical execution',workload:'Fixture task',variant:'Authored fixture',observed_at:'2026-09-27',contributor:'Regression author',funding:'No compute expenditure',relationship:'Software test',limitations:['Authored regression fixture; never public performance evidence.'],sources:[{label:'Fixture',url:'',sha256:'b'.repeat(64),revision:null}],relation:null};
return C.make('historical-finding',{model:'test-model',support:'fixture',task:'fixture-task',measure:'fixture accepted count',value:1,maximum:2,cost_usd:null,cost_basis:'unknown',source_sha256:'b'.repeat(64),source_excerpt:'Authored software fixture.',study_status:'software-only'},metadata);}
test('invalid packaged seed leaves destination available for corrected retry',()=>{const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'sr-seed-recovery-'));try{
 const origin=path.join(tmp,'origin');U.init(origin,'Fixture origin',false);const seed=path.join(origin,'app','feed.json'),original=fs.readFileSync(seed),destination=path.join(tmp,'retry');const copied=require(path.join(origin,'app','cli.cjs'));
 fs.writeFileSync(seed,'{invalid');assert.throws(()=>copied.init(destination,'Retry'));assert.equal(fs.existsSync(destination),false);
 fs.writeFileSync(seed,original);assert.equal(copied.init(destination,'Retry').status,'BUILT');
}finally{fs.rmSync(tmp,{recursive:true,force:true});}});
test('withdrawal retires generated public paths while keeping objects and review history',async()=>{const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'sr-withdraw-'));let service;try{
 const hub=path.join(tmp,'hub'),p=packet(),input=path.join(tmp,'packet.json');fs.writeFileSync(input,JSON.stringify(p));U.init(hub,'Withdrawal fixture',false);U.stage(input,hub);U.review(p.sha256,hub,'accept','Regression author','Explicit local software-fixture admission');U.buildHub(hub);service=await U.serve(hub,0);
 assert.equal((await fetch(service.origin+'/records/'+p.sha256+'.json')).status,200);
 U.review(p.sha256,hub,'reject','Regression author','Withdraw this local fixture');assert.equal(U.buildHub(hub).records,0);
 for(const suffix of ['/records/'+p.sha256+'.json','/r/'+p.sha256+'.html'])assert.equal((await fetch(service.origin+suffix)).status,404);
 assert.equal(fs.existsSync(path.join(hub,'objects',p.sha256+'.json')),true);assert.equal(U.events(hub).length,2);assert.equal(fs.existsSync(path.join(hub,'retired-projections')),true);
}finally{if(service){service.server.closeAllConnections();await new Promise(r=>service.server.close(r));}fs.rmSync(tmp,{recursive:true,force:true});}});
