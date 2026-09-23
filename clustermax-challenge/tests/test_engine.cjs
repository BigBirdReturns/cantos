'use strict';
// Node.js parity check for the engine embedded in index.html; no npm dependencies.
// Every case below is scored by BOTH engines and the full result objects must be identical
// (same numbers bit for bit, same HOLD reasons). Python remains the reference scorer.
const fs=require('fs'),os=require('os'),path=require('path'),vm=require('vm'),crypto=require('crypto'),cp=require('child_process');
const root=path.resolve(__dirname,'..');
const PYTHON=process.env.PYTHON||(process.platform==='win32'?'python':'python3');
const VARIANTS=['demo','demo-shuffled','demo-level-shift'];
cp.execFileSync(PYTHON,[path.join(root,'scripts/make_demo.py')]);
for(const v of VARIANTS)cp.execFileSync(PYTHON,[path.join(root,'scripts/challenge.py'),'--plan',path.join(root,'data',v+'-plan.json'),'--binding',path.join(root,'data',v+'-binding.json'),'--outcomes',path.join(root,'data',v+'-outcomes.json'),'--output',path.join(root,'data',v+'-result.json')]);
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const ctx={module:{exports:{}}};vm.runInNewContext(html.match(/<script id="engine">([\s\S]*?)<\/script>/)[1],ctx);
const e=ctx.module.exports,sha=b=>crypto.createHash('sha256').update(b).digest('hex');let checks=0;
function check(condition,message){if(!condition)throw Error(message);checks++}
function diff(a,b,p,out){if(typeof a==='number'&&typeof b==='number'){if(!Object.is(a,b)&&a!==b)out.push(p+': js '+a+' vs py '+b);return}
  if(a===null||b===null||typeof a!=='object'||typeof b!=='object'){if(a!==b)out.push(p+': js '+JSON.stringify(a)+' vs py '+JSON.stringify(b));return}
  const ka=Object.keys(a).sort(),kb=Object.keys(b).sort();if(ka.join('\u0000')!==kb.join('\u0000'))out.push(p+': keys js-only ['+ka.filter(k=>!kb.includes(k))+'] py-only ['+kb.filter(k=>!ka.includes(k))+']');
  for(const k of ka)if(Object.prototype.hasOwnProperty.call(b,k))diff(a[k],b[k],p+'.'+k,out)}
function same(js,py,label){const out=[];diff(JSON.parse(JSON.stringify(js)),py,'',out);check(out.length===0,label+' parity:\n  '+out.slice(0,8).join('\n  '))}

// 1. SHA-256 vectors
for(const n of [0,1,3,55,56,63,64,65,127,128,1000,1000000]){let b=Buffer.alloc(n);for(let i=0;i<n;i++)b[i]=(i*173+53)%256;check(e.sha256Local(b)===sha(b),'SHA mismatch: '+n)}
// 2. Embedded registry / published transform are the design files, verbatim
const registry=JSON.parse(fs.readFileSync(path.join(root,'design/registry.json'),'utf8')),transform=JSON.parse(fs.readFileSync(path.join(root,'design/transform.json'),'utf8'));
check(JSON.stringify(e.REGISTRY)===JSON.stringify(registry),'index.html REGISTRY differs from design/registry.json');
check(JSON.stringify(e.PUBLISHED_TRANSFORM)===JSON.stringify(transform),'index.html PUBLISHED_TRANSFORM differs from design/transform.json');
check(registry.transforms.map(t=>t.sha256).join()===e.canonicalSha256(transform),'design/transform.json is not the registered transform');
// 3. Demo fixtures: full-result parity and expected verdicts
const expected={'demo':['positive','exact_enumeration'],'demo-shuffled':['inconclusive','exact_enumeration'],'demo-level-shift':['inconclusive','monte_carlo']};
for(const v of VARIANTS){const rd=f=>fs.readFileSync(path.join(root,'data',v+'-'+f+'.json'));const pb=rd('plan'),bb=rd('binding'),ob=rd('outcomes');
  const r=e.evaluateObjects(JSON.parse(pb),JSON.parse(ob),JSON.parse(bb),sha(pb),sha(ob),sha(bb));same(r,JSON.parse(rd('result')),v);
  check(r.signal===expected[v][0]&&r.medal_permutation_test.method===expected[v][1],v+': expected '+expected[v]+', got '+r.signal+'/'+r.medal_permutation_test.method)}
check(JSON.parse(fs.readFileSync(path.join(root,'data/demo-level-shift-result.json'))).descriptive.comparison_vs_reference.bootstrap_95[0]>0.004,'level-shift fixture no longer reproduces the v1.3 false positive');

// 4. Adversarial / parity cases, scored by both engines
const base={p:JSON.parse(fs.readFileSync(path.join(root,'data/demo-plan.json'))),b:JSON.parse(fs.readFileSync(path.join(root,'data/demo-binding.json'))),o:JSON.parse(fs.readFileSync(path.join(root,'data/demo-outcomes.json')))};
const clone=x=>JSON.parse(JSON.stringify(x));
function pack({plan,binding,outcomes,planText,bindingText,outcomesText}={}){const p=clone(base.p),b=clone(base.b),o=clone(base.o);if(plan)plan(p,b,o);if(binding)binding(b,p,o);if(outcomes)outcomes(o,p,b);
  let pt=JSON.stringify(p,null,2)+'\n';if(planText)pt=planText(pt);b.plan_sha256=o.plan_sha256=sha(Buffer.from(pt));
  let bt=JSON.stringify(b,null,2)+'\n';if(bindingText)bt=bindingText(bt);o.binding_sha256=sha(Buffer.from(bt));
  let ot=JSON.stringify(o,null,2)+'\n';if(outcomesText)ot=outcomesText(ot);return [pt,bt,ot]}
const REG=[['CoreWeave','Platinum'],['Oracle','Gold'],['Google Cloud','Gold'],['Azure','Silver'],['Firmus','Silver'],['Lambda','Silver'],['GMI','Silver'],['AWS','Bronze'],['GCore','Bronze'],['Verda','Bronze']];
function registered(names=REG,digest='79dc81e4cf7a503632c631b69f011f2a7af109e719cc32253344820cda402e02',version='3.0'){return {plan:(p,b,o)=>{const ids=Object.keys(b.medals).sort(),map=Object.fromEntries(ids.map((id,i)=>[id,names[i][0]]));for(const r of [...p.trials,...o.trials])r.provider_id=map[r.provider_id];b.medals=Object.fromEntries(names);for(const x of [p,b]){x.rating_name='ClusterMAX';x.rating_version=version}b.source.sha256=digest}}}
const setTransform=f=>({plan:p=>{f(p.transform);p.transform_sha256=e.canonicalSha256(p.transform)}});
const allRows=f=>({plan:p=>p.trials.forEach(f)});
const cases={
  base:[{},'positive'],
  tier_constructor:[{binding:b=>{b.medals.EXAMPLE_01='constructor'}},'HOLD'],
  tier_toString:[{binding:b=>{b.medals.EXAMPLE_01='toString'}},'HOLD'],
  tier___proto__:[{bindingText:t=>t.replace('"EXAMPLE_01": "Gold"','"EXAMPLE_01": "__proto__"')},'HOLD'],
  provider___proto__:[{planText:t=>t.split('EXAMPLE_01').join('__proto__'),bindingText:t=>t.split('EXAMPLE_01').join('__proto__'),outcomesText:t=>t.split('EXAMPLE_01').join('__proto__')},'positive'],
  accepted_min_integral_float:[{planText:t=>t.split('"accepted_min": 900').join('"accepted_min": 900.0')},'positive'],
  accepted_min_fraction:[{planText:t=>t.split('"accepted_min": 900').join('"accepted_min": 900.5')},'HOLD'],
  minimum_providers_integral_float:[{planText:t=>t.replace('"minimum_providers": 8','"minimum_providers": 8.0')},'positive'],
  accepted_integral_float:[{outcomesText:t=>t.split('"accepted": 1000,').join('"accepted": 1000.0,')},'positive'],
  prediction_0_4ms_after_freeze:[{plan:p=>{p.trials[0].predicted_at='2026-01-02T00:00:00.0004Z'}},'HOLD'],
  fraction_seven_digits:[{plan:p=>{p.trials[0].predicted_at='2026-01-01T12:00:00.1234567+00:00'}},'positive'],
  fraction_truncates_to_freeze:[{plan:p=>{p.trials[0].predicted_at='2026-01-02T00:00:00.0000009Z'}},'positive'],
  bound_before_start_distinct_us:[{binding:b=>{b.bound_at='2026-01-02T23:59:59.999001Z'},outcomes:o=>{o.trials[0].started_at='2026-01-02T23:59:59.999002Z'}},'positive'],
  bound_equals_start_after_truncation:[{binding:b=>{b.bound_at='2026-01-02T23:59:59.9990004Z'},outcomes:o=>{o.trials[0].started_at='2026-01-02T23:59:59.9990009Z'}},'HOLD'],
  year_1969:[{plan:p=>{p.baseline.frozen_at='1969-12-31T00:00:00Z'}},'HOLD'],
  offset_24h:[{plan:p=>{p.trials[0].predicted_at='2026-01-01T12:00:00+24:00'}},'HOLD'],
  offset_0530:[{plan:p=>{p.trials[0].predicted_at='2026-01-01T17:30:00+05:30'}},'positive'],
  feb_29_2026:[{plan:p=>{p.trials[0].predicted_at='2026-02-29T12:00:00Z'}},'HOLD'],
  transform_exponent_float:[setTransform(t=>{t.alternative_weights=[1e-7,0.4]}),'HOLD'],
  transform_integral_float:[setTransform(t=>{t.alternative_weights=[0.1,1.0];t.anchors.Underperforming=0.0}),'HOLD'],
  transform_astral_keys:[setTransform(t=>{t['\u{1F600}k']='x';t['Ａk']='y'}),'HOLD'],
  transform_lone_surrogate:[{plan:p=>{p.transform.description+='\uD800'}},'HOLD'],
  transform_reference_095:[setTransform(t=>{t.reference_anchor=0.95}),'HOLD'],
  transform_inverted_anchors:[setTransform(t=>{t.anchors={Platinum:.1,Gold:.2,Silver:.5,Bronze:.8,Underperforming:.9}}),'HOLD'],
  nonuniform_gates:[allRows(r=>{if(r.provider_id==='EXAMPLE_01')r.gates.cost_max_usd=0.5}),'HOLD'],
  empty_training:[{plan:p=>{p.baseline.training_providers=[];p.with_rating.training_providers=[]}},'HOLD'],
  inverted_medals:[{binding:b=>{for(const k in b.medals)b.medals[k]={Gold:'Bronze',Bronze:'Gold',Silver:'Silver'}[b.medals[k]]}},'negative'],
  one_tier_up:[{binding:b=>{for(const k in b.medals)b.medals[k]={Gold:'Platinum',Silver:'Gold',Bronze:'Silver'}[b.medals[k]]}},'positive'],
  single_medal:[{binding:b=>{for(const k in b.medals)b.medals[k]='Gold'}},'not_testable'],
  registered_source:[registered(),'registered'],
  registered_tweet_digest:[registered(REG,'5477994f1bf0881f02175344123eb167eddcded31c6cb7471fdeb5fe018b5c51'),'registered'],
  registered_wrong_digest:[registered(REG,'a'.repeat(64)),'HOLD'],
  registered_tier_mismatch:[registered([['CoreWeave','Gold'],...REG.slice(1)]),'HOLD'],
  registered_unknown_name:[registered([['Coreweave','Platinum'],...REG.slice(1)]),'HOLD'],
  unregistered_version:[registered(REG,'c'.repeat(64),'3.1'),'unverified'],
  p95_missing:[{outcomes:o=>{delete o.trials[0].p95_ms}},'HOLD'],
  p_baseline_1e400:[{planText:t=>t.replace('"p_baseline": 0.5,','"p_baseline": 1e400,')},'HOLD'],
  accepted_huge_int:[{outcomesText:t=>t.replace('"attempted": 1050,','"attempted": 1'+'0'.repeat(400)+',')},'HOLD'],
  missing_provider:[{binding:b=>{delete b.medals.EXAMPLE_01}},'HOLD'],
  extra_provider:[{binding:b=>{b.medals.NOT_A_TEST_PROVIDER='Gold'}},'HOLD'],
  tier_diamond:[{binding:b=>{b.medals.EXAMPLE_01='Diamond'}},'HOLD'],
  tier_unavailable:[{binding:b=>{b.medals.EXAMPLE_01='Unavailable'}},'HOLD'],
  bound_before_frozen:[{binding:b=>{b.bound_at='2026-01-01T00:00:00Z'}},'HOLD'],
  bound_after_start:[{binding:b=>{b.bound_at='2026-01-10T00:00:00Z'}},'HOLD'],
  rubric_missing:[{binding:b=>{delete b.rubric}},'HOLD'],
  rubric_no_url:[{binding:b=>{delete b.rubric.url}},'HOLD'],
  rubric_non_hex:[{binding:b=>{b.rubric.sha256='not-hex-'+'0'.repeat(56)}},'HOLD'],
  rubric_late:[{binding:b=>{b.rubric.retrieved_utc='2026-01-05T00:00:00Z'}},'HOLD'],
  source_late:[{binding:b=>{b.source.retrieved_utc='2026-01-05T00:00:00Z'}},'HOLD'],
  binding_rules_missing:[{plan:p=>{delete p.binding_rules}},'HOLD'],
  binding_rules_tiers:[{plan:p=>{p.binding_rules.tiers=['Platinum','Gold']}},'HOLD'],
  credits_over_cost:[{outcomes:o=>{o.trials[0].credits_redeemed_usd=o.trials[0].total_cost_usd+1}},'HOLD'],
  few_sessions:[{plan:p=>p.trials.forEach(r=>{if(r.provider_id==='EXAMPLE_01')r.session_id='S1'}),outcomes:o=>o.trials.forEach(r=>{if(r.provider_id==='EXAMPLE_01')r.session_id='S1'})},'HOLD'],
  dropped_trial:[{outcomes:o=>{o.trials.pop()}},'HOLD'],
  wrong_rating_version:[{binding:b=>{b.rating_version='some-other-version'}},'HOLD'],
  plan_is_array:[{planText:()=>'[]\n'},'HOLD'],
};
for(const f of ['relationship','compensation','credits','special_support','editorial_influence'])cases['disclosure_missing_'+f]=[{plan:p=>{delete p.disclosure[f]}},'HOLD'];
['CONFIRM','Unknown','unconfirmed','TBD','TODO','pending','???','[redact]','none / describe'].forEach((tok,i)=>{cases['disclosure_placeholder_'+i]=[{plan:p=>{p.disclosure.relationship=tok}},'HOLD']});
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'cmax-parity-'));const js={};
for(const [name,[spec]] of Object.entries(cases)){const [pt,bt,ot]=pack(spec);const dir=path.join(tmp,name);fs.mkdirSync(dir);
  fs.writeFileSync(path.join(dir,'plan.json'),pt);fs.writeFileSync(path.join(dir,'binding.json'),bt);fs.writeFileSync(path.join(dir,'outcomes.json'),ot);
  let p,b,o;try{p=JSON.parse(pt);b=JSON.parse(bt);o=JSON.parse(ot)}catch(err){p=null}
  js[name]=e.evaluateObjects(p,o,b,sha(Buffer.from(pt)),sha(Buffer.from(ot)),sha(Buffer.from(bt)))}
// Canonical-JSON vectors, parsed from the same JSON text by both engines
const canon=['{"b":1.0,"a":[0.1,1e-07,100.0,0.30000000000000004,-0.0,1E21,2.5e-8,5e-324,1.7976931348623157e308,123456789012345678901234]}','{"\\uff21k":1,"\\ud83d\\ude00k":2,"a":{"z":[true,false,null,"\\u00e9\\n\\u0001"]}}','[1.5e20,1e-6,1e-7,0.000001234,1e16,9007199254740993]'];
fs.writeFileSync(path.join(tmp,'canon.json'),JSON.stringify(canon));
const pyCode="import sys,os,json;sys.path.insert(0,sys.argv[2]);import challenge as c\nd=sys.argv[1];out={}\nfor n in sorted(os.listdir(d)):\n  if n=='canon.json':continue\n  r=lambda f:open(os.path.join(d,n,f),'rb').read()\n  out[n]=c.evaluate(r('plan.json'),r('binding.json'),r('outcomes.json'))\nout['__canon__']=[c.canonical_json(json.loads(s)) for s in json.load(open(os.path.join(d,'canon.json')))]\nsys.stdout.write(json.dumps(out,allow_nan=False))";
const py=JSON.parse(cp.execFileSync(PYTHON,['-c',pyCode,tmp,path.join(root,'scripts')],{maxBuffer:1<<28}).toString());
fs.rmSync(tmp,{recursive:true,force:true});
canon.forEach((s,i)=>check(e.canonicalJSON(JSON.parse(s))===py.__canon__[i],'canonical JSON parity: '+e.canonicalJSON(JSON.parse(s))+' vs '+py.__canon__[i]));
for(const [name,[,want]] of Object.entries(cases)){const r=js[name];same(r,py[name],name);
  const got=r.status==='HOLD'?'HOLD':r.signal;
  if(want==='registered')check(r.status!=='HOLD'&&r.source_verification==='registered_source',name+': expected registered_source, got '+(r.reason||r.source_verification));
  else if(want==='unverified')check(r.status!=='HOLD'&&r.source_verification==='source_unverified',name+': expected source_unverified, got '+(r.reason||r.source_verification));
  else check(got===want,name+': expected '+want+', got '+got+(r.reason?' ('+r.reason+')':''))}
check(js.one_tier_up.medal_permutation_test.p_help===js.base.medal_permutation_test.p_help,'uniform level shift of all medals changed the permutation p-value');
console.log(JSON.stringify({checks_passed:checks,cases:Object.keys(cases).length,scope:'12 hash vectors; embedded registry/transform == design files; full bit-identical Python/JS results for 3 demo fixtures (informative positive/exact, shuffled inconclusive/exact, level-shift inconclusive/Monte Carlo) and '+Object.keys(cases).length+' adversarial/parity cases (prototype names, integral floats, microsecond timestamps, canonical floats/astral keys/lone surrogates, transform lock, uniform gates, empty training, source registry, v1.3 HOLD rules); canonical JSON vectors'},null,2));
