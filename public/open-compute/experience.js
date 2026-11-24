'use strict';
const frame=document.getElementById('decision-app'),steps=[...document.querySelectorAll('[data-step]')];
const title=document.getElementById('guide-title'),copy=document.getElementById('guide-copy'),next=document.getElementById('guide-next'),request=document.getElementById('guide-request');
let activeStep='compare',state=null,startupError='';
function command(name){
 frame.contentWindow?.postMessage({type:'cantos-guide',command:name},location.origin);
 if(name!=='status'&&matchMedia('(max-width:720px)').matches){
  requestAnimationFrame(()=>frame.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'}));
 }
}
function setStep(name,act=true){
 if(!['compare','evidence','change','retain'].includes(name))return;
 activeStep=name;
 for(const b of steps){if(b.dataset.step===name)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');}
 renderGuide();
 if(act)command(name);
}
function renderGuide(){
 if(startupError&&!state){
  title.textContent='The workspace could not open.';copy.textContent=startupError;
  next.hidden=true;request.hidden=true;document.getElementById('guide-status').textContent='Workspace unavailable';
  document.getElementById('guide-detail').textContent='The stored copy remains untouched. A fresh replay workspace is linked below.';
  document.getElementById('guide-hash').textContent='';return;
 }
 next.hidden=false;
 const changed=state?.rates?.find(r=>r.runId==='n-t0')?.rate!==4.41;
 const stale=state&&!state.current,retained=(state?.reportCount||0)>1;
 let heading,body,label,destination;
 if(activeStep==='compare'){
  heading='Start with accepted work.';
  body='Each arm received 8,622 scheduled requests. The comparison counts answers that met correctness and timing requirements.';
  label='Inspect acceptance';destination='evidence';
 }else if(activeStep==='evidence'){
  heading='Follow the result to its evidence.';
  body='Inspect the acceptance contract and a retained request. The recorded grade and timing explain what counted as useful work.';
  label='Change a price';destination='change';
 }else if(activeStep==='change'){
  if(stale){
   heading='The earlier decision is now stale.';
   body='The assumption has changed. Recompute dependent work in the workspace to calculate the new scenario; the earlier edition stays intact.';
   label='Show the comparison';destination='compare';
  }else if(changed&&state){
   heading='The new scenario is calculated.';
   body='The calculation uses the same retained measurements. Review the changed decision and record why you would choose it.';
   label='Review & retain';destination='retain';
  }else{
   heading='Change one assumption.';
   body='Set the H100 list rate to $2.49 per hour, then apply the change. Recompute explicitly to see what that price does to the decision.';
   label='Focus the price';destination='change';
  }
 }else if(retained){
  heading='Carry both decisions forward.';
  body='Compare the retained editions, export the packet, then open it in a fresh workspace. Reopening verifies the journal and recomputes its recorded calculations.';
  label='Inspect decision history';destination='history';
 }else{
  heading='Keep the reasoning with the decision.';
  body='Enter a reviewer and rationale, record the review, and retain the edition. Export packet carries the evidence, assumptions, review and predecessor together.';
  label='Focus review';destination='retain';
 }
 title.textContent=heading;copy.textContent=body;next.textContent=label;next.dataset.command=destination;
 request.hidden=activeStep!=='evidence';
 document.getElementById('guide-status').textContent=state?state.state.toLowerCase().replace(/^./,c=>c.toUpperCase()):'Verifying retained packet…';
 document.getElementById('guide-detail').textContent=state?.storageWarning|| (state?(stale?'Changed inputs · prior result preserved':state.reportCount+' retained edition'+(state.reportCount===1?'':'s')+' · '+(state.reviewReady?'review recorded':'review available')):'The workspace opens directly in this page.');
 document.getElementById('guide-hash').textContent=state?'Packet '+state.packetHash.slice(0,12)+'…':'';
}
for(const b of steps)b.addEventListener('click',()=>setStep(b.dataset.step));
next.addEventListener('click',()=>{const dest=next.dataset.command;if(dest==='history')command(dest);else setStep(dest);});
request.addEventListener('click',()=>command('request'));
document.getElementById('try-change').addEventListener('click',()=>{setStep('change');if(!matchMedia('(max-width:720px)').matches)document.getElementById('workbench').scrollIntoView({block:'start',behavior:'smooth'});});
window.addEventListener('message',e=>{
 if(e.source!==frame.contentWindow||e.origin!==location.origin)return;
 if(e.data?.type==='cantos-error'){startupError=e.data.message;renderGuide();return;}
 if(e.data?.type!=='cantos-state')return;
 startupError='';state=e.data;window.CantosGuideState=state;renderGuide();
});
frame.addEventListener('load',()=>command('status'));
function revealAnchor(){
 const id=location.hash.slice(1);
 if(['deployment','maintainers','start','common-grade'].includes(id)){document.getElementById('instrument').open=true;requestAnimationFrame(()=>document.getElementById(id)?.scrollIntoView());}
}
window.addEventListener('hashchange',revealAnchor);
renderGuide();revealAnchor();
