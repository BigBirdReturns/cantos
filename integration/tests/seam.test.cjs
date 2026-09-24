'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),cp=require('node:child_process');
const ROOT=path.resolve(__dirname,'../..');
const {Store}=require('../../hot-aisle/runner/lib/store.cjs'),{Jobs}=require('../../hot-aisle/runner/lib/jobs.cjs');
const local=require('../../hot-aisle/runner/lib/adapters/local.cjs'),instrument=require('../../hot-aisle/runner/lib/server.cjs');
const P=require('../../hot-aisle/runner/lib/publication.cjs'),E=require('../../hot-aisle/runner/lib/engine.cjs');
const record=require('../../hot-aisle/runner/lib/record.cjs'),catalogue=require('../../hot-aisle/runner/lib/catalog.cjs');
const desk=require('../../compute/scripts/connect.cjs'),Q=require('../../compute/adapters/qualified-engine.cjs');
const client=require('../../compute/adapters/instrument.cjs');
const clone=x=>JSON.parse(JSON.stringify(x));
function reseal(r){const {sha256,...rest}=r;r.sha256=E.sha256(E.load().canonical(rest));return r;}
let dir,store,jobs,rec,bundle;
test.before(async()=>{dir=fs.mkdtempSync(path.join(os.tmpdir(),'compute-seam-'));store=new Store(dir);jobs=new Jobs(store);const job=jobs.plan(local.demoPlanInput({repeats:2,concurrency:[1,8],target:{env:{FAKE_VLLM_DELAY_MS:'0'}}}));jobs.approve(job.id,{plan_sha256:job.plan.sha256});await jobs.start(job.id);rec=store.read('records',jobs.get(job.id).record_id);bundle=P.bundle(rec);});
test.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
test('one catalogue, DigitalOcean default and future schedule remain explicit',()=>{
 assert.equal(fs.readFileSync(path.join(ROOT,'compute/data/catalog.json'),'utf8'),fs.readFileSync(path.join(ROOT,'hot-aisle/data/catalog.json'),'utf8'));
 assert.equal(catalogue.quote('do-mi300x').rate,2.59);assert.equal(catalogue.quote('do-h100').rate,4.41);
 assert.equal(catalogue.quote('nb-h100','2026-10-01').rate,4.5);assert.equal(local.demoPlanInput().comparator.provider,'DigitalOcean H100');
});
test('generated browser and CLI verifier match instrument projection',()=>{
 assert.equal(Q.authority.engine.engine_sha256,E.identity().engine_sha256);
 assert.equal(E.load().canonical(Q.publication.projection(bundle)),E.load().canonical(P.projection(bundle)));
 assert.equal(Q.publication.projection(bundle).synthetic,true);
 assert.equal(Q.publication.projection(bundle).expected_trials,4);
});
test('no publication before explicit handoff; retries do not overwrite snapshots',()=>{
 assert.equal(require('../../hot-aisle/runner/lib/publication-store.cjs').list(store).publications.length,0);
 const a=instrument.publish(store,rec),file=path.join(a.published,'bundle.json'),bytes=fs.readFileSync(file),b=instrument.publish(store,rec);
 assert.equal(a.publication_id,b.publication_id);assert.deepEqual(fs.readFileSync(file),bytes);
 const next=clone(rec);next.created=new Date(Date.parse(rec.created)+1000).toISOString();reseal(next);const c=instrument.publish(store,next);
 assert.notEqual(a.publication_id,c.publication_id);assert.deepEqual(fs.readFileSync(file),bytes);
});
test('read-only services discover and recompute the published record, not raw files',async()=>{
 const runner=instrument.createServer({store,jobs});const base=await runner.listenOn();
 const ws=desk.makeWorkspace({runner:base});const service=await desk.startHttp(ws);
 const headers={Authorization:'Bearer '+service.token};
 try{
  const listing=await(await fetch(service.origin+'/api/publications',{headers})).json();assert.equal(listing.status,'CONNECTED');assert.equal(listing.catalog.state,'MATCH');assert.equal(listing.publications.length,2);
  const row=listing.publications.find(x=>x.record_sha256===rec.sha256),response=await fetch(service.origin+'/api/publications/'+row.publication_id,{headers}),value=await response.json();
  assert.equal(response.status,200);assert.equal(value.record.sha256,rec.sha256);assert.equal(value.evidence.sha256,bundle.evidence.sha256);Q.publication.verify(value);
  assert.equal((await ws.listRuns()).runs.length,0);
  assert.equal((await fetch(service.origin+'/api/jobs',{method:'POST',headers})).status,405);
  const count=jobs.list().length;await desk.call(ws,'compute_get_publication',{id:row.publication_id});assert.equal(jobs.list().length,count);
 }finally{await new Promise(r=>service.server.close(r));await new Promise(r=>runner.close(r));}
});
test('record/evidence checksum mismatch is rejected',()=>{const bad=clone(bundle);bad.record.derived.primary_concurrency=99;assert.throws(()=>Q.publication.verify(bad));});
test('re-signed false disposition cannot replace derived qualification',()=>{const bad=clone(bundle);bad.record.disposition={qualified:false,reasons:['arbitrary']};reseal(bad.record);assert.throws(()=>Q.publication.verify(bad),/disposition/i);});
test('rule mirrors cannot disagree with the approved plan',()=>{const bad=clone(bundle);bad.record.rule.gates.ttft=1;reseal(bad.record);assert.throws(()=>Q.publication.verify(bad),/gates|mirror/i);});
test('an individually valid packet from a different record is rejected',()=>{const altered=clone(rec);altered.created='2026-09-01T00:00:00.000Z';reseal(altered);const bad=clone(bundle);bad.evidence=record.packet(altered);E.load().recompute(bad.evidence);assert.throws(()=>Q.publication.verify(bad),/does not belong/);});
test('different source engine cannot be blessed by re-signing the record',()=>{const bad=clone(bundle);bad.record.derived.engine.engine_sha256='f'.repeat(64);reseal(bad.record);assert.throws(()=>Q.publication.verify(bad),/identity/);});
test('deleted retained trial invalidates derived figures',()=>{const bad=clone(bundle);bad.record.observed.trials.pop();reseal(bad.record);assert.throws(()=>Q.publication.verify(bad));});
test('partial campaigns preserve their exact completeness boundary',()=>{const partial=clone(rec);partial.observed.trials.pop();partial.derived=record.derive(partial);partial.disposition=partial.derived.disposition;reseal(partial);const p=Q.publication.projection(P.bundle(partial));assert.equal(p.complete,false);assert.equal(p.completed_trials,3);assert.equal(p.expected_trials,4);});
test('same-allocation repricing uses instrument revalidation and preserves original bytes',()=>{
 const before=JSON.stringify(bundle),count=store.list('jobs').length;
 const first=Q.decision(bundle),next=Q.decision(bundle,{price:{rate:1.5}},new Date().toISOString(),first.sha256);Q.verifyDecision(next);
 assert.equal(next.payload.previous,first.sha256);assert.equal(next.payload.result.summary.requires_measurement,0);assert.ok(Math.abs(next.payload.result.scenario.cells[0].cost_per_1000/rec.derived.cells[0].cost.costPer1000-1.5/rec.declared.price.rate)<1e-12);
 assert.equal(JSON.stringify(bundle),before);assert.equal(store.list('jobs').length,count);
 const f=path.join(dir,'decision.json');fs.writeFileSync(f,JSON.stringify(next));const out=cp.spawnSync(process.execPath,[path.join(ROOT,'compute/scripts/recompute.cjs'),f],{encoding:'utf8'});assert.equal(out.status,0,out.stderr);assert.equal(JSON.parse(out.stdout).record_sha256,rec.sha256);
});
test('failed local publication stays visible as a hold',()=>{
 const pub=instrument.publish(store,rec),p=path.join(pub.published,'bundle.json'),before=fs.readFileSync(p);try{fs.writeFileSync(p,'{}');const s=require('../../hot-aisle/runner/lib/publication-store.cjs').list(store);assert.equal(s.holds.length,1);assert.equal(s.publications.length,1);}finally{fs.writeFileSync(p,before);}
});
test('connection refuses remote origins, credentials and path injection',()=>{
 for(const u of ['https://example.com','http://localhost:8000','http://127.0.0.1:8000/path','http://user@127.0.0.1:8000','http://127.0.0.1:8000/?x=y'])assert.throws(()=>client.configure(u));
});
test('runner rejects untrusted Host headers',async()=>{const s=instrument.createServer({store,jobs}),base=await s.listenOn();try{const status=await new Promise((resolve,reject)=>{require('node:http').get(base+'/api/status',{headers:{Host:'attacker.invalid'}},r=>{r.resume();resolve(r.statusCode);}).on('error',reject);});assert.equal(status,403);}finally{await new Promise(r=>s.close(r));}});

test('mutating an approved plan body is rejected before any execution',async()=>{const j=jobs.plan(local.demoPlanInput({repeats:1,concurrency:[1]}));jobs.approve(j.id,{plan_sha256:j.plan.sha256});const altered=jobs.get(j.id);altered.plan.workload.num_prompts+=1;store.write('jobs',j.id,altered);await assert.rejects(()=>jobs.start(j.id),/body changed/);assert.equal(jobs.get(j.id).trials[0].status,'pending');});
test('price-only change cannot borrow performance from another GPU allocation',()=>{assert.throws(()=>Q.decision(bundle,{price:{gpus:8}}),/new performance qualification/);});

require('node:test').test('published-origin theme bootstrap has no remote font dependency',()=>{
 const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
 const html=fs.readFileSync(path.resolve(__dirname,'../../hot-aisle/index.html'),'utf8');
 const bootstrap=html.match(/<script>([\s\S]*?)<\/script>/);assert.ok(bootstrap,'theme bootstrap is present');
 const appended=[],document={documentElement:{dataset:{}},createElement:()=>({}),head:{append:x=>appended.push(x)}};
 vm.runInNewContext(bootstrap[1],{location:{hostname:'bigbirdreturns.github.io',protocol:'https:'},localStorage:{getItem:()=> 'dark'},document},{timeout:1000});
 assert.equal(document.documentElement.dataset.theme,'dark');assert.equal(appended.length,0,'public visits must not insert remote dependencies');
});
