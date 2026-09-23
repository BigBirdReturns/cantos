'use strict';
/* Evaluation lifecycle: planned → approved → running → completed | cancelled | failed,
   with interrupted as the recovery state when the owning process died mid-run.
   Plans are immutable once approved (approval binds the plan's SHA-256). Trials are
   the unit of retention: a cancel, a limit or a crash keeps every completed trial. */
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { EventEmitter } = require('node:events');
const engine = require('./engine.cjs');
const { Store } = require('./store.cjs');
const vllm = require('./vllm.cjs');
const record = require('./record.cjs');

const STATES = ['planned', 'approved', 'running', 'completed', 'cancelled', 'failed', 'interrupted'];

function alive(pid) { if (!pid) return false; try { process.kill(pid, 0); return true; } catch (e) { return e.code === 'EPERM'; } }

function canonicalPlan(plan) {
  const HA = engine.load();
  const { sha256, ...rest } = plan;
  return HA.canonical(rest);
}

class Jobs extends EventEmitter {
  constructor(store = new Store()) {
    super();
    this.store = store;
    this.instance = os.hostname() + ':' + process.pid;
    this.controllers = new Map();
    this.recover();
  }

  /* Any job that claims to be running under a process that no longer exists is
     marked interrupted; its running trials become interrupted and can be re-run. */
  recover() {
    const recovered = [];
    for (const id of this.store.list('jobs')) {
      const job = this.store.read('jobs', id);
      if (job.state === 'running' && !(job.lease && job.lease.instance === this.instance) && !alive(job.lease && job.lease.pid)) {
        job.state = 'interrupted';
        for (const t of job.trials) if (t.status === 'running') { t.status = 'interrupted'; t.ended = new Date().toISOString(); }
        job.log.push(stamp('Runner process ' + (job.lease ? job.lease.instance : '?') + ' disappeared; job marked interrupted.'));
        job.lease = null;
        this.save(job);
        recovered.push(id);
      }
    }
    return recovered;
  }

  list() { return this.store.list('jobs').map(id => this.summary(this.store.read('jobs', id))).sort((a, b) => a.created < b.created ? 1 : -1); }
  get(id) { const j = this.store.read('jobs', id); if (!j) throw new Error('Unknown job ' + id + '.'); return j; }
  save(job) { job.updated = new Date().toISOString(); this.store.write('jobs', job.id, job); this.emit('job', this.summary(job)); return job; }

  summary(job) {
    const total = job.trials.length, completed = job.trials.filter(t => t.status === 'completed').length, failed = job.trials.filter(t => t.status === 'failed').length;
    return { id: job.id, state: job.state, created: job.created, updated: job.updated, target: job.plan.target.name, model: job.plan.workload.model, cells: job.plan.cells.length, trials: { total, completed, failed, pending: job.trials.filter(t => ['pending', 'interrupted'].includes(t.status)).length }, progress: job.progress, disposition: job.disposition, record_id: job.record_id, plan_sha256: job.plan.sha256, synthetic: job.plan.target.adapter === 'local' };
  }

  /* Validates and freezes a plan. Nothing is executed. */
  plan(input) {
    const HA = engine.load();
    const p = normalizePlan(input);
    p.workload_id = 'sha256:' + engine.sha256(HA.canonical(p.workload)).slice(0, 32);
    p.identity.workload_id = p.workload_id;
    p.cells = [];
    for (const c of p.concurrency) for (let r = 0; r < p.repeats; r++) p.cells.push({ concurrency: c, repeat: r });
    p.commands = p.cells.slice(0, 1).map(cell => vllm.commandString(p.target.vllm_command || ['vllm', 'bench', 'serve'], vllm.buildArgs({ ...p, sha256: 'pending' }, cell, '<result-dir>', 'cell-c' + cell.concurrency + '-r' + cell.repeat + '.json')));
    p.estimate = estimate(p);
    p.sha256 = engine.sha256(canonicalPlan(p));
    p.commands = p.cells.slice(0, 1).map(cell => vllm.commandString(p.target.vllm_command || ['vllm', 'bench', 'serve'], vllm.buildArgs(p, cell, '<result-dir>', 'cell-c' + cell.concurrency + '-r' + cell.repeat + '.json')));
    const job = { schema: 'hot-aisle/evaluation-job@1', id: this.store.newId('job'), created: new Date().toISOString(), updated: null, state: 'planned', plan: p, approval: null, lease: null, trials: p.cells.map(cell => ({ cell, status: 'pending', started: null, ended: null, source: null, error: null, preview: null })), progress: { completed: 0, total: p.cells.length, elapsed_s: 0, measured_s: 0, spend_usd: 0 }, cancel_requested: false, disposition: null, record_id: null, log: [stamp('Plan created; awaiting approval.')] };
    return this.save(job);
  }

  approve(id, { by = 'operator', plan_sha256 } = {}) {
    const job = this.get(id);
    if (job.state !== 'planned') throw new Error('Job ' + id + ' is ' + job.state + ', not awaiting approval.');
    if (plan_sha256 && plan_sha256 !== job.plan.sha256) throw new Error('Approval names a different plan (' + plan_sha256.slice(0, 12) + ' ≠ ' + job.plan.sha256.slice(0, 12) + ').');
    job.approval = { by, at: new Date().toISOString(), plan_sha256: job.plan.sha256 };
    job.state = 'approved';
    job.log.push(stamp('Approved by ' + by + ' for plan ' + job.plan.sha256.slice(0, 12) + '.'));
    return this.save(job);
  }

  /* Idempotent: starting a running job returns it; starting an interrupted job resumes
     only trials that never completed. The promise resolves when the run ends. */
  async start(id) {
    let job = this.get(id);
    if (job.state === 'running') { if (job.lease && (job.lease.instance === this.instance || alive(job.lease.pid))) return this.summary(job); job.state = 'interrupted'; }
    if (!['approved', 'interrupted'].includes(job.state)) throw new Error('Job ' + id + ' is ' + job.state + '; only approved or interrupted jobs can start.');
    if (!job.approval || job.approval.plan_sha256 !== job.plan.sha256) throw new Error('Plan changed since approval.');
    const resumed = job.state === 'interrupted';
    job.state = 'running';
    job.lease = { instance: this.instance, pid: process.pid, since: new Date().toISOString() };
    job.cancel_requested = false;
    job.log.push(stamp(resumed ? 'Resumed; completed trials retained.' : 'Started.'));
    this.save(job);
    const controller = new AbortController();
    this.controllers.set(id, controller);
    const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'workload-' + id + '-'));
    const started = Date.now();
    const hourly = job.plan.price.gpus * job.plan.price.rate + (job.plan.price.extra || 0);
    try {
      for (let i = 0; i < job.trials.length; i++) {
        job = this.get(id);
        const trial = job.trials[i];
        if (trial.status === 'completed') continue;
        if (job.cancel_requested) break;
        const limit = checkLimits(job, started, hourly);
        if (limit) { job.disposition = { outcome: 'limit_reached', reason: limit }; job.log.push(stamp('Stopped before trial ' + (i + 1) + ': ' + limit)); this.save(job); break; }
        trial.status = 'running'; trial.started = new Date().toISOString(); trial.error = null;
        job.log.push(stamp('Trial ' + (i + 1) + '/' + job.trials.length + ' started (concurrency ' + trial.cell.concurrency + ', repeat ' + trial.cell.repeat + ').'));
        this.save(job);
        this.emit('trial', { job: id, index: i, status: 'running', cell: trial.cell });
        try {
          const out = await vllm.execute({ target: job.plan.target, plan: job.plan, cell: trial.cell, workDir, signal: controller.signal, onLine: l => this.emit('line', { job: id, index: i, line: l.slice(0, 300) }) });
          const admitted = admit(out.bytes, this.store, job.plan);
          job = this.get(id);
          Object.assign(job.trials[i], { status: 'completed', ended: new Date().toISOString(), source: admitted.source, preview: out.preview, normalized: admitted.normalized, measured_s: admitted.normalized.duration });
          job.log.push(stamp('Trial ' + (i + 1) + ' completed: ' + admitted.normalized.completed + '/' + admitted.normalized.attempted + ' in ' + admitted.normalized.duration.toFixed(1) + ' s; sha256 ' + admitted.source.sha256.slice(0, 12) + '.'));
        } catch (e) {
          job = this.get(id);
          if (e.cancelled) { job.trials[i].status = 'pending'; job.trials[i].started = null; job.log.push(stamp('Trial ' + (i + 1) + ' cancelled before completion; not retained.')); this.save(job); break; }
          Object.assign(job.trials[i], { status: 'failed', ended: new Date().toISOString(), error: e.message, preview: e.preview || null });
          job.log.push(stamp('Trial ' + (i + 1) + ' failed: ' + e.message));
        }
        job.progress = progress(job, started, hourly);
        this.save(job);
        this.emit('trial', { job: id, index: i, status: job.trials[i].status, cell: trial.cell });
      }
    } finally {
      this.controllers.delete(id);
      try { fs.rmSync(workDir, { recursive: true, force: true }); } catch (e) { /* temp dir */ }
    }
    job = this.get(id);
    job.progress = progress(job, started, hourly);
    job.lease = null;
    const completed = job.trials.filter(t => t.status === 'completed').length, failed = job.trials.filter(t => t.status === 'failed').length;
    if (job.cancel_requested) { job.state = 'cancelled'; job.disposition = { outcome: 'cancelled', reason: 'Cancelled by operator; ' + completed + ' completed trial(s) retained.' }; }
    else if (!completed) { job.state = 'failed'; job.disposition = { outcome: 'failed', reason: failed + ' trial(s) failed; no admissible evidence.' }; }
    else { job.state = 'completed'; if (!job.disposition) job.disposition = { outcome: failed ? 'partial' : 'complete', reason: failed ? failed + ' trial(s) failed; record built from ' + completed + ' completed trial(s).' : 'All ' + completed + ' trials completed.' }; }
    if (completed) {
      const rec = record.build(job);
      this.store.write('records', rec.id, rec);
      job.record_id = rec.id;
      job.log.push(stamp('Qualified record ' + rec.id + ' written (' + (rec.disposition.qualified ? 'QUALIFIED' : 'NOT QUALIFIED') + ').'));
    }
    job.log.push(stamp('Ended: ' + job.state + '.'));
    this.save(job);
    return this.summary(job);
  }

  cancel(id) {
    const job = this.get(id);
    if (!['running', 'approved', 'interrupted', 'planned'].includes(job.state)) throw new Error('Job ' + id + ' is ' + job.state + '; nothing to cancel.');
    job.cancel_requested = true;
    if (job.state !== 'running') { job.state = 'cancelled'; job.disposition = { outcome: 'cancelled', reason: 'Cancelled before it ran.' }; }
    job.log.push(stamp('Cancellation requested.'));
    this.save(job);
    const c = this.controllers.get(id);
    if (c) c.abort();
    return this.summary(job);
  }
}

function stamp(text) { return { at: new Date().toISOString(), text }; }

function progress(job, started, hourly) {
  const measured = job.trials.filter(t => t.status === 'completed').reduce((s, t) => s + (t.measured_s || 0), 0);
  const elapsed = (Date.now() - started) / 1000 + (job.progress.elapsed_s_prior || 0);
  return { completed: job.trials.filter(t => t.status === 'completed').length, total: job.trials.length, elapsed_s: +elapsed.toFixed(1), measured_s: +measured.toFixed(1), spend_usd: +(hourly * elapsed / 3600).toFixed(4), hourly_usd: hourly };
}

function checkLimits(job, started, hourly) {
  const l = job.plan.limits;
  const elapsedMin = (Date.now() - started) / 60000;
  if (l.max_minutes && elapsedMin > l.max_minutes) return 'Time limit of ' + l.max_minutes + ' min reached.';
  const spend = hourly * (Date.now() - started) / 3600000;
  if (l.max_spend_usd && spend > l.max_spend_usd) return 'Spend limit of $' + l.max_spend_usd + ' reached (modeled $' + spend.toFixed(2) + ').';
  return null;
}

/* Evidence admission: the exact bytes are hashed and retained, then parsed and
   normalized by the engine. Anything the engine refuses is a failed trial, never a
   silently repaired one. */
function admit(bytes, store, plan) {
  const HA = engine.load();
  const saved = store.saveEvidence(bytes);
  let docs;
  try { docs = HA.parseDocuments(new TextDecoder('utf-8', { fatal: true }).decode(bytes)); } catch (e) { throw new Error('Evidence rejected: ' + e.message); }
  if (docs.length !== 1) throw new Error('Evidence rejected: expected one result object, found ' + docs.length + '.');
  const source = { sha256: saved.sha256, record_index: 0, bytes: saved.bytes };
  let normalized;
  try { normalized = HA.normalize(docs[0], source); } catch (e) { throw new Error('Evidence rejected: ' + e.message); }
  if (plan.target.adapter !== 'local' && normalized.synthetic) throw new Error('Evidence rejected: a synthetic marker appeared in a non-local run.');
  if (plan.target.adapter === 'local' && !normalized.synthetic) throw new Error('Evidence rejected: local environment output must be marked synthetic.');
  return { source, normalized };
}

function normalizePlan(input) {
  if (!input || typeof input !== 'object') throw new Error('Plan input must be an object.');
  const t = input.target || {};
  if (!t.adapter || !['hotaisle', 'local'].includes(t.adapter)) throw new Error('target.adapter must be hotaisle or local.');
  if (!['local', 'ssh'].includes(t.exec)) throw new Error('target.exec must be local or ssh.');
  if (t.exec === 'ssh' && !t.host) throw new Error('target.host is required for ssh execution.');
  /* The local adapter is the integration environment: it always drives the fake benchmark. */
  if (t.adapter === 'local' && !t.vllm_command) t.vllm_command = [process.execPath, path.join(__dirname, '..', 'fixtures', 'fake-vllm.cjs')];
  if (t.adapter === 'hotaisle' && t.vllm_command && /fake-vllm/.test(t.vllm_command.join(' '))) throw new Error('A Hot Aisle target cannot use the fake benchmark.');
  const w = { backend: 'openai', dataset: 'random', request_rate: 'inf', seed: 1, ...(input.workload || {}) };
  for (const k of ['model', 'base_url']) if (!w[k]) throw new Error('workload.' + k + ' is required.');
  for (const k of ['input_len', 'output_len', 'num_prompts']) if (!Number.isSafeInteger(w[k]) || w[k] < 1) throw new Error('workload.' + k + ' must be a positive integer.');
  const concurrency = [...new Set((input.concurrency || [1]).map(Number))].sort((a, b) => a - b);
  if (!concurrency.length || concurrency.some(c => !Number.isSafeInteger(c) || c < 1)) throw new Error('concurrency must be positive integers.');
  const repeats = input.repeats ?? 3;
  if (!Number.isSafeInteger(repeats) || repeats < 1 || repeats > 10) throw new Error('repeats must be 1–10.');
  const price = { provider: 'Hot Aisle', extra: 0, ...(input.price || {}) };
  if (!Number.isSafeInteger(price.gpus) || price.gpus < 1) throw new Error('price.gpus must be a positive integer.');
  if (!Number.isFinite(price.rate) || price.rate < 0) throw new Error('price.rate must be a nonnegative number.');
  const comparator = input.comparator ? { extra: 0, ...input.comparator } : null;
  const limits = { max_minutes: 60, max_spend_usd: null, ...(input.limits || {}) };
  const gates = { ttft: input.gates?.ttft ?? null, e2e: input.gates?.e2e ?? null, queue: input.gates?.queue === true, quality: input.gates?.quality === true };
  const requirements = { max_p95_ttft_ms: null, max_p95_e2e_ms: null, min_accepted_per_s: null, max_failure_rate: null, ...(input.requirements || {}) };
  const identity = { model_revision: '', precision: '', tokenizer_revision: '', cache_policy: '', runtime_digest: '', ...(input.identity || {}) };
  const primary = input.primary_concurrency ?? null;
  if (primary !== null && !concurrency.includes(primary)) throw new Error('primary_concurrency must be one of the planned concurrencies.');
  return { schema: 'hot-aisle/evaluation-plan@1', target: { ...t, vllm_command: t.vllm_command || undefined }, workload: w, concurrency, repeats, identity, price, comparator, limits, gates, requirements, primary_concurrency: primary, created: new Date().toISOString() };
}

function estimate(p) {
  const hourly = p.price.gpus * p.price.rate + (p.price.extra || 0);
  const perTrialS = p.workload.num_prompts * (p.workload.output_len * 0.02 + 0.3) / Math.max(1, Math.min(p.workload.num_prompts, 8)) + 20;
  const seconds = p.cells.length * perTrialS;
  return { cells: p.cells.length, rough_seconds: Math.round(seconds), rough_spend_usd: +(hourly * seconds / 3600).toFixed(2), hourly_usd: hourly, basis: 'Coarse planning estimate (decode ~20 ms/token, ~20 s overhead per trial). The limits, not this estimate, bound the run.' };
}

module.exports = { Jobs, STATES, normalizePlan, canonicalPlan };
