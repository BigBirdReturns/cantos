'use strict';
// Read-only projection. Network refresh is an explicit, separate Python command.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const MAX=2*1024*1024;
function read(p){const s=fs.lstatSync(p);if(s.isSymbolicLink()||!s.isFile()||s.size>MAX)throw Error('Material input outside file policy.');const b=fs.readFileSync(p);if(b.length>MAX)throw Error('Material input exceeds read budget.');return b;}
function inspect(root, args={}, clock=Date.now()){
 const rb=read(path.join(root,'materials/registry.json')),registry=JSON.parse(rb);
 if(registry.schema!=='second-run/material-registry@1')throw Error('Unknown material registry.');
 const rh=crypto.createHash('sha256').update(rb).digest('hex');
 let snapshot=null,error=null;
 try{snapshot=JSON.parse(read(path.join(root,'materials/observations.json')));
  if(snapshot.schema!=='second-run/material-observations@1'||snapshot.registry_sha256!==rh)throw Error('Observation registry identity mismatch.');
  if(!Number.isFinite(Date.parse(snapshot.collected_at))||Date.parse(snapshot.collected_at)>clock)throw Error('Observation time invalid or in the future.');
 }catch(e){snapshot=null;error=e.message;}
 if(args.recipe&&!registry.recipes.some(r=>r.id===args.recipe))throw Error('Unknown recipe.');
 if(args.layer&&!registry.sources.some(r=>r.layer===args.layer))throw Error('Unknown layer.');
 const recipes=registry.recipes.filter(r=>!args.recipe||r.id===args.recipe);
 const needed=new Set(recipes.flatMap(r=>r.sources));
 const byId=new Map((snapshot?.observations||[]).map(r=>[r.id,r]));
 const sources=registry.sources.filter(s=>needed.has(s.id)&&(!args.layer||s.layer===args.layer)).map(s=>{
  const o=byId.get(s.id),g=o?.last_good;let state='UNOBSERVED';
  if(o?.url!==s.url&&o)state='SOURCE_MISMATCH';
  else if(o?.status==='UNAVAILABLE')state='READ_FAILED';
  else if(g){const t=Date.parse(g.observed_at),e=Date.parse(g.expires_at);
   if(!Number.isFinite(t)||!Number.isFinite(e)||t>clock||e<=t)state='INVALID_TIME';
   else state=clock>=e?'STALE':'OBSERVED';
  }
  return {...s,observation_state:state,change:o?.change||'UNKNOWN',last_good:g||null,next_action:o?.next_action||s.on_change};
 });
 return {schema:'second-run/material-view@1',registry_sha256:rh,as_of:new Date(clock).toISOString(),
  snapshot_status:snapshot?'READ':'UNAVAILABLE',snapshot_error:error,
  sources,recipes,operator_shapes:registry.operator_shapes.filter(x=>x.materials.some(id=>sources.some(s=>s.id===id))),
  actions_permitted:['inspect sources','prepare a bounded qualification','reprice using separately verified quotes'],
  actions_not_granted:['provision','execute','install','change client settings','read secrets','promote route','reuse across tenants'],
  boundary:registry.boundary};
}
module.exports={inspect};
if(require.main===module){try{console.log(JSON.stringify(inspect(path.resolve(__dirname,'..'),{recipe:process.argv[2]||undefined}),null,2));}catch(e){console.error(e.message);process.exitCode=2;}}
