// Run cell files through the page's own report engine (index.html #report-engine).
//   node campaign/engine_table.cjs <resultsDir> <rate> <ttft_ms> <e2e_ms> [prefix]
'use strict';
const fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
const sb={module:{exports:{}},TextEncoder,Uint8Array,Uint32Array,DataView};
vm.runInNewContext(html.match(/<script id="report-engine">([\s\S]*?)<\/script>/)[1],sb);const H=sb.module.exports;
const [dir,rate,ttftA,e2eA,prefix='cell-']=process.argv.slice(2);const ttft=ttftA===''||ttftA==='-'?null:+ttftA,e2e=e2eA===''||e2eA==='-'?null:+e2eA;
const groups={};
for(const f of fs.readdirSync(dir).filter(f=>f.startsWith(prefix)&&f.endsWith('.json'))){const k=f.replace(/-r\d+\.json$/,'');(groups[k]??=[]).push(f);}
const price={provider:path.basename(dir),gpus:1,rate:+rate,extra:0,source:'list',period:'2026-09-23'};
const out=[];
for(const [k,files] of Object.entries(groups)){
  const runs=files.sort().map((f,i)=>{const b=fs.readFileSync(path.join(dir,f));return H.normalize(JSON.parse(b),{sha256:crypto.createHash('sha256').update(b).digest('hex'),record_index:i,bytes:b.length});});
  const a=H.aggregate(runs,{ttft,e2e});const c=H.costing(a,price);
  out.push({cell:k,runs:a.runs,completed:a.completed,attempted:a.attempted,accepted:a.accepted,accepted_pct:+(100*a.accepted/a.attempted).toFixed(1),accepted_per_s:a.rate==null?null:+a.rate.toFixed(3),holds:a.holds,cost_per_1k:c.costPer1000==null?null:+c.costPer1000.toFixed(4)});
}
out.sort((x,y)=>x.cell.localeCompare(y.cell,undefined,{numeric:true}));
console.log(JSON.stringify({dir:path.basename(dir),rate:+rate,gates:{ttft_ms:ttft,e2e_ms:e2e},engine:H.VERSION,cells:out},null,1));
