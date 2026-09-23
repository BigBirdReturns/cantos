#!/usr/bin/env python3
"""Fetch and normalize a provider's public status-page incident history into
retrospective/incidents/<slug>.json (schema secondrun.status-incidents.v1; see
retrospective/incidents/SCHEMA.md). Stdlib only.

Three collection modes:

  atlassian-history  Talks to Atlassian Statuspage's `history.json?page=N`
             endpoint, which -- unlike /api/v2/incidents.json -- is NOT capped
             at a fixed recent window: it lists every calendar month back to
             the page's creation, including empty months, three months per
             page, newest first. For each incident code found, fetches
             `/incidents/<code>.json` for the exact created_at/resolved_at/
             impact and whether it is scheduled maintenance. This is the
             correct way to get real historical depth from Atlassian
             Statuspage; an earlier pass over this repo wrongly concluded
             Atlassian history was capped because it only looked at
             /api/v2/incidents.json (see collect_atlassian below) and a
             /history?page=N HTML route that plain statuspage.io deployments
             don't serve at all.

  atlassian  Talks to an Atlassian-Statuspage-compatible /api/v2/incidents.json
             endpoint (this covers real statuspage.io instances and several
             other platforms that ship an API-compatible clone, e.g. incident.io)
             and best-effort paginates the classic HTML history at /history?page=N
             for anything the API's recent-incidents endpoint doesn't cover.
             Kept for platforms (e.g. incident.io-hosted pages) that expose
             the /api/v2 surface but not history.json; its /api/v2/incidents.json
             endpoint caps out at a fixed recent window, so coverage_start
             stays null unless pagination independently confirms the end of
             history.

  generic    Saves the raw page and does not attempt automated parsing. Pass
             --manual-json to merge a hand-authored incidents document (checked
             against this schema) that cites the saved raw HTML by its SHA-256.

`--mode auto` (default) probes history.json, then /api/v2/status.json, to pick
between the three.

This script is deliberately conservative about `coverage_start`/`coverage_end`:
it only claims a start date it can justify (pagination reached a confirmed
end of history, or a month older than the claim). See SCHEMA.md's notes on
why an API's "most recent N incidents" is not evidence that nothing older
exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

INCIDENTS_SCHEMA = 'secondrun.status-incidents.v1'
USER_AGENT = 'clustermax-retrospective-collector/0.1 (+https://github.com/second-run/axm-tools)'
HISTORY_PAGE_CAP = 40  # safety cap; ~40 months is well past any 180-day study window
NORMALIZED_SEVERITIES = ('none', 'minor', 'major', 'critical')

# history.json paging stops once a page's oldest month predates this date
# (deliberately a bit before the secondary release's window start of
# 2025-03-26, so a page that straddles the boundary still gets fetched).
HISTORY_PAGE_STOP_BEFORE = date(2025, 3, 1)
# coverage_start may only be claimed if paging reached a month older than
# this date, or ran out of pages (reached the page's own creation).
HISTORY_COVERAGE_REQUIRES_BEFORE = date(2025, 3, 26)

MONTH_NUMBERS = {
    'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
    'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12,
}

# Atlassian's own impact/severity vocabulary, plus "maintenance" for scheduled
# work (their history.json labels these incidents impact="maintenance").
HISTORY_SEVERITY_MAP = {
    'critical': 'critical', 'major': 'major', 'minor': 'minor',
    'none': 'none', 'maintenance': 'none',
}

# Be polite: at most 2 requests/second against a live status page.
MIN_REQUEST_INTERVAL = 0.5
_last_request_at = [0.0]

# Retry these as transient; anything else (404, JSON errors, ...) is not retried.
_TRANSIENT_HTTP_CODES = (429, 500, 502, 503, 504)


class CollectorError(RuntimeError):
    pass


def default_fetch(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _rate_limit_wait(sleep_fn=time.sleep) -> None:
    """Enforce <=2 requests/sec against real status pages. No-op cost for
    fixture tests, which pass their own `fetch` and never call this."""
    now = time.monotonic()
    elapsed = now - _last_request_at[0]
    if elapsed < MIN_REQUEST_INTERVAL:
        sleep_fn(MIN_REQUEST_INTERVAL - elapsed)
    _last_request_at[0] = time.monotonic()


def default_fetch_paced(url: str, timeout: float = 20.0) -> bytes:
    """Same as default_fetch but paced to <=2 requests/sec. Use this (not
    default_fetch) as the real-network fetch for history.json collection,
    which issues many more requests than the old /api/v2 collector."""
    _rate_limit_wait()
    return default_fetch(url, timeout=timeout)


def fetch_with_retry(fetch, url: str, retries: int = 3, backoff: float = 1.0, sleep_fn=time.sleep):
    """Call fetch(url), retrying transient errors up to `retries` times total
    (i.e. up to retries-1 retries after the first attempt) with linear
    backoff. Transient: 429/500/502/503/504 HTTPError, or a network-level
    URLError/timeout. Anything else (404, etc.) is raised immediately."""
    last_exc = None
    for attempt in range(retries):
        try:
            return fetch(url)
        except urllib.error.HTTPError as exc:
            if exc.code in _TRANSIENT_HTTP_CODES and attempt < retries - 1:
                last_exc = exc
                sleep_fn(backoff * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_exc = exc
            if attempt < retries - 1:
                sleep_fn(backoff * (attempt + 1))
                continue
            raise
    raise last_exc  # pragma: no cover -- loop always returns or raises above


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def rel_path(path: Path) -> str:
    try:
        return os.path.relpath(path, Path.cwd()).replace('\\', '/')
    except ValueError:
        return str(path).replace('\\', '/')


def save_raw(raw_dir: Path, filename: str, data: bytes, url: str, raw_files: list) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_bytes(data)
    raw_files.append({'path': rel_path(path), 'sha256': sha256_bytes(data), 'url': url})
    return path


# --------------------------------------------------------------------------- #
# Atlassian-Statuspage-compatible collector
# --------------------------------------------------------------------------- #

def normalize_atlassian_incident(raw: dict, base_url: str, is_maintenance: bool):
    impact = (raw.get('impact') or 'none').lower()
    severity = impact if impact in NORMALIZED_SEVERITIES else 'none'
    incident_id = raw.get('id') or raw.get('shortlink')
    if not incident_id:
        return None
    started = raw.get('scheduled_for') if is_maintenance else raw.get('started_at')
    started = started or raw.get('created_at')
    resolved = raw.get('resolved_at')
    if is_maintenance and not resolved:
        resolved = raw.get('scheduled_until')
    if not started:
        return None
    return {
        'id': incident_id, 'title': raw.get('name', ''), 'impact_label': impact,
        'severity': severity, 'started_utc': started, 'resolved_utc': resolved,
        'is_maintenance': is_maintenance,
        'url': raw.get('shortlink') or f'{base_url}/incidents/{incident_id}',
    }


# Best-effort regex for the classic Atlassian Statuspage.io history template
# (a <a class="...incident-title..." href="/incidents/<id>">Title</a> per
# incident, grouped under monthly <div class="month">). This has NOT been
# verified against a live statuspage.io instance from this environment (the
# one live smoke target available, status.lambda.ai, turned out to be an
# incident.io-hosted page with an Atlassian-compatible /api/v2 surface but no
# /history route at all -- see the note this run left in `notes`). Entries
# found here without a start timestamp are deliberately dropped rather than
# fabricated; see the loop in parse_history_html.
HISTORY_LINK_RE = re.compile(
    r'href="(?P<href>/incidents/[A-Za-z0-9_-]+)"[^>]*class="[^"]*incident-title[^"]*"[^>]*>'
    r'(?P<title>[^<]*)</a>', re.IGNORECASE)


def parse_history_html(body: bytes, base_url: str):
    text = body.decode('utf-8', 'replace')
    found = []
    for m in HISTORY_LINK_RE.finditer(text):
        href = m.group('href')
        incident_id = href.rsplit('/', 1)[-1]
        found.append({
            'id': incident_id, 'title': m.group('title').strip(), 'href': href,
            'url': base_url + href,
        })
    return found


def collect_atlassian(slug: str, base_url: str, out_root: Path, fetch=default_fetch,
                       max_history_pages: int = HISTORY_PAGE_CAP):
    base_url = base_url.rstrip('/')
    raw_dir = out_root / 'raw' / slug
    raw_files: list = []
    notes: list = []
    incidents_by_id: dict = {}

    api_url = f'{base_url}/api/v2/incidents.json'
    try:
        body = fetch(api_url)
    except Exception as exc:  # noqa: BLE001 - surfaced as CollectorError
        raise CollectorError(f'{api_url}: {exc}') from exc
    save_raw(raw_dir, 'api-v2-incidents.json', body, api_url, raw_files)
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CollectorError(f'{api_url}: not JSON: {exc}') from exc
    for raw in data.get('incidents', []):
        norm = normalize_atlassian_incident(raw, base_url, is_maintenance=False)
        if norm:
            incidents_by_id[norm['id']] = norm
    notes.append(f'{api_url} returned {len(data.get("incidents", []))} incidents '
                 '(most such endpoints cap this at a fixed recent window, commonly ~50; '
                 'it is not a complete history by itself)')

    maint_url = f'{base_url}/api/v2/scheduled-maintenances.json'
    try:
        mbody = fetch(maint_url)
        save_raw(raw_dir, 'api-v2-scheduled-maintenances.json', mbody, maint_url, raw_files)
        mdata = json.loads(mbody)
        for raw in mdata.get('scheduled_maintenances', []):
            norm = normalize_atlassian_incident(raw, base_url, is_maintenance=True)
            if norm:
                incidents_by_id[norm['id']] = norm
    except Exception as exc:  # noqa: BLE001 - optional endpoint
        notes.append(f'{maint_url} unavailable ({exc}); scheduled maintenance not separately captured')

    # Best-effort classic HTML history pagination. If page 1 fails outright
    # (404, connection error, non-Atlassian platform), we do not guess at
    # coverage -- see the coverage_start logic below.
    history_reached_end = False
    history_pages_fetched = 0
    dropped_no_timestamp = 0
    page = 1
    while page <= max_history_pages:
        hurl = f'{base_url}/history?page={page}'
        try:
            hbody = fetch(hurl)
        except Exception as exc:  # noqa: BLE001
            if page == 1:
                notes.append(f'no classic Atlassian /history page found at {hurl} ({exc}); '
                             'relying on the recent-incidents API only')
            break
        save_raw(raw_dir, f'history-page-{page}.html', hbody, hurl, raw_files)
        history_pages_fetched += 1
        found = parse_history_html(hbody, base_url)
        if not found:
            history_reached_end = True
            break
        for f in found:
            if f['id'] in incidents_by_id:
                continue
            # The history listing alone doesn't reliably carry a machine-parsable
            # start timestamp; without one we cannot place the incident in a
            # window, so we record it was seen but do not fabricate a date.
            dropped_no_timestamp += 1
        page += 1
    else:
        notes.append(f'stopped paginating /history at the {max_history_pages}-page safety cap; '
                     'history may extend further back than what was fetched')

    if dropped_no_timestamp:
        notes.append(f'{dropped_no_timestamp} incident(s) found via /history HTML listings but '
                     'omitted: no confirmed start timestamp was available (would need per-incident '
                     'detail-page fetches, not implemented here)')

    incidents = sorted(incidents_by_id.values(), key=lambda i: i['started_utc'])
    severity_map = {i['impact_label']: i['severity'] for i in incidents}

    if history_pages_fetched and history_reached_end and incidents:
        coverage_start = min(i['started_utc'] for i in incidents)[:10]
    else:
        coverage_start = None
        notes.append('coverage_start left null: pagination did not confirm it reached the true start '
                     'of this provider\'s incident history; set it manually only if you can justify it '
                     '(see SCHEMA.md)')
    coverage_end = now_utc_iso()[:10]

    return {
        'schema': INCIDENTS_SCHEMA, 'provider': slug, 'status_page_url': base_url,
        'retrieved_utc': now_utc_iso(), 'raw_files': raw_files,
        'coverage_start': coverage_start, 'coverage_end': coverage_end,
        'severity_map': severity_map, 'incidents': incidents, 'notes': notes,
    }


# --------------------------------------------------------------------------- #
# Atlassian history.json collector (real full-depth history)
# --------------------------------------------------------------------------- #

def month_first_day(name: str, year: int) -> date:
    return date(year, MONTH_NUMBERS[name], 1)


def parse_iso_date(ts: str):
    try:
        return datetime.fromisoformat(ts.replace('Z', '+00:00')).date()
    except (ValueError, AttributeError):
        return None


def normalize_history_incident(raw: dict, base_url: str, code: str):
    """Build a normalized incident from an /incidents/<code>.json detail
    response. `raw['impact']` is Atlassian's own label; 'maintenance' is a
    real value they use for scheduled maintenance (also cross-checked
    against `scheduled_for`, since some clones only set one of the two)."""
    incident_id = raw.get('id') or code
    if not incident_id:
        return None
    impact = (raw.get('impact') or 'none').lower()
    is_maintenance = (impact == 'maintenance') or bool(raw.get('scheduled_for'))
    if is_maintenance:
        impact_label = 'maintenance'
    else:
        impact_label = impact if impact in NORMALIZED_SEVERITIES else 'none'
    severity = HISTORY_SEVERITY_MAP.get(impact_label, 'none')
    started = raw.get('created_at') or raw.get('started_at') or raw.get('scheduled_for')
    resolved = raw.get('resolved_at')
    if is_maintenance and not resolved:
        resolved = raw.get('scheduled_until')
    if not started:
        return None
    return {
        'id': incident_id, 'title': raw.get('name', ''), 'impact_label': impact_label,
        'severity': severity, 'started_utc': started, 'resolved_utc': resolved,
        'is_maintenance': is_maintenance,
        'url': raw.get('shortlink') or f'{base_url}/incidents/{incident_id}',
    }


def normalize_history_summary(inc_ref: dict, base_url: str):
    """Degraded fallback when the per-incident detail fetch fails: build a
    normalized incident from the coarse history.json month entry alone
    (code, name, impact, timestamp). timestamp there is a human/HTML string,
    not reliably machine-parsable, so this is only used when the detail
    fetch itself failed (see the note recorded alongside it)."""
    code = inc_ref.get('code')
    ts = inc_ref.get('timestamp')
    if not code or not ts:
        return None
    impact = (inc_ref.get('impact') or 'none').lower()
    is_maintenance = impact == 'maintenance'
    impact_label = 'maintenance' if is_maintenance else (impact if impact in NORMALIZED_SEVERITIES else 'none')
    return {
        'id': code, 'title': inc_ref.get('name', ''), 'impact_label': impact_label,
        'severity': HISTORY_SEVERITY_MAP.get(impact_label, 'none'), 'started_utc': None,
        'resolved_utc': None, 'is_maintenance': is_maintenance,
        'url': f'{base_url}/incidents/{code}',
    }


def collect_atlassian_history(slug: str, base_url: str, out_root: Path, fetch=default_fetch_paced,
                               max_pages: int = HISTORY_PAGE_CAP, retries: int = 3, sleep_fn=time.sleep,
                               page_stop_before: date = HISTORY_PAGE_STOP_BEFORE,
                               coverage_requires_before: date = HISTORY_COVERAGE_REQUIRES_BEFORE):
    """Page `<base_url>/history.json?page=N` (3 months/page, newest first,
    including zero-incident months) until a page's oldest month predates
    `page_stop_before` or pages run out, then fetch each incident's detail
    JSON for exact times/impact. See module docstring."""
    base_url = base_url.rstrip('/')
    raw_dir = out_root / 'raw' / slug
    raw_files: list = []
    notes: list = []
    all_months: list = []
    page_created_at = None
    reached_end = False
    page = 1

    while page <= max_pages:
        hurl = f'{base_url}/history.json?page={page}'
        try:
            body = fetch_with_retry(fetch, hurl, retries=retries, sleep_fn=sleep_fn)
        except Exception as exc:  # noqa: BLE001
            if page == 1:
                raise CollectorError(f'{hurl}: {exc}') from exc
            notes.append(f'history.json paging stopped at page {page}: {exc}')
            break
        save_raw(raw_dir, f'history-page-{page}.json', body, hurl, raw_files)
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise CollectorError(f'{hurl}: not JSON: {exc}') from exc

        if page_created_at is None:
            page_created_at = ((data.get('page_status') or {}).get('page') or {}).get('created_at')

        months = data.get('months') or []
        if not months:
            reached_end = True
            break
        all_months.extend(months)
        if len(months) < 3:
            # A partial page is the last page of this provider's history.
            reached_end = True
            break
        last_month = months[-1]
        if month_first_day(last_month['name'], last_month['year']) < page_stop_before:
            break
        page += 1
    else:
        notes.append(f'stopped paginating history.json at the {max_pages}-page safety cap; '
                     'history may extend further back than what was fetched')

    # Fetch exact times/impact for every incident code we saw, deduped.
    incidents_by_id: dict = {}
    seen_codes = set()
    for month in all_months:
        for inc_ref in month.get('incidents', []):
            code = inc_ref.get('code')
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            durl = f'{base_url}/incidents/{code}.json'
            norm = None
            try:
                dbody = fetch_with_retry(fetch, durl, retries=retries, sleep_fn=sleep_fn)
            except Exception as exc:  # noqa: BLE001
                notes.append(f'{durl}: incident detail fetch failed ({exc}); '
                             'using the coarse history.json summary instead (no exact times)')
                norm = normalize_history_summary(inc_ref, base_url)
            else:
                save_raw(raw_dir, f'incident-{code}.json', dbody, durl, raw_files)
                try:
                    ddata = json.loads(dbody)
                except json.JSONDecodeError as exc:
                    notes.append(f'{durl}: not JSON ({exc}); using the coarse history.json summary instead')
                    norm = normalize_history_summary(inc_ref, base_url)
                else:
                    norm = normalize_history_incident(ddata, base_url, code)
            if norm:
                incidents_by_id[norm['id']] = norm

    incidents = [i for i in incidents_by_id.values() if i.get('started_utc')]
    dropped_no_ts = len(incidents_by_id) - len(incidents)
    if dropped_no_ts:
        notes.append(f'{dropped_no_ts} incident(s) dropped: no usable start timestamp from either '
                     'the detail fetch or the history.json summary')
    incidents.sort(key=lambda i: i['started_utc'])
    severity_map = {i['impact_label']: i['severity'] for i in incidents}

    oldest_month_date = None
    if all_months:
        last = all_months[-1]
        oldest_month_date = month_first_day(last['name'], last['year'])

    coverage_start = None
    if oldest_month_date is None:
        notes.append('coverage_start left null: history.json returned no months')
    else:
        reached_pre_window = oldest_month_date < coverage_requires_before
        if reached_end or reached_pre_window:
            candidates = [oldest_month_date]
            page_created_date = parse_iso_date(page_created_at) if page_created_at else None
            if page_created_date:
                candidates.append(page_created_date)
            coverage_start = max(candidates).isoformat()
        else:
            notes.append('coverage_start left null: paging neither reached the page\'s creation nor a '
                         f'month before {coverage_requires_before.isoformat()}')

    coverage_end = now_utc_iso()[:10]

    return {
        'schema': INCIDENTS_SCHEMA, 'provider': slug, 'status_page_url': base_url,
        'retrieved_utc': now_utc_iso(), 'raw_files': raw_files,
        'coverage_start': coverage_start, 'coverage_end': coverage_end,
        'severity_map': severity_map, 'incidents': incidents, 'notes': notes,
    }


# --------------------------------------------------------------------------- #
# generic fallback
# --------------------------------------------------------------------------- #

def collect_generic(slug: str, url: str, out_root: Path, fetch=default_fetch):
    raw_dir = out_root / 'raw' / slug
    raw_files: list = []
    try:
        body = fetch(url)
    except Exception as exc:  # noqa: BLE001
        raise CollectorError(f'{url}: {exc}') from exc
    save_raw(raw_dir, 'homepage.html', body, url, raw_files)
    return {
        'schema': INCIDENTS_SCHEMA, 'provider': slug, 'status_page_url': url,
        'retrieved_utc': now_utc_iso(), 'raw_files': raw_files,
        'coverage_start': None, 'coverage_end': None, 'severity_map': {}, 'incidents': [],
        'notes': ['generic fallback: no automated incident/history parser for this status page. '
                  'Author a manual incidents JSON against SCHEMA.md (cite the saved raw HTML above '
                  'by its sha256 as evidence) and re-run with --manual-json to merge it in.'],
    }


def apply_manual_json(doc: dict, manual_path: Path) -> dict:
    manual = json.loads(manual_path.read_text(encoding='utf-8'))
    for key in ('coverage_start', 'coverage_end', 'severity_map', 'incidents', 'provider', 'status_page_url'):
        if key in manual:
            doc[key] = manual[key]
    doc.setdefault('notes', []).append(f'merged manual incident data from {manual_path.name}')
    return doc


# --------------------------------------------------------------------------- #
# validation and mode detection
# --------------------------------------------------------------------------- #

def validate_doc(doc: dict) -> list:
    problems = []
    if doc.get('schema') != INCIDENTS_SCHEMA:
        problems.append('schema mismatch')
    for key in ('provider', 'status_page_url', 'retrieved_utc', 'raw_files', 'severity_map', 'incidents'):
        if key not in doc:
            problems.append(f'missing key: {key}')
    for i, inc in enumerate(doc.get('incidents', [])):
        for key in ('id', 'title', 'impact_label', 'severity', 'started_utc', 'is_maintenance', 'url'):
            if key not in inc:
                problems.append(f'incidents[{i}]: missing {key}')
        if inc.get('severity') not in NORMALIZED_SEVERITIES:
            problems.append(f'incidents[{i}]: invalid severity {inc.get("severity")!r}')
    return problems


def detect_mode(url: str, fetch=default_fetch) -> str:
    try:
        body = fetch(url.rstrip('/') + '/history.json?page=1')
        data = json.loads(body)
        if isinstance(data, dict) and 'months' in data:
            return 'atlassian-history'
    except Exception:  # noqa: BLE001
        pass
    try:
        body = fetch(url.rstrip('/') + '/api/v2/status.json')
        data = json.loads(body)
        if isinstance(data, dict) and 'page' in data and 'status' in data:
            return 'atlassian'
    except Exception:  # noqa: BLE001
        pass
    return 'generic'


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--slug', required=True, help='provider slug, e.g. lambda')
    ap.add_argument('--url', required=True, help='status page base URL, e.g. https://status.example.com')
    ap.add_argument('--mode', choices=('auto', 'atlassian-history', 'atlassian', 'generic'), default='auto')
    ap.add_argument('--manual-json', type=Path, default=None,
                     help='hand-authored incidents JSON to merge in (generic mode, or to correct '
                          'an atlassian-mode run)')
    ap.add_argument('--out-root', type=Path,
                     default=Path(__file__).resolve().parents[1] / 'retrospective' / 'incidents')
    args = ap.parse_args(argv)

    mode = args.mode if args.mode != 'auto' else detect_mode(args.url)

    try:
        if mode == 'atlassian-history':
            doc = collect_atlassian_history(args.slug, args.url, args.out_root, fetch=default_fetch_paced)
        elif mode == 'atlassian':
            doc = collect_atlassian(args.slug, args.url, args.out_root)
        else:
            doc = collect_generic(args.slug, args.url, args.out_root)
    except CollectorError as exc:
        print(f'FETCH FAILED: {exc}', file=sys.stderr)
        return 2

    if args.manual_json:
        doc = apply_manual_json(doc, args.manual_json)

    problems = validate_doc(doc)
    if problems:
        print('WARNING: normalized document has schema problems:', file=sys.stderr)
        for p in problems:
            print(f'  - {p}', file=sys.stderr)

    args.out_root.mkdir(parents=True, exist_ok=True)
    out_path = args.out_root / f'{args.slug}.json'
    out_path.write_text(json.dumps(doc, indent=2, sort_keys=False) + '\n', encoding='utf-8')
    print(f'[{mode}] wrote {out_path} '
          f'({len(doc["incidents"])} incidents, coverage {doc["coverage_start"]}..{doc["coverage_end"]})')
    for note in doc.get('notes', []):
        print(f'  note: {note}')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
