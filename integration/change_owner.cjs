'use strict';
/* File exchange with existing owners. No new grading or dependency validator. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

async function execute(input) {
  const raw = fs.readFileSync(input.source);
  const source = JSON.parse(raw);
  if (input.task_class === 'record-change') {
    if (source.schema !== 'hot-aisle/qualified-record@1') throw Error('record-change requires a qualified record; an imported aggregate or shelf card is not one.');
    const { revalidate } = require('../hot-aisle/runner/lib/revalidate.cjs');
    const result = revalidate(source, input.change);
    return { task_class: input.task_class, source_sha256: digest(raw),
      source_record_id: source.id, synthetic: source.synthetic, result,
      boundary: 'Native revalidation of supplied retained evidence. Plans and evaluator requests are proposed operations; no benchmark, evaluator, resource allocation, approval or publication was executed.' };
  }
  if (input.task_class !== 'source-correction') throw Error('Unsupported change task class.');
  const app = fs.readFileSync(path.join(root, 'research-desk/app.html'));
  if (digest(app) !== input.expected_app_sha256) throw Error('Research Desk source changed after preparation.');
  const scripts = [...app.toString('utf8').matchAll(/<script id="research-core">([\s\S]*?)<\/script>/g)];
  if (scripts.length !== 1) throw Error('Exactly one marked ResearchCore script is required.');
  vm.runInThisContext(scripts[0][1], { filename: 'research-desk/app.html#research-core' });
  const C = globalThis.ResearchCore;
  const ws = await C.verifyPacket(source);
  const before = C.state(ws);
  const previous = C.latest(before, input.change.record_id);
  if (!previous) throw Error('Correction target is absent from the research packet.');
  const affectedIds = C.impact(before, previous.id);
  const beforeStates = {};
  for (const id of affectedIds) beforeStates[id] = {
    dependency: C.dependencyState(before, id), review: await C.reviewState(before, id),
  };
  const timestamp = input.change.timestamp ?? ws.events.at(-1)?.at;
  if (!timestamp) throw Error('Correction requires an explicit timestamp or a retained input-event timestamp.');
  const historical = C.canonical(before.reports);
  const successor = await C.put(ws, { ...previous, ...input.change.patch },
    'Common operating floor: local candidate preparation', timestamp);
  const after = C.state(ws);
  const affected = [];
  for (const id of affectedIds) affected.push({ id, before: beforeStates[id],
    after: { dependency: C.dependencyState(after, id), review: await C.reviewState(after, id) } });
  if (historical !== C.canonical(after.reports)) throw Error('Historical report snapshots changed.');
  return { task_class: input.task_class, source_sha256: digest(raw),
    research_core_sha256: digest(app), source_record_id: previous.id,
    before_revision: previous.revision, after_revision: successor.revision,
    event_timestamp: timestamp, timestamp_basis: input.change.timestamp ? 'explicit' : 'inherited from last input event; not a fresh observation time',
    affected, packet: await C.pack(ws), historical_reports_preserved: true,
    next_operation: affected.length ? 'Revisit affected records against the corrected source; recompute supported calculations and obtain any required fresh review.' : 'No existing dependent records were found.',
    boundary: 'Native ResearchCore revision and dependency handling only. No review, accepted standing, frozen successor report, source authenticity or external action is granted.' };
}

let text = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { text += chunk; });
process.stdin.on('end', () => execute(JSON.parse(text)).then(result => {
  process.stdout.write(JSON.stringify(result) + '\n');
}).catch(error => { process.stderr.write(error.message + '\n'); process.exitCode = 1; }));
