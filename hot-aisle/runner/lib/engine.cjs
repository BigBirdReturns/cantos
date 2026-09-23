'use strict';
/* Single arithmetic authority. The report engine embedded in index.html is the only
   place cost, latency, comparison and checksum rules live. Everything in the runner
   loads it from the page rather than re-implementing it. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');

const PAGE = path.resolve(__dirname, '..', '..', 'index.html');
const cache = new Map();

function sha256(input) {
  return crypto.createHash('sha256').update(input).digest('hex');
}

function load(pagePath = PAGE) {
  if (cache.has(pagePath)) return cache.get(pagePath).api;
  const html = fs.readFileSync(pagePath, 'utf8');
  const m = html.match(/<script id="report-engine">([\s\S]*?)<\/script>/);
  if (!m) throw new Error('report-engine script missing from ' + pagePath);
  const sandbox = { module: { exports: {} }, TextEncoder, Uint8Array, Uint32Array, DataView };
  vm.runInNewContext(m[1], sandbox, { filename: 'report-engine.js' });
  const api = sandbox.module.exports;
  if (typeof api.aggregate !== 'function' || typeof api.recompute !== 'function') throw new Error('report-engine did not export its API');
  cache.set(pagePath, { api, source_sha256: sha256(m[1]), page_sha256: sha256(html) });
  return api;
}

function identity(pagePath = PAGE) {
  load(pagePath);
  const c = cache.get(pagePath);
  return { version: c.api.VERSION, engine_sha256: c.source_sha256, page_sha256: c.page_sha256, page: pagePath };
}

module.exports = { load, identity, sha256, PAGE };
