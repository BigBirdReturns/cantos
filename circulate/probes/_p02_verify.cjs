'use strict';
// usage: node _p02_verify.cjs <hot-aisle dir> <record.json> <evidence.json>
// Mirrors runner/test/run3-door.test.cjs: record.verify, then publication.verify (which runs the page engine's recompute
// and requires the evidence to equal the packet derived from the record). Prints one JSON line. A number is printed only
// when every check passed, which is what the front-door card does.
const path = require('node:path'), fs = require('node:fs');
const [, , ha, recPath, evPath] = process.argv;
const record = require(path.join(ha, 'runner/lib/record.cjs'));
const publication = require(path.join(ha, 'runner/lib/publication.cjs'));
const engine = require(path.join(ha, 'runner/lib/engine.cjs'));
const out = { record_verified: null, publication_verified: false, error: null, cost_per_1000: null, engine_step: null };
try {
  const rec = JSON.parse(fs.readFileSync(recPath, 'utf8'));
  const ev = JSON.parse(fs.readFileSync(evPath, 'utf8'));
  out.record_verified = record.verify(rec).verified;
  out.engine_step = 'recompute';
  engine.load().recompute(JSON.parse(JSON.stringify(ev)));
  out.engine_step = 'publication.verify';
  publication.verify({ schema: 'hot-aisle/publication@1', record: rec, evidence: ev });
  out.publication_verified = true;
  out.cost_per_1000 = rec.derived.cells[0].cost.costPer1000;
} catch (e) { out.error = String(e && e.message || e); }
console.log(JSON.stringify(out));
