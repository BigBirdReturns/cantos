#!/usr/bin/env node
'use strict';
/* Builds the real Run 3 qualified record for the page's front door.
   Inputs are the retained A/T0 arm bytes under campaign/results/run3-scored-a-t0 (Hot Aisle
   1x MI300X, 2026-09-24). The record is derived by the page's own report engine through the
   runner's record module; nothing here types a figure. Outputs:
     data/run3/{record,evidence,headline}.json, report.html, SOURCES.json, source/*
   and, with --embed, the two marked blocks in index.html (run3-record, market-data) so the page
   opens from disk with zero network requests.
   Usage: node data/run3/build-run3.cjs [--embed]
   The record's `created` is fixed (the day the record was retrofitted) so a rebuild is byte-stable. */
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const root = path.resolve(__dirname, '..', '..');
const engine = require('../../runner/lib/engine.cjs');
const record = require('../../runner/lib/record.cjs');
const HA = engine.load();
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const CREATED = '2026-09-29T00:00:00.000Z';

const arm = path.join(root, 'campaign', 'results', 'run3-scored-a-t0');
const results = path.join(root, 'campaign', 'results');
const files = {
  'source/detailed.json': path.join(arm, 'detailed.json'),
  'source/evaluation.json': path.join(arm, 'grade', 'evaluation.json'),
  'source/ledger-times.json': path.join(arm, 'ledger-times.json'),
  'source/env.json': path.join(arm, 'env.json'),
  'source/invocation.json': path.join(arm, 'invocation.json'),
  'source/MANIFEST.sha256': path.join(arm, 'MANIFEST.sha256'),
  'source/RUN3-RESULTS.md': path.join(results, 'RUN3-RESULTS.md'),
  'source/DISCLOSURES.md': path.join(root, 'campaign', 'DISCLOSURES.md'),
};
const out = __dirname;
fs.mkdirSync(path.join(out, 'source'), { recursive: true });
const bytes = {};
for (const [dst, src] of Object.entries(files)) { bytes[dst] = fs.readFileSync(src); fs.writeFileSync(path.join(out, dst), bytes[dst]); }

function median(xs) { const s = [...xs].sort((p, q) => p - q), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; }

const detailBytes = bytes['source/detailed.json'];
const raw = JSON.parse(detailBytes);
const source = { sha256: sha(detailBytes), record_index: 0, bytes: detailBytes.length };
let run = HA.normalize(raw, source);
run = HA.attachQuality(run, JSON.parse(bytes['source/evaluation.json']));
const times = JSON.parse(bytes['source/ledger-times.json']);
const id = run.identity;

const plan = {
  schema: 'hot-aisle/evaluation-plan@1',
  provenance: 'Retrofitted from retained Run 3 arm bytes by data/run3/build-run3.cjs. Not produced by a runner job and not approved through the runner; the trial is the retained detailed result, hashed as received.',
  target: { adapter: 'hotaisle', exec: 'ssh', name: 'enc1-gpuvm004', host: 'enc1-gpuvm004', gpus: 1, gpu_model: 'AMD MI300X', allocation_label: '1× MI300X VM' },
  workload: { backend: 'openai', dataset: 'azure-llm-inference-code-trace-2023', model: raw.model_id, base_url: 'http://127.0.0.1:8000', input_len: Math.round(median(raw.input_lens)), output_len: Math.round(median(raw.output_lens)), num_prompts: raw.num_prompts, request_rate: 'trace-replay x0.95', seed: 700000, note: 'Bursty trace replay of graded EvalPlus tasks. input_len and output_len are per-request medians (tokens), not a fixed shape.' },
  concurrency: [256], repeats: 1,
  identity: { model_revision: id.revision, precision: id.precision, tokenizer_revision: id.tokenizer, cache_policy: id.cache, runtime_digest: id.runtime, workload_id: id.workload },
  price: { provider: 'Hot Aisle', gpus: 1, rate: 2.99, extra: 0, source: 'undiscounted list price; the run was paid from a Hot Aisle credit', period: '2026-09-24' },
  comparator: { provider: 'DigitalOcean H100', gpus: 1, rate: 4.41, extra: 0, source: 'DigitalOcean list price, campaign DISCLOSURES.md', period: '2026-09-24' },
  limits: { max_minutes: 110, max_spend_usd: null },
  gates: { ttft: 1000, e2e: 60000, queue: true, quality: true },
  requirements: { max_p95_ttft_ms: 1000, max_p95_e2e_ms: 60000, min_accepted_per_s: null, max_failure_rate: 0.01 },
  primary_concurrency: 256,
  created: '2026-09-24T00:42:43.547Z',
};
plan.cells = [{ concurrency: 256, repeat: 0 }];
plan.commands = [];
{ const { sha256, commands, ...body } = plan; plan.sha256 = engine.sha256(HA.canonical(body)); }

const job = {
  id: 'job-20260924T004243Z-run3at0', plan, approval: null, disposition: null,
  trials: [{ status: 'completed', cell: { concurrency: 256, repeat: 0 }, source, normalized: run, started: times.t_work_start, ended: times.t_work_end }],
};
const rec = record.build(job);
rec.created = CREATED;
{ const { sha256, ...rest } = rec; rec.sha256 = engine.sha256(HA.canonical(rest)); }
const v = record.verify(rec);
if (!v.verified) { console.error('record failed verification: ' + v.problems.join(' | ')); process.exit(1); }
const packet = record.packet(rec);
HA.recompute(packet);
const headline = record.headline(rec, { evidence_url: 'evidence.json', report_url: 'report.html' });
fs.writeFileSync(path.join(out, 'record.json'), JSON.stringify(rec, null, 2) + '\n');
fs.writeFileSync(path.join(out, 'evidence.json'), JSON.stringify(packet, null, 2) + '\n');
fs.writeFileSync(path.join(out, 'report.html'), record.receipt(rec));
fs.writeFileSync(path.join(out, 'headline.json'), JSON.stringify(headline, null, 2) + '\n');

const disk = n => sha(fs.readFileSync(path.join(out, n)));
const sources = {
  schema: 'hot-aisle/run3-sources@1',
  note: 'Origin paths are relative to the parent of the axm-tools checkout copy (main/). sha256 is of the bytes copied here; each copy is byte-identical to its origin at build time.',
  built_by: 'data/run3/build-run3.cjs',
  record: { id: rec.id, sha256: rec.sha256, engine_sha256: rec.derived.engine.engine_sha256, primary_concurrency: 256 },
  derived: ['record.json', 'evidence.json', 'headline.json', 'report.html'].map(n => ({ file: n, sha256: disk(n) })),
  copies: Object.entries(files).map(([dst, src]) => ({ file: dst, origin: path.relative(path.resolve(root, '..'), src).replace(/\\/g, '/'), sha256: sha(bytes[dst]), bytes: bytes[dst].length })),
  not_copied: 'The graded completions (tasks.json, replay/) stay in campaign/results/run3-scored-a-t0 and are named in MANIFEST.sha256.',
};
fs.writeFileSync(path.join(out, 'SOURCES.json'), JSON.stringify(sources, null, 2) + '\n');

if (process.argv.includes('--embed')) {
  const page = path.join(root, 'index.html');
  let html = fs.readFileSync(page, 'utf8');
  const swap = (name, payload) => {
    const re = new RegExp('<!-- ' + name + ':begin -->[\\s\\S]*?<!-- ' + name + ':end -->');
    const block = '<!-- ' + name + ':begin --><script id="' + name + '" type="application/json">' + JSON.stringify(payload).replace(/<\//g, '<\\/') + '</script><!-- ' + name + ':end -->';
    if (!re.test(html)) throw new Error(name + ' markers not found in index.html');
    html = html.replace(re, () => block);
  };
  swap('run3-record', { ...rec, links: { report: 'data/run3/report.html', evidence: 'data/run3/evidence.json', record: 'data/run3/record.json' } });
  swap('market-data', JSON.parse(fs.readFileSync(path.join(root, 'data', 'market.json'), 'utf8')));
  fs.writeFileSync(page, html);
}
const a = rec.derived.cells[0].aggregate, c = rec.derived.cells[0].cost;
console.log(JSON.stringify({ record: rec.id, sha256: rec.sha256, qualified: rec.disposition.qualified, accepted: a.accepted, attempted: a.attempted, cost_per_1000: c.costPer1000, rate: a.rate, p95_ttft_ms: a.metrics.ttft.p95 }, null, 2));
