'use strict';
/* Native test for the Cantos foundation. Loads the projected owners (never app.html's UI),
   replays the seed, and walks the primary journey twice: once in this process, once in a
   fresh core instance from the exported packet. Exit 1 on any failure. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const here = __dirname, cantos = path.resolve(here, '..'), root = path.resolve(cantos, '../..');
const sha = t => crypto.createHash('sha256').update(t).digest('hex');
let failures = 0, n = 0;
function check(ok, label, detail) { n++; console.log((ok ? 'ok   ' : 'FAIL ') + n + ' ' + label + (ok || detail === undefined ? '' : ' :: ' + detail)); if (!ok) failures++; }

function freshCore() {
  /* A second, independent ResearchCore instance evaluated from the projected file in this realm
     (a separate vm realm would make plain-object checks fail across realms; a real fresh browser
     context is exercised by the browser tests). */
  const text = fs.readFileSync(path.join(cantos, 'native/research-core.js'), 'utf8');
  const mod = { exports: {} };
  new Function('module', 'require', text + String.fromCharCode(10) + 'return module.exports;')(mod, require);
  return mod.exports;
}

(async () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(cantos, 'native/MANIFEST.json'), 'utf8'));
  const app = fs.readFileSync(path.join(root, 'research-desk/app.html'), 'utf8');
  const inApp = [...app.matchAll(/<script id="research-core">([\s\S]*?)<\/script>/g)];
  check(inApp.length === 1 && sha(inApp[0][1]) === manifest.artifacts['research-core.js'].projected_sha256, 'projected research-core is byte-identical to app.html script');
  check(sha(fs.readFileSync(path.join(root, 'compute/engine.cjs'), 'utf8')) === manifest.artifacts['compute-engine.js'].projected_sha256, 'projected compute-engine is byte-identical to compute/engine.cjs');
  check(sha(fs.readFileSync(path.join(root, 'research-desk/app.html'))) === manifest.app_sha256, 'app.html hash frozen');

  const C = require(path.join(cantos, 'native/research-core.js'));
  const K = require(path.join(cantos, 'native/compute-engine.js'));
  const F = require(path.join(cantos, 'foundation.js'));
  const seedPath = fs.existsSync(path.join(cantos, 'data/seed.json')) ? path.join(cantos, 'data/seed.json') : path.join(here, 'provisional-seed.json');
  const seed = JSON.parse(fs.readFileSync(seedPath, 'utf8'));
  console.log('seed ' + path.relative(root, seedPath).replace(/\\/g, '/') + (seed.provisional ? ' (PROVISIONAL)' : ''));

  const desk = F.createDesk({ core: C, compute: K });
  const v0 = await desk.ready(seed);
  const desk2 = F.createDesk({ core: C, compute: K }); await desk2.ready(seed);
  const packA = await desk.exportPacket(), packB = await desk2.exportPacket();
  check(packA.ok && packA.sha256 === packB.sha256, 'seed replay is deterministic', packA.sha256 + ' vs ' + packB.sha256);
  const target = seed.case.target;
  const econ0 = v0.records.find(r => r.role === 'economics'), price0 = v0.records.find(r => r.role === 'price');
  const meas0 = v0.records.find(r => r.role === 'measurement' && econ0.deps.some(d => d.id === r.id));
  check(econ0 && econ0.derived && econ0.derived.verified === true, 'economics recomputes through Compute.quote', econ0 && econ0.derived && econ0.derived.error);
  const expectTotal = K.quote(price0.offer, { hours: econ0.data.inputs.hours, asOf: econ0.data.inputs.asOf }).total;
  check(Math.abs(econ0.derived.result.usd_per_1k_accepted - expectTotal / meas0.metrics.accepted * 1000) < 1e-9, 'usd per 1k accepted equals Compute total / accepted * 1000', econ0.derived.result.usd_per_1k_accepted);
  console.log('     economics: ' + econ0.derived.result.usd_per_1k_accepted.toFixed(4) + ' USD per 1k accepted at ' + price0.offer.rate + '/GPU-h for ' + econ0.data.inputs.hours + ' h, accepted ' + meas0.metrics.accepted);
  check(v0.recommendation.status === 'awaiting-review' && v0.recommendation.dependency.current, 'seed recommendation is current and awaiting review', v0.recommendation.status);
  check(v0.identity.seed_status === (seed.provisional ? 'provisional' : 'sol'), 'identity reports seed status');

  const measBefore = C.canonical(desk.workspace().events.filter(e => e.type === 'record' && e.payload.id === meas0.id));
  const bad = await desk.freeze({ reviewer: 'Tester' });
  check(!bad.ok && /review/i.test(bad.error), 'freeze without review refuses natively', bad.error);
  const held = await desk.review({ decision: 'hold', rationale: 'Holding until the own-window basis is checked.', reviewer: 'Tester' });
  check(held.ok && held.view.recommendation.status === 'awaiting-review', 'hold review recorded but does not make the target ready');
  const acc = await desk.review({ decision: 'accept', rationale: 'Pinned evidence, limitations and own-window basis checked.', reviewer: 'Tester' });
  check(acc.ok && acc.view.recommendation.status === 'reviewed', 'accept review binds the current closure', acc.error);
  const fr1 = await desk.freeze({ reviewer: 'Tester' });
  check(fr1.ok && fr1.view.deliveries.length === 1 && fr1.view.recommendation.status === 'issued', 'delivery 1 frozen', fr1.error);
  const d1 = fr1.view.deliveries[0];
  const html1 = desk.reportHTML(d1.seq);
  check(typeof html1 === 'string' && html1.includes(d1.snapshot_hash) && html1.includes('FROZEN'), 'delivery 1 report renders through ResearchCore.reportHTML');

  const same = await desk.priceScenario({ rate: price0.offer.rate, actor: 'Tester' });
  check(!same.ok, 'scenario with the unchanged rate refuses');
  const sc = await desk.priceScenario({ rate: 3.39, note: 'Test scenario', actor: 'Tester' });
  check(sc.ok && sc.view.scenario.active && sc.view.scenario.rate === 3.39 && sc.view.scenario.base_rate === price0.offer.rate, 'price scenario recorded as proposal successor', sc.error);
  const pr = sc.view.records.find(r => r.role === 'price');
  check(pr.tier === 'proposal' && pr.scenario === true && pr.revision === 2, 'scenario price record is tier proposal, revision 2');
  check(sc.view.recommendation.status === 'stale', 'recommendation is stale after the scenario', sc.view.recommendation.status);
  const blockers = sc.view.recommendation.dependency.blockers.join(' | ');
  check(blockers.includes(price0.id + ': pinned v1, current v2'), 'stale blocker names the exact moved pin', blockers);
  check(sc.view.stale.ids.includes(econ0.id) && sc.view.stale.ids.includes(target) && !sc.view.stale.ids.includes(meas0.id), 'stale set is economics + recommendation, not the measurement');
  check(sc.view.deliveries[0].current === false, 'delivery 1 is marked no longer current');
  const measAfter = C.canonical(desk.workspace().events.filter(e => e.type === 'record' && e.payload.id === meas0.id));
  check(measBefore === measAfter, 'measurement record journal bytes unchanged by the scenario');
  const noEdit = await desk.revise({ id: meas0.id, patch: { summary: 'x' }, actor: 'Tester' });
  check(!noEdit.ok, 'measurement cannot be revised through the bridge');
  const shaBefore = (await desk.exportPacket()).sha256;
  const badRevise = await desk.revise({ id: price0.id, patch: { data: { offer: null } }, actor: 'Tester' });
  check(!badRevise.ok && (await desk.exportPacket()).sha256 === shaBefore, 'rejected revision leaves the workspace byte-identical', badRevise.error);
  const rc = await desk.recompute({ actor: 'Tester' });
  check(rc.ok, 'recompute forms successors natively', rc.error);
  const econ1 = rc.view.records.find(r => r.role === 'economics'), rec1 = rc.view.recommendation;
  check(econ1.revision === 2 && econ1.derived.verified && econ1.tier === 'proposal' && econ1.scenario, 'economics v2 verified, tier proposal, scenario');
  const expect2 = K.quote({ ...price0.offer, rate: 3.39 }, { hours: econ0.data.inputs.hours, asOf: econ0.data.inputs.asOf }).total / meas0.metrics.accepted * 1000;
  check(Math.abs(econ1.derived.result.usd_per_1k_accepted - expect2) < 1e-9, 'economics v2 uses the scenario rate through Compute', econ1.derived.result.usd_per_1k_accepted);
  check(econ1.derived.result.accepted === meas0.metrics.accepted, 'accepted count unchanged in v2');
  check(rec1.revision === 2 && rec1.status === 'awaiting-review' && rec1.scenario && /SCENARIO/.test(rec1.summary), 'recommendation v2 drafted, awaiting a new review', rec1.status);
  check(rec1.dependency.current, 'recommendation v2 pins are current');
  const fr2bad = await desk.freeze({ reviewer: 'Tester' });
  check(!fr2bad.ok, 'freeze of v2 refuses until reviewed again');
  const acc2 = await desk.review({ decision: 'accept', rationale: 'Scenario successor checked; still a scenario.', reviewer: 'Second reviewer' });
  const fr2 = await desk.freeze({ reviewer: 'Second reviewer' });
  check(acc2.ok && fr2.ok && fr2.view.deliveries.length === 2, 'delivery 2 frozen; delivery 1 preserved', fr2.error);
  check(fr2.view.deliveries[0].snapshot_hash === d1.snapshot_hash && fr2.view.deliveries[1].snapshot_hash !== d1.snapshot_hash, 'both snapshot hashes retained and distinct');
  check(fr2.view.deliveries[1].scenario === true && fr2.view.deliveries[0].scenario === false, 'delivery 2 labelled scenario, delivery 1 not');
  const noop = await desk.recompute({ actor: 'Tester' });
  check(!noop.ok, 'recompute with nothing stale refuses');
  check(fr2.view.timeline.length === desk.workspace().events.length && fr2.view.path.edges.some(e => e.from === price0.id && e.to === econ0.id && e.stale === false), 'timeline covers every journal event; path edges current after recompute');

  const exp = await desk.exportPacket();
  check(exp.ok && exp.name.startsWith('cantos-packet-'), 'export packet');
  const C2 = freshCore();
  const clean = await C2.verifyPacket(C2.parse(exp.text));
  check(clean.events.length === desk.workspace().events.length, 'fresh core instance verifies the exported packet by replay');
  const desk3 = F.createDesk({ core: C2, compute: K }); await desk3.ready(seed);
  const imp = await desk3.importPacket(exp.text);
  check(imp.ok && imp.view.deliveries.length === 2 && imp.view.recommendation.revision === 2, 'independent desk restores the packet with both deliveries', imp.error);
  const before = (await desk3.exportPacket()).sha256;
  const tampered = JSON.parse(exp.text); tampered.workspace.events[1].payload.summary = 'altered';
  const bad1 = await desk3.importPacket(JSON.stringify(tampered));
  const bad2 = await desk3.importPacket('{not json');
  const bad3 = await desk3.importPacket(JSON.stringify({ schema: 'second-run/research-packet@1', workspace: { schema: 'x' } }));
  check(!bad1.ok && !bad2.ok && !bad3.ok, 'tampered, malformed and foreign packets refuse', [bad1.error, bad2.error, bad3.error].join(' / '));
  check((await desk3.exportPacket()).sha256 === before, 'current work intact after refused imports');
  const rs = await desk3.restoreSeed();
  check(rs.ok && rs.view.deliveries.length === 0 && rs.view.workspace.event_count === seed.records.length, 'restoreSeed returns to the seeded workspace');
  const draft = desk3.reportHTML('draft');
  check(typeof draft === 'string' && draft.includes('DRAFT'), 'draft report renders');

  console.log((failures ? 'FAILED ' : 'PASSED ') + (n - failures) + '/' + n);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error('FAIL uncaught: ' + (e.stack || e.message)); process.exit(1); });
