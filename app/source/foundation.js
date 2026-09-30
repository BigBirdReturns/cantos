/* Cantos owns presentation and workflow sequencing. ResearchCore owns the journal,
   dependency validity, comparison, reviews, snapshots and packet verification. */
(function(root){'use strict';
const C=root.ResearchCore||(typeof require!=='undefined'?require('./research-core.js'):null);
const actor='Cantos synthetic example author',at='2026-09-28T00:00:00Z';
const meta={id:'cantos-research-preview',version:'0.1.1',basis:'New authored synthetic example; not BEP data or a GPU measurement.',owner:'ResearchCore 1.0.1 candidate',sourceApp:'5951f7f3d994ec980d2958ae18246edc6dbe5b57db8d38e90c1c18956b96e470'};
function record(id,kind,title,summary,data,deps=[]){return {id,kind,title,summary,tier:'synthetic',disposition:kind==='source'?'observed':'draft',data,deps};}
function ref(r){return {id:r.id,revision:r.revision};}
function runData(letter){const A=letter==='A',tasks=[];for(let i=1;i<=24;i++){
 const expected={invoice:'INV-'+String(i).padStart(3,'0'),total:100+i};let output=JSON.stringify(expected),status='ok',elapsed_ms=2000+i*80;
 if(A&&i>12&&i<=22)output='```json\n'+output+'\n```';
 if((A&&i===23)||(!A&&i>=21&&i<=22))output=JSON.stringify({...expected,total:0});
 if(A&&i===24){status='timeout';elapsed_ms=12000;output='';}
 if(!A&&i>=23)elapsed_ms=14000;
 tasks.push({id:'invoice-'+i,expected,attempts:[{status,elapsed_ms,output,cost_usd:null}]});}
 return {schema:'second-run/task-run@1',run_id:'configuration-'+letter.toLowerCase(),label:'Configuration '+letter,evidence:'synthetic',pins:{taskset:'cantos-invoices-24-v1',contract:'extract-invoice-fields-v1',load:'authored-24-items-v1',boundary:'original-task-to-completion'},tasks,billing:{actual_total_usd:null,quote_total_usd:A?2.4:3.6,currency:'USD',scope:'Illustrative complete cost for 24 tasks including failures; not an invoice.'}};
}
async function taskRecompute(ws,stamp){const s=C.state(ws),policy=C.latest(s,'policy'),runs=['run-a','run-b'].map(id=>C.latest(s,id));
 for(const r of [policy,...runs])if(!C.dependencyState(s,r.id).current)throw Error('Resolve the source or contract before recomputing.');
 const comparison=C.compare(runs.map(r=>r.data),policy.data);
 const calc=await C.put(ws,record('calculation','calculation','Cost per accepted original task','Computed by the retained ResearchCore evaluator; all 24 tasks remain in each denominator.',{...comparison,selectedRecordIds:runs.map(r=>r.id),recipe:'task-cost@1'},[ref(policy),...runs.map(ref)]),'Cantos local calculation',stamp);
 const winner=comparison.results.find(r=>r.run_id===comparison.winner);
 const decision=await C.put(ws,record('decision','conclusion','Configuration recommendation',winner?`${winner.label} has the lowest complete quoted cost per accepted task under this version of the contract.`:'No configuration qualifies under the current contract.',{winner:comparison.winner,reason:comparison.blockers,limitations:[meta.basis,'Sample eligibility is not production reliability.','No purchase or execution authority is granted.']},[ref(calc)]),'Cantos local calculation',stamp);
 return decision;
}
async function create(){const ws=C.empty('Cantos / research that can be continued');
 const source=await C.put(ws,record('source','source','24 invoice records / worked example','Two authored configurations process the same 24 fictional invoices. Some outputs are fenced JSON; wrong fields, timeouts and late answers remain in the record.',{...meta,task_count:24,original_data:'Authored fixture, no customer or provider data.'}),actor,at);
 await C.put(ws,record('policy','policy','Acceptance contract','Read the complete JSON response, verify every expected field, and finish within 12 seconds.',{grader:'strict_json',deadline_ms:12000,quality_floor:.5,min_tasks:24,cost_basis:'quote',comparison_mode:'task'},[ref(source)]),actor,at);
 for(const letter of ['A','B'])await C.put(ws,record('run-'+letter.toLowerCase(),'run','Configuration '+letter+' / retained attempts','Original task outputs, cumulative timing and complete quoted cost remain inspectable.',runData(letter),[ref(source)]),actor,at);
 await recompute(ws,at);
 await C.review(ws,'decision','accept','Bundled synthetic baseline edition for demonstrating preserved delivery and a later revision.',actor,at);
 await C.freeze(ws,'decision',actor,at);
 return ws;
}
async function taskView(ws){const s=C.state(ws),policy=C.latest(s,'policy'),calc=C.latest(s,'calculation'),decision=C.latest(s,'decision');
 return {meta,label:ws.label,policy,calc,decision,records:s.records,runs:['run-a','run-b'].map(id=>C.latest(s,id)),current:C.dependencyState(s,'decision'),review:await C.reviewState(s,'decision'),reports:s.reports,events:ws.events,revision:decision.revision,packetHash:(await C.pack(ws)).sha256};
}
async function taskChange(ws,{grader,deadline_ms,costA}){const next=C.clone(ws),s=C.state(next);let changed=false;
 const policy=C.clone(C.latest(s,'policy'));
 if(grader!==undefined&&grader!==policy.data.grader){policy.data.grader=grader;changed=true;}
 if(deadline_ms!==undefined&&deadline_ms!==policy.data.deadline_ms){policy.data.deadline_ms=deadline_ms;changed=true;}
 if(changed){policy.summary=`${policy.data.grader==='extract_json'?'Extract exactly one unambiguous JSON object':'Require the complete response to be JSON'}, match every expected field, and finish within ${policy.data.deadline_ms/1000} seconds.`;await C.put(next,policy,'Local scenario editor');}
 const ra=C.clone(C.latest(C.state(next),'run-a'));
 if(costA!==undefined&&costA!==ra.data.billing.quote_total_usd){if(typeof costA!=='number'||!Number.isFinite(costA)||costA<0)throw Error('Quote must be a finite nonnegative number.');ra.data.billing.quote_total_usd=costA;ra.summary='Illustrative quote revised; original task outputs and timings preserved.';await C.put(next,ra,'Local scenario editor');changed=true;}
 if(!changed)throw Error('Choose a different contract, deadline or quote first.');return next;
}
// ---- Hardware decision class (ResearchCore 1.0.2 candidate: grader 'recorded', cost_basis 'list') ----
// Fixed ids as in the task class: policy, calculation, decision. Arm run ids and source/claim ids are free.
const hwMeta={id:'cantos-hardware-decision',basis:'Retained per-request measurements. A change is an assumption edit; recompute is arithmetic over retained records, no new model run.',owner:'ResearchCore 1.0.2 candidate'};
const hwTiers=['operator_supplied','public_observation','synthetic'];
function decisionClass(ws){const p=C.latest(C.state(ws),'policy');return p?.kind==='policy'&&p.data?.comparison_mode==='hardware'?'hardware':'task';}
function armIds(s){const calc=C.latest(s,'calculation');if(!calc)throw Error('Incomplete hardware workflow: missing calculation.');return calc.deps.map(d=>d.id).filter(id=>C.latest(s,id)?.kind==='run');}
const usd=n=>'$'+n.toFixed(2);
function flipSentence(comparison){const r=comparison.results,w=r.find(x=>x.run_id===comparison.winner);
 if(!w)return 'No arm qualifies under the current policy'+(comparison.blockers.length?' ('+comparison.blockers.join('; ')+')':'')+'.';
 const others=r.filter(x=>x!==w).map(x=>x.identity.arm+' '+(x.cost_per_success===null?'unavailable':usd(x.cost_per_success*1000))+(x.eligible?'':' (ineligible: '+x.blockers.map(b=>b.replace(/\.$/,'')).join('; ')+')')).join(', ');
 return `${w.identity.arm} (${w.identity.hardware}, ${w.identity.vendor}) is the lowest-cost eligible arm per 1,000 accepted: ${usd(w.cost_per_success*1000)} at ${usd(w.rate_usd_per_hour)}/h against ${others}.`;}
async function hwRecompute(ws,stamp){const s=C.state(ws),policy=C.latest(s,'policy'),runs=armIds(s).map(id=>C.latest(s,id));
 for(const r of [policy,...runs])if(!C.dependencyState(s,r.id).current)throw Error('Resolve the source or policy before recomputing.');
 const comparison=C.compare(runs.map(r=>r.data),policy.data),prevCalc=C.latest(s,'calculation'),prevDecision=C.latest(s,'decision');
 const calc=await C.put(ws,{id:'calculation',kind:'calculation',title:prevCalc.title,summary:'Recomputed by the retained ResearchCore evaluator from retained per-request records; arithmetic only, no new model run.',tier:prevCalc.tier,disposition:'draft',data:{...comparison,selectedRecordIds:runs.map(r=>r.id),recipe:'task-cost@1'},deps:[ref(policy),...runs.map(ref)]},'Cantos local calculation',stamp);
 const deps=prevDecision.deps.map(d=>d.id==='calculation'?ref(calc):ref(C.latest(C.state(ws),d.id)));
 const results=comparison.results.map(x=>({run_id:x.run_id,arm:x.identity.arm,accepted:x.accepted,tasks:x.tasks,rate_usd_per_hour:x.rate_usd_per_hour,window_minutes:x.window_minutes,cost_per_1000_accepted:x.cost_per_success===null?null:x.cost_per_success*1000,eligible:x.eligible}));
 return C.put(ws,{id:'decision',kind:'conclusion',title:prevDecision.title,summary:flipSentence(comparison)+' Recomputed from retained measurements; no new model run.',tier:prevDecision.tier,disposition:'draft',data:{winner:comparison.winner,reason:comparison.blockers,results,limitations:prevDecision.data.limitations??[hwMeta.basis]},deps},'Cantos local calculation',stamp);
}
async function hwView(ws){const s=C.state(ws),policy=C.latest(s,'policy'),calc=C.latest(s,'calculation'),decision=C.latest(s,'decision');
 return {meta:hwMeta,decisionClass:'hardware',label:ws.label,policy,calc,decision,records:s.records,runs:armIds(s).map(id=>C.latest(s,id)),current:C.dependencyState(s,'decision'),review:await C.reviewState(s,'decision'),reports:s.reports,events:ws.events,revision:decision.revision,packetHash:(await C.pack(ws)).sha256,flip:flipSentence(calc.data),recompute_basis:hwMeta.basis};
}
function limit(v,label){if(typeof v!=='number'||!Number.isFinite(v)||v<1)throw Error(label+' must be a finite number of at least 1 ms.');}
async function hwChange(ws,opts){const {rates,first_token_ms,deadline_ms}=opts;
 for(const k of Object.keys(opts))if(!['rates','first_token_ms','deadline_ms'].includes(k)&&opts[k]!==undefined)throw Error('The hardware class changes list rates, the first-token limit or the completion deadline only; '+k+' is a task-class field.');
 const next=C.clone(ws);let changed=false;const s=C.state(next),policy=C.clone(C.latest(s,'policy'));
 if(first_token_ms!==undefined){limit(first_token_ms,'First-token limit');if(first_token_ms!==policy.data.first_token_ms){policy.data.first_token_ms=first_token_ms;changed=true;}}
 if(deadline_ms!==undefined){limit(deadline_ms,'Completion deadline');if(deadline_ms!==policy.data.deadline_ms){policy.data.deadline_ms=deadline_ms;changed=true;}}
 if(changed){policy.summary=`Accepted = recorded correct, first token within ${policy.data.first_token_ms} ms and completion within ${policy.data.deadline_ms/1000} s of scheduled arrival (assumption edit over retained measurements).`;await C.put(next,policy,'Local scenario editor');}
 if(rates!==undefined){if(rates===null||typeof rates!=='object'||Array.isArray(rates))throw Error('Rates must map an arm to a list rate in USD per hour.');
  const arms=armIds(C.state(next)).map(id=>C.latest(C.state(next),id));
  for(const [key,rate] of Object.entries(rates)){const run=arms.find(r=>r.id===key)||arms.find(r=>r.data.run_id===key);if(!run)throw Error('Unknown arm: '+key+'.');if(typeof rate!=='number'||!Number.isFinite(rate)||rate<0)throw Error('List rate must be a finite nonnegative number.');
   if(rate===run.data.billing.rate_usd_per_hour)continue;const r=C.clone(C.latest(C.state(next),run.id));const was=r.data.billing.rate_usd_per_hour;r.data.billing.rate_usd_per_hour=rate;r.summary=`Rate scenario: ${usd(rate)}/h replaces ${usd(was)}/h (assumption edit). Retained requests, timings and grades unchanged; no new model run.`;await C.put(next,r,'Local scenario editor');changed=true;}}
 if(!changed)throw Error('Choose a different list rate, first-token limit or completion deadline first.');return next;
}
function hwWorkflow(ws){const s=C.state(ws);
 for(const event of ws.events){if(event.type!=='record')continue;const r=event.payload;
  if(!['source','claim','policy','run','calculation','conclusion'].includes(r.kind)||!hwTiers.includes(r.tier))throw Error('Unsupported evidence or record type for the hardware decision workflow.');
  if((r.id==='policy')!==(r.kind==='policy')||(r.id==='calculation')!==(r.kind==='calculation')||(r.id==='decision')!==(r.kind==='conclusion'))throw Error('Unsupported record id for '+r.id+': the hardware workflow uses policy, calculation and decision.');
  const depKinds=r.deps.map(d=>C.version(s,d.id,d.revision).kind);
  if(['source','claim','policy','run'].includes(r.kind)&&depKinds.some(k=>!['source','claim'].includes(k)))throw Error('Unsupported dependency topology for '+r.id+'. The prior workspace remains unchanged.');
  if(r.kind==='policy'&&(r.data.comparison_mode!=='hardware'||r.data.grader!=='recorded'))throw Error('A workspace cannot change decision class.');
  if(r.kind==='run'){C.validateRun(r.data);if(r.data.identity===undefined)throw Error('Hardware runs must be arm records with identity.');}
  if(r.kind==='conclusion'){const calcs=r.deps.filter(d=>d.id==='calculation');if(calcs.length!==1||depKinds.some(k=>!['calculation','source','claim'].includes(k)))throw Error('Unsupported dependency topology for decision. The prior workspace remains unchanged.');
   if(r.data.winner!==C.version(s,'calculation',calcs[0].revision).data.winner)throw Error('Decision winner differs from its pinned calculation.');}
 }
 for(const [id,kind] of [['policy','policy'],['calculation','calculation'],['decision','conclusion']])if(C.latest(s,id)?.kind!==kind)throw Error('Incomplete hardware workflow: missing '+id+'.');
 const arms=armIds(s);if(arms.length<2)throw Error('The hardware workflow compares at least two arms.');
 for(const id of Object.keys(s.records))if(s.records[id][0].kind==='run'&&!arms.includes(id))throw Error('Run '+id+' is not pinned by the calculation.');
 for(const freeze of s.reports){const keys=Object.keys(freeze.snapshot.records);if(freeze.target!=='decision'||!['policy','calculation','decision'].every(k=>keys.includes(k)))throw Error('Retained edition does not contain the complete hardware decision workflow.');}
 return ws;
}
// ---- Class dispatch. The task class keeps its exact 0.4.1 behaviour. ----
async function recompute(ws,stamp){return decisionClass(ws)==='hardware'?hwRecompute(ws,stamp):taskRecompute(ws,stamp);}
async function view(ws){return decisionClass(ws)==='hardware'?hwView(ws):{...await taskView(ws),decisionClass:'task'};}
async function change(ws,opts={}){if(decisionClass(ws)==='hardware')return hwChange(ws,opts);
 for(const k of ['rates','first_token_ms'])if(opts[k]!==undefined)throw Error('List rates and the first-token limit apply to the hardware class only.');
 return taskChange(ws,opts);}
function workflow(ws){return decisionClass(ws)==='hardware'?hwWorkflow(ws):taskWorkflow(ws);}
async function reviewed(ws,name,rationale){if(!name.trim())throw Error('Enter a reviewer name.');if(rationale.trim().length<12)throw Error('Record a review rationale of at least 12 characters.');const next=C.clone(ws);await C.review(next,'decision','accept',rationale.trim(),name.trim());return next;}
async function sealed(ws,name){const next=C.clone(ws);const s=C.state(next),v=await C.reviewState(s,'decision');if(s.reports.some(r=>r.fingerprint===v.fingerprint))throw Error('This exact decision already has a retained edition.');await C.freeze(next,'decision',name||v.review?.reviewer||'Local reviewer');return next;}
// A valid Research Desk packet may still be outside this page's supported workflow.
function taskWorkflow(ws){
 const expected={source:'source',policy:'policy','run-a':'run','run-b':'run',calculation:'calculation',decision:'conclusion'};
 const deps={source:[],policy:['source'],'run-a':['source'],'run-b':['source'],calculation:['policy','run-a','run-b'],decision:['calculation']};
 const s=C.state(ws);
 for(const event of ws.events){
  if(event.type!=='record')continue;
  const r=event.payload;
  if(expected[r.id]!==r.kind||r.tier!=='synthetic')throw Error('Unsupported evidence or record type: this page accepts only the complete synthetic Cantos workflow.');
  if(C.canonical(r.deps.map(d=>d.id).sort())!==C.canonical([...deps[r.id]].sort()))throw Error('Unsupported dependency topology for '+r.id+'. The prior workspace remains unchanged.');
  if(r.id==='source'&&(r.data.id!==meta.id||r.data.task_count!==24))throw Error('Unsupported synthetic source population.');
  if(r.kind==='run'){
   C.validateRun(r.data);
   const expectedId=r.id==='run-a'?'configuration-a':'configuration-b';
   if(r.data.evidence!=='synthetic'||r.data.run_id!==expectedId||r.data.tasks.length!==24)throw Error('Unsupported run population or evidence class.');
   if(r.data.billing.quote_total_usd===null)throw Error('This worked-example page requires complete synthetic quotes. Use Research Desk for missing-cost cases.');
   if(C.canonical(r.data.tasks.map(t=>t.id).sort())!==C.canonical(Array.from({length:24},(_,i)=>'invoice-'+(i+1)).sort()))throw Error('Unsupported original task identities.');
  }
  if(r.kind==='conclusion'){
   const d=r.deps[0],calculation=C.version(s,d.id,d.revision);
   if(r.data.winner!==calculation.data.winner)throw Error('Decision winner differs from its pinned calculation.');
  }
 }
 for(const [id,kind] of Object.entries(expected))if(C.latest(s,id)?.kind!==kind)throw Error('Incomplete Cantos workflow: missing '+id+'.');
 for(const freeze of s.reports){
  if(freeze.target!=='decision'||C.canonical(Object.keys(freeze.snapshot.records).sort())!==C.canonical(Object.keys(expected).sort()))throw Error('Retained edition does not contain the complete Cantos decision workflow.');
 }
 return ws;
}
async function restore(packet){return workflow(await C.verifyPacket(packet));}
async function correctSource(ws){const next=C.clone(ws),st=C.state(next),key=st.records.source?'source':Object.keys(st.records).find(k=>st.records[k][0].kind==='source'),src=C.clone(C.latest(st,key));src.summary+=' This scenario marks the source as withdrawn.';src.disposition='withdrawn';await C.put(next,src,'Local source-withdrawal scenario');return next;}
root.CantosDesk={meta,hwMeta,decisionClass,create,view,workflow,change,recompute,reviewed,sealed,restore,correctSource,pack:C.pack,core:C};if(typeof module!=='undefined')module.exports=root.CantosDesk;
})(typeof globalThis!=='undefined'?globalThis:this);
