'use strict';
// Optional Node.js check; no npm dependencies. Python remains the reference scorer.
const fs=require('fs'),path=require('path'),vm=require('vm'),crypto=require('crypto'),cp=require('child_process');
const root=path.resolve(__dirname,'..');
const PYTHON=process.env.PYTHON||(process.platform==='win32'?'python':'python3');
cp.execFileSync(PYTHON,[path.join(root,'scripts/make_demo.py')]);
cp.execFileSync(PYTHON,[path.join(root,'scripts/challenge.py'),'--plan',path.join(root,'data/demo-plan.json'),'--binding',path.join(root,'data/demo-binding.json'),'--outcomes',path.join(root,'data/demo-outcomes.json'),'--output',path.join(root,'data/demo-result.json')]);
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const ctx={module:{exports:{}}};vm.runInNewContext(html.match(/<script id="engine">([\s\S]*?)<\/script>/)[1],ctx);
const e=ctx.module.exports,sha=b=>crypto.createHash('sha256').update(b).digest('hex');let checks=0;
function check(condition,message){if(!condition)throw Error(message);checks++}
for(const n of [0,1,3,55,56,63,64,65,127,128,1000,1000000]){let b=Buffer.alloc(n);for(let i=0;i<n;i++)b[i]=(i*173+53)%256;check(e.sha256Local(b)===sha(b),'SHA mismatch: '+n)}
const pb=fs.readFileSync(path.join(root,'data/demo-plan.json')),bb=fs.readFileSync(path.join(root,'data/demo-binding.json')),ob=fs.readFileSync(path.join(root,'data/demo-outcomes.json'));
const p=JSON.parse(pb),b=JSON.parse(bb),o=JSON.parse(ob);
const r=e.evaluateObjects(p,o,b,sha(pb),sha(ob),sha(bb)),ref=JSON.parse(fs.readFileSync(path.join(root,'data/demo-result.json')));
check(r.status===ref.status&&r.signal===ref.signal,'Status/signal parity');
check(Math.abs(r.comparison_vs_baseline.mean_lift-ref.comparison_vs_baseline.mean_lift)<1e-12,'Baseline comparison point-estimate parity');
check(Math.abs(r.comparison_vs_reference.mean_lift-ref.comparison_vs_reference.mean_lift)<1e-12,'Reference comparison point-estimate parity');
check(r.comparison_vs_baseline.bootstrap_95.every((x,i)=>Math.abs(x-ref.comparison_vs_baseline.bootstrap_95[i])<1e-12),'Baseline interval parity');
check(r.comparison_vs_reference.bootstrap_95.every((x,i)=>Math.abs(x-ref.comparison_vs_reference.bootstrap_95[i])<1e-12),'Reference interval parity');
check(r.sensitivity.length===ref.sensitivity.length&&r.sensitivity.every((s,i)=>s.weight===ref.sensitivity[i].weight&&Math.abs(s.mean_lift_vs_baseline-ref.sensitivity[i].mean_lift_vs_baseline)<1e-12&&Math.abs(s.mean_lift_vs_reference-ref.sensitivity[i].mean_lift_vs_reference)<1e-12),'Sensitivity parity');
check(r.leave_one_provider_out.length===ref.leave_one_provider_out.length&&r.leave_one_provider_out.every((x,i)=>x.excluded_provider===ref.leave_one_provider_out[i].excluded_provider&&Math.abs(x.mean_lift_vs_reference-ref.leave_one_provider_out[i].mean_lift_vs_reference)<1e-12),'Leave-one-provider-out parity');
check(r.transform_sha256===ref.transform_sha256&&JSON.stringify(r.transform)===JSON.stringify(ref.transform),'Transform parity');
check(r.binding_sha256===ref.binding_sha256&&JSON.stringify(r.binding)===JSON.stringify(ref.binding),'Binding parity');
check(r.providers===ref.providers&&r.trials===ref.trials,'Cohort size parity');
const someProvider=Object.keys(r.provider_results)[0];
check(r.provider_results[someProvider][0].medal===ref.provider_results[someProvider][0].medal&&r.provider_results[someProvider][0].session_id===ref.provider_results[someProvider][0].session_id&&r.provider_results[someProvider][0].date===ref.provider_results[someProvider][0].date,'Per-trial medal/session/date parity');
const dropped=JSON.parse(ob);dropped.trials.pop();check(e.evaluateObjects(p,dropped,b,sha(pb),'test',sha(bb)).status==='HOLD','Dropped trial accepted');
check(e.evaluateObjects(p,o,b,'0'.repeat(64),sha(ob),sha(bb)).status==='HOLD','Plan-hash mismatch accepted');
check(e.evaluateObjects(p,o,b,sha(pb),sha(ob),'0'.repeat(64)).status==='HOLD','Binding tamper (outcomes.binding_sha256 mismatch) accepted');
const wrongVintage=JSON.parse(bb);wrongVintage.rating_version='some-other-version';check(e.evaluateObjects(p,o,wrongVintage,sha(pb),sha(ob),'test').status==='HOLD','Wrong rating_version accepted');
const missingProvider=JSON.parse(bb);delete missingProvider.medals[Object.keys(missingProvider.medals)[0]];check(e.evaluateObjects(p,o,missingProvider,sha(pb),sha(ob),'test').status==='HOLD','Missing provider in binding accepted');
const extraProvider=JSON.parse(bb);extraProvider.medals['NOT_A_TEST_PROVIDER']='Gold';check(e.evaluateObjects(p,o,extraProvider,sha(pb),sha(ob),'test').status==='HOLD','Extra provider in binding accepted');
const unknownTier=JSON.parse(bb);unknownTier.medals[Object.keys(unknownTier.medals)[0]]='Diamond';check(e.evaluateObjects(p,o,unknownTier,sha(pb),sha(ob),'test').status==='HOLD','Unknown medal tier accepted');
const unavailableTier=JSON.parse(bb);unavailableTier.medals[Object.keys(unavailableTier.medals)[0]]='Unavailable';check(e.evaluateObjects(p,o,unavailableTier,sha(pb),sha(ob),'test').status==='HOLD','"Unavailable" medal tier accepted');
const earlyBinding=JSON.parse(bb);earlyBinding.bound_at='2026-01-01T00:00:00Z';check(e.evaluateObjects(p,o,earlyBinding,sha(pb),sha(ob),'test').status==='HOLD','bound_at before frozen_at accepted');
const lateBinding=JSON.parse(bb);lateBinding.bound_at='2026-01-10T00:00:00Z';check(e.evaluateObjects(p,o,lateBinding,sha(pb),sha(ob),'test').status==='HOLD','bound_at after a started_at accepted');
for(const field of ['relationship','compensation','credits','special_support','editorial_influence']){
  const noField=JSON.parse(pb);delete noField.disclosure[field];const noFieldBytes=Buffer.from(JSON.stringify(noField));
  check(e.evaluateObjects(noField,o,b,sha(noFieldBytes),sha(ob),sha(bb)).status==='HOLD','Missing disclosure.'+field+' accepted');
}
for(const token of ['CONFIRM','Unknown','unconfirmed','TBD','TODO','pending','???','[redact]','none / describe']){
  const placeholder=JSON.parse(pb);placeholder.disclosure.relationship=token;const placeholderBytes=Buffer.from(JSON.stringify(placeholder));
  check(e.evaluateObjects(placeholder,o,b,sha(placeholderBytes),sha(ob),sha(bb)).status==='HOLD','Disclosure placeholder "'+token+'" accepted');
}
check(r.subsidized_trials===ref.subsidized_trials,'Subsidized-trials count parity');
check(r.subsidized_trials>0,'Demo fixture should exercise at least one subsidized trial');
const someEcon=r.economics.find(x=>x.credits_redeemed_usd>0);
check(!!someEcon,'At least one economics row should carry nonzero credits_redeemed_usd');
check(JSON.stringify(r.economics)===JSON.stringify(ref.economics),'Economics (credits_redeemed_usd included) parity');
check(r.binding.rubric&&typeof r.binding.rubric==='object'&&JSON.stringify(r.binding.rubric)===JSON.stringify(ref.binding.rubric),'Binding rubric parity');
const missingRubric=JSON.parse(bb);delete missingRubric.rubric;check(e.evaluateObjects(p,o,missingRubric,sha(pb),sha(ob),'test').status==='HOLD','Missing binding.rubric accepted');
const incompleteRubric=JSON.parse(bb);delete incompleteRubric.rubric.url;check(e.evaluateObjects(p,o,incompleteRubric,sha(pb),sha(ob),'test').status==='HOLD','Incomplete binding.rubric (no url) accepted');
const nonHexRubric=JSON.parse(bb);nonHexRubric.rubric.sha256='not-hex-'+'0'.repeat(56);check(e.evaluateObjects(p,o,nonHexRubric,sha(pb),sha(ob),'test').status==='HOLD','Non-hex binding.rubric.sha256 accepted');
const lateRubric=JSON.parse(bb);lateRubric.rubric.retrieved_utc='2026-01-05T00:00:00Z';check(e.evaluateObjects(p,o,lateRubric,sha(pb),sha(ob),'test').status==='HOLD','binding.rubric.retrieved_utc after bound_at accepted');
const lateSource=JSON.parse(bb);lateSource.source.retrieved_utc='2026-01-05T00:00:00Z';check(e.evaluateObjects(p,o,lateSource,sha(pb),sha(ob),'test').status==='HOLD','binding.source.retrieved_utc after bound_at accepted');
const noBindingRules=JSON.parse(pb);delete noBindingRules.binding_rules;const noBindingRulesBytes=Buffer.from(JSON.stringify(noBindingRules));check(e.evaluateObjects(noBindingRules,o,b,sha(noBindingRulesBytes),sha(ob),sha(bb)).status==='HOLD','Missing plan.binding_rules accepted');
const badTiers=JSON.parse(pb);badTiers.binding_rules.tiers=['Platinum','Gold'];const badTiersBytes=Buffer.from(JSON.stringify(badTiers));check(e.evaluateObjects(badTiers,o,b,sha(badTiersBytes),sha(ob),sha(bb)).status==='HOLD','binding_rules.tiers mismatch accepted');
const overCredits=JSON.parse(ob);overCredits.trials[0].credits_redeemed_usd=overCredits.trials[0].total_cost_usd+1;const overCreditsBytes=Buffer.from(JSON.stringify(overCredits));check(e.evaluateObjects(p,overCredits,b,sha(pb),sha(overCreditsBytes),sha(bb)).status==='HOLD','credits_redeemed_usd exceeding total_cost_usd accepted');
const fewSessions=JSON.parse(pb),fewSessionsOut=JSON.parse(ob);
for(const row of fewSessions.trials.filter(x=>x.provider_id===someProvider))row.session_id='S1';
for(const row of fewSessionsOut.trials.filter(x=>x.provider_id===someProvider))row.session_id='S1';
const fsb=Buffer.from(JSON.stringify(fewSessions));fewSessionsOut.plan_sha256=sha(fsb);
check(e.evaluateObjects(fewSessions,fewSessionsOut,b,sha(fsb),'test',sha(bb)).status==='HOLD','Session coverage floor not enforced');
console.log(JSON.stringify({checks_passed:checks,scope:'12 hash vectors, Python/JS status/signal/comparison/sensitivity/LOO/transform/binding/medal/economics/subsidized-trials parity, dropped cohort, wrong rating_version, missing/extra provider, unknown/Unavailable tier, bound_at before frozen_at, bound_at after started_at, missing/incomplete/non-hex/late binding.rubric, late binding.source, missing plan.binding_rules, binding_rules.tiers mismatch, credits_redeemed_usd exceeding total_cost_usd, 5 missing-disclosure fields, 9 placeholder variants, session coverage floor'},null,2));
