import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import collect_status as cs  # noqa: E402


def fake_fetch(routes: dict):
    """routes: {url: bytes-or-Exception}. Never touches the network."""
    def fetch(url, timeout=20.0):
        target = routes.get(url)
        if target is None:
            raise cs.urllib.error.HTTPError(url, 404, 'Not Found', {}, None)
        if isinstance(target, Exception):
            raise target
        return target
    return fetch


def j(obj) -> bytes:
    return json.dumps(obj).encode('utf-8')


class AtlassianCollectorTests(unittest.TestCase):
    def test_normalizes_recent_incidents_and_maintenance(self):
        base = 'https://status.example.com'
        incidents_payload = {'incidents': [
            {'id': 'INC1', 'name': 'API errors', 'impact': 'major',
             'started_at': '2026-02-01T00:00:00Z', 'resolved_at': '2026-02-01T02:00:00Z',
             'shortlink': f'{base}/incidents/INC1'},
            {'id': 'INC2', 'name': 'Still open', 'impact': 'critical',
             'started_at': '2026-02-05T00:00:00Z', 'resolved_at': None},
        ]}
        maint_payload = {'scheduled_maintenances': [
            {'id': 'MAINT1', 'name': 'Planned upgrade', 'impact': 'none',
             'scheduled_for': '2026-02-10T00:00:00Z', 'scheduled_until': '2026-02-10T01:00:00Z'},
        ]}
        routes = {
            f'{base}/api/v2/incidents.json': j(incidents_payload),
            f'{base}/api/v2/scheduled-maintenances.json': j(maint_payload),
            # no /history route -> generic-style "not found" via fake_fetch default
        }
        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td) / 'incidents'
            doc = cs.collect_atlassian('example', base, out_root, fetch=fake_fetch(routes))

        self.assertEqual(doc['schema'], cs.INCIDENTS_SCHEMA)
        ids = {i['id']: i for i in doc['incidents']}
        self.assertEqual(len(ids), 3)
        self.assertEqual(ids['INC1']['severity'], 'major')
        self.assertFalse(ids['INC1']['is_maintenance'])
        self.assertEqual(ids['INC2']['severity'], 'critical')
        self.assertIsNone(ids['INC2']['resolved_utc'])
        self.assertTrue(ids['MAINT1']['is_maintenance'])
        self.assertEqual(doc['severity_map']['major'], 'major')
        # no confirmed pagination to the start of history -> coverage_start must
        # stay null rather than being inferred from the oldest incident seen
        self.assertIsNone(doc['coverage_start'])
        self.assertTrue(any('coverage_start left null' in n for n in doc['notes']))
        self.assertEqual(len(cs.validate_doc(doc)), 0)

    def test_raw_files_are_hashed_and_saved(self):
        base = 'https://status.example.com'
        body = j({'incidents': []})
        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td) / 'incidents'
            routes = {f'{base}/api/v2/incidents.json': body}
            doc = cs.collect_atlassian('example', base, out_root, fetch=fake_fetch(routes))
            self.assertEqual(len(doc['raw_files']), 1)
            raw = doc['raw_files'][0]
            self.assertEqual(raw['sha256'], cs.sha256_bytes(body))
            saved = Path(td) / 'incidents' / 'raw' / 'example' / 'api-v2-incidents.json'
            self.assertTrue(saved.exists())
            self.assertEqual(saved.read_bytes(), body)

    def test_history_pagination_reaches_confirmed_end_sets_coverage_start(self):
        base = 'https://status.example.com'
        incidents_payload = {'incidents': [
            {'id': 'INC1', 'name': 'x', 'impact': 'minor',
             'started_at': '2026-05-01T00:00:00Z', 'resolved_at': '2026-05-01T01:00:00Z'},
        ]}
        history_page_1 = b'<div class="month"><a href="/incidents/OLD1" class="incident-title">Old one</a></div>'
        routes = {
            f'{base}/api/v2/incidents.json': j(incidents_payload),
            f'{base}/history?page=1': history_page_1,
            f'{base}/history?page=2': b'<html>no incidents here</html>',
        }
        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td) / 'incidents'
            doc = cs.collect_atlassian('example', base, out_root, fetch=fake_fetch(routes))
        # OLD1 has no confirmed timestamp so it's dropped, but pagination DID
        # reach an empty page -> we treat that as confirmed end of history, and
        # coverage_start falls back to the oldest incident we *do* have a date for.
        self.assertEqual(doc['coverage_start'], '2026-05-01')
        self.assertTrue(any('omitted' in n for n in doc['notes']))

    def test_scheduled_maintenance_endpoint_missing_is_tolerated(self):
        base = 'https://status.example.com'
        routes = {f'{base}/api/v2/incidents.json': j({'incidents': []})}
        with tempfile.TemporaryDirectory() as td:
            doc = cs.collect_atlassian('example', base, Path(td) / 'incidents', fetch=fake_fetch(routes))
        self.assertEqual(doc['incidents'], [])
        self.assertTrue(any('scheduled-maintenances.json unavailable' in n for n in doc['notes']))


class GenericCollectorTests(unittest.TestCase):
    def test_saves_raw_and_flags_manual_authoring_needed(self):
        url = 'https://status.example.com/'
        routes = {url: b'<html>a plain status page</html>'}
        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td) / 'incidents'
            doc = cs.collect_generic('example', url, out_root, fetch=fake_fetch(routes))
        self.assertEqual(doc['incidents'], [])
        self.assertIsNone(doc['coverage_start'])
        self.assertEqual(len(doc['raw_files']), 1)
        self.assertTrue(any('manual' in n for n in doc['notes']))

    def test_manual_json_merges_in(self):
        url = 'https://status.example.com/'
        routes = {url: b'<html></html>'}
        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td) / 'incidents'
            doc = cs.collect_generic('example', url, out_root, fetch=fake_fetch(routes))
            manual_path = Path(td) / 'manual.json'
            manual_path.write_text(json.dumps({
                'coverage_start': '2026-01-01', 'coverage_end': '2026-09-01',
                'severity_map': {'Critical': 'critical'},
                'incidents': [{'id': 'M1', 'title': 't', 'impact_label': 'Critical',
                               'severity': 'critical', 'started_utc': '2026-02-01T00:00:00Z',
                               'resolved_utc': None, 'is_maintenance': False,
                               'url': 'https://status.example.com/incidents/M1'}],
            }), encoding='utf-8')
            merged = cs.apply_manual_json(doc, manual_path)
        self.assertEqual(merged['coverage_start'], '2026-01-01')
        self.assertEqual(len(merged['incidents']), 1)
        self.assertEqual(len(cs.validate_doc(merged)), 0)


def history_page(months, page_created_at='2019-01-01T00:00:00.000Z'):
    return j({
        'page_status': {'page': {'created_at': page_created_at}},
        'months': months,
    })


def month(name, year, incidents=None):
    return {'name': name, 'year': year, 'incidents': incidents or []}


def inc_ref(code, name='An incident', impact='major', timestamp='Mar 1, 00:00 - 01:00 UTC'):
    return {'code': code, 'name': name, 'impact': impact, 'timestamp': timestamp}


def inc_detail(code, name='An incident', impact='major', created_at='2026-03-01T00:00:00.000Z',
                resolved_at='2026-03-01T01:00:00.000Z', scheduled_for=None, scheduled_until=None):
    return j({
        'id': code, 'name': name, 'impact': impact, 'status': 'resolved',
        'created_at': created_at, 'resolved_at': resolved_at,
        'scheduled_for': scheduled_for, 'scheduled_until': scheduled_until,
        'shortlink': f'https://stspg.io/{code}',
    })


class AtlassianHistoryCollectorTests(unittest.TestCase):
    def test_stops_paging_before_2025_03_and_sets_coverage_start(self):
        base = 'https://status.example.com'
        routes = {
            f'{base}/history.json?page=1': history_page([
                month('September', 2026, [inc_ref('INC1')]),
                month('August', 2026), month('July', 2026),
            ]),
            f'{base}/history.json?page=2': history_page([
                month('June', 2026), month('May', 2026), month('April', 2026),
            ]),
            f'{base}/history.json?page=3': history_page([
                month('March', 2026), month('February', 2026), month('January', 2025),
            ]),
            f'{base}/incidents/INC1.json': inc_detail('INC1'),
        }
        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td) / 'incidents'
            doc = cs.collect_atlassian_history('example', base, out_root, fetch=fake_fetch(routes),
                                                sleep_fn=lambda s: None)
        # January 2025 < page_stop_before (2025-03-01) -> pagination stops after page 3
        self.assertEqual(len(doc['incidents']), 1)
        self.assertEqual(doc['incidents'][0]['id'], 'INC1')
        self.assertEqual(doc['incidents'][0]['started_utc'], '2026-03-01T00:00:00.000Z')
        self.assertEqual(doc['incidents'][0]['severity'], 'major')
        # oldest month returned is January 2025, well before the coverage
        # threshold (2025-03-26) -> coverage_start may be claimed
        self.assertEqual(doc['coverage_start'], '2025-01-01')
        self.assertEqual(len(cs.validate_doc(doc)), 0)

    def test_reaches_page_creation_before_threshold_still_sets_coverage_start(self):
        base = 'https://status.example.com'
        # page created after 2025-03-26: pagination reaches the true start of
        # history (a short final page) without ever seeing a month before
        # the coverage threshold -- coverage_start should still be set,
        # using the later of page_created_at and the oldest month.
        routes = {
            f'{base}/history.json?page=1': history_page([
                month('June', 2025), month('May', 2025),
            ], page_created_at='2025-05-15T00:00:00.000Z'),
        }
        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td) / 'incidents'
            doc = cs.collect_atlassian_history('example', base, out_root, fetch=fake_fetch(routes),
                                                sleep_fn=lambda s: None)
        # oldest month first day (2025-05-01) is before page_created_at date
        # (2025-05-15) -> coverage_start is the LATER of the two: 2025-05-15
        self.assertEqual(doc['coverage_start'], '2025-05-15')

    def test_neither_threshold_reached_leaves_coverage_start_null(self):
        base = 'https://status.example.com'
        # A full 3-month page whose oldest month is still after the coverage
        # threshold, and pagination stops (page 2 errors) without reaching
        # page creation -> nothing justifies a coverage_start claim.
        routes = {
            f'{base}/history.json?page=1': history_page([
                month('September', 2026), month('August', 2026), month('July', 2026),
            ], page_created_at='2019-01-01T00:00:00.000Z'),
        }
        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td) / 'incidents'
            doc = cs.collect_atlassian_history('example', base, out_root, fetch=fake_fetch(routes),
                                                sleep_fn=lambda s: None)
        self.assertIsNone(doc['coverage_start'])
        self.assertTrue(any('coverage_start left null' in n for n in doc['notes']))

    def test_maintenance_detected_and_severity_none(self):
        base = 'https://status.example.com'
        routes = {
            f'{base}/history.json?page=1': history_page([
                month('September', 2026, [inc_ref('MAINT1', impact='maintenance')]),
                month('August', 2026), month('July', 2026),
            ]),
            f'{base}/incidents/MAINT1.json': inc_detail(
                'MAINT1', impact='maintenance', created_at='2026-09-05T00:00:00.000Z',
                resolved_at=None, scheduled_for='2026-09-05T00:00:00.000Z',
                scheduled_until='2026-09-05T02:00:00.000Z'),
        }
        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td) / 'incidents'
            doc = cs.collect_atlassian_history('example', base, out_root, fetch=fake_fetch(routes),
                                                sleep_fn=lambda s: None)
        inc = doc['incidents'][0]
        self.assertTrue(inc['is_maintenance'])
        self.assertEqual(inc['severity'], 'none')
        self.assertEqual(inc['impact_label'], 'maintenance')
        # falls back to scheduled_until since resolved_at was null
        self.assertEqual(inc['resolved_utc'], '2026-09-05T02:00:00.000Z')
        self.assertEqual(doc['severity_map']['maintenance'], 'none')

    def test_detail_fetch_failure_falls_back_to_history_summary(self):
        base = 'https://status.example.com'
        routes = {
            f'{base}/history.json?page=1': history_page([
                month('September', 2026, [inc_ref('INC1', impact='minor',
                                                    timestamp='Sep 1, 00:00 - 01:00 UTC')]),
                month('August', 2026), month('July', 2026),
            ]),
            # no incidents/INC1.json route -> detail fetch 404s
        }
        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td) / 'incidents'
            doc = cs.collect_atlassian_history('example', base, out_root, fetch=fake_fetch(routes),
                                                sleep_fn=lambda s: None)
        self.assertEqual(len(doc['incidents']), 0)  # summary timestamp isn't a real start time
        self.assertTrue(any('using the coarse history.json summary' in n for n in doc['notes']))

    def test_raw_files_hashed_for_history_pages_and_incident_details(self):
        base = 'https://status.example.com'
        page1_body = history_page([
            month('September', 2026, [inc_ref('INC1')]),
            month('August', 2026), month('July', 2026),
        ])
        detail_body = inc_detail('INC1')
        routes = {
            f'{base}/history.json?page=1': page1_body,
            f'{base}/incidents/INC1.json': detail_body,
        }
        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td) / 'incidents'
            doc = cs.collect_atlassian_history('example', base, out_root, fetch=fake_fetch(routes),
                                                sleep_fn=lambda s: None)
            self.assertEqual(len(doc['raw_files']), 2)
            by_url = {rf['url']: rf for rf in doc['raw_files']}
            self.assertEqual(by_url[f'{base}/history.json?page=1']['sha256'], cs.sha256_bytes(page1_body))
            self.assertEqual(by_url[f'{base}/incidents/INC1.json']['sha256'], cs.sha256_bytes(detail_body))
            raw_dir = out_root / 'raw' / 'example'
            self.assertTrue((raw_dir / 'history-page-1.json').exists())
            self.assertTrue((raw_dir / 'incident-INC1.json').exists())

    def test_max_pages_safety_cap(self):
        base = 'https://status.example.com'
        routes = {}
        for p in range(1, 4):
            routes[f'{base}/history.json?page={p}'] = history_page([
                month('September', 2026), month('August', 2026), month('July', 2026),
            ])
        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td) / 'incidents'
            doc = cs.collect_atlassian_history('example', base, out_root, fetch=fake_fetch(routes),
                                                sleep_fn=lambda s: None, max_pages=2)
        self.assertTrue(any('safety cap' in n for n in doc['notes']))


class RetryAndRateLimitTests(unittest.TestCase):
    def test_retries_transient_http_errors_then_succeeds(self):
        calls = {'n': 0}

        def flaky_fetch(url, timeout=20.0):
            calls['n'] += 1
            if calls['n'] < 3:
                raise cs.urllib.error.HTTPError(url, 503, 'Service Unavailable', {}, None)
            return b'ok'

        sleeps = []
        result = cs.fetch_with_retry(flaky_fetch, 'https://x', retries=3, sleep_fn=sleeps.append)
        self.assertEqual(result, b'ok')
        self.assertEqual(calls['n'], 3)
        self.assertEqual(len(sleeps), 2)

    def test_gives_up_after_retries_exhausted(self):
        def always_503(url, timeout=20.0):
            raise cs.urllib.error.HTTPError(url, 503, 'Service Unavailable', {}, None)

        with self.assertRaises(cs.urllib.error.HTTPError):
            cs.fetch_with_retry(always_503, 'https://x', retries=3, sleep_fn=lambda s: None)

    def test_non_transient_error_not_retried(self):
        calls = {'n': 0}

        def always_404(url, timeout=20.0):
            calls['n'] += 1
            raise cs.urllib.error.HTTPError(url, 404, 'Not Found', {}, None)

        with self.assertRaises(cs.urllib.error.HTTPError):
            cs.fetch_with_retry(always_404, 'https://x', retries=3, sleep_fn=lambda s: None)
        self.assertEqual(calls['n'], 1)


class ValidateAndDetectTests(unittest.TestCase):
    def test_validate_doc_catches_bad_severity(self):
        doc = {'schema': cs.INCIDENTS_SCHEMA, 'provider': 'x', 'status_page_url': 'u',
               'retrieved_utc': 'now', 'raw_files': [], 'severity_map': {},
               'incidents': [{'id': '1', 'title': 't', 'impact_label': 'weird', 'severity': 'weird',
                              'started_utc': 'x', 'is_maintenance': False, 'url': 'u'}]}
        problems = cs.validate_doc(doc)
        self.assertTrue(any('invalid severity' in p for p in problems))

    def test_detect_mode_atlassian(self):
        url = 'https://status.example.com'
        routes = {f'{url}/api/v2/status.json': j({'page': {'name': 'x'}, 'status': {'indicator': 'none'}})}
        self.assertEqual(cs.detect_mode(url, fetch=fake_fetch(routes)), 'atlassian')

    def test_detect_mode_generic_on_failure(self):
        url = 'https://status.example.com'
        self.assertEqual(cs.detect_mode(url, fetch=fake_fetch({})), 'generic')


if __name__ == '__main__':
    unittest.main()
