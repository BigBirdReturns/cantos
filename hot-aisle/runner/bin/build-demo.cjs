#!/usr/bin/env node
'use strict';
/* Builds the demonstration record that ships inside the page. It runs the real
   pipeline (plan → approve → run → record) against the local integration environment
   in a throwaway state directory, then embeds the resulting record between the
   demo-record markers in index.html and writes its projections under data/demo/.
   The record is synthetic by construction and says so in every projection. */
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { Store } = require('../lib/store.cjs');
const { Jobs } = require('../lib/jobs.cjs');
const record = require('../lib/record.cjs');
const local = require('../lib/adapters/local.cjs');

async function main() {
  const root = path.resolve(__dirname, '..', '..');
  const page = path.join(root, 'index.html');
  const store = new Store(fs.mkdtempSync(path.join(os.tmpdir(), 'wl-demo-')));
  const jobs = new Jobs(store);
  const job = jobs.plan(local.demoPlanInput({ repeats: 2, concurrency: [1, 8, 32], target: { env: { FAKE_VLLM_DELAY_MS: '0' } } }));
  jobs.approve(job.id, { by: 'build-demo', plan_sha256: job.plan.sha256 });
  const s = await jobs.start(job.id);
  if (s.state !== 'completed' || !s.record_id) throw new Error('Demo run did not complete: ' + s.state);
  const rec = store.read('records', s.record_id);
  const v = record.verify(rec);
  if (!v.verified) throw new Error('Demo record failed verification: ' + v.problems.join(' '));
  const out = path.join(root, 'data', 'demo');
  fs.mkdirSync(out, { recursive: true });
  fs.writeFileSync(path.join(out, 'record.json'), JSON.stringify(rec, null, 2) + '\n');
  fs.writeFileSync(path.join(out, 'evidence.json'), JSON.stringify(record.packet(rec), null, 2) + '\n');
  fs.writeFileSync(path.join(out, 'report.html'), record.receipt(rec));
  fs.writeFileSync(path.join(out, 'summary.txt'), record.summary(rec) + '\n');
  fs.writeFileSync(path.join(out, 'headline.json'), JSON.stringify(record.headline(rec, { evidence_url: 'evidence.json', report_url: 'report.html' }), null, 2) + '\n');
  const embedded = { ...rec, links: { report: 'data/demo/report.html', evidence: 'data/demo/evidence.json', record: 'data/demo/record.json' } };
  const html = fs.readFileSync(page, 'utf8');
  const block = '<!-- demo-record:begin --><script id="demo-record" type="application/json">' + JSON.stringify(embedded).replace(/<\//g, '<\\/') + '</script><!-- demo-record:end -->';
  const next = html.replace(/<!-- demo-record:begin -->[\s\S]*?<!-- demo-record:end -->/, block);
  if (next === html) throw new Error('demo-record markers not found in index.html');
  fs.writeFileSync(page, next);
  console.log(JSON.stringify({ record: rec.id, sha256: rec.sha256, synthetic: rec.synthetic, qualified: rec.disposition.qualified, primary_concurrency: rec.derived.primary_concurrency, trials: rec.observed.trials.length, embedded_bytes: block.length, out }, null, 2));
}

main().catch(e => { console.error('build-demo failed: ' + e.message); process.exit(1); });
