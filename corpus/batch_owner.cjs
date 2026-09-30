#!/usr/bin/env node
'use strict';
// Research Desk owns validation and the journal. Imported rows remain source data.
// Reads corpus rows.jsonl (written in origin, row_id order) and retains them as
// native Research Desk packets through the pinned ResearchCore owner.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const {StringDecoder} = require('node:string_decoder');
const EXPECTED_CORE_SHA256 = '6375c45ae35890250020ae24e3edfc18a9c9e3bc7f2fa92dd87e578e1d29f0a5';
const MAX_ROWS = 1000, MAX_BYTES = 2500000;
function fail(m){throw new Error(m)}
function sha256(b){return crypto.createHash('sha256').update(b).digest('hex')}
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
async function* sourceLines(file,hash){
 // Pull chunks only as the packet owner asks for another line. readline's
 // event queue can otherwise fill while native packet verification is awaited.
 const decoder=new StringDecoder('utf8');let pending='';
 for await(const chunk of fs.createReadStream(file,{highWaterMark:65536})){
  hash.update(chunk);pending+=decoder.write(chunk);
  let end;
  while((end=pending.indexOf('\n'))!==-1){
   const line=pending.slice(0,end);pending=pending.slice(end+1);
   yield line.endsWith('\r')?line.slice(0,-1):line;
  }
  if(Buffer.byteLength(pending)>12*1024*1024)fail('A source row exceeds the native packet size limit');
 }
 pending+=decoder.end();
 if(pending)yield pending.endsWith('\r')?pending.slice(0,-1):pending;
}
async function main(){
 const [input,output,actorArg]=process.argv.slice(2);
 if(!input||!output)fail('Usage: node batch_owner.cjs rows.jsonl output-directory [actor-label]');
 const actor=(actorArg||'Cantos estate importer').slice(0,160);
 if(fs.existsSync(output)&&fs.readdirSync(output).length)fail('Refusing to write packets into a non-empty directory: '+output);
 fs.mkdirSync(output,{recursive:true});
 const C=loadCore(), index=[];let batch=[],bytes=0,total=0;
 async function emit(){
  if(!batch.length)return;
  for(let i=1;i<batch.length;i++)if(!(batch[i-1].row_id<batch[i].row_id))fail('rows.jsonl is not in ascending row_id order within '+batch[i].source.origin);
  const serial=JSON.stringify(batch),id='batch-'+sha256(serial).slice(0,32);
  const origins=[...new Set(batch.map(r=>r.source.origin))],kinds=[...new Set(batch.map(r=>r.kind))];
  if(origins.length!==1)fail('a batch must hold one origin');
  const at=batch.map(r=>r.source.retrieved_at).sort().at(-1);
  const synthetic=batch.every(r=>r.source.evidence_class==='synthetic');
  if(batch.some(r=>r.source.evidence_class==='synthetic')&&!synthetic)fail('Mixed evidence batch');
  const ws=C.empty('Cantos estate collection / '+id);
  await C.put(ws,{id,kind:'source',title:'Estate-captured observations / '+origins[0].slice(0,160),
   summary:batch.length+' normalized rows ('+kinds.join(', ')+') with original source locators, producer provenance, units and evidence classes.',
   tier:synthetic?'synthetic':'public_observation',disposition:'observed',deps:[],
   data:{rows:batch,rows_sha256:sha256(serial),row_count:batch.length,kinds,normalization:'derived common projection',calibration:'not performed',benchmark_executed:false}},actor,at);
  const packet=await C.pack(ws),replayed=await C.verifyPacket(packet);
  if((await C.pack(replayed)).sha256!==packet.sha256)fail('Native replay differs');
  const file=id+'.research-packet.json',body=JSON.stringify(packet),target=path.join(output,file);
  if(fs.existsSync(target)&&fs.readFileSync(target,'utf8')!==body)fail('Different packet at same identity');
  if(!fs.existsSync(target))fs.writeFileSync(target,body);
  index.push({file,sha256:sha256(body),workspace_sha256:packet.sha256,rows:batch.length,origins,kinds,
   first_row_id:batch[0].row_id,last_row_id:batch[batch.length-1].row_id,
   evidence_tier:synthetic?'synthetic':'public_observation',native_replay:'pass'});
  total+=batch.length;batch=[];bytes=0;
 }
 const inputHash=crypto.createHash('sha256');let lastGroup='';
 for await(const line of sourceLines(input,inputHash)){
  if(!line.trim())continue;const row=JSON.parse(line),group=row.source.origin+'|'+row.source.evidence_class;
  if(batch.length&&(batch.length>=MAX_ROWS||bytes+Buffer.byteLength(line)>MAX_BYTES||lastGroup!==group))await emit();
  batch.push(row);bytes+=Buffer.byteLength(line);lastGroup=group;
 }
 await emit();
 const receipt={native_core_sha256:EXPECTED_CORE_SHA256,input_sha256:inputHash.digest('hex'),total_rows:total,packets:index.length,batches:index,
  owner:'corpus/batch_owner.cjs',owner_sha256:sha256(fs.readFileSync(__filename)),actor_label:actor,
  boundary:'Source batches replay through unchanged Research Desk 1.0.0; no synthetic review, inference, benchmark execution or accepted-work measurement.'};
 fs.writeFileSync(path.join(output,'INDEX.json'),JSON.stringify(receipt,null,2));
 process.stdout.write(JSON.stringify({rows:total,packets:index.length,native_core_sha256:EXPECTED_CORE_SHA256,all_replayed:true})+'\n');
}
if(require.main===module)main().catch(e=>{process.stderr.write(String(e?.stack||e)+'\n');process.exitCode=1});
module.exports={sourceLines};
