'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { Store } = require('../lib/store.cjs');
const { Jobs } = require('../lib/jobs.cjs');
const local = require('../lib/adapters/local.cjs');
const { HotAisle, maskEmail } = require('../lib/adapters/hotaisle.cjs');
const { createServer } = require('../lib/server.cjs');
const mcp = require('../lib/mcp.cjs');

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'wl-if-'));

test('Hot Aisle adapter reads allocations, state, balance and retrieved prices; rejects a bad token', async () => {
  const api = await local.startFakeApi();
  try {
    const env = await new HotAisle({ token: api.token, baseUrl: api.baseUrl }).inspect({ team: 'demo-team' });
    assert.equal(env.adapter, 'hotaisle');
    assert.equal(env.allocations.length, 1);
    assert.equal(env.allocations[0].gpus.count, 1);
    assert.equal(env.allocations[0].gpus.model, 'AMD MI300X');
    assert.equal(env.allocations[0].state, 'running');
    assert.equal(env.allocations[0].price.gpu_hour_usd, 2.99);
    assert.equal(env.allocations[0].price.retrieved, true);
    assert.equal(env.balance.available_usd, 482.5);
    assert.equal(env.user.email, 'd***@example.invalid');
    assert.deepEqual(env.unknown, []);
    await assert.rejects(() => new HotAisle({ token: 'wrong', baseUrl: api.baseUrl }).inspect(), /refused the token/);
  } finally { await api.close(); }
  assert.equal(maskEmail('someone@host.tld'), 's***@host.tld');
});

test('localhost server: status, plan, approve, start, events, record views, origin policy', async () => {
  const store = new Store(tmp());
  const fakeApi = await local.startFakeApi();
  const server = createServer({ store, jobs: new Jobs(store), fakeApi });
  const base = await server.listenOn(0);
  const H = { 'X-Workload-Client': 'page', 'Content-Type': 'application/json' };
  try {
    const status = await (await fetch(base + '/api/status')).json();
    assert.equal(status.runner, 'connected');
    assert.equal(status.engine.version, '2.0.0');
    const page = await fetch(base + '/');
    assert.equal(page.status, 200);
    assert.match(await page.text(), /<script id="report-engine">/);
    assert.equal((await fetch(base + '/runner/lib/store.cjs')).status, 404, 'runner source is not served');
    const env = await (await fetch(base + '/api/environment?adapter=local')).json();
    assert.equal(env.allocations[0].name, 'mi300x-dev-01');
    const input = await (await fetch(base + '/api/demo/plan?repeats=1&concurrency=1')).json();
    assert.equal((await fetch(base + '/api/jobs', { method: 'POST', body: JSON.stringify(input) })).status, 403, 'POST without client header refused');
    assert.equal((await fetch(base + '/api/jobs', { method: 'POST', headers: { ...H, Origin: 'https://evil.example' }, body: JSON.stringify(input) })).status, 403, 'foreign origin refused');
    const job = await (await fetch(base + '/api/jobs', { method: 'POST', headers: { ...H, Origin: base }, body: JSON.stringify(input) })).json();
    assert.equal(job.state, 'planned');
    assert.equal((await (await fetch(base + '/api/jobs/' + job.id + '/approve', { method: 'POST', headers: H, body: JSON.stringify({ plan_sha256: job.plan_sha256 }) })).json()).state, 'approved');
    const events = [];
    const es = await fetch(base + '/api/jobs/' + job.id + '/events');
    const reader = es.body.getReader();
    const pump = (async () => { const dec = new TextDecoder(); let buf = ''; for (;;) { const { value, done } = await reader.read(); if (done) break; buf += dec.decode(value); events.push(...buf.split('\n\n').filter(Boolean).map(x => x.split('\n')[0])); buf = ''; } })();
    assert.equal((await fetch(base + '/api/jobs/' + job.id + '/start', { method: 'POST', headers: H, body: '{}' })).status, 202);
    for (let i = 0; i < 100; i++) { const j = await (await fetch(base + '/api/jobs/' + job.id)).json(); if (j.state === 'completed') break; await new Promise(r => setTimeout(r, 100)); }
    const done = await (await fetch(base + '/api/jobs/' + job.id)).json();
    assert.equal(done.state, 'completed');
    reader.cancel(); await pump.catch(() => {});
    assert.ok(events.some(e => e === 'event: trial'), 'trial events streamed');
    const recs = await (await fetch(base + '/api/records')).json();
    assert.equal(recs[0].id, done.record_id);
    assert.equal((await (await fetch(base + '/api/records/' + done.record_id + '/verify')).json()).verified, true);
    const head = await (await fetch(base + '/api/records/' + done.record_id + '/headline')).json();
    assert.equal(head.generated, true);
    assert.equal(head.status, 'demonstration');
    assert.match(await (await fetch(base + '/api/records/' + done.record_id + '/report.html')).text(), /SYNTHETIC DEMONSTRATION/);
    const reval = await (await fetch(base + '/api/records/' + done.record_id + '/revalidate', { method: 'POST', headers: H, body: JSON.stringify({ price: { rate: 1.99 } }) })).json();
    assert.equal(reval.summary.requires_measurement, 0);
    const pub = await (await fetch(base + '/api/records/' + done.record_id + '/publish', { method: 'POST', headers: H, body: '{}' })).json();
    assert.ok(fs.existsSync(path.join(pub.published, 'headline.json')));
    assert.equal(JSON.parse(fs.readFileSync(path.join(pub.published, 'headline.json'), 'utf8')).status, 'demonstration');
  } finally { server.close(); await fakeApi.close(); }
});

test('MCP server: initialize, list, prepare/start/status/result/revalidate over stdio', async () => {
  const home = tmp();
  const child = spawn(process.execPath, [path.join(__dirname, '..', 'bin', 'workload.cjs'), 'mcp'], { env: { ...process.env, WORKLOAD_HOME: home }, stdio: ['pipe', 'pipe', 'pipe'] });
  const pending = new Map(); let buf = ''; let nextId = 1;
  child.stdout.on('data', d => { buf += d; let i; while ((i = buf.indexOf('\n')) >= 0) { const line = buf.slice(0, i); buf = buf.slice(i + 1); if (!line.trim()) continue; const m = JSON.parse(line); if (m.id !== undefined && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } } });
  const rpc = (method, params) => new Promise(r => { const id = nextId++; pending.set(id, r); child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n'); });
  const call = async (name, a) => { const m = await rpc('tools/call', { name, arguments: a }); assert.equal(m.result.isError, false, JSON.stringify(m.result.content)); return m.result.structuredContent; };
  try {
    const init = await rpc('initialize', { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'test', version: '0' } });
    assert.equal(init.result.protocolVersion, '2025-06-18');
    assert.ok(init.result.capabilities.tools);
    child.stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) + '\n');
    const list = await rpc('tools/list', {});
    assert.equal(list.result.tools.length, 8);
    assert.equal(list.result.tools.find(t => t.name === 'start_evaluation')._meta.ui.resourceUri, 'ui://hot-aisle/evaluation');
    const res = await rpc('resources/read', { uri: 'ui://hot-aisle/evaluation' });
    assert.equal(res.result.contents[0].mimeType, 'text/html;profile=mcp-app');
    const env = await call('inspect_environment', { adapter: 'local' });
    assert.equal(env.allocations[0].gpus.model, 'AMD MI300X');
    const prep = await call('prepare_evaluation', { demo: true, repeats: 1, concurrency: [1] });
    assert.match(prep.plan_sha256, /^[a-f0-9]{64}$/);
    const bad = await rpc('tools/call', { name: 'start_evaluation', arguments: { job_id: prep.job_id, approved_plan_sha256: 'f'.repeat(64) } });
    assert.equal(bad.result.isError, true, 'wrong approval hash cannot start');
    const started = await call('start_evaluation', { job_id: prep.job_id, approved_plan_sha256: prep.plan_sha256, approved_by: 'test' });
    assert.equal(started.state, 'running');
    let st; for (let i = 0; i < 100; i++) { st = await call('evaluation_status', { job_id: prep.job_id }); if (st.state === 'completed') break; await new Promise(r => setTimeout(r, 100)); }
    assert.equal(st.state, 'completed');
    const result = await call('evaluation_result', { job_id: prep.job_id });
    assert.equal(result.verification.verified, true);
    assert.equal(result.headline.generated, true);
    const reval = await call('revalidate', { record_id: result.record_id, change: { price: { rate: 3.39 } } });
    assert.equal(reval.summary.requires_measurement, 0);
    const unknown = await rpc('tools/call', { name: 'nope', arguments: {} });
    assert.equal(unknown.error.code, -32602);
  } finally { child.stdin.end(); child.kill(); }
});
