/* Cantos workbench UI. Presentation only: every action goes through window.CantosDesk
   (research-desk/cantos/foundation.js), which delegates to the native ResearchCore.
   This file computes no economics and invents no evidence. */
(function(){
'use strict';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const reduced=()=>window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
let D=null,R=null,V=null,busy=false;

/* ---------- helpers ---------- */
function toast(msg,kind){const t=$('toast');t.textContent=msg;t.hidden=false;t.style.borderLeftColor=kind==='bad'?'var(--bad)':kind==='ok'?'var(--ok)':'';clearTimeout(toast.h);toast.h=setTimeout(()=>{t.hidden=true;},kind==='bad'?9000:5000);}
function flash(el){if(!el||reduced())return;el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash');}
function when(iso){if(!iso)return '';const d=new Date(iso);return isNaN(d)?String(iso):d.toISOString().replace('T',' ').replace(/\.\d+Z$/,'Z');}
function short(h){return h?String(h).slice(0,12)+'…':'';}
function link(href,text){if(!href)return esc(text);const safe=/^https?:\/\//i.test(href)?href:null;return safe?'<a href="'+esc(safe)+'" target="_blank" rel="noopener noreferrer">'+esc(text)+'</a>':esc(text);}
const STATE_LABEL={derived:'Recomputed under scenario',current:'Current',stale:'Stale — an input changed',blocked:'Blocked',review:'Needs review',changed:'Changed input'};
function stateOf(x){return x&&STATE_LABEL[x]?x:'current';}
function cls(tier){const t=String(tier||'').toLowerCase();if(/post/.test(t))return 'posthoc';if(/synth/.test(t))return 'synthetic';if(/scen|proposal/.test(t))return 'scenario';if(/measur|public|observ|retained|operator/.test(t))return 'measured';return '';}
function tag(tier,label){return tier?'<span class="tag '+cls(tier)+'">'+esc(label||String(tier).replace(/_/g,' '))+'</span>':'';}

async function act(btn,fn,okMsg){
  if(busy)return null;busy=true;if(btn)btn.setAttribute('aria-busy','true');
  try{
    const r=await fn();
    if(r&&r.ok===false)throw new Error(r.error||'The foundation refused this action.');
    R=r&&r.view?r.view:D.view();render();
    if(okMsg)toast(typeof okMsg==='function'?okMsg(r):okMsg,'ok');
    return r||{};
  }catch(e){toast(e&&e.message?e.message:String(e),'bad');return null;}
  finally{busy=false;if(btn)btn.removeAttribute('aria-busy');}
}

/* ---------- guide ---------- */
function guide(){
  const steps=[
    ['Read the recommendation',true],
    ['Review it',!!(V.review&&V.review.bound)||V.snapshots.length>0],
    ['Issue version 1',V.snapshots.length>=1],
    ['Change an input',V.inputs.some(i=>i.changed)||V.snapshots.length>=2],
    ['Recompute',V.recomputed||V.snapshots.length>=2],
    ['Review again and issue',V.snapshots.length>=2],
    ['Export and restore',!!V.exported]
  ];
  let now=steps.findIndex(s=>!s[1]);
  $('guide').innerHTML=steps.map((s,i)=>'<li class="'+(s[1]?'done':i===now?'now':'')+'"'+(i===now?' aria-current="step"':'')+'>'+esc(s[0])+'</li>').join('');
}

/* ---------- recommendation ---------- */
function renderRec(){
  const r=V.recommendation||{},st=r.state||'current';
  const needs=st==='current'&&!(V.review&&V.review.ready);
  const badge=st!=='current'?st:needs?'review':'current';
  const label=st==='current'?(needs?'Current · awaiting review':'Current · reviewed'):STATE_LABEL[st]||st;
  let h='<p class="eyebrow">Recommendation'+(r.revision?' · revision '+esc(r.revision):'')+'</p>';
  h+='<span class="state '+esc(badge)+'">'+esc(label)+'</span>';
  h+='<blockquote>'+esc(r.text||'No recommendation recorded.')+'</blockquote>';
  if(r.scope)h+='<p class="small">'+esc(r.scope)+'</p>';
  if(r.figures&&r.figures.length)h+='<div class="figures">'+r.figures.map(f=>'<div class="fig'+(f.changed?' changed':'')+'"><span class="k">'+esc(f.label)+'</span><span class="v">'+esc(f.value)+'</span>'+(f.scope?'<span class="scope">'+esc(f.scope)+'</span>':'')+(f.tier?tag(f.tier,f.tierLabel):'')+'</div>').join('')+'</div>';
  if(r.conditions&&r.conditions.length)h+='<h4 style="margin-top:20px">Holds only while</h4><ul class="conds">'+r.conditions.map(c=>'<li>'+esc(c)+'</li>').join('')+'</ul>';
  if(st==='stale')h+='<div class="notice"><strong>This conclusion no longer matches its inputs.</strong> '+esc((r.blockers||[]).join(' · ')||'An upstream record has a newer revision.')+' The issued versions below are unchanged. Recompute to form a successor, then review it.</div>';
  if(st==='blocked')h+='<div class="notice bad">'+esc((r.blockers||[]).join(' · '))+'</div>';
  $('rec-body').innerHTML=h;
}

/* ---------- evidence ---------- */
function renderEvidence(){
  const rows=V.evidence||[];
  $('ev-note').textContent=V.evidenceNote||'';
  if(!rows.length){$('ev-table').innerHTML='<tbody><tr><td>No evidence rows supplied.</td></tr></tbody>';return;}
  const groups=[...new Set(rows.map(r=>r.group))];let body='';
  for(const group of groups){
    const items=rows.filter(r=>r.group===group);
    body+='<tr class="grp"><th scope="rowgroup" colspan="3">'+esc(group||'')+'</th></tr>';
    for(const e of items)body+='<tr><td>'+esc(e.label)+'</td><td class="num">'+esc(e.value)+'</td><td>'+tag(e.tier||'measured',e.tierLabel)+'</td></tr>';
    const notes=[...new Set(items.flatMap(e=>[e.scope,e.caveat]).filter(Boolean))];
    const sources=new Map();for(const e of items)if(e.source)sources.set(e.source,e);
    body+='<tr class="group-notes"><td colspan="3">'+notes.map(n=>'<p class="small">'+esc(n)+'</p>').join('')+[...sources.values()].map(e=>'<p class="small">'+esc(e.date||'')+'<br><span class="mono">'+link(e.href,e.source)+'</span></p>').join('')+'</td></tr>';
  }
  $('ev-table').innerHTML='<caption class="sr">Evidence behind the recommendation</caption><thead><tr><th scope="col">Measure</th><th scope="col">Value</th><th scope="col">Evidence class</th></tr></thead><tbody>'+body+'</tbody>';
  $('ev-limits').innerHTML=(V.limits||[]).length?'<h4 style="margin-top:20px">Disclosed limitations</h4><ul class="small">'+V.limits.map(l=>'<li>'+esc(l)+'</li>').join('')+'</ul>':'';
}

/* ---------- dependency chain (layered: evidence -> calculation -> conclusion) ---------- */
const LAYERS=[['Evidence',['source','measurement','price','context']],['Calculation',['economics']],['Conclusion',['recommendation']]];
function renderChain(){
  const recs=V.path||[];let h='';
  for(const [name,roles] of LAYERS){
    const rs=recs.filter(r=>roles.includes(r.role)||(name==='Evidence'&&!LAYERS.some(l=>l[1].includes(r.role))));
    if(!rs.length)continue;
    h+='<li class="layer"><span class="kind">'+esc(name)+'</span></li>';
    h+=rs.map(r=>{
      const st=r.state;
      const why=st==='changed'?'Scenario input · revision '+r.revision+(r.note?' — '+r.note:''):st==='derived'?'Formed from the scenario price; carries the scenario label':st==='stale'?(r.why||'Pins an older revision of an input'):st==='blocked'?(r.why||'Blocked'):'';
      const pins=(r.deps||[]).map(d=>d.id+' v'+d.revision+(d.current_revision&&d.current_revision!==d.revision?' → latest v'+d.current_revision:'')).join(' · ');
      return '<li class="'+esc(st)+'"><span class="dot" aria-hidden="true"></span><div><span class="kind">'+esc(r.roleLabel)+' · v'+esc(r.revision)+' · '+esc(STATE_LABEL[st]||st)+'</span><span class="title">'+esc(r.title)+'</span>'+(why?'<span class="why">'+esc(why)+'</span>':'')+(pins?'<span class="pin">pins '+esc(pins)+'</span>':'')+'</div></li>';
    }).join('');
  }
  $('chain').innerHTML=h||'<li><div class="small">No dependency path.</div></li>';
}

/* ---------- change input ---------- */
function renderChange(){
  const inputs=V.inputs||[];
  const f=$('form-change');
  if(!inputs.length){f.innerHTML='<p class="small">No editable inputs in this case.</p>';return;}
  const keep=document.activeElement&&f.contains(document.activeElement)?document.activeElement.name:null;
  f.innerHTML=inputs.map((i,n)=>'<fieldset style="border:0;padding:0;margin:0;display:grid;gap:8px"><legend class="small" style="padding:0">'+esc(i.kindLabel||(i.kind==='price'?'Price assumption':'Source assumption'))+' · now v'+esc(i.revision||1)+'</legend>'+
    '<label>'+esc(i.label)+(i.unit?' ('+esc(i.unit)+')':'')+'<input name="v'+n+'" data-id="'+esc(i.id)+'" value="'+esc(i.value)+'" '+(i.type==='number'?'type="number" step="any" inputmode="decimal"':'')+'></label>'+
    (i.help?'<p class="small" style="margin:0">'+esc(i.help)+'</p>':'')+'</fieldset>').join('')+
    '<label>Why the change <input name="note" maxlength="300" placeholder="e.g. hypothetical A/T0 price for sensitivity analysis"></label>'+
    '<div class="actions"><button type="submit" id="btn-change">Apply change</button><button type="button" class="primary" id="btn-recompute"'+(V.canRecompute?'':' hidden')+'>Recompute successor</button></div>'+
    '<p class="small" style="margin:0">'+esc(V.scenarioNote||'A price change is a scenario. It does not refresh supply or alter any measured result.')+'</p>';
  if(keep&&f.elements[keep])f.elements[keep].focus();
}

/* ---------- review / deliveries ---------- */
function renderReview(){
  const rv=V.review||{};let h='';
  if(rv.ready)h='<div class="notice ok">Reviewed and current: '+esc(rv.bound.reviewer)+' · '+esc(rv.bound.decision)+' · '+esc(when(rv.bound.at))+'<br><span class="small">'+esc(rv.bound.rationale)+'</span></div>';
  else if(rv.bound&&rv.bound.decision!=='accept')h='<div class="notice bad">Latest review for this exact state is <strong>'+esc(rv.bound.decision)+'</strong>. It cannot be issued.</div>';
  else if(rv.previous)h='<div class="notice pink">The earlier review by '+esc(rv.previous.reviewer)+' was bound to a different set of inputs. This version needs its own review.</div>';
  else h='<p class="small">No review is bound to the current state.</p>';
  $('review-state').innerHTML=h;
  const fz=$('btn-freeze');fz.disabled=false;fz.title=rv.ready?'':'Record an accepting review of the current state first';
  const snaps=V.snapshots||[];
  $('deliveries').innerHTML=snaps.length?snaps.slice().reverse().map((s,i)=>'<li class="'+(i===0?'latest':'')+'"><strong>Version '+esc(s.n)+(i===0?' · latest':' · historical, unchanged')+'</strong><span>'+esc(s.title||'')+'</span><span class="small">Reviewed by '+esc(s.reviewer)+' · '+esc(when(s.at))+'</span><span class="mono">sha256 '+esc(s.sha256)+'</span><div class="actions"><button type="button" class="quiet" data-open-report="'+esc(s.index)+'">Open report</button><button type="button" class="quiet" data-dl-report="'+esc(s.index)+'">Download</button></div></li>').join(''):'<li class="small">Nothing issued yet.</li>';
}

/* ---------- timeline ---------- */
function renderTimeline(){
  const t=V.timeline||[],seedActor=t.length?t[0].actor:null;
  const seed=t.filter(e=>e.actor===seedActor&&e.cls!=='review'&&e.cls!=='freeze'&&e.at===t[0].at),rest=t.filter(e=>!seed.includes(e));
  const li=e=>'<li class="'+esc(e.cls||'')+'"><time datetime="'+esc(e.at)+'">'+esc(when(e.at))+' · #'+esc(e.seq)+'</time>'+esc(e.text)+(e.actor?' <span class="small">— '+esc(e.actor)+'</span>':'')+'</li>';
  let h=rest.slice().reverse().map(li).join('');
  if(seed.length)h+='<li><time datetime="'+esc(seed[0].at)+'">'+esc(when(seed[0].at))+' · #1–'+esc(seed[seed.length-1].seq)+'</time>Workspace opened with '+seed.length+' records from public evidence <span class="small">— '+esc(seedActor)+'</span><details><summary class="small">Show the seeded records</summary><ol class="timeline">'+seed.map(li).join('')+'</ol></details></li>';
  $('timeline').innerHTML=h||'<li class="small">No events yet.</li>';
  if(!rest.length)$('timeline').insertAdjacentHTML('afterbegin','<li class="small">Nothing changed yet. Reviews, price changes and issued versions appear here, newest first.</li>');
}

/* ---------- drawer ---------- */
function renderDrawer(){
  const a=V.architecture||{};let h='';
  if(a.summary)h+='<p>'+esc(a.summary)+'</p>';
  for(const g of a.groups||[]){h+='<section><h4>'+esc(g.title)+'</h4>'+(g.note?'<p class="small">'+esc(g.note)+'</p>':'')+'<ul class="owners">'+(g.items||[]).map(i=>'<li><strong>'+esc(i.name)+'</strong>'+(i.status?' '+tag(i.status,i.statusLabel):'')+'<br><span class="small">'+esc(i.role||'')+'</span>'+(i.path?'<br><span class="mono">'+esc(i.path)+'</span>':'')+'</li>').join('')+'</ul></section>';}
  if(V.records&&V.records.length)h+='<section><h4>Every record in this workspace</h4><div class="table-scroll" tabindex="0" role="region" aria-label="All records"><table><thead><tr><th>Record</th><th>Kind</th><th>Rev</th><th>Tier</th><th>State</th></tr></thead><tbody>'+V.records.map(r=>'<tr><td>'+esc(r.title)+'<span class="caveat mono">'+esc(r.id)+'</span></td><td>'+esc(r.kind)+'</td><td class="num">'+esc(r.revision)+'</td><td>'+tag(r.tier)+'</td><td>'+esc(STATE_LABEL[r.state]||r.state||'')+'</td></tr>').join('')+'</tbody></table></div></section>';
  for(const r of (R.records||[])){
    if(r.role==='measurement'){
      const data=r.data||{},identity=data.identity||{};
      h+='<section><h4>'+esc(r.title)+' · recipe identity</h4><dl>'+Object.entries(identity).map(([k,v])=>'<dt class="small">'+esc(k.replace(/_/g,' '))+'</dt><dd class="mono" style="margin:0 0 10px">'+esc(v)+'</dd>').join('')+'</dl>';
      if(data.grading&&data.grading.registered)h+='<p class="small">'+esc(data.grading.registered)+'</p>';
      if(data.window&&data.window.basis)h+='<p class="small">'+esc(data.window.basis)+'</p>';
      h+='</section>';
    }
    if(r.role==='context')h+='<section><h4>'+esc(r.title)+'</h4><p>'+esc(r.summary)+'</p>'+(r.data&&r.data.funding?'<p class="small">'+esc(r.data.funding)+'</p>':'')+'</section>';
  }
  if(V.build)h+='<section><h4>This build</h4><p class="mono">'+esc(V.build)+'</p></section>';
  $('drawer-body').innerHTML=h||'<p class="small">Architecture map not supplied.</p>';
}
let lastFocus=null;
function openDrawer(open){const d=$('drawer');d.dataset.open=String(open);d.setAttribute('aria-hidden',String(!open));$('btn-arch').setAttribute('aria-expanded',String(open));document.body.style.overflow=open?'hidden':'';if(open){lastFocus=document.activeElement;d.querySelector('.sheet').focus();}else if(lastFocus)lastFocus.focus();}

/* ---------- render ---------- */
function render(){
  V=normalize(R);
  $('case-line').innerHTML=esc(V.caseLine||'');
  renderRec();renderEvidence();renderChain();renderChange();renderReview();renderTimeline();renderDrawer();guide();
  $('foot-build').textContent=V.build||'';
}

/* ---------- report open/download ---------- */
function download(name,text,type){const b=new Blob([text],{type:type||'application/json'});const u=URL.createObjectURL(b);const a=document.createElement('a');a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000);}
async function reportText(seq){const r=await D.reportHTML(Number(seq));if(r&&r.ok===false)throw new Error(r.error);return typeof r==='string'?r:(r.html||r.text||'');}
async function report(seq,dl){const html=await reportText(seq);const name='cantos-report-'+seq+'.html';if(dl){download(name,html,'text/html');return;}const w=window.open('','_blank');if(!w){download(name,html,'text/html');return;}w.opener=null;w.document.open();w.document.write(html);w.document.close();}

/* ---------- wiring ---------- */
function reviewerName(){return ($('form-review').elements.reviewer.value||'').trim()||'Local operator';}
function wire(){
  $('form-review').addEventListener('submit',e=>{e.preventDefault();const f=e.currentTarget.elements;const reviewer=f.reviewer.value.trim(),rationale=f.rationale.value.trim();if(!reviewer||!rationale){toast('Enter a reviewer and a rationale.','bad');(reviewer?f.rationale:f.reviewer).focus();return;}
    act($('btn-review'),()=>D.review({target:V.target,decision:f.decision.value,rationale,reviewer}),'Review recorded against the exact inputs shown in the path.').then(r=>{if(r)f.rationale.value='';});});
  $('btn-freeze').addEventListener('click',e=>{if(!(V.review&&V.review.ready)){toast('Record an accepting review of the current state first.','bad');$('form-review').elements.reviewer.focus();return;}
    act(e.currentTarget,()=>D.freeze({target:V.target,reviewer:reviewerName()}),'Issued. Earlier versions remain unchanged.').then(r=>{if(r)flash($('deliveries'));});});
  $('form-change').addEventListener('submit',e=>{e.preventDefault();const f=e.currentTarget;const inp=f.querySelector('input[data-id]');const rate=Number(inp&&inp.value);if(!inp||inp.value===''||!(rate>=0)){toast('Enter a price in USD per GPU-hour.','bad');return;}const note=(f.elements.note.value||'').trim()||'Illustrative price scenario';
    act($('btn-change'),()=>D.priceScenario({rate,note,actor:reviewerName()}),'Price changed as a scenario. Dependent records are marked stale; nothing was recomputed silently.').then(r=>{if(r){flash($('chain'));flash($('rec'));}});});
  $('form-change').addEventListener('click',e=>{if(e.target.id==='btn-recompute')act(e.target,()=>D.recompute({actor:reviewerName()}),'Successor formed through the native engine. It needs a fresh review before it can be issued.').then(r=>{if(r)flash($('rec'));});});
  $('deliveries').addEventListener('click',e=>{const o=e.target.closest('[data-open-report]'),d=e.target.closest('[data-dl-report]');if(o)report(o.dataset.openReport,false).catch(x=>toast(x.message,'bad'));if(d)report(d.dataset.dlReport,true).catch(x=>toast(x.message,'bad'));});
  $('btn-export').addEventListener('click',e=>act(e.currentTarget,async()=>{const p=await D.exportPacket();if(p&&p.ok===false)return p;download(p.name||'cantos-packet.json',p.text);exported=p.sha256||true;return {ok:true};},()=>'Packet saved'+(typeof exported==='string'?' (sha256 '+short(exported)+')':'')+'. Keep it: this page stores nothing on its own.'));
  $('btn-restore').addEventListener('click',()=>$('file-restore').click());
  $('file-restore').addEventListener('change',async e=>{const file=e.target.files[0];e.target.value='';if(!file)return;const text=await file.text();act($('btn-restore'),()=>D.importPacket(text),'Packet verified by replay and restored.');});
  $('btn-arch').addEventListener('click',()=>openDrawer(true));
  $('drawer').addEventListener('click',e=>{if(e.target.closest('[data-close]'))openDrawer(false);});
  document.addEventListener('keydown',e=>{
    if($('drawer').dataset.open!=='true')return;
    if(e.key==='Escape'){e.preventDefault();openDrawer(false);return;}
    if(e.key==='Tab'){
      const sheet=$('drawer').querySelector('.sheet');
      const items=[...sheet.querySelectorAll('button,a[href],input,select,textarea,[tabindex]')].filter(x=>!x.disabled&&x.tabIndex>=0&&x.getClientRects().length);
      if(!items.length){e.preventDefault();sheet.focus();return;}
      const first=items[0],last=items[items.length-1],active=document.activeElement;
      if(e.shiftKey&&(active===first||active===sheet||!sheet.contains(active))){e.preventDefault();last.focus();}
      else if(!e.shiftKey&&(active===last||active===sheet||!sheet.contains(active))){e.preventDefault();first.focus();}
    }
  });
}
let exported=false;

/* ---------- bridge adapter: the single seam between the UI and CantosDesk.view() ---------- */
const ROLE_LABEL={source:'Source',measurement:'Measured result',price:'Price',economics:'Cost calculation',recommendation:'Recommendation',context:'Context'};
const TIER_LABEL={public_observation:'public observation',operator_supplied:'operator reported',synthetic:'synthetic',proposal:'scenario'};
const METRIC_LABEL={accepted:['Accepted requests',''],completed:['Completed requests',''],scheduled:['Scheduled requests',''],correct_raw:['Correct, registered raw grade',''],acceptance_rate:['Acceptance rate','%'],ttft_p50_ms:['Time to first token p50','ms'],ttft_p95_ms:['Time to first token p95','ms'],ttft_p99_ms:['Time to first token p99','ms']};
function fmtNum(k,v){if(typeof v!=='number')return String(v);if(k==='acceptance_rate')return (v*100).toFixed(1)+' %';const u=(METRIC_LABEL[k]||[])[1];return v.toLocaleString('en-US')+(u&&u!=='%'?' '+u:'');}
function money(n,d){return typeof n==='number'&&isFinite(n)?'$'+n.toFixed(d==null?2:d):'—';}
function priceOf(r,byId){return (r.deps||[]).map(x=>byId[x.id]).find(p=>p&&p.role==='price');}
function normalize(raw){
  const v=raw||{},out={raw:v};
  const recs=v.records||[],byId={};for(const r of recs)byId[r.id]=r;
  const rec=v.recommendation||{};
  out.target=rec.id||(v.case&&v.case.target);
  out.caseLine=(v.case&&(v.case.question||v.case.title))||'';
  const status=rec.status||'reviewed';
  const st=status==='stale'?'stale':status==='blocked'?'blocked':'current';
  const econ=recs.filter(r=>r.role==='economics');
  out.recommendation={
    revision:rec.revision,text:rec.summary||rec.title,state:st,status,scenario:!!rec.scenario,tier:rec.tier,disposition:rec.disposition,
    blockers:(rec.dependency&&rec.dependency.blockers)||[],
    conditions:(rec.conditions||[]).concat((rec.holds_unless||[]).map(x=>'Reassess if '+String(x).replace(/^[A-Z](?=[a-z])/,c=>c.toLowerCase()))),
    scope:rec.scenario?'This version was formed under a price scenario. The measured results it rests on are unchanged.':'',
    figures:econ.map(r=>{const d=r.derived||{},price=priceOf(r,byId),o=(price&&price.offer)||{};
      return {label:[o.provider,o.gpu].filter(Boolean).join(' ')+' · per 1,000 accepted',value:d.usd_per_1k_accepted!=null?money(d.usd_per_1k_accepted):'—',
        scope:[o.rate!=null?money(o.rate)+'/GPU-hour':'',price&&price.data&&price.data.scope,r.stale?'stale: pins an older price':'',d.verified===false?'recomputation did not verify':''].filter(Boolean).join(' · '),
        tier:r.scenario?'proposal':r.tier,tierLabel:r.scenario?'scenario':TIER_LABEL[r.tier],changed:!!(r.scenario||r.stale)};})
  };
  const rv=rec.review||{};const reviews=(v.reviews||[]).filter(x=>x.target===out.target);
  out.review={ready:!!rv.ready,bound:rv.review||null,previous:!rv.review&&reviews.length?reviews[reviews.length-1]:null};
  const ev=[],limits=[];
  for(const r of recs){
    const src=r.source||{},date=src.observed_on||'';const sref=src.relative_path?src.relative_path+(src.sha256?' · sha256 '+short(src.sha256):''):'';
    if(r.role==='measurement'&&r.metrics){
      for(const [k,val] of Object.entries(r.metrics))ev.push({group:r.title,label:(METRIC_LABEL[k]||[k.replace(/_/g,' ')])[0],value:fmtNum(k,val),tier:'measured',tierLabel:'measured · '+(TIER_LABEL[r.tier]||r.tier),scope:(r.data&&r.data.window&&r.data.window.basis)||'',date,source:sref,href:src.url});
      const ph=r.data&&r.data.grading&&r.data.grading.posthoc;if(ph&&typeof ph==='object')for(const [k,val] of Object.entries(ph))if(k!=='label')ev.push({group:r.title,label:k.replace(/_/g,' '),value:typeof val==='number'?val.toLocaleString('en-US'):String(val),tier:'posthoc',tierLabel:ph.label||'post-hoc, not registered',caveat:'Outside the registered result; the deadline-qualified accepted count was not recomputed for it.',date,source:sref,href:src.url});
    }
    if(r.role==='price'&&r.offer)ev.push({group:'Prices',label:[r.offer.provider,r.offer.gpu].filter(Boolean).join(' ')+' list price'+(r.scenario?' (scenario)':''),value:money(r.offer.rate)+'/GPU-hour',tier:r.scenario?'proposal':r.tier,tierLabel:r.scenario?'scenario, not a quote':TIER_LABEL[r.tier],scope:[r.data&&r.data.billing,r.data&&r.data.scope].filter(Boolean).join(' · '),date:r.scenario?'':(date||r.offer.reviewedOn||''),source:sref,href:src.url});
    for(const l of r.limitations||[])if(!limits.includes(l))limits.push(l);
  }
  ev.sort((a,b)=>(a.group==='Prices')-(b.group==='Prices'));out.evidence=ev;out.limits=limits;
  out.evidenceNote=(v.boundaries&&v.boundaries.evidence)||'';
  const nodeState={};for(const n of ((v.path&&v.path.nodes)||[]))nodeState[n.id]=n.state;
  out.path=recs.map(r=>{const ns=nodeState[r.id]||(r.stale?'stale':'current');return {id:r.id,role:r.role,roleLabel:ROLE_LABEL[r.role]||r.kind,title:r.title,revision:r.revision,deps:r.deps,
    state:ns==='scenario'?(r.role==='price'?'changed':'derived'):ns,note:r.scenario&&v.scenario?v.scenario.note:'',why:((r.dependency&&r.dependency.blockers)||[]).join(' · ')};});
  const sc=v.scenario||{};const prices=recs.filter(r=>r.role==='price');
  const tp=prices.find(p=>p.scenario)||prices.find(p=>p.offer&&p.offer.rate===sc.base_rate)||prices[prices.length-1];
  out.inputs=tp?[{id:tp.id,kind:'price',label:[tp.offer&&tp.offer.provider,tp.offer&&tp.offer.gpu].filter(Boolean).join(' ')+' hourly price',unit:sc.unit||'USD per GPU-hour',value:sc.rate!=null?sc.rate:(tp.offer&&tp.offer.rate),type:'number',revision:tp.revision,changed:!!sc.active,
    help:'Dated list price '+money(sc.base_rate!=null?sc.base_rate:(tp.offer&&tp.offer.rate))+((tp.source&&tp.source.observed_on)?', observed '+tp.source.observed_on:'')+'. '+(tp.data&&tp.data.scope||'')}]:[];
  out.scenarioNote=(v.boundaries&&v.boundaries.scenario)||'A price change is a scenario. It does not refresh supply, availability or any measured result.';
  out.canRecompute=st==='stale';
  out.snapshots=(v.deliveries||[]).map((d,i)=>({n:i+1,index:d.seq,sha256:d.snapshot_hash,at:d.at,reviewer:d.reviewer,title:'Recommendation v'+d.revision+(d.scenario?' · under a price scenario':'')+(d.current?' · matches current inputs':'')}));
  out.timeline=(v.timeline||[]).map(e=>({seq:e.seq,at:e.at,actor:e.actor,cls:e.type==='freeze'?'freeze':e.type==='review'?'review':(e.revision>1?'change':''),
    text:e.type==='freeze'?'Issued '+(e.target||'')+' v'+(e.revision||''):e.type==='review'?'Review of '+(e.target||'')+(e.summary?': '+e.summary:''):((e.revision>1?'Revised ':'Recorded ')+(e.kind||'')+' '+(e.target||'')+' v'+(e.revision||'')+(e.scenario?' (scenario)':'')+(e.summary?' — '+e.summary:''))}));
  out.recomputed=recs.some(r=>r.role==='recommendation'&&r.revision>1);
  out.records=recs.map(r=>({id:r.id,title:r.title,kind:r.kind,revision:r.revision,tier:r.scenario?'proposal':r.tier,state:r.stale?'stale':r.scenario?'changed':'current'}));
  out.architecture=architecture(v);
  const id=v.identity||{};out.build=['Research Desk core '+(id.research_core_version||'?')+' sha256 '+short(id.research_core_sha256),'compute '+(id.compute_version||'?')+' '+short(id.compute_sha256),'seed '+(id.seed_status||'?')+' '+short(id.seed_sha256)].join(' · ');
  out.exported=!!exported;
  return out;
}
function seedJSON(){try{return JSON.parse(document.getElementById('cantos-seed').textContent);}catch(e){return {};}}
function architecture(v){
  const seed=seedJSON(),a=seed.architecture||{};const b=v.boundaries||{};
  const groups=(a.groups||[]).slice();
  const bounds=Object.entries(b).map(([k,t])=>({name:k[0].toUpperCase()+k.slice(1),role:t}));
  if(bounds.length)groups.push({title:'Boundaries this page keeps',items:bounds});
  return {summary:a.summary||'The page is a thin view over existing owners. The Research Desk core keeps the journal, revisions, dependency pins, reviews and snapshots; the compute engine prices a seat. Nothing here replaces either.',groups};
}

async function boot(){
  D=window.CantosDesk;
  if(!D){$('rec-body').innerHTML='<div class="notice bad">The research foundation did not load. Open the built page produced by research-desk/cantos/build.py.</div>';return;}
  wire();
  try{const r=await D.ready();if(r&&r.ok===false)throw new Error(r.error);R=D.view();render();if(D.subscribe)D.subscribe(v=>{R=v;});}
  catch(e){$('rec-body').innerHTML='<div class="notice bad">'+esc(e.message||e)+'</div>';}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
window.CantosPage={get view(){return V;}};
})();
