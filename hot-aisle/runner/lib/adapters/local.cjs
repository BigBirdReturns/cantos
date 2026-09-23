'use strict';
/* Local integration environment. A fake Hot Aisle API with the subset of endpoints the
   adapter reads, plus a target that runs the fake benchmark on this machine. It lets
   the whole journey (inspect, plan, approve, run, cancel, reconnect, revalidate) be
   exercised end to end before any token or GPU is involved. Everything it yields is
   marked synthetic. */
const http = require('node:http');
const path = require('node:path');

const FAKE_TOKEN = 'local-demo-token';

const fixtures = {
  user: { user: { name: 'Demo Operator', email: 'demo@example.invalid', created: '2026-01-01T00:00:00Z' }, teams: [{ handle: 'demo-team', name: 'Demo team', roles: ['owner'], effective_roles: ['owner', 'operator'] }] },
  vms: [{ deployment_id: 'dep-mi300x-01', name: 'mi300x-dev-01', description: 'Demo 1x MI300X VM', ip_address: '127.0.0.1', ssh_access: { dns_name: 'localhost', ip_address: '127.0.0.1', port: 22 }, cpu_cores: 24, ram_capacity: 240 * 1024 ** 3, disk_capacity: 2 * 1024 ** 4, gpus: [{ count: 1, manufacturer: 'AMD', model: 'MI300X' }] }],
  types: [
    { Quantity: 3, MinimumReservationMinutes: 1, OnDemandPrice: 299, Specs: { gpus: [{ count: 1, manufacturer: 'AMD', model: 'MI300X' }] } },
    { Quantity: 1, MinimumReservationMinutes: 1, OnDemandPrice: 598, Specs: { gpus: [{ count: 2, manufacturer: 'AMD', model: 'MI300X' }] } },
    { Quantity: 0, MinimumReservationMinutes: 1, OnDemandPrice: 1196, Specs: { gpus: [{ count: 4, manufacturer: 'AMD', model: 'MI300X' }] } },
  ],
  balance: { available_balance: 48250, hourly_rate: 299, estimated_runout_time: '2026-09-29T00:00:00Z', virtual_machine_count: 1, bare_metal_server_count: 0 },
  state: { host: 'demo-host-01', state: 'running' },
};

function startFakeApi({ token = FAKE_TOKEN } = {}) {
  const server = http.createServer((req, res) => {
    const send = (code, body) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)); };
    if (req.headers.authorization !== 'Token ' + token) return send(401, { detail: 'Invalid token.' });
    const p = req.url.replace(/\?.*$/, '');
    if (p === '/api/user/') return send(200, fixtures.user);
    if (p === '/api/teams/') return send(200, fixtures.user.teams);
    if (p === '/api/teams/demo-team/virtual_machines/') return send(200, fixtures.vms);
    if (p === '/api/teams/demo-team/virtual_machines/available/') return send(200, fixtures.types);
    if (p === '/api/teams/demo-team/balance/') return send(200, fixtures.balance);
    if (/^\/api\/teams\/demo-team\/virtual_machines\/[^/]+\/state\/$/.test(p)) return send(200, fixtures.state);
    if (/^\/api\/teams\/demo-team\/virtual_machines\/[^/]+\/$/.test(p)) return send(200, fixtures.vms[0]);
    send(404, { detail: 'Not found.' });
  });
  return new Promise(resolve => server.listen(0, '127.0.0.1', () => resolve({ baseUrl: 'http://127.0.0.1:' + server.address().port + '/api', token, close: () => new Promise(r => server.close(r)) })));
}

/* A plan target that executes the fake benchmark locally. */
function localTarget(overrides = {}) {
  return {
    adapter: 'local', exec: 'local', name: 'local-demo', deployment_id: 'dep-mi300x-01', host: '127.0.0.1',
    gpus: 1, gpu_model: 'AMD MI300X (synthetic)', allocation_label: '1× MI300X VM (synthetic)',
    vllm_command: [process.execPath, path.join(__dirname, '..', '..', 'fixtures', 'fake-vllm.cjs')],
    env: {},
    ...overrides,
  };
}

function demoPlanInput(overrides = {}) {
  return {
    target: localTarget(overrides.target),
    workload: { model: 'Qwen/Qwen3-Coder-30B-A3B-Instruct', backend: 'openai', base_url: 'http://127.0.0.1:8000', dataset: 'random', input_len: 2048, output_len: 256, num_prompts: 48, request_rate: 'inf', seed: 7, ...(overrides.workload || {}) },
    concurrency: overrides.concurrency || [1, 8, 32],
    repeats: overrides.repeats ?? 2,
    identity: { model_revision: 'demo-rev', precision: 'FP8', tokenizer_revision: 'demo-rev', cache_policy: 'warm', runtime_digest: 'rocm/vllm@sha256:demo', ...(overrides.identity || {}) },
    price: { provider: 'Hot Aisle', gpus: 1, rate: 2.99, extra: 0, source: 'local demo (fake API on-demand price)', period: 'synthetic', ...(overrides.price || {}) },
    comparator: overrides.comparator === null ? null : { provider: 'Nebius HGX H100', gpus: 1, rate: 3.85, extra: 0, source: 'https://nebius.com/prices', period: '2026-09-22 snapshot', ...(overrides.comparator || {}) },
    limits: { max_minutes: 30, max_spend_usd: 5, ...(overrides.limits || {}) },
    gates: overrides.gates || {},
    requirements: overrides.requirements || { max_p95_ttft_ms: 1000, max_p95_e2e_ms: 15000 },
    primary_concurrency: overrides.primary_concurrency,
  };
}

module.exports = { startFakeApi, localTarget, demoPlanInput, FAKE_TOKEN, fixtures };
