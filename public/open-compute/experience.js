'use strict';
const frame=document.getElementById('decision-app'),steps=[...document.querySelectorAll('[data-step]')];
const title=document.getElementById('guide-title'),copy=document.getElementById('guide-copy'),next=document.getElementById('guide-next'),request=document.getElementById('guide-request');
let activeStep='compare',state=null,startupError='';
const video=document.getElementById('walkthrough-video'),watchPanel=document.getElementById('walkthrough'),livePanel=document.getElementById('workbench'),viewTabs=[...document.querySelectorAll('[data-view]')];
let currentView='watch';
function chooseView(name,{scroll=false,remember=false}={}){
 if(!['watch','live'].includes(name))return;
 currentView=name;
 const live=name==='live';
 if(live&&!video.paused)video.pause();
 watchPanel.hidden=live;livePanel.hidden=!live;
 for(const tab of viewTabs){const selected=tab.dataset.view===name;tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;}
 if(remember){const url=new URL(location.href);url.hash=live?'workbench':'walkthrough';history.replaceState(null,'',url);}
 if(live)requestAnimationFrame(()=>command('status'));
 if(scroll)requestAnimationFrame(()=>document.getElementById('experience').scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'}));
}
for(const tab of viewTabs){
 tab.addEventListener('click',()=>chooseView(tab.dataset.view,{remember:true}));
 tab.addEventListener('keydown',e=>{
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
  e.preventDefault();
  const index=e.key==='Home'?0:e.key==='End'?viewTabs.length-1:(viewTabs.indexOf(tab)+(e.key==='ArrowRight'?1:-1)+viewTabs.length)%viewTabs.length;
  chooseView(viewTabs[index].dataset.view,{remember:true});viewTabs[index].focus();
 });
}
for(const button of document.querySelectorAll('[data-open-live]'))button.addEventListener('click',()=>chooseView('live',{scroll:true,remember:true}));
for(const link of document.querySelectorAll('.watch-link'))link.addEventListener('click',e=>{e.preventDefault();chooseView('watch',{scroll:true,remember:true});});
const filmStatus=document.getElementById('film-status');
video.addEventListener('playing',()=>{
 // The initial poster has no role after the first decoded playback begins.
 video.removeAttribute('poster');
 filmStatus.textContent='Playing recorded walkthrough';
 document.getElementById('film-error').hidden=true;
});
video.addEventListener('pause',()=>{filmStatus.textContent=video.ended?'Walkthrough complete':video.currentTime>0?'Paused walkthrough':'Recorded walkthrough · 1:57';});
video.addEventListener('ended',()=>{filmStatus.textContent='Walkthrough complete';});
video.addEventListener('error',()=>{filmStatus.textContent='Recording unavailable in this player';document.getElementById('film-error').hidden=false;});
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
  body='Each configuration received 8,622 requests. Compare the cost of answers that were correct and delivered on time.';
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
  body='Compare the original and revised decisions, export the workspace, then open it in a fresh workspace. Reopening verifies the record and recomputes its calculations.';
  label='Inspect decision history';destination='history';
 }else{
  heading='Keep the reasoning with the decision.';
  body='Enter a reviewer and rationale, record the review, and retain the revised decision. Export workspace carries the evidence and both versions together.';
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
 if(id==='workbench')chooseView('live');
 else if(id==='walkthrough')chooseView('watch');
 if(['deployment','maintainers','start','common-grade'].includes(id)){document.getElementById('instrument').open=true;requestAnimationFrame(()=>document.getElementById(id)?.scrollIntoView());}
}
window.addEventListener('hashchange',revealAnchor);
renderGuide();revealAnchor();
