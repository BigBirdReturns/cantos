'use strict';
const test=require('node:test'),a=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),cp=require('node:child_process');
const K=require('../community/core.cjs'),R=require('../scripts/recompute.cjs');
function sample(){
 const meta={title:'Dispatcher fixture',provider:'Test provider',hardware:'No measured hardware',workload:'Test work',variant:'Authored fixture',observed_at:'2026-09-27',contributor:'Software test',funding:'No expenditure',relationship:'Software test author',limitations:['Authored software fixture, not a public measurement.'],sources:[{label:'Fixture',url:'',sha256:'b'.repeat(64),revision:null}],relation:null};
 const body={model:'test-model',support:'fixture',task:'test-work',measure:'fixture accepted count',value:1,maximum:2,cost_usd:1,cost_basis:'shadow-estimated',source_sha256:'b'.repeat(64),source_excerpt:'Authored test data.',study_status:'software-only'};
 const p=K.make('historical-finding',body,meta);
 return K.decision([p],{left:p.sha256,right:p.sha256,metric:'cost_per_unit',operator:'less',threshold:0,scope:'general',wording:'A universal fixture claim'});
}
test('shared verifier delegates a community decision to its existing authority',()=>{const d=sample(),r=R.verify(d);a.equal(r.status,'RECOMPUTED');a.equal(r.kind,'community-claim');a.equal(r.sha256,d.sha256);a.equal(r.execution_authorized,false);a.deepEqual(r.result,d.payload.result);});
test('community decision tampering remains rejected through shared verifier',()=>{const d=sample();d.payload.claim.wording='Changed after sealing';a.throws(()=>R.verify(d));});
test('shared CLI accepts a valid community export above its old five MiB limit',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'sr-dispatch-')),file=path.join(dir,'decision.json');
 try{fs.writeFileSync(file,JSON.stringify(sample())+' '.repeat(6*1024*1024));const r=cp.spawnSync(process.execPath,[path.resolve(__dirname,'../scripts/recompute.cjs'),file],{encoding:'utf8',timeout:30000,windowsHide:true});a.equal(r.status,0,r.stderr);a.equal(JSON.parse(r.stdout).kind,'community-claim');}
 finally{fs.rmSync(dir,{recursive:true,force:true});}
});
