#!/usr/bin/env node
'use strict';
/* workload — command line over the same core the page and the MCP server use. */
const fs = require('node:fs');
const path = require('node:path');
const engine = require('../lib/engine.cjs');
const { Store } = require('../lib/store.cjs');
const { Jobs } = require('../lib/jobs.cjs');
const record = require('../lib/record.cjs');
const { revalidate } = require('../lib/revalidate.cjs');
const local = require('../lib/adapters/local.cjs');
const { HotAisle } = require('../lib/adapters/hotaisle.cjs');
const { createServer, publish } = require('../lib/server.cjs');

const HELP = `workload — connected qualification for a vLLM workload on Hot Aisle

  quote <catalogue-offer-id> [--as-of YYYY-MM-DD]        dated allocation price, no execution
  inspect [--adapter hotaisle|local] [--team handle]   read the authorized environment
  plan <plan.json | --demo> [--json]                    validate and freeze a plan (runs nothing)
  approve <job> [--by name]                             bind approval to the plan hash
  start <job>                                           run or resume; prints progress
  status <job>                                          state, trials, limits, log
  cancel <job>                                          stop the owned benchmark, keep trials
  result <job|record>                                   qualified record summary + verification
  records                                               list qualified records
  verify <record>                                       recompute derived conclusions from evidence
  revalidate <record> --price 3.39 | --concurrency 64,128 | --runtime k=v | --gate-ttft 500 | --evaluator
  publish <record>                                      write headline.json, evidence.json, report.html
  serve [--port 8787] [--demo]                          localhost service + page (connected mode)
  mcp                                                   MCP server on stdio
  demo [--fast]                                         the whole journey in the local environment

State lives in $WORKLOAD_HOME (default ~/.workload-report). No dependencies.`;

const args = process.argv.slice(2);
const cmd = args[0];
const flag = (name, dflt) => { const i = args.indexOf('--' + name); return i >= 0 ? (args[i + 1] && !args[i + 1].startsWith('--') ? args[i + 1] : true) : dflt; };
const out = v => process.stdout.write((typeof v === 'string' ? v : JSON.stringify(v, null, 2)) + '\n');

async function main() {
  const store = new Store();
  const jobs = new Jobs(store);
  switch (cmd) {
    case 'quote': return out(require('../lib/catalog.cjs').quote(args[1],flag('as-of',undefined)));
    case 'inspect': {
      if (flag('adapter', 'hotaisle') === 'local') { const api = await local.startFakeApi(); try { out(await new HotAisle({ token: api.token, baseUrl: api.baseUrl }).inspect({ team: 'demo-team' })); } finally { await api.close(); } }
      else out(await new HotAisle().inspect({ team: flag('team') }));
      return;
    }
    case 'plan': {
      const input = flag('demo') ? local.demoPlanInput({ repeats: Number(flag('repeats', 2)) }) : JSON.parse(fs.readFileSync(args[1], 'utf8'));
      const job = jobs.plan(input);
      if (flag('json')) return out(job);
      out('job ' + job.id + '\nplan sha256 ' + job.plan.sha256 + '\ncells ' + job.plan.cells.length + ' (concurrency ' + job.plan.concurrency.join(', ') + ' × ' + job.plan.repeats + ')\nfirst command:\n  ' + job.plan.commands[0] + '\nestimate ' + JSON.stringify(job.plan.estimate) + '\nlimits ' + JSON.stringify(job.plan.limits) + '\n\nApprove with: workload approve ' + job.id);
      return;
    }
    case 'approve': return out(jobs.approve(args[1], { by: flag('by', process.env.USER || process.env.USERNAME || 'operator'), plan_sha256: flag('plan') }));
    case 'start': {
      jobs.on('trial', t => out('  trial ' + (t.index + 1) + ' ' + t.status + ' (c' + t.cell.concurrency + ' r' + t.cell.repeat + ')'));
      const done = await jobs.start(args[1]);
      out(done);
      if (done.record_id) out(record.summary(store.read('records', done.record_id)));
      return;
    }
    case 'status': { const j = jobs.get(args[1]); return out({ ...jobs.summary(j), limits: j.plan.limits, trials: j.trials.map(t => ({ cell: t.cell, status: t.status, error: t.error })), log: j.log.slice(-10) }); }
    case 'cancel': return out(jobs.cancel(args[1]));
    case 'result': {
      const id = args[1].startsWith('job-') ? jobs.get(args[1]).record_id : args[1];
      const rec = store.read('records', id); if (!rec) throw new Error('No record ' + id + '.');
      if (flag('json')) return out(rec);
      out(record.summary(rec)); out(record.verify(rec)); return;
    }
    case 'records': return out(store.list('records').map(id => { const r = store.read('records', id); return { id, created: r.created, synthetic: r.synthetic, qualified: r.disposition.qualified, model: r.declared.plan.workload.model }; }));
    case 'verify': return out(record.verify(store.read('records', args[1])));
    case 'revalidate': {
      const rec = store.read('records', args[1]); if (!rec) throw new Error('No record.');
      const change = {};
      if (flag('price')) change.price = { rate: Number(flag('price')) };
      if (flag('gpus')) change.price = { ...(change.price || {}), gpus: Number(flag('gpus')) };
      if (flag('concurrency')) change.traffic = { concurrency: String(flag('concurrency')).split(',').map(Number) };
      if (flag('input-len')) change.traffic = { ...(change.traffic || {}), input_len: Number(flag('input-len')) };
      if (flag('runtime')) { const [k, v] = String(flag('runtime')).split('='); change.runtime = { [k]: v }; }
      if (flag('gate-ttft')) change.gates = { ttft: Number(flag('gate-ttft')) };
      if (flag('gate-e2e')) change.gates = { ...(change.gates || {}), e2e: Number(flag('gate-e2e')) };
      if (flag('max-p95-ttft')) change.requirements = { max_p95_ttft_ms: Number(flag('max-p95-ttft')) };
      if (flag('evaluator')) change.evaluator = { criterion_id: 'corrected' };
      const r = revalidate(rec, change);
      if (flag('json')) return out(r);
      out('record ' + rec.id + '\nchange ' + JSON.stringify(change));
      for (const x of r.conclusions) out('  ' + x.status.toUpperCase().padEnd(22) + x.subject.padEnd(14) + x.detail);
      if (r.scenario) out('scenario: ' + JSON.stringify(r.scenario.cells.map(c => ({ c: c.concurrency, per1000: c.cost_per_1000, meets: c.meets }))) + ' qualified=' + r.scenario.qualified);
      if (r.minimal_plan) out('minimal plan: concurrency ' + r.minimal_plan.concurrency.join(', ') + ' × ' + r.minimal_plan.repeats + ' — ' + r.minimal_plan.note);
      out('summary ' + JSON.stringify(r.summary));
      return;
    }
    case 'publish': return out(publish(store, store.read('records', args[1])));
    case 'serve': {
      const fakeApi = flag('demo') ? await local.startFakeApi() : null;
      const server = createServer({ store, jobs, fakeApi });
      const url = await server.listenOn(Number(flag('port', 8787)));
      out('workload runner listening at ' + url + (fakeApi ? ' (demo environment attached)' : '') + '\nopen ' + url + '/ for the connected page; Ctrl-C to stop');
      await new Promise(() => {});
      return;
    }
    case 'mcp': { require('../lib/mcp.cjs').serve({ store, jobs }); await new Promise(() => {}); return; }
    case 'demo': return demo(store, jobs, !!flag('fast'));
    case 'engine': return out(engine.identity());
    default: out(HELP); if (cmd && cmd !== 'help') process.exitCode = 2;
  }
}

/* One continuous journey in the local environment: inspect, plan, approve, run, cancel
   and resume, verify, revalidate three ways, publish. Everything it produces is
   synthetic and says so. */
async function demo(store, jobs, fast) {
  const step = s => out('\n== ' + s);
  const api = await local.startFakeApi();
  try {
    step('inspect environment (fake Hot Aisle API)');
    const env = await new HotAisle({ token: api.token, baseUrl: api.baseUrl }).inspect({ team: 'demo-team' });
    out(env.allocations.map(a => a.name + ' · ' + a.gpus.count + '× ' + a.gpus.model + ' · ' + a.state + ' · $' + (a.price ? a.price.gpu_hour_usd : '?') + '/GPU-hr (retrieved)').join('\n') + '\nbalance $' + env.balance.available_usd + ' · burn $' + env.balance.hourly_usd + '/h');
    step('prepare plan');
    const input = local.demoPlanInput({ repeats: 2, target: { env: { FAKE_VLLM_DELAY_MS: fast ? '0' : '600' } } });
    input.price = { ...input.price, rate: env.allocations[0].price.gpu_hour_usd, source: 'retrieved from API ' + env.retrieved_at };
    let job = jobs.plan(input);
    out('job ' + job.id + '\nplan ' + job.plan.sha256 + '\nfirst command:\n  ' + job.plan.commands[0] + '\nestimate ' + JSON.stringify(job.plan.estimate));
    step('approve (binds the plan hash)');
    jobs.approve(job.id, { by: 'demo-operator', plan_sha256: job.plan.sha256 });
    step('start, then cancel after the first trial, then resume');
    jobs.on('trial', t => out('  trial ' + (t.index + 1) + '/' + job.trials.length + ' ' + t.status + ' (c' + t.cell.concurrency + ' r' + t.cell.repeat + ')'));
    const firstRun = jobs.start(job.id);
    await new Promise(r => { const h = t => { if (t.status === 'completed') { jobs.off('trial', h); r(); } }; jobs.on('trial', h); });
    jobs.cancel(job.id);
    let s = await firstRun;
    out('after cancel: ' + s.state + ' · ' + s.trials.completed + ' completed trial(s) retained · record ' + s.record_id);
    step('a new runner instance recovers the same job and resumes only the missing trials');
    const jobs2 = new Jobs(store);
    const j2 = jobs2.get(job.id);
    j2.state = 'interrupted'; j2.approval = j2.approval; jobs2.save(j2);
    jobs2.on('trial', t => out('  trial ' + (t.index + 1) + ' ' + t.status));
    s = await jobs2.start(job.id);
    out('after resume: ' + s.state + ' · ' + s.trials.completed + '/' + s.trials.total + ' · record ' + s.record_id);
    const rec = store.read('records', s.record_id);
    step('qualified record');
    out(record.summary(rec));
    out('verify: ' + JSON.stringify(record.verify(rec)));
    step('revalidate: price change (no GPU time)');
    show(revalidate(rec, { price: { rate: 3.39 } }));
    step('revalidate: traffic adds concurrency 64 (only the new cell needs measurement)');
    show(revalidate(rec, { traffic: { concurrency: [1, 8, 32, 64] } }));
    step('revalidate: runtime digest changed (record superseded; candidate plan)');
    show(revalidate(rec, { runtime: { runtime_digest: 'rocm/vllm@sha256:next' } }));
    step('publish (explicit; synthetic status preserved)');
    out(publish(store, rec));
  } finally { await api.close(); }
  function show(r) { for (const x of r.conclusions) out('  ' + x.status.toUpperCase().padEnd(22) + x.subject.padEnd(14) + x.detail); if (r.minimal_plan) out('  minimal plan → concurrency ' + r.minimal_plan.concurrency.join(', ') + ' × ' + r.minimal_plan.repeats); if (r.scenario) out('  scenario → ' + r.scenario.cells.map(c => 'c' + c.concurrency + ' $' + (c.cost_per_1000 === null ? '—' : c.cost_per_1000.toFixed(4))).join(' · ')); }
}

main().catch(e => { process.stderr.write('error: ' + e.message + '\n'); process.exit(1); });
