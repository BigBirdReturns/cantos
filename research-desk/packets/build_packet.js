#!/usr/bin/env node
'use strict';
/* Builds PUBLIC-TAIL-2026-09-29.research-packet.json for Research Desk 1.0.0 (app.html, SHA-256 pinned in README.md).
   No dependencies. Inputs are read-only. The functions safeTree/plain/canonical/hash below are copied verbatim
   from app.html's <script id="research-core">; loadAppCore() extracts that same script so validate_packet.js
   can prove the copies agree with the app. */
const fs = require('fs');
const path = require('path');
const nodeCrypto = require('node:crypto');

const HERE = __dirname;
const DESK = path.resolve(HERE, '..');
const APP_HTML = path.join(DESK, 'app.html');
const APP_SHA256 = '5951f7f3d994ec980d2958ae18246edc6dbe5b57db8d38e90c1c18956b96e470';
const SESS = process.env.PT_SESSIONS || 'D:/Projects/Organs/AXM/axm-tools/sessions';
const CMAX = path.join(SESS, 'clustermax-cloudreview-20260929');
const LANES = path.join(SESS, 'public-tail-20260929/lanes');
const OUT = path.join(HERE, 'PUBLIC-TAIL-2026-09-29.research-packet.json');
const NOTES_OUT = path.join(HERE, 'PUBLIC-TAIL-2026-09-29.build-notes.json');
const BUILD_AT = '2026-09-29T22:00:00Z'; // fixed so rebuilds are byte-identical
const ACTOR = 'Public-tail packet builder';

// ---- verbatim from app.html research-core (lines 22-28) -------------------------------------------------
const root = globalThis;
const enc = new TextEncoder();
function assert(ok,message){if(!ok)throw new Error(message);}
function plain(v){return v!==null&&typeof v==='object'&&!Array.isArray(v)&&(Object.getPrototypeOf(v)===Object.prototype||Object.getPrototypeOf(v)===null);}
function safeTree(v,depth=0){assert(depth<60,'Object nesting exceeds 60 levels.'); if(typeof v==='number')assert(Number.isFinite(v),'Non-finite numbers are forbidden.'); if(v&&typeof v==='object'){assert(Array.isArray(v)||plain(v),'Only plain JSON data is supported.'); for(const k of Object.keys(v)){assert(!['__proto__','constructor','prototype'].includes(k),'Unsafe object key.');safeTree(v[k],depth+1);}}}
function canonical(v){safeTree(v);if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';if(plain(v))return '{'+Object.keys(v).sort().filter(k=>v[k]!==undefined).map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';assert(v!==undefined,'Undefined JSON value.');return JSON.stringify(v);}
function clone(v){return JSON.parse(canonical(v));}
async function hash(v){const bytes=typeof v==='string'?enc.encode(v):v instanceof Uint8Array?v:enc.encode(canonical(v));const crypto=root.crypto || (typeof require!=='undefined'?require('node:crypto').webcrypto:null);assert(crypto?.subtle,'Web Crypto is unavailable; use a current browser or localhost.');return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');}
// ---------------------------------------------------------------------------------------------------------

const ZERO = '0'.repeat(64);
const SCHEMA = 'second-run/research-desk@1', VERSION = '1.0.0';
const BOUNDARY = 'Checksum and journal detect changes relative to this packet. They do not authenticate a publisher or prevent a hostile party from rebuilding an entirely new chain. Retain a trusted prior checksum separately.';

/** Extract and evaluate the app's own research-core (verifies app.html is the pinned build first). */
function loadAppCore() {
  const buf = fs.readFileSync(APP_HTML);
  const sha = nodeCrypto.createHash('sha256').update(buf).digest('hex');
  if (sha !== APP_SHA256) throw new Error('app.html SHA-256 is ' + sha + ', expected ' + APP_SHA256);
  const html = buf.toString('utf8');
  const m = html.match(/<script id="research-core">([\s\S]*?)<\/script>/);
  if (!m) throw new Error('research-core script not found');
  const sandbox = { crypto: globalThis.crypto, TextEncoder, TextDecoder, module: { exports: {} }, console };
  sandbox.globalThis = sandbox;
  require('node:vm').runInNewContext(m[1], sandbox, { filename: 'app.html#research-core' });
  return { core: sandbox.module.exports, appSha256: sha, coreSource: m[1] };
}

const sha256hex = b => nodeCrypto.createHash('sha256').update(b).digest('hex');
const readText = p => fs.readFileSync(p, 'utf8');
const rdJsonl = p => readText(p).replace(/^\uFEFF/, '').split('\n').filter(l => l.trim()).map(l => JSON.parse(l));
const rdJson = p => JSON.parse(readText(p).replace(/^\uFEFF/, ''));

class Journal {
  constructor(label) { this.ws = { schema: SCHEMA, version: VERSION, label, events: [] }; this.latest = new Map(); this.counts = {}; }
  async record(r) {
    const prev = this.latest.get(r.id);
    const rec = clone({ ...r, revision: (prev?.revision || 0) + 1 });
    if (prev) assert(prev.kind === rec.kind, 'kind change');
    for (const d of rec.deps) { const t = this.latest.get(d.id); assert(t && t.revision === d.revision, 'dep missing ' + d.id); }
    const events = this.ws.events;
    const body = { seq: events.length + 1, prev: events.at(-1)?.hash || ZERO, type: 'record', actor: ACTOR, at: BUILD_AT, payload: rec };
    events.push({ ...body, hash: await hash(body) });
    this.latest.set(rec.id, rec);
    this.counts[rec.kind] = (this.counts[rec.kind] || 0) + 1;
  }
}

const clip = (s, n) => (s.length <= n ? s : s.slice(0, n - 1).trimEnd() + '\u2026');
const slugId = s => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
const fmt = v => (typeof v === 'number' ? v.toFixed(2) : String(v));

async function build() {
  const { appSha256 } = loadAppCore();
  const J = new Journal('Public tail 2026-09-29: ClusterMAX reviews, SemiAnalysis newsletter and podcasts, TCO calculator, OpenComputePrices');
  const inputs = {};
  const track = (label, p) => { inputs[label] = { path: p.replace(/\\/g, '/'), bytes: fs.statSync(p).size, sha256: sha256hex(fs.readFileSync(p)) }; };

  // (a)+(b) ClusterMAX review pages and claims ------------------------------------------------------------
  const claimsP = path.join(CMAX, 'claims.all.jsonl'), headersP = path.join(CMAX, 'headers.all.json'), capP = path.join(CMAX, 'capture-manifest.json');
  [['claims.all.jsonl', claimsP], ['headers.all.json', headersP], ['capture-manifest.json', capP]].forEach(([l, p]) => track(l, p));
  const claims = rdJsonl(claimsP), headers = rdJson(headersP), cap = rdJson(capP);
  const hdrByUrl = new Map(headers.map(h => [h.canonical_url, h]));
  const capByUrl = new Map(cap.map(c => [c.url, c]));
  const urls = [...new Set(claims.map(c => c.url))].sort();
  const cmaxSrcId = new Map();
  for (const url of urls) {
    const h = hdrByUrl.get(url); assert(h, 'no header for ' + url);
    const html = capByUrl.get(url), txt = capByUrl.get(url + '/llm.txt');
    assert(html && txt, 'no capture-manifest entry for ' + url);
    assert(txt.sha256 === h.text_sha256, 'llm.txt sha mismatch ' + url); assert(!h.retrieved_utc || h.retrieved_utc === txt.retrieved_utc, 'retrieved mismatch ' + url);
    const rowShas = new Set(claims.filter(c => c.url === url).map(c => c.sha256_of_saved_raw));
    assert(rowShas.size === 1 && rowShas.has(h.text_sha256), 'claim sha mismatch ' + url);
    const id = 'cmax-src-' + slugId(h.slug); cmaxSrcId.set(url, id);
    await J.record({
      id, kind: 'source', tier: 'public_observation', disposition: 'observed', deps: [],
      title: clip('ClusterMAX review page: ' + h.provider + ' (' + h.source_version + ')', 240),
      summary: clip(h.provider + ' review page on clustermax.ai. Tier on page: ' + h.tier_on_page + '. Published ' + h.published + ', last updated ' + h.last_updated + '. Source version: ' + h.source_version + (h.stub ? '. Page is a stub (short entry).' : '.'), 2000),
      data: {
        url, canonical_url: url, provider: h.provider, slug: h.slug,
        sha256: h.text_sha256, sha256_of: 'llm.txt text view of the page (GET ' + url + '/llm.txt)', text_url: url + '/llm.txt', text_bytes: h.text_bytes,
        html_sha256: html.sha256, html_bytes: html.bytes, html_sha256_of: 'raw HTML of the page (GET ' + url + ')',
        retrieved_utc: txt.retrieved_utc, html_retrieved_utc: html.retrieved_utc,
        published: h.published, last_updated: h.last_updated, authors: h.authors,
        tier_on_page: h.tier_on_page, tier_definition: h.tier_definition, source_version: h.source_version,
        source_article: h.source_article, stub: !!h.stub,
        refetch_note: 'Live page may have changed since retrieval; compare fetched llm.txt bytes to sha256. Page content is ClusterMAX 2.0 text (2.1 update sections on four pages).'
      }
    });
  }
  for (const c of claims) {
    const prov = c.providers.join(', ');
    await J.record({
      id: 'cmax-claim-' + slugId(c.id), kind: 'claim', tier: 'public_observation', disposition: 'open',
      deps: [{ id: cmaxSrcId.get(c.url), revision: 1 }],
      title: clip(prov + ' [' + c.topic + ']: ' + c.quote, 240),
      summary: c.quote,
      data: { quote: c.quote, quote_is_verbatim: true, topic: c.topic, stance: c.stance, providers: c.providers, date: c.date_utc, speaker: c.speaker, venue: c.venue,
        source_claim_id: c.id, url: c.url, sha256: c.sha256_of_saved_raw, retrieved_utc: c.retrieved_utc,
        locator: 'quote appears verbatim in ' + c.url + '/llm.txt' }
    });
  }

  // (c) SemiAnalysis newsletter posts ---------------------------------------------------------------------
  const postsP = path.join(LANES, 'sa-newsletter/rows/posts.jsonl'), postManP = path.join(LANES, 'sa-newsletter/manifest.json');
  track('sa-newsletter/rows/posts.jsonl', postsP); track('sa-newsletter/manifest.json', postManP);
  const posts = rdJsonl(postsP), postMan = rdJsonl(postManP);
  const byUrl = new Map();
  for (const p of posts) { if (!byUrl.has(p.url)) byUrl.set(p.url, []); byUrl.get(p.url).push(p); }
  const manByUrl = new Map();
  for (const m of postMan) { if (!manByUrl.has(m.url)) manByUrl.set(m.url, []); manByUrl.get(m.url).push(m); }
  let dupUrls = 0;
  const PREVIEW_MAX = 600;
  for (const [url, rows] of [...byUrl].sort((a, b) => (a[0] < b[0] ? -1 : 1))) {
    const p = rows.at(-1); // later extraction of the same page (larger preview cap)
    if (rows.length > 1) dupUrls++;
    const mans = manByUrl.get(url) || [];
    const m = mans.find(x => x.sha256 === p.provenance.sha256);
    assert(m, 'manifest sha mismatch ' + url);
    const prevText = p.free_preview_text || '';
    await J.record({
      id: 'sa-post-' + slugId(p.slug).slice(0, 80), kind: 'source', tier: 'public_observation', disposition: 'observed', deps: [],
      title: clip(p.title, 240),
      summary: clip((p.paywalled ? 'Paywalled' : 'Free') + ' SemiAnalysis newsletter post, published ' + p.datePublished.slice(0, 10) + '. Free preview word count: ' + p.word_count_free + '. ' + (p.subtitle || ''), 2000),
      data: {
        url, canonical_url: url, slug: p.slug, sha256: p.provenance.sha256, sha256_of: 'raw HTML of the post as fetched (GET ' + url + ')', bytes: m.bytes,
        retrieved_utc: p.provenance.retrieved_at, published: p.datePublished, authors: p.authors, subtitle: p.subtitle || null,
        paywalled: p.paywalled, free_preview_word_count: p.word_count_free, companies_mentioned_in_free_text: p.companies_mentioned,
        free_preview_excerpt: prevText.slice(0, PREVIEW_MAX), free_preview_excerpt_truncated: prevText.length > PREVIEW_MAX,
        free_preview_original_chars: prevText.length, free_preview_original_sha256: sha256hex(Buffer.from(prevText, 'utf8')),
        preview_note: 'Preview text truncated to ' + PREVIEW_MAX + ' chars for this packet. The lane extractor captured page-head markup (CSS/JSON-LD) ahead of article prose, so the excerpt and free_preview_word_count are extractor output, not a clean count of article words.',
        duplicate_extractions: rows.length > 1 ? rows.map(r => ({ word_count_free: r.word_count_free, preview_chars: (r.free_preview_text || '').length, sha256: r.provenance.sha256 })) : null,
        refetch_note: 'Live post may have changed since retrieval; the SHA-256 is of raw HTML bytes and may not reproduce for dynamic Substack markup.'
      }
    });
  }

  // (d) SemiAnalysis podcast/YouTube caption quotes ---------------------------------------------------------
  const quotesP = path.join(LANES, 'sa-podcasts/rows/quotes.jsonl'), podManP = path.join(LANES, 'sa-podcasts/manifest.json');
  track('sa-podcasts/rows/quotes.jsonl', quotesP); track('sa-podcasts/manifest.json', podManP);
  const quotes = rdJsonl(quotesP), podMan = rdJsonl(podManP);
  const PODS = {
    'https://www.youtube.com/watch?v=gO7oczGh9qE': { title: 'SemiAnalysis Weekly Ep. 033: ClusterMAX 3.0 Is Here! Neoclouds Ranked (YouTube captions)' },
    'https://www.youtube.com/watch?v=cZp9eJCWXW0': { title: 'SemiAnalysis ClusterMAX 2.0: The Ultimate GPU Cloud Power Ranking (YouTube captions)' },
    'https://www.youtube.com/watch?v=mDG_Hx3BSUE': { title: 'Dwarkesh Podcast: Dylan Patel deep dive (YouTube captions)' }
  };
  const podSrcId = new Map();
  for (const url of [...new Set(quotes.map(q => q.source_url))].sort()) {
    const meta = PODS[url]; assert(meta, 'unknown podcast url ' + url);
    const rows = quotes.filter(q => q.source_url === url);
    const sha = new Set(rows.map(r => r.provenance.sha256)); assert(sha.size === 1, 'multiple hashes for ' + url);
    const man = podMan.find(m => m.url === url); assert(man && man.sha256 === [...sha][0], 'pod manifest mismatch ' + url);
    const id = 'sa-pod-' + slugId(url.split('=')[1]);
    podSrcId.set(url, id);
    await J.record({
      id, kind: 'source', tier: 'public_observation', disposition: 'observed', deps: [],
      title: meta.title,
      summary: 'Auto-generated English captions (VTT) for a public video. Speaker labels are not reliable and are recorded as UNVERIFIED; captions can misrecognize names.',
      data: { url, canonical_url: url, sha256: man.sha256, sha256_of: 'saved English VTT caption file ' + man.file + ' (yt-dlp subtitle fetch), not the video', bytes: man.bytes, retrieved_utc: man.retrieved_utc,
        source_label: rows[0].source, quote_rows: rows.length, license_terms_note: man.license_terms_note,
        refetch_note: 'Re-fetch with yt-dlp --write-auto-subs --sub-langs en --skip-download; auto-captions can be regenerated by YouTube, so byte-identity is not guaranteed.' }
    });
  }
  for (const [i, q] of quotes.entries()) {
    await J.record({
      id: 'sa-pod-quote-' + String(i + 1).padStart(3, '0'), kind: 'claim', tier: 'public_observation', disposition: 'open',
      deps: [{ id: podSrcId.get(q.source_url), revision: 1 }],
      title: clip('Caption ' + q.timestamp + ': ' + q.verbatim_text, 240),
      summary: q.verbatim_text,
      data: { quote: q.verbatim_text, quote_is_verbatim: true, timestamp: q.timestamp, speaker: q.speaker, url: q.source_url, sha256: q.provenance.sha256, retrieved_utc: q.provenance.retrieved_at,
        row_index: i + 1, locator: 'caption cue near ' + q.timestamp + ' in the VTT (sentence boundaries inferred from cues)' }
    });
  }

  // (e) SemiAnalysis TCO calculator ---------------------------------------------------------------------------
  const tcoP = path.join(CMAX, 'tco-model.json'), chunkP = path.join(CMAX, 'tco_chunks/1bj4l-d6k82v1.js'), parseP = path.join(CMAX, 'parse_tco.py');
  track('tco-model.json', tcoP); track('tco_chunks/1bj4l-d6k82v1.js', chunkP); track('parse_tco.py', parseP);
  const tco = rdJson(tcoP);
  const chunkUrl = 'https://www.clustermax.ai/_next/static/immutable/chunks/1bj4l-d6k82v1.js';
  const chunkSha = inputs['tco_chunks/1bj4l-d6k82v1.js'].sha256;
  await J.record({
    id: 'tco-src-clustermax-tco-chunk', kind: 'source', tier: 'public_observation', disposition: 'observed', deps: [],
    title: 'SemiAnalysis AI Cloud TCO calculator: page JavaScript chunk 1bj4l-d6k82v1.js',
    summary: 'Client-side JavaScript chunk of https://www.clustermax.ai/tco that embeds the calculator scenarios, per-tier prices and MTBF presets. Assumption values were extracted from the minified source by regex (parse_tco.py).',
    data: { url: chunkUrl, canonical_url: chunkUrl, page: tco.page, sha256: chunkSha, sha256_of: 'JS chunk bytes as saved', bytes: inputs['tco_chunks/1bj4l-d6k82v1.js'].bytes,
      retrieved_date: tco.retrieved_utc, retrieved_utc: null, retrieved_utc_note: 'Only the date (2026-09-29) was recorded for this chunk.',
      chunk_url_note: 'Chunk URL is the site origin plus the path recorded in tco_chunks/list.txt; the chunk filename is content-hashed by the site build and may change.',
      extraction: { script: 'parse_tco.py', script_sha256: inputs['parse_tco.py'].sha256, output: 'tco-model.json', output_sha256: inputs['tco-model.json'].sha256, method: 'regex parse of minified JS; verify against the chunk before relying on any value' },
      tier_key_order: tco.tier_key_order }
  });
  const tcoSrc = [{ id: 'tco-src-clustermax-tco-chunk', revision: 1 }];
  const tierNames = ['gold', 'hyperscaler', 'silver'];
  let tcoItems = 0;
  for (const sc of tco.scenarios) {
    for (const r of sc.rows) {
      if (!r.prices) continue;
      tcoItems++;
      const vals = tierNames.map(t => r.prices[t]);
      const sentence = r.units === '$/GPU/hr'
        ? 'SemiAnalysis TCO calculator assumes ' + r.label + ' $' + vals.map(fmt).join('/') + ' per GPU-hr gold/hyperscaler/silver (scenario "' + sc.name + '", quantity ' + r.qty + ').'
        : 'SemiAnalysis TCO calculator assumes ' + r.section + ' line "' + r.label + '" at ' + vals.join('/') + ' (' + r.units + ') gold/hyperscaler/silver (scenario "' + sc.name + '", quantity ' + r.qty + ', calc ' + r.calc + ').';
      await J.record({
        id: 'tco-' + slugId(sc.name).slice(0, 40) + '-' + slugId(r.id), kind: 'claim', tier: 'public_observation', disposition: 'open', deps: tcoSrc,
        title: clip('TCO assumption [' + sc.name + ']: ' + r.section + ' / ' + r.label, 240), summary: sentence,
        data: { assertion_type: 'calculator_assumption', scenario: sc.name, engineering_salary_raw: sc.engineeringSalary, line_item_id: r.id, label: r.label, section: r.section, units: r.units, quantity: r.qty,
          calc: r.calc, description: r.description, prices: r.prices, tier_order: tierNames, storage_unit: r.storageUnit || null, network_unit: r.networkUnit || null,
          url: tco.page, source_chunk_url: chunkUrl, sha256: chunkSha, retrieved_date: tco.retrieved_utc,
          note: 'A calculator default in a public web app, not a market price observation. Non-numeric price values (for example "included") are kept as strings.' }
      });
    }
  }
  for (const [i, g] of tco.goodput_presets.entries()) {
    await J.record({
      id: 'tco-mtbf-' + String(i + 1).padStart(2, '0') + '-' + slugId(g.label).slice(0, 40), kind: 'claim', tier: 'public_observation', disposition: 'open', deps: tcoSrc,
      title: clip('TCO goodput preset: ' + g.label + ' = ' + g.mtbfGpuHrs + ' GPU-hrs MTBF', 240),
      summary: 'SemiAnalysis TCO calculator goodput preset "' + g.label + '" assumes an MTBF of ' + g.mtbfGpuHrs + ' GPU-hours' + (g.sourceUrl ? ', citing ' + (g.sourceLabel || g.sourceUrl) + ' (' + g.sourceUrl + ').' : '.'),
      data: { assertion_type: 'calculator_preset', preset_label: g.label, mtbf_gpu_hrs: g.mtbfGpuHrs, cited_source_label: g.sourceLabel || null, cited_source_url: g.sourceUrl || null, preset_index: i + 1,
        url: tco.page, source_chunk_url: chunkUrl, sha256: chunkSha, retrieved_date: tco.retrieved_utc,
        note: 'Preset value in a public web app; the cited source has not been fetched or checked for this record.' }
    });
  }

  // (f) OpenComputePrices July 2026 medians ----------------------------------------------------------------------
  const ocp = path.join(LANES, 'opencomputeprices');
  const repP = path.join(ocp, 'REPORT.md'), covP = path.join(ocp, 'summary/coverage.md'), ocpManP = path.join(ocp, 'manifest.json');
  track('opencomputeprices/REPORT.md', repP); track('opencomputeprices/summary/coverage.md', covP); track('opencomputeprices/manifest.json', ocpManP);
  const ocpMan = rdJson(ocpManP);
  const master = ocpMan.find(m => m.member === '_master.csv'); assert(master && master.sha256, 'no _master.csv in manifest');
  const tarball = ocpMan.find(m => m.file === 'raw/releases/data.tar.gz'); assert(tarball, 'no data.tar.gz in manifest');
  const report = readText(repP), cov = readText(covP);
  const julLine = cov.split('\n').find(l => l.startsWith('| 2026-07 |')); assert(julLine, 'no 2026-07 row in coverage.md');
  const cells = julLine.split('|').slice(2, 7).map(s => s.trim());
  const SKUS = ['H100', 'H200', 'B200', 'MI300X', 'MI355X'];
  const repSeg = report.match(/Jul 2026: (.+?)\.\s*Trend/s); assert(repSeg, 'no Jul 2026 segment in REPORT.md');
  const stats = SKUS.map((sku, i) => {
    const m = cells[i].match(/^([\d.]+) \/ ([\d.]+) \((\d+)\)$/); assert(m, 'bad cell ' + cells[i]);
    const rm = repSeg[1].match(new RegExp(sku + ' ([\\d.]+)(?: \\((\\d+) providers?\\))?')); assert(rm, 'REPORT missing ' + sku);
    assert(Number(rm[1]) === Number(m[2]), 'REPORT/coverage provider-median disagree for ' + sku);
    if (rm[2]) assert(rm[2] === m[3], 'REPORT/coverage provider count disagree for ' + sku);
    return { sku, row_median: Number(m[1]), provider_median: Number(m[2]), provider_count: Number(m[3]) };
  });
  const ocpSrcId = 'ocp-src-latest-data-2026-07-29';
  await J.record({
    id: ocpSrcId, kind: 'source', tier: 'public_observation', disposition: 'observed', deps: [],
    title: 'OpenComputePrices release latest-data (GPU Pricing Data, 2026-07-29 14:36 UTC), _master.csv',
    summary: 'GitHub release "latest-data" of thatkavish/OpenComputePrices (MIT). _master.csv is a member of data.tar.gz; it was streamed and hashed but not saved locally (10.6 GB).',
    data: { url: 'https://github.com/thatkavish/OpenComputePrices/releases/download/latest-data/data.tar.gz', canonical_url: 'https://github.com/thatkavish/OpenComputePrices/releases/tag/latest-data', repository: 'https://github.com/thatkavish/OpenComputePrices',
      release_tag: 'latest-data', release_title: 'GPU Pricing Data \u2014 2026-07-29 14:36 UTC', release_updated: '2026-07-29',
      tarball: { file: 'data.tar.gz', sha256: tarball.sha256, bytes: tarball.bytes },
      member: '_master.csv', sha256: master.sha256, sha256_of: '_master.csv member of data.tar.gz, as recorded in the lane manifest.json (streamed hash)', bytes: master.bytes, rows_scanned: master.rows,
      retrieved_date: tarball.retrieved_utc, retrieved_utc: null, retrieved_utc_note: 'Lane manifest recorded the date only.', not_saved_locally: true,
      license: 'MIT (repo)', derived_files: { 'REPORT.md': inputs['opencomputeprices/REPORT.md'].sha256, 'summary/coverage.md': inputs['opencomputeprices/summary/coverage.md'].sha256, 'manifest.json': inputs['opencomputeprices/manifest.json'].sha256 },
      refetch_note: 'latest-data is a rolling release tag. A later fetch may return a different data.tar.gz; compare the tarball SHA-256 above first, then extract _master.csv and hash it. The lane report notes row totals do not reconcile to the 54.8M in the release body.' }
  });
  for (const s of stats) {
    const pl = s.provider_count + ' provider' + (s.provider_count === 1 ? '' : 's');
    await J.record({
      id: 'ocp-jul2026-' + slugId(s.sku), kind: 'claim', tier: 'public_observation', disposition: 'open', deps: [{ id: ocpSrcId, revision: 1 }],
      title: 'OpenComputePrices July 2026 on-demand ' + s.sku + ': provider-median $' + s.provider_median.toFixed(2) + '/GPU-hr (' + pl + ')',
      summary: 'In the OpenComputePrices July 2026 data, the median across providers of per-provider median on-demand ' + s.sku + ' prices is $' + s.provider_median.toFixed(2) + ' per GPU-hr across ' + pl + ' (row-median $' + s.row_median.toFixed(2) + '). Derived by the lane script from the release data.',
      data: { assertion_type: 'derived_median', sku: s.sku, month: '2026-07', price_type: 'on_demand', unit: 'USD per GPU-hour', provider_median: s.provider_median, provider_count: s.provider_count, row_median: s.row_median,
        statistic: 'provider_median = median of per-provider medians; row_median = median over all price rows; zero/null prices excluded',
        preferred_statistic: 'provider_median (lane report: row medians are dominated by providers listing many instance shapes)',
        derived: true, derived_from_sha256: master.sha256, derivation: 'lane processing of _master.csv and archives, tabulated in summary/coverage.md "Median on-demand $/GPU-hr by month" and REPORT.md finding 2',
        coverage_md_sha256: inputs['opencomputeprices/summary/coverage.md'].sha256, report_md_sha256: inputs['opencomputeprices/REPORT.md'].sha256,
        caveat: s.provider_count === 1 ? 'single provider; not a market median' : 'derived figure; reproducing it requires the 10.6 GB _master.csv which is not stored with this packet' }
    });
  }

  // envelope ------------------------------------------------------------------------------------------------------
  const ws = J.ws;
  const packet = { schema: 'second-run/research-packet@1', workspace: clone(ws), sha256: await hash(ws), boundary: BOUNDARY };
  const text = JSON.stringify(packet, null, 1) + '\n';
  fs.writeFileSync(OUT, text);
  const notes = {
    packet: path.basename(OUT), packet_bytes: Buffer.byteLength(text), packet_file_sha256: sha256hex(Buffer.from(text)), envelope_sha256: packet.sha256,
    built_for_app_sha256: appSha256, built_at_fixed: BUILD_AT, events: ws.events.length, records_by_kind: J.counts,
    counts: { cmax_sources: urls.length, cmax_claims: claims.length, newsletter_rows: posts.length, newsletter_distinct_urls: byUrl.size, newsletter_urls_with_duplicate_rows: dupUrls,
      podcast_sources: podSrcId.size, podcast_quotes: quotes.length, tco_line_item_claims: tcoItems, tco_mtbf_claims: tco.goodput_presets.length, ocp_claims: stats.length },
    inputs
  };
  fs.writeFileSync(NOTES_OUT, JSON.stringify(notes, null, 1) + '\n');
  return notes;
}

module.exports = { canonical, clone, hash, safeTree, plain, loadAppCore, sha256hex, APP_SHA256, APP_HTML, build, BOUNDARY, ZERO, SCHEMA, VERSION };
if (require.main === module) build().then(n => { console.log(JSON.stringify({ ...n, inputs: undefined }, null, 1)); }).catch(e => { console.error(e); process.exit(1); });
