// Run the existing Canon evidence validator; never grant reviewed standing.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { stripTypeScriptTypes } from 'node:module';

const commit = 'fec0ddc9a5697d465ac46e55b7e3cb7647221952';
const pins = {
  'src/canon/reconcile/types.ts': 'c8ad6a9b3dbeb8a6c773dd779a269466fb2648d77d984672e07e1ac29de76ba9',
  'src/canon/reconcile/validate.ts': 'df86e85344d8c6071dfa38096fbfc8b09c5b759a66577b454b9fe2e2a7d9528c',
  'src/canon/reconcile/canonical.ts': 'a4ac6378a49a0491a1ee868367146aff331a685b386b395ff39e88dcd29bb440',
  'src/runtime/determinism.ts': '6e6f3f1e7866862085a33721b3ad85c79eab9efe3b2788f82069aa643693ef9a',
  'src/runtime/fingerprint.ts': '34fd69b25fd70a1ad4d798df1c7c6bb9e5324efda35c370fc0782a37c4572cbe',
};
const args = process.argv.slice(2);
const option = key => args[args.indexOf(key) + 1];
if (!args.includes('--source-root') || !args.includes('--bundle')) {
  throw new Error('Required: --source-root <pinned scratch source> --bundle <Run3 binding> [--fetch]');
}
const sourceRoot = path.resolve(option('--source-root'));
const bundleRoot = path.resolve(option('--bundle'));
const runtime = path.join(sourceRoot, 'runtime-js');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const files = [];
for (const [relative, digest] of Object.entries(pins)) {
  const original = path.join(sourceRoot, relative);
  const url = `https://raw.githubusercontent.com/BigBirdReturns/axm-canon/${commit}/${relative}`;
  if (args.includes('--fetch')) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Source unavailable: ${response.status} ${url}`);
    const downloaded = Buffer.from(await response.arrayBuffer());
    if (sha(downloaded) !== digest) throw new Error(`Source pin mismatch: ${relative}`);
    await mkdir(path.dirname(original), { recursive: true });
    await writeFile(original, downloaded);
  }
  const bytes = await readFile(original);
  if (sha(bytes) !== digest) throw new Error(`Source pin mismatch: ${relative}`);
  const generated = path.join(runtime, relative.replace(/\.ts$/, '.js'));
  await mkdir(path.dirname(generated), { recursive: true });
  await writeFile(generated, stripTypeScriptTypes(bytes.toString('utf8'), { mode: 'strip' }));
  files.push({ path: relative, sha256: digest, url });
}
await writeFile(path.join(runtime, 'package.json'), '{"type":"module"}\n');
const { validateCanonEvidenceBundle } = await import(pathToFileURL(path.join(runtime, 'src/canon/reconcile/validate.js')));
const binding = JSON.parse(await readFile(path.join(bundleRoot, 'binding.json')));
const card = JSON.parse(await readFile(path.join(bundleRoot, 'card.json')));
const source = await readFile(path.join(bundleRoot, 'shard/content/source.txt'));
if (sha(source) !== binding.source_sha256) throw new Error('Binding source digest mismatch');
const sourceId = 'run3-card-source';
const continuityId = `run3-at0:${card.a_claim.period.experiment_date}`;
const input = {
  format: 'axm-canon-evidence-bundle/1', id: `run3:${binding.card_revision_sha256}`,
  universeId: 'compute-claims',
  sources: [{ id: sourceId, title: card.title, version: binding.card_revision_sha256,
    universeId: 'compute-claims', continuityId, custody: 'local-private',
    sourceHintIds: [card.id], digest: sha(source), fileSizeBytes: source.length }],
  locators: binding.claims.map(c => ({ id: c.span_id, sourceId, kind: 'byte',
    unit: 'UTF-8 byte offset; end exclusive', start: c.byte_start, end: c.byte_end,
    contentDigest: sha(source.subarray(c.byte_start, c.byte_end)) })),
  records: binding.claims.map(c => ({ id: c.claim_id, sourceId, locatorIds: [c.span_id],
    continuityId, kind: 'proposition', label: c.predicate,
    normalized: { value: c.object, shard_id: binding.shard_id, card_id: card.id,
      card_revision_sha256: binding.card_revision_sha256 },
    reconciliationKeys: [card.id, c.claim_id], producedBy: 'extractor',
    reviewStatus: 'machine-extracted' })),
};
const findings = validateCanonEvidenceBundle(input);
const attemptedReview = structuredClone(input);
for (const record of attemptedReview.records) record.reviewStatus = 'reviewed';
const unsupportedReview = validateCanonEvidenceBundle(attemptedReview);
const result = {
  card_id: card.id, card_revision_sha256: binding.card_revision_sha256,
  shard_id: binding.shard_id, source_commit: commit, source_files: files,
  validator: 'validateCanonEvidenceBundle', node: process.version,
  execution: 'Pinned native TypeScript, Node built-in type erasure; no replacement validator',
  input, input_sha256: sha(Buffer.from(JSON.stringify(input))), findings,
  status: findings.some(f => f.severity === 'error') ? 'FAIL' : 'PASS',
  unsupported_review: { findings: unsupportedReview,
    refused: unsupportedReview.some(f => f.code === 'missing-evidence-reviewer' && f.severity === 'error') },
  standing: 'machine-extracted/candidate', reviewer: null, accepted: false,
  boundary: 'Evidence-bundle compatibility only. Recall packet and human reconciliation are not run; no fictional domain is assigned.',
};
process.stdout.write(JSON.stringify(result) + '\n');
if (result.status !== 'PASS' || !result.unsupported_review.refused) process.exitCode = 1;
