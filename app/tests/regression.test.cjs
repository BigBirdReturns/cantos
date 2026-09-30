'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const D=require('../source/foundation.js'),C=D.core;
const packet=name=>JSON.parse(fs.readFileSync(path.join(__dirname,'reproduced-packets',name),'utf8'));
for(const [name,error] of [['null-quote.json',/complete synthetic quotes/],['detached-decision.json',/dependency topology/],['mixed-evidence.json',/Unsupported evidence/],['review-mismatch.json',/review contents differ/]]){
 test('refuses reproduced '+name,async()=>{const p=packet(name),before=C.canonical(p);await assert.rejects(()=>D.restore(p),error);assert.equal(C.canonical(p),before);});
}
test('native owner itself rejects review-content mismatch',async()=>{await assert.rejects(()=>C.verifyPacket(packet('review-mismatch.json')),/review contents differ/);});
test('unmodified old packet remains compatible and retains its exact historical hashes',async()=>{const p=packet('compatible-old-workspace.json'),ws=await D.restore(p);assert.equal((await C.pack(ws)).sha256,p.sha256);assert.equal(ws.version,'1.0.0');});
test('Edition 01 and workspace match across fresh native processes',()=>{
 const code="const D=require('./source/foundation.js');D.create().then(w=>D.pack(w)).then(p=>process.stdout.write(JSON.stringify({packet:p.sha256,edition:D.core.state(p.workspace).reports[0].snapshot_hash,at:p.workspace.events.map(e=>e.at)})))";
 const read=()=>JSON.parse(cp.execFileSync(process.execPath,['-e',code],{cwd:path.join(__dirname,'..'),encoding:'utf8'}));
 const a=read(),b=read();assert.deepEqual(a,b);assert.ok(a.at.every(x=>x==='2026-09-28T00:00:00Z'));
});
test('historical non-synthetic records also refuse after a synthetic successor',async()=>{
 const p=packet('mixed-evidence.json'),ws=await C.verifyPacket(p),r=C.clone(C.latest(C.state(ws),'external-source'));r.tier='synthetic';await C.put(ws,r,'Synthetic successor test');const packed=await C.pack(ws);await assert.rejects(()=>D.restore(packed),/Unsupported evidence/);
});
test('three second deadline is consequential and preserves baseline',async()=>{
 let w=await D.create();const frozen=C.canonical(C.state(w).reports[0]);w=await D.change(w,{deadline_ms:3000});await D.recompute(w);assert.deepEqual((await D.view(w)).calc.data.results.map(x=>x.accepted),[12,12]);assert.equal(C.canonical(C.state(w).reports[0]),frozen);
});
test('new snapshot review equals the journal review in full',async()=>{
 let w=await D.create();w=await D.change(w,{grader:'extract_json'});await D.recompute(w);w=await D.reviewed(w,'Review regression','Accepted under an explicit synthetic extraction contract.');w=await D.sealed(w,'Review regression');const s=C.state(w),r=s.reports.at(-1);assert.deepEqual(r.snapshot.review,s.reviews.find(x=>x.event_hash===r.snapshot.review.event_hash));await C.verifyPacket(await C.pack(w));
});

// ---- Hardware decision class regressions (1.0.2 candidate). SYNTHETIC arms unless the real Run 3 records are present. ----
const hwAt='2026-09-29T00:00:00Z';
const hwPins={taskset:'synthetic',contract:'recorded-correct',load:'synthetic',boundary:'scheduled-arrival-to-release',model:'m',revision:'r',precision:'fp8',tokenizer:'t',runtime:'rt',cache:'none'};
function synthArm(letter,n,rate){const tasks=[];for(let i=0;i<n;i++)tasks.push({id:'req-'+i,scheduled_at_ms:i*400,attempts:[{status:'ok',first_token_ms:(i*37)%1400,elapsed_ms:1000+(i*53)%70000,correct:(i*7+(letter==='a'?1:2))%3!==0}]});
 return {schema:'second-run/task-run@1',run_id:'arm-'+letter,label:'SYNTHETIC arm '+letter,evidence:'synthetic',pins:hwPins,identity:{vendor:'V'+letter,hardware:'H'+letter,arm:letter.toUpperCase()+'/S0',runtime:'rt',window_minutes:60,window_basis:'closed_ledger'},tasks,billing:{rate_usd_per_hour:rate,cost_basis:'list',currency:'USD',scope:'SYNTHETIC list rate.'}};}
async function hwWorkspace(armsData,policy,tier='synthetic',extra){const ws=C.empty('SYNTHETIC hardware regression'),rec=(id,kind,data,deps=[])=>({id,kind,title:id,summary:'regression fixture',tier,disposition:kind==='source'?'observed':'draft',data,deps}),ref=r=>({id:r.id,revision:r.revision});
 const src=await C.put(ws,rec('src','source',{fixture:true}),'Test',hwAt),pol=await C.put(ws,rec('policy','policy',policy,[ref(src)]),'Test',hwAt);const runs=[];
 for(const d of armsData)runs.push(await C.put(ws,rec('run-'+d.run_id,'run',d,[ref(src)]),'Test',hwAt));if(extra)await extra(ws,rec,ref,src);
 const cmp=C.compare(runs.map(r=>r.data),pol.data),calc=await C.put(ws,rec('calculation','calculation',{...cmp,selectedRecordIds:runs.map(r=>r.id),recipe:'task-cost@1'},[ref(pol),...runs.map(ref)]),'Test',hwAt);
 await C.put(ws,rec('decision','conclusion',{winner:cmp.winner},[ref(calc)]),'Test',hwAt);await C.review(ws,'decision','accept','Regression fixture review; label only.','Test',hwAt);await C.freeze(ws,'decision','Test',hwAt);return ws;}
const synthPolicy={grader:'recorded',deadline_ms:60000,first_token_ms:1000,quality_floor:0,min_tasks:50,cost_basis:'list',comparison_mode:'hardware'};
test('1.0.1 workspaces remain readable and 1.0.2 is the new write version',async()=>{const w=await D.create();assert.equal(w.version,'1.0.2');w.version='1.0.1';const p=await C.pack(w);assert.equal((await D.restore(p)).version,'1.0.1');w.version='1.0.3';await assert.rejects(async()=>C.verifyPacket(await C.pack(w)),/Unsupported workspace version/);});
test('arm size cap is lifted to 20,000 recorded requests, not removed',async()=>{const big=synthArm('a',6000,2.99);C.validateRun(big);const r=C.evaluate(big,{...synthPolicy,min_tasks:6000});assert.equal(r.strip.length,6000);
 const huge=synthArm('a',20001,2.99);assert.throws(()=>C.validateRun(huge),/20,000/);});
test('a run not pinned by the calculation is refused by the hardware workflow',async()=>{const w=await hwWorkspace([synthArm('a',50,2.99),synthArm('b',50,4.41)],synthPolicy,'synthetic',async(ws,rec,ref,src)=>{await C.put(ws,rec('run-orphan','run',{...synthArm('c',50,1),run_id:'arm-c'},[ref(src)]),'Test',hwAt);});
 await assert.rejects(async()=>D.restore(await C.pack(w)),/not pinned by the calculation/);});
test('a hardware workspace cannot silently switch to the task class',async()=>{const w=await hwWorkspace([synthArm('a',50,2.99),synthArm('b',50,4.41)],synthPolicy);const p=C.clone(C.latest(C.state(w),'policy'));p.data={...p.data,grader:'strict_json',cost_basis:'quote',comparison_mode:'hardware'};
 await C.put(w,p,'Test');await assert.rejects(async()=>D.restore(await C.pack(w)),/cannot change decision class/);
 p.data={...p.data,comparison_mode:'task'};await C.put(w,{...p,revision:undefined},'Test');await assert.rejects(async()=>D.restore(await C.pack(w)),/Unsupported evidence/);});
test('the hardware six-pin rule still holds for arms',async()=>{const b=synthArm('b',50,4.41);b.pins={...hwPins,runtime:'other'};const cmp=C.compare([synthArm('a',50,2.99),b],synthPolicy);assert.equal(cmp.winner,null);assert.ok(cmp.blockers.includes('Mismatched comparison pin: runtime'));});
test('forged calculation figures are refused at append time',async()=>{const w=await hwWorkspace([synthArm('a',50,2.99),synthArm('b',50,4.41)],synthPolicy),calc=C.clone(C.latest(C.state(w),'calculation'));calc.data.results[1].cost_per_success=0.0001;calc.data.winner='arm-b';
 await assert.rejects(()=>C.put(w,calc,'Test'),/does not recompute from its pinned inputs/);});
// Real Run 3 records (hands/run3data) when present: reconcile the report and prove two editions fit the 12 MB import limit.
const run3=process.env.CANTOS_RUN3_DATA||path.join(__dirname,'..','..','..','hands','run3data');
test('real Run 3 arms reconcile and a two-edition packet fits 12 MB',{skip:!fs.existsSync(path.join(run3,'run3-requests-n-t0.json'))&&'hands/run3data not present'},async()=>{
 const load=(f,id,identity,rate)=>({schema:'second-run/task-run@1',run_id:id,label:identity.arm,evidence:'producer_reported',pins:{...hwPins,runtime:'vLLM 0.30.0'},identity,billing:{rate_usd_per_hour:rate,cost_basis:'list',currency:'USD',scope:'List rate (probe).'},
  tasks:JSON.parse(fs.readFileSync(path.join(run3,f),'utf8')).map(x=>({id:String(x.id),scheduled_at_ms:x.scheduled_at_ms,attempts:[{status:x.elapsed_ms===null?'error':'ok',first_token_ms:x.first_token_ms,elapsed_ms:x.elapsed_ms,correct:x.correct}]}))});
 const A=load('run3-requests-a-t0.json','a-t0',{vendor:'Hot Aisle',hardware:'1x MI300X',arm:'A/T0',runtime:'vLLM 0.30.0',window_minutes:64.7,window_basis:'own_seat_equivalent'},2.99),N=load('run3-requests-n-t0.json','n-t0',{vendor:'DigitalOcean',hardware:'1x H100',arm:'N/T0',runtime:'vLLM 0.30.0',window_minutes:69.8,window_basis:'closed_ledger'},4.41);
 const policy={...synthPolicy,min_tasks:8622};let w=await hwWorkspace([A,N],policy,'operator_supplied');let v=await D.view(w);
 assert.deepEqual(v.calc.data.results.map(x=>x.accepted),[4336,4280]);assert.deepEqual(v.calc.data.results.map(x=>(x.cost_per_success*1000).toFixed(2)),['0.74','1.20']);assert.equal(v.calc.data.winner,'a-t0');
 w=await D.change(w,{rates:{'n-t0':2.49}});await D.recompute(w);w=await D.reviewed(w,'Test','Rate scenario over retained records.');w=await D.sealed(w,'Test');v=await D.view(w);assert.equal(v.calc.data.winner,'n-t0');
 const text=JSON.stringify(await D.pack(w));assert.ok(text.length<12000000,'packet '+text.length);assert.equal(C.state(await D.restore(C.parse(text))).reports.length,2);});
