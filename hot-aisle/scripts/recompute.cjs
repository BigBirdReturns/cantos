#!/usr/bin/env node
/* Recompute a saved report. Optional original result files also bind its normalized data. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const file=process.argv[2];if(!file){console.error('Usage: node scripts/recompute.cjs evidence.json [original-result.json ...]');process.exit(2);}
try{
 const page=fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
 const source=page.match(/<script id="report-engine">([\s\S]*?)<\/script>/);if(!source)throw Error('Workbench engine missing.');
 const sandbox={module:{exports:{}},TextEncoder,Uint8Array,Uint32Array,DataView};vm.runInNewContext(source[1],sandbox);const H=sandbox.module.exports;
 const envelope=JSON.parse(fs.readFileSync(file,'utf8')),p=H.recompute(envelope),provided=process.argv.slice(3),matched=new Set();
 for(const f of provided){const bytes=fs.readFileSync(f),hash=crypto.createHash('sha256').update(bytes).digest('hex'),trials=p.sides.flatMap(s=>s.normalized).filter(r=>r.source.sha256===hash);if(!trials.length)throw Error('An original file does not match any committed input.');
  const docs=H.parseDocuments(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
  for(const trial of trials){if(bytes.length!==trial.source.bytes)throw Error('Original source byte length mismatch.');const actual=H.normalize(docs[trial.source.record_index],trial.source),expected=JSON.parse(JSON.stringify(trial));delete expected.quality;if(H.canonical(actual)!==H.canonical(expected))throw Error('Normalized measurements do not match the committed original source.');matched.add(hash+':'+trial.source.record_index);}
 }
 const required=p.sides.flatMap(s=>s.normalized).map(r=>r.source.sha256+':'+r.source.record_index),missing=required.filter(x=>!matched.has(x));
 if(provided.length&&missing.length)throw Error('Not all original source records were supplied.');
 console.log(JSON.stringify({status:'RECOMPUTED',version:p.version,synthetic:p.synthetic,original_records_checked:matched.size,original_records_total:required.length,originals_status:provided.length?'ALL_PROVIDED_BENCHMARK_BYTES_MATCH':'NOT_SUPPLIED',independent_hardware_rerun:false,source_authenticity_proved:false,evaluation_scope:'Any evaluator pass/fail remains an attributable supplied assertion, not independently adjudicated by this verifier.',results:p.sides.map(s=>({label:s.label,unit:s.aggregate.unit,qualifying_requests:s.aggregate.accepted,cost_per_1000:s.cost.costPer1000})),comparison:p.comparison},null,2));
}catch(e){console.error('NOT VERIFIED: '+e.message);process.exit(2);}
