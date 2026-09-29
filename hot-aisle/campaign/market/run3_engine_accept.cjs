'use strict';
// Price-only recompute helper for the retained Run 3 arms. No CLI exists for a price-only
// recompute of the ledger arms (runner `revalidate` needs a runner qualified record, which
// Run 3 did not produce), so this calls the page's own report engine (index.html #report-engine)
// exactly as campaign/run3/engine_check.cjs does: normalize -> attachQuality -> aggregate -> costing.
//   node run3_engine_accept.cjs            -> JSON {arms:{A_T0:{...},N_T0:{...}}, engine}
//   the engine's costing() is then called for every dated price by economics_by_date.cjs
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const ROOT=path.join(__dirname,'../..');
function engine(){const html=fs.readFileSync(path.join(ROOT,'index.html'),'utf8');const sb={module:{exports:{}},TextEncoder,Uint8Array,Uint32Array,DataView};
  vm.runInNewContext(html.match(/<script id="report-engine">([\s\S]*?)<\/script>/)[1],sb);return sb.module.exports;}
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const ARMS={A_T0:'run3-scored-a-t0',N_T0:'run3-scored-n-t0'};
function arm(H,dir){
  const d=path.join(ROOT,'campaign/results',dir);
  const bytes=fs.readFileSync(path.join(d,'detailed.json'));
  const run=H.normalize(JSON.parse(bytes),{sha256:sha(bytes),record_index:0,bytes:bytes.length});
  const evb=fs.readFileSync(path.join(d,'grade/evaluation.json'));
  const a=H.aggregate([H.attachQuality(run,JSON.parse(evb))],{ttft:1000,e2e:60000,queue:true,quality:true});
  return {dir,detailed_sha256:sha(bytes),evaluation_sha256:sha(evb),attempted:a.attempted,completed:a.completed,accepted:a.accepted,holds:a.holds,window_seconds:a.duration};
}
function load(){const H=engine();const out={};for(const [k,v] of Object.entries(ARMS))out[k]=arm(H,v);return {H,arms:out};}
module.exports={load,ROOT,sha};
if(require.main===module){const {H,arms}=load();console.log(JSON.stringify({engine:H.VERSION,arms},null,1));}
