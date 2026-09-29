"""Stage inferencex: new SemiAnalysisAI/InferenceX results_bmk artifacts since the backfill index.

Lists artifacts (gh api, newest first) until a page holds nothing new, downloads at most MAX_NEW new ones,
imports them with backfill/importer.py's own inferencemax adapter (imported-observation@1), and appends:
  hot-aisle/campaign/backfill/imported/daily/<date>.jsonl.gz   new rows only
  hot-aisle/campaign/backfill/imported/history-index.json     one entry per artifact
  hot-aisle/campaign/backfill/IMPORT-SUMMARY.md               a marked standing table
Raw artifact bytes go to retained/. An artifact the importer refuses is recorded as status "refused" with the
importer's message: no count is invented for it.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

from stages._common import (FAIL, HOLD, OK, SKIP, Hold, Stage, gz_read_lines, gz_write_lines, iso, read_json,
                            sha256_bytes, write_json)

NAME = 'inferencex'
MAX_NEW = 500
REPO_API = 'repos/SemiAnalysisAI/InferenceX/actions/artifacts'
BF = 'hot-aisle/campaign/backfill'
INDEX = f'{BF}/imported/history-index.json'
SUMMARY = f'{BF}/IMPORT-SUMMARY.md'
BEGIN, END = '<!-- circulate:standing:begin -->', '<!-- circulate:standing:end -->'
ZIP_LIMIT = 64 * 1024 * 1024


def backfill_importer(ctx):
    bf = str(ctx.repo / BF)
    if bf not in sys.path:
        sys.path.insert(0, bf)
    import importer  # noqa: E402  (hot-aisle/campaign/backfill/importer.py, unchanged)
    return importer


def list_new(ctx, index, s):
    """Newest-first listing. Returns (new_artifacts, capped, pages)."""
    new, seen_ids, pages = [], set(), 0
    if ctx.offline:
        listing = read_json(ctx.fixtures / 'inferencex' / 'listing.json')
        pages_data = [listing['artifacts']]
        s.source('fixture:circulate/fixtures/inferencex/listing.json', (ctx.fixtures / 'inferencex' / 'listing.json').read_bytes())
    else:
        pages_data = None
    page = 1
    while True:
        if pages_data is not None:
            arts = pages_data.pop(0) if pages_data else []
        else:
            status, headers, body = ctx.gh(f'{REPO_API}?name=results_bmk&per_page=100&page={page}')
            if status != 200:
                raise Hold(f'artifact listing returned HTTP {status}', http=status)
            s.source(f'https://api.github.com/{REPO_API}?name=results_bmk&per_page=100&page={page}', body)
            arts = json.loads(body)['artifacts']
        pages += 1
        fresh = 0
        for a in arts:
            if a.get('name') != 'results_bmk' or a['id'] in seen_ids:
                continue
            seen_ids.add(a['id'])
            if str(a['id']) in index or a.get('expired'):
                continue
            new.append(a)
            fresh += 1
        if not arts or fresh == 0:
            break
        if len(new) >= MAX_NEW:
            break
        page += 1
    new.sort(key=lambda a: a['id'])
    capped = len(new) >= MAX_NEW
    return new[:MAX_NEW], capped, len(new), pages


def fetch_agg(ctx, a):
    """Return the root agg_bmk.json bytes of one artifact zip."""
    aid = a['id']
    if ctx.offline:
        raw = (ctx.fixtures / 'inferencex' / f'results_bmk_{aid}' / 'agg_bmk.json').read_bytes()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:      # exercise the real unzip path
            z.writestr('agg_bmk.json', raw)
        archive = buf.getvalue()
    else:
        status, headers, archive = ctx.gh(f'{REPO_API}/{aid}/zip')
        if status == 410:
            return None, 'artifact expired (HTTP 410)'
        if status != 200:
            raise Hold(f'artifact {aid} zip returned HTTP {status}', http=status)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        names = [i for i in z.infolist() if i.filename == 'agg_bmk.json']
        if len(names) != 1 or names[0].file_size > ZIP_LIMIT:
            return None, 'zip lacks exactly one bounded root agg_bmk.json'
        return z.read(names[0]), None


def standing_block(ctx, index, daily_dir_files, base_count):
    rows_by_group = defaultdict(lambda: [0, 0, 0])
    per_day = []
    for f in daily_dir_files:
        seen, n_obs, arts = set(), 0, set()
        for line in gz_read_lines(f):
            r = json.loads(line)
            n_obs += 1
            k = (r['provenance'].get('artifact_id'), r['provenance']['sha256'], r['row_index'])
            arts.add(r['provenance'].get('artifact_id'))
            if k in seen:
                continue
            seen.add(k)
            g = rows_by_group[(r['hardware'], r['framework'], r['workload']['scenario'])]
            g[0] += 1
            if r.get('num_requests_total') is not None and r.get('num_requests_successful') is not None:
                g[1] += r['num_requests_successful']
                g[2] += r['num_requests_total']
        day = f.name.split('.')[0]
        entries = [v for v in index.values() if v.get('daily_file') == f'daily/{f.name}']
        per_day.append((day, len(entries), len(seen), n_obs, sum(1 for v in entries if v.get('source_rows') == 0)))
    refused = sum(1 for v in index.values() if v.get('status') == 'refused')
    new_total = sum(1 for v in index.values() if 'listed_utc' in v)
    lines = ['### Standing additions (circulate)', '',
             '**Imported external observations; not our measurements or qualified results.** Written by `circulate/stages/inferencex.py`; '
             'rows are `imported-observation@1` from the same adapter as the full-history import, appended under `imported/daily/`.', '',
             f'Updated {ctx.today.isoformat()}. `history-index.json` holds {len(index)} artifacts ({base_count} in the 2026-09-29 baseline, '
             f'{new_total} added since, {refused} refused by the importer and kept with the reason).', '']
    if per_day:
        lines += ['| Day file | New artifacts | Source rows | Metric observations | Empty aggregates |', '|---|---:|---:|---:|---:|']
        lines += [f'| {d} | {a} | {r} | {o} | {e} |' for d, a, r, o, e in per_day]
        lines += ['', '| Hardware | Framework | Scenario | Rows | Successful / total |', '|---|---|---|---:|---:|']
        for (hw, fw, sc), (n, ok, tot) in sorted(rows_by_group.items()):
            lines.append(f'| {hw} | {fw} | {sc} | {n} | ' + (f'{ok} / {tot}' if tot else 'unknown') + ' |')
    else:
        lines.append('No artifact has been added since the baseline.')
    return '\n'.join(lines)


def write_summary(ctx, block, s):
    real = ctx.repo / SUMMARY
    if ctx.offline:
        ctx.seed(SUMMARY, real)
    path = ctx.out(SUMMARY)
    text = path.read_text(encoding='utf-8') if path.exists() else (real.read_text(encoding='utf-8') if real.exists() else '')
    full = f'{BEGIN}\n{block.rstrip()}\n{END}'
    b, e = text.find(BEGIN), text.find(END)
    if b != -1 and e > b:
        new = text[:b] + full + text[e + len(END):]
    else:
        i = text.find('\n## ')
        new = (text[:i] + '\n\n' + full + '\n' + text[i:]) if i != -1 else text.rstrip('\n') + '\n\n' + full + '\n'
    if new != text:
        path.write_text(new, encoding='utf-8', newline='\n')
    s.output(path)


def run(ctx):
    s = Stage(ctx, NAME)
    importer = backfill_importer(ctx)
    if ctx.offline:
        ctx.seed(INDEX, ctx.fixtures / 'inferencex' / 'history-index.seed.json')
    index_path = ctx.out(INDEX) if ctx.offline else ctx.repo / INDEX
    index = json.loads(index_path.read_text(encoding='utf-8'))
    base_count = sum(1 for v in index.values() if 'listed_utc' not in v)
    try:
        new, capped, total_new, pages = list_new(ctx, index, s)
    except Hold as h:
        return s.hold(h)
    s.counts.update(index_before=len(index), listing_pages=pages, new_artifacts_found=total_new, downloaded=0, imported=0,
                    empty=0, refused=0, source_rows=0, metric_observations=0, capped_at=MAX_NEW if capped else None)
    ctx.log(f'{len(index)} artifacts already indexed; {total_new} new in the listing ({pages} page(s))')
    raw_dir = ctx.stage_dir() / 'raw'
    daily_rel = f'{BF}/imported/daily/{ctx.today.isoformat()}.jsonl.gz'
    daily_path = ctx.out(daily_rel)
    added_lines, entries_added, held = [], {}, None
    if new:
        manifest_hash = sha256_bytes(json.dumps([a['id'] for a in new], sort_keys=True).encode())
        for n, a in enumerate(new, 1):
            aid = str(a['id'])
            run_info = a.get('workflow_run') or {}
            try:
                raw, why = fetch_agg(ctx, a)
            except Hold as h:
                held = h
                break
            if n % 50 == 0 and not ctx.offline:
                ctx.rate_check()
            if raw is None:
                entries_added[aid] = {'artifact_id': a['id'], 'created_at': a.get('created_at'), 'head_sha': run_info.get('head_sha'),
                                      'workflow_run_id': run_info.get('id'), 'status': 'expired' if 'expired' in why else 'refused',
                                      'reason': why, 'listed_utc': iso(), 'daily_file': None}
                s.counts['refused'] += 1
                continue
            s.counts['downloaded'] += 1
            folder = raw_dir / f'results_bmk_{aid}'
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'agg_bmk.json').write_bytes(raw)
            sha = sha256_bytes(raw)
            retrieved = iso()
            entry = {'source': 'inferencemax', 'path': f'results_bmk_{aid}/agg_bmk.json',
                     'url': f'https://api.github.com/repos/SemiAnalysisAI/InferenceX/actions/artifacts/{aid}',
                     'revision': run_info.get('head_sha') or 'UNVERIFIED', 'retrieved_at': retrieved, 'observed_at': None,
                     'sha256': sha, 'artifact_id': a['id'], 'workflow_run_id': run_info.get('id'),
                     'head_sha': run_info.get('head_sha'), 'created_at': a.get('created_at')}
            write_json(folder / 'artifact.json', {k: entry[k] for k in ('artifact_id', 'created_at', 'head_sha', 'workflow_run_id')}
                       | {'sha256': sha, 'retrieved_at': retrieved, 'zip_digest': a.get('digest')})
            s.source(entry['url'], sha=sha)
            base = {'artifact_id': a['id'], 'created_at': a.get('created_at'), 'head_sha': run_info.get('head_sha'),
                    'workflow_run_id': run_info.get('id'), 'sha256': sha, 'retrieved_at': retrieved}
            try:
                rows = importer.inferencemax(entry, raw, manifest_hash, False)
                src_rows = len(json.loads(raw))
            except (ValueError, KeyError, TypeError) as e:
                # loud refusal, no count invented
                entries_added[aid] = base | {'status': 'refused', 'reason': f'{type(e).__name__}: {e}', 'listed_utc': iso(),
                                             'expired': bool(a.get('expired')), 'size_in_bytes': a.get('size_in_bytes'),
                                             'source_rows': None, 'metric_observations': None, 'zip_digest': a.get('digest'),
                                             'daily_file': None}
                s.counts['refused'] += 1
                ctx.log(f'REFUSED {aid}: {e}')
                continue
            for r in rows:
                added_lines.append(json.dumps(r, sort_keys=True, allow_nan=False))
            entries_added[aid] = base | {'status': 'imported', 'listed_utc': iso(), 'expired': bool(a.get('expired')),
                                         'size_in_bytes': a.get('size_in_bytes'), 'source_rows': src_rows,
                                         'metric_observations': len(rows), 'zip_digest': a.get('digest'),
                                         'daily_file': f'daily/{daily_path.name}'}
            s.counts['imported'] += 1
            s.counts['empty'] += 1 if src_rows == 0 else 0
            s.counts['source_rows'] += src_rows
            s.counts['metric_observations'] += len(rows)
    # rows: dedupe on the immutable observation id, append to today's day file
    if added_lines:
        existing = [line.rstrip('\n') for line in gz_read_lines(daily_path)] if daily_path.exists() else []
        seen = {json.loads(l)['id'] for l in existing}
        fresh = [l for l in added_lines if json.loads(l)['id'] not in seen]
        gz_write_lines(daily_path, existing + fresh)
        s.output(daily_path)
    if entries_added:
        index.update(entries_added)
        index_path.write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8', newline='\n')
        s.output(index_path)
    day_files = sorted((daily_path.parent).glob('*.jsonl.gz')) if daily_path.parent.exists() else []
    if entries_added or day_files:
        write_summary(ctx, standing_block(ctx, index, day_files, base_count), s)
    if held is not None:
        s.counts['held_at_artifact'] = held.args[0][:120]
        return s.hold(held)
    if not new:
        return s.done(SKIP, f'nothing new: all {len(index)} listed artifacts are already in history-index.json')
    note = f'{s.counts["imported"]} artifacts imported ({s.counts["source_rows"]} source rows, {s.counts["metric_observations"]} metric observations, ' \
           f'{s.counts["empty"]} empty), {s.counts["refused"]} refused.'
    if capped:
        note += f' Capped at {MAX_NEW} new artifacts this run; the listing may hold more (found at least {total_new}); the rest are picked up next run.'
    return s.done(OK, note)
