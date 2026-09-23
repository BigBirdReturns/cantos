'use strict';
// Optional Node.js check; no npm dependencies. Python remains the reference scorer.
const fs=require('fs'),path=require('path'),vm=require('vm'),crypto=require('crypto'),cp=require('child_process');
const root=path.resolve(__dirname,'..');
cp.execFileSync(process.env.PYTHON||'python3',[path.join(root,'scripts/make_demo.py')]);
cp.execFileSync(process.env.PYTHON||'python3',[path.join(root,'scripts/challenge.py'),'--plan',path.join(root,'data/demo-plan.json'),'--outcomes',path.join(root,'data/demo-outcomes.json'),'--output',path.join(root,'data/demo-result.json')]);
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const ctx={module:{exports:{}}};vm.runInNewContext(html.match(/<script id="engine">([\s\S]*?)<\/script>/)[1],ctx);
const e=ctx.module.exports,sha=b=>crypto.createHash('sha256').update(b).digest('hex');let checks=0;
function check(condition,message){if(!condition)throw Error(message);checks++}
for(const n of [0,1,3,55,56,63,64,65,127,128,1000,1000000]){let b=Buffer.alloc(n);for(let i=0;i<n;i++)b[i]=(i*173+53)%256;check(e.sha256Local(b)===sha(b),'SHA mismatch: '+n)}
const pb=fs.readFileSync(path.join(root,'data/demo-plan.json')),ob=fs.readFileSync(path.join(root,'data/demo-outcomes.json')),p=JSON.parse(pb),o=JSON.parse(ob),r=e.evaluateObjects(p,o,sha(pb),sha(ob)),ref=JSON.parse(fs.readFileSync(path.join(root,'data/demo-result.json')));
check(r.status===ref.status&&Math.abs(r.mean_lift-ref.mean_lift)<1e-12,'Point estimate parity');
check(r.bootstrap_95.every((x,i)=>Math.abs(x-ref.bootstrap_95[i])<1e-12),'Interval parity');
const dropped=JSON.parse(ob);dropped.trials.pop();check(e.evaluateObjects(p,dropped,sha(pb),'test').status==='HOLD','Dropped trial accepted');
const nullPlan=JSON.parse(pb);nullPlan.trials.forEach(x=>x.p_with_rating=x.p_baseline);const nb=Buffer.from(JSON.stringify(nullPlan));const nullOut={...o,plan_sha256:sha(nb)};check(e.evaluateObjects(nullPlan,nullOut,sha(nb),'test').status==='LIFT_NOT_DEMONSTRATED','Null rating got credit');
console.log(JSON.stringify({checks_passed:checks,scope:'12 hash vectors, Python/JS point and CI parity, dropped cohort, null rating'},null,2));
