// Reproduce the four constructions recorded in Astra's review against the original release.
// These are fresh packets with fresh event times, not copies of Astra's retained packet bytes.
const fs=require('node:fs'),path=require('node:path');
const oldRoot=path.resolve(process.argv[2]);const out=path.resolve(process.argv[3]);fs.mkdirSync(out,{recursive:true});
const D=require(path.join(oldRoot,'source/foundation.js')),C=D.core;
async function save(name,w){const p=await C.pack(w);await C.verifyPacket(p);fs.writeFileSync(path.join(out,name),JSON.stringify(p,null,2)+'\n');}
(async()=>{
 let w=await D.create();await save('compatible-old-workspace.json',w);
 let r=C.clone(C.latest(C.state(w),'run-a'));r.data.billing.quote_total_usd=null;await C.put(w,r,'Astra construction reproduced');await D.recompute(w);await save('null-quote.json',w);
 w=await D.create();let d=C.clone(C.latest(C.state(w),'decision'));d.deps=[];await C.put(w,d,'Astra construction reproduced');await C.review(w,'decision','accept','Native-valid conclusion without its calculation dependency.','Boundary reproduction');await C.freeze(w,'decision','Boundary reproduction');await save('detached-decision.json',w);
 w=await D.create();await C.put(w,{id:'external-source',kind:'source',title:'Non-synthetic marker',summary:'Authored test marker, not an observed event.',tier:'operator_supplied',disposition:'observed',deps:[],data:{test_marker:true}},'Astra construction reproduced');await save('mixed-evidence.json',w);
 w=await D.create();const original=C.state(w).reports[0],snapshot=C.clone(original.snapshot);snapshot.review.reviewer='Reviewer absent from the review journal';snapshot.review.rationale='This rationale was never recorded as an accepted review.';await C.append(w,'freeze',{target:'decision',fingerprint:original.fingerprint,snapshot,snapshot_hash:await C.hash(snapshot)},'Astra construction reproduced');await save('review-mismatch.json',w);
 const accepted=[];for(const f of ['null-quote.json','detached-decision.json','mixed-evidence.json','review-mismatch.json']){await D.restore(JSON.parse(fs.readFileSync(path.join(out,f))));accepted.push(f);}
 const a=await D.create();await new Promise(r=>setTimeout(r,20));const b=await D.create();
 console.log(JSON.stringify({old_adapter_accepted:accepted,old_create_changes_initial_edition:C.state(a).reports[0].snapshot_hash!==C.state(b).reports[0].snapshot_hash,packet_basis:'New constructions matching review code, not original council packets'},null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
