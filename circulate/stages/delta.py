"""Stage delta: backfill/delta.py over every imported file against the retained campaign cells (../results).

delta.py's own report() does the comparison and ranking; this stage feeds it the imports in chunks (the full
history is ~290k observations) and merges the chunks: gaps concatenated, checkpoints re-ranked by (-score, id),
header counts recomputed over the union. Nothing is compared by hand and no ratio is produced outside delta.py.

Inputs, deduplicated by observation id:
  imported/inferencex-2026-09-29.jsonl  the >1 GB full history, only if the retained copy named in its POINTER
                                        file exists here AND matches the pointer's SHA-256; otherwise the
                                        100-artifact 2026-09-23 sample stands in and the output says so
  imported/mlperf-2026-09-29.jsonl, imported/daily/*.jsonl.gz
Writes DELTA-standing.md (committed) and the full ranked delta as retained/delta/delta-standing.json.gz.
"""
from __future__ import annotations

import gzip
import json
import os
import sys
from collections import Counter
from pathlib import Path

from stages._common import FAIL, HOLD, OK, SKIP, Stage, gz_read_lines, import_by_path, sha256_file

NAME = 'delta'
BF = 'hot-aisle/campaign/backfill'
OUT = f'{BF}/DELTA-standing.md'
CHUNK = 15000


def load_delta(ctx):
    bf = ctx.repo / BF
    if str(bf) not in sys.path:
        sys.path.insert(0, str(bf))
    return import_by_path('circulate_bf_delta', bf / 'delta.py', bf)


def resolve_pointer(ctx, pointer: Path):
    """(path, note) of the retained big file if present and hash-verified, else (None, why)."""
    if not pointer.exists():
        return None, 'no pointer file'
    ptr = json.loads(pointer.read_text(encoding='utf-8'))
    for base in (ctx.repo.parent, ctx.repo):
        cand = base / ptr['retained_at']
        if cand.exists():
            if cand.stat().st_size == ptr['bytes'] and sha256_file(cand) == ptr['sha256']:
                return cand, f'retained copy verified against pointer sha256 {ptr["sha256"][:16]}...'
            return None, f'retained copy at {ptr["retained_at"]} does not match the pointer (size/sha256); not used'
    return None, f'retained copy {ptr["retained_at"]} not present on this machine'


def input_files(ctx):
    imp = ctx.repo / BF / 'imported'
    files, notes = [], []
    if ctx.offline:
        files.append(('fixture sample (40 rows of the 2026-09-23 import)', ctx.fixtures / 'delta' / 'imports-sample.jsonl', False))
        sb = ctx.sandbox / BF / 'imported' / 'daily'
        for f in sorted(sb.glob('*.jsonl.gz')) if sb.exists() else []:
            files.append((f'daily {f.name} (sandbox)', f, True))
        return files, ['offline: fixtures only']
    big, why = resolve_pointer(ctx, imp / 'inferencex-2026-09-29.jsonl.POINTER.json')
    if big is not None:
        files.append(('inferencex-2026-09-29.jsonl (full history)', big, False))
    else:
        notes.append(f'full history not used: {why}; the 2026-09-23 sample stands in')
        files.append(('inferencex-2026-09-23.jsonl (100-artifact sample)', imp / 'inferencex-2026-09-23.jsonl', False))
    files.append(('mlperf-2026-09-29.jsonl', imp / 'mlperf-2026-09-29.jsonl', False))
    for f in sorted((imp / 'daily').glob('*.jsonl.gz')) if (imp / 'daily').exists() else []:
        files.append((f'daily {f.name}', f, True))
    return files, notes


def iter_rows(files):
    seen, dup = set(), 0
    for label, path, gz in files:
        lines = gz_read_lines(path) if gz else (l for l in open(path, encoding='utf-8-sig') if l.strip())
        n = 0
        for line in lines:
            r = json.loads(line)
            if r['id'] in seen:
                dup += 1
                continue
            seen.add(r['id'])
            n += 1
            yield label, r
    iter_rows.dups = dup


def src_key(r):
    return (r['provenance'].get('sha256', r['provenance'].get('path')), r['provenance'].get('artifact_id'), r['row_index'])


def run(ctx):
    s = Stage(ctx, NAME)
    dmod = load_delta(ctx)
    files, notes = input_files(ctx)
    for label, p, gz in files:
        if not p.exists():
            return s.done(HOLD, f'input missing: {label}')
        s.sources.append({'url': ctx.rel(p), 'sha256': sha256_file(p), 'retrieved_utc': None})
    cells = dmod.measured_cells(ctx.repo / BF.rsplit('/', 1)[0] / 'results')
    as_of = ctx.today
    gaps, checkpoints, keys, id_key = [], [], set(), {}
    per_file = Counter()
    buf, n_obs, chunks = [], 0, 0

    def flush():
        nonlocal buf, chunks
        if not buf:
            return
        res = dmod.report(buf, cells, as_of, False)
        gaps.extend(res['gaps'])
        checkpoints.extend(res['unreproduced'])
        chunks += 1
        buf = []

    for label, r in iter_rows(files):
        per_file[label] += 1
        n_obs += 1
        k = src_key(r)
        keys.add(k)
        id_key[r['id']] = k
        buf.append(r)
        if len(buf) >= CHUNK:
            flush()
            ctx.log(f'{n_obs} observations compared')
    flush()
    if not n_obs:
        return s.done(HOLD, 'no imported observations to compare')
    checkpoints.sort(key=lambda c: (-c['score'], c['imported_id']))
    for i, c in enumerate(checkpoints, 1):
        c['rank'] = i
    comp_ids = {g['imported_id'] for g in gaps}
    header = {'schema': 'backfill-delta@1', 'as_of': as_of.isoformat(), 'measured_cells': len(cells),
              'imported_source_rows': len(keys), 'comparable_observations': len(comp_ids),
              'comparable_source_rows': len({id_key[i] for i in comp_ids}), 'imported_observations': n_obs, 'fixture': False,
              'notice': 'Contextual raw gaps and rerun candidates only. No imported checkpoint is certified reproduced by these campaign cells.'}
    full = ctx.stage_dir() / 'delta-standing.json.gz'
    with open(full, 'wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=6) as gz:
        head = json.dumps(header, allow_nan=False)[:-1]
        gz.write((head + ', "gaps": ' + json.dumps(gaps, allow_nan=False) + ', "unreproduced": [').encode('utf-8'))
        for i, c in enumerate(checkpoints):
            gz.write((('' if i == 0 else ',') + json.dumps(c, allow_nan=False)).encode('utf-8'))
        gz.write(b']}\n')
    s.outputs.append(ctx.output(full, committed=False))
    score = Counter(c['score'] for c in checkpoints)
    by_src = Counter((c['source'], c['score']) for c in checkpoints)
    sc = ', '.join(f'score {k}: {v}' for k, v in sorted(score.items(), reverse=True))
    bs = ', '.join(f'{a} score {b}: {v}' for (a, b), v in sorted(by_src.items(), key=lambda x: (-x[1], x[0])))
    top = json.dumps(checkpoints[:10], indent=2, allow_nan=False)
    md = [f'# Delta against retained campaign cells, standing run {ctx.today.isoformat()}', '',
          f'Generated by `circulate/stages/delta.py` calling `backfill/delta.py` unchanged (`--as-of {as_of.isoformat()}`, results = `../results`, '
          f'{len(cells)} retained fixed-sequence cells). Contextual only; nothing here is a reproduction. The full ranked output is written to the CI artifact / `retained/delta/delta-standing.json.gz` '
          f'({len(checkpoints)} ranked entries), not committed.', '', '## Inputs', '']
    md += [f'- {label}: {n} observations' for label, n in per_file.items()]
    md += [f'- duplicates skipped (same observation id): {getattr(iter_rows, "dups", 0)}'] + [f'- {n}' for n in notes]
    md += ['', '## Header as emitted', '', '```json', json.dumps(header, indent=2), '```', '', '## Ranked triage', '',
           f'{len(checkpoints)} unreproduced checkpoints ranked; `gaps` holds {len(gaps)} ratios. Score distribution: {sc}. By source and score: {bs}.', '',
           'First 10 entries verbatim:', '', '```json', top, '```', '']
    if ctx.offline:
        md.insert(2, '> OFFLINE FIXTURE RUN: computed over fixture rows only; not a statement about the real history.\n')
    out = ctx.out(OUT)
    out.write_text('\n'.join(md), encoding='utf-8', newline='\n')
    s.output(out)
    s.counts.update(inputs=len(files), observations=n_obs, source_rows=len(keys), chunks=chunks, measured_cells=len(cells),
                    comparable_observations=len(comp_ids), gaps=len(gaps), ranked=len(checkpoints))
    return s.done(OK, f'{n_obs} observations vs {len(cells)} measured cells: {len(comp_ids)} comparable, {len(checkpoints)} ranked.')
