'use strict';
/* The runner owns the qualified record and its publication contract.
   A desk consumes this pair; it never interprets raw vLLM rows again. */
const engine = require('./engine.cjs');
const record = require('./record.cjs');

function verifyRecord(rec) {
  if (!rec || typeof rec !== 'object') throw Error('Qualified record required.');
  const v = record.verify(rec);
  if (!v.verified) throw Error('Qualified record rejected: ' + v.problems.join(' '));
  if (rec.derived.engine.engine_sha256 !== engine.identity().engine_sha256)
    throw Error('Report-engine identity differs; requalify the verifier for this record.');
  return rec;
}
function bundle(rec) {
  verifyRecord(rec);
  const evidence = record.packet(rec);
  engine.load().recompute(evidence);
  return {schema:'hot-aisle/publication@1', record:rec, evidence};
}
function verify(input) {
  if (!input || input.schema !== 'hot-aisle/publication@1') throw Error('Unsupported publication contract.');
  const rec = verifyRecord(input.record), HA=engine.load();
  HA.recompute(input.evidence);
  if (HA.canonical(input.evidence) !== HA.canonical(record.packet(rec)))
    throw Error('Evidence packet does not belong to this qualified record and primary cell.');
  return input;
}
function identity(input) {
  verify(input);
  return engine.sha256(engine.load().canonical(input));
}
function projection(input) {
  verify(input);
  const rec=input.record, cell=record.primaryCell(rec);
  const expected=rec.declared.plan.concurrency.length*rec.declared.plan.repeats;
  return {publication_id:rec.id+'-'+rec.sha256.slice(0,16), record_id:rec.id,
    record_sha256:rec.sha256, publication_sha256:identity(input),
    model:rec.declared.plan.workload.model, created:rec.created,
    synthetic:rec.synthetic, qualified:rec.disposition.qualified,
    completed_trials:rec.observed.trials.length, expected_trials:expected,
    complete:rec.observed.trials.length===expected && rec.observed.failed_trials.length===0,
    primary_concurrency:rec.derived.primary_concurrency,
    headline:record.headline(rec), cell};
}
module.exports={bundle,verify,identity,projection};
