#!/usr/bin/env node
'use strict';
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const EXPECTED_CORE_SHA256 = '6375c45ae35890250020ae24e3edfc18a9c9e3bc7f2fa92dd87e578e1d29f0a5';
function fail(m){throw new Error(m)}
function sha256(b){return crypto.createHash('sha256').update(b).digest('hex')}
function readJson(f){return JSON.parse(fs.readFileSync(f,'utf8'))}
function loadCore(){
 const app=path.resolve(__dirname,'..','research-desk','app.html'), html=fs.readFileSync(app,'utf8');
 const m=[...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].find(x=>x[1].includes('root.ResearchCore=api'));
 if(!m)fail('Research Desk app does not contain its ResearchCore owner script.');
 const source=Buffer.from(m[1],'utf8'), digest=sha256(source);
 if(digest!==EXPECTED_CORE_SHA256)fail('ResearchCore raw-byte pin mismatch: expected '+EXPECTED_CORE_SHA256+', got '+digest);
 const util=require('node:util'); globalThis.TextEncoder ||= util.TextEncoder; globalThis.TextDecoder ||= util.TextDecoder;
 const nativeModule={exports:{}}; new Function('module','require',source.toString('utf8'))(nativeModule,require);
 if(!nativeModule.exports||typeof nativeModule.exports.verifyPacket!=='function')fail('ResearchCore did not initialize.');
 return nativeModule.exports;
}
async function main(){
 const args=process.argv.slice(2), opts={};
 for(let i=0;i<args.length;i+=2){if(!args[i]?.startsWith('--')||!args[i+1])fail('expected --packet PATH --receipt PATH');opts[args[i].slice(2)]=args[i+1]}
 if(!opts.packet||!opts.receipt||Object.keys(opts).some(k=>!['packet','receipt'].includes(k)))fail('expected --packet PATH --receipt PATH');
 const C=loadCore(), original=readJson(opts.packet), receipt=readJson(opts.receipt), ws=await C.verifyPacket(original), state=C.state(ws);
 if(receipt.schema!=='cantos/observation-reprojection@1'||receipt.operation!=='reimported_projection')fail('unsupported or non-reimport projection receipt');
 if(typeof receipt.row_id!=='string'||!/^[0-9a-f]{64}$/.test(receipt.row_id))fail('invalid receipt row_id');
 if(typeof receipt.actor!=='string'||!receipt.actor.trim())fail('receipt actor label is required');
 if(typeof receipt.observed_at!=='string')fail('receipt observed_at is required');
 for(const k of ['pinned_source_match','raw_sha256_match','row_id_match','native_row_sha256_match'])if(receipt.checks?.[k]!==true)fail('receipt check failed: '+k);
 if(!receipt.procedure||typeof receipt.procedure.name!=='string'||!/^[0-9a-f]{64}$/.test(receipt.procedure.sha256||''))fail('receipt procedure pin is incomplete');
 if(receipt.outcome?.kind!=='reimport'||receipt.outcome.benchmark_executed!==false||receipt.outcome.calibration_performed!==false||receipt.outcome.accepted_work!==null)fail('receipt outcome misstates re-import as execution or acceptance');
 if(typeof receipt.matches_current_projection!=='boolean')fail('receipt must state projection comparison result');
 const candidates=[];
 for(const id of Object.keys(state.records)){
  const record=C.version(state,id,1); if(!record||record.kind!=='source'||!Array.isArray(record.data?.rows))continue;
  for(const row of record.data.rows)if(row?.row_id===receipt.row_id)candidates.push({record,row});
 }
 if(candidates.length!==1)fail('expected exactly one row '+receipt.row_id+' in packet source history; found '+candidates.length);
 const {record:batch,row}=candidates[0];
 if(C.canonical(receipt.before)!==C.canonical(row))fail('receipt before-row differs from exact retained native source row');
 if(!receipt.source||typeof receipt.source!=='object')fail('receipt source lineage is missing');
 for(const key of ['origin','url','revision','retrieved_at','evidence_class','raw_sha256','row_index','native_row_sha256','license','time_basis'])if(receipt.source[key]!==row.source?.[key])fail('receipt source lineage differs from retained native field '+key);
 if(receipt.row_id!==row.row_id)fail('receipt row_id does not match retained source row');
 const calculatedMatch=C.canonical(receipt.before)===C.canonical(receipt.rebuilt);
 if(receipt.matches_current_projection!==calculatedMatch)fail('receipt projection match flag does not match before/rebuilt rows');
 if(!receipt.rebuilt||receipt.rebuilt.row_id!==row.row_id)fail('rebuilt projection must retain selected row_id');
 const sourceId='projection-'+receipt.row_id.slice(0,40);
 const claimId='projection-attempt-'+receipt.row_id.slice(0,24)+'-'+sha256(Buffer.from(JSON.stringify(receipt))).slice(0,16);
 const actor=receipt.actor.slice(0,160);
 const sourceRecord=await C.put(ws,{
  id:sourceId,kind:'source',title:'Re-imported observation projection '+receipt.row_id.slice(0,16),
  summary:'Current adapter re-import for retained row '+receipt.row_id+'; exact before/rebuilt rows and transformation receipt retained. Actor is a supplied label, not authenticated identity.',
  tier:batch.tier,disposition:'observed',deps:[{id:batch.id,revision:1}],
  data:{schema:'cantos/observation-reprojection@1',operation:receipt.operation,row_id:receipt.row_id,
   source_batch_id:batch.id,source_batch_revision:1,bundle:receipt.bundle,source:receipt.source,before:receipt.before,rebuilt:receipt.rebuilt,
   matches_current_projection:receipt.matches_current_projection,procedure:receipt.procedure,outcome:receipt.outcome,
   actor_label:actor,actor_authenticated:false,observed_at:receipt.observed_at,checks:receipt.checks}
 },actor,receipt.observed_at);
 const claimRecord=await C.put(ws,{
  id:claimId,kind:'claim',title:'Projection re-import attempt '+receipt.row_id.slice(0,16),
  summary:receipt.matches_current_projection
   ?'The current adapter reproduced the retained normalized row. Source re-import only; no benchmark, calibration, or accepted-work outcome was produced.'
   :'The current adapter produced a changed normalized row. Source re-import only; no benchmark, calibration, or accepted-work outcome was produced.',
  tier:batch.tier,disposition:'observed',deps:[{id:sourceRecord.id,revision:sourceRecord.revision},{id:batch.id,revision:1}],
  data:{schema:'cantos/projection-attempt@1',operation:receipt.operation,row_id:receipt.row_id,
   projection_source_id:sourceRecord.id,projection_source_revision:sourceRecord.revision,source_batch_id:batch.id,source_batch_revision:1,bundle:receipt.bundle,
   procedure:receipt.procedure,observed_at:receipt.observed_at,actor_label:actor,actor_authenticated:false,
   result:{matches_current_projection:receipt.matches_current_projection,before:receipt.before,rebuilt:receipt.rebuilt,checks:receipt.checks},
   limits:{benchmark_executed:false,calibration_performed:false,accepted_work:null,attribution_authenticates_identity:false}}
 },actor,receipt.observed_at);
 const packet=await C.pack(ws); await C.verifyPacket(packet);
 process.stdout.write(JSON.stringify({packet,source_record_id:sourceRecord.id,source_record_revision:sourceRecord.revision,
  claim_record_id:claimRecord.id,claim_record_revision:claimRecord.revision,actor_label:actor}));
}
main().catch(e=>{process.stderr.write(String(e?.stack||e)+'\n');process.exitCode=1});
