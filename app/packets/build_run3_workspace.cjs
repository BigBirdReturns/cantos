/* Build the two Run 3 decision editions from retained request and grade records.
   This script reads the published campaign and the council's versioned core candidate;
   it writes only beside itself. No request is simulated or sent. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');

const HERE = __dirname;
const RESULTS = 'D:/Projects/Organs/AXM/axm-tools/main/hot-aisle/campaign/results';
const REPORT = path.join(RESULTS, 'RUN3-RESULTS.md');
const BASELINE = 'D:/Projects/Organs/AXM/axm-tools/sessions/compute-shop-compare-20260925/supervision/codex-takeover-20260926/FIRST-BASELINE-RESULT.md';
const CORE_102 = path.resolve(HERE, '../../opus/deliverables/research-core-1.0.2.js');
const CORE_101 = path.resolve(HERE, '../../base/owner-research-core/research-core-1.0.1.js');
const corePath = fs.existsSync(CORE_102) ? CORE_102 : CORE_101;
const C = require(corePath);

function assert(x, message) { if (!x) throw new Error(message); }
function readJson(p) { return JSON.parse(fs.readFileSync(p, 'utf8')); }
function round1(n) { return Math.round(n * 10) / 10; }
function source(arm) { return path.join(RESULTS, `run3-scored-${arm}`); }

function armData(arm) {
  const dir = source(arm);
  const planPath = path.join(dir, 'replay/plan.json');
  const rowsPath = path.join(dir, 'replay/requests.jsonl');
  const gradePath = path.join(dir, 'grade/evaluation.json');
  const plan = readJson(planPath), grade = readJson(gradePath);
  const raw = fs.readFileSync(rowsPath, 'utf8').trimEnd().split(/\r?\n/).map(JSON.parse);
  raw.sort((a,b) => a.request_index-b.request_index);
  assert(raw.length === 8622 && grade.passed.length === 8622, `${arm}: incomplete request or grade rows`);
  const tasks = raw.map((r,i) => {
    assert(r.request_index === i, `${arm}: noncontiguous request index at ${i}`);
    const first = r.first_token_ts == null ? null : round1((r.first_token_ts-r.scheduled_ts)*1000);
    const elapsed = r.end_ts == null ? null : round1((r.end_ts-r.scheduled_ts)*1000);
    return {
      id:`request.${String(i).padStart(5,'0')}`,
      scheduled_at_ms:round1((r.scheduled_ts-plan.start_ts)*1000),
      attempts:[{status:r.error ? 'error' : 'ok',first_token_ms:first,elapsed_ms:elapsed,correct:Boolean(grade.passed[i])}]
    };
  });
  const accepted = tasks.filter(t => t.attempts.some(a => a.status==='ok' && a.correct && a.first_token_ms<=1000 && a.elapsed_ms<=60000)).length;
  const correct = tasks.filter(t => t.attempts.some(a => a.correct)).length;
  return {tasks, plan, accepted, correct, paths:{planPath,rowsPath,gradePath}};
}

const commonPins = {
  taskset:'EvalPlus HumanEval+ 164 and MBPP+ 378, cycled over 8,622 requests',
  contract:'EvalPlus base+plus, first token <= 1000 ms, completion <= 60000 ms',
  load:'Azure LLM inference CODE trace, factor 0.95, one-hour replay',
  boundary:'Run 3 scored T0 arms, 2026-09-24',
  model:'Qwen3-Coder-30B-A3B-Instruct-FP8',
  revision:'dcaee4d4dfc5ee71ad501f01f530e5652438fde0',
  precision:'FP8',
  tokenizer:'Qwen3-Coder-30B-A3B-Instruct-FP8',
  runtime:'vLLM 0.30.0',
  cache:'Run 3 frozen serving configuration'
};
const dep = (id,revision=1) => ({id,revision});
function record(id,kind,title,summary,data,deps=[],tier='operator_supplied',disposition='supported') {
  return {id,kind,title,summary,tier,disposition,deps,data};
}
function runRecord(id,label,vendor,hardware,minutes,basis,rate,arm) {
  return record(id,'run',label,
    `${arm.tasks.length.toLocaleString()} retained scored requests, ${arm.accepted.toLocaleString()} accepted at the registered limits. ${basis.replaceAll('_',' ')} list-rate window.`,
    {schema:'second-run/task-run@1',run_id:id,label,evidence:'producer_reported',pins:commonPins,
     identity:{vendor,hardware,arm:id.toUpperCase().replace('-','/'),runtime:'vLLM 0.30.0',window_minutes:minutes,basis},
     billing:{rate_usd_per_hour:rate,cost_basis:'list',currency:'USD',scope:`One ${hardware} at list price over ${minutes} minute ${basis.replaceAll('_',' ')} window`},
     tasks:arm.tasks},[dep('run3-source')]);
}
function calcData(ws) {
  const s=C.state(ws);
  const runs=['a-t0','n-t0'].map(id=>C.latest(s,id));
  const p=C.latest(s,'policy');
  return {...C.compare(runs.map(r=>r.data),p.data),selectedRecordIds:runs.map(r=>r.id),recipe:'task-cost@1'};
}
function provenance(arms,packet1,packet2) {
  const item=(file,lines,scope)=>({file:file.replaceAll('\\','/'),lines,scope});
  const figures={
    workload:item(REPORT,[4,5,6,7],'Run 3 registered workload and acceptance rule'),
    'A/T0 accepted 4336':item(arms.a.paths.gradePath,[1],'Grade bits joined by request index to timed request rows'),
    'N/T0 accepted 4280':item(arms.n.paths.gradePath,[1],'Grade bits joined by request index to timed request rows'),
    'A/T0 requests 8622':item(arms.a.paths.rowsPath,[1,8622],'One retained request per line'),
    'N/T0 requests 8622':item(arms.n.paths.rowsPath,[1,8622],'One retained request per line'),
    'A/T0 $2.99/h':item(REPORT,[12],'Published list rate'),
    'N/T0 $4.41/h':item(REPORT,[12],'Published list rate'),
    'A/T0 64.7 min':item(REPORT,[18,44],'Own-seat equivalent window'),
    'N/T0 69.8 min':item(REPORT,[18],'Closed ledger window'),
    'A/T0 $0.74/1000':item(REPORT,[18],'Report display rounds recomputed list-cost value'),
    'N/T0 $1.20/1000':item(REPORT,[18],'Report display rounds recomputed list-cost value'),
    'H100 $2.49/h scenario':item(REPORT,[23,28],'Report flip-table assumption; no new run'),
    'H100 $0.68/1000 scenario':item(REPORT,[28],'Report display rounds recomputed scenario value'),
    '26 Sep baseline 4274':item(BASELINE,[1,14],'Separate later Hot Aisle baseline, lineage only'),
    'A/T0 TTFT p50/p95/p99 53/155/571 ms':item(REPORT,[15],'Reported Run 3 timing summary'),
    'N/T0 TTFT p50/p95/p99 35/76/2254 ms':item(REPORT,[15],'Reported Run 3 timing summary')
  };
  return {schema:'cantos/figure-provenance@1',source_date:'2026-09-24',figures,
    request_fields:{
      'A/T0':{scheduled_at_ms:item(arms.a.paths.rowsPath,[1,8622],'scheduled_ts minus plan.start_ts'),first_token_ms:item(arms.a.paths.rowsPath,[1,8622],'first_token_ts minus scheduled_ts'),elapsed_ms:item(arms.a.paths.rowsPath,[1,8622],'end_ts minus scheduled_ts'),correct:item(arms.a.paths.gradePath,[1],'passed[request_index]'),start:item(arms.a.paths.planPath,[1],'start_ts')},
      'N/T0':{scheduled_at_ms:item(arms.n.paths.rowsPath,[1,8622],'scheduled_ts minus plan.start_ts'),first_token_ms:item(arms.n.paths.rowsPath,[1,8622],'first_token_ts minus scheduled_ts'),elapsed_ms:item(arms.n.paths.rowsPath,[1,8622],'end_ts minus scheduled_ts'),correct:item(arms.n.paths.gradePath,[1],'passed[request_index]'),start:item(arms.n.paths.planPath,[1],'start_ts')}
    },
    derived:{edition1_sha256:packet1.sha256,edition2_sha256:packet2.sha256,formula:'rate_usd_per_hour * window_minutes / 60 / accepted; multiply by 1000 for display'}
  };
}

async function main() {
  assert(C.VERSION === '1.0.2',`ResearchCore ${C.VERSION} cannot represent the hardware contract; waiting for ${CORE_102}`);
  const a=armData('a-t0'),n=armData('n-t0');
  assert(a.accepted===4336 && n.accepted===4280 && a.correct===4371 && n.correct===4329,'Retained counts disagree with Run 3 report');
  assert(a.plan.trace_sha256===n.plan.trace_sha256 && a.plan.tasks_sha256===n.plan.tasks_sha256,'Arms lack common trace/task pins');
  const ws=C.empty('Run 3 · MI300X versus H100 · 24 Sep 2026');
  const actor='Sol backfill';
  const put=(r,at)=>C.put(ws,r,actor,at);
  await put(record('run3-source','source','Run 3 scored archive','Retained scored Run 3 request, grade, ledger and report files. Operator supplied; checksum journal does not authenticate the source.',
    {path:'hot-aisle/campaign/results',report:'hot-aisle/campaign/results/RUN3-RESULTS.md',arms:['run3-scored-a-t0','run3-scored-n-t0'],date:'2026-09-24'}),'2026-09-29T06:00:00Z');
  await put(record('baseline-lineage','claim','26 Sep Hot Aisle baseline','A fresh Hot Aisle allocation recorded 4,274 accepted of 8,622. This is a later lineage observation, not a Run 3 comparison arm.',
    {accepted:4274,requests:8622,date:'2026-09-26',source:'compute-shop-compare-20260925/supervision/codex-takeover-20260926/FIRST-BASELINE-RESULT.md'}),'2026-09-29T06:00:01Z');
  await put(record('policy','policy','Run 3 registered acceptance and cost',
    'Correct EvalPlus base+plus, first token within 1 second, completion within 60 seconds, and list-rate whole-run cost. No acceptance-rate floor: Run 3 preregistered gates were a complete hour, no holds, transport failures under 1% (run3/PREREG.md L95-115).',
    {grader:'recorded',deadline_ms:60000,first_token_ms:1000,quality_floor:0,min_tasks:8622,cost_basis:'list',comparison_mode:'hardware'},[dep('run3-source')]),'2026-09-29T06:00:02Z');
  await put(runRecord('a-t0','A/T0 · Hot Aisle MI300X','Hot Aisle','1× MI300X',64.7,'own_seat_equivalent',2.99,a),'2026-09-29T06:00:03Z');
  await put(runRecord('n-t0','N/T0 · DigitalOcean H100','DigitalOcean','1× H100',69.8,'closed_ledger',4.41,n),'2026-09-29T06:00:04Z');
  await put(record('calculation','calculation','Run 3 cost per accepted closure','Recomputed from the pinned policy and both retained run records.',calcData(ws),
    [dep('policy'),dep('a-t0'),dep('n-t0')]),'2026-09-29T06:00:05Z');
  let first=C.latest(C.state(ws),'calculation').data;
  assert(first.winner==='a-t0',`Expected MI300X winner, got ${first.winner}`);
  await put(record('decision','conclusion','Choose Hot Aisle MI300X at Run 3 list prices',
    'At $2.99/h and $4.41/h, the MI300X is about $0.74 versus $1.20 per 1,000 accepted closures. This is one measured run per arm, at list prices and the recorded windows.',
    {winner:'a-t0',decision_class:'hardware',edition:1,scope:'Run 3 one-run-per-arm list-price comparison'},
    [dep('calculation'),dep('baseline-lineage')]),'2026-09-29T06:00:06Z');
  await C.review(ws,'decision','accept','The Run 3 operator record selects the MI300X because the two arms accepted similar numbers of the same scheduled requests while the list-rate whole-run cost is lower. “Run 3 operator record” is a reviewer label, not an authenticated person or a fresh review.','Run 3 operator record','2026-09-29T06:00:07Z');
  await C.freeze(ws,'decision','Sol backfill','2026-09-29T06:00:08Z');
  const packet1=await C.pack(ws);
  await C.verifyPacket(packet1);
  fs.writeFileSync(path.join(HERE,'run3-decision.workspace.json'),JSON.stringify(packet1));

  const prior=C.latest(C.state(ws),'n-t0');
  await put({...prior,summary:'Scenario: H100 list rate set to $2.49/h; retained measurements and closed ledger window unchanged.',
    data:{...prior.data,billing:{...prior.data.billing,rate_usd_per_hour:2.49}}},'2026-09-29T06:01:00Z');
  await put(record('calculation','calculation','Run 3 cost per accepted closure at $2.49 H100 rate',
    'Arithmetic scenario over unchanged retained requests; no new model run.',calcData(ws),
    [dep('policy'),dep('a-t0'),dep('n-t0',2)]),'2026-09-29T06:01:01Z');
  const second=C.latest(C.state(ws),'calculation').data;
  assert(second.winner==='n-t0',`Expected the H100 arm to win at $2.49/h with no acceptance floor; got ${second.winner}`);
  const h100=second.results.find(r=>r.run_id==='n-t0');
  assert(h100 && h100.eligible && h100.blockers.length===0,'Expected the H100 arm eligible with no blockers');
  await put(record('decision','conclusion','Choose DigitalOcean H100 if its list rate is $2.49/h',
    'At $2.49/h, the unchanged H100 measurements yield about $0.68 per 1,000 accepted against the MI300X at about $0.74, so the ranking flips. This supersedes Edition 01 on a price assumption only; the retained requests, grades and windows are unchanged and no model run was repeated.',
    {winner:'n-t0',economic_lowest_cost:'n-t0',decision_class:'hardware',edition:2,supersedes:'Edition 01',scope:'Run 3 retained measurements with the H100 list-rate scenario from the report flip table'},
    [dep('calculation',2),dep('baseline-lineage')]),'2026-09-29T06:01:02Z');
  await C.review(ws,'decision','accept','The Run 3 report’s flip table puts $2.49/h for H100 below the approximate $2.72/h economic crossing. With no acceptance-rate floor in the registered policy, the H100 arm is eligible and becomes the lowest complete cost per accepted closure. The retained request outcomes are unchanged; this is an arithmetic rate scenario. “Run 3 operator record” is a reviewer label, not an authenticated person.','Run 3 operator record','2026-09-29T06:01:03Z');
  await C.freeze(ws,'decision','Sol backfill','2026-09-29T06:01:04Z');
  const packet2=await C.pack(ws);
  await C.verifyPacket(packet2);
  fs.writeFileSync(path.join(HERE,'run3-decision.workspace.edition2.json'),JSON.stringify(packet2));
  fs.writeFileSync(path.join(HERE,'PROVENANCE.json'),JSON.stringify(provenance({a,n},packet1,packet2),null,2)+'\n');
  console.log(JSON.stringify({core:corePath,version:C.VERSION,edition1:{sha256:packet1.sha256,winner:first.winner,bytes:fs.statSync(path.join(HERE,'run3-decision.workspace.json')).size},edition2:{sha256:packet2.sha256,winner:second.winner,bytes:fs.statSync(path.join(HERE,'run3-decision.workspace.edition2.json')).size},accepted:{a:a.accepted,n:n.accepted}}));
}
main().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
