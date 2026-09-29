#!/usr/bin/env node
'use strict';
/* Usage: node validate_packet.js [packet.json]   (default: PUBLIC-TAIL-2026-09-29.research-packet.json)
   Replays the import checks of Research Desk 1.0.0 (app.html "Open packet" -> parse -> verifyPacket):
   size limit, envelope schema, workspace checksum, per-event sequence/predecessor/hash, record rules
   (kind, tier, disposition, id, revision sequence, dependency pins, cycles, kind stability, limits),
   then runs the app's own verifyPacket (extracted from the pinned app.html) as the authoritative replay.
   Exit code 0 = pass, 1 = fail. No dependencies. */
const fs = require('fs');
const path = require('path');
const B = require('./build_packet.js');
const { canonical, hash, ZERO } = B;

const file = path.resolve(process.argv[2] || path.join(__dirname, 'PUBLIC-TAIL-2026-09-29.research-packet.json'));
const KINDS = ['source', 'claim', 'policy', 'run', 'calculation', 'conclusion', 'instruments', 'diligence', 'mandate'];
const TIERS = ['public_observation', 'operator_supplied', 'synthetic', 'proposal'];
const DISPS = ['open', 'observed', 'supported', 'conflict', 'withdrawn', 'draft'];
const fails = [];
const fail = m => { if (fails.length < 25) fails.push(m); else if (fails.length === 25) fails.push('... further failures suppressed'); };
const check = (ok, m) => { if (!ok) fail(m); return ok; };

(async () => {
  const t0 = Date.now();
  const raw = fs.readFileSync(file, 'utf8');
  check(raw.length <= 12000000, 'File limit is 12 MB (app import: Packet exceeds 12 MB).');
  const packet = JSON.parse(raw);
  B.safeTree(packet);
  check(packet.schema === 'second-run/research-packet@1', 'Unsupported workspace envelope.');
  const ws = packet.workspace;
  check(ws?.schema === B.SCHEMA && ws.version === B.VERSION, 'Unsupported workspace version.');
  check(typeof ws?.label === 'string' && ws.label.trim() && ws.label.length <= 200, 'Workspace label invalid.');
  check(Array.isArray(ws?.events) && ws.events.length <= 3000, 'Invalid event list.');
  if (fails.length) return finish();

  check(await hash(ws) === packet.sha256, 'Workspace checksum failed.');
  check(canonical(ws).length <= 11000000, 'Workspace exceeds the 11 MB working limit.');

  const latest = new Map();          // id -> latest record
  const versions = new Map();        // id -> Map(revision -> record)
  const counts = {}, tiers = {}, disps = {};
  let prev = ZERO;
  for (const [i, e] of ws.events.entries()) {
    const where = 'event ' + (i + 1);
    check(e.seq === i + 1, where + ': Noncontiguous event sequence.');
    check(e.prev === prev, where + ': Broken predecessor.');
    const { hash: stored, ...body } = e;
    check(await hash(body) === stored, where + ': Event hash failed.');
    prev = stored;
    check(typeof e.actor === 'string' && e.actor.trim() && e.actor.length <= 160, where + ': actor invalid.');
    check(typeof e.at === 'string' && /T.*(?:Z|[+-]\d\d:\d\d)$/.test(e.at) && Number.isFinite(Date.parse(e.at)), where + ': Timestamp requires a timezone.');
    if (e.type !== 'record') { check(['review', 'freeze'].includes(e.type), where + ': Unknown journal event.'); continue; }
    const r = e.payload;
    check(typeof r.id === 'string' && r.id.length <= 90 && /^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$/.test(r.id), where + ': Invalid ID ' + r.id);
    check(KINDS.includes(r.kind), where + ': Unsupported record kind ' + r.kind);
    const p = latest.get(r.id);
    if (p) check(p.kind === r.kind, where + ': A successor cannot change the record kind.');
    check(typeof r.title === 'string' && r.title.trim() && r.title.length <= 240, where + ': Title invalid (' + r.id + ').');
    check(typeof r.summary === 'string' && r.summary.length <= 30000, where + ': Summary too long.');
    check(TIERS.includes(r.tier), where + ': Evidence tier is required.');
    check(DISPS.includes(r.disposition), where + ': Invalid disposition ' + r.disposition);
    check(Array.isArray(r.deps) && r.deps.length <= 100, where + ': Dependencies must be an array.');
    check(r.revision === (p?.revision || 0) + 1, where + ': Revision must be the next sequence (' + r.id + ').');
    const seen = new Set();
    for (const d of r.deps || []) {
      check(typeof d.id === 'string' && /^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$/.test(d.id), where + ': dep id invalid.');
      check(!seen.has(d.id), where + ': Duplicate dependency.'); seen.add(d.id);
      check(d.id !== r.id, where + ': A record cannot depend on itself.');
      check(Number.isInteger(d.revision) && versions.get(d.id)?.has(d.revision), where + ': Dependency revision missing: ' + d.id);
    }
    // stable-ID cycle walk, as in the app
    const walk = (key, visited = new Set()) => { if (key === r.id) { fail(where + ': Dependency cycle.'); return; } if (visited.has(key)) return; visited.add(key); for (const d of latest.get(key)?.deps || []) walk(d.id, visited); };
    for (const d of r.deps || []) walk(d.id);
    check(r.data !== null && typeof r.data === 'object' && !Array.isArray(r.data), where + ': Record data must be an object.');
    // provenance rule for this packet: every source needs url + sha256 + a retrieval stamp
    if (r.kind === 'source') check(/^https?:\/\//.test(r.data.url || '') && /^[0-9a-f]{64}$/.test(r.data.sha256 || '') && (r.data.retrieved_utc || r.data.retrieved_date), where + ': source lacks url/sha256/retrieval stamp (' + r.id + ').');
    if (r.kind === 'claim') { const d = r.deps[0] && versions.get(r.deps[0].id)?.get(r.deps[0].revision); check(d?.kind === 'source', where + ': claim must pin a source record (' + r.id + ').'); }
    if (!versions.has(r.id)) versions.set(r.id, new Map());
    versions.get(r.id).set(r.revision, r);
    latest.set(r.id, r);
    counts[r.kind] = (counts[r.kind] || 0) + 1; tiers[r.tier] = (tiers[r.tier] || 0) + 1; disps[r.disposition] = (disps[r.disposition] || 0) + 1;
  }
  if (fails.length) return finish();

  // The app's own code path: extract research-core from the pinned app.html and run verifyPacket.
  const { core, appSha256 } = B.loadAppCore();
  // Cross-check the copied primitives against the app's on this very packet.
  const appPacket = core.parse(raw); // parsed inside the app's realm (its plain() test is realm-bound)
  check(core.canonical(appPacket.workspace) === canonical(ws), 'canonical() differs from the app copy.');
  check(await core.hash(appPacket.workspace) === packet.sha256, 'app hash(workspace) differs from packet.sha256.');
  try {
    const t1 = Date.now();
    const restored = await core.verifyPacket(core.parse(raw));
    console.log('app verifyPacket: OK, ' + restored.events.length + ' events replayed in ' + ((Date.now() - t1) / 1000).toFixed(1) + ' s');
    const s = core.state(restored);
    let blocked = 0; for (const k of Object.keys(s.records)) if (!core.dependencyState(s, k).current) blocked++;
    console.log('app dependencyState: ' + (Object.keys(s.records).length - blocked) + ' records current, ' + blocked + ' blocked (open dispositions block downstream acceptance by design)');
  } catch (err) { fail('app verifyPacket: ' + err.message); }
  console.log('app.html sha256 ' + appSha256);
  console.log('by kind ' + JSON.stringify(counts) + ' by tier ' + JSON.stringify(tiers) + ' by disposition ' + JSON.stringify(disps));
  console.log('elapsed ' + ((Date.now() - t0) / 1000).toFixed(1) + ' s');
  finish();

  function finish() {
    if (fails.length) { console.error('FAIL ' + path.basename(file)); fails.forEach(f => console.error(' - ' + f)); process.exit(1); }
    console.log('PASS ' + path.basename(file) + ' (' + raw.length + ' bytes, envelope sha256 ' + packet.sha256 + ')');
  }
})().catch(e => { console.error('FAIL ' + e.message); process.exit(1); });
