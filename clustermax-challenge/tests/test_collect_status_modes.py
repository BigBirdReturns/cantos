"""Tests for the Better Stack, Instatus and SorryApp modes of scripts/collect_status.py.

Fixtures are saved provider pages copied from the R2 raw lane (see fixtures/status_modes/MANIFEST.json for
the two mechanical changes made to HTML copies). Expected values are the hand-parsed R2 incident files,
so these tests also check that the automated modes reproduce what the R2 collection recorded.
Nothing here touches the network.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'scripts'))
import collect_status as cs  # noqa: E402

FIX = HERE / 'fixtures' / 'status_modes'
INC = HERE.parent / 'retrospective' / 'incidents'


def load(name):
    return json.loads((INC / name).read_text(encoding='utf-8'))


def fixture_fetch(routes):
    def fetch(url):
        path = routes.get(url)
        if path is None:
            raise urllib.error.HTTPError(url, 404, 'not found', {}, None)
        return (FIX / path).read_bytes()
    return fetch


def subset(doc, ids):
    return sorted((i for i in doc['incidents'] if i['id'] in ids), key=lambda i: i['id'])


class BetterStackTests(unittest.TestCase):
    BASE = 'https://status.verda.com'

    def routes(self):
        r = {f'{self.BASE}/incidents/2026-04/2026-06': 'verda/incidents_2026-04_2026-06.html'}
        for i in ('901666', '905600', '909828'):
            r[f'{self.BASE}/incident/{i}'] = f'verda/incident_{i}.html'
        return r

    def test_quarter_and_detail_pages_match_hand_parsed_r2_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = cs.collect_betterstack('verda', self.BASE, Path(tmp), fetch=fixture_fetch(self.routes()),
                                         start=date(2026, 4, 1), today=date(2026, 6, 30))
            self.assertEqual(cs.validate_doc(doc), [])
            self.assertEqual(doc['coverage_start'], '2026-04-01')
            self.assertEqual(doc['coverage_end'], '2026-06-30')
            got = sorted(doc['incidents'], key=lambda i: i['id'])
            self.assertEqual(got, subset(load('verda.json'), {'901666', '905600', '909828'}))
            self.assertEqual(len(doc['raw_files']), 4)
            for rf in doc['raw_files']:
                self.assertRegex(rf['sha256'], r'^[0-9a-f]{64}$')
                self.assertTrue((Path(tmp) / 'raw' / 'verda' / Path(rf['path']).name).exists())

    def test_worst_state_colour_sets_severity(self):
        body = (FIX / 'verda/incident_901666.html').read_bytes()
        got = cs.parse_betterstack_incident(body, self.BASE, '901666')
        want = next(i for i in load('verda.json')['incidents'] if i['id'] == '901666')
        self.assertEqual(got['impact_label'], want['impact_label'])
        self.assertEqual(got['severity'], want['severity'])
        self.assertIn(got['severity'], cs.NORMALIZED_SEVERITIES)

    def test_zero_incident_quarter_is_a_zero_file_with_the_page_marker_counted(self):
        base = 'https://status.together.ai'
        routes = {f'{base}/incidents/2026-07/2026-09': 'together-ai/incidents_2026-07_2026-09.html'}
        with tempfile.TemporaryDirectory() as tmp:
            doc = cs.collect_betterstack('together-ai', base, Path(tmp), fetch=fixture_fetch(routes),
                                         start=date(2026, 7, 1), today=date(2026, 9, 29))
        self.assertEqual(doc['incidents'], [])
        self.assertEqual(doc['coverage_start'], '2026-07-01')
        self.assertTrue(any('No incidents reported' in n and ': 3' in n for n in doc['notes']))

    def test_detail_fetch_failure_records_nothing_for_that_incident(self):
        routes = self.routes()
        del routes[f'{self.BASE}/incident/905600']
        with tempfile.TemporaryDirectory() as tmp:
            doc = cs.collect_betterstack('verda', self.BASE, Path(tmp), fetch=fixture_fetch(routes),
                                         start=date(2026, 4, 1), today=date(2026, 6, 30), sleep_fn=lambda s: None)
        self.assertEqual({i['id'] for i in doc['incidents']}, {'901666', '909828'})
        self.assertTrue(any('905600' in n for n in doc['notes']))

    def test_non_betterstack_page_is_unsupported_not_zero_incidents(self):
        def fetch(url):
            return b'<html><body>Instatus - Get ready for downtime</body></html>'
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(cs.UnsupportedPlatform):
                cs.collect_betterstack('x', 'https://status.example.com', Path(tmp), fetch=fetch,
                                       start=date(2026, 7, 1), today=date(2026, 9, 29))


class InstatusTests(unittest.TestCase):
    BASE = 'https://status.mithril.ai'

    def routes(self):
        r = {}
        for m in ('05', '06', '07', '08', '09'):
            month_key = int(datetime(2026, int(m), 1, tzinfo=timezone.utc).timestamp() * 1000)
            r[f'{cs.INSTATUS_API}/status.mithril.ai/notices/monthly/{month_key}?page_no=1'] = f'mithril/notices_2026-{m}_p1.json'
        return r

    def test_months_match_hand_parsed_r2_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = cs.collect_instatus('mithril', self.BASE, Path(tmp), fetch=fixture_fetch(self.routes()),
                                      start=date(2026, 5, 1), today=date(2026, 9, 29))
        self.assertEqual(cs.validate_doc(doc), [])
        want = [i for i in load('mithril.json')['incidents'] if i['started_utc'] >= '2026-05-01']
        self.assertEqual(doc['incidents'], sorted(want, key=lambda i: i['started_utc']))
        self.assertEqual(doc['coverage_start'], '2026-05-01')
        self.assertEqual(len(doc['raw_files']), 5)

    def test_severity_mapping_is_the_declared_one(self):
        self.assertEqual(cs.INSTATUS_SEVERITY['MAJOROUTAGE'], 'critical')
        self.assertEqual(cs.INSTATUS_SEVERITY['PARTIALOUTAGE'], 'major')
        self.assertEqual(cs.INSTATUS_SEVERITY['DEGRADEDPERFORMANCE'], 'minor')
        self.assertEqual(cs.INSTATUS_SEVERITY['UNDERMAINTENANCE'], 'none')

    def test_maintenance_uses_start_field_and_is_flagged(self):
        n = {'id': 'abc', 'name': {'default': 'Planned', 'en': 'Planned'}, 'start': '2026-01-29T13:00:00.000Z',
             'resolved': '2026-01-29T14:00:00.000Z', 'impact': 'UNDERMAINTENANCE'}
        got = cs.normalize_instatus_notice(n, self.BASE)
        self.assertTrue(got['is_maintenance'])
        self.assertEqual(got['started_utc'], '2026-01-29T13:00:00.000Z')
        self.assertEqual(got['severity'], 'none')

    def test_page_key_uses_subdomain_for_instatus_hosts(self):
        self.assertEqual(cs.instatus_page_key('https://atlascloud.instatus.com'), 'atlascloud')
        self.assertEqual(cs.instatus_page_key('https://status.gcore.com/'), 'status.gcore.com')

    def test_unanswered_api_is_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(cs.UnsupportedPlatform):
                cs.collect_instatus('x', 'https://palebluedot.instatus.com', Path(tmp), fetch=fixture_fetch({}),
                                    start=date(2026, 9, 1), today=date(2026, 9, 29), sleep_fn=lambda s: None)


class SorryAppTests(unittest.TestCase):
    BASE = 'https://status.radiant.co'

    def routes(self):
        return {f'{self.BASE}/history/2026/january': 'radiant/history_2026-january.html',
                f'{self.BASE}/history/2026/march': 'radiant/history_2026-march.html'}

    def test_cards_parse_and_missing_month_is_noted_not_filled(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = cs.collect_sorryapp('radiant', self.BASE, Path(tmp), fetch=fixture_fetch(self.routes()),
                                      start=date(2026, 1, 1), today=date(2026, 3, 31), sleep_fn=lambda s: None)
        self.assertEqual(cs.validate_doc(doc), [])
        byid = {i['id']: i for i in doc['incidents']}
        self.assertEqual(sorted(byid), ['478686', '488667', '489271'])
        self.assertFalse(byid['478686']['is_maintenance'])          # Resolved card = incident
        self.assertEqual(byid['478686']['title'], 'Service Disruption in Seattle')
        self.assertEqual(byid['478686']['started_utc'], '2026-01-16T10:25:12Z')
        self.assertTrue(byid['488667']['is_maintenance'])           # Complete card = maintenance
        self.assertFalse(byid['489271']['is_maintenance'])
        self.assertTrue(all(i['severity'] == 'none' for i in doc['incidents']))  # SorryApp exposes no severity
        self.assertTrue(any('2026-02' in n and '404' in n for n in doc['notes']))
        self.assertEqual(len(doc['raw_files']), 2)

    def test_first_month_error_is_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(cs.UnsupportedPlatform):
                cs.collect_sorryapp('x', 'https://status.example.com', Path(tmp), fetch=fixture_fetch({}),
                                    start=date(2026, 1, 1), today=date(2026, 1, 31), sleep_fn=lambda s: None)


class DetectionAndCliTests(unittest.TestCase):
    def test_existing_detection_results_are_unchanged(self):
        # both Atlassian probes fail and no extra platform answers -> generic, exactly as before
        self.assertEqual(cs.detect_mode('https://status.example.com', fetch=fixture_fetch({})), 'generic')
        routes = {'https://s.example/history.json?page=1': None}
        page = json.dumps({'months': []}).encode()
        self.assertEqual(cs.detect_mode('https://s.example', fetch=lambda u: page if 'history.json' in u else b'x'),
                         'atlassian-history')

    def test_betterstack_page_is_detected_after_atlassian_probes_fail(self):
        body = b"<a href='/incidents/2026-07/2026-09'>x</a> <a href='https://betterstack.com/'>Powered by</a>"
        def fetch(url):
            if url.endswith('/incidents'):
                return body
            raise urllib.error.HTTPError(url, 404, 'nf', {}, None)
        self.assertEqual(cs.detect_mode('https://status.example.com', fetch=fetch), 'betterstack')

    def test_new_modes_are_cli_choices_and_unsupported_exits_3(self):
        with mock.patch.object(cs, 'collect_instatus', side_effect=cs.UnsupportedPlatform('nope')):
            with tempfile.TemporaryDirectory() as tmp:
                rc = cs.main(['--slug', 'x', '--url', 'https://x.instatus.com', '--mode', 'instatus',
                              '--out-root', tmp])
        self.assertEqual(rc, 3)
        with self.assertRaises(SystemExit):
            cs.main(['--slug', 'x', '--url', 'https://x', '--mode', 'nonsense'])


if __name__ == '__main__':
    unittest.main()
