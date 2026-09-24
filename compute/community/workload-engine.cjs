/* Hot Aisle Workload Report 2.0.0 | MIT | No I/O, no eval, no dependencies. */
(function(root){
'use strict';
const VERSION='2.0.0', MAX_REQUESTS=100000, MAX_RUNS=50;
const fail=m=>{throw Error(m)};
const obj=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
const num=(x,name,min=0)=>typeof x==='number'&&Number.isFinite(x)&&x>=min?x:fail(name+' must be a finite number ≥ '+min+'.');
const count=(x,name)=>Number.isSafeInteger(num(x,name))&&x<=MAX_REQUESTS?x:fail(name+' must be an integer ≤ '+MAX_REQUESTS+'.');
const opt=(x,name)=>x===undefined||x===null?null:num(x,name);
const text=x=>typeof x==='string'?x.slice(0,500):typeof x==='number'&&Number.isFinite(x)?String(x):'';
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function canonical(x){if(x===null||typeof x!=='object')return JSON.stringify(x);if(Array.isArray(x))return '['+x.map(canonical).join(',')+']';return '{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}';}
function parseDocuments(raw){
 if(typeof raw!=='string'||raw.length>25*1024*1024)fail('Use a UTF-8 result file up to 25 MiB.');
 let s=raw.replace(/^\uFEFF/,'').trim();if(!s)fail('The result is empty.');
 if(!/^[\[{]/.test(s)||s.includes('Serving Benchmark Result'))return [parseConsole(s)];
 // Accept JSON, arrays, NDJSON and vLLM --append-result concatenated objects.
 const values=[];let start=-1,depth=0,inString=false,escaped=false;
 for(let i=0;i<s.length;i++){let c=s[i];if(start<0){if(/\s/.test(c))continue;if(c!=='{'&&c!=='[')fail('Expected a JSON object, array or another appended result.');start=i;}
  if(inString){if(escaped)escaped=false;else if(c==='\\')escaped=true;else if(c==='"')inString=false;continue;}
  if(c==='"')inString=true;else if(c==='{'||c==='[')depth++;else if(c==='}'||c===']'){depth--;if(depth===0){let v;try{v=JSON.parse(s.slice(start,i+1));}catch(e){fail('Invalid JSON: '+e.message);}values.push(...(Array.isArray(v)?v:[v]));start=-1;if(values.length>MAX_RUNS)fail('At most 50 trials per import.');}}
 }
 if(start>=0||inString||depth)fail('The JSON is incomplete.');if(!values.length)fail('No results found.');return values;
}
function parseConsole(s){
 const out={format:'vllm-console-summary'};
 const labels={'Successful requests':'completed','Failed requests':'failed','Benchmark duration (s)':'duration','Total input tokens':'total_input_tokens','Total generated tokens':'total_output_tokens','Request throughput (req/s)':'request_throughput','Request goodput (req/s)':'request_goodput','Maximum request concurrency':'max_concurrency','Request rate configured (RPS)':'request_rate'};
 for(const line of s.replace(/\x1b\[[0-9;]*m/g,'').split(/\r?\n/)){const m=line.trim().match(/^(.+?):\s+([\d.eE+\-]+)\s*$/);if(!m)continue;const name=labels[m[1]];if(name){if(out[name]!==undefined)fail('Paste one console result at a time; use JSON for repeated runs.');out[name]=Number(m[2]);}
  const q=m[1].match(/^(Mean|Median|P50|P95|P99) (TTFT|TPOT|ITL|E2EL) \(ms\)$/);if(q)out[(q[1]==='Median'?'median':q[1].toLowerCase())+'_'+q[2].toLowerCase()+'_ms']=Number(m[2]);
 }
 if(out.duration===undefined||out.completed===undefined)fail('Expected a vLLM result JSON or its “Serving Benchmark Result” console block.');return out;
}
function quantile(values,p){if(!values.length)return null;const a=[...values].sort((x,y)=>x-y),i=(a.length-1)*p/100,lo=Math.floor(i),hi=Math.ceil(i);return a[lo]+(a[hi]-a[lo])*(i-lo);}
function percentiles(a){return a===null?null:{p50:quantile(a,50),p95:quantile(a,95),p99:quantile(a,99)};}
function normalize(raw,source){
 if(!obj(raw))fail('Every trial must be a result object.');
 const d=num(raw.duration,'duration',Number.MIN_VALUE),completed=count(raw.completed,'completed');
 let n=raw.num_prompts===undefined?null:count(raw.num_prompts,'num_prompts');
 const failed=raw.failed===undefined?null:count(raw.failed,'failed');
 if(failed!==null){if(n!==null&&n!==failed+completed)fail('num_prompts differs from completed + failed.');n=failed+completed;}
 const arrays=['errors','ttfts','latencies','queue_times','output_lens','input_lens'];
 for(const key of arrays)if(raw[key]!==undefined){if(!Array.isArray(raw[key])||raw[key].length>MAX_REQUESTS)fail(key+' must be a bounded array.');if(n===null)n=raw[key].length;if(raw[key].length!==n)fail(key+' length differs from attempted requests.');}
 if(n!==null&&completed>n)fail('Completed requests exceed attempted requests.');
 if(n!==null&&n>MAX_REQUESTS)fail('Too many requests.');
 const warnings=[];let mask=null;
 if(raw.errors!==undefined){if(raw.errors.some(e=>typeof e!=='string'))fail('errors must contain strings.');mask=raw.errors.map(e=>e==='');if(mask.filter(Boolean).length!==completed)fail('The errors array disagrees with the completed-request count.');}
 else if(n!==null&&completed===n)mask=Array(n).fill(true);
 const vectors={};for(const key of arrays.filter(k=>k!=='errors')){if(raw[key]!==undefined){vectors[key]=raw[key].map((v,i)=>num(v,key+'['+i+']'));if(key.endsWith('_lens')&&vectors[key].some(v=>!Number.isSafeInteger(v)))fail(key+' must contain integer lengths.');}}
 function metric(key,label){const samples=vectors[key]&&mask?vectors[key].filter((_,i)=>mask[i]).map(x=>x*1000):null;const summary={};for(const p of [50,95,99]){const k='p'+p+'_'+label+'_ms';summary['p'+p]=opt(raw[k]??(p===50?raw['median_'+label+'_ms']:null),k);}let prev=null;for(const p of ['p50','p95','p99'])if(summary[p]!==null){if(prev!==null&&summary[p]<prev)fail('Percentile summary is not monotonic.');prev=summary[p];}return {samples,percentiles:samples!==null?percentiles(samples):summary,basis:samples!==null?'recomputed from successful-request samples':'producer-reported summary'};}
 const metrics={ttft:metric('ttfts','ttft'),e2e:metric('latencies','e2el')};
 for(const m of Object.values(metrics))if(!completed){m.samples=[];m.percentiles={p50:null,p95:null,p99:null};}
 if(vectors.latencies&&vectors.ttfts&&mask)for(let i=0;i<n;i++)if(mask[i]&&vectors.latencies[i]+1e-9<vectors.ttfts[i])fail('End-to-end latency is smaller than time to first token.');
 const totalOutput=opt(raw.total_output_tokens,'total_output_tokens');
 if(totalOutput!==null&&!Number.isSafeInteger(totalOutput))fail('Total output tokens must be an integer.');
 if(totalOutput!==null&&vectors.output_lens&&mask){const total=vectors.output_lens.reduce((s,v,i)=>s+(mask[i]?v:0),0);if(total!==totalOutput)fail('Output-token total disagrees with the successful-request lengths.');}
 const throughput=opt(raw.request_throughput,'request_throughput');if(throughput!==null&&Math.abs(throughput-completed/d)>Math.max(.02,completed/d*.01))warnings.push('Reported throughput differs from count ÷ duration; this report uses count ÷ duration.');
 const goodput=opt(raw.request_goodput??raw['request_goodput:'],'request_goodput');if(goodput!==null&&goodput>completed/d+Math.max(.001,completed/d*.001))fail('Reported goodput exceeds completed-request throughput.');
 const meta=obj(raw.metadata)?raw.metadata:{};const field=k=>text(raw[k]??meta[k]);
 const identity={model:field('model_id')||field('model'),revision:field('model_revision'),precision:field('precision')||field('dtype'),tokenizer:field('tokenizer_revision'),workload:field('workload_id')||field('dataset_sha256'),cache:field('cache_policy'),runtime:field('runtime_digest')||field('runtime'),load:field('load_profile')};
 if(!identity.load&&(raw.request_rate!==undefined||raw.max_concurrency!==undefined))identity.load='rps='+text(raw.request_rate)+'; concurrency='+text(raw.max_concurrency)+'; burstiness='+text(raw.burstiness);
 const rows=mask?mask.map((success,i)=>({success,ttft_ms:vectors.ttfts?vectors.ttfts[i]*1000:null,e2e_ms:vectors.latencies?vectors.latencies[i]*1000:null,queue_ms:vectors.queue_times?vectors.queue_times[i]*1000:null})):null;
 return {format:raw.format==='vllm-console-summary'?'vllm-console-summary':'vllm-serve-json',source,identity,duration:d,completed,attempted:n,outputTokens:totalOutput,metrics,rows,reportedGoodput:goodput,warnings,synthetic:raw.synthetic===true};
}
const CONTRACT=['model','revision','precision','tokenizer','workload','cache','load'];
function contract(runs,overrides={}){const result={},issues=[];for(const k of [...CONTRACT,'runtime']){const vals=[...new Set(runs.map(r=>r.identity[k]).filter(Boolean))];if(vals.length>1)issues.push('Mixed '+k+' across trials.');if(overrides[k]&&vals.some(v=>v!==overrides[k]))issues.push('Entered '+k+' conflicts with imported metadata.');result[k]=text(overrides[k])||vals[0]||'';}return {values:result,issues};}
function attachQuality(run,q){
 if(!obj(q)||q.schema!=='hot-aisle/request-evaluation@1')fail('Unsupported evaluation sidecar.');
 if(q.source_sha256!==run.source.sha256||q.record_index!==run.source.record_index)fail('Evaluation does not match this exact source file and record index.');
 if(!run.rows||!Array.isArray(q.passed)||q.passed.length!==run.rows.length||q.passed.some(v=>typeof v!=='boolean'))fail('Evaluation requires one boolean per original request and an unambiguous success mask.');
 if(!text(q.evaluator)||!text(q.criterion_id))fail('Evaluation needs an evaluator and a criterion ID.');
 if(q.passed.some((v,i)=>v&&!run.rows[i].success))fail('Evaluation marks a failed request as passed.');
 return {...run,quality:{evaluator:text(q.evaluator),criterion:text(q.criterion_id),passed:q.passed}};
}
function aggregate(runs,settings={}){
 if(!runs.length)fail('Import at least one trial.');if(runs.length>MAX_RUNS)fail('At most 50 trials.');if(runs.reduce((n,r)=>n+(r.rows?.length||0),0)>250000)fail('At most 250,000 detailed request rows per side.');
 const seen=new Set();for(const r of runs){const k=r.source.sha256+':'+r.source.record_index;if(seen.has(k))fail('Duplicate trial: the same source record cannot be counted twice.');seen.add(k);}
 const c=contract(runs,settings.identity||{});if(c.issues.length)fail(c.issues.join(' '));
 const ttft=opt(settings.ttft,'TTFT limit'),e2e=opt(settings.e2e,'E2E limit');
 const useQ=settings.quality===true,useLatency=ttft!==null||e2e!==null;
 const label=useQ?(useLatency?'evaluator-passed, latency-qualified requests':'evaluator-passed requests'):(useLatency?'latency-qualified requests':'completed requests');
 const gates={ttft_ms:ttft,e2e_ms:e2e,include_client_queue:settings.queue===true,quality:useQ};
 const holds=[],warnings=[],criteria=new Set();let accepted=0;
 for(const r of runs){warnings.push(...r.warnings);if(useQ){if(!r.quality)holds.push('Missing evaluation for a trial.');else criteria.add(r.quality.criterion);}
  if(useQ||useLatency){if(!r.rows){holds.push('Request-level outcomes are unavailable; import a detailed JSON.');continue;}
   for(let i=0;i<r.rows.length;i++){const row=r.rows[i];if(!row.success)continue;
    if(ttft!==null&&row.ttft_ms===null)holds.push('TTFT samples are missing.');if(e2e!==null&&row.e2e_ms===null)holds.push('End-to-end samples are missing.');
    if(settings.queue&&useLatency&&row.queue_ms===null)holds.push('Client queue samples are missing.');
    const extra=settings.queue?(row.queue_ms??0):0;
    if((ttft===null||row.ttft_ms!==null&&row.ttft_ms+extra<=ttft)&&(e2e===null||row.e2e_ms!==null&&row.e2e_ms+extra<=e2e)&&(!useQ||r.quality?.passed[i]===true))accepted++;
   }
  }else accepted+=r.completed;
 }
 if(criteria.size>1)holds.push('Different evaluation criteria across trials.');
 const duration=runs.reduce((s,r)=>s+r.duration,0),completed=runs.reduce((s,r)=>s+r.completed,0),attempted=runs.every(r=>r.attempted!==null)?runs.reduce((s,r)=>s+r.attempted,0):null;
 if(!Number.isFinite(duration)||!Number.isFinite(completed/duration)||!Number.isFinite(accepted/duration))fail('Trial totals overflow the calculation.');
 const good=holds.length?null:accepted;
 const metrics={};for(const name of ['ttft','e2e']){
  const sampleComplete=runs.every(r=>r.metrics[name].samples!==null);
  if(sampleComplete){const a=runs.flatMap(r=>r.metrics[name].samples);metrics[name]={...percentiles(a),basis:'pooled successful-request samples',n:a.length};}
  else if(runs.length===1)metrics[name]={...runs[0].metrics[name].percentiles,basis:runs[0].metrics[name].basis,n:null};
  else{const ranges={};for(const p of ['p50','p95','p99']){const vals=runs.map(r=>r.metrics[name].percentiles[p]);ranges[p]=vals.every(v=>v!==null)?[Math.min(...vals),Math.max(...vals)]:null;}metrics[name]={p50:null,p95:null,p99:null,basis:'per-trial percentile ranges; percentiles are not averaged',ranges,n:null};}
 }
 const trialRates=runs.map(r=>r.completed/r.duration),mean=trialRates.reduce((a,b)=>a+b,0)/runs.length;
 return {identity:c.values,unit:label,gates,criterion:criteria.size===1?[...criteria][0]:'',runs:runs.length,duration,completed,attempted,failed:attempted===null?null:attempted-completed,accepted:good,rate:good===null?null:good/duration,completedRate:completed/duration,failureRate:attempted?1-completed/attempted:null,qualifiedFraction:attempted&&good!==null?good/attempted:null,metrics,trialRateRange:[Math.min(...trialRates),Math.max(...trialRates)],trialRateStd:runs.length>1?Math.sqrt(trialRates.reduce((s,x)=>s+(x-mean)**2,0)/(runs.length-1)):null,holds:[...new Set(holds)],warnings:[...new Set(warnings)],synthetic:runs.some(r=>r.synthetic),sources:runs.map(r=>r.source)};
}
function costing(a,p){
 const gpu=num(p.gpus,'Billable GPUs',1);if(!Number.isSafeInteger(gpu))fail('Billable GPUs must be an integer.');
 const rate=num(p.rate,'GPU-hour price'),extra=num(p.extra??0,'Hourly extras'),hourly=gpu*rate+extra;
 const supplied=p.total!==undefined&&p.total!==null&&p.total!=='';const total=supplied?num(p.total,'Total charge'):hourly*a.duration/3600;
 const cost=a.accepted===null||a.accepted===0?null:1000*total/a.accepted;
 if(!Number.isFinite(hourly)||!Number.isFinite(total)||(cost!==null&&!Number.isFinite(cost)))fail('Cost inputs overflow the calculation.');
 return {provider:text(p.provider),gpus:gpu,rate,extra,hourly,total,costPer1000:cost,basis:supplied?'user-supplied total charge':'modeled charge for summed benchmark windows',source:text(p.source),period:text(p.period),quote:text(p.quote),unit:a.unit};
}
function compare(a,pa,b,pb){
 const issues=[];for(const k of CONTRACT){if(!a.identity[k]||!b.identity[k])issues.push('Specify '+k+' for both sides.');else if(a.identity[k]!==b.identity[k])issues.push('Different '+k+'.');}
 if(canonical(a.gates)!==canonical(b.gates)||a.unit!==b.unit||a.criterion!==b.criterion)issues.push('Different result or acceptance basis.');
 if(a.holds.length||b.holds.length)issues.push('A request gate could not be evaluated.');if(a.accepted===0||b.accepted===0)issues.push('A side produced zero qualifying requests.');
 if(pa.basis!==pb.basis)issues.push('Different billing bases.');
 if(a.sources.some(x=>b.sources.some(y=>x.sha256===y.sha256&&x.record_index===y.record_index)))issues.push('The same source trial appears on both sides.');
 if(pa.costPer1000===null||pb.costPer1000===null)issues.push('Cost per result is unavailable.');
 const eligible=!issues.length;
 return {status:eligible?'COMPARISON_OF_SUPPLIED_EVIDENCE':'DESCRIPTIVE_ONLY',issues:[...new Set(issues)],saving:eligible&&pb.costPer1000>0?1-pa.costPer1000/pb.costPer1000:null,winner:eligible?(pa.costPer1000<pb.costPer1000?'A':pa.costPer1000>pb.costPer1000?'B':'tie'):null,synthetic:a.synthetic||b.synthetic};
}
function threshold(hotRate,hotHourly,otherHourly){num(hotRate,'Throughput');num(hotHourly,'Hot Aisle allocation-hour price',Number.MIN_VALUE);num(otherHourly,'Other allocation-hour price');return hotRate*otherHourly/hotHourly;}
function receiptHTML(packet){
 const e=escape,fmt=x=>x===null||x===undefined?'Not available':x.toLocaleString('en-US',{maximumFractionDigits:3}),usd=x=>x===null?'Not available':'$'+x.toFixed(x<1?4:2);
 const rows=packet.sides.map(s=>{const a=s.aggregate,c=s.cost;return '<article><h2>'+e(s.label)+'</h2><p>'+e(a.identity.model||'Model not supplied')+'</p><strong class="price">'+usd(c.costPer1000)+'</strong><p>per 1,000 '+e(a.unit)+'</p><dl><dt>Result rate</dt><dd>'+fmt(a.rate)+' / second</dd><dt>Completed / attempted</dt><dd>'+fmt(a.completed)+' / '+fmt(a.attempted)+'</dd><dt>Trials / total measured seconds</dt><dd>'+a.runs+' / '+fmt(a.duration)+'</dd><dt>Allocation</dt><dd>'+c.gpus+' GPUs × '+usd(c.rate)+'/hour + '+usd(c.extra)+'/hour extras</dd><dt>Cost basis</dt><dd>'+e(c.basis)+'; '+usd(c.total)+'</dd><dt>Price source / period</dt><dd>'+e(c.source)+' / '+e(c.period)+'</dd><dt>Quote / cost note</dt><dd>'+e(c.quote||'None')+'</dd></dl><h3>Successful-request latency (ms)</h3><table><tr><th></th><th>p50</th><th>p95</th><th>p99</th></tr>'+['ttft','e2e'].map(k=>'<tr><th>'+e(k.toUpperCase())+'</th>'+['p50','p95','p99'].map(p=>'<td>'+fmt(a.metrics[k][p])+'</td>').join('')+'</tr><tr><td colspan="4">'+e(a.metrics[k].basis)+(a.metrics[k].ranges?' · ranges: '+e(JSON.stringify(a.metrics[k].ranges)):'')+'</td></tr>').join('')+'</table><details><summary>Conditions and input commitments</summary><pre>'+e(JSON.stringify({identity:a.identity,gates:a.gates,criterion:a.criterion,holds:a.holds,warnings:a.warnings},null,2))+'</pre><h3>Input commitments</h3>'+a.sources.map(x=>'<p class="hash">SHA-256 '+e(x.sha256)+'<br>Record '+x.record_index+' · '+x.bytes+' bytes</p>').join('')+'</details></article>';}).join('');
 const comp=packet.comparison;
 return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Workload cost report</title><style>body{font:15px/1.5 system-ui,sans-serif;max-width:1000px;margin:35px auto;padding:0 24px;color:#202322;background:#fafaf7}header{border-bottom:2px solid;padding-bottom:15px}h1{font-size:30px}h2{font-size:23px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:35px}.price{font-size:42px}dl{display:grid;grid-template-columns:1fr 1fr;gap:7px}dd{margin:0}dt{color:#575c58}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:7px;border-bottom:1px solid #ddd}.hash{overflow-wrap:anywhere;font:11px/1.5 monospace}.notice{padding:12px;background:#eee9cf}footer{border-top:1px solid;margin-top:24px;font-size:12px}@media(max-width:480px){.grid{display:block}dl{grid-template-columns:1fr}dd{margin-bottom:12px}}@media print{body{margin:0;background:white}.grid{display:block}article{break-inside:avoid}h3{break-after:avoid}details{display:none}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}body{font-size:11px}.price{font-size:32px}h1{font-size:25px}h2{font-size:18px}footer{font-size:10px}}</style><header><p>WORKLOAD REPORT · '+e(packet.version)+'</p><h1>'+e(packet.title||'Cost per result')+'</h1><p>'+e(packet.generated_at)+'</p></header><p class="notice">'+(packet.synthetic?'SYNTHETIC DEMONSTRATION. These are software-test fixtures, not GPU measurements.':'Imported producer results and user-supplied commercial inputs. No independent hardware rerun or source authenticity is claimed.')+'</p>'+(comp?'<p><b>'+e(comp.status)+'</b> '+(comp.saving!==null?e((Math.abs(comp.saving)*100).toFixed(1)+'% '+(comp.saving>=0?'lower':'higher')+' modeled cost for A relative to B.'):e(comp.issues.join(' ')))+'</p>':'')+'<div class="grid">'+rows+'</div><footer>Completion is transport success, not task correctness. Latency gates and evaluator-declared outcomes are separate. Pooled windows do not establish production availability; setup, idle time and omitted costs remain outside window estimates. Raw prompts, generated text, source filenames and error bodies are excluded. Keep originals privately to verify their hashes against this report. Packet checksum binds supplied bytes, not the truth of their producer. Export the JSON packet for recomputation. Independent tool by Second Run; no provider endorsement.</footer></html>';
}

function sha256(input){
 const bytes=input instanceof Uint8Array?input:new Uint8Array(input),len=bytes.length;
 const k=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
 const h=new Uint32Array([0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]);
 const buffer=new Uint8Array(Math.ceil((len+9)/64)*64);buffer.set(bytes);buffer[len]=128;const view=new DataView(buffer.buffer);view.setUint32(buffer.length-8,Math.floor(len/0x20000000));view.setUint32(buffer.length-4,(len*8)>>>0);
 const w=new Uint32Array(64),r=(x,n)=>(x>>>n)|(x<<(32-n));
 for(let pos=0;pos<buffer.length;pos+=64){for(let i=0;i<16;i++)w[i]=view.getUint32(pos+4*i);for(let i=16;i<64;i++){let x=w[i-15],y=w[i-2];w[i]=(w[i-16]+(r(x,7)^r(x,18)^(x>>>3))+w[i-7]+(r(y,17)^r(y,19)^(y>>>10)))>>>0;}
  let [a,b,c,d,e,f,g,z]=h;for(let i=0;i<64;i++){let t1=(z+(r(e,6)^r(e,11)^r(e,25))+((e&f)^(~e&g))+k[i]+w[i])>>>0,t2=((r(a,2)^r(a,13)^r(a,22))+((a&b)^(a&c)^(b&c)))>>>0;z=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;}const q=[a,b,c,d,e,f,g,z];for(let i=0;i<8;i++)h[i]=(h[i]+q[i])>>>0;
 }
 return [...h].map(v=>v.toString(16).padStart(8,'0')).join('');
}
function restoreRun(r){
 if(!obj(r)||!obj(r.source)||!/^([a-f0-9]{64})$/.test(r.source.sha256)||!Number.isSafeInteger(r.source.record_index)||r.source.record_index<0||!Number.isSafeInteger(r.source.bytes)||r.source.bytes<0)fail('Invalid normalized source commitment.');
 const raw={duration:r.duration,completed:r.completed,synthetic:r.synthetic,model_id:r.identity?.model,total_output_tokens:r.outputTokens};if(r.attempted!==null)raw.num_prompts=r.attempted;
 for(const [key,id] of Object.entries({model_revision:'revision',precision:'precision',tokenizer_revision:'tokenizer',workload_id:'workload',cache_policy:'cache',runtime_digest:'runtime',load_profile:'load'}))raw[key]=r.identity?.[id]||'';
 for(const [key,label] of [['ttft','ttft'],['e2e','e2el']])for(const p of ['p50','p95','p99'])raw[p+'_'+label+'_ms']=r.metrics?.[key]?.percentiles?.[p];
 if(r.rows!==null){if(!Array.isArray(r.rows)||r.rows.some(row=>!obj(row)||typeof row.success!=='boolean'))fail('Invalid normalized request outcomes.');raw.errors=r.rows.map(row=>row.success?'':'redacted failure');for(const [key,field] of [['ttfts','ttft_ms'],['latencies','e2e_ms'],['queue_times','queue_ms']]){if(r.rows.every(row=>row[field]!==null)){raw[key]=r.rows.map(row=>num(row[field],field)/1000);}else if(r.rows.some(row=>row[field]!==null))fail('Mixed missing request samples.');}}
 let clean=normalize(raw,r.source);if(r.quality)clean=attachQuality(clean,{schema:'hot-aisle/request-evaluation@1',source_sha256:r.source.sha256,record_index:r.source.record_index,evaluator:r.quality.evaluator,criterion_id:r.quality.criterion,passed:r.quality.passed});return clean;
}
function recompute(envelope){
 if(!obj(envelope)||envelope.schema!=='hot-aisle/sealed-report@1'||!obj(envelope.payload))fail('Unsupported report envelope.');const p=envelope.payload;
 if(sha256(new TextEncoder().encode(canonical(p)))!==envelope.sha256)fail('Report checksum mismatch.');if(p.schema!=='hot-aisle/workload-report@2'||p.version!==VERSION||!Array.isArray(p.sides)||!p.sides.length||p.sides.length>2)fail('Unsupported report payload.');
 const sides=p.sides.map(s=>{if(!Array.isArray(s.normalized))fail('Missing normalized trials.');const runs=s.normalized.map(restoreRun),a=aggregate(runs,s.settings),c=costing(a,s.price);if(canonical({...a,warnings:[]})!==canonical({...s.aggregate,warnings:[]})||canonical(c)!==canonical(s.cost))fail('Derived results disagree with the normalized evidence.');return {...s,aggregate:a,cost:c};});
 const comparison=sides.length===2?compare(sides[0].aggregate,sides[0].cost,sides[1].aggregate,sides[1].cost):null;if(canonical(comparison)!==canonical(p.comparison))fail('Comparison does not match the evidence.');if(p.synthetic!==sides.some(s=>s.aggregate.synthetic))fail('Synthetic status mismatch.');return {...p,sides,comparison};
}

const API={sha256,restoreRun,recompute,VERSION,MAX_REQUESTS,MAX_RUNS,parseDocuments,parseConsole,normalize,aggregate,contract,attachQuality,costing,compare,threshold,quantile,canonical,receiptHTML,escape};if(typeof module==='object'&&module.exports)module.exports=API;root.HA=API;
})(typeof globalThis==='undefined'?this:globalThis);
