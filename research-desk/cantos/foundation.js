/* Cantos foundation 0.1.0 | MIT. Thin bridge over existing owners.
   ResearchCore (research-desk/app.html, projected byte-exact) owns every journal,
   revision, dependency, review, freeze, packet and report decision.
   Compute (compute/engine.cjs, projected byte-exact) owns seat price arithmetic.
   This file joins them for one case, derives a read-only view, and never
   persists, fetches or executes anything. */
(function (root) {
'use strict';
const VERSION = '0.1.0';
const SEED_SCHEMA = 'cantos/seed@1';
const ECON_RECIPE = 'cantos/seat-economics@1';
const ROLES = ['source', 'measurement', 'price', 'economics', 'recommendation', 'context'];
const APP_SHA256_EXPECTED = '5951f7f3d994ec980d2958ae18246edc6dbe5b57db8d38e90c1c18956b96e470';

function createDesk(options) {
  const C = options.core, K = options.compute;
  if (!C || typeof C.put !== 'function' || C.SCHEMA !== 'second-run/research-desk@1') throw new Error('ResearchCore is required.');
  if (!K || typeof K.quote !== 'function') throw new Error('Compute engine is required.');
  const assert = C.assert;
  let seed = options.seed || null, seedText = null, ws = null, view = null, identity = null, subscribers = [];

  /* ---------- seed replay through the native journal ---------- */
  function checkSeed(s) {
    assert(s && s.schema === SEED_SCHEMA, 'Unsupported seed schema; expected ' + SEED_SCHEMA + '.');
    assert(typeof s.workspace_label === 'string' && s.workspace_label.trim(), 'Seed workspace_label required.');
    assert(s.case && typeof s.case.target === 'string', 'Seed case.target required.');
    assert(Array.isArray(s.records) && s.records.length > 0, 'Seed records required.');
    assert(typeof s.actor === 'string' && typeof s.at === 'string', 'Seed actor and at required.');
    for (const r of s.records) {
      assert(r && r.data && ROLES.includes(r.data.role), 'Seed record ' + (r && r.id) + ' needs data.role in ' + ROLES.join('|') + '.');
      if (r.data.relative_path !== undefined) assert(!/^(?:[A-Za-z]:|\\\\|\/)/.test(r.data.relative_path), 'relative_path must be repo-relative: ' + r.id);
    }
    assert(s.records.some(r => r.id === s.case.target && r.data.role === 'recommendation'), 'case.target must be a recommendation record.');
  }
  function pinLatest(s, deps) {
    return (deps || []).map(d => { const now = C.latest(s, d.id); assert(now, 'Dependency missing: ' + d.id); return { id: d.id, revision: now.revision }; });
  }
  function roleOf(r) { return r && r.data && r.data.role || null; }
  function findDep(s, record, role, pinned) {
    const hits = record.deps.map(d => pinned ? C.version(s, d.id, d.revision) : C.latest(s, d.id)).filter(x => x && roleOf(x) === role);
    assert(hits.length === 1, record.id + ' must pin exactly one ' + role + ' record.');
    return hits[0];
  }
  /* Economics: Compute.quote owns the money; the only join here is dividing the seat total by accepted work. */
  function deriveEconomics(s, record, pinned) {
    const inputs = record.data.inputs;
    assert(record.data.recipe === ECON_RECIPE && inputs && typeof inputs === 'object', record.id + ' needs recipe ' + ECON_RECIPE + ' and inputs.');
    const price = findDep(s, record, 'price', pinned), meas = findDep(s, record, 'measurement', pinned);
    assert(price.data.offer && typeof price.data.offer.rate === 'number', 'Price record needs data.offer accepted by Compute.quote.');
    const accepted = meas.data.metrics && meas.data.metrics.accepted;
    assert(Number.isInteger(accepted) && accepted > 0, 'Measurement needs integer metrics.accepted.');
    assert(inputs.accepted === accepted, 'economics inputs.accepted must equal the pinned measurement metrics.accepted (' + accepted + ').');
    const quote = K.quote(price.data.offer, { hours: inputs.hours, asOf: inputs.asOf, extraPerHour: inputs.extraPerHour || 0, fixedCost: inputs.fixedCost || 0 });
    return { engine: 'compute/engine.cjs@' + K.VERSION, quote, accepted, usd_per_1k_accepted: quote.total / accepted * 1000,
      formula: 'Compute.quote(offer,{hours,asOf}).total / measurement.metrics.accepted * 1000',
      scope: price.data.scope || 'own-seat quote at the pinned list rate; not an invoice', price_revision: price.revision, measurement_revision: meas.revision };
  }
  function verifyDerived(s, record) {
    if (roleOf(record) !== 'economics') return null;
    let result = null, verified = false, error = null;
    try { result = deriveEconomics(s, record, true); verified = C.canonical(result) === C.canonical(record.data.result); } catch (e) { error = e.message; }
    return { recipe: ECON_RECIPE, verified, result: record.data.result || null, recomputed: result, error, usd_per_1k_accepted: record.data.result ? record.data.result.usd_per_1k_accepted : null };
  }
  async function replay(s) {
    checkSeed(s);
    const w = C.empty(s.workspace_label);
    for (const input of s.records) {
      const st = C.state(w), r = C.clone(input);
      delete r.revision;
      r.deps = pinLatest(st, r.deps);
      if (roleOf(r) === 'economics') { assert(r.data.result === undefined, 'Seed supplies economics inputs, never results: ' + r.id); r.data.result = deriveEconomics(st, r, true); }
      await C.put(w, r, s.actor, s.at);
    }
    return w;
  }

  /* ---------- derived view ---------- */
  function closure(s, key, out) { out = out || {}; const r = C.latest(s, key); assert(r, 'Record missing: ' + key); if (out[key]) return out; out[key] = r; for (const d of r.deps) closure(s, d.id, out); return out; }
  function checkWorkspace(s) {
    for (const k of Object.keys(s.records)) for (const r of s.records[k]) {
      if (roleOf(r) === 'price') { assert(r.data.offer && typeof r.data.offer === 'object', 'Price record ' + k + ' v' + r.revision + ' has no offer.'); K.quote(r.data.offer, { hours: 1, asOf: r.data.offer.reviewedOn }); }
      if (roleOf(r) === 'economics') { const v = verifyDerived(s, r); assert(v.verified, 'Economics record ' + k + ' v' + r.revision + ' does not recompute through Compute: ' + (v.error || 'result mismatch')); }
    }
  }
  function isScenario(r) { return !!(r && r.data && r.data.scenario === true); }
  async function buildView(ws) {
    const s = C.state(ws), target = seed.case.target;
    const keys = Object.keys(s.records);
    const fps = {}; for (const k of keys) fps[k] = await C.fingerprint(s, k);
    const rec = C.latest(s, target); assert(rec, 'Case target missing from workspace: ' + target);
    const rs = await C.reviewState(s, target);
    const ds = C.dependencyState(s, target);
    const stalePins = b => b.some(x => /pinned v\d+, current v/.test(x));
    const stateOf = (r, d) => !d.current ? (stalePins(d.blockers) ? 'stale' : 'blocked') : isScenario(r) ? 'scenario' : 'current';
    const records = keys.map(k => {
      const r = C.latest(s, k), d = C.dependencyState(s, k);
      return { id: r.id, revision: r.revision, kind: r.kind, tier: r.tier, role: roleOf(r), title: r.title, summary: r.summary, disposition: r.disposition, scenario: isScenario(r),
        deps: r.deps.map(x => { const now = C.latest(s, x.id); return { id: x.id, revision: x.revision, current_revision: now ? now.revision : null, stale: !now || now.revision !== x.revision }; }),
        dependency: d, stale: !d.current, state: stateOf(r, d),
        source: (r.data.url || r.data.relative_path || r.data.sha256 || r.data.observed_on) ? { url: r.data.url || null, relative_path: r.data.relative_path || null, sha256: r.data.sha256 || null, observed_on: r.data.observed_on || null } : null,
        limitations: Array.isArray(r.data.limitations) ? r.data.limitations : [],
        metrics: r.data.metrics || null, offer: r.data.offer && typeof r.data.offer === 'object' ? C.clone(r.data.offer) : null, window: r.data.window ? C.clone(r.data.window) : null, identity: r.data.identity ? C.clone(r.data.identity) : null, grading: r.data.grading ? C.clone(r.data.grading) : null, billing: r.data.billing || null, scope: r.data.scope || null, url: r.data.url || null, derived: verifyDerived(s, r), data: C.clone(r.data),
        history: s.records[k].map(v => ({ revision: v.revision, at: eventOf('record', v.id, v.revision).at, actor: eventOf('record', v.id, v.revision).actor, tier: v.tier, scenario: isScenario(v) })) };
    });
    function eventOf(type, id, revision) { return ws.events.find(e => e.type === type && e.payload.id === id && e.payload.revision === revision) || { at: null, actor: null }; }
    const edges = []; for (const r of records) for (const d of r.deps) edges.push({ from: d.id, to: r.id, pinned_revision: d.revision, current_revision: d.current_revision, stale: d.stale });
    const deliveries = s.reports.map(r => { const seq = ws.events.find(e => e.hash === r.event_hash).seq; const snap = r.snapshot.records[r.target]; return { seq, at: r.at, reviewer: r.snapshot.review.reviewer, decision: r.snapshot.review.decision, target: r.target, revision: snap.revision, title: snap.title, summary: snap.summary, snapshot_hash: r.snapshot_hash, fingerprint: r.fingerprint, current: r.fingerprint === fps[r.target], scenario: isScenario(snap) }; });
    const reviews = s.reviews.map(r => ({ seq: ws.events.find(e => e.hash === r.event_hash).seq, at: r.at, reviewer: r.reviewer, decision: r.decision, rationale: r.rationale, target: r.target, fingerprint: r.fingerprint, current: r.fingerprint === fps[r.target] }));
    const timeline = ws.events.map(e => { const p = e.payload; return { seq: e.seq, at: e.at, type: e.type, actor: e.actor, target: e.type === 'record' ? p.id : p.target, revision: e.type === 'record' ? p.revision : (C.version(s, p.target, (p.snapshot && p.snapshot.records[p.target] || {}).revision) || C.latest(s, p.target)).revision, kind: e.type === 'record' ? p.kind : e.type, decision: p.decision || null, summary: e.type === 'record' ? p.title + (p.revision > 1 ? ' (revision ' + p.revision + ')' : '') : e.type === 'review' ? 'Review ' + p.decision + ' by ' + e.actor : 'Delivery frozen: ' + (p.snapshot.records[p.target] || {}).title, scenario: e.type === 'record' ? isScenario(p) : isScenario((p.snapshot && p.snapshot.records[p.target]) || null) }; });
    const priceRecs = records.filter(r => r.role === 'price');
    const price = priceRecs[0] || null, priceBase = price ? s.records[price.id][0] : null;
    const scenario = price && price.offer && priceBase.data.offer ? { active: price.scenario, base_rate: priceBase.data.offer.rate, rate: price.offer.rate, unit: 'USD per GPU-hour', note: price.data.scenario_note || null, since_seq: price.scenario ? eventSeq('record', price.id, price.revision) : null, price_id: price.id } : { active: false, base_rate: null, rate: null, unit: 'USD per GPU-hour', note: null, since_seq: null, price_id: null };
    function eventSeq(type, id, revision) { const e = ws.events.find(x => x.type === type && x.payload.id === id && x.payload.revision === revision); return e ? e.seq : null; }
    const successors = ws.events.filter(e => e.type === 'record' && e.payload.revision > 1);
    const since = successors.length ? { id: successors.at(-1).payload.id, revision: successors.at(-1).payload.revision, seq: successors.at(-1).seq } : null;
    const stale = { ids: records.filter(r => r.stale).map(r => r.id), since, impact: since ? C.impact(s, since.id) : [] };
    const status = !ds.current ? (stalePins(ds.blockers) ? 'stale' : 'blocked') : deliveries.some(d => d.current) ? 'issued' : rs.ready ? 'reviewed' : 'awaiting-review';
    return { case: C.clone(seed.case), workspace: { label: ws.label, event_count: ws.events.length },
      recommendation: { id: rec.id, revision: rec.revision, title: rec.title, summary: rec.summary, conditions: rec.data.conditions || [], holds_unless: rec.data.holds_unless || [], tier: rec.tier, disposition: rec.disposition, scenario: isScenario(rec), dependency: ds, review: rs, status },
      records, path: { nodes: records.map(r => ({ id: r.id, role: r.role, label: r.title, revision: r.revision, state: r.state })), edges },
      deliveries, reviews, timeline, scenario, stale, boundaries: C.clone(seed.boundaries || {}), identity: C.clone(identity) };
  }
  function notify() { for (const fn of subscribers) { try { fn(view); } catch (e) { /* subscriber errors never touch state */ } } }
  async function refresh() { view = await buildView(ws); notify(); return view; }

  /* ---------- guarded mutation: clone, apply, verify, swap ---------- */
  async function mutate(fn) {
    const draft = C.clone(ws);
    try { const event = await fn(draft, C.state(draft)); const candidate = await buildView(draft); /* candidate view must build before anything is committed */ ws = draft; view = candidate; notify(); return { ok: true, event: C.clone(event), view }; }
    catch (e) { return { ok: false, error: e.message || String(e), view }; }
  }
  function latestByRole(s, role) { const hits = Object.keys(s.records).map(k => C.latest(s, k)).filter(r => roleOf(r) === role); assert(hits.length === 1, 'Expected exactly one ' + role + ' record; found ' + hits.length + '.'); return hits[0]; }
  function fill(template, values) { return String(template).replace(/\{(\w+)\}/g, (m, k) => values[k] !== undefined ? String(values[k]) : m); }
  function money(n, d) { return typeof n === 'number' && Number.isFinite(n) ? '$' + n.toFixed(d) : 'unavailable'; }

  const desk = {
    VERSION,
    async ready(input) {
      if (input !== undefined) seed = C.parse(typeof input === 'string' ? input : JSON.stringify(input)); /* re-parse in the core's realm */
      if (!seed && typeof document !== 'undefined') { const el = document.getElementById('cantos-seed'); assert(el, 'Seed element #cantos-seed missing.'); seedText = el.textContent; seed = C.parse(seedText); }
      assert(seed, 'Seed required.');
      if (!seedText) seedText = C.canonical(seed);
      ws = await replay(seed);
      identity = { foundation_version: VERSION, research_core_version: C.VERSION, compute_version: K.VERSION, app_sha256_expected: APP_SHA256_EXPECTED, seed_sha256: await C.hash(seedText), seed_status: seed.provisional ? 'provisional' : 'sol', research_core_sha256: null, compute_sha256: null, build: null, core_matches_build: null };
      if (typeof document !== 'undefined') {
        const core = document.getElementById('research-core'), comp = document.getElementById('compute-engine'), build = document.getElementById('cantos-build');
        if (core) identity.research_core_sha256 = await C.hash(core.textContent);
        if (comp) identity.compute_sha256 = await C.hash(comp.textContent);
        if (build) { try { identity.build = C.parse(build.textContent); identity.core_matches_build = identity.build.research_core_sha256 === identity.research_core_sha256 && identity.build.compute_sha256 === identity.compute_sha256; identity.seed_matches_build = identity.build.seed_sha256 === identity.seed_sha256; } catch (e) { identity.build = null; } }
      } else if (options.identity) Object.assign(identity, options.identity);
      return refresh();
    },
    view() { assert(view, 'Call ready() first.'); return view; },
    identity() { return C.clone(identity); },
    subscribe(fn) { subscribers.push(fn); return () => { subscribers = subscribers.filter(f => f !== fn); }; },
    workspace() { return C.clone(ws); },
    review(p) { return mutate(w => C.review(w, p.target || seed.case.target, p.decision, p.rationale, p.reviewer)); },
    freeze(p) { return mutate(w => C.freeze(w, p.target || seed.case.target, p.reviewer)); },
    priceScenario(p) { return mutate(async (w, s) => {
      const price = latestByRole(s, 'price'); const rate = p.rate;
      assert(typeof rate === 'number' && Number.isFinite(rate) && rate >= 0, 'Scenario rate must be a finite nonnegative number.');
      assert(price.data.offer && typeof price.data.offer === 'object', 'Price record has no offer.'); assert(price.data.offer.rate !== rate, 'The current price record already carries ' + money(rate, 2) + ' per GPU-hour.');
      const base = s.records[price.id][0];
      const next = { ...C.clone(price), tier: 'proposal', disposition: 'observed',
        summary: 'SCENARIO, not a supply refresh: ' + money(rate, 2) + ' per GPU-hour assumed in place of the observed ' + money(base.data.offer.rate, 2) + ' (reviewed ' + base.data.offer.reviewedOn + '). ' + (p.note ? String(p.note).slice(0, 2000) : 'No note supplied.'),
        data: { ...C.clone(price.data), offer: { ...C.clone(price.data.offer), rate }, scenario: true, scenario_note: p.note ? String(p.note).slice(0, 2000) : null, scenario_of: { revision: base.revision, rate: base.data.offer.rate, reviewedOn: base.data.offer.reviewedOn } } };
      delete next.revision;
      return C.put(w, next, p.actor || 'Local operator');
    }); },
    revise(p) { return mutate((w, s) => {
      const prev = C.latest(s, p.id); assert(prev, 'Record missing: ' + p.id);
      assert(roleOf(prev) !== 'measurement', 'Measured results are not editable here; admit new evidence as a new record instead.');
      assert(roleOf(prev) !== 'economics', 'Economics records are recomputed through recompute(), not edited.');
      const patch = p.patch || {};
      const next = { ...C.clone(prev), ...C.clone(patch), id: prev.id, kind: prev.kind, data: { ...C.clone(prev.data), ...C.clone(patch.data || {}), role: roleOf(prev) } };
      if (p.tier) next.tier = p.tier; delete next.revision; next.deps = pinLatest(s, next.deps);
      if (roleOf(prev) === 'price') { assert(next.data.offer && typeof next.data.offer === 'object', 'A price record needs data.offer.'); K.quote(next.data.offer, { hours: 1, asOf: next.data.offer.reviewedOn }); }
      return C.put(w, next, p.actor || 'Local operator');
    }); },
    recompute(p) { return mutate(async (w, s) => {
      const target = seed.case.target, rec = C.latest(s, target), ds = C.dependencyState(s, target);
      assert(!ds.current, 'Nothing is stale: the recommendation already pins the current inputs.');
      const actor = p.actor || 'Local operator'; let econ = null, lastEvent = null;
      for (const d of rec.deps) {
        const e = C.latest(s, d.id); if (roleOf(e) !== 'economics' || C.dependencyState(s, e.id).current) continue;
        const next = { ...C.clone(e), data: { ...C.clone(e.data) } }; delete next.revision; delete next.data.result;
        next.deps = pinLatest(s, e.deps);
        const st = C.state(w); next.data.result = deriveEconomics(st, next, true);
        const price = findDep(st, next, 'price', true); next.data.scenario = isScenario(price); next.tier = isScenario(price) ? 'proposal' : price.tier;
        next.summary = (next.data.scenario ? 'SCENARIO recomputation: ' : 'Recomputed: ') + money(next.data.result.usd_per_1k_accepted, 2) + ' per 1,000 accepted requests at ' + money(price.data.offer.rate, 2) + ' per GPU-hour for ' + next.data.inputs.hours + ' h of one seat; measured acceptance unchanged (' + next.data.result.accepted + ').';
        lastEvent = await C.put(w, next, actor); econ = C.latest(C.state(w), e.id); s = C.state(w);
      }
      const nextRec = { ...C.clone(rec), disposition: 'draft', data: { ...C.clone(rec.data) } }; delete nextRec.revision;
      nextRec.deps = pinLatest(s, rec.deps);
      const econNow = econ || findDep(s, nextRec, 'economics', true);
      const priceNow = findDep(s, econNow, 'price', true);
      nextRec.data.scenario = isScenario(econNow); nextRec.tier = isScenario(econNow) ? 'proposal' : rec.tier === 'proposal' ? econNow.tier : rec.tier;
      const values = { usd_per_1k_accepted: money(econNow.data.result.usd_per_1k_accepted, 2), rate: money(priceNow.data.offer.rate, 2), accepted: econNow.data.result.accepted, hours: econNow.data.inputs.hours };
      nextRec.summary = p.summary ? String(p.summary).slice(0, 30000) : (rec.data.template ? fill(rec.data.template, values) : 'Successor draft: ' + values.usd_per_1k_accepted + ' per 1,000 accepted at ' + values.rate + ' per GPU-hour. Review required before delivery.');
      if (nextRec.data.scenario) nextRec.summary = 'SCENARIO (assumed price, not observed supply): ' + nextRec.summary;
      const ev = await C.put(w, nextRec, actor);
      return ev || lastEvent;
    }); },
    async exportPacket() { try { const packet = await C.pack(ws); const text = JSON.stringify(packet, null, 1); return { ok: true, name: 'cantos-packet-' + packet.sha256.slice(0, 12) + '.json', text, sha256: packet.sha256 }; } catch (e) { return { ok: false, error: e.message }; } },
    async importPacket(text) {
      try { const packet = C.parse(text); const clean = await C.verifyPacket(packet); const s = C.state(clean);
        const rec = C.latest(s, seed.case.target); assert(rec && roleOf(rec) === 'recommendation', 'Packet verified but does not contain this case (' + seed.case.target + ').');
        checkWorkspace(s);
        const candidate = await buildView(clean); ws = clean; view = candidate; notify(); return { ok: true, view, sha256: packet.sha256, events: clean.events.length }; }
      catch (e) { return { ok: false, error: e.message || String(e), view }; }
    },
    async restoreSeed() { try { const w = await replay(seed); const candidate = await buildView(w); ws = w; view = candidate; notify(); return { ok: true, view }; } catch (e) { return { ok: false, error: e.message, view }; } },
    reportHTML(which) {
      const s = C.state(ws);
      if (which === 'draft' || which === undefined) { const target = seed.case.target, ds = C.dependencyState(s, target); const rev = [...s.reviews].reverse().find(r => r.target === target) || null;
        const snapshot = { schema: 'second-run/research-report@1', workspace: ws.label, target, records: closure(s, target), review: null, evidence_boundary: 'Draft view of the current dependency closure; not a frozen delivery.' };
        return C.reportHTML(snapshot, 'DRAFT / ' + (ds.current ? 'AWAITING REVIEW' : ds.blockers.join('; ')), null); }
      const e = ws.events.find(x => x.seq === which && x.type === 'freeze'); assert(e, 'No frozen delivery at journal seq ' + which + '.');
      return C.reportHTML(e.payload.snapshot, 'FROZEN / REVIEWED AT ' + e.at + ' / CHECK CURRENT DESK FOR LATER REVISIONS', e.payload.snapshot_hash);
    }
  };
  // Serialize existing asynchronous entry points so completed edits cannot be lost.
  let pending = Promise.resolve();
  for (const name of ['ready','review','freeze','priceScenario','revise','recompute','importPacket','restoreSeed','exportPacket']) {
    const invoke = desk[name].bind(desk);
    desk[name] = (...args) => {
      const task = pending.then(() => invoke(...args));
      pending = task.then(() => undefined, () => undefined);
      return task;
    };
  }
  return desk;
}

const api = { VERSION, SEED_SCHEMA, ECON_RECIPE, ROLES, APP_SHA256_EXPECTED, createDesk };
if (typeof module !== 'undefined' && module.exports) module.exports = api;
root.CantosFoundation = api;
if (root.ResearchCore && root.Compute && typeof document !== 'undefined') root.CantosDesk = createDesk({ core: root.ResearchCore, compute: root.Compute });
})(typeof globalThis !== 'undefined' ? globalThis : this);
