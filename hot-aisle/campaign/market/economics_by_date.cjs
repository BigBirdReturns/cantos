'use strict';
// Price-only recompute of the retained Run 3 economics (RERUN-POLICY: "Price changes only: recompute
// economics with dated price, billing minimum, credits and setup interval. No GPU rerun").
// There is no CLI for this on the ledger arms (runner `revalidate` needs a runner qualified record), so this
// script calls the page engine's normalize/attachQuality/aggregate/costing (via run3_engine_accept.cjs).
//   node economics_by_date.cjs  -> writes RUN3-ECONOMICS-BY-DATE.jsonl
// Interval per arm (same as the published $0.74 / $1.20): A/T0 own-seat-equivalent = (t_ssh - seat request)
// + (t_script_end - t_script_start) = 64.68 min; N/T0 = closure t_request -> t_released = 69.82 min.
const fs = require('node:fs'), path = require('node:path');
const { load, ROOT, sha } = require('./run3_engine_accept.cjs');
const PH = path.join(ROOT, 'data/price-history');
const RES = path.join(ROOT, 'campaign/results');
const ms = t => Date.parse(t);
const readJ = f => JSON.parse(fs.readFileSync(f, 'utf8'));

const { H, arms } = load();
const aT = readJ(path.join(RES, 'run3-scored-a-t0/ledger-times.json'));
const seatRequest = '2026-09-24T00:08:55Z'; // RUN3-HOTAISLE-SUMMARY.md: requested 00:08:55Z (shared seat)
const hoursA = ((ms(aT.t_ssh) - ms(seatRequest)) + (ms(aT.t_script_end) - ms(aT.t_script_start))) / 3.6e6;
const nC = readJ(path.join(RES, 'run3-scored-n-t0/closure.json'));
const hoursN = (ms(nC.t_released) - ms(nC.t_request)) / 3.6e6;
const AS_RUN = { ha: 2.99, cmp: 4.41 };
const IDX = readJ(path.join(PH, 'INDEX.json'));
const SRC_PRI = ['getdeploying', 'shadeform', 'skypilot'];

function file(p, day) { const f = path.join(PH, p, day + '.json'); if (!fs.existsSync(f)) return null; const b = fs.readFileSync(f); return { sha: sha(b), j: JSON.parse(b) }; }
function haPrice(f) { // 1x MI300X on-demand VM, latest snapshot of the day
  const c = f.j.products.filter(x => x.gpu === 'MI300X' && x.gpu_count === 1 && x.price_type === 'on_demand' && x.hourly_price_usd != null);
  if (!c.length) return null; c.sort((a, b) => a.snapshot_ts < b.snapshot_ts ? 1 : -1); return { rate: c[0].hourly_price_usd, source: c[0].source, all: [...new Set(c.map(x => x.hourly_price_usd))] };
}
function cmpPrice(f) { // DigitalOcean 1x H100 on-demand; source priority, cheapest region row if several
  const c = f.j.products.filter(x => x.gpu === 'H100' && x.gpu_count === 1 && x.price_type === 'on_demand' && x.hourly_price_usd != null);
  const by = {}; for (const x of c) (by[x.source] ??= []).push(x.hourly_price_usd);
  const src = SRC_PRI.find(s => by[s]); if (!src) return null;
  return { rate: Math.min(...by[src]), source: src, all_sources: Object.fromEntries(Object.entries(by).map(([k, v]) => [k, Math.min(...v)])) };
}
const cost = (arm, hours, rate) => { const c = H.costing({ window_seconds: 0, accepted: arm.accepted, duration: 0, unit: 'accepted requests' }, { provider: 'x', gpus: 1, rate, extra: 0, total: rate * hours, source: 'dated', period: 'dated' }); return c.costPer1000; };
const r4 = x => x == null ? null : +x.toFixed(4);

const common = {
  engine: H.VERSION, accepted_hot_aisle: arms.A_T0.accepted, accepted_comparator: arms.N_T0.accepted,
  billed_hours_hot_aisle: +hoursA.toFixed(4), billed_hours_comparator: +hoursN.toFixed(4),
  billing_minimum_applied: 'none binding (both intervals exceed any minimum: DO 60s/5min, Hot Aisle none published)',
  credits: 'Hot Aisle arm was paid from credit; costed at list (credit not netted). Comparator self-funded.',
  setup_interval: 'included: A/T0 seat request->SSH (2.03 min) + arm window; N/T0 request->release',
  run3_source_sha256: { hot_aisle_detailed: arms.A_T0.detailed_sha256, hot_aisle_evaluation: arms.A_T0.evaluation_sha256, comparator_detailed: arms.N_T0.detailed_sha256, comparator_evaluation: arms.N_T0.evaluation_sha256 },
};
const out = [];
out.push({ kind: 'as_run_reference', date: '2026-09-24', hot_aisle_gpu_hour: AS_RUN.ha, comparator_gpu_hour: AS_RUN.cmp,
  comparator: 'DigitalOcean 1x H100 (as run; self-funded list price)', cost_per_1k_accepted_hot_aisle: r4(cost(arms.A_T0, hoursA, AS_RUN.ha)),
  cost_per_1k_accepted_comparator: r4(cost(arms.N_T0, hoursN, AS_RUN.cmp)), price_source: 'campaign/results/RUN3-RESULTS.md', ...common });
const days = IDX.providers.hot_aisle.files.map(x => x.date);
for (const day of days) {
  const ha = file('hot_aisle', day), dof = file('digitalocean', day);
  const hp = ha && haPrice(ha), cp = dof && cmpPrice(dof);
  const a = hp ? cost(arms.A_T0, hoursA, hp.rate) : null, n = cp ? cost(arms.N_T0, hoursN, cp.rate) : null;
  out.push({ kind: 'dated', date: day, hot_aisle_gpu_hour: hp && hp.rate, hot_aisle_price_source: hp && hp.source,
    comparator_gpu_hour: cp && cp.rate, comparator: 'DigitalOcean 1x H100 on-demand', comparator_source: cp && cp.source,
    comparator_all_source_values: cp && cp.all_sources,
    cost_per_1k_accepted_hot_aisle: r4(a), cost_per_1k_accepted_comparator: r4(n),
    hot_aisle_cheaper_by: a != null && n != null ? +(1 - a / n).toFixed(4) : null,
    source_sha256: { hot_aisle_price_file: ha && ha.sha, comparator_price_file: dof && dof.sha, opencomputeprices_prices_jsonl: IDX.generated_from.sha256 },
    ...common });
}
fs.writeFileSync(path.join(__dirname, 'RUN3-ECONOMICS-BY-DATE.jsonl'), out.map(x => JSON.stringify(x)).join('\n') + '\n');
console.log('rows', out.length, 'hoursA', hoursA.toFixed(4), 'hoursN', hoursN.toFixed(4));
console.log(out.slice(0, 2).concat(out.slice(-2)).map(x => [x.kind, x.date, x.hot_aisle_gpu_hour, x.comparator_gpu_hour, x.cost_per_1k_accepted_hot_aisle, x.cost_per_1k_accepted_comparator, x.hot_aisle_cheaper_by].join(' ')).join('\n'));
