/* Second Run Compute 0.1.0 | MIT. Pure calculations. No I/O or execution authority. */
(function (root) {
'use strict';
const VERSION='0.1.0';
const fail=m=>{throw new Error(m);};
const finite=(v,n,min=0,max=Number.MAX_SAFE_INTEGER)=>typeof v==='number'&&Number.isFinite(v)&&v>=min&&v<=max?v:fail(n+' is outside the supported range.');
const integer=(v,n,min=0,max=Number.MAX_SAFE_INTEGER)=>Number.isSafeInteger(finite(v,n,min,max))?v:fail(n+' must be an integer.');
const text=(s,max=200)=>typeof s==='string'?s.slice(0,max):'';
function date(s){if(typeof s!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(s)||new Date(s+'T00:00:00Z').toISOString().slice(0,10)!==s)fail('Use a valid ISO date.');return s;}
function canonical(x){if(x===null||typeof x!=='object'){if(typeof x==='number'&&!Number.isFinite(x))fail('Nonfinite value.');return JSON.stringify(x);}if(Array.isArray(x))return '['+x.map(canonical).join(',')+']';return '{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}';}
function validateCatalog(c){
 if(c?.schema!=='second-run/compute-catalog@1'||!Array.isArray(c.offers)||c.offers.length>1000)fail('Unsupported catalog.');date(c.reviewedOn);integer(c.staleAfterDays,'Price review interval',1,365);
 const ids=new Set();for(const o of c.offers){if(!/^[a-z0-9-]+$/.test(o.id)||ids.has(o.id))fail('Invalid or duplicate offer ID.');ids.add(o.id);if(!c.providers.some(p=>p.id===o.provider)||!c.sources[o.source])fail('Unknown provider or source.');finite(o.rate,'GPU-hour price');finite(o.memoryGB,'Advertised memory',1,100000);integer(o.gpus,'Billable GPU count',1,1024);finite(o.minimumHours,'Minimum charge',0,87600);date(o.reviewedOn);for(const s of o.schedules){date(s.effectiveOn);finite(s.rate,'Scheduled price');}if(!/^https:\/\//.test(c.sources[o.source].url))fail('Source must be HTTPS.');}return c;
}
function priceAt(o,asOf){date(asOf);if(asOf<o.reviewedOn)fail('This snapshot does not establish earlier prices.');let rate=o.rate,effective=o.reviewedOn;for(const s of [...o.schedules].sort((a,b)=>a.effectiveOn.localeCompare(b.effectiveOn)))if(s.effectiveOn<=asOf){rate=s.rate;effective=s.effectiveOn;}return {rate,effective,scheduled:effective>o.reviewedOn};}
function freshness(c,today){date(today);const age=Math.floor((Date.parse(today)-Date.parse(c.reviewedOn))/86400000);return {reviewedOn:c.reviewedOn,ageDays:age,status:age<0?'FUTURE_SNAPSHOT':age>c.staleAfterDays?'STALE':'DATED_SNAPSHOT',staleAfterDays:c.staleAfterDays};}
function quote(o,params){
 const h=finite(params.hours,'Reserved hours',0,87600),extra=finite(params.extraPerHour??0,'Hourly extras'),fixed=finite(params.fixedCost??0,'One-time extras');const p=priceAt(o,params.asOf);
 const billedHours=h===0?0:Math.max(h,o.minimumHours);const rate=p.rate*o.gpus;
 return {id:o.id,provider:o.provider,gpu:o.gpu,vendor:o.vendor,memoryGB:o.memoryGB,gpus:o.gpus,ratePerGPU:p.rate,allocationHourly:rate,hours:h,billedHours,minimumApplied:billedHours>h,gpuCharge:rate*billedHours,extraCharge:extra*billedHours+fixed,total:rate*billedHours+extra*billedHours+fixed,effectiveOn:p.effective,allocation:o.allocation,stock:o.stock,terms:o.terms,source:o.source,kind:o.kind,evidence:'PUBLISHED_PRICE_MODEL'};
}
function market(c,p){validateCatalog(c);finite(p.minMemoryGB??0,'Per-GPU memory floor',0,100000);const rows=c.offers.filter(o=>(!p.provider||p.provider==='all'||o.provider===p.provider)&&(!p.vendor||p.vendor==='all'||o.vendor===p.vendor)&&o.memoryGB>=(p.minMemoryGB??0)&&(!p.gpus||o.gpus===p.gpus)&&(!p.query||(o.gpu+' '+o.provider).toLowerCase().includes(text(p.query).toLowerCase()))).map(o=>quote(o,p));return rows.sort((a,b)=>a.total-b.total||a.id.localeCompare(b.id));}
function ownership(p){
 const h=finite(p.hours,'Active hours',0,720),capex=finite(p.capex,'Purchase cost'),residual=finite(p.residual,'Residual value',0,capex),months=finite(p.months,'Ownership horizon',1,120),load=finite(p.loadWatts,'System load power',0,1000000),idle=finite(p.idleWatts,'System idle power',0,load),energy=finite(p.kwhPrice,'Electricity price',0,100),factor=finite(p.powerFactor??1,'Facility power multiplier',1,10),ops=finite(p.opsMonthly??0,'Monthly operating cost'),cloud=finite(p.cloudHourly,'Cloud allocation rate');
 const power=(h*load+(720-h)*idle)/1000*energy*factor,amortization=(capex-residual)/months,local=power+ops+amortization;
 if((p.localRate!==undefined)!==(p.cloudRate!==undefined))fail('Supply both work rates or neither.');
 const equalThroughput=p.localRate!==undefined&&p.cloudRate!==undefined;
 const throughputRatio=equalThroughput?finite(p.localRate,'Local work rate',Number.EPSILON)/finite(p.cloudRate,'Cloud work rate',Number.EPSILON):1;
 const cloudHours=h*throughputRatio,requiredCopies=cloudHours>0?Math.ceil(cloudHours/720):0;
 const minH=finite(p.cloudMinimumHours??0,'Cloud minimum hours');
 // Costs below concern one comparator allocation; >720h requires parallelism / a longer window.
 const cloudBillableHours=cloudHours===0?0:Math.max(cloudHours,minH),cloudCost=cloudBillableHours*cloud;
 const saving=cloudCost-(power+ops),cashBreakeven=saving>0?capex/saving:null;
 return {basis:equalThroughput?'USER_DECLARED_EQUAL_WORK_RATES':'EQUAL_RESERVED_HOURS_NOT_EQUAL_OUTPUT',hours:h,cloudHours,cloudBillableHours,cloudCopiesNeeded:requiredCopies,energyMonthly:power,amortizationMonthly:amortization,opsMonthly:ops,ownershipMonthly:local,rentalMonthly:cloudCost,monthlyDifference:cloudCost-local,cashBreakevenMonths:cashBreakeven,ownershipHorizonCost:local*months,rentalHorizonCost:cloudCost*months,capacityWarning:cloudHours>720,hardwarePerformanceVerified:false};
}
function route(p){
 const volume=integer(p.requests,'Requests per batch',1,1e9),premium=finite(p.premiumHourly,'Premium allocation rate'),setup=finite(p.qualificationCost,'Initial qualification cost'),verifier=finite(p.validationCostPerRequest??0,'Validation cost per request'),repeats=integer(p.repeats??1,'Repeat batches',1,100000);
 if(!Array.isArray(p.classes)||p.classes.length<1||p.classes.length>30)fail('Provide 1–30 workload classes.');
 if(Math.abs(p.classes.reduce((s,c)=>s+finite(c.share,'Workload share',0,100),0)-100)>1e-7)fail('Workload shares must total 100%.');
 const classes=p.classes.map(c=>{
 if(typeof c.premium!=='boolean')fail('Premium-path designation must be boolean.');
 const count=volume*c.share/100,baseSec=finite(c.baselineSeconds,'Baseline seconds per request'),newSec=finite(c.targetSeconds,'Target seconds per request'),newPrice=finite(c.targetHourly,'Target hourly price'),fallback=finite(c.fallbackPercent,'Fallback percentage',0,100)/100;
 if(c.premium&&fallback!==0)fail('The premium terminal path must have zero fallback.');
 if(c.premium&&Math.abs(newPrice-premium)>1e-9)fail('Premium path rate must match the selected premium allocation.');
 const base=count*baseSec/3600*premium,target=count*newSec/3600*newPrice,fallbackSeconds=c.premium?0:count*fallback*baseSec;
 return {name:text(c.name),share:c.share,requests:count,baseSeconds:count*baseSec,premiumSeconds:c.premium?count*newSec:fallbackSeconds,baselineCost:base,attemptCost:target,fallbackCost:fallbackSeconds/3600*premium,newCost:target+fallbackSeconds/3600*premium+count*verifier,movedRequests:c.premium?0:count*(1-fallback),status:'SCENARIO_REQUIRES_TASK_QUALIFICATION'};});
 const sum=k=>classes.reduce((n,c)=>n+c[k],0);const baseline=sum('baselineCost'),recurring=sum('newCost'),delta=baseline-recurring,pb=sum('baseSeconds'),pa=sum('premiumSeconds');
 return {classes,requests:volume,repeats,baselinePerBatch:baseline,recurringPerBatch:recurring,qualificationCost:setup,firstBatch:recurring+setup,baselineTotal:baseline*repeats,proposedTotal:recurring*repeats+setup,savingsTotal:delta*repeats-setup,breakEvenBatches:delta>0?Math.floor(setup/delta)+1:null,requestsMovedPct:sum('movedRequests')/volume*100,premiumSecondsBefore:pb,premiumSecondsAfter:pa,premiumTimeReductionPct:pb>0?(1-pa/pb)*100:null,capacityReleased:null,status:'MODELED_POLICY_NOT_ADMITTED',qualification:'Task acceptance, end-to-end latency, placement, residency, and actual allocation release require measurement.'};
}
function footprint(p){const countB=finite(p.parametersB,'Parameters',0.001,10000),bits=finite(p.bits,'Bits per parameter',1,64),overhead=finite(p.overheadPct??15,'Representation overhead',0,200),runtime=finite(p.runtimeGB??3,'Runtime budget'),kv=finite(p.kvGB??0,'KV-cache budget');return {weightGB:countB*bits/8,estimatedGB:countB*bits/8*(1+overhead/100)+runtime+kv,status:'PLANNING_ESTIMATE_NOT_NATIVE_FIT',note:'All resident parameters, including MoE experts. Runtime, KV-cache, concurrency and quantization layout must be qualified.'};}
function plan(c,p){validateCatalog(c);const ids=p.offerIds??[];if(!Array.isArray(ids)||new Set(ids).size!==ids.length||ids.length>4)fail('Select at most four offers.');const offers=ids.map(id=>c.offers.find(o=>o.id===id)??fail('Unknown offer.'));
 return {schema:'second-run/compute-plan@1',version:VERSION,status:'PROPOSAL',asOf:date(p.asOf),catalogReviewedOn:c.reviewedOn,workload:text(p.workload||'Unspecified workload'),requirements:{minMemoryGB:finite(p.minMemoryGB??0,'Memory requirement'),acceptance:text(p.acceptance||'Acceptance contract required',2000)},reservedHours:finite(p.hours,'Hours',0,87600),options:offers.map(o=>quote(o,p)),authority:{provision:false,execute:false,pay:false,publish:false},nextChecks:['Confirm purchasable allocation, region and current quote.','Qualify exact artifact/runtime fit; advertised memory is a filter only.','Run the agreed acceptance and latency tests on representative held-out work.','Count all failed attempts, setup, transfer, verification and billable idle time.'],invalidation:{price:'Recompute economics from retained performance.',model_runtime_workload_acceptance:'Requalify affected results; preserve the baseline.'}};
}
function aperture(raw){if(raw?.schema!=='aperture-support/1')fail('Use an aperture-support/1 receipt.');const safeNum=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0?v:null;return {schema:'second-run/hardware-view@1',basis:'SUPPLIED_APERTURE_RECEIPT',createdAt:text(raw.createdAt),version:text(raw.apertureVersion),cpu:text(raw.cpu?.model),logicalCPUs:safeNum(raw.cpu?.logicalCpus),memory:{totalBytes:safeNum(raw.memory?.totalBytes),headroomBytes:safeNum(raw.memory?.allocationHeadroomBytes)},graphics:(raw.nvidia?.length?raw.nvidia:raw.graphics??[]).slice(0,32).map(g=>({name:text(g.name),totalBytes:safeNum(g.totalBytes??g.capacityBytes),freeBytes:safeNum(g.freeBytes),driver:text(g.driver),memoryDomain:text(g.memoryDomain)})),qualification:'Inventory only. No new hardware scan, stress test, native fit or inference run.'};}
const api={VERSION,finite,integer,date,text,canonical,validateCatalog,priceAt,freshness,quote,market,ownership,route,footprint,plan,aperture};
if(typeof module==='object'&&module.exports)module.exports=api;root.Compute=api;
})(typeof globalThis==='undefined'?this:globalThis);
