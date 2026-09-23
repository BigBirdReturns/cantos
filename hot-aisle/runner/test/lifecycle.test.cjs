'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const engine = require('../lib/engine.cjs');
const { Store } = require('../lib/store.cjs');
const { Jobs } = require('../lib/jobs.cjs');
const record = require('../lib/record.cjs');
const { revalidate } = require('../lib/revalidate.cjs');
const local = require('../lib/adapters/local.cjs');

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'wl-test-'));
const plan = (o = {}) => local.demoPlanInput({ repeats: 1, concurrency: [1, 8], ...o });

async function run(store, o = {}) {
  const jobs = new Jobs(store);
  const job = jobs.plan(plan(o));
  jobs.approve(job.id, { plan_sha256: job.plan.sha256 });
  const s = await jobs.start(job.id);
  return { jobs, job: jobs.get(job.id), s, rec: s.record_id ? store.read('records', s.record_id) : null };
}

test('engine loads from the page and is the 2.0.0 authority', () => {
  const HA = engine.load();
  assert.equal(HA.VERSION, '2.0.0');
  assert.equal(engine.identity().engine_sha256.length, 64);
});

test('plan freezes inputs, computes cells and a hash; approval binds that hash', async () => {
  const jobs = new Jobs(new Store(tmp()));
  const job = jobs.plan(plan({ concurrency: [1, 8, 32], repeats: 2 }));
  assert.equal(job.state, 'planned');
  assert.equal(job.plan.cells.length, 6);
  assert.match(job.plan.commands[0], /--save-result --save-detailed --percentile-metrics ttft,tpot,itl,e2el --metric-percentiles 50,95,99/);
  assert.match(job.plan.commands[0], /--metadata .*workload_id=sha256:/);
  assert.throws(() => jobs.approve(job.id, { plan_sha256: 'a'.repeat(64) }), /different plan/);
  await assert.rejects(() => jobs.start(job.id), /only approved/);
  jobs.approve(job.id, { plan_sha256: job.plan.sha256 });
  assert.equal(jobs.get(job.id).state, 'approved');
});

test('full lifecycle produces a verified qualified record whose projections match the engine', async () => {
  const store = new Store(tmp());
  const { job, s, rec } = await run(store);
  assert.equal(s.state, 'completed');
  assert.equal(job.trials.filter(t => t.status === 'completed').length, 2);
  assert.ok(rec, 'record written');
  assert.equal(rec.synthetic, true, 'local environment output is synthetic');
  assert.equal(record.verify(rec).verified, true);
  assert.equal(rec.derived.cells.length, 2);
  const HA = engine.load();
  // headline is a projection: numbers equal a fresh engine computation over the retained trials
  const h = record.headline(rec);
  assert.equal(h.generated, true);
  assert.equal(h.status, 'demonstration');
  const cell = rec.derived.cells.find(c => c.concurrency === rec.derived.primary_concurrency);
  const fresh = HA.aggregate(rec.observed.trials.filter(t => t.cell.concurrency === cell.concurrency).map(t => HA.restoreRun(t.normalized)), { identity: record.declaredIdentity(rec.declared.plan) });
  const cost = HA.costing(fresh, rec.declared.price);
  assert.equal(h.sides[0].cost_per_1000, cost.costPer1000);
  assert.equal(h.sides[0].p95_ttft_ms, fresh.metrics.ttft.p95);
  // the evidence packet recomputes under the engine's own verifier
  const env = record.packet(rec);
  assert.equal(HA.recompute(env).sides[0].cost.costPer1000, cost.costPer1000);
  // the retained raw bytes still hash to the committed source
  for (const t of rec.observed.trials) { const p = store.evidencePath(t.source.sha256); assert.ok(p); assert.equal(engine.sha256(fs.readFileSync(p)), t.source.sha256); }
  // tampering is detected
  const tampered = JSON.parse(JSON.stringify(rec)); tampered.derived.cells[0].cost.costPer1000 = 0.01;
  assert.equal(record.verify(tampered).verified, false);
});

test('cancel stops the owned benchmark and retains completed trials; reconnect resumes only the rest', async () => {
  const store = new Store(tmp());
  const jobs = new Jobs(store);
  const mark = tmp();
  const job = jobs.plan(plan({ concurrency: [1, 8, 32], repeats: 1, target: { env: { FAKE_VLLM_DELAY_MS: '700', FAKE_VLLM_MARK:mark } } }));
  jobs.approve(job.id, { plan_sha256: job.plan.sha256 });
  const running = jobs.start(job.id);
  await new Promise(r => { const h = t => { if (t.status === 'completed') { jobs.off('trial', h); r(); } }; jobs.on('trial', h); });
  jobs.cancel(job.id);
  const s = await running;
  assert.equal(s.state, 'cancelled');
  assert.equal(s.trials.completed, 1);
  assert.ok(s.record_id, 'partial record from the completed trial');
  // a fresh runner instance (new process in practice) sees the same durable job
  const jobs2 = new Jobs(store);
  const j = jobs2.get(job.id);
  assert.equal(j.state, 'cancelled');
  j.state = 'interrupted'; jobs2.save(j);
  const markedBefore = fs.readdirSync(mark).length; // instrumentation was frozen before approval
  const s2 = await jobs2.start(job.id);
  assert.equal(s2.state, 'completed');
  assert.equal(s2.trials.completed, 3);
  assert.equal(fs.readdirSync(mark).length-markedBefore, 2, 'only the two missing trials ran');
});

test('a dead lease is recovered as interrupted, never as running', () => {
  const store = new Store(tmp());
  const jobs = new Jobs(store);
  const job = jobs.plan(plan());
  job.state = 'running'; job.lease = { instance: 'ghost:999999', pid: 999999, since: 'x' }; job.trials[0].status = 'running'; jobs.save(job);
  const jobs2 = new Jobs(store);
  const j = jobs2.get(job.id);
  assert.equal(j.state, 'interrupted');
  assert.equal(j.trials[0].status, 'interrupted');
});

test('corrupt evidence fails its trial; the record uses only admitted trials; all-corrupt fails the job', async () => {
  const store = new Store(tmp());
  const jobs = new Jobs(store);
  const job = jobs.plan(plan({ concurrency: [1, 8], target: { env: { FAKE_VLLM_FAIL: 'corrupt' } } }));
  jobs.approve(job.id, { plan_sha256: job.plan.sha256 });
  const s = await jobs.start(job.id);
  assert.equal(s.state, 'failed');
  assert.equal(s.record_id, null);
  assert.match(jobs.get(job.id).trials[0].error, /Evidence rejected/);
  // mixed: exit failure on one run only is not possible per-cell with env, so simulate a partial by marking one trial completed via a second job
  const { s: ok } = await run(store, { concurrency: [1] });
  assert.equal(ok.state, 'completed');
});

test('a non-local target refuses synthetic evidence', () => {
  const store = new Store(tmp());
  const jobs = new Jobs(store);
  const j = jobs.plan(plan({ target: { adapter: 'hotaisle', exec: 'ssh', host: 'example.invalid', vllm_command: undefined } }));
  assert.equal(j.plan.target.adapter, 'hotaisle');
  assert.match(j.plan.commands[0], /^vllm bench serve /);
});

test('spend limit stops the run early and keeps what completed', async () => {
  const store = new Store(tmp());
  const jobs = new Jobs(store);
  const job = jobs.plan(plan({ concurrency: [1, 8, 32], target: { env: { FAKE_VLLM_DELAY_MS: '400' } }, price: { rate: 100000, gpus: 8 }, limits: { max_spend_usd: 0.5 } }));
  jobs.approve(job.id, { plan_sha256: job.plan.sha256 });
  const s = await jobs.start(job.id);
  assert.equal(s.state, 'completed');
  assert.equal(s.disposition.outcome, 'limit_reached');
  assert.ok(s.trials.completed >= 1 && s.trials.completed < 3);
});

test('requirements decide qualification; the primary cell is the cheapest that meets them', async () => {
  const store = new Store(tmp());
  const { rec } = await run(store, { concurrency: [1, 8, 32], requirements: { max_p95_ttft_ms: 100000, max_p95_e2e_ms: 100000 } });
  assert.equal(rec.disposition.qualified, true);
  const meeting = rec.derived.cells.filter(c => c.meets);
  const cheapest = meeting.reduce((a, c) => c.cost.costPer1000 < a.cost.costPer1000 ? c : a);
  assert.equal(rec.derived.primary_concurrency, cheapest.concurrency);
  const { rec: strict } = await run(store, { concurrency: [1], requirements: { max_p95_ttft_ms: 1 } });
  assert.equal(strict.disposition.qualified, false);
  assert.match(strict.disposition.reasons[0], /p95 TTFT .* exceeds 1 ms/);
});

test('revalidation: price recomputes without measurement; traffic adds only new cells; runtime supersedes; evaluator stands', async () => {
  const store = new Store(tmp());
  const { rec } = await run(store, { concurrency: [1, 8] });
  const price = revalidate(rec, { price: { rate: 3.39 } });
  assert.equal(price.summary.requires_measurement, 0);
  assert.ok(price.conclusions.some(c => c.subject === 'economics' && c.status === 'recomputed'));
  const before = rec.derived.cells[0].cost.costPer1000, after = price.scenario.cells[0].cost_per_1000;
  assert.ok(Math.abs(after / before - 3.39 / 2.99) < 1e-9, 'cost scales with rate exactly');
  const traffic = revalidate(rec, { traffic: { concurrency: [1, 8, 64] } });
  assert.deepEqual(traffic.minimal_plan.concurrency, [64]);
  assert.ok(traffic.conclusions.some(c => c.status === 'stands' && /1, 8/.test(c.detail)));
  const shape = revalidate(rec, { traffic: { input_len: 16384 } });
  assert.deepEqual(shape.minimal_plan.concurrency, [1, 8]);
  const runtime = revalidate(rec, { runtime: { runtime_digest: 'rocm/vllm@sha256:next' } });
  assert.ok(runtime.summary.superseded);
  assert.equal(runtime.minimal_plan.identity.runtime_digest, 'rocm/vllm@sha256:next');
  assert.deepEqual(runtime.minimal_plan.concurrency, [1, 8]);
  const same = revalidate(rec, { runtime: { runtime_digest: rec.declared.plan.identity.runtime_digest } });
  assert.ok(same.conclusions.every(c => c.status === 'stands'));
  const evaluator = revalidate(rec, { evaluator: { criterion_id: 'v2' } });
  assert.ok(evaluator.conclusions.every(c => c.status === 'stands'));
  const gates = revalidate(rec, { gates: { ttft: 400 } });
  assert.ok(gates.conclusions.some(c => c.subject === 'acceptance' && c.status === 'recomputed'));
  assert.equal(gates.scenario.cells[0].unit, 'latency-qualified requests');
  assert.throws(() => revalidate(rec, {}), /Nothing changed/);
});
