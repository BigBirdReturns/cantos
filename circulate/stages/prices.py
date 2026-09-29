"""Stage prices: OpenComputePrices `latest-data` release, asset digests compared with the last recorded set.

The release is a rolling tag of eight assets (one 967 MB tarball plus monthly archives). This stage
  1. reads the release through gh api and records every asset digest,
  2. diffs them against INDEX.json["release_assets"] (bootstrapped once, see below),
  3. if a digest changed and the changed data can be turned into rows, appends only NEW snapshot days to
     hot-aisle/data/price-history/INDEX.json (sha256 per day; per-day files go to retained/), else HOLDs.

It never interpolates a missing day and never overwrites a recorded day. Converting the release CSVs into the
normalized rows that build_price_history.py reads (the lane's prices.jsonl) is not automated: a changed digest
online is a HOLD that names the changed assets, it does not fabricate rows. Offline, the fixture slice (50 real
rows) stands in for the converted rows so the append path runs end to end.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from stages._common import (FAIL, HOLD, OK, SKIP, Hold, Stage, import_by_path, iso, read_json, sha256_bytes,
                            sha256_file, write_json)

NAME = 'prices'
INDEX = 'hot-aisle/data/price-history/INDEX.json'
RELEASE_API = 'repos/thatkavish/OpenComputePrices/releases/tags/latest-data'
LANE_SHA = 'public-tail-20260929/lanes/opencomputeprices/sha256.txt'


def sessions_dir(ctx) -> Path:
    return Path(os.environ.get('CIRCULATE_SESSIONS') or (ctx.repo.parent / 'sessions'))


def observed_assets(release: dict) -> dict:
    return {a['name']: {'digest': a.get('digest'), 'size': a.get('size'), 'updated_at': a.get('updated_at')}
            for a in release.get('assets', [])}


def lane_baseline(ctx):
    p = sessions_dir(ctx) / LANE_SHA
    if not p.exists():
        return None
    out = {}
    for line in p.read_text(encoding='utf-8').splitlines():
        parts = line.split()
        if len(parts) == 2:
            out[parts[1].lstrip('*')] = 'sha256:' + parts[0]
    return out


def apply_rows(ctx, s, rows_path: Path, release: dict, index: dict):
    """Run build_price_history.py's own builder over a rows file into a scratch dir and append only new days."""
    market = ctx.repo / 'hot-aisle/campaign/market'
    bph = import_by_path('circulate_bph', market / 'build_price_history.py')
    work = ctx.stage_dir() / 'build'
    shutil.rmtree(work, ignore_errors=True)
    (work / 'aux').mkdir(parents=True)
    bph.ROWS = str(rows_path).replace('\\', '/')
    bph.OUT = str(work / 'price-history').replace('\\', '/')
    bph.HERE = str(work / 'aux')
    tarball = observed_assets(release).get('data.tar.gz', {})
    bph.LANE_REL = ctx.rel(rows_path)
    bph.RELEASE = dict(bph.RELEASE, release_title=release.get('name'), release_updated=(tarball.get('updated_at') or '')[:10],
                       retrieved_utc=ctx.today.isoformat())
    stderr, sys.stderr = sys.stderr, open(os.devnull, 'w')
    try:
        bph.main()
    finally:
        sys.stderr.close()
        sys.stderr = stderr
    built = read_json(work / 'price-history' / 'INDEX.json')
    day_dir = ctx.retained / 'price-history'
    added = []
    for p, pv in built['providers'].items():
        have = index['providers'].setdefault(p, {'name': pv['name'], 'first': None, 'last': None, 'days': 0, 'files': []})
        known = {f['date'] for f in have['files']}
        for f in pv['files']:
            if f['date'] in known:
                continue
            have['files'].append(f)
            dst = day_dir / p / f"{f['date']}.json"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(work / 'price-history' / p / f"{f['date']}.json", dst)
            added.append((p, f['date']))
        have['files'].sort(key=lambda x: x['date'])
        if have['files']:
            have.update(first=have['files'][0]['date'], last=have['files'][-1]['date'], days=len(have['files']))
    if added:
        index['series_range']['last'] = max(index['series_range']['last'], max(d for _, d in added))
        index.setdefault('circulate_updates', []).append({
            'run_date': ctx.today.isoformat(), 'rows_file': ctx.rel(rows_path), 'rows_sha256': sha256_file(rows_path),
            'release_title': release.get('name'), 'days_added': sorted({d for _, d in added}), 'provider_days_added': len(added)})
    return added


def run(ctx):
    s = Stage(ctx, NAME)
    idx_real = ctx.repo / INDEX
    if ctx.offline:
        ctx.seed(INDEX, ctx.fixtures / 'prices' / 'INDEX.seed.json')
        release = read_json(ctx.fixtures / 'prices' / 'release-latest-data.json')
        s.source('fixture:circulate/fixtures/prices/release-latest-data.json', (ctx.fixtures / 'prices' / 'release-latest-data.json').read_bytes())
    else:
        try:
            status, headers, body = ctx.gh(RELEASE_API)
        except Hold as h:
            return s.hold(h)
        if status != 200:
            return s.hold(Hold(f'release API returned HTTP {status}', http=status))
        release = json.loads(body)
        s.source(f'https://api.github.com/{RELEASE_API}', body)
    index_path = ctx.out(INDEX) if ctx.offline else idx_real
    index = json.loads(index_path.read_text(encoding='utf-8'))
    now_assets = observed_assets(release)
    s.counts.update(assets=len(now_assets), days_before=sum(p['days'] for p in index['providers'].values()))
    recorded = (index.get('release_assets') or {}).get('assets')

    def record(basis):
        index['release_assets'] = {'observed_utc': iso(), 'basis': basis, 'release_title': release.get('name'), 'assets': now_assets}

    if not recorded:
        base = lane_baseline(ctx)
        if base is not None and all(base.get(n) == a['digest'] for n, a in now_assets.items()) and set(base) == set(now_assets):
            record('bootstrap: every asset digest equals the lane sha256.txt captured 2026-09-29 (sessions/public-tail-20260929/lanes/opencomputeprices)')
        elif base is None and (index.get('generated_from', {}).get('release', {}).get('release_title') == release.get('name')):
            record('bootstrap: release title equals the title INDEX.json was built from; asset digests were not independently comparable (lane files absent)')
        else:
            return s.done(HOLD, 'no recorded asset digests and the release does not match what INDEX.json was built from; '
                                'cannot tell what changed. Not refreshed.')
        index_path.write_text(json.dumps(index, indent=1) + '\n', encoding='utf-8', newline='\n')
        s.output(index_path)
        return s.done(OK, 'baseline asset digests recorded; release unchanged since the INDEX build (' + release.get('name', '') + ').')

    changed = sorted(n for n, a in now_assets.items() if (recorded.get(n) or {}).get('digest') != a['digest'])
    removed = sorted(set(recorded) - set(now_assets))
    s.counts.update(changed_assets=len(changed), removed_assets=len(removed))
    if not changed and not removed:
        return s.done(SKIP, f'release unchanged: all {len(now_assets)} asset digests equal the recorded set ({release.get("name")}).')
    if not ctx.offline:
        detail = ', '.join(f"{n} ({now_assets[n]['size']} bytes, updated {now_assets[n]['updated_at']})" for n in changed)
        return s.done(HOLD, f'release changed: {detail or "assets removed: " + ", ".join(removed)}. Not downloaded: turning the release CSVs '
                            'into the normalized rows build_price_history.py reads is not automated, and no price is guessed from an '
                            'unconverted file. Recorded digests left as they were so this stays visible.')
    # offline: fixture rows stand in for the converted release
    rows = ctx.fixtures / 'prices' / 'rows-slice.jsonl'
    s.source('fixture:circulate/fixtures/prices/rows-slice.jsonl', sha=sha256_file(rows))
    added = apply_rows(ctx, s, rows, release, index)
    record('fixture: slice applied offline')
    index_path.write_text(json.dumps(index, indent=1) + '\n', encoding='utf-8', newline='\n')
    s.output(index_path)
    s.counts.update(provider_days_added=len(added), days_after=sum(p['days'] for p in index['providers'].values()),
                    day_files_retained=len(added))
    if not added:
        return s.done(SKIP, 'digest changed but the rows contained no day that is not already recorded.')
    return s.done(OK, f'{len(added)} provider-days appended from the fixture slice (never overwrites a recorded day).')
