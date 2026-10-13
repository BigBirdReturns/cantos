#!/usr/bin/env node
'use strict';
// Checks the published Chapek seat page against the owners in this tree. The page embeds, unchanged,
// app/source/research-core.js (decision record) and compute/capacity/index.html (server economics,
// saved-input slot filled). Every number it shows is priced by compute/capacity/capacity.cjs and the
// Compute engine. If either owner changes, this check fails until the page is rebuilt against it.
// Since edition 5 the record may carry a recommendation written before its inputs changed: that is the
// record's own dependency state, shown on the first screen, and is accepted here as long as every blocker
// names a later revision present in the same record and nothing has been signed off.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),vm=require('node:vm');
const HERE=__dirname,ROOT=path.join(HERE,'..','..'),sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const C=require(path.join(ROOT,'app/source/research-core.js')),A=require(path.join(ROOT,'compute/capacity/capacity.cjs'));
const BOOT_EMPTY='<script type="application/json" id="boot">null</script>',CONTACT='bigbirdreturns@proton.me';
const checks=[];const must=(ok,m)=>{if(!ok)throw Error(m);};const pass=(name,detail)=>{checks.push(name);console.log('PASS '+name+(detail?' :: '+detail:''));};
const scriptsOf=html=>[...html.matchAll(/<script(\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m=>({attrs:(m[1]||'').trim(),body:m[2]}));
(async()=>{
 const html=fs.readFileSync(path.join(HERE,'index.html'),'utf8');must(!html.includes('\r'),'Page must use LF line endings.');
 const fm=html.match(/<iframe id="capacity-frame"[^>]*?srcdoc="([^"]*)"><\/iframe>/);must(fm,'Server instrument frame missing.');
 const parent=html.replace(fm[1],''),srcdoc=fm[1].replace(/&quot;/g,'"').replace(/&amp;/g,'&'),ps=scriptsOf(parent),exec=ps.filter(s=>!s.attrs);
 must(ps.length===3&&exec.length===2&&ps[0].attrs.includes('id="seed-packet"'),'Unexpected script inventory.');exec.forEach(s=>new vm.Script(s.body));
 must(exec[0].body===fs.readFileSync(path.join(ROOT,'app/source/research-core.js'),'utf8'),'Embedded ResearchCore differs from app/source/research-core.js.');
 must(parent.includes("connect-src 'none'")&&!/\s(src|href)=["']?https?:/i.test(parent.replace(/<a [^>]*>/g,'')),'Page loads external resources or lacks its CSP.');
 pass('embedded_research_core_and_csp','ResearchCore byte-identical to the tree; only <a> links are external; connect-src none');
 const bm=srcdoc.match(/<script type="application\/json" id="boot">([\s\S]*?)<\/script>/);must(bm,'Instrument saved-input slot missing.');
 must(srcdoc.replace(bm[0],()=>BOOT_EMPTY)===fs.readFileSync(path.join(ROOT,'compute/capacity/index.html'),'utf8'),'Embedded instrument differs from compute/capacity/index.html; rebuild the page.');
 scriptsOf(srcdoc).filter(s=>!s.attrs).forEach(s=>new vm.Script(s.body));pass('embedded_instrument_matches_tree','compute/capacity/index.html byte-identical except its saved-input slot');
 const seed=C.parse(ps[0].body),ws=await C.verifyPacket(seed),s=C.state(ws);must(s.reviews.length===0&&s.reports.length===0,'Delivered record must carry no reviews or sign-offs.');
 const ds=C.dependencyState(s,'target-choice');
 if(!ds.current)for(const b of ds.blockers){const m=b.match(/^([A-Za-z0-9_.:-]+): pinned v(\d+), current v(\d+)$/);must(m&&C.latest(s,m[1])&&C.latest(s,m[1]).revision===+m[3]&&+m[3]>+m[2],'A blocker does not name a later revision in this record: '+b);}
 pass('decision_record_verifies',ws.events.length+' events replay through ResearchCore '+C.VERSION+'; '+(ds.current?'current draft':'draft flagged by its own inputs ('+ds.blockers.join('; ')+')')+'; no reviews');
 const procs=Object.values(s.records).map(rs=>rs.at(-1)).filter(r=>r.kind==='claim'&&r.data&&r.data.work);
 for(const pr of procs){const w=pr.data.work;must(Object.keys(w).sort().join(',')==='computation_key,task'&&/^[0-9a-f]{64}$/.test(w.computation_key)&&!('id'in w.task)&&!('actor'in w.task)&&C.dependencyState(s,pr.id).current,'Retained procedure malformed or stale: '+pr.id);}
 pass('retained_procedures_well_formed',procs.length+' retained procedures carry a native task and a 64-hex computation key and are current');
 const a=C.latest(s,'allocation-scenario'),p=a.data.capacity_packet;must(C.canonical(p)===C.canonical(JSON.parse(bm[1])),'Record numbers and instrument slot differ.');
 must(sha(Buffer.from(p.body_json,'utf8'))===p.sha256,'Numbers checksum mismatch.');const b=A.verifyBody(JSON.parse(p.body_json));
 pass('server_numbers_recompute','$'+b.result.charge.gpuCharge.toFixed(2)+' for '+b.input.committedHours+' h recomputed through capacity.cjs and the Compute engine');
 const money=new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(b.result.charge.gpuCharge);
 const ex=parent.match(/<strong>Worked example\.<\/strong> ([^<]*)/);must(ex&&ex[1].includes(money),'No-JavaScript worked example does not state the numbers in use ('+money+').');
 if(a.data.price_source&&a.data.price_source.commitment)must(ex[1].includes('annual term')&&a.data.price_source.commitment.includes('twelve months'),'Commitment basis must be stated wherever the changed economics appear.');
 pass('worked_example_states_numbers_in_use',money+(a.data.price_source&&a.data.price_source.commitment?' as the monthly equivalent under the annual term, commitment basis stated':''));
 const ZIP='Cantos-Chapek-Seat-package.zip',link=parent.match(/href="(https:\/\/bigbirdreturns\.github\.io\/cantos\/compute\/chapek\/Cantos-Chapek-Seat-package\.zip)"/);
 must(link&&fs.existsSync(path.join(HERE,ZIP))&&fs.statSync(path.join(HERE,ZIP)).size<20*1024*1024,'The page must link the package zip beside it (tests/package_check.py verifies its contents).');
 pass('package_download_linked_and_present',ZIP+' · '+fs.statSync(path.join(HERE,ZIP)).size+' bytes');
 must(parent.includes('Jonathan Sandhu')&&parent.includes('href="mailto:'+CONTACT+'"'),'Author or contact missing.');
 const emails=[...new Set((html.replace(exec[0].body,'').match(/[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}/g)||[]))];must(emails.length===1&&emails[0]===CONTACT,'Unexpected email addresses: '+emails.join(', '));
 must(!/[A-Z]:[\\/](Projects|Users)/.test(html),'Local file paths in the page.');pass('author_contact_only_and_no_local_paths',CONTACT);
 console.log(JSON.stringify({status:'PASS',checks:checks.length,sha256:sha(Buffer.from(html,'utf8')),scope:'Published bytes against the owners in this tree. Browser behaviour: tests/browser_check.py.'}));
})().catch(e=>{console.error('FAIL '+e.message);process.exit(1);});
