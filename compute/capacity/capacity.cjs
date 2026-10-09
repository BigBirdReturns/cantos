/* Dedicated-capacity view candidate. Native reservation charging stays in Compute.quote.
   New arithmetic is an explicit scenario projection, not a measured capacity result. */
(function(root){
'use strict';
const C=typeof module==='object'&&module.exports?require('../engine.cjs'):root.Compute;
const VERSION='0.1.0-candidate';
const BASE='9633e3e79d7a5c4ba0382560ed99dc9273b5fdeb';
const ENGINE_BLOB='21956dbce1449a3bbfdedfce3a5064e5b8d87495';
const SOURCE_BLOB='95289238fca808c15f82b9c90aad364d8405d640';
const COSTS=['preparation','validation','operations','recovery','coordination','capture','upkeep'];
const SCHEMA='cantos/dedicated-capacity-scenario@0.1';
const PACKET='cantos/dedicated-capacity-packet@0.1';
const own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
const obj=(o,label)=>{if(!o||typeof o!=='object'||Array.isArray(o)||Object.getPrototypeOf(o)!==Object.prototype)throw Error(label+' must be a plain object.');return o;};
const keys=(o,allowed,label)=>{obj(o,label);const bad=Object.keys(o).filter(k=>!allowed.includes(k));if(bad.length)throw Error(label+': unsupported fields '+bad.join(', '));};
const number=(v,label,min=0,max=1e12)=>C.finite(v,label,min,max);
const str=(v,label,max=2000)=>{if(typeof v!=='string'||v.length>max)throw Error(label+' must be text of at most '+max+' characters.');return v;};
function defaults(){return {schema:SCHEMA,asOf:'2026-10-09',label:'Dedicated allocation',gpu:'Target GPU not qualified',gpus:8,commitmentUSD:10000,committedHours:720,productiveHours:360,acceptedPerProductiveHour:null,costs:Object.fromEntries(COSTS.map(k=>[k,null])),acceptance:'Define the buyer’s quality check and end-to-end deadline.',runtime:'Target model, runtime and allocation remain unqualified.'};}
function validate(x){
 keys(x,['schema','asOf','label','gpu','gpus','commitmentUSD','committedHours','productiveHours','acceptedPerProductiveHour','costs','acceptance','runtime'],'Scenario');
 if(x.schema!==SCHEMA)throw Error('Unsupported scenario schema.');C.date(x.asOf);
 str(x.label,'Label',200);str(x.gpu,'GPU label',200);str(x.acceptance,'Acceptance condition');str(x.runtime,'Runtime');
 C.integer(x.gpus,'GPU count',1,1024);number(x.commitmentUSD,'Whole-period allocation fee');number(x.committedHours,'Committed allocation hours',Number.EPSILON,87600);number(x.productiveHours,'Productive allocation hours',0,x.committedHours);
 if(x.acceptedPerProductiveHour!==null)number(x.acceptedPerProductiveHour,'Assumed accepted results per productive allocation-hour',0,1e12);
 keys(x.costs,COSTS,'Costs');for(const k of COSTS){if(!own(x.costs,k))throw Error('Missing cost field '+k);if(x.costs[k]!==null)number(x.costs[k],k+' cost');}return x;
}
function evaluate(input){
 const x=validate(input);const unknown=COSTS.filter(k=>x.costs[k]===null);const extra=COSTS.reduce((a,k)=>a+(x.costs[k]??0),0);
 const offer={id:'user-commitment',provider:'User-supplied scenario',gpu:x.gpu,vendor:'Unverified',memoryGB:null,gpus:x.gpus,rate:x.commitmentUSD/(x.committedHours*x.gpus),minimumHours:x.committedHours,reviewedOn:x.asOf,schedules:[],allocation:x.label,stock:'UNQUALIFIED',terms:'Full stated commitment is charged, including zero productive use.',source:'USER_INPUT_NOT_PROVIDER_QUOTE',kind:'reserved'};
 // Charge the entire commitment. Productive use NEVER shortens billable hours.
 const charge=C.quote(offer,{hours:x.committedHours,asOf:x.asOf,fixedCost:extra});
 // quote's normal catalog label does not apply to caller-supplied inputs.
 charge.evidence='USER_SUPPLIED_SCENARIO_NOT_PROVIDER_QUOTE';
 const accepted=x.acceptedPerProductiveHour===null?null:x.acceptedPerProductiveHour*x.productiveHours;
 const per1000=accepted>0?charge.total/accepted*1000:null;
 const infraPer1000=accepted>0?charge.gpuCharge/accepted*1000:null;
 for(const v of [charge.total,accepted,per1000,infraPer1000])if(v!==null&&!Number.isFinite(v))throw Error('Scenario exceeds numeric range.');
 return {status:'SCENARIO_REQUIRES_TARGET_QUALIFICATION',basis:'USER_ASSUMPTIONS',charge,unknown_costs:unknown,known_cost_total:charge.total,cost_scope:unknown.length?'KNOWN_COST_SUBTOTAL_NOT_ALL_IN':'ALL_LISTED_COST_CATEGORIES_SUPPLIED_AS_ASSUMPTIONS',productive_hours:x.productiveHours,productive_share:x.productiveHours/x.committedHours,modeled_accepted:accepted,cost_per_1000_accepted:per1000,infrastructure_per_1000_accepted:infraPer1000,denominator_status:accepted===null?'UNMEASURED':accepted===0?'ZERO_MODELED_OUTPUT':'MODELED_NOT_MEASURED',target_qualified:false,authority:{provision:false,execute:false,pay:false,publish:false},limits:['Accepted throughput is a caller assumption for the whole allocation, not per GPU.','Productive share assumes a constant accepted rate during productive hours; it is not a queue or scaling model.','Unknown costs remain unknown; retries and escalations must be reflected in productive time, accepted rate and route costs.','A price change preserves the assumed denominator; configuration or acceptance changes require new target evidence.','No provider quote, target benchmark, SLA proof, jurisdiction proof or execution attestation is established.']};
}
function historical(rate){
 number(rate,'Scenario MI300X hourly rate',0,1e9);const hours=64.7/60;
 const offer={id:'run3-a-t0-summary',provider:'Hot Aisle',gpu:'MI300X',vendor:'AMD',memoryGB:192,gpus:1,rate,minimumHours:0,reviewedOn:'2026-09-24',schedules:[],allocation:'One MI300X, A/T0 retained published summary',stock:'HISTORICAL',terms:'Own-seat equivalent, rounded 64.7-minute duration; invoices unreconciled.',source:SOURCE_BLOB,kind:'historical'};
 const q=C.quote(offer,{hours,asOf:'2026-09-24'});q.evidence='REPRICE_OF_PUBLISHED_SUMMARY_NOT_FRESH_MEASUREMENT';
 return {basis:'PUBLISHED_RUN3_SUMMARY',accepted:4336,scheduled:8622,correct:4371,minutes:64.7,source_blob:SOURCE_BLOB,source_commit:BASE,quote:q,cost_per_1000_accepted:q.total/4336*1000,acceptance:'EvalPlus base and plus pass; first token <= 1 s and completion <= 60 s from scheduled arrival.',limits:['The accepted count is read from the published summary, not regraded or joined from request rows in this preview.','One run per arm; rounded own-seat-equivalent duration; no invoice reconciliation.','This reprice applies to that historical MI300X result and supplies no H200/B300 or multi-GPU performance evidence.']};
}
function body(input,rate,parent=null){
 if(parent!==null&&!/^[a-f0-9]{64}$/.test(parent))throw Error('Parent checksum must be a SHA-256 hex value.');
 return {schema:'cantos/dedicated-capacity-body@0.1',version:VERSION,origin:{repo:'BigBirdReturns/cantos',commit:BASE,engine_blob:ENGINE_BLOB,run3_blob:SOURCE_BLOB},parent_checksum:parent,input:JSON.parse(C.canonical(validate(input))),result:evaluate(input),historical_rate:rate,historical:historical(rate)};
}
function verifyBody(b){
 keys(b,['schema','version','origin','parent_checksum','input','result','historical_rate','historical'],'Body');
 if(b.schema!=='cantos/dedicated-capacity-body@0.1'||b.version!==VERSION)throw Error('Unsupported body version.');
 const expected=body(b.input,b.historical_rate,b.parent_checksum);
 if(C.canonical(expected)!==C.canonical(b))throw Error('Stored result or source identity disagrees with recomputation.');return expected;
}
const api={VERSION,BASE,ENGINE_BLOB,SOURCE_BLOB,COSTS,SCHEMA,PACKET,defaults,validate,evaluate,historical,body,verifyBody,canonical:C.canonical};
if(typeof module==='object'&&module.exports)module.exports=api;root.Capacity=api;
})(globalThis);
