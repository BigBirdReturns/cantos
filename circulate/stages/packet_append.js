#!/usr/bin/env node
'use strict';
/* Append standing newsletter rows to a Research Desk packet as new `source` records, continuing its hash chain.
   Uses research-desk/packets/build_packet.js's own exported canonical/clone/hash/loadAppCore, so the events are hashed by
   the same primitives the app verifies. The base packet's events are never modified.

   node packet_append.js --packets-dir <research-desk/packets> --base <packet.json> --rows <newsletter-standing.jsonl>
                         --out <packet.json> --at <ISO time> [--prefix N] [--label TEXT]
   --prefix N   use only the first N events of the base (offline fixture-sized packet); envelope re-hashed.
   Prints one JSON line: events_before, appended, skipped_existing, events_after, file_sha256, envelope_sha256. */
const fs = require('fs');
const path = require('path');
const crypto = require('node:crypto');

const args = {};
for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
const B = require(path.resolve(args['packets-dir'], 'build_packet.js'));
const { canonical, clone, hash, ZERO, SCHEMA, VERSION, BOUNDARY } = B;
const ACTOR = 'circulate newsletter append';
const MAX_EVENTS = 3000, MAX_BYTES = 12000000;

const clip = (s, n) => (s.length <= n ? s : s.slice(0, n - 1).trimEnd() + '…');
const slugId = s => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
const sha256hex = b => crypto.createHash('sha256').update(b).digest('hex');
const rdJsonl = p => fs.readFileSync(p, 'utf8').replace(/^﻿/, '').split('\n').filter(l => l.trim()).map(l => JSON.parse(l));

(async () => {
  const base = JSON.parse(fs.readFileSync(args.base, 'utf8'));
  const ws = clone(base.workspace);
  if (args.prefix) { ws.events = ws.events.slice(0, Number(args.prefix)); }
  if (args.label) ws.label = args.label;
  const events = ws.events;
  const before = events.length;
  const latest = new Map();
  for (const e of events) if (e.type === 'record') latest.set(e.payload.id, e.payload);
  const rows = rdJsonl(args.rows);
  let appended = 0, skipped = 0;
  const PREVIEW_MAX = 600;
  for (const p of rows) {
    const id = 'sa-post-' + slugId(p.slug).slice(0, 80);
    if (latest.has(id)) { skipped++; continue; }
    const prevText = p.free_preview_text || '';
    const rec = clone({
      id, kind: 'source', tier: 'public_observation', disposition: 'observed', deps: [],
      title: clip((p.title && p.title !== 'UNVERIFIED') ? p.title : p.slug, 240),
      summary: clip((p.paywalled ? 'Paywalled' : 'Free') + ' SemiAnalysis newsletter post, published ' + String(p.datePublished).slice(0, 10) +
        '. Free preview word count: ' + p.word_count_free + '. ' + (p.subtitle || ''), 2000),
      data: {
        url: p.url, canonical_url: p.url, slug: p.slug, sha256: p.provenance.sha256,
        sha256_of: 'raw HTML of the post as fetched (GET ' + p.url + ')', bytes: p.bytes,
        retrieved_utc: p.provenance.retrieved_at, published: p.datePublished, authors: p.authors, subtitle: p.subtitle || null,
        paywalled: p.paywalled, free_preview_word_count: p.word_count_free, companies_mentioned_in_free_text: p.companies_mentioned,
        free_preview_excerpt: prevText.slice(0, PREVIEW_MAX), free_preview_excerpt_truncated: prevText.length > PREVIEW_MAX,
        free_preview_original_chars: prevText.length, free_preview_original_sha256: sha256hex(Buffer.from(prevText, 'utf8')),
        preview_note: 'Preview text truncated to ' + PREVIEW_MAX + ' chars for this packet. Extracted by circulate/newsletter@1 from the visible text of the article body before the paywall (the earlier lane extractor captured page-head markup instead).',
        extractor_warning: p.extractor_warning || null,
        refetch_note: 'Live post may have changed since retrieval; the SHA-256 is of raw HTML bytes and may not reproduce for dynamic Substack markup.'
      },
      revision: 1
    });
    const body = { seq: events.length + 1, prev: events.at(-1)?.hash || ZERO, type: 'record', actor: ACTOR, at: args.at, payload: rec };
    events.push({ ...body, hash: await hash(body) });
    latest.set(id, rec);
    appended++;
  }
  if (events.length > MAX_EVENTS) { console.log(JSON.stringify({ error: 'event_limit', events_after: events.length, limit: MAX_EVENTS })); process.exit(3); }
  const packet = { schema: 'second-run/research-packet@1', workspace: clone(ws), sha256: await hash(ws), boundary: BOUNDARY };
  const text = JSON.stringify(packet, null, 1) + '\n';
  if (text.length > MAX_BYTES) { console.log(JSON.stringify({ error: 'byte_limit', bytes: text.length })); process.exit(3); }
  fs.mkdirSync(path.dirname(args.out), { recursive: true });
  fs.writeFileSync(args.out, text);
  console.log(JSON.stringify({ events_before: before, appended, skipped_existing: skipped, events_after: events.length,
    bytes: Buffer.byteLength(text), file_sha256: sha256hex(Buffer.from(text)), envelope_sha256: packet.sha256 }));
})().catch(e => { console.error(e); process.exit(1); });
