#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),crypto=require('node:crypto'),A=require('./capacity.cjs');
function verifyFile(path){
 const stat=fs.statSync(path);if(!stat.isFile()||stat.size>150000)throw Error('Use a decision JSON file no larger than 150 KB.');
 const p=JSON.parse(fs.readFileSync(path,'utf8'));
 if(!p||typeof p!=='object'||Array.isArray(p)||Object.keys(p).sort().join(',')!=='body_json,schema,sha256'||p.schema!==A.PACKET||typeof p.body_json!=='string'||p.body_json.length>100000||!/^[a-f0-9]{64}$/.test(p.sha256))throw Error('Unsupported decision packet.');
 const actual=crypto.createHash('sha256').update(p.body_json,'utf8').digest('hex');
 if(actual!==p.sha256)throw Error('Checksum mismatch.');
 const b=A.verifyBody(JSON.parse(p.body_json));
 return {status:'PASS',checks:['SHA-256 of retained body bytes','Complete projection recomputed through the pinned Compute engine and candidate adapter'],sha256:p.sha256,parent_checksum:b.parent_checksum,modeled_accepted:b.result.modeled_accepted,known_cost_total:b.result.known_cost_total,unknown_costs:b.result.unknown_costs,source_authenticity_verified:false,target_performance_verified:false,signature_verified:false,ancestor_presence_verified:false,limits:'Unsigned scenario. Arithmetic and internal consistency do not establish source truth, legal jurisdiction or execution.'};
}
if(require.main===module){try{if(process.argv.length!==3)throw Error('Usage: node verify.cjs decision.json');console.log(JSON.stringify(verifyFile(process.argv[2]),null,2));}catch(e){console.error(JSON.stringify({status:'FAIL',reason:e.message}));process.exitCode=1;}}
module.exports={verifyFile};
