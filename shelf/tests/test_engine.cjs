'use strict';
// The engine embedded in index.html must agree with scripts/shelf.py on the shared fixture.
// Run: node --test shelf/tests/test_engine.cjs
const test=require('node:test'),a=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{execFileSync}=require('node:child_process');
const TOOL=path.join(__dirname,'..');
const html=fs.readFileSync(path.join(TOOL,'index.html'),'utf8');
const m=html.match(/<script id="shelf-engine">([\s\S]*?)<\/script>/);
if(!m)throw new Error('shelf-engine script missing from index.html');
vm.runInThisContext(m[1],{filename:'index.html#shelf-engine'});const S=globalThis.Shelf;
const cases=JSON.parse(fs.readFileSync(path.join(__dirname,'cases.json'),'utf8'));
const parseCards=t=>{t=t.replace(/^﻿/,'');try{const v=JSON.parse(t);return Array.isArray(v)?v:[v];}catch(e){return t.split(/\r?\n/).filter(l=>l.trim()).map(l=>JSON.parse(l));}};
const CARDS=parseCards(fs.readFileSync(path.join(TOOL,'data','cards.jsonl'),'utf8'));
const BY=Object.fromEntries(CARDS.map(c=>[c.id,c]));
const py=args=>{try{return execFileSync(process.env.PYTHON||'python',['-B',path.join(TOOL,'scripts','shelf.py'),...args],{encoding:'utf8'});}catch(e){if(typeof e.stdout==='string'&&e.stdout)return e.stdout;throw e;}};

test('engine exposes the same surface as the CLI',()=>{for(const k of['validateCard','compose','which','observationDate','inPeriod'])a.equal(typeof S[k],'function');a.deepEqual(S.PURPOSES,['cost_per_accepted','accepted_work','seat_property','measured_cost','same_period']);});
test('five shelf cards pass the filing check in the browser engine',()=>{for(const c of CARDS)a.deepEqual(S.validateCard(c),[],c.id);});
for(const v of cases.validate)test('validate fixture '+v.file,()=>{const card=parseCards(fs.readFileSync(path.join(__dirname,v.file),'utf8'))[0];const errors=S.validateCard(card);a.equal(errors.length,v.expect_errors,JSON.stringify(errors));for(const needle of v.contains||[])a.ok(errors.some(e=>e.includes(needle)),needle);});
test('validate error strings match Python exactly on the failing stranger card',()=>{const file=path.join(__dirname,'fixtures','card6-latitude-h100.json');const card=parseCards(fs.readFileSync(file,'utf8'))[0];const js=S.validateCard(card);const out=py(['validate',file]).split(/\r?\n/).filter(l=>l.startsWith('[FAIL')).map(l=>l.replace(/^\[FAIL\s*\] [^:]+: /,''));a.deepEqual(js,out);});
for(const c of cases.compose)test('compose '+c.a+' x '+c.b+' for '+c.purpose,()=>a.equal(S.compose(BY[c.a],BY[c.b],c.purpose),c.expect));
test('compose refuses an unknown purpose and a missing operand',()=>{a.match(S.compose(BY['run3-at0'],BY['run3-at0'],'rank'),/unknown purpose/);a.match(S.compose(BY['run3-at0'],null,'same_period'),/missing operand/);});
for(const w of cases.which)test('which: '+w.name,()=>{const rows=S.which(CARDS,w.unit,w.period,w.measured);a.deepEqual(Object.fromEntries(rows.map(r=>[r.id,r.status])),w.expect);for(const[id,needle]of Object.entries(w.reason_contains||{}))a.ok(rows.find(r=>r.id===id).reason.includes(needle),needle);});
test('which output is byte-identical between the browser engine and the CLI',()=>{for(const w of cases.which){const args=['which',path.join(TOOL,'data','cards.jsonl'),'--unit',w.unit,'--json'];if(w.period)args.push('--period',w.period);if(w.measured)args.push('--measured');const pyRows=JSON.parse(py(args));a.deepEqual(S.which(CARDS,w.unit,w.period,w.measured),pyRows,w.name);}});
test('period forms',()=>{a.ok(S.inPeriod('2026-09-24','2026'));a.ok(S.inPeriod('2026-09-24','2026-09'));a.ok(!S.inPeriod('2026-09-24','2026-08'));a.ok(S.inPeriod('2026-09-24','2026-09-01..2026-09-30'));a.ok(!S.inPeriod('2026-10-01','2026-09-01..2026-09-30'));});
test('retrieval never supplies the observation date',()=>{const c=JSON.parse(JSON.stringify(BY['hotaisle-blog']));c.a_claim.period.retrieved_at='2026-09-24';a.equal(S.observationDate(c),null);});
test('page has no external requests: no remote script, style, font or frame',()=>{a.ok(!/<(script|link|iframe|img)[^>]+(src|href)=["']https?:/i.test(html));a.ok(!/@import|fonts\.googleapis|fonts\.gstatic/i.test(html));});
