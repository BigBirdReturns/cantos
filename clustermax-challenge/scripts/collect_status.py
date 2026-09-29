#!/usr/bin/env python3
"""Fetch and normalize a provider's public status-page incident history into
retrospective/incidents/<slug>.json (schema secondrun.status-incidents.v1; see
retrospective/incidents/SCHEMA.md). Stdlib only.

Collection modes (atlassian-history, atlassian, and the newer betterstack, instatus, sorryapp; see
the block before `generic fallback` for those three):

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
# Better Stack, Instatus and SorryApp collectors (added 2026-09-29)
#
# These match what retrospective/incidents/COLLECTION-LOG-2026-09-29.md
# describes as hand-parsed. Each one fetches the platform's own public pages,
# saves every page under raw/<slug>/ with its SHA-256, and returns the same
# secondrun.status-incidents.v1 document as the Atlassian collectors. None of
# them invents a value: a field the page does not carry stays null / 'none'
# and the rule is written into `notes`.
# --------------------------------------------------------------------------- #

MONTH_NAMES = ('january', 'february', 'march', 'april', 'may', 'june', 'july',
               'august', 'september', 'october', 'november', 'december')


class UnsupportedPlatform(CollectorError):
    """The URL did not answer like the platform this mode expects."""


def _strip_markup(body: bytes) -> str:
    text = body.decode('utf-8', 'replace')
    text = re.sub(r'<style.*?</style>', '', text, flags=re.S)
    text = re.sub(r'<script.*?</script>', '', text, flags=re.S)
    # Keep svg tags (Better Stack encodes the affected-service state in the svg class); drop only their
    # drawing paths. Removing whole <svg>..</svg> spans is wrong: a self-closed <svg/> makes a lazy
    # match swallow the next real svg.
    return re.sub(r'<path[^>]*>(?:</path>)?', '', text)


def _month_range(start: date, today: date):
    y, m = start.year, start.month
    while (y, m) <= (today.year, today.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def _html_text(fragment: str) -> str:
    import html as _html
    return re.sub(r'\s+', ' ', _html.unescape(re.sub(r'<[^>]+>', ' ', fragment))).strip()


# ---- Better Stack (status pages served from /incidents/<quarter>) ---------- #

BETTERSTACK_STATE = {  # svg colour class on the per-update affected-service tooltip
    'red': ('Downtime', 'critical'),
    'yellow': ('Degraded performance', 'minor'),
    'blue': ('Maintenance', 'none'),
}
BETTERSTACK_STATE_ORDER = ('red', 'yellow', 'blue')  # worst first
BETTERSTACK_NO_STATE = '(no affected-component state recorded)'
_BS_INCIDENT_HREF = re.compile(r"href='/incident/(\d+)'")
_BS_TIME = re.compile(r"local-time-datetime-value='([^']+)'")
_BS_UPDATE = re.compile(
    r"<span class='font-medium[^']*'>\s*([^<]+?)\s*</span>\s*(?:<br[^>]*>\s*)?"
    r"<span[^>]*local-time-datetime-value='([^']+)'")
_BS_TOOLTIP = re.compile(r"id='update-states-tooltip-\d+'>(.*?)</div>\s*</div>", re.S)


def betterstack_quarter_url(base_url: str, year: int, quarter: int) -> str:
    first, last = 3 * quarter - 2, 3 * quarter
    return f'{base_url}/incidents/{year}-{first:02d}/{year}-{last:02d}'


def parse_betterstack_quarter(body: bytes) -> dict:
    """Quarter page -> {'incidents': [{'id','title'}], 'empty_months': n, 'is_betterstack': bool}."""
    text = _strip_markup(body)
    is_bs = 'betterstack.com' in text and ("status-report" in text or 'incidents-content' in text
                                            or '/incidents/' in text)
    incidents, seen = [], set()
    for m in re.finditer(r"<a [^>]*href='/incident/(\d+)'[^>]*>(.*?)</a>", text, re.S):
        ident = m.group(1)
        if ident in seen:
            continue
        seen.add(ident)
        pm = re.search(r"<p class='grow[^']*'[^>]*>(.*?)</p>", m.group(2), re.S) \
            or re.search(r"<p[^>]*font-medium[^>]*>(.*?)</p>", m.group(2), re.S)
        incidents.append({'id': ident, 'title': _html_text(pm.group(1)) if pm else ''})
    return {'incidents': incidents, 'empty_months': text.count('No incidents reported'),
            'is_betterstack': bool(is_bs)}


def parse_betterstack_incident(body: bytes, base_url: str, ident: str):
    """Detail page -> normalized incident, or None when the page has no report container."""
    text = _strip_markup(body)
    box = text.find("id='status-report-container'")
    if box < 0:
        return None
    seg = text[box:]
    h2 = re.search(r'<h2[^>]*>(.*?)</h2>', seg, re.S)
    title = _html_text(h2.group(1)) if h2 else ''
    head_time = _BS_TIME.search(seg[h2.end():] if h2 else seg)
    started = head_time.group(1) if head_time else None
    resolved = None
    for label, ts in _BS_UPDATE.findall(seg):  # newest update first on the page
        if label.strip().lower() == 'resolved':
            if resolved is None or ts > resolved:
                resolved = ts
    states = set()
    for tip in _BS_TOOLTIP.findall(seg):
        states.update(re.findall(r'text-statuspage-(red|yellow|blue|green)', tip))
    worst = next((c for c in BETTERSTACK_STATE_ORDER if c in states), None)
    label, severity = BETTERSTACK_STATE.get(worst, (BETTERSTACK_NO_STATE, 'none'))
    if not started:
        return None
    return {'id': ident, 'title': title, 'impact_label': label, 'severity': severity,
            'started_utc': started, 'resolved_utc': resolved,
            'is_maintenance': worst == 'blue', 'url': f'{base_url}/incident/{ident}'}


def collect_betterstack(slug: str, base_url: str, out_root: Path, fetch=default_fetch_paced,
                        start: date = date(2026, 1, 1), today: date | None = None,
                        retries: int = 3, sleep_fn=time.sleep):
    base_url = base_url.rstrip('/')
    today = today or datetime.now(timezone.utc).date()
    raw_dir = out_root / 'raw' / slug
    raw_files: list = []
    notes: list = []
    quarters = []
    for y, m in _month_range(start, today):
        q = (m - 1) // 3 + 1
        if (y, q) not in quarters:
            quarters.append((y, q))
    listed: dict = {}
    fetched_quarters = []
    empty_months = 0
    for y, q in quarters:
        url = betterstack_quarter_url(base_url, y, q)
        try:
            body = fetch_with_retry(fetch, url, retries=retries, sleep_fn=sleep_fn)
        except Exception as exc:  # noqa: BLE001
            if not fetched_quarters:
                raise CollectorError(f'{url}: {exc}') from exc
            notes.append(f'{url}: quarter page failed ({exc}); not counted as coverage')
            continue
        page = parse_betterstack_quarter(body)
        if not page['is_betterstack']:
            raise UnsupportedPlatform(f'{url}: page does not look like a Better Stack status page')
        save_raw(raw_dir, f'incidents_{y}-{3 * q - 2:02d}_{y}-{3 * q:02d}.html', body, url, raw_files)
        fetched_quarters.append((y, q))
        empty_months += page['empty_months']
        for inc in page['incidents']:
            listed.setdefault(inc['id'], inc)
    incidents = []
    for ident in listed:
        durl = f'{base_url}/incident/{ident}'
        try:
            dbody = fetch_with_retry(fetch, durl, retries=retries, sleep_fn=sleep_fn)
        except Exception as exc:  # noqa: BLE001
            notes.append(f'{durl}: detail fetch failed ({exc}); incident not recorded (no fabricated times)')
            continue
        save_raw(raw_dir, f'incident_{ident}.html', dbody, durl, raw_files)
        norm = parse_betterstack_incident(dbody, base_url, ident)
        if norm is None:
            notes.append(f'{durl}: detail page had no parsable report; incident not recorded')
            continue
        incidents.append(norm)
    incidents.sort(key=lambda i: i['started_utc'])
    severity_map = {}
    for i in incidents:
        severity_map[i['impact_label']] = i['severity']
    coverage_start = None
    if fetched_quarters:
        y, q = fetched_quarters[0]
        coverage_start = date(y, 3 * q - 2, 1).isoformat()
    else:
        notes.append('coverage_start left null: no quarter page was fetched')
    notes.append('better-stack platform; collected by paging /incidents/<quarter> and fetching every /incident/<id> detail page. '
                 'impact_label is the worst per-update affected-service state colour shown by Better Stack '
                 '(red=Downtime->critical, yellow=Degraded performance->minor, blue=Maintenance->none and is_maintenance, '
                 'green or no affected component->none). Better Stack has no separate impact field.')
    notes.append(f'quarter pages fetched: {len(fetched_quarters)}; incidents listed: {len(listed)}; recorded: {len(incidents)}; '
                 f'"No incidents reported" month markers seen: {empty_months}')
    return {
        'schema': INCIDENTS_SCHEMA, 'provider': slug, 'status_page_url': base_url,
        'retrieved_utc': now_utc_iso(), 'raw_files': raw_files,
        'coverage_start': coverage_start, 'coverage_end': today.isoformat(),
        'severity_map': severity_map, 'incidents': incidents, 'notes': notes,
    }


# ---- Instatus (paged JSON the status page itself calls) --------------------- #

INSTATUS_API = 'https://api.instatus.com/public'
INSTATUS_SEVERITY = {
    'MAJOROUTAGE': 'critical', 'PARTIALOUTAGE': 'major',
    'DEGRADEDPERFORMANCE': 'minor', 'MINOROUTAGE': 'minor',
    'OPERATIONAL': 'none', 'UNDERMAINTENANCE': 'none',
}
INSTATUS_PAGE_CAP = 60


def instatus_page_key(base_url: str) -> str:
    from urllib.parse import urlparse
    host = urlparse(base_url if '//' in base_url else '//' + base_url).hostname or base_url
    if host.endswith('.instatus.com'):
        return host[:-len('.instatus.com')]  # the host form 404s on the API for *.instatus.com pages
    return host


def _instatus_text(value) -> str:
    if isinstance(value, dict):
        return value.get('default') or value.get('en') or next(iter(value.values()), '') or ''
    return value or ''


def normalize_instatus_notice(raw: dict, base_url: str):
    ident = raw.get('id')
    started = raw.get('started') or raw.get('start')
    if not ident or not started:
        return None
    impact = raw.get('impact') or 'UNKNOWN'
    maintenance = impact == 'UNDERMAINTENANCE' or not raw.get('started')
    return {
        'id': ident, 'title': _instatus_text(raw.get('name')), 'impact_label': impact,
        'severity': INSTATUS_SEVERITY.get(impact, 'none'), 'started_utc': started,
        'resolved_utc': raw.get('resolved'), 'is_maintenance': maintenance,
        'url': f'{base_url}/{ident}',
    }


def collect_instatus(slug: str, base_url: str, out_root: Path, fetch=default_fetch_paced,
                     start: date = date(2026, 1, 1), today: date | None = None,
                     retries: int = 3, sleep_fn=time.sleep):
    base_url = base_url.rstrip('/')
    today = today or datetime.now(timezone.utc).date()
    key = instatus_page_key(base_url)
    raw_dir = out_root / 'raw' / slug
    raw_files: list = []
    notes: list = []
    by_id: dict = {}
    months_fetched = []
    unknown_impacts = set()
    for y, m in _month_range(start, today):
        month_key = int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp() * 1000)
        page_no, ok = 1, False
        while page_no <= INSTATUS_PAGE_CAP:
            url = f'{INSTATUS_API}/{key}/notices/monthly/{month_key}?page_no={page_no}'
            try:
                body = fetch_with_retry(fetch, url, retries=retries, sleep_fn=sleep_fn)
                data = json.loads(body)
            except Exception as exc:  # noqa: BLE001
                if not months_fetched and page_no == 1:
                    raise UnsupportedPlatform(f'{url}: {exc}') from exc
                notes.append(f'{url}: failed ({exc}); month {y}-{m:02d} coverage not claimed')
                break
            if not isinstance(data, dict) or not isinstance(data.get('month'), dict):
                if not months_fetched and page_no == 1:
                    raise UnsupportedPlatform(f'{url}: response has no "month" object')
                notes.append(f'{url}: unexpected payload; month {y}-{m:02d} coverage not claimed')
                break
            save_raw(raw_dir, f'notices_{y}-{m:02d}_p{page_no}.json', body, url, raw_files)
            ok = True
            for n in data['month'].get('notices') or []:
                norm = normalize_instatus_notice(n, base_url)
                if norm:
                    by_id[norm['id']] = norm
                    if norm['impact_label'] not in INSTATUS_SEVERITY:
                        unknown_impacts.add(norm['impact_label'])
            if data['month'].get('isLastPage') is not False:
                break
            page_no += 1
        else:
            notes.append(f'month {y}-{m:02d}: stopped at the {INSTATUS_PAGE_CAP}-page safety cap')
        if ok:
            months_fetched.append((y, m))
    incidents = sorted(by_id.values(), key=lambda i: i['started_utc'])
    severity_map = {}
    for i in incidents:
        severity_map[i['impact_label']] = i['severity']
    if unknown_impacts:
        notes.append('impact labels not in the declared mapping (severity none): ' + ', '.join(sorted(unknown_impacts)))
    coverage_start = date(*months_fetched[0], 1).isoformat() if months_fetched else None
    if coverage_start is None:
        notes.append('coverage_start left null: no month fetched')
    notes.append(f'instatus platform; collected via {INSTATUS_API}/{key}/notices/monthly/<monthKey>?page_no=N for every month '
                 f'{start.isoformat()[:7]}..{today.isoformat()[:7]}, following pages until isLastPage. '
                 'Notices with impact UNDERMAINTENANCE (or without a "started" field) are is_maintenance. '
                 'MAJOROUTAGE->critical, PARTIALOUTAGE->major, DEGRADEDPERFORMANCE/MINOROUTAGE->minor.')
    return {
        'schema': INCIDENTS_SCHEMA, 'provider': slug, 'status_page_url': base_url,
        'retrieved_utc': now_utc_iso(), 'raw_files': raw_files,
        'coverage_start': coverage_start, 'coverage_end': today.isoformat(),
        'severity_map': severity_map, 'incidents': incidents, 'notes': notes,
    }


# ---- SorryApp (monthly history pages of notice cards) ----------------------- #

_SORRY_CARD = re.compile(r'id="notice-card-(\d+)"(.*?)(?=id="notice-card-\d+"|<div[^>]*id="history_pagination"|\Z)', re.S)
_SORRY_LABEL_MAINTENANCE = ('complete', 'completed', 'scheduled', 'in progress', 'upcoming', 'maintenance')


def parse_sorryapp_month(body: bytes, base_url: str) -> list:
    text = _strip_markup(body)
    out = []
    for m in _SORRY_CARD.finditer(text):
        ident, seg = m.group(1), m.group(2)
        label_m = re.search(r'<p class="text-gray-900/80[^"]*">\s*([A-Za-z ]+?)\s*<small', seg, re.S)
        label = label_m.group(1).strip() if label_m else ''
        time_m = re.search(r'Ended:\s*<time datetime="([^"]+)"', seg)
        title_m = re.search(r'<p class="text-lg[^"]*font-semibold[^"]*">(.*?)</p>', seg, re.S)
        href_m = re.search(r'<a href="(/history/[^"]+)"', seg)
        if not (label and time_m and title_m and href_m):
            continue
        ended = datetime.strptime(time_m.group(1), '%Y-%m-%dT%H:%M:%S%z').astimezone(timezone.utc)
        ts = ended.strftime('%Y-%m-%dT%H:%M:%SZ')
        out.append({
            'id': ident, 'title': _html_text(title_m.group(1)),
            'impact_label': 'notice-' + label.lower().replace(' ', '-'), 'severity': 'none',
            'started_utc': ts, 'resolved_utc': ts,
            'is_maintenance': label.lower() in _SORRY_LABEL_MAINTENANCE,
            'url': base_url + href_m.group(1),
        })
    return out


def collect_sorryapp(slug: str, base_url: str, out_root: Path, fetch=default_fetch_paced,
                     start: date = date(2026, 1, 1), today: date | None = None,
                     retries: int = 3, sleep_fn=time.sleep):
    base_url = base_url.rstrip('/')
    today = today or datetime.now(timezone.utc).date()
    raw_dir = out_root / 'raw' / slug
    raw_files: list = []
    notes: list = []
    by_id: dict = {}
    fetched, missing = [], []
    for y, m in _month_range(start, today):
        url = f'{base_url}/history/{y}/{MONTH_NAMES[m - 1]}'
        try:
            body = fetch_with_retry(fetch, url, retries=retries, sleep_fn=sleep_fn)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                if not fetched and not missing and (y, m) == (start.year, start.month):
                    pass  # a 404 on the very first month is ambiguous; keep going and judge at the end
                missing.append((y, m))
                continue
            if not fetched:
                raise UnsupportedPlatform(f'{url}: HTTP {exc.code}') from exc
            notes.append(f'{url}: HTTP {exc.code}; month not counted')
            continue
        except Exception as exc:  # noqa: BLE001
            if not fetched:
                raise UnsupportedPlatform(f'{url}: {exc}') from exc
            notes.append(f'{url}: {exc}; month not counted')
            continue
        if b'sorryapp.com' not in body and b'notice-card' not in body:
            raise UnsupportedPlatform(f'{url}: page does not look like a SorryApp status page')
        save_raw(raw_dir, f'history_{y}-{MONTH_NAMES[m - 1]}.html', body, url, raw_files)
        fetched.append((y, m))
        for n in parse_sorryapp_month(body, base_url):
            by_id[n['id']] = n
    if not fetched:
        raise UnsupportedPlatform(f'{base_url}: no history month page returned 200')
    incidents = sorted(by_id.values(), key=lambda i: i['started_utc'])
    severity_map = {}
    for i in incidents:
        severity_map[i['impact_label']] = i['severity']
    if missing:
        notes.append('months returning 404 (the site lists no notices for them): '
                     + ', '.join(f'{y}-{m:02d}' for y, m in missing)
                     + '. A 404 is weaker evidence than an explicit "no incidents" page.')
    notes.append('SorryApp platform; parsed /history/<year>/<month> notice cards. The card shows only the "Ended" time, '
                 'so started_utc == resolved_utc == Ended. SorryApp exposes no severity: impact_label is the card state '
                 '(Resolved / Complete ...), severity is none. Cards in the Complete state are treated as maintenance; '
                 'a Resolved card is an incident.')
    return {
        'schema': INCIDENTS_SCHEMA, 'provider': slug, 'status_page_url': base_url,
        'retrieved_utc': now_utc_iso(), 'raw_files': raw_files,
        'coverage_start': date(start.year, start.month, 1).isoformat(), 'coverage_end': today.isoformat(),
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
    return detect_extra_mode(url, fetch) or 'generic'


def detect_extra_mode(url: str, fetch=default_fetch):
    """Platforms added after the Atlassian modes. Only consulted when both Atlassian
    probes failed, so existing detection results are unchanged. Returns a mode
    name or None."""
    base = url.rstrip('/')
    try:
        body = fetch(base + '/incidents')
        if b'betterstack.com' in body and b'/incidents/' in body:
            return 'betterstack'
    except Exception:  # noqa: BLE001
        pass
    try:
        key = instatus_page_key(base)
        month_key = int(datetime(datetime.now(timezone.utc).year, datetime.now(timezone.utc).month, 1,
                                 tzinfo=timezone.utc).timestamp() * 1000)
        data = json.loads(fetch(f'{INSTATUS_API}/{key}/notices/monthly/{month_key}?page_no=1'))
        if isinstance(data, dict) and isinstance(data.get('month'), dict):
            return 'instatus'
    except Exception:  # noqa: BLE001
        pass
    try:
        now = datetime.now(timezone.utc)
        body = fetch(f'{base}/history/{now.year}/{MONTH_NAMES[now.month - 1]}')
        if b'sorryapp.com' in body or b'notice-card' in body:
            return 'sorryapp'
    except Exception:  # noqa: BLE001
        pass
    return None


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--slug', required=True, help='provider slug, e.g. lambda')
    ap.add_argument('--url', required=True, help='status page base URL, e.g. https://status.example.com')
    ap.add_argument('--mode', choices=('auto', 'atlassian-history', 'atlassian', 'betterstack', 'instatus', 'sorryapp',
                                                  'generic'), default='auto')
    ap.add_argument('--manual-json', type=Path, default=None,
                     help='hand-authored incidents JSON to merge in (generic mode, or to correct '
                          'an atlassian-mode run)')
    ap.add_argument('--out-root', type=Path,
                     default=Path(__file__).resolve().parents[1] / 'retrospective' / 'incidents')
    ap.add_argument('--since', default='2026-01-01',
                     help='betterstack/instatus/sorryapp: first month to fetch (YYYY-MM-DD; coverage_start is that '
                          'month/quarter, never inferred from incidents)')
    args = ap.parse_args(argv)
    since = date.fromisoformat(args.since)

    mode = args.mode if args.mode != 'auto' else detect_mode(args.url)

    try:
        if mode == 'atlassian-history':
            doc = collect_atlassian_history(args.slug, args.url, args.out_root, fetch=default_fetch_paced)
        elif mode == 'atlassian':
            doc = collect_atlassian(args.slug, args.url, args.out_root)
        elif mode == 'betterstack':
            doc = collect_betterstack(args.slug, args.url, args.out_root, start=since)
        elif mode == 'instatus':
            doc = collect_instatus(args.slug, args.url, args.out_root, start=since)
        elif mode == 'sorryapp':
            doc = collect_sorryapp(args.slug, args.url, args.out_root, start=since)
        else:
            doc = collect_generic(args.slug, args.url, args.out_root)
    except UnsupportedPlatform as exc:
        print(f'UNSUPPORTED: {exc}', file=sys.stderr)
        return 3
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
