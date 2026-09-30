'use strict';
const D=CantosDesk,C=D.core,$=id=>document.getElementById(id),KEY='cantos.research-preview.v0.1',money=n=>n===null?'Unavailable':'$'+n.toFixed(2);
let workspace,viewState,busy=false,lastInputs='',persist=false,pendingImport=null,savedHash=null;
const escapeHTML=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notice(message,error=false){$('notice').textContent=message;$('notice').classList.toggle('error',error);}
function download(name,text,type='application/json'){const blob=new Blob([text],{type}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
// The analytical owner is unchanged. This layer prepares a complete detached
// display, then commits state and its visible representation in the same callback.
let transition=null;
async function installPrepared(candidate,prepared,options={}){
 const swap=()=>{
  const previousMain=document.querySelector('main');
  const focusId=document.activeElement?.id;
  const scrolls=['workspace'].map(id=>[id,$(id)?.scrollTop||0]);
  if(workspace&&!options.resetFields){
   for(const id of ['reviewer','rationale','grader','deadline','quote']){
    const old=$(id),next=prepared.node.querySelector('#'+id);
    if(old&&next)next.value=old.value;
   }
  }
  let saved=options.persist===undefined?persist:options.persist,saveFailed=false;
  if(options.resetStorage)localStorage.removeItem(KEY);
  if(options.save){try{localStorage.setItem(KEY,prepared.packetJSON);}catch(e){saved=false;saveFailed=true;}}
  prepared.node.querySelector('#save-btn').textContent=saved?'Saved on this device':'Save on this device';
  prepared.node.querySelector('#storage-status').textContent=saved?'Saved on this device · export for portability':'In memory · save or export to retain';
  const before=snapshotNums(document);
  previousMain.replaceWith(prepared.node);
  workspace=candidate;viewState=prepared.v;persist=saved;
  animateNums(before);
  if(options.resetStorage)savedHash=null;
  if(options.save&&!saveFailed)savedHash=prepared.v.packetHash;
  window.CantosPreviewState=prepared.publicState;
  for(const [id,top] of scrolls)if($(id))$(id).scrollTop=top;
  if(focusId&&$(focusId)&&!$(focusId).disabled)$(focusId).focus({preventScroll:true});
  prepared.saveFailed=saveFailed;
 };
 if(document.startViewTransition&&workspace&&!matchMedia('(prefers-reduced-motion: reduce)').matches){
  if(transition)transition.skipTransition();
  transition=document.startViewTransition(swap);
  // A new click can run after the atomic swap; animation never owns the input path.
  await transition.updateCallbackDone;
 }else swap();
 return prepared;
}
async function render(){await installPrepared(workspace,await prepareView(workspace));}
async function transact(fn,message){
 if(busy){notice('Completing the current operation.');return;}
 busy=true;
 try{
  const next=await fn(C.clone(workspace));if(!next)return;
  const prepared=await prepareView(next);
  await installPrepared(next,prepared,{save:persist});
  notice(prepared.saveFailed?'Work updated in memory; local save failed. The previous saved copy is unchanged. Export to keep these changes.':message,prepared.saveFailed);
 }catch(e){notice((e.message||String(e))+' Current workspace was preserved.',true);}
 finally{busy=false;}
}
function calculationInputs(candidate,v){
 const s=C.state(candidate),refs=v.calc.deps;
 return {policy:C.version(s,'policy',refs.find(x=>x.id==='policy').revision),
  runs:['run-a','run-b'].map(id=>C.version(s,id,refs.find(x=>x.id===id).revision))};
}
function taskKind(task,result,policy){
 if(result.accepted)return {kind:'accepted',label:'Accepted'};
 if(result.quality||!task.attempts.some(a=>a.status==='ok'))return {kind:'late',label:'Late or incomplete'};
 if(policy.grader==='strict_json'&&task.attempts.some(a=>a.status==='ok'&&C.grade(a.output,task.expected,'extract_json')))return {kind:'format',label:'JSON wrapper rejected'};
 return {kind:'wrong',label:'Required fields do not match'};
}
async function prepareView(candidate){
 D.workflow(candidate);
 const v=await D.view(candidate),main=document.querySelector('main').cloneNode(true),$=id=>main.querySelector('#'+id);
 const calc=v.calc.data,current=v.current.current,winner=calc.results.find(r=>r.run_id===calc.winner),frozen=v.reports.some(r=>r.fingerprint===v.review.fingerprint);
 const pinned=calculationInputs(candidate,v);
 $('winner').textContent=current?(winner?.label||'No eligible result'):'Decision needs updating';
 $('decision-kicker').textContent=current?'LOWEST COST / ACCEPTED INVOICE':'CHANGED INPUT / PREVIOUS RESULT RETAINED';
 $('decision-summary').textContent=current?(winner?'The lower complete cost for work that meets this contract.':'No configuration meets the current acceptance contract.'):'The comparison below belongs to the previous contract.';
 const status=$('current-state');status.textContent=!current?'STALE':frozen?'RETAINED EDITION':v.review.ready?'REVIEWED':'DRAFT';status.className='state '+(!current?'stale':!frozen?'draft':'');
 $('policy-version').textContent='v'+v.policy.revision;
 for(const id of ['calc-node','decision-node'])$(id).classList.toggle('stale',!current);
 const alternative=winner&&calc.results.find(r=>r.run_id!==winner.run_id&&r.eligible);
 const reduction=alternative&&alternative.cost_per_success>0?Math.round(100*(1-winner.cost_per_success/alternative.cost_per_success)):null;
 $('advantage').innerHTML=current&&reduction!==null&&reduction>0?'<strong>↓ '+reduction+'%</strong>cost / accepted':'';
 $('comparison').innerHTML=calc.results.map((r,index)=>{
  const run=pinned.runs[index].data,results=new Map(r.rows.map(x=>[x.id,x]));
  const cells=run.tasks.map((t,i)=>{const k=taskKind(t,results.get(t.id),pinned.policy.data);return `<button type="button" class="task-cell ${k.kind}" style="--vt:cell-${index?'b':'a'}-${i+1}" data-run="${index}" data-task="${i}" title="Invoice ${i+1} · ${escapeHTML(k.label)}" aria-label="Configuration ${index?'B':'A'}, invoice ${i+1}: ${escapeHTML(k.label)}">${String(i+1).padStart(2,'0')}</button>`;}).join('');
  return `<article class="comp-row ${r.run_id===calc.winner?'winner':''}" data-configuration="${index?'B':'A'}"><div class="comp-header"><span class="config-id"><b>${index?'B':'A'}</b>Configuration ${index?'B':'A'}</span>${r.run_id===calc.winner?'<span class="tag">'+(current?'PREFERRED':'PRIOR RESULT')+'</span>':''}</div><div class="comp-price"><strong class="comp-value">${money(r.cost_per_success)}</strong><small>/ accepted invoice</small></div><div class="comp-stats"><strong>${r.accepted}<small> / ${r.tasks}</small></strong><span>accepted</span></div><div class="bar"><span style="width:${100*r.accepted/r.tasks}%"></span></div><div class="task-matrix">${cells}</div><div class="comp-footer"><span>${money(r.total_usd)} full quote</span><button class="text-button" data-inspect="run-${index?'b':'a'}">Inspect ${index?'B':'A'}</button></div>${r.blockers.length?'<p class="field-note">'+escapeHTML(r.blockers.join(' '))+'</p>':''}</article>`;
 }).join('');
 const summary=$('change-summary');summary.hidden=current;summary.textContent=v.current.blockers.join(' · ');
 const sourceCurrent=C.dependencyState(C.state(candidate),'source').current;
 $('recompute-btn').disabled=current||!sourceCurrent;
 $('review-btn').disabled=!current;$('freeze-btn').disabled=!current||!v.review.ready||frozen;
 $('next-step-note').textContent=!sourceCurrent?'Source withdrawn. Earlier editions remain available.':!current?'Update only the dependent calculation.':!frozen&&!v.review.ready?'Review the new decision in the scenario panel.':v.review.ready&&!frozen?'Retain the reviewed successor.':'Change a requirement to compare another scenario.';
 $('review-status').textContent=!current?'Update the decision before reviewing.':frozen?'This version is retained.':v.review.ready?'Reviewed. Ready to retain.':'New decision. Record your reasoning before retaining.';
 $('review-light').style.background=v.review.ready?'var(--accepted)':'var(--dim)';
 $('grader').value=v.policy.data.grader;$('deadline').value=String(v.policy.data.deadline_ms);$('quote').value=v.runs[0].data.billing.quote_total_usd.toFixed(2);
 $('consumer-caption').textContent=v.policy.data.grader==='strict_json'?'10 correct answers have a wrapper.':'One extracted object is permitted.';
 $('history-count').textContent=String(v.reports.length).padStart(2,'0');
 $('editions').innerHTML=v.reports.map((r,i)=>{
  const parts=snapshotParts(r),w=parts.calc.data.results.find(x=>x.run_id===parts.calc.data.winner),same=r.fingerprint===v.review.fingerprint;
  return `<article class="edition ${same?'current-edition':''}"><header><h3>Edition ${String(i+1).padStart(2,'0')} · ${escapeHTML(w?.label||'No recommendation')}</h3><span class="tag">${same?'CURRENT':'HISTORY'}</span></header><p>${escapeHTML(parts.policy.data.grader==='strict_json'?'Raw JSON':'Extract one object')} · ${parts.policy.data.deadline_ms/1000}s · ${w?money(w.cost_per_success)+'/accepted':'No eligible result'}</p>${i?'<p class="successor-line">Supersedes Edition '+String(i).padStart(2,'0')+' · '+v.reports[i-1].snapshot_hash.slice(0,12)+'…</p>':''}<div class="edition-bottom"><code>${r.snapshot_hash.slice(0,12)}…</code><span><button class="text-button" data-edition="${i}">Compare</button> · <button class="text-button" data-brief="${i}">Brief</button></span></div></article>`;
 }).join('');
 $('storage-status').textContent=persist?'Saved on this device · export for portability':'In memory · save or export to retain';
 $('save-btn').textContent=persist?'Saved on this device':'Save on this device';
 const publicState={current,reportCount:v.reports.length,winner:calc.winner,packetHash:v.packetHash,events:v.events.length,sourceDisposition:C.latest(C.state(candidate),'source').disposition};
 $('outcome-diff').textContent=outcomeExplanation(v);
 return {node:main,v,publicState,packetJSON:JSON.stringify(await D.pack(candidate))};
}
function openInspector(title,meta,readable,raw){
 $('inspector-title').textContent=title;$('inspector-meta').textContent=meta;
 $('inspector-readable').innerHTML=readable;
 $('inspector-body').textContent=JSON.stringify(raw,null,2);$('inspector-body').hidden=false;
 $('inspector').querySelector('.raw-details').open=false;
 $('inspector').showModal();
}
function inspectTask(runIndex,index){
 const inputs=calculationInputs(workspace,viewState),run=inputs.runs[runIndex],task=run.data.tasks[index];if(!task)return;
 const result=viewState.calc.data.results[runIndex].rows.find(r=>r.id===task.id),k=taskKind(task,result,inputs.policy.data),a=task.attempts.at(-1);
 const readable='<div class="inspection-facts"><div><small>NATIVE RESULT</small><strong>'+escapeHTML(k.label)+'</strong></div><div><small>ELAPSED</small><strong>'+a.elapsed_ms/1000+'s / '+inputs.policy.data.deadline_ms/1000+'s</strong></div><div><small>FORMAT RULE</small><strong>'+escapeHTML(inputs.policy.data.grader==='strict_json'?'Raw JSON':'Extract one object')+'</strong></div></div><div class="output-compare"><div><span>Required fields</span><pre>'+escapeHTML(JSON.stringify(task.expected,null,2))+'</pre></div><div><span>Retained answer</span><pre>'+escapeHTML(a.output||'[No completed output]')+'</pre></div></div><p class="inspection-note">'+(k.kind==='format'?'The required fields are present inside a Markdown fence. This contract requires the whole answer to be JSON.':k.kind==='accepted'?'The native evaluator accepted the required fields within the recorded deadline.':k.kind==='wrong'?'The output does not match all required fields under this contract.':'A correct value is insufficient when the task is late or incomplete.')+'</p>';
 openInspector('Invoice '+String(index+1).padStart(2,'0')+' · Configuration '+(runIndex?'B':'A'),'Retained result under contract v'+inputs.policy.revision+' · synthetic',readable,{task,policy:inputs.policy.data,result});
}
function inspect(id){
 const s=C.state(workspace),r=C.latest(s,id);if(!r)return;
 const dep=C.dependencyState(s,id);let html='<p>'+escapeHTML(r.summary)+'</p>';
 if(id==='source')html+='<div class="inspection-facts"><div><small>ORIGINAL TASKS</small><strong>24</strong></div><div><small>EVIDENCE</small><strong>Synthetic</strong></div><div><small>STATE</small><strong>'+escapeHTML(r.disposition)+'</strong></div></div><button id="withdraw-source" class="outline-button mini-danger"'+(r.disposition==='withdrawn'?' disabled':'')+'>Withdraw this example source</button>';
 if(id==='run-a'||id==='run-b'){const i=id==='run-a'?0:1;html+='<div class="inspection-facts"><div><small>ORIGINAL TASKS</small><strong>'+r.data.tasks.length+'</strong></div><div><small>FULL QUOTE</small><strong>'+money(r.data.billing.quote_total_usd)+'</strong></div><div><small>EVIDENCE</small><strong>Synthetic</strong></div></div><button class="outline-button" data-inspector-task="12" data-run="'+i+'">Inspect answer 13</button>';}
 if(id==='policy')html+='<div class="inspection-facts"><div><small>FORMAT</small><strong>'+escapeHTML(r.data.grader)+'</strong></div><div><small>DEADLINE</small><strong>'+r.data.deadline_ms/1000+'s</strong></div><div><small>COST BASIS</small><strong>'+escapeHTML(r.data.cost_basis)+'</strong></div></div>';
 if(id==='calculation')html+=comparisonTable(r.data.results);
 openInspector(r.title,r.id+' · v'+r.revision+' · '+r.tier+' · '+(dep.current?'Current dependencies':'Changed dependencies'),html,r);
}
function comparisonTable(results){return '<table><thead><tr><th>Configuration</th><th>Accepted / original</th><th>Cost / accepted</th></tr></thead><tbody>'+results.map(r=>'<tr><td>'+escapeHTML(r.label)+'</td><td>'+r.accepted+' / '+r.tasks+'</td><td>'+money(r.cost_per_success)+'</td></tr>').join('')+'</tbody></table>';}
function snapshotParts(r){const records=Object.values(r.snapshot.records);return {calc:records.find(x=>x.kind==='calculation'),policy:records.find(x=>x.kind==='policy')};}
function editionDifference(r,prior){
 if(!prior)return 'Fixed synthetic starting edition.';
 const a=snapshotParts(prior),b=snapshotParts(r);
 return 'Contract '+a.policy.data.grader+' → '+b.policy.data.grader+'; deadline '+a.policy.data.deadline_ms/1000+' → '+b.policy.data.deadline_ms/1000+' seconds. '+b.calc.data.results.map(x=>{const old=a.calc.data.results.find(y=>y.run_id===x.run_id);return x.label+': '+old.accepted+' → '+x.accepted+' of '+x.tasks+' accepted.';}).join(' ');
}
function outcomeExplanation(v){
 if(!v.current.current)return 'Changed requirement. Earlier results stay visible until you recompute.';
 const previous=v.reports.findLast(r=>r.snapshot.records.calculation.revision!==v.calc.revision);
 if(!previous)return 'B accepts 20 invoices; A accepts 12. The purple tiles are correct answers whose JSON wrapper fails this contract.';
 const a=snapshotParts(previous),run=v.runs[0].data,policy=v.policy.data;
 const fenced=run.tasks.filter(t=>t.attempts.some(x=>x.status==='ok'&&x.elapsed_ms<=policy.deadline_ms&&x.output.includes('```')&&C.grade(x.output,t.expected,'extract_json')&&!C.grade(x.output,t.expected,'strict_json'))).length;
 const counts=v.calc.data.results.map(r=>{const old=a.calc.data.results.find(x=>x.run_id===r.run_id);return r.label.replace('Configuration ','')+': '+old.accepted+' → '+r.accepted;}).join(' · ');
 return (a.policy.data.grader!==policy.grader&&policy.grader==='extract_json'?fenced+' of A’s fenced answers now pass both fields and deadline. ':'')+counts+'. Outputs and timings unchanged.';
}
function inspectEdition(i){
 const r=viewState.reports[i],parts=snapshotParts(r),prev=viewState.reports[i-1];
 $('inspector-title').textContent='Retained edition '+(i+1);$('inspector-meta').textContent='Immutable snapshot · '+r.snapshot_hash;
 $('inspector-readable').innerHTML='<p>'+escapeHTML(r.snapshot.records[r.target].summary)+'</p><p>'+escapeHTML(editionDifference(r,prev))+'</p><table><thead><tr><th>Configuration</th><th>Accepted / tasks</th><th>Cost / accepted</th></tr></thead><tbody>'+parts.calc.data.results.map(x=>'<tr><td>'+escapeHTML(x.label)+'</td><td>'+x.accepted+' / '+x.tasks+'</td><td>'+money(x.cost_per_success)+'</td></tr>').join('')+'</tbody></table><p>Review: '+escapeHTML(r.snapshot.review.reviewer)+' · '+escapeHTML(r.snapshot.review.rationale)+'</p><p>The full native snapshot follows.</p>';
 $('inspector-body').hidden=false;$('inspector-body').textContent=JSON.stringify(r.snapshot,null,2);$('inspector').querySelector('.raw-details').open=false;$('inspector').showModal();
}
function brief(i){const r=viewState.reports[i],s=r.snapshot,rows=Object.values(s.records),calc=rows.find(x=>x.kind==='calculation'),p=rows.find(x=>x.kind==='policy');const html=`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none';style-src 'unsafe-inline';base-uri 'none'"><title>Cantos research edition ${i+1}</title><style>body{font:16px/1.65 system-ui;max-width:850px;margin:45px auto;padding:0 24px;color:#18232c}h1{font:42px Georgia}table{border-collapse:collapse;width:100%}td,th{padding:12px;text-align:left;border-bottom:1px solid #ddd}.boundary{padding:15px;background:#f2ead8}code{overflow-wrap:anywhere}small{color:#55616a}</style><body><small>CANTOS / SECOND RUN / EDITION ${i+1}</small><h1>${escapeHTML(s.records[s.target].title)}</h1><p class="boundary">Synthetic worked example. No BEP data, production performance, client endorsement or purchase authority.</p><p>${escapeHTML(s.records[s.target].summary)}</p><h2>Calculation</h2><table><thead><tr><th>Configuration</th><th>Accepted / tasks</th><th>Complete quote</th><th>Cost / accepted</th></tr></thead><tbody>${calc.data.results.map(x=>`<tr><td>${escapeHTML(x.label)}</td><td>${x.accepted} / ${x.tasks}</td><td>${money(x.total_usd)}</td><td>${money(x.cost_per_success)}</td></tr>`).join('')}</tbody></table><p>Contract: ${escapeHTML(p.data.grader)}; deadline ${p.data.deadline_ms/1000} seconds; cost basis ${escapeHTML(p.data.cost_basis)}.</p><h2>Edition history</h2><p>${escapeHTML(editionDifference(r,viewState.reports[i-1]))}</p>${i?'<p>Supersedes Edition '+i+' · '+viewState.reports[i-1].snapshot_hash+'</p>':''}<h2>Recorded review</h2><p>${escapeHTML(s.review.reviewer)} · ${escapeHTML(s.review.at)}</p><p>${escapeHTML(s.review.rationale)}</p><h2>Retained identity</h2><code>${r.snapshot_hash}</code><p>This document is a readable projection. Export the workspace packet for the complete journal, source records and native recomputation. A checksum is not source authentication.</p></body></html>`;download('Cantos-research-edition-'+(i+1)+'.html',html,'text/html');notice('The retained edition was exported. Its original snapshot is unchanged.');}
function view(name){
 if(!['decision','evidence','architecture'].includes(name))return;
 setControls(false);
 for(const n of ['decision','evidence','architecture'])$(n+'-view').hidden=n!==name;
 document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('active',b.dataset.view===name));
 document.querySelector('.workspace-name').innerHTML=name==='decision'?'Research decision <span class="tag">SYNTHETIC EXAMPLE</span>':name==='evidence'?'GPU inference <span class="tag">RETAINED EXPERIMENT</span>':'Cantos / Second Run <span class="tag">SYSTEM MAP</span>';
 document.querySelector('.toolbar-actions').hidden=name!=='decision';document.querySelector('.rail-section').hidden=name!=='decision';
 notice(name==='evidence'?'Run 3 · historical measurement · list-price accounting.':name==='architecture'?'The page and estate components retain separate owners.':'Invoice laboratory · select a task to inspect its retained answer.');
}
function setControls(open){
 const main=document.querySelector('main'),panel=$('scenario-panel');
 main.classList.toggle('controls-open',Boolean(open));$('mobile-scenario').setAttribute('aria-expanded',String(Boolean(open)));
 if(open&&matchMedia('(max-width:720px)').matches){panel.setAttribute('role','dialog');panel.setAttribute('aria-modal','true');$('grader').focus();}
 else {panel.removeAttribute('role');panel.removeAttribute('aria-modal');if(document.activeElement?.closest('#scenario-panel'))$('mobile-scenario').focus({preventScroll:true});}
}

async function exportCurrent(){const packet=await D.pack(workspace);download('Cantos-research-workspace.json',JSON.stringify(packet,null,2));notice('Exported the actual committed workspace, including its evidence, reviews and editions.');}
async function importFile(file){
 if(!file)return;
 if(busy||pendingImport){notice('Finish the current operation before opening another packet.',true);return;}
 busy=true;
 try{
  if(file.size>12000000)throw Error('File exceeds the 12 MB import limit.');
  const candidate=await D.restore(C.parse(await file.text()));
  const prepared=await prepareView(candidate);
  if(prepared.v.packetHash===viewState.packetHash){notice('Packet verified. It is identical to the current workspace.');return;}
  pendingImport={candidate,baseHash:viewState.packetHash};
  $('import-dialog').showModal();
 }catch(e){notice('Import refused: '+e.message+' Current work was preserved.',true);}
 finally{busy=false;$('packet-file').value='';}
}
async function confirmImport(){
 if(!pendingImport||busy)return;busy=true;
 try{
  if(pendingImport.baseHash!==(await D.pack(workspace)).sha256)throw Error('Current work changed while confirmation was open. Reopen the packet.');
  const next=await D.restore(await D.pack(pendingImport.candidate));
  const prepared=await prepareView(next);
  await installPrepared(next,prepared,{persist:false,resetFields:true});pendingImport=null;$('import-dialog').close();
  notice('Verified workspace restored. Previous saved copy unchanged; save explicitly to replace it.');
 }catch(e){pendingImport=null;$('import-dialog').close();notice('Import refused: '+e.message+' Current work was preserved.',true);}
 finally{busy=false;}
}
async function saveCurrent(){
 if(busy)return;busy=true;
 try{
  const prepared=await prepareView(workspace);
  await installPrepared(workspace,prepared,{persist:true,save:true});
  notice(prepared.saveFailed?'Local save failed. Work is in memory; export the workspace to retain it.':'Workspace saved on this device.',prepared.saveFailed);
 }catch(e){notice('Local save failed. Work is in memory; export the workspace to retain it.',true);}
 finally{busy=false;}
}
async function resetCurrent(){
 if(busy)return;busy=true;
 try{
  const next=await D.create(),prepared=await prepareView(next);
  await installPrepared(next,prepared,{persist:false,resetStorage:true,resetFields:true});$('reset-dialog').close();notice('Fixed starting edition restored. Exported work is unchanged.');
 }catch(e){$('reset-dialog').close();notice('Reset refused: saved state could not be cleared. Current work and saved copy were preserved.',true);}
 finally{busy=false;}
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;
 try{
  if(b.dataset.view)view(b.dataset.view);
  if(b.dataset.openWorkspace)openWorkspace(b.dataset.openWorkspace);
  if(b.dataset.inspect)inspect(b.dataset.inspect);
  if(b.dataset.edition!==undefined)inspectEdition(Number(b.dataset.edition));
  if(b.dataset.brief!==undefined)brief(Number(b.dataset.brief));
  if(b.dataset.task!==undefined)inspectTask(Number(b.dataset.run),Number(b.dataset.task));
  if(b.dataset.inspectorTask!==undefined){$('inspector').close();inspectTask(Number(b.dataset.run),Number(b.dataset.inspectorTask));}
  switch(b.id){
   case 'mobile-scenario':setControls(true);break;
   case 'close-controls':case 'controls-backdrop':setControls(false);break;
   case 'apply-btn': await transact(w=>D.change(w,{grader:$('grader').value,deadline_ms:Number($('deadline').value),costA:Number($('quote').value)}),'Assumption revised. The prior decision is stale and its retained edition is preserved.');if(matchMedia('(max-width:720px)').matches)setControls(false);break;
   case 'recompute-btn':await transact(async w=>{await D.recompute(w);return w;},'Dependent work recomputed. The change explanation is below the comparison; review before retaining a successor.');break;
   case 'review-btn':await transact(w=>D.reviewed(w,$('reviewer').value,$('rationale').value),'Review recorded against the current dependency closure.');break;
   case 'freeze-btn':await transact(w=>D.sealed(w,$('reviewer').value),'Successor edition retained with its predecessor visible.');break;
   case 'save-btn':await saveCurrent();break;
   case 'export-btn':case 'export-before-import':await exportCurrent();break;
   case 'open-btn':$('packet-file').click();break;
   case 'confirm-import':await confirmImport();break;
   case 'cancel-import':pendingImport=null;$('import-dialog').close();notice('Import cancelled. Current work and saved state were preserved.');break;
   case 'reset-btn':$('reset-dialog').showModal();break;
   case 'cancel-reset':$('reset-dialog').close();break;
   case 'confirm-reset':await resetCurrent();break;
   case 'withdraw-source':$('inspector').close();$('withdraw-dialog').showModal();break;
   case 'cancel-withdraw':$('withdraw-dialog').close();break;
   case 'confirm-withdraw':$('withdraw-dialog').close();await transact(w=>D.correctSource(w),'Example source withdrawn. Dependent judgments are stale; retained editions remain.');break;
  }
 }catch(error){notice(error.message,true);}
});
document.addEventListener('change',e=>{if(e.target.id==='packet-file')importFile(e.target.files?.[0]);});
$('import-dialog').addEventListener('cancel',()=>{pendingImport=null;notice('Import cancelled. Current work was preserved.');});
(async()=>{
 try{
  let saved;try{saved=localStorage.getItem(KEY);}catch{}
  let next,message;
  if(saved){try{next=await D.restore(C.parse(saved));persist=true;savedHash=(await D.pack(next)).sha256;message='Saved workspace restored after native and workflow verification.';}catch(e){next=await D.create();message='Saved copy could not be restored and was left untouched. A fresh in-memory example is open; export before replacing saved work.';}}
  else{
   // Cold visitor: open the real, verified Run 3 decision (Edition 01) from the embedded packet.
   const node=document.getElementById('run3-packet');
   try{if(!node)throw Error('embedded Run 3 packet absent');next=await D.restore(C.parse(node.textContent));message='Run 3 decision open: Hot Aisle 1x MI300X against DigitalOcean 1x H100, Edition 01. Ctrl K opens the worked example.';}
   catch(e){next=await D.create();message='Purple invoices contain correct JSON inside a wrapper. Select one to inspect it, or change the receiving system.';}
  }
  const prepared=await prepareView(next);await installPrepared(next,prepared,{resetFields:true});notice(message);
 }catch(e){notice('Unable to start: '+e.message,true);}
})();

document.addEventListener('keydown',e=>{if(!document.querySelector('main').classList.contains('controls-open')||!matchMedia('(max-width:720px)').matches||document.querySelector('dialog[open]'))return;if(e.key==='Escape'){e.preventDefault();setControls(false);}if(e.key==='Tab'){const list=[...$('scenario-panel').querySelectorAll('button:not(:disabled),input,select,textarea')].filter(n=>n.getClientRects().length);const first=list[0],last=list.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}});

// ===== v0.3.0 interaction layer. Nothing below touches the analytical owner; it reads the rendered state and drives the existing controls. =====
const motionOff=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
// — numbers roll to their new value instead of jumping —
const TICK_GROUPS=['.comp-value','.comp-stats strong','#advantage strong','.real-price'];
function parseNum(text){const m=String(text).match(/^([^\d-]*)(-?\d[\d,]*)(\.\d+)?(.*)$/s);if(!m)return null;return {prefix:m[1],value:parseFloat(m[2].replace(/,/g,'')+(m[3]||'')),decimals:m[3]?m[3].length-1:0,grouped:m[2].includes(','),suffix:m[4]};}
function numNode(el){return el.firstChild&&el.firstChild.nodeType===3?el.firstChild:null;}
function snapshotNums(scope){const map=new Map();for(const sel of TICK_GROUPS)scope.querySelectorAll(sel).forEach((el,i)=>{const n=numNode(el);const parsed=n?parseNum(n.nodeValue):null;if(parsed)map.set(sel+'#'+i,parsed);});return map;}
function fmt(v,p){let s=v.toFixed(p.decimals);if(p.grouped)s=s.replace(/\B(?=(\d{3})+(?!\d))/g,',');return p.prefix+s+p.suffix;}
function animateNums(before){
 if(motionOff()||!before||!before.size)return;
 const ease=x=>1-Math.pow(1-x,3),dur=680,t0=performance.now(),jobs=[];
 for(const sel of TICK_GROUPS)document.querySelectorAll(sel).forEach((el,i)=>{const n=numNode(el);if(!n)return;const to=parseNum(n.nodeValue),from=before.get(sel+'#'+i);if(!to||!from||from.value===to.value||from.prefix!==to.prefix)return;jobs.push({n,from:from.value,to});});
 if(!jobs.length)return;
 const step=now=>{const k=ease(Math.min(1,(now-t0)/dur));for(const j of jobs)j.n.nodeValue=fmt(j.from+(j.to.value-j.from)*k,j.to);if(k<1)requestAnimationFrame(step);else for(const j of jobs)j.n.nodeValue=fmt(j.to.value,j.to);};
 requestAnimationFrame(step);
}
// — surfaces know where the cursor is —
document.addEventListener('pointermove',e=>{const card=e.target.closest?.('.comp-row,.real-card,.edition');if(!card)return;const r=card.getBoundingClientRect();card.style.setProperty('--mx',(e.clientX-r.left)+'px');card.style.setProperty('--my',(e.clientY-r.top)+'px');},{passive:true});
// — tile hover card: the answer to "what is this cell" without leaving the grid —
function tileInfo(runIndex,index){const inputs=calculationInputs(workspace,viewState),task=inputs.runs[runIndex].data.tasks[index];if(!task)return null;const result=viewState.calc.data.results[runIndex].rows.find(r=>r.id===task.id),k=taskKind(task,result,inputs.policy.data),a=task.attempts.at(-1);return {k,a,deadline:inputs.policy.data.deadline_ms,fenced:(a?.output||'').includes('```')};}
let tileTimer=null;
function showTileCard(cell){
 const card=$('tile-card');if(!card||!('showPopover' in card))return;
 const info=tileInfo(Number(cell.dataset.run),Number(cell.dataset.task));if(!info)return;
 const n=String(Number(cell.dataset.task)+1).padStart(2,'0'),cfg=cell.dataset.run==='1'?'B':'A';
 card.innerHTML='<b>Invoice '+n+' · Configuration '+cfg+'</b><span class="kind kind-'+info.k.kind+'">'+escapeHTML(info.k.label)+'</span><small>'+(info.a?(info.a.elapsed_ms/1000).toFixed(1)+' s of '+info.deadline/1000+' s':'no completed attempt')+(info.fenced?' · fenced answer':'')+' · click to inspect</small>';
 const r=cell.getBoundingClientRect(),w=250;card.style.left=Math.min(innerWidth-w-8,Math.max(8,r.left+r.width/2-w/2))+'px';card.style.top=(r.top-8)+'px';
 if(!card.matches(':popover-open'))card.showPopover();
}
function hideTileCard(){const card=$('tile-card');if(card&&card.matches(':popover-open'))card.hidePopover();}
document.addEventListener('pointerover',e=>{const cell=e.target.closest?.('.task-cell');clearTimeout(tileTimer);if(cell){tileTimer=setTimeout(()=>showTileCard(cell),60);}else if(!e.target.closest?.('#tile-card'))hideTileCard();},{passive:true});
document.addEventListener('focusin',e=>{const cell=e.target.closest?.('.task-cell');if(cell)showTileCard(cell);else hideTileCard();});
document.addEventListener('scroll',hideTileCard,{capture:true,passive:true});
document.addEventListener('pointerdown',hideTileCard,{passive:true});
// — command palette: every action, one keystroke away —
const isMac=/Mac|iPhone|iPad/.test(navigator.platform||'');if($('command-kbd'))$('command-kbd').textContent=isMac?'⌘ K':'Ctrl K';
let paletteIndex=0,paletteItems=[];
function commands(){
 const byId=id=>$(id),enabled=id=>!!byId(id)&&!byId(id).disabled,click=id=>()=>byId(id)?.click();
 const list=[
  {label:'Apply change',hint:'scenario',run:click('apply-btn'),on:enabled('apply-btn')},
  {label:'Recompute dependent work',hint:'decision',run:click('recompute-btn'),on:enabled('recompute-btn')},
  {label:'Record review',hint:'review',run:click('review-btn'),on:enabled('review-btn')},
  {label:'Retain edition',hint:'review',run:click('freeze-btn'),on:enabled('freeze-btn')},
  {label:'Receiving system: requires raw JSON',hint:'scenario',run:()=>{$('grader').value='strict_json';$('apply-btn').click();},on:true},
  {label:'Receiving system: can extract one JSON object',hint:'scenario',run:()=>{$('grader').value='extract_json';$('apply-btn').click();},on:true},
  ...[3,12,15].map(sec=>({label:'Deadline: '+sec+' seconds',hint:'scenario',run:()=>{$('deadline').value=String(sec*1000);$('apply-btn').click();},on:true})),
  {label:'Save on this device',hint:'workspace',run:click('save-btn'),on:true},
  {label:'Export workspace',hint:'workspace',run:click('export-btn'),on:true},
  {label:'Open packet',hint:'workspace',run:click('open-btn'),on:true},
  {label:'Go to Invoice extraction',hint:'view',run:()=>view('decision'),on:true},
  {label:'Go to GPU inference evidence',hint:'view',run:()=>view('evidence'),on:true},
  {label:'Go to System map',hint:'view',run:()=>view('architecture'),on:true},
  {label:'Distance to the floor',hint:'page',run:()=>{location.href='floor/index.html';},on:true},
  {label:'Circulation receipts',hint:'page',run:()=>{location.href='circulate/index.html';},on:true},
  {label:'Inspect the 24 original invoices',hint:'record',run:()=>inspect('source'),on:true},
  {label:'Inspect the acceptance contract',hint:'record',run:()=>inspect('policy'),on:true},
  {label:'Inspect the native calculation',hint:'record',run:()=>inspect('calculation'),on:true},
  {label:'Reset worked example',hint:'workspace',run:click('reset-btn'),on:true},
 ];
 for(const run of [0,1])for(let i=0;i<24;i++)list.push({label:'Inspect invoice '+String(i+1).padStart(2,'0')+' · Configuration '+(run?'B':'A'),hint:'invoice',run:()=>inspectTask(run,i),on:true});
 return list;
}
function scoreCmd(q,label){const a=label.toLowerCase(),b=q.toLowerCase().trim();if(!b)return 1;if(a.startsWith(b))return 3;if(a.includes(b))return 2;let j=0;for(const ch of a){if(ch===b[j])j++;if(j===b.length)return 1;}return 0;}
function renderPalette(){
 const q=$('command-input').value;paletteItems=commands().map(c=>({...c,score:scoreCmd(q,c.label)})).filter(c=>c.score>0).sort((x,y)=>y.score-x.score).slice(0,12);
 paletteIndex=Math.min(paletteIndex,Math.max(0,paletteItems.length-1));
 $('command-list').innerHTML=paletteItems.length?paletteItems.map((c,i)=>'<button type="button" role="option" class="palette-item'+(i===paletteIndex?' selected':'')+(c.on?'':' off')+'" data-cmd="'+i+'" aria-selected="'+(i===paletteIndex)+'"><span>'+escapeHTML(c.label)+'</span><small>'+escapeHTML(c.hint)+'</small></button>').join(''):'<div class="palette-empty">Nothing matches.</div>';
}
function openPalette(){const d=$('command-palette');if(!d||d.open)return;paletteIndex=0;$('command-input').value='';renderPalette();d.showModal();$('command-input').focus();}
function runCmd(i){const c=paletteItems[i];if(!c)return;$('command-palette').close();if(!c.on){notice('That action is not available in the current state.');return;}c.run();}
document.addEventListener('keydown',e=>{
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();$('command-palette')?.open?$('command-palette').close():openPalette();return;}
 const d=$('command-palette');if(!d||!d.open)return;
 if(e.key==='ArrowDown'){e.preventDefault();paletteIndex=Math.min(paletteItems.length-1,paletteIndex+1);renderPalette();}
 else if(e.key==='ArrowUp'){e.preventDefault();paletteIndex=Math.max(0,paletteIndex-1);renderPalette();}
 else if(e.key==='Enter'){e.preventDefault();runCmd(paletteIndex);}
});
$('command-input')?.addEventListener('input',()=>{paletteIndex=0;renderPalette();});
$('command-list')?.addEventListener('click',e=>{const b=e.target.closest('[data-cmd]');if(b)runCmd(Number(b.dataset.cmd));});
$('command-list')?.addEventListener('pointermove',e=>{const b=e.target.closest('[data-cmd]');if(b&&Number(b.dataset.cmd)!==paletteIndex){paletteIndex=Number(b.dataset.cmd);renderPalette();}});
$('command-btn')?.addEventListener('click',openPalette);

// ===== integrated: astra/deliverables/fixes.js =====
/* Append as a classic inline script AFTER app.js (not type=module).
 * Presentation-only overrides. No ResearchCore, foundation or analytical mutation.
 * Existing IDs and data attributes are preserved. */
(() => {
  'use strict';
  if (window.CantosFloorInstalled) return;
  window.CantosFloorInstalled = true;

  const input = $('command-input'), list = $('command-list'), palette = $('command-palette');
  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-autocomplete', 'list');
  input.setAttribute('aria-controls', 'command-list');
  input.setAttribute('aria-expanded', 'false');
  $('command-btn').setAttribute('aria-haspopup', 'dialog');
  $('command-btn').setAttribute('aria-controls', 'command-palette');
  let rendered = '';
  renderPalette = function () {
    paletteItems = commands().map(c => ({...c, score: scoreCmd(input.value, c.label)}))
      .filter(c => c.score > 0).sort((a, b) => b.score - a.score).slice(0, 12);
    paletteIndex = Math.max(0, Math.min(paletteIndex, paletteItems.length - 1));
    const key = JSON.stringify(paletteItems.map(c => [c.label, c.hint, c.on]));
    if (key !== rendered) {
      rendered = key;
      list.innerHTML = paletteItems.length ? paletteItems.map((c, i) =>
        '<button type="button" tabindex="-1" role="option" id="floor-command-' + i +
        '" class="palette-item' + (c.on ? '' : ' off') + '" data-cmd="' + i +
        '" aria-disabled="' + !c.on + '"><span>' + escapeHTML(c.label) +
        '</span><small>' + escapeHTML(c.hint) + '</small></button>').join('') :
        '<div class="palette-empty" role="status">Nothing matches.</div>';
    }
    list.querySelectorAll('[data-cmd]').forEach((row, i) => {
      row.classList.toggle('selected', i === paletteIndex);
      row.setAttribute('aria-selected', String(i === paletteIndex));
    });
    const selected = list.querySelector('[aria-selected="true"]');
    if (selected) {
      input.setAttribute('aria-activedescendant', selected.id);
      // Do not scroll the body or animate keyboard navigation.
      const r = selected.getBoundingClientRect(), box = list.getBoundingClientRect();
      if (r.top < box.top) list.scrollTop -= box.top - r.top;
      if (r.bottom > box.bottom) list.scrollTop += r.bottom - box.bottom;
    } else input.removeAttribute('aria-activedescendant');
  };
  palette.addEventListener('toggle', () => {
    input.setAttribute('aria-expanded', String(palette.open));
    if (!palette.open) input.removeAttribute('aria-activedescendant');
  });
  // One focus owner: arrows change the active descendant, Tab stays in the
  // native modal's single input. Pointer selection never rebuilds the rows.
  list.addEventListener('pointerdown', e => e.preventDefault());
  document.addEventListener('keydown', e => {
    const shortcut = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k';
    if (shortcut && document.querySelector('dialog[open]:not(#command-palette)')) {
      e.preventDefault(); e.stopImmediatePropagation(); return;
    }
    if (!palette.open) {
      if (e.key === 'Escape') hideTileCard();
      return;
    }
    if (e.key === 'Tab') {
      e.preventDefault(); e.stopImmediatePropagation(); input.focus();
    } else if (e.key === 'Home' || e.key === 'End') {
      // Preserve native text editing when the user holds Shift.
      if (e.shiftKey) return;
      e.preventDefault(); e.stopImmediatePropagation();
      paletteIndex = e.key === 'Home' ? 0 : Math.max(0, paletteItems.length - 1); renderPalette();
    }
  }, true);

  const card = $('tile-card'), originalShow = showTileCard, originalHide = hideTileCard;
  let anchor = null, previousDescription = null;
  card.removeAttribute('aria-hidden'); card.setAttribute('role', 'tooltip');
  hideTileCard = function () {
    clearTimeout(tileTimer);
    if (anchor) {
      if (previousDescription === null) anchor.removeAttribute('aria-describedby');
      else anchor.setAttribute('aria-describedby', previousDescription);
    }
    anchor = null; previousDescription = null; originalHide();
  };
  showTileCard = function (cell) {
    if (!cell.isConnected || !cell.getClientRects().length || document.querySelector('dialog[open]')) {
      hideTileCard(); return;
    }
    if (anchor !== cell) {
      hideTileCard(); anchor = cell; previousDescription = cell.getAttribute('aria-describedby');
      cell.setAttribute('aria-describedby', [previousDescription, 'tile-card'].filter(Boolean).join(' '));
    }
    originalShow(cell);
    const r = cell.getBoundingClientRect(), c = card.getBoundingClientRect(), gap = 8;
    const left = Math.max(gap, Math.min(innerWidth - c.width - gap, r.left + r.width / 2 - c.width / 2));
    const preferred = r.top - c.height - gap >= gap ? r.top - c.height - gap : r.bottom + gap;
    card.style.left = left + 'px';
    card.style.top = Math.max(gap, Math.min(innerHeight - c.height - gap, preferred)) + 'px';
  };
  document.addEventListener('pointerdown', () => hideTileCard(), true);
  document.addEventListener('scroll', () => hideTileCard(), {capture: true, passive: true});
  window.addEventListener('resize', () => hideTileCard(), {passive: true});
  for (const dialog of document.querySelectorAll('dialog')) {
    dialog.addEventListener('beforetoggle', e => { if (e.newState === 'open') hideTileCard(); });
    const heading = dialog.querySelector('h2');
    if (heading && !dialog.hasAttribute('aria-label') && !dialog.hasAttribute('aria-labelledby')) {
      if (!heading.id) heading.id = dialog.id + '-heading';
      dialog.setAttribute('aria-labelledby', heading.id);
    }
  }
  new MutationObserver(() => {
    if (anchor && (!anchor.isConnected || !anchor.getClientRects().length)) hideTileCard();
  }).observe(document.querySelector('body'), {childList: true, subtree: true});

  let frame = 0, jobs = [];
  const finishTicks = () => {
    cancelAnimationFrame(frame); frame = 0;
    for (const j of jobs) if (j.n.isConnected) j.n.nodeValue = fmt(j.to.value, j.to);
    jobs = [];
  };
  animateNums = function (before) {
    finishTicks();
    if (motionOff() || !before?.size) return;
    for (const sel of TICK_GROUPS) document.querySelectorAll(sel).forEach((el, i) => {
      const n = numNode(el), to = n && parseNum(n.nodeValue), from = before.get(sel + '#' + i);
      if (to && from && from.value !== to.value && from.prefix === to.prefix) jobs.push({n, from: from.value, to});
    });
    if (!jobs.length) return;
    const start = performance.now();
    const tick = now => {
      if (motionOff()) { finishTicks(); return; }
      const t = Math.min(1, (now - start) / 680), eased = 1 - Math.pow(1 - t, 3);
      for (const j of jobs) if (j.n.isConnected) j.n.nodeValue = fmt(j.from + (j.to.value - j.from) * eased, j.to);
      if (t < 1) frame = requestAnimationFrame(tick); else finishTicks();
    };
    frame = requestAnimationFrame(tick);
  };
  matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', e => {
    if (e.matches) { finishTicks(); if (transition) transition.skipTransition(); }
  });
})();


// ===== integrated: fable/deliverables/fable.js =====
/* Fable integration: the tile cascade is armed only for a recompute. The class lives for one transition
   and then the tiles fall back to Astra's uncaptured, immediately clickable state. Presentation only. */
(() => {
  'use strict';
  const root = document.documentElement;
  let timer = null;
  const arm = () => {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    root.classList.add('cascade');
    clearTimeout(timer);
    timer = setTimeout(() => root.classList.remove('cascade'), 1100);
  };
  // capture phase: runs before the app's own click handler starts the transaction
  document.addEventListener('click', e => { if (e.target.closest && e.target.closest('#recompute-btn')) arm(); }, true);
})();

// ===== integrated: astra/deliverables/hardware-view.js =====
/* Append as a classic script after app.js. Presentation only: all mutations,
 * eligibility, acceptance and cost results remain owned by CantosDesk/Core. */
(() => {
 'use strict';
 const task = {prepareView, calculationInputs, outcomeExplanation, inspect, inspectTask, inspectEdition, editionDifference, brief, view, commands, setControls};
 const template = document.querySelector('main').cloneNode(true);
 const hardware = ws => Boolean(ws && D.decisionClass && D.decisionClass(ws) === 'hardware');
 const num = n => Number.isFinite(n) ? n.toLocaleString('en-US') : 'Unavailable';
 const price = n => Number.isFinite(n) ? '$' + (1000*n).toFixed(2) : 'Unavailable';
 const stamp = (scope,source='RUN3-RESULTS.md:5–18') => `<span class="stamp"><span>24 Sep 2026</span><span>${escapeHTML(source)}</span><span>${escapeHTML(scope)}</span></span>`;
 const resultRun = (runs,r) => runs.find(x=>x.data.run_id===r.run_id || x.id===r.run_id);
 const recordsOf = ws => Object.values(C.state(ws).records).map(rs=>rs.at(-1));
 const sourceOf = ws => recordsOf(ws).find(r=>r.kind==='source');
 const ordered = run => [...run.data.tasks].sort((a,b)=>a.scheduled_at_ms-b.scheduled_at_ms);
 function resultRows(run,r) {
  if(r.rows)return new Map(r.rows.map(row=>[row.id,row]));
  return new Map(ordered(run).map((t,i)=>[t.id,{id:t.id,accepted:r.strip?.[i]==='a',code:r.strip?.[i]}]));
 }
 const armName = r => [r.data.identity?.vendor,r.data.identity?.hardware].filter(Boolean).join(' · ') || r.data.label;
 const windowValue = r => typeof r.data.identity.window_minutes==='object' ? r.data.identity.window_minutes.value ?? r.data.identity.window_minutes.minutes : r.data.identity.window_minutes;
 const windowBasis = r => r.data.identity.window_minutes?.basis || r.data.identity.basis || r.data.identity.window_basis || 'retained window';
 const quantile = (xs,p) => xs.length ? xs[Math.max(0,Math.ceil(xs.length*p)-1)] : null;
 const timing = run => run.data.tasks.flatMap(t=>t.attempts.map(a=>a.first_token_ms)).filter(x=>typeof x==='number'&&Number.isFinite(x)).sort((a,b)=>a-b);
 function category(t,row,p) {
  if(row?.code)return ({a:'accepted',f:'first-token-late',l:'late',x:'wrong',e:'late'})[row.code];
  if(row?.accepted)return 'accepted';
  const attempts=t.attempts||[];
  if(!attempts.some(a=>a.status==='ok'))return 'late';
  if(!attempts.some(a=>a.correct===true))return 'wrong';
  if(!attempts.some(a=>a.status==='ok'&&a.correct===true&&a.first_token_ms!==null&&a.first_token_ms<=p.first_token_ms))return 'first-token-late';
  return 'late';
 }
 calculationInputs = function(candidate,v) {
  if(!hardware(candidate))return task.calculationInputs(candidate,v);
  const s=C.state(candidate),refs=v.calc.deps.map(d=>C.version(s,d.id,d.revision));
  return {policy:refs.find(r=>r.kind==='policy'),runs:refs.filter(r=>r.kind==='run')};
 };
 function explanation(v) {
  if(!v.current.current)return 'Assumptions changed; the previous result remains visible until recompute. Retained measurements are unchanged; no new model run.';
  const rows=v.calc.data.results,winner=rows.find(r=>r.run_id===v.calc.data.winner),previous=v.reports.findLast(r=>snapshotParts(r).calc.revision!==v.calc.revision);
  const values=rows.map(r=>`${armName(resultRun(v.runs,r))}: ${price(r.cost_per_success)} per 1,000 accepted${r.eligible?'':' (ineligible: '+r.blockers.join('; ')+')'}`).join(' versus ');
  if(previous && snapshotParts(previous).calc.data.winner!==v.calc.data.winner && winner) {
   const run=resultRun(v.runs,winner);
   return `At ${money(run.data.billing.rate_usd_per_hour)}/h, the decision flips to ${armName(run)}: ${values}; arithmetic over retained measurements, no new model run.`;
  }
  return `${winner?armName(resultRun(v.runs,winner))+' has the lowest eligible cost':'No arm is eligible'}: ${values}; list-price arithmetic over retained measurements, no new model run.`;
 }
 outcomeExplanation = v => v.policy.data.comparison_mode==='hardware' ? explanation(v) : task.outcomeExplanation(v);
 function restoreTaskChrome(node) {
  node.classList.remove('hardware-workspace');
  for(const sel of ['.case-heading h1','.case-heading p','.decision-stamps','.matrix-legend','.controls-heading h2','.case-link[data-view="decision"]','.rail-section .source-card','.lineage [data-inspect="source"]','.workspace-name']) {
   node.querySelector(sel).innerHTML=template.querySelector(sel).innerHTML;
  }
  const vals=['grader','deadline','quote'].map(id=>[id,node.querySelector('#'+id).value]);
  node.querySelector('.controls-fields').innerHTML=template.querySelector('.controls-fields').innerHTML;
  for(const [id,value] of vals)node.querySelector('#'+id).value=value;
 }
 prepareView = async function(candidate) {
  if(!hardware(candidate)) {
   const prepared=await task.prepareView(candidate);
   if(prepared.node.classList.contains('hardware-workspace'))restoreTaskChrome(prepared.node);
   return prepared;
  }
  D.workflow(candidate);
  const v=await D.view(candidate),main=template.cloneNode(true),get=id=>main.querySelector('#'+id),calc=v.calc.data,current=v.current.current,pinned=calculationInputs(candidate,v);
  const winner=calc.results.find(r=>r.run_id===calc.winner),frozen=v.reports.some(r=>r.fingerprint===v.review.fingerprint),source=sourceOf(candidate),sourceCurrent=source&&C.dependencyState(C.state(candidate),source.id).current;
  main.classList.add('hardware-workspace');
  // Preserve current navigation and drawer state across an atomic render.
  const old=document.querySelector('main');
  for(const name of ['decision','evidence','architecture'])get(name+'-view').hidden=old.querySelector('#'+name+'-view').hidden;
  for(const nav of main.querySelectorAll('.nav[data-view]'))nav.classList.toggle('active',!get(nav.dataset.view+'-view').hidden);
  if(old.classList.contains('controls-open'))main.classList.add('controls-open');
  main.querySelector('.workspace-name').innerHTML='Research decision <span class="tag">RETAINED RUN 3</span>';
  main.querySelector('.case-heading h1').textContent='Same work. Different list prices.';
  main.querySelector('.case-heading p').textContent='Same coding workload. Retained answers and timings. A revisable list-price decision.';
  main.querySelector('.case-link[data-view="decision"] strong').textContent='Run 3 decision';
  main.querySelector('.case-link[data-view="decision"] small').textContent='Hardware · list-price scenario';
  main.querySelector('.rail-section .source-card').textContent='Run 3 source records';
  main.querySelector('.lineage [data-inspect="source"] span').textContent='Retained requests';
  main.querySelector('.decision-stamps').innerHTML=stamp('Run 3 · observed workload, scenario list prices');
  get('winner').textContent=current?(winner?armName(resultRun(pinned.runs,winner)):'No eligible result'):'Decision needs updating';
  get('decision-kicker').textContent=current?'LOWEST COST / 1,000 ACCEPTED':'CHANGED INPUT / PREVIOUS RESULT RETAINED';
  get('decision-summary').textContent='Correct, first token within '+pinned.policy.data.first_token_ms+' ms, complete within '+pinned.policy.data.deadline_ms/1000+' s from scheduled arrival.';
  get('current-state').textContent=!current?'STALE':frozen?'RETAINED EDITION':v.review.ready?'REVIEWED':'DRAFT';
  get('current-state').className='state '+(!current?'stale':!frozen?'draft':'');
  get('policy-version').textContent='v'+v.policy.revision;
  for(const id of ['calc-node','decision-node'])get(id).classList.toggle('stale',!current);
  get('advantage').innerHTML='';
  get('comparison').innerHTML=calc.results.map((r,i)=>{
   const run=resultRun(pinned.runs,r),identity=run.data.identity,ts=timing(run);
   const pct=[.5,.95,.99].map(p=>quantile(ts,p));
   return `<article class="comp-row hardware-arm ${r.run_id===calc.winner?'winner':''}" data-configuration="${i?'B':'A'}" data-arm="${escapeHTML(identity.arm)}"><div class="comp-header"><span class="config-id"><b>${escapeHTML(identity.arm)}</b>${escapeHTML(identity.vendor)}</span>${r.run_id===calc.winner?'<span class="tag">'+(current?'PREFERRED':'PRIOR RESULT')+'</span>':!r.eligible?'<span class="tag">INELIGIBLE</span>':''}</div><div class="hardware-badges"><span>${escapeHTML(identity.hardware)}</span><span>${escapeHTML(identity.runtime)}</span></div><div class="comp-price"><strong class="comp-value">${price(r.cost_per_success)}</strong><small>/ 1,000 accepted</small></div><div class="comp-stats"><strong>${num(r.accepted)}<small> / ${num(r.tasks)}</small></strong><span>accepted requests</span></div><div class="hardware-percentiles"><span>First token from scheduled arrival</span>${pct.map((n,j)=>`<span><small>p${[50,95,99][j]}</small><b>${n===null?'Unavailable':Math.round(n)+' ms'}</b></span>`).join('')}</div><figure class="request-density"><canvas width="256" height="${Math.ceil(run.data.tasks.length/256)}" role="img" aria-label="${escapeHTML(identity.arm)} request outcomes in scheduled arrival order"></canvas><figcaption>Arrival order · left to right, then next row</figcaption>${stamp('Retained requests · nearest-rank first-token percentiles',"run3-scored-"+identity.arm.toLowerCase().replace("/","-")+"/replay/requests.jsonl:1-8622")}</figure><div class="comp-footer"><span>${money(run.data.billing.rate_usd_per_hour)}/h · ${num(windowValue(run))} min<br>${escapeHTML(windowBasis(run).replaceAll('_',' '))}</span><button class="text-button" data-inspect="${escapeHTML(run.id)}">Inspect arm</button></div>${stamp('Whole-run list cost / accepted · not an invoice','RUN3-RESULTS.md:12–18; '+run.id+'@'+run.revision)}${r.blockers.length?'<p class="field-note">'+escapeHTML(r.blockers.join(' '))+'</p>':''}</article>`;
  }).join('');
  const colors={accepted:'#8fbea7',late:'#d5b477',wrong:'#d48691','first-token-late':'#a99bd6'};
  calc.results.forEach((r,i)=>{
   const run=resultRun(pinned.runs,r),rows=resultRows(run,r),canvas=main.querySelectorAll('.request-density canvas')[i],ctx=canvas.getContext('2d'),counts={accepted:0,late:0,wrong:0,'first-token-late':0};
   [...run.data.tasks].sort((a,b)=>a.scheduled_at_ms-b.scheduled_at_ms).forEach((t,j)=>{const k=category(t,rows.get(t.id),pinned.policy.data);counts[k]++;ctx.fillStyle=colors[k];ctx.fillRect(j%256,Math.floor(j/256),1,1);});
   canvas.setAttribute('aria-label',`${run.data.identity.arm}: ${num(run.data.tasks.length)} requests in arrival order; ${counts.accepted} accepted, ${counts.late} late or incomplete, ${counts.wrong} incorrect, ${counts['first-token-late']} first-token-late. Multiple failures use precedence: incorrect, first-token-late, late.`);
  });
  main.querySelector('.matrix-legend').innerHTML='<span><i class="accepted"></i>Accepted</span><span><i class="late"></i>Late / incomplete</span><span><i class="wrong"></i>Incorrect</span><span><i class="format"></i>First-token late</span>';
  get('outcome-diff').textContent=explanation(v);
  get('outcome-diff').insertAdjacentHTML('beforeend',stamp('Current scenario · retained measurements','calculation@'+v.calc.revision));
  get('change-summary').hidden=current;get('change-summary').textContent=v.current.blockers.join(' · ');
  get('recompute-btn').disabled=current||!sourceCurrent;
  get('review-btn').disabled=!current;get('freeze-btn').disabled=!current||!v.review.ready||frozen;
  get('next-step-note').textContent=!sourceCurrent?'Source withdrawn. Retained editions remain.':!current?'Recompute list-price arithmetic; no new model run.':!v.review.ready?'Review the changed decision before retaining.':!frozen?'Retain the reviewed successor.':'Change a list rate or timing limit to compare a scenario.';
  get('review-status').textContent=!current?'Recompute before reviewing.':frozen?'This version is retained.':v.review.ready?'Reviewed. Ready to retain.':'Record the reasoning for this scenario.';
  get('review-light').style.background=v.review.ready?'var(--accepted)':'var(--dim)';
  main.querySelector('.controls-heading h2').textContent='Change an assumption';
  const fields=main.querySelector('.controls-fields');
  // Keep every existing id/data attribute, hiding the invoice-specific controls.
  get('grader').hidden=true;main.querySelector('label[for="grader"]').hidden=true;main.querySelector('.format-preview').hidden=true;
  const deadline=get('deadline'),input=document.createElement('input');for(const a of deadline.attributes)input.setAttribute(a.name,a.value);input.type='number';input.min='1';input.step='1';input.value=v.policy.data.deadline_ms;deadline.replaceWith(input);
  main.querySelector('label[for="deadline"]').textContent='Completion limit · ms';
  main.querySelector('label[for="quote"]').textContent=v.runs[0].data.identity.arm+' · $/hour';get('quote').value=v.runs[0].data.billing.rate_usd_per_hour;get('quote').dataset.hardwareRate=v.runs[0].id;
  const extra=document.createElement('div');extra.className='hardware-fields';
  extra.innerHTML=v.runs.slice(1).map(r=>`<label>${escapeHTML(r.data.identity.arm)} · list $/hour<input type="number" min="0" step="0.01" data-hardware-rate="${escapeHTML(r.id)}" value="${r.data.billing.rate_usd_per_hour}"></label>`).join('')+`<label>First-token limit · ms<input type="number" min="1" step="1" data-first-token value="${v.policy.data.first_token_ms}"></label>`;
  fields.insertBefore(extra,get('apply-btn'));fields.querySelector('.field-note').textContent='Arithmetic over retained measurements; no new model run.';
  get('history-count').textContent=String(v.reports.length).padStart(2,'0');
  get('editions').innerHTML=v.reports.map((r,i)=>{const parts=snapshotParts(r),w=parts.calc.data.results.find(x=>x.run_id===parts.calc.data.winner),same=r.fingerprint===v.review.fingerprint;return `<article class="edition ${same?'current-edition':''}"><header><h3>Edition ${String(i+1).padStart(2,'0')} · ${escapeHTML(w?.label||'No recommendation')}</h3><span class="tag">${same?'CURRENT':'HISTORY'}</span></header><p>${w?price(w.cost_per_success)+'/1,000 accepted':'No eligible result'} · first token ≤ ${parts.policy.data.first_token_ms} ms · complete ≤ ${parts.policy.data.deadline_ms/1000} s</p>${i?'<p class="successor-line">Supersedes Edition '+String(i).padStart(2,'0')+' · '+v.reports[i-1].snapshot_hash.slice(0,12)+'…</p>':''}${stamp('Frozen scenario · retained measurements','calculation@'+parts.calc.revision)}<div class="edition-bottom"><code>${r.snapshot_hash.slice(0,12)}…</code><span><button class="text-button" data-edition="${i}">Compare</button> · <button class="text-button" data-brief="${i}">Brief</button></span></div></article>`;}).join('');
  const publicState={current,reportCount:v.reports.length,winner:calc.winner,packetHash:v.packetHash,events:v.events.length,sourceDisposition:source?.disposition,decisionClass:'hardware'};
  return {node:main,v,publicState,packetJSON:JSON.stringify(await D.pack(candidate))};
 };
 // Route hardware form values into the already-owned transactional API.
 document.addEventListener('click',async e=>{
  if(!hardware(workspace)||!e.target.closest('#apply-btn'))return;
  e.preventDefault();e.stopImmediatePropagation();
  const rates=Object.fromEntries([...document.querySelectorAll('[data-hardware-rate]')].map(el=>[el.dataset.hardwareRate,Number(el.value)]));
  const deadline_ms=Number($('deadline').value),first_token_ms=Number(document.querySelector('[data-first-token]').value);
  await transact(w=>D.change(w,{rates,deadline_ms,first_token_ms}),'Assumption revised. Recompute over retained measurements; no new model run.');
  if(matchMedia('(max-width:720px)').matches)setControls(false);
 },true);
 setControls = function(open) {task.setControls(open);if(open&&hardware(workspace))$('quote').focus({preventScroll:true});};
 view = function(name) {task.view(name);if(hardware(workspace)&&name==='decision'){document.querySelector('.workspace-name').innerHTML='Research decision <span class="tag">RETAINED RUN 3</span>';notice('Run 3 · list-price scenario over retained measurements; no new model run.');}};
 inspect = function(id) {
  if(!hardware(workspace))return task.inspect(id);
  const r=C.latest(C.state(workspace),id)||recordsOf(workspace).find(r=>r.kind===({decision:'conclusion',calculation:'calculation',source:'source',policy:'policy'}[id]));if(!r)return;
  let html='<p>'+escapeHTML(r.summary)+'</p>'+stamp('Retained record · operator supplied',r.id+'@'+r.revision);
  if(r.kind==='run')html+=`<p>${escapeHTML(armName(r))} · ${num(r.data.tasks.length)} retained requests · ${money(r.data.billing.rate_usd_per_hour)}/h.</p><label>Request in retained order<input type="number" min="1" max="${r.data.tasks.length}" value="1" data-request-index></label><button class="outline-button" data-open-request="${escapeHTML(r.id)}">Inspect request</button>`;
  openInspector(r.title,r.id+' · v'+r.revision+' · '+r.tier,html,r);
 };
 document.addEventListener('click',e=>{const b=e.target.closest('[data-open-request]');if(!b)return;const i=viewState.runs.findIndex(r=>r.id===b.dataset.openRequest),n=Number(document.querySelector('[data-request-index]').value)-1;$('inspector').close();inspectTask(i,n);});
 inspectTask = function(i,n) {
  if(!hardware(workspace))return task.inspectTask(i,n);
  const pin=calculationInputs(workspace,viewState),run=pin.runs[i],t=run?.data.tasks[n];if(!t)return;
  const result=viewState.calc.data.results.find(r=>r.run_id===run.data.run_id),row=resultRows(run,result).get(t.id),kind=category(t,row,pin.policy.data);
  openInspector('Request '+t.id,armName(run)+' · retained measurements','<p>'+escapeHTML(kind)+'</p>'+stamp('Scheduled-arrival timing · recorded correctness',run.id+'@'+run.revision+' / '+t.id),{task:t,result:row,policy:pin.policy.data});
 };
 editionDifference = function(r,prior) {if(snapshotParts(r).policy.data.comparison_mode!=='hardware')return task.editionDifference(r,prior);return (prior?'Successor scenario over the same retained measurements. ':'Retained Run 3 starting decision. ')+snapshotParts(r).calc.data.results.map(x=>x.label+': '+price(x.cost_per_success)+'/1,000 accepted').join('; ')+'. No new model run.';};
 inspectEdition = function(i) {if(!hardware(workspace))return task.inspectEdition(i);const r=viewState.reports[i];openInspector('Retained edition '+String(i+1).padStart(2,'0'),'Immutable snapshot · '+r.snapshot_hash,'<p>'+escapeHTML(editionDifference(r,viewState.reports[i-1]))+'</p>'+stamp('Frozen scenario · not a fresh execution','Edition '+(i+1)),r.snapshot);};
 brief = function(i) {if(!hardware(workspace))return task.brief(i);const r=viewState.reports[i];download('Cantos-hardware-edition-'+(i+1)+'.html',C.reportHTML(r.snapshot,'Retained Run 3 list-price scenario. Arithmetic over retained measurements; no new model run.',r.snapshot_hash),'text/html');};
 commands = function() {
  const list=task.commands();if(!hardware(workspace))return list;
  const kept=list.filter(c=>!c.label.startsWith('Receiving system:')&&!c.label.startsWith('Deadline:')&&!c.label.startsWith('Inspect invoice')&&!c.label.includes('24 original invoices')&&!c.label.includes('Invoice extraction'));
  kept.push({label:'Go to Run 3 decision',hint:'view',on:true,run:()=>view('decision')},{label:'Set H100 list rate to $2.49/h',hint:'scenario',on:!busy,run:()=>{const r=viewState.runs.find(r=>/H100/i.test(r.data.identity.hardware));if(!r)return;document.querySelector('[data-hardware-rate="'+r.id+'"]').value='2.49';$('apply-btn').click();}},{label:'Set timing limits',hint:'scenario',on:true,run:()=>setControls(true)});
  return kept;
 };
})();


// ===== integrated: fable — open the real Run 3 decision from the embedded packet (no fetch; CSP) =====
async function openWorkspace(kind){
 const run3=kind==='run3',label=run3?'the Run 3 decision':'the worked example';
 if(busy||pendingImport){notice('Finish the current operation before opening '+label+'.',true);return;}
 busy=true;
 try{
  let candidate;
  if(run3){const node=document.getElementById('run3-packet');if(!node)return;candidate=await D.restore(C.parse(node.textContent));}
  else candidate=await D.create();
  const prepared=await prepareView(candidate);
  if(prepared.v.packetHash===viewState.packetHash){notice(run3?'The Run 3 decision is already open.':'The worked example is already open.');return;}
  pendingImport={candidate,baseHash:viewState.packetHash};$('import-dialog').showModal();
 }catch(e){notice((run3?'Run 3 decision':'Worked example')+' refused: '+e.message+' Current work was preserved.',true);}
 finally{busy=false;}
}
const openEmbeddedRun3=()=>openWorkspace('run3');
if(typeof commands==='function'){const baseCommands=commands;commands=function(){const list=baseCommands();list.unshift({label:'Open the Run 3 decision (real, MI300X vs H100)',hint:'decision',run:()=>openWorkspace('run3'),on:true},{label:'Open the worked example',hint:'synthetic',run:()=>openWorkspace('example'),on:true});return list;};}

// ===== cold-visitor entry: rail lists the real decision first, orientation line on Run 3 =====
const ORIENTATION='One measured decision: the same coding workload on two rented seats, cost per 1,000 accepted requests at list price, every figure stamped with its source.';
function composeRail(node,run3){
 const nav=node.querySelector('.case-nav');if(!nav)return;
 const viewOn=n=>{const v=node.querySelector('#'+n+'-view');return v&&!v.hidden;};
 const link=(attr,eyebrow,name,active)=>'<button class="nav case-link'+(active?' active':'')+'" '+attr+'><span><small class="ws-eyebrow">'+eyebrow+'</small><strong>'+name+'</strong></span></button>';
 const gpu=['Real decision · Run 3, 24 Sep 2026','GPU inference'],ex=['Worked example · synthetic','Invoice extraction'];
 nav.setAttribute('aria-label','Workspaces');
 nav.innerHTML=run3
  ?link('data-view="decision"',gpu[0],gpu[1],viewOn('decision'))+link('data-open-workspace="example"',ex[0],ex[1],false)
  :link('data-open-workspace="run3"',gpu[0],gpu[1],false)+link('data-view="decision"',ex[0],ex[1],viewOn('decision'));
 const ev=node.querySelector('.rail-bottom .nav[data-view="evidence"]');if(ev)ev.classList.toggle('active',viewOn('evidence'));
 const arch=node.querySelector('.rail-bottom .nav[data-view="architecture"]');if(arch)arch.classList.toggle('active',viewOn('architecture'));
 node.querySelectorAll('.orientation').forEach(e=>e.remove());
 const head=node.querySelector('.case-heading');
 if(run3&&head){const p=document.createElement('p');p.className='orientation';p.textContent=ORIENTATION;head.after(p);}
}
{const basePrepare=prepareView;prepareView=async function(candidate){const prepared=await basePrepare(candidate);composeRail(prepared.node,Boolean(D.decisionClass&&D.decisionClass(candidate)==='hardware'));return prepared;};}

