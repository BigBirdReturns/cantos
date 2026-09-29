'use strict';
/* The front door opens on the real Run 3 record. These checks bind the shipped bytes together:
   record, evidence, headline, sources, the copy embedded in index.html, and the market strip. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const engine = require('../lib/engine.cjs');
const record = require('../lib/record.cjs');
const publication = require('../lib/publication.cjs');

const root = path.resolve(__dirname, '..', '..');
const read = p => fs.readFileSync(path.join(root, p));
const json = p => JSON.parse(read(p));
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const html = read('index.html').toString('utf8');
const embedded = id => { const m = html.match(new RegExp('<script id="' + id + '" type="application/json">([\\s\\S]*?)</script>')); assert.ok(m, id + ' block missing'); return JSON.parse(m[1]); };

test('the real Run 3 record verifies through the runner and the published pair recomputes', () => {
  const rec = json('data/run3/record.json'), ev = json('data/run3/evidence.json');
  const v = record.verify(rec);
  assert.deepEqual(v.problems, []);
  assert.equal(rec.synthetic, false);
  assert.equal(rec.disposition.qualified, true);
  publication.verify({ schema: 'hot-aisle/publication@1', record: rec, evidence: ev });
  const a = rec.derived.cells[0].aggregate, c = rec.derived.cells[0].cost;
  assert.equal(a.accepted, 4336);
  assert.equal(a.attempted, 8622);
  assert.equal(a.synthetic, false);
  assert.equal(rec.scenario.allocation.gpu_model, 'AMD MI300X');
  assert.ok(Math.abs(c.costPer1000 - 0.6908) < 1e-4);
});

test('the record is bound to the retained result bytes copied beside it', () => {
  const rec = json('data/run3/record.json');
  const src = rec.observed.trials[0].source;
  assert.equal(sha(read('data/run3/source/detailed.json')), src.sha256);
  assert.equal(read('data/run3/source/detailed.json').length, src.bytes);
  // the engine, given the original bytes, reproduces the normalized trial exactly
  const HA = engine.load();
  let run = HA.normalize(json('data/run3/source/detailed.json'), src);
  run = HA.attachQuality(run, json('data/run3/source/evaluation.json'));
  assert.equal(HA.canonical(run), HA.canonical(rec.observed.trials[0].normalized));
});

test('SOURCES.json hashes match every shipped file', () => {
  const s = json('data/run3/SOURCES.json');
  assert.equal(s.record.sha256, json('data/run3/record.json').sha256);
  for (const f of [...s.derived, ...s.copies]) assert.equal(sha(read('data/run3/' + f.file)), f.sha256, f.file);
  assert.ok(s.copies.every(f => /^[a-z0-9_./-]+$/i.test(f.origin) && !/^[A-Za-z]:/.test(f.origin)), 'origins are portable paths');
  const h = json('data/run3/headline.json');
  assert.equal(h.record_sha256, s.record.sha256);
});

test('the copy embedded in index.html is the shipped record', () => {
  const rec = json('data/run3/record.json');
  const { links, ...plain } = embedded('run3-record');
  assert.deepEqual(plain, rec);
  assert.equal(links.record, 'data/run3/record.json');
  assert.equal(record.verify(plain).verified, true);
});

test('the report engine identity in the record matches the page', () => {
  assert.equal(json('data/run3/record.json').derived.engine.engine_sha256, engine.identity().engine_sha256);
});

test('market strip data: the four GPUs, provider counts, source and manifest hash', () => {
  const m = json('data/market.json');
  assert.deepEqual(m.gpus.map(g => [g.gpu, g.median_usd_per_gpu_hr, g.providers]), [['MI300X', 3.04, 7], ['H100', 2.99, 42], ['H200', 4.29, 33], ['B200', 6.49, 23]]);
  assert.equal(m.source, 'OpenComputePrices latest-data release 2026-07-29');
  assert.equal(m.period, '2026-07');
  assert.match(m.master_csv_sha256, /^[0-9a-f]{64}$/);
  assert.match(m.label.toLowerCase(), /public on-demand list prices, not the priced allocation/);
  assert.deepEqual(embedded('market-data'), m);
});
