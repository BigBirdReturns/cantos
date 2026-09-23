"""Offline qualification; all writes use temporary directories inside this lane."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import unittest
from unittest.mock import patch
import urllib.error
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
import probe
import heatmap

ROOT = Path(__file__).resolve().parent
NOW = '2026-09-23T21:00:00Z'


def fixture(name):
    return json.loads((ROOT / 'fixtures' / name).read_text(encoding='utf-8'))


class AvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.cfg = probe.config(ROOT / 'probes.json')
        self.target = self.cfg['probes'][2]
        self.ha = self.cfg['probes'][0]
        # Python 3.13's Windows mode-0700 temp ACL excludes this sandbox token.
        # Inherit the lane ACL instead; all test data is synthetic.
        self.temp = ROOT / ('test-tmp-' + uuid.uuid4().hex)
        self.temp.mkdir(mode=0o755)
        self.addCleanup(self.cleanup)
        self.out = self.temp / 'observations.jsonl'

    def cleanup(self):
        for path in self.temp.iterdir():
            path.unlink()
        self.temp.rmdir()

    def test_missing_tokens_no_network(self):
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network')):
            rows = probe.collect(self.cfg, env={}, now=NOW)
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(r['outcome'] == 'unknown' and r['layer'] == 'listed' for r in rows))
        self.assertTrue(all('missing ' in r['reason'] for r in rows))

    def test_dry_run_never_calls_fetch_and_labels_synthetic(self):
        rows = probe.collect(self.cfg, True, fetch=lambda *a: self.fail('network'), now=NOW)
        self.assertTrue(all(r['synthetic'] for r in rows))
        self.assertEqual(sum(r['outcome'] == 'available' for r in rows), 2)
        self.assertEqual(rows[-1]['outcome'], 'unknown')

    def test_do_regions_flag_gpu_count_and_missing(self):
        rows = fixture('digitalocean.json')['sizes']
        self.assertEqual(probe.digitalocean(rows, self.target)[0], 'available')
        self.assertEqual(probe.digitalocean(rows, dict(self.target, region='ams3'))[0], 'out_of_capacity')
        self.assertEqual(probe.digitalocean(rows, dict(self.target, gpus=8))[0], 'unknown')
        self.assertEqual(probe.digitalocean([], self.target)[0], 'unknown')
        self.assertEqual(probe.digitalocean(rows+rows, self.target)[0], 'unknown')
        for invalid in ('true', 1, None):
            bad = copy.deepcopy(rows)
            bad[0]['available'] = invalid
            self.assertEqual(probe.digitalocean(bad, self.target)[0], 'unknown')

    def test_hotaisle_region_and_quantity(self):
        rows = fixture('hotaisle.json')
        self.assertEqual(probe.hotaisle(rows, self.ha, {})[0], 'unknown')
        scoped = {'region_scope':'enc1'}
        self.assertEqual(probe.hotaisle(rows, self.ha, scoped)[0], 'available')
        self.assertEqual(probe.hotaisle(rows, self.cfg['probes'][1], scoped)[0], 'out_of_capacity')
        rows[0]['Quantity'] = True
        self.assertEqual(probe.hotaisle(rows, self.ha, scoped)[0], 'unknown')

    def test_hotaisle_request_identity(self):
        cfg = copy.deepcopy(self.cfg)
        cfg['probes'] = [self.ha]
        cfg['hotaisle'] = {'team':'test/team', 'auth_status':'verified', 'region_scope':'enc1'}
        calls = []
        def fetch(url, header):
            calls.append((url, header))
            return fixture('hotaisle.json')
        rows = probe.collect(cfg, env={'HOTAISLE_API_TOKEN':'fixture-secret'}, fetch=fetch)
        self.assertEqual(calls, [(probe.HA+'/teams/test%2Fteam/virtual_machines/available/', 'Token fixture-secret')])
        self.assertEqual(rows[0]['outcome'], 'available')
        self.assertNotIn('fixture-secret', json.dumps(rows))

    def test_pagination_and_auth(self):
        calls = []
        def fetch(url, header):
            calls.append((url, header))
            if len(calls) == 1:
                return {'sizes':[], 'links':{'pages':{'next':probe.DO+'?page=2'}}}
            return fixture('digitalocean.json')
        rows = probe.do_pages('fixture-secret', fetch)
        self.assertEqual(len(rows), 4)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(h == 'Bearer fixture-secret' for _, h in calls))

    def test_pagination_rejects_cross_host_and_cycles(self):
        for url in ('https://evil.example/sizes', 'http://api.digitalocean.com/v2/sizes', probe.DO+'?per_page=200'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                probe.do_pages('fixture', lambda *a: {'sizes':[], 'links':{'pages':{'next':url}}})

    def test_redirects_refused(self):
        with self.assertRaises(ValueError):
            probe.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere.example')

    def test_http_timeout_and_malformed_are_unknown_without_secret(self):
        cfg = dict(self.cfg, probes=[self.target])
        failures = [urllib.error.HTTPError(probe.DO, n, 'fixture-secret', {}, None) for n in (401,403,429,500)]
        failures += [TimeoutError('fixture-secret'), ValueError('fixture-secret'), TypeError('fixture-secret')]
        for error in failures:
            def fetch(*args):
                raise error
            rows = probe.collect(cfg, env={'DIGITALOCEAN_TOKEN':'fixture-secret'}, fetch=fetch)
            self.assertEqual(rows[0]['outcome'], 'unknown')
            self.assertNotIn('fixture-secret', json.dumps(rows))
        rows = probe.collect(cfg, env={'DIGITALOCEAN_TOKEN':'fixture'}, fetch=lambda *a: {'sizes':[{'slug':self.target['sku'], 'available':True, 'regions':[], 'gpu_info':None}]})
        self.assertEqual(rows[0]['outcome'], 'unknown')

    def receipt(self):
        r = fixture('delivered.json')
        r.update(real_create_attempt=True, synthetic=False)
        return r

    def test_delivered_requires_real_create_and_ssh(self):
        with self.assertRaises(ValueError):
            probe.delivered(fixture('delivered.json'))
        r = self.receipt()
        self.assertEqual(probe.delivered(r)['layer'], 'delivered')
        for changes in ({'ssh_reached':False}, {'time_to_ssh_s':-1}, {'time_to_ssh_s':float('nan')}, {'evidence':''}, {'attempt_id':''}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                probe.delivered(dict(r, **changes))
        failed = probe.delivered(dict(r, outcome='create_failed', ssh_reached=False))
        self.assertFalse(failed['provisioned'])
        self.assertNotIn('time_to_ssh_s', failed)

    def test_append_preserves_prefix_rejects_duplicates_and_partial_tail(self):
        seed = b'{"old":true}\n'
        self.out.write_bytes(seed)
        row = probe.delivered(self.receipt())
        probe.append(self.out, [row])
        self.assertTrue(self.out.read_bytes().startswith(seed))
        before = self.out.read_bytes()
        with self.assertRaises(ValueError):
            probe.append(self.out, [row])
        self.assertEqual(before, self.out.read_bytes())
        self.out.write_bytes(b'{"partial":')
        with self.assertRaises(ValueError):
            probe.append(self.out, [row])
        self.assertEqual(self.out.read_bytes(), b'{"partial":')

    def test_lock_prevents_competing_writer(self):
        with probe.ledger_lock(self.out):
            with self.assertRaises(FileExistsError):
                probe.append(self.out, [])
        self.assertFalse(Path(str(self.out)+'.lock').exists())

    def records(self):
        return [json.loads(s) for s in (ROOT/'fixtures/observations.jsonl').read_text().splitlines()]

    def test_heatmap_denominators_and_hour_boundaries(self):
        records = self.records()
        start, now, grid, excluded = heatmap.aggregate(records, [self.target], NOW)
        cells = grid[probe.key(self.target)]
        self.assertEqual(len(cells), 168)
        cell = cells[166]
        self.assertEqual((cell['yes'], cell['valid'], cell['unknown'], len(cell['slots'])), (1,2,1,3))
        self.assertEqual(cell['attempts'], ['available','create_failed'])
        self.assertEqual(cells[167]['valid'], 0)
        page, summary = heatmap.render(records, [self.target], NOW)
        self.assertIn('listed 1/2; unknown 1; missed 1/4 slots; delivered 1/2', summary)
        self.assertIn('fill="hsl(90,65%,43%)"', page)
        self.assertIn('fill="#94a3b8"', page)
        svg = page[page.index('<svg '):page.index('</svg>')+6]
        root = ET.fromstring(svg)
        self.assertEqual(len(root.findall('{http://www.w3.org/2000/svg}rect')), 168)
        self.assertEqual(len(root.findall('{http://www.w3.org/2000/svg}circle')), 2)

    def test_synthetic_legacy_future_and_old_exclusions(self):
        row = self.records()[0]
        records = [dict(row, synthetic=True), dict(row, ts='2026-09-24T00:00:00Z'),
                   dict(row, ts='2026-09-01T00:00:00Z'),
                   dict(row, layer=None, method='tui-provision-list', provisioned=True)]
        _, _, grid, excluded = heatmap.aggregate(records, [self.target], NOW)
        self.assertEqual(sum(c['valid'] for c in grid[probe.key(row)]), 0)
        self.assertEqual(sum(excluded.values()), 4)

    def test_legacy_create_only_counts_ssh_evidence(self):
        row = dict(self.records()[0], layer=None, method='console-create', provisioned=True)
        _, _, grid, _ = heatmap.aggregate([row], [self.target], NOW)
        self.assertEqual(grid[probe.key(row)][166]['attempts'], ['unknown'])
        row['time_to_ssh_s'] = 60
        _, _, grid, _ = heatmap.aggregate([row], [self.target], NOW)
        self.assertEqual(grid[probe.key(row)][166]['attempts'], ['available'])

    def test_html_escaping_and_duplicate_attempts(self):
        row = dict(self.records()[0], sku='<script>alert(1)</script>')
        page, _ = heatmap.render([row], [row], NOW)
        self.assertNotIn('<script>', page)
        self.assertIn('&lt;script&gt;', page)
        records = self.records()
        with self.assertRaises(ValueError):
            heatmap.render(records + [records[-1]], [self.target], NOW)

    def test_cli_dry_run_and_delivered_fixture_guard(self):
        before = (ROOT/'observations.jsonl').read_bytes()
        result = subprocess.run([sys.executable, '-B', str(ROOT/'probe.py'), '--dry-run'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 12)
        self.assertEqual(before, (ROOT/'observations.jsonl').read_bytes())
        result = subprocess.run([sys.executable, '-B', str(ROOT/'probe.py'), '--dry-run', '--output', str(ROOT/'observations.jsonl')], capture_output=True)
        self.assertEqual(result.returncode, 2)
        result = subprocess.run([sys.executable, '-B', str(ROOT/'probe.py'), '--delivered', str(ROOT/'fixtures/delivered.json'), '--output', str(self.out)], capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.out.exists())

    def test_cli_missing_tokens_appends_unknown_and_exits_one(self):
        env = {k:v for k,v in os.environ.items() if k not in probe.TOKENS.values()}
        result = subprocess.run([sys.executable, '-B', str(ROOT/'probe.py'), '--output', str(self.out)], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        rows = [json.loads(line) for line in self.out.read_text().splitlines()]
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(r['outcome'] == 'unknown' and not r['synthetic'] for r in rows))

    def test_cli_render_and_input_protection(self):
        output = self.temp/'heatmap.html'
        summary = self.temp/'heatmap.txt'
        args = [sys.executable, '-B', str(ROOT/'heatmap.py'), '--input', str(ROOT/'fixtures/observations.jsonl'), '--now', NOW, '--html', str(output), '--summary', str(summary)]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('listed 1/2', summary.read_text())
        args[-1] = args[5]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
