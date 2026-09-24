'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const M=require('../scripts/materials.cjs');
const raw=fs.readFileSync(path.join(__dirname,'../materials/registry.json'));
const hash=crypto.createHash('sha256').update(raw).digest('hex'),now=Date.parse('2026-09-24T20:00:00Z');
function fixture(snapshot){const root=fs.mkdtempSync(path.join(os.tmpdir(),'sr-materials-'));fs.mkdirSync(path.join(root,'materials'));fs.writeFileSync(path.join(root,'materials/registry.json'),raw);if(snapshot)fs.writeFileSync(path.join(root,'materials/observations.json'),JSON.stringify(snapshot));return root;}
function s(){return {schema:'second-run/material-observations@1',registry_sha256:hash,collected_at:'2026-09-24T19:00:00Z',observations:[{id:'ha-price',url:'https://hotaisle.xyz/pricing',status:'OBSERVED',change:'NEW',last_good:{observed_at:'2026-09-24T19:00:00Z',expires_at:'2026-09-25T19:00:00Z',content_sha256:'a'.repeat(64)}}]};}
function use(snap,f){const root=fixture(snap);try{f(root);}finally{fs.rmSync(root,{recursive:true,force:true});}}
test('registry reads without network, no snapshot is explicit',()=>use(null,r=>{const x=M.inspect(r,{},now);assert.equal(x.snapshot_status,'UNAVAILABLE');assert.equal(x.recipes.length,4);}));
test('current observation is source observation, not qualified route',()=>use(s(),r=>{const x=M.inspect(r,{},now);assert.equal(x.sources[0].observation_state,'OBSERVED');assert.ok(x.actions_not_granted.includes('execute'));}));
test('recipe selects its dependencies',()=>use(s(),r=>{const x=M.inspect(r,{recipe:'coding-burst'},now);assert.equal(x.recipes.length,1);assert.ok(x.sources.some(x=>x.id==='evalplus-contract'));}));
test('unknown recipe refused',()=>use(s(),r=>assert.throws(()=>M.inspect(r,{recipe:'missing'},now),/Unknown recipe/)));
test('unknown layer refused',()=>use(s(),r=>assert.throws(()=>M.inspect(r,{layer:'medals'},now),/Unknown layer/)));
test('registry mismatch never becomes fresh',()=>{let x=s();x.registry_sha256='0'.repeat(64);use(x,r=>assert.equal(M.inspect(r,{},now).snapshot_status,'UNAVAILABLE'));});
test('expiry is recalculated at read time',()=>use(s(),r=>assert.equal(M.inspect(r,{},now+86400000*2).sources[0].observation_state,'STALE')));
test('future capture rejected',()=>{let x=s();x.collected_at='2099-01-01T00:00:00Z';use(x,r=>assert.equal(M.inspect(r,{},now).snapshot_status,'UNAVAILABLE'));});
test('failed read never renews a source',()=>{let x=s();x.observations[0].status='UNAVAILABLE';use(x,r=>assert.equal(M.inspect(r,{},now).sources[0].observation_state,'READ_FAILED'));});
test('source URL mismatch held',()=>{let x=s();x.observations[0].url='https://other.invalid/';use(x,r=>assert.equal(M.inspect(r,{},now).sources[0].observation_state,'SOURCE_MISMATCH'));});
test('invalid expiry held',()=>{let x=s();x.observations[0].last_good.expires_at='bad';use(x,r=>assert.equal(M.inspect(r,{},now).sources[0].observation_state,'INVALID_TIME'));});
test('CFD recipe preserves commercial rights gate',()=>use(s(),r=>assert.match(M.inspect(r,{recipe:'numerical-batch'},now).recipes[0].authority,/licence/)));
