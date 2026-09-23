'use strict';
/* Localhost service behind the page's connected mode. Binds 127.0.0.1 only. Serves the
   page itself plus a JSON API and server-sent events for job progress. State-changing
   calls require a client header and a loopback or known page origin, so a stray
   website cannot drive the runner. */
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const engine = require('./engine.cjs');
const { Jobs } = require('./jobs.cjs');
const { Store } = require('./store.cjs');
const record = require('./record.cjs');
const publications = require('./publication-store.cjs');
const prices = require('./catalog.cjs');
const { revalidate } = require('./revalidate.cjs');
const local = require('./adapters/local.cjs');
const { HotAisle, tokenFromEnvironment } = require('./adapters/hotaisle.cjs');

/* Origins that may drive the runner from a browser: the runner's own loopback page (any
   port, so a kit served elsewhere on this machine still works) and the published page
   on GitHub Pages. A file:// page sends Origin "null" and is refused. */
const ORIGINS = /^(https?:\/\/(127\.0\.0\.1|localhost|\[::1\])(:\d+)?|https:\/\/bigbirdreturns\.github\.io)$/;
const STATIC = { '.html': 'text/html; charset=utf-8', '.md': 'text/markdown; charset=utf-8', '.json': 'application/json', '.zip': 'application/zip', '.txt': 'text/plain; charset=utf-8', '.cjs': 'text/javascript', '.py': 'text/plain; charset=utf-8' };

function createServer({ store = new Store(), jobs = new Jobs(store), pageDir = path.dirname(engine.PAGE), fakeApi = null } = {}) {
  const clients = new Map();
  const broadcast = (jobId, event, data) => { for (const [res, id] of clients) if (!id || id === jobId) res.write('event: ' + event + '\ndata: ' + JSON.stringify(data) + '\n\n'); };
  jobs.on('job', j => broadcast(j.id, 'job', j));
  jobs.on('trial', t => broadcast(t.job, 'trial', t));
  jobs.on('line', l => broadcast(l.job, 'line', l));

  async function environment(adapter, team) {
    if (adapter === 'local') {
      const api = fakeApi || await local.startFakeApi();
      try { return await new HotAisle({ token: api.token, baseUrl: api.baseUrl }).inspect({ team: 'demo-team' }); } finally { if (!fakeApi) await api.close(); }
    }
    return new HotAisle().inspect({ team });
  }

  const server = http.createServer(async (req, res) => {
    const allowedHosts = ['127.0.0.1','localhost','[::1]'].map(h=>h+':'+server.address().port);
    if(!allowedHosts.includes(req.headers.host)){res.writeHead(403);return res.end('Host not allowed.');}
    const origin = req.headers.origin;
    if (origin !== undefined && !ORIGINS.test(origin)) { res.writeHead(403); return res.end('Origin not allowed.'); }
    if (origin) {
      res.setHeader('Access-Control-Allow-Origin', origin); res.setHeader('Vary', 'Origin');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-Workload-Client'); res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
      /* Chrome's private-network-access preflight (a public https page talking to 127.0.0.1)
         needs this or the browser drops the request before it reaches us. */
      res.setHeader('Access-Control-Allow-Private-Network', 'true');
      res.setHeader('Access-Control-Max-Age', '600');
    }
    if (req.method === 'OPTIONS') { res.writeHead(204); return res.end(); }
    const url = new URL(req.url, 'http://127.0.0.1');
    const json = (code, body) => { res.writeHead(code, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(body)); };
    const fail = e => json(e.status || 400, { error: e.message });
    try {
      if (req.method === 'POST') {
        if (req.headers['x-workload-client'] !== 'page') return json(403, { error: 'Missing X-Workload-Client header.' });
        req.body = await readJSON(req);
      }
      const p = url.pathname;
      let m;
      if (p === '/api/status') return json(200, { runner: 'connected', version: '2.2.0', engine: engine.identity(), home: store.root, jobs: store.list('jobs').length, records: store.list('records').length, adapters: { local: true, hotaisle: !!tokenFromEnvironment() }, demo: !!fakeApi });
      if (p === '/api/environment') return json(200, await environment(url.searchParams.get('adapter') || 'local', url.searchParams.get('team') || undefined));
      if (p === '/api/demo/plan') return json(200, local.demoPlanInput({ repeats: Number(url.searchParams.get('repeats') || 2), concurrency: (url.searchParams.get('concurrency') || '1,8,32').split(',').map(Number) }));
      if (p === '/api/jobs' && req.method === 'GET') return json(200, jobs.list());
      if (p === '/api/jobs' && req.method === 'POST') return json(201, jobs.summary(jobs.plan(req.body)));
      if ((m = p.match(/^\/api\/jobs\/([A-Za-z0-9._-]+)$/))) return json(200, jobs.get(m[1]));
      if ((m = p.match(/^\/api\/jobs\/([A-Za-z0-9._-]+)\/plan$/))) return json(200, jobs.get(m[1]).plan);
      if ((m = p.match(/^\/api\/jobs\/([A-Za-z0-9._-]+)\/approve$/)) && req.method === 'POST') return json(200, jobs.summary(jobs.approve(m[1], req.body || {})));
      if ((m = p.match(/^\/api\/jobs\/([A-Za-z0-9._-]+)\/start$/)) && req.method === 'POST') { const id = m[1]; const j = jobs.get(id); if (!['approved', 'interrupted', 'running'].includes(j.state)) throw new Error('Job is ' + j.state + '.'); jobs.start(id).catch(e => broadcast(id, 'error', { job: id, error: e.message })); return json(202, jobs.summary(jobs.get(id))); }
      if ((m = p.match(/^\/api\/jobs\/([A-Za-z0-9._-]+)\/cancel$/)) && req.method === 'POST') return json(200, jobs.cancel(m[1]));
      if ((m = p.match(/^\/api\/jobs\/([A-Za-z0-9._-]+)\/events$/))) { res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', Connection: 'keep-alive' }); res.write('event: job\ndata: ' + JSON.stringify(jobs.summary(jobs.get(m[1]))) + '\n\n'); clients.set(res, m[1]); req.on('close', () => clients.delete(res)); return; }
      if (p === '/api/events') { res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', Connection: 'keep-alive' }); res.write('event: hello\ndata: {}\n\n'); clients.set(res, null); req.on('close', () => clients.delete(res)); return; }
      if (p === '/api/catalog' && req.method === 'GET') return json(200, prices.snapshot());
      if (p === '/api/publications' && req.method === 'GET') return json(200, publications.list(store));
      if ((m=p.match(/^\/api\/publications\/([A-Za-z0-9._-]+)$/)) && req.method === 'GET') return json(200, publications.read(store,m[1]));
      if (p === '/api/records') return json(200, store.list('records').map(id => { const r = store.read('records', id); return { id, created: r.created, synthetic: r.synthetic, qualified: r.disposition.qualified, model: r.declared.plan.workload.model, primary_concurrency: r.derived.primary_concurrency, job_id: r.job_id, sha256: r.sha256 }; }).sort((a, b) => a.created < b.created ? 1 : -1));
      if ((m = p.match(/^\/api\/records\/([A-Za-z0-9._-]+)(\/(verify|headline|summary|report\.html|evidence\.json|revalidate|publish))?$/))) {
        const rec = store.read('records', m[1]); if (!rec) return json(404, { error: 'Unknown record.' });
        const view = m[3];
        if (!view) return json(200, rec);
        if (view === 'verify') return json(200, record.verify(rec));
        if (view === 'headline') return json(200, record.headline(rec, { evidence_url: '/api/records/' + rec.id + '/evidence.json', report_url: '/api/records/' + rec.id + '/report.html' }));
        if (view === 'summary') { res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' }); return res.end(record.summary(rec)); }
        if (view === 'report.html') { res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); return res.end(record.receipt(rec, num(url.searchParams.get('concurrency')))); }
        if (view === 'evidence.json') return json(200, record.packet(rec, num(url.searchParams.get('concurrency'))));
        if (view === 'revalidate' && req.method === 'POST') return json(200, revalidate(rec, req.body));
        if (view === 'publish' && req.method === 'POST') return json(200, publish(store, rec));
      }
      if (req.method === 'GET') return serveStatic(pageDir, p === '/' ? '/index.html' : p, res);
      json(404, { error: 'Not found.' });
    } catch (e) { fail(e); }
  });
  server.listenOn = (port = 0, host = '127.0.0.1') => new Promise(resolve => server.listen(port, host, () => resolve('http://' + host + ':' + server.address().port)));
  return server;
}

function num(v) { return v === null || v === undefined || v === '' ? undefined : Number(v); }

/* Publishing is an explicit act over an existing record: the headline, evidence packet
   and report are generated side by side from the same record. */
function publish(store, rec) { return publications.publish(store, rec); }

function serveStatic(root, p, res) {
  const clean = path.normalize(decodeURIComponent(p)).replace(/^([/\\])+/, '');
  const file = path.join(root, clean);
  if (!file.startsWith(root) || clean.includes('..') || clean.startsWith('runner')) { res.writeHead(404); return res.end(); }
  const type = STATIC[path.extname(file)];
  if (!type || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); return res.end('Not found.'); }
  res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-store' });
  fs.createReadStream(file).pipe(res);
}

function readJSON(req) {
  return new Promise((resolve, reject) => {
    let size = 0; const chunks = [];
    req.on('data', c => { size += c.length; if (size > 1024 * 1024) { reject(Object.assign(new Error('Body too large.'), { status: 413 })); req.destroy(); } else chunks.push(c); });
    req.on('end', () => { try { resolve(chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {}); } catch (e) { reject(new Error('Invalid JSON body.')); } });
    req.on('error', reject);
  });
}

module.exports = { createServer, publish };
