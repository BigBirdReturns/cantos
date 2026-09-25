'use strict';
/* Selective revalidation. Given a qualified record and a change, decide which
   conclusions still stand, which can be recomputed from retained evidence with no
   GPU time, which require new measurement, and the smallest plan that restores
   confidence. The dependency model is explicit so the answer is inspectable. */
const engine = require('./engine.cjs');
const record = require('./record.cjs');

const RUNTIME_KEYS = ['model_revision', 'precision', 'tokenizer_revision', 'runtime_digest', 'cache_policy'];
const WORKLOAD_KEYS = ['model', 'dataset', 'input_len', 'output_len', 'num_prompts', 'request_rate', 'backend'];

function revalidate(rec, change) {
  if (!change || typeof change !== 'object' || Array.isArray(change)) throw new Error('change must be an object.');
  const supported = ['price', 'gates', 'requirements', 'traffic', 'runtime', 'evaluator'];
  const unsupported = Object.keys(change).filter(key => !supported.includes(key));
  if (unsupported.length) throw new Error('Unsupported change field(s): ' + unsupported.join(', ') + '.');
  const verified=record.verify(rec);if(!verified.verified)throw Error('Revalidation requires a verified record: '+verified.problems.join(' '));
  if(change?.price?.gpus!==undefined&&change.price.gpus!==rec.declared.plan.price.gpus)throw Error('A different GPU allocation requires new performance qualification; change only its price here.');
  const kinds = Object.keys(change).filter(k => change[k] !== undefined && change[k] !== null);
  if (!kinds.length) throw new Error('Nothing changed.');
  const plan = rec.declared.plan;
  const conclusions = [];
  let candidate = null, scenario = null, requiredCells = new Set(), reevaluate = false;

  /* Economics depend only on price inputs and retained aggregates. */
  if (change.price) {
    const price = { ...plan.price, ...change.price };
    scenario = priceScenario(rec, price);
    conclusions.push(c('economics', 'recomputed', 'Cost per 1,000 recomputed from retained trials at ' + price.gpus + ' × $' + price.rate + ' + $' + (price.extra || 0) + '/h. No GPU time.'));
    conclusions.push(c('performance', 'stands', 'Throughput and latency do not depend on price.'));
  }

  /* Gates change the accepted denominator; recomputable only when request rows exist. */
  if (change.gates) {
    const rows = rec.observed.trials.every(t => t.normalized.rows);
    if (rows && !(change.gates.quality && !rec.observed.trials.every(t => t.normalized.quality))) {
      scenario = gateScenario(rec, { ...plan.gates, ...change.gates }, scenario);
      conclusions.push(c('acceptance', 'recomputed', 'Accepted counts recomputed from retained per-request samples under the new gates.'));
    } else {
      for (const cell of rec.derived.cells) requiredCells.add(cell.concurrency);
      conclusions.push(c('acceptance', 'requires_measurement', rows ? 'Evaluator-passed gating needs a sidecar for every trial; none retained.' : 'Retained trials have no per-request samples; gating needs a detailed rerun.'));
    }
  }

  /* Requirements are thresholds over existing aggregates: always recomputable. */
  if (change.requirements) {
    scenario = requirementScenario(rec, { ...plan.requirements, ...change.requirements }, scenario);
    conclusions.push(c('qualification', 'recomputed', 'Requirement thresholds re-applied to retained aggregates.'));
  }

  /* Traffic: cells already measured under identical workload stand; new cells need
     measurement; a changed request shape is a different workload identity. */
  if (change.traffic) {
    const t = change.traffic;
    const shapeChanged = WORKLOAD_KEYS.some(k => t[k] !== undefined && t[k] !== plan.workload[k]);
    const wanted = t.concurrency ? [...new Set(t.concurrency.map(Number))].sort((a, b) => a - b) : plan.concurrency;
    if (shapeChanged) {
      for (const cc of wanted) requiredCells.add(cc);
      conclusions.push(c('capacity', 'requires_measurement', 'Request shape changed (' + WORKLOAD_KEYS.filter(k => t[k] !== undefined && t[k] !== plan.workload[k]).join(', ') + '); every cell needs new evidence under the new workload identity.'));
    } else {
      const have = new Set(rec.derived.cells.map(x => x.concurrency));
      const missing = wanted.filter(x => !have.has(x)), kept = wanted.filter(x => have.has(x));
      for (const cc of missing) requiredCells.add(cc);
      if (kept.length) conclusions.push(c('capacity', 'stands', 'Cells at concurrency ' + kept.join(', ') + ' were measured under this workload and stand.'));
      if (missing.length) conclusions.push(c('capacity', 'requires_measurement', 'Concurrency ' + missing.join(', ') + ' has no evidence; ' + plan.repeats + ' trial(s) each.'));
      const dropped = [...have].filter(x => !wanted.includes(x));
      if (dropped.length) conclusions.push(c('capacity', 'stands', 'Concurrency ' + dropped.join(', ') + ' no longer requested; evidence retained.'));
    }
  }

  /* Runtime or model identity: the record is superseded; a new candidate is planned. */
  if (change.runtime) {
    const changed = RUNTIME_KEYS.filter(k => change.runtime[k] !== undefined && change.runtime[k] !== plan.identity[k]);
    if (changed.length) {
      candidate = { ...cloneInput(plan), identity: { ...plan.identity, ...pick(change.runtime, RUNTIME_KEYS) } };
      for (const cc of plan.concurrency) requiredCells.add(cc);
      conclusions.push(c('qualification', 'superseded', 'Runtime identity changed (' + changed.join(', ') + '). This record stays as history; a new candidate qualification covers all cells.'));
      conclusions.push(c('economics', 'stands', 'Price inputs are unchanged, but they will be applied to the candidate\'s new measurements.'));
    } else conclusions.push(c('qualification', 'stands', 'Declared runtime identity is unchanged.'));
  }

  /* Evaluator correction: only evaluator-gated conclusions are affected, and they need
     re-adjudication of retained requests, not new GPU time. */
  if (change.evaluator) {
    if (plan.gates.quality) { reevaluate = true; conclusions.push(c('acceptance', 'requires_reevaluation', 'Acceptance counted evaluator-passed outcomes. Re-run the corrected evaluator over the retained request set and attach new sidecars; no benchmark rerun.')); }
    else conclusions.push(c('acceptance', 'stands', 'Acceptance did not depend on an evaluator.'));
  }

  const required = [...requiredCells].sort((a, b) => a - b);
  let minimal = null;
  if (required.length) {
    const base = candidate || cloneInput(plan);
    if (change.traffic) base.workload = { ...base.workload, ...pick(change.traffic, WORKLOAD_KEYS) };
    minimal = { ...base, concurrency: required, note: (required.length === plan.concurrency.length && !change.traffic ? 'Full candidate qualification.' : 'Only the cells without valid evidence.') + ' Prior trials are retained in ' + rec.id + '.' };
  }
  const summary = { stands: conclusions.filter(x => x.status === 'stands').length, recomputed: conclusions.filter(x => x.status === 'recomputed').length, requires_measurement: required.length ? required.length * plan.repeats : 0, superseded: conclusions.some(x => x.status === 'superseded') };
  return { schema: 'hot-aisle/revalidation@1', record_id: rec.id, change, conclusions, scenario, minimal_plan: minimal, reevaluate, summary };
}

function c(subject, status, detail) { return { subject, status, detail }; }
function pick(o, keys) { const out = {}; for (const k of keys) if (o[k] !== undefined) out[k] = o[k]; return out; }
function cloneInput(plan) {
  return { target: { ...plan.target }, workload: { ...plan.workload }, concurrency: [...plan.concurrency], repeats: plan.repeats, identity: { ...plan.identity }, price: { ...plan.price }, comparator: plan.comparator ? { ...plan.comparator } : null, limits: { ...plan.limits }, gates: { ...plan.gates }, requirements: { ...plan.requirements }, primary_concurrency: plan.primary_concurrency };
}

/* Scenario projections reuse the record's own machinery with substituted inputs; the
   observed section is untouched. */
function rederive(rec, planPatch) {
  const clone = JSON.parse(JSON.stringify(rec));
  Object.assign(clone.declared.plan, planPatch);
  if (planPatch.price) clone.declared.price = planPatch.price;
  if (planPatch.gates) clone.rule.gates = planPatch.gates;
  if (planPatch.requirements) clone.rule.requirements = planPatch.requirements;
  const derived = record.derive(clone);
  return { cells: derived.cells.map(x => ({ concurrency: x.concurrency, cost_per_1000: x.cost ? x.cost.costPer1000 : null, accepted_per_s: x.aggregate ? x.aggregate.rate : null, unit: x.aggregate ? x.aggregate.unit : null, meets: x.meets, reasons: x.reasons })), primary_concurrency: derived.primary_concurrency, qualified: derived.disposition.qualified, reasons: derived.disposition.reasons };
}
function priceScenario(rec, price) { return { kind: 'price', price, ...rederive(rec, { price }) }; }
function gateScenario(rec, gates, prev) { const s = rederive(rec, { gates, ...(prev && prev.price ? { price: prev.price } : {}) }); return { kind: prev ? prev.kind + '+gates' : 'gates', gates, ...(prev && prev.price ? { price: prev.price } : {}), ...s }; }
function requirementScenario(rec, requirements, prev) { const s = rederive(rec, { requirements, ...(prev && prev.price ? { price: prev.price } : {}), ...(prev && prev.gates ? { gates: prev.gates } : {}) }); return { ...(prev || {}), kind: prev ? prev.kind + '+requirements' : 'requirements', requirements, ...s }; }

module.exports = { revalidate, RUNTIME_KEYS, WORKLOAD_KEYS };
