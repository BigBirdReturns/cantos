'use strict';
/* MCP server over stdio (JSON-RPC 2.0, newline-delimited). Exposes the same operations
   as the CLI and the HTTP API: inspect the permitted environment, prepare an evaluation,
   start an approved one, read progress, retrieve results, revalidate after a change.
   Starting a job requires the plan hash that prepare returned, so a model cannot start
   anything the operator has not seen. Zero dependencies. */
const readline = require('node:readline');
const engine = require('./engine.cjs');
const { Jobs } = require('./jobs.cjs');
const { Store } = require('./store.cjs');
const record = require('./record.cjs');
const { revalidate } = require('./revalidate.cjs');
const local = require('./adapters/local.cjs');
const { HotAisle, tokenFromEnvironment } = require('./adapters/hotaisle.cjs');

const PROTOCOLS = ['2025-06-18', '2025-03-26', '2024-11-05'];
const UI_URI = 'ui://hot-aisle/evaluation';

const TOOLS = [
  { name: 'inspect_environment', title: 'Inspect environment', description: 'Read-only. Lists the authorized Hot Aisle team, allocations (GPU count and model, state, SSH endpoint), balance and on-demand VM prices. adapter "local" returns the synthetic integration environment.', inputSchema: { type: 'object', properties: { adapter: { type: 'string', enum: ['hotaisle', 'local'], default: 'hotaisle' }, team: { type: 'string' } } }, annotations: { readOnlyHint: true } },
  { name: 'prepare_evaluation', title: 'Prepare evaluation', description: 'Validates and freezes an evaluation plan without running anything. Returns the job id, the plan SHA-256 the operator must approve, the exact first benchmark command, and a coarse spend estimate.', inputSchema: { type: 'object', properties: { target: { type: 'object' }, workload: { type: 'object' }, concurrency: { type: 'array', items: { type: 'integer' } }, repeats: { type: 'integer' }, identity: { type: 'object' }, price: { type: 'object' }, comparator: { type: ['object', 'null'] }, limits: { type: 'object' }, gates: { type: 'object' }, requirements: { type: 'object' }, primary_concurrency: { type: 'integer' }, demo: { type: 'boolean', description: 'Fill every field from the local demonstration plan.' } } } },
  { name: 'start_evaluation', title: 'Start approved evaluation', description: 'Approves and starts a prepared job. approved_plan_sha256 must equal the plan hash shown by prepare_evaluation; it is the operator\'s approval token. Runs in the background; poll evaluation_status.', inputSchema: { type: 'object', required: ['job_id', 'approved_plan_sha256'], properties: { job_id: { type: 'string' }, approved_plan_sha256: { type: 'string' }, approved_by: { type: 'string' } } }, annotations: { destructiveHint: false, idempotentHint: true }, _meta: { ui: { resourceUri: UI_URI, visibility: ['model', 'app'] } } },
  { name: 'evaluation_status', title: 'Evaluation status', description: 'Progress, limits, completed trials and disposition of a job. Safe to call repeatedly.', inputSchema: { type: 'object', required: ['job_id'], properties: { job_id: { type: 'string' } } }, annotations: { readOnlyHint: true }, _meta: { ui: { resourceUri: UI_URI, visibility: ['model', 'app'] } } },
  { name: 'cancel_evaluation', title: 'Cancel evaluation', description: 'Stops the benchmark the job owns. Completed trials are retained.', inputSchema: { type: 'object', required: ['job_id'], properties: { job_id: { type: 'string' } } } },
  { name: 'evaluation_result', title: 'Evaluation result', description: 'The qualified record for a job or record id: disposition, per-cell cost and latency, verification status, and the generated headline.', inputSchema: { type: 'object', properties: { job_id: { type: 'string' }, record_id: { type: 'string' } } }, annotations: { readOnlyHint: true }, _meta: { ui: { resourceUri: UI_URI, visibility: ['model', 'app'] } } },
  { name: 'list_records', title: 'List qualified records', description: 'All retained qualified records, newest first.', inputSchema: { type: 'object', properties: {} }, annotations: { readOnlyHint: true } },
  { name: 'revalidate', title: 'Revalidate after a change', description: 'Given a record and a change (price, gates, requirements, traffic, runtime, evaluator), reports which conclusions stand, which were recomputed from retained evidence, which need new measurement, and the minimal plan.', inputSchema: { type: 'object', required: ['record_id', 'change'], properties: { record_id: { type: 'string' }, change: { type: 'object', properties: { price: { type: 'object' }, gates: { type: 'object' }, requirements: { type: 'object' }, traffic: { type: 'object' }, runtime: { type: 'object' }, evaluator: { type: 'object' } } } } }, annotations: { readOnlyHint: true } },
];

function uiResource() {
  return '<!doctype html><html lang="en"><meta charset="utf-8"><title>Evaluation</title><style>body{margin:0;font:14px/1.5 Inter,system-ui,sans-serif;color:#171717;background:#f8f8f5;padding:16px}.k{font:600 11px/1 ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;color:#6b6a64}.v{font-size:28px;font-weight:700;letter-spacing:-.03em;margin:6px 0 14px}.bar{height:6px;background:#e8e7e1;border-radius:3px;overflow:hidden}.bar i{display:block;height:100%;background:#c04712}pre{font:12px ui-monospace,monospace;white-space:pre-wrap;color:#30302c}@media(prefers-color-scheme:dark){body{background:#0b0d0b;color:#f2f1ed}.bar{background:#2a2d2a}pre{color:#d9d8d1}}</style><body><div class="k">Workload evaluation</div><div class="v" id="t">Waiting for a tool result…</div><div class="bar"><i id="b" style="width:0"></i></div><pre id="p"></pre><script>function render(r){try{const s=r.structuredContent||r;document.getElementById("t").textContent=s.state?("Job "+s.state):s.disposition?(s.disposition.qualified?"Qualified":"Not qualified"):"Result";if(s.progress)document.getElementById("b").style.width=Math.round(100*s.progress.completed/Math.max(1,s.progress.total))+"%";document.getElementById("p").textContent=JSON.stringify(s,null,1).slice(0,4000);}catch(e){}}if(window.__MCP_TOOL_RESULT__)render(window.__MCP_TOOL_RESULT__);addEventListener("message",e=>{const d=e.data||{};if(d.params&&(d.params.structuredContent||d.params.content))render(d.params);else if(d.result)render(d.result);});</script></body></html>';
}

function serve({ input = process.stdin, output = process.stdout, store = new Store(), jobs = new Jobs(store) } = {}) {
  const rl = readline.createInterface({ input, crlfDelay: Infinity });
  const send = msg => output.write(JSON.stringify(msg) + '\n');
  const ok = (id, result) => send({ jsonrpc: '2.0', id, result });
  const err = (id, code, message, data) => send({ jsonrpc: '2.0', id, error: { code, message, ...(data ? { data } : {}) } });
  const toolResult = (value, isError = false) => ({ content: [{ type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value, null, 1) }], structuredContent: typeof value === 'string' ? { text: value } : value, isError });

  async function call(name, a = {}) {
    switch (name) {
      case 'inspect_environment': {
        if ((a.adapter || 'hotaisle') === 'local') { const api = await local.startFakeApi(); try { return await new HotAisle({ token: api.token, baseUrl: api.baseUrl }).inspect({ team: 'demo-team' }); } finally { await api.close(); } }
        return new HotAisle().inspect({ team: a.team });
      }
      case 'prepare_evaluation': {
        const input = a.demo ? local.demoPlanInput(a) : a;
        const job = jobs.plan(input);
        return { job_id: job.id, state: job.state, plan_sha256: job.plan.sha256, cells: job.plan.cells.length, first_command: job.plan.commands[0], estimate: job.plan.estimate, limits: job.plan.limits, next: 'Show the operator the plan hash and the command. Call start_evaluation with approved_plan_sha256 only after they approve.' };
      }
      case 'start_evaluation': {
        const job = jobs.get(a.job_id);
        if (job.state === 'planned') jobs.approve(a.job_id, { by: a.approved_by || 'mcp-client', plan_sha256: a.approved_plan_sha256 });
        else if (job.plan.sha256 !== a.approved_plan_sha256) throw new Error('approved_plan_sha256 does not match the job\'s plan.');
        jobs.start(a.job_id).catch(() => {});
        return jobs.summary(jobs.get(a.job_id));
      }
      case 'evaluation_status': { const j = jobs.get(a.job_id); return { ...jobs.summary(j), limits: j.plan.limits, log: j.log.slice(-8), trials: j.trials.map(t => ({ cell: t.cell, status: t.status, completed: t.normalized ? t.normalized.completed : null, attempted: t.normalized ? t.normalized.attempted : null, error: t.error })) }; }
      case 'cancel_evaluation': return jobs.cancel(a.job_id);
      case 'evaluation_result': {
        const id = a.record_id || (a.job_id && jobs.get(a.job_id).record_id);
        if (!id) throw new Error('No record for that job yet.');
        const rec = store.read('records', id); if (!rec) throw new Error('Unknown record.');
        return { record_id: rec.id, sha256: rec.sha256, synthetic: rec.synthetic, disposition: rec.disposition, verification: record.verify(rec), cells: rec.derived.cells.map(c => ({ concurrency: c.concurrency, runs: c.runs, cost_per_1000: c.cost ? c.cost.costPer1000 : null, accepted_per_s: c.aggregate ? c.aggregate.rate : null, p95_ttft_ms: c.aggregate ? c.aggregate.metrics.ttft.p95 : null, p95_e2e_ms: c.aggregate ? c.aggregate.metrics.e2e.p95 : null, meets: c.meets, reasons: c.reasons })), headline: record.headline(rec), summary: record.summary(rec) };
      }
      case 'list_records': return store.list('records').map(id => { const r = store.read('records', id); return { id, created: r.created, synthetic: r.synthetic, qualified: r.disposition.qualified, model: r.declared.plan.workload.model }; }).sort((x, y) => x.created < y.created ? 1 : -1);
      case 'revalidate': { const rec = store.read('records', a.record_id); if (!rec) throw new Error('Unknown record.'); return revalidate(rec, a.change); }
      default: { const e = new Error('Unknown tool: ' + name); e.protocol = true; throw e; }
    }
  }

  rl.on('line', async line => {
    if (!line.trim()) return;
    let msg; try { msg = JSON.parse(line); } catch (e) { return send({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Parse error' } }); }
    const { id, method, params = {} } = msg;
    if (method === undefined) return;
    try {
      if (method === 'initialize') return ok(id, { protocolVersion: PROTOCOLS.includes(params.protocolVersion) ? params.protocolVersion : PROTOCOLS[0], capabilities: { tools: { listChanged: false }, resources: { subscribe: false, listChanged: false } }, serverInfo: { name: 'hot-aisle-workload-report', title: 'Hot Aisle workload report runner', version: '2.2.0' }, instructions: 'Inspect first. prepare_evaluation never runs anything; start_evaluation needs the plan hash the operator approved. Results are qualified records; use revalidate before proposing a rerun.' });
      if (method === 'notifications/initialized' || method.startsWith('notifications/')) return;
      if (method === 'ping') return ok(id, {});
      if (method === 'tools/list') return ok(id, { tools: TOOLS });
      if (method === 'tools/call') {
        if (!TOOLS.some(t => t.name === params.name)) return err(id, -32602, 'Unknown tool: ' + params.name);
        try { return ok(id, toolResult(await call(params.name, params.arguments || {}))); } catch (e) { if (e.protocol) return err(id, -32602, e.message); return ok(id, toolResult('Error: ' + e.message, true)); }
      }
      if (method === 'resources/list') return ok(id, { resources: [{ uri: UI_URI, name: 'Evaluation view', mimeType: 'text/html;profile=mcp-app', description: 'Progress and result view for evaluation tools.' }] });
      if (method === 'resources/templates/list') return ok(id, { resourceTemplates: [] });
      if (method === 'resources/read') { if (params.uri !== UI_URI) return err(id, -32002, 'Unknown resource: ' + params.uri); return ok(id, { contents: [{ uri: UI_URI, mimeType: 'text/html;profile=mcp-app', text: uiResource() }] }); }
      if (method === 'prompts/list') return ok(id, { prompts: [] });
      return err(id, -32601, 'Method not found: ' + method);
    } catch (e) { return err(id, -32603, e.message); }
  });
  return { close: () => rl.close(), tools: TOOLS };
}

module.exports = { serve, TOOLS, PROTOCOLS, UI_URI, uiResource };
