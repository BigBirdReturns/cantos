'use strict';
/* The qualified record: one durable object that separates what was observed, what the
   operator declared, which acceptance rule applied and which economic scenario was
   priced. Every visible number (headline, report, agent summary, evidence packet) is
   a projection computed from it through the page's engine. Nothing is typed twice. */
const engine = require('./engine.cjs');

function cells(job) {
  const HA = engine.load();
  const plan = job.plan;
  const byConcurrency = new Map();
  for (const t of job.trials) if (t.status === 'completed') { if (!byConcurrency.has(t.cell.concurrency)) byConcurrency.set(t.cell.concurrency, []); byConcurrency.get(t.cell.concurrency).push(t); }
  const out = [];
  for (const [concurrency, trials] of [...byConcurrency.entries()].sort((a, b) => a[0] - b[0])) {
    const runs = trials.map(t => HA.restoreRun(t.normalized));
    const settings = { identity: declaredIdentity(plan), ttft: plan.gates.ttft, e2e: plan.gates.e2e, queue: plan.gates.queue, quality: plan.gates.quality };
    let aggregate, cost, error = null;
    try { aggregate = HA.aggregate(runs, settings); cost = HA.costing(aggregate, plan.price); } catch (e) { error = e.message; }
    const check = aggregate ? requirements(aggregate, plan.requirements) : { meets: false, reasons: [error] };
    out.push({ concurrency, trials: trials.map(t => ({ cell: t.cell, source: t.source, normalized: t.normalized })), settings, aggregate: aggregate || null, cost: cost || null, meets: check.meets, reasons: check.reasons, error });
  }
  return out;
}

function declaredIdentity(plan) {
  const map = { model_revision: 'revision', precision: 'precision', tokenizer_revision: 'tokenizer', cache_policy: 'cache', runtime_digest: 'runtime', workload_id: 'workload' };
  const out = {};
  for (const [k, id] of Object.entries(map)) if (plan.identity[k]) out[id] = plan.identity[k];
  return out;
}

function requirements(a, req) {
  const reasons = [];
  if (a.holds.length) reasons.push(...a.holds);
  if (req.max_p95_ttft_ms !== null && req.max_p95_ttft_ms !== undefined) { const v = a.metrics.ttft.p95; if (v === null) reasons.push('p95 TTFT unavailable.'); else if (v > req.max_p95_ttft_ms) reasons.push('p95 TTFT ' + v.toFixed(0) + ' ms exceeds ' + req.max_p95_ttft_ms + ' ms.'); }
  if (req.max_p95_e2e_ms !== null && req.max_p95_e2e_ms !== undefined) { const v = a.metrics.e2e.p95; if (v === null) reasons.push('p95 E2E unavailable.'); else if (v > req.max_p95_e2e_ms) reasons.push('p95 E2E ' + v.toFixed(0) + ' ms exceeds ' + req.max_p95_e2e_ms + ' ms.'); }
  if (req.min_accepted_per_s !== null && req.min_accepted_per_s !== undefined) { if (a.rate === null) reasons.push('Accepted rate unavailable.'); else if (a.rate < req.min_accepted_per_s) reasons.push('Accepted rate ' + a.rate.toFixed(3) + '/s below ' + req.min_accepted_per_s + '/s.'); }
  if (req.max_failure_rate !== null && req.max_failure_rate !== undefined) { if (a.failureRate === null) reasons.push('Failure rate unavailable.'); else if (a.failureRate > req.max_failure_rate) reasons.push('Failure rate ' + (a.failureRate * 100).toFixed(1) + '% exceeds ' + (req.max_failure_rate * 100) + '%.'); }
  return { meets: !reasons.length, reasons };
}

function derive(rec) {
  const HA = engine.load();
  const job = { plan: rec.declared.plan, trials: rec.observed.trials.map(t => ({ status: 'completed', cell: t.cell, source: t.source, normalized: t.normalized })) };
  const cs = cells(job);
  const primary = pickPrimary(cs, rec.declared.plan.primary_concurrency);
  let comparison = null;
  if (rec.declared.comparator && primary && primary.cost) {
    const pc = rec.declared.comparator;
    comparison = { kind: 'price_threshold', provider: pc.provider, allocation_hour_usd: pc.gpus * pc.rate + (pc.extra || 0), required_rate_to_tie: primary.aggregate.rate !== null && primary.cost.hourly > 0 ? HA.threshold(primary.aggregate.rate, primary.cost.hourly, pc.gpus * pc.rate + (pc.extra || 0)) : null, note: 'Price ratio only. The comparator has no measured evidence in this record.' };
  }
  const qualified = !!(primary && primary.meets && primary.aggregate && !primary.aggregate.holds.length);
  const reasons = primary ? (primary.meets ? ['Primary cell (concurrency ' + primary.concurrency + ') meets every stated requirement.'] : primary.reasons) : ['No completed cell.'];
  return {
    cells: cs.map(c => ({ concurrency: c.concurrency, runs: c.trials.length, aggregate: c.aggregate, cost: c.cost, meets: c.meets, reasons: c.reasons, error: c.error })),
    primary_concurrency: primary ? primary.concurrency : null,
    comparison,
    disposition: { qualified, reasons, cells_meeting: cs.filter(c => c.meets).map(c => c.concurrency) },
    engine: (({ version, engine_sha256 }) => ({ version, engine_sha256 }))(engine.identity()),
  };
}

function pickPrimary(cs, wanted) {
  if (!cs.length) return null;
  if (wanted !== null && wanted !== undefined) return cs.find(c => c.concurrency === wanted) || null;
  const meeting = cs.filter(c => c.meets && c.cost && c.cost.costPer1000 !== null);
  if (meeting.length) return meeting.reduce((best, c) => c.cost.costPer1000 < best.cost.costPer1000 ? c : best);
  return cs[cs.length - 1];
}

function build(job) {
  const HA = engine.load();
  const rec = {
    schema: 'hot-aisle/qualified-record@1',
    id: job.id.replace(/^job-/, 'rec-'),
    created: new Date().toISOString(),
    job_id: job.id,
    synthetic: job.plan.target.adapter === 'local' || job.trials.some(t => t.normalized && t.normalized.synthetic),
    observed: { trials: job.trials.filter(t => t.status === 'completed').map(t => ({ cell: t.cell, source: t.source, normalized: t.normalized, started: t.started, ended: t.ended })), failed_trials: job.trials.filter(t => t.status === 'failed').map(t => ({ cell: t.cell, error: t.error })), disposition: job.disposition },
    declared: { plan: job.plan, identity: job.plan.identity, price: job.plan.price, comparator: job.plan.comparator, approval: job.approval },
    rule: { gates: job.plan.gates, requirements: job.plan.requirements },
    scenario: { allocation: { label: job.plan.target.allocation_label || (job.plan.price.gpus + '× ' + (job.plan.target.gpu_model || 'GPU')), gpus: job.plan.price.gpus, gpu_model: job.plan.target.gpu_model || null, adapter: job.plan.target.adapter, deployment_id: job.plan.target.deployment_id || null } },
  };
  rec.derived = derive(rec);
  rec.disposition = rec.derived.disposition;
  rec.sha256 = engine.sha256(HA.canonical(withoutSha(rec)));
  return rec;
}

function withoutSha(rec) { const { sha256, ...rest } = rec; return rest; }

/* Recomputes the derived section from observed + declared + rule and compares it to
   the stored one. Mirrors the engine's own recompute discipline: a record whose stored
   conclusions do not follow from its evidence is not verified. */
function verify(rec) {
  const HA = engine.load();
  const problems = [];
  if (rec.schema !== 'hot-aisle/qualified-record@1') problems.push('Unsupported record schema.');
  if (engine.sha256(HA.canonical(withoutSha(rec))) !== rec.sha256) problems.push('Record checksum mismatch.');
  const {sha256:planSha,commands,...planBody}=rec.declared.plan;
  if(engine.sha256(HA.canonical(planBody))!==planSha)problems.push('Plan body does not match its identity.');
  const fresh = derive(rec);
  const strip = d => ({ ...d, engine: undefined });
  if (HA.canonical(strip(fresh)) !== HA.canonical(strip(rec.derived))) problems.push('Derived conclusions do not follow from the retained evidence.');
  if (rec.synthetic !== (rec.declared.plan.target.adapter === 'local' || rec.observed.trials.some(t => t.normalized.synthetic))) problems.push('Synthetic status mismatch.');
  if (HA.canonical(rec.disposition) !== HA.canonical(rec.derived.disposition)) problems.push('Top-level disposition differs from the derived verdict.');
  for (const key of ['price','identity','comparator'])
    if (HA.canonical(rec.declared[key]) !== HA.canonical(rec.declared.plan[key])) problems.push('Declared '+key+' differs from the approved plan.');
  for (const key of ['gates','requirements'])
    if (HA.canonical(rec.rule[key]) !== HA.canonical(rec.declared.plan[key])) problems.push('Rule '+key+' differs from the approved plan.');
  if (rec.declared.approval && rec.declared.approval.plan_sha256 !== rec.declared.plan.sha256) problems.push('Approval is bound to a different plan.');

  return { verified: !problems.length, problems, engine: fresh.engine };
}

/* Projections. */
function primaryCell(rec) { return rec.derived.cells.find(c => c.concurrency === rec.derived.primary_concurrency) || null; }

function packet(rec, concurrency = rec.derived.primary_concurrency) {
  const HA = engine.load();
  const cell = rec.derived.cells.find(c => c.concurrency === concurrency);
  if (!cell || !cell.aggregate) throw new Error('No aggregable cell at concurrency ' + concurrency + '.');
  const trials = rec.observed.trials.filter(t => t.cell.concurrency === concurrency);
  const settings = { identity: declaredIdentity(rec.declared.plan), ttft: rec.rule.gates.ttft, e2e: rec.rule.gates.e2e, queue: rec.rule.gates.queue, quality: rec.rule.gates.quality };
  const side = { id: 'a', label: rec.declared.price.provider, settings, price: rec.declared.price, normalized: trials.map(t => t.normalized), aggregate: cell.aggregate, cost: cell.cost };
  const p = { schema: 'hot-aisle/workload-report@2', version: HA.VERSION, generated_at: rec.created, title: cell.aggregate.identity.model || 'Workload cost report', synthetic: !!cell.aggregate.synthetic, sides: [side], comparison: null };
  return { schema: 'hot-aisle/sealed-report@1', sha256: engine.sha256(HA.canonical(p)), payload: p };
}

function receipt(rec, concurrency) {
  const HA = engine.load();
  const env = packet(rec, concurrency);
  return HA.receiptHTML(env.payload).replace('</footer>', '<p class="hash">Evidence JSON payload SHA-256: ' + env.sha256 + '</p><p class="hash">Qualified record ' + HA.escape(rec.id) + ' · ' + rec.sha256 + '</p></footer>');
}

function headline(rec, { evidence_url = null, report_url = null, published_on = null } = {}) {
  const cell = primaryCell(rec);
  const a = cell && cell.aggregate, c = cell && cell.cost;
  const plan = rec.declared.plan;
  const side = { label: rec.declared.price.provider, allocation: rec.scenario.allocation.label, rate: '$' + rec.declared.price.rate.toFixed(2) + ' / GPU-hr', cost_per_1000: c ? c.costPer1000 : null, p95_ttft_ms: a ? a.metrics.ttft.p95 : null, p95_e2e_ms: a ? a.metrics.e2e.p95 : null, runs: a ? a.runs : 0, accepted_per_s: a ? a.rate : null, unit: a ? a.unit : null };
  const comp = rec.declared.comparator ? { label: rec.declared.comparator.provider, allocation: rec.declared.comparator.gpus + '× ' + rec.declared.comparator.provider.replace(/^Nebius /, ''), rate: '$' + rec.declared.comparator.rate.toFixed(2) + ' / GPU-hr', cost_per_1000: null, p95_ttft_ms: null, p95_e2e_ms: null, runs: 0, price_only: true, required_rate_to_tie: rec.derived.comparison ? rec.derived.comparison.required_rate_to_tie : null } : null;
  return {
    schema: 'hot-aisle/headline@2', status: rec.synthetic ? 'demonstration' : 'published', record_id: rec.id, record_sha256: rec.sha256, generated: true,
    unit: a ? a.unit : 'accepted requests',
    workload: plan.workload.model + ' · ' + plan.workload.input_len.toLocaleString('en-US') + ' in / ' + plan.workload.output_len + ' out · concurrency ' + plan.concurrency.join(', '),
    primary_concurrency: rec.derived.primary_concurrency,
    qualified: rec.disposition.qualified, reasons: rec.disposition.reasons,
    sides: comp ? [side, comp] : [side],
    saving: null,
    published_on, evidence_url, report_url,
  };
}

function summary(rec) {
  const h = headline(rec);
  const s = h.sides[0];
  const lines = [(rec.synthetic ? 'DEMONSTRATION (synthetic) — ' : '') + 'Qualified record ' + rec.id + ': ' + (rec.disposition.qualified ? 'QUALIFIED' : 'NOT QUALIFIED')];
  lines.push(h.workload);
  lines.push(s.label + ' · ' + s.allocation + ' · ' + s.rate + ': ' + (s.cost_per_1000 === null ? 'no finite cost' : '$' + s.cost_per_1000.toFixed(s.cost_per_1000 < 1 ? 4 : 2)) + ' per 1,000 ' + h.unit + ' at concurrency ' + h.primary_concurrency + '; p95 TTFT ' + fmt(s.p95_ttft_ms) + ' ms; p95 E2E ' + fmt(s.p95_e2e_ms) + ' ms; ' + s.runs + ' trial(s).');
  for (const c of rec.derived.cells) lines.push('  concurrency ' + c.concurrency + ': ' + (c.meets ? 'meets requirements' : 'does not meet: ' + c.reasons.join(' ')) + (c.cost && c.cost.costPer1000 !== null ? ' · $' + c.cost.costPer1000.toFixed(4) + '/1,000' : ''));
  if (h.sides[1]) lines.push(h.sides[1].label + ' at ' + h.sides[1].rate + ' would need ' + fmt(h.sides[1].required_rate_to_tie, 3) + ' ' + h.unit + '/s to tie on rental cost (price ratio, not a measurement).');
  lines.push('Reasons: ' + rec.disposition.reasons.join(' '));
  return lines.join('\n');
}

function fmt(v, d = 0) { return v === null || v === undefined ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d }); }

module.exports = { build, verify, derive, packet, receipt, headline, summary, primaryCell, requirements, declaredIdentity };
