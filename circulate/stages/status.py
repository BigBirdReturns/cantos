"""Stage status: standing incident files for every provider in retrospective/status-pages.json whose platform
has a collector (atlassian-history, atlassian, betterstack, instatus, sorryapp).

Uses scripts/collect_status.py unchanged for the Atlassian modes and the three modes added with this driver.
Writes retrospective/incidents/<slug>-standing.json (never a file R1 or R2 read) and COLLECTION-LOG-standing.md.
A provider whose page cannot be read is recorded with the HTTP code / reason and gets no file; a platform
mismatch is recorded UNSUPPORTED, never turned into an empty incident file. Raw pages go to retained/.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
from datetime import date, timedelta
from pathlib import Path

from stages._common import FAIL, HOLD, OK, SKIP, Hold, Stage, import_by_path, read_json, write_json

NAME = 'status'
INC = 'clustermax-challenge/retrospective/incidents'
LOG = f'{INC}/COLLECTION-LOG-standing.md'
FETCH_DAYS = 200          # a little beyond the 180-day R2 window so a page/quarter straddling the boundary is covered
WINDOW_DAYS = 180
OFFLINE_DAYS = 60

# status-pages.json "platform" text -> collector mode
def mode_for(platform: str | None):
    p = (platform or '').lower()
    if p.startswith('atlassian'):
        return 'atlassian-history'
    if p.startswith('incident.io'):
        return 'atlassian'
    if p in ('betterstack', 'betteruptime', 'better stack', 'better uptime'):
        return 'betterstack'
    if p.startswith('instatus'):
        return 'instatus'
    if p.startswith('sorryapp'):
        return 'sorryapp'
    return None


def base_slug(name: str, pmap: dict, slugify) -> str:
    stripped = re.sub(r'\s*\(.*?\)\s*', ' ', name).strip()
    return pmap.get(name) or pmap.get(stripped) or slugify(stripped)


def fixture_providers(ctx):
    fx = ctx.fixtures / 'status'
    return [
        {'rating_name': 'Crusoe', 'status_url': 'https://status.crusoecloud.com', 'platform': 'atlassian-statuspage'},
        {'rating_name': 'Verda (formerly DataCrunch)', 'status_url': 'https://status.verda.com', 'platform': 'betterstack'},
        {'rating_name': 'Mithril', 'status_url': 'https://status.mithril.ai', 'platform': 'instatus'},
        {'rating_name': 'Radiant', 'status_url': 'https://status.radiant.co', 'platform': 'sorryapp'},
    ], fx


def fixture_fetch(fx: Path):
    from datetime import datetime, timezone

    def fetch(url):
        path = None
        m = re.match(r'https://status\.crusoecloud\.com/history\.json\?page=(\d+)$', url)
        if m and m.group(1) == '1':
            path = 'crusoe/history-page-1.json'
        m = re.match(r'https://status\.crusoecloud\.com/incidents/(\w+)\.json$', url)
        if m:
            path = f'crusoe/incident-{m.group(1)}.json'
        m = re.match(r'https://status\.verda\.com/incidents/2026-07/2026-09$', url)
        if m:
            path = 'verda/incidents_2026-07_2026-09.html'
        m = re.match(r'https://status\.verda\.com/incident/(\d+)$', url)
        if m:
            path = f'verda/incident_{m.group(1)}.html'
        m = re.search(r'/public/status\.mithril\.ai/notices/monthly/(\d+)\?page_no=(\d+)$', url)
        if m:
            d = datetime.fromtimestamp(int(m.group(1)) / 1000, timezone.utc)
            path = f'mithril/notices_{d.year}-{d.month:02d}_p{m.group(2)}.json'
        m = re.match(r'https://status\.radiant\.co/history/2026/september$', url)
        if m:
            path = 'radiant/history_2026-september.html'
        p = fx / path if path else None
        if p is None or not p.exists():
            raise urllib.error.HTTPError(url, 404, 'not found (fixture)', {}, None)
        return p.read_bytes()
    return fetch


def collect_one(ctx, cs, prov, mode, slug, out_root, fetch, start, page_stop, cov_req):
    url = prov['status_url']
    if mode == 'atlassian-history':
        return cs.collect_atlassian_history(slug, url, out_root, fetch=fetch, page_stop_before=page_stop,
                                            coverage_requires_before=cov_req, sleep_fn=(lambda s: None) if ctx.offline else __import__('time').sleep)
    if mode == 'atlassian':
        return cs.collect_atlassian(slug, url, out_root, fetch=fetch)
    kw = dict(start=start, today=ctx.today)
    if ctx.offline:
        kw['sleep_fn'] = lambda s: None
    if mode == 'betterstack':
        return cs.collect_betterstack(slug, url, out_root, fetch=fetch, **kw)
    if mode == 'instatus':
        return cs.collect_instatus(slug, url, out_root, fetch=fetch, **kw)
    if mode == 'sorryapp':
        return cs.collect_sorryapp(slug, url, out_root, fetch=fetch, **kw)
    raise ValueError(mode)


def http_code(exc):
    text = str(exc)
    m = re.search(r'HTTP(?: Error)? (\d{3})', text)
    return int(m.group(1)) if m else None


def run(ctx):
    s = Stage(ctx, NAME)
    ch = ctx.repo / 'clustermax-challenge'
    cs = import_by_path('circulate_collect_status', ch / 'scripts' / 'collect_status.py')
    r2 = import_by_path('circulate_run_r2_for_slugs', ch / 'retrospective' / 'run_r2.py')   # only for the shared slug map
    retro = ch / 'retrospective'
    pmap = dict(read_json(retro / 'provider_map.json'))
    pmap.update(read_json(retro / 'provider_map_R2.json'))
    slugify = r2.R.slugify
    if ctx.offline:
        providers, fx = fixture_providers(ctx)
        fetch = fixture_fetch(fx)
        days = OFFLINE_DAYS
        s.source('fixture:circulate/fixtures/status/MANIFEST.json', (fx / 'MANIFEST.json').read_bytes())
    else:
        providers = read_json(retro / 'status-pages.json')['providers']
        fetch = None
        days = FETCH_DAYS
    start = ctx.today - timedelta(days=days)
    start_q = start
    page_stop = start
    cov_req = ctx.today - timedelta(days=days - 20 if days > 60 else days)   # 180 online
    out_root = ctx.stage_dir() / 'raw-root'
    rows, outputs = [], []
    counts = {'providers_in_file': len(providers), 'collected': 0, 'hold': 0, 'unsupported': 0, 'failed': 0, 'no_collector': 0,
              'incidents': 0}
    for prov in providers:
        name = prov['rating_name']
        mode = mode_for(prov.get('platform'))
        if not prov.get('status_url') or mode is None:
            counts['no_collector'] += 1
            rows.append({'name': name, 'platform': prov.get('platform'), 'mode': None, 'outcome': 'NO COLLECTOR',
                         'detail': 'no status page' if not prov.get('status_url') else f'platform {prov.get("platform")!r} has no collector'})
            continue
        slug = base_slug(name, pmap, slugify) + '-standing'
        f = fetch
        if f is None:
            f = cs.default_fetch_paced if mode in ('atlassian-history', 'betterstack', 'instatus', 'sorryapp') else cs.default_fetch
        ctx.log(f'{name}: {mode} -> {slug}')
        try:
            doc = collect_one(ctx, cs, prov, mode, slug, out_root, f, start_q, page_stop, cov_req)
        except cs.UnsupportedPlatform as e:
            counts['unsupported'] += 1
            rows.append({'name': name, 'platform': prov.get('platform'), 'mode': mode, 'outcome': 'UNSUPPORTED', 'detail': str(e)[:200]})
            continue
        except cs.CollectorError as e:
            counts['hold'] += 1
            rows.append({'name': name, 'platform': prov.get('platform'), 'mode': mode, 'outcome': 'HOLD',
                         'http': http_code(e), 'detail': str(e)[:200]})
            continue
        except Exception as e:  # noqa: BLE001 - a parser bug must show as FAIL, not disappear
            counts['failed'] += 1
            rows.append({'name': name, 'platform': prov.get('platform'), 'mode': mode, 'outcome': 'FAIL',
                         'detail': f'{type(e).__name__}: {e}'[:200]})
            ctx.log(f'FAIL {name}: {type(e).__name__}: {e}')
            continue
        problems = cs.validate_doc(doc)
        if problems:
            counts['failed'] += 1
            rows.append({'name': name, 'platform': prov.get('platform'), 'mode': mode, 'outcome': 'FAIL',
                         'detail': 'schema: ' + '; '.join(problems[:3])})
            continue
        doc['provider'] = name
        doc.setdefault('notes', []).insert(0, f'STANDING collection {ctx.today.isoformat()} by circulate; not read by R1 or R2. '
                                             f'Raw pages (with SHA-256 above) are kept in the CI artifact / retained/, not committed.')
        path = ctx.out(f'{INC}/{slug}.json')
        write_json(path, doc)
        s.output(path)
        # one source row per provider: the hash of its sorted raw-page hashes (every page's own hash is in the standing file)
        import hashlib
        combined = hashlib.sha256(','.join(sorted(rf['sha256'] for rf in doc['raw_files'])).encode()).hexdigest()
        s.sources.append({'url': prov['status_url'], 'sha256': combined, 'retrieved_utc': doc['retrieved_utc'],
                          'pages': len(doc['raw_files'])})
        real = [i for i in doc['incidents'] if not i['is_maintenance']]
        counts['collected'] += 1
        counts['incidents'] += len(doc['incidents'])
        rows.append({'name': name, 'platform': prov.get('platform'), 'mode': mode, 'outcome': 'OK', 'file': f'{slug}.json',
                     'incidents': len(doc['incidents']), 'non_maintenance': len(real),
                     'coverage': f'{doc["coverage_start"]}..{doc["coverage_end"]}', 'raw_pages': len(doc['raw_files'])})
    log_lines = [f'# Standing incident collection, {ctx.today.isoformat()}', '',
                 'Written by `circulate/stages/status.py`. Files are `<slug>-standing.json`; the frozen R1/R2 incident files are not touched. '
                 f'Window fetched: about {days} days back from {ctx.today.isoformat()}; coverage_start is the first day of the oldest page/month/quarter '
                 'actually fetched, never inferred from the oldest incident. A provider that could not be read has no file; nothing is filled in.', '',
                 '| Provider | Platform | Mode | Outcome | Incidents (non-maintenance) | Coverage | Detail |', '|---|---|---|---|---|---|---|']
    for r in rows:
        inc = f'{r["incidents"]} ({r["non_maintenance"]})' if r['outcome'] == 'OK' else ''
        detail = r.get('file') or ((f'HTTP {r["http"]}: ' if r.get('http') else '') + r.get('detail', ''))
        log_lines.append(f'| {r["name"]} | {r.get("platform") or ""} | {r.get("mode") or ""} | {r["outcome"]} | {inc} | {r.get("coverage", "")} | {str(detail).replace("|", "/")} |')
    lp = ctx.out(LOG)
    lp.write_text('\n'.join(log_lines) + '\n', encoding='utf-8', newline='\n')
    s.output(lp)
    s.counts.update(counts)
    if counts['failed']:
        return s.done(FAIL, f'{counts["failed"]} provider(s) failed inside the collector code (parser bug or schema problem); see log. '
                            f'{counts["collected"]} collected.', error='; '.join(f'{r["name"]}: {r["detail"]}' for r in rows if r['outcome'] == 'FAIL')[:500])
    if not counts['collected']:
        return s.done(HOLD, f'no provider could be read ({counts["hold"]} unreachable, {counts["unsupported"]} platform mismatch).')
    return s.done(OK, f'{counts["collected"]} providers collected ({counts["incidents"]} incident records); {counts["hold"]} unreachable (HOLD), '
                      f'{counts["unsupported"]} unsupported, {counts["no_collector"]} without a collector.')
