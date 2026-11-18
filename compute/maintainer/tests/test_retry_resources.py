"""Resource-boundary acceptance with independently calculated integrals."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import retry_resources as resources


class ResourceBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = {'hostname': 'fixture', 'boot_id': 'fixture-boot', 'clock': 'monotonic'}
        self.campaign = {'observation_id': 'fixture-observation', 'clock_identity': self.clock}
        self.source = {'sha256': 'a'*64}

    def telemetry(self, points=None, gap=1.1, failures=()):
        points = points if points is not None else [(0, 10), (1, 20), (2, 30), (3, 40)]
        head = {'kind': 'sampler_started', 'clock_identity': self.clock,
                'devices': ['GPU-fixture'], 'max_gap_s': gap,
                'producer': {'sha256': 'fixture-producer'}}
        body = [{'kind': 'power_sample', 't_s': at,
                 'readings': [{'device_uuid': 'GPU-fixture', 'watts': watts}]} for at, watts in points]
        body += [{'kind': 'sample_error', 't_s': at, 'error': 'fixture'} for at in failures]
        body.sort(key=lambda x: x['t_s'])
        journal = self.root/'samples.jsonl'
        journal.write_text('\n'.join(json.dumps(x) for x in [head]+body+[{'kind': 'sampler_ended'}])+'\n')
        receipt = {'schema': 'cantos.retry.telemetry/1', 'campaign_sha256': self.source['sha256'],
                   'observation_id': self.campaign['observation_id'], 'clock_identity': self.clock,
                   'devices': head['devices'], 'max_gap_s': gap, 'producer': head['producer'],
                   'samples': {'path': journal.name, 'sha256': hashlib.sha256(journal.read_bytes()).hexdigest(),
                               'bytes': journal.stat().st_size},
                   'evidence_class': 'synthetic-accounting-fixture'}
        path = self.root/'telemetry.json'
        path.write_text(json.dumps(receipt))
        return path

    def read(self, path, accepted=3):
        return resources.read_telemetry(path, self.campaign, self.source, .5, 2.5, accepted)

    def test_interpolation_all_campaign_energy_over_all_accepted_work(self):
        # Integral of W=10+10t from .5 to 2.5 is exactly 50 J.
        result = self.read(self.telemetry())
        self.assertEqual(result['gross_board_joules'], 50)
        self.assertAlmostEqual(result['gross_board_joules_per_accepted_task'], 50/3)
        self.assertEqual(result['scope'], 'gpu_board')
        self.assertFalse(result['calibrated'])

    def test_zero_success_keeps_energy_and_null_ratio(self):
        result = self.read(self.telemetry(), 0)
        self.assertEqual(result['gross_board_joules'], 50)
        self.assertIsNone(result['gross_board_joules_per_accepted_task'])
        self.assertEqual(result['denominator_status'], 'zero_accepted_tasks')

    def test_unbracketed_or_gapped_samples_remain_unknown(self):
        for points in [[(1, 20), (2, 30), (3, 40)], [(0, 10), (1, 20), (2, 30)], [(0, 10), (3, 40)]]:
            with self.subTest(points=points):
                self.assertIsNone(self.read(self.telemetry(points))['gross_board_joules'])

    def test_sensor_error_inside_window_prevents_interpolation_over_error(self):
        self.assertIsNone(self.read(self.telemetry(failures=[1.5]))['gross_board_joules'])

    def test_clock_campaign_and_device_identity_are_checked(self):
        path = self.telemetry()
        original = json.loads(path.read_text())
        for key, value in [('campaign_sha256', 'b'*64), ('clock_identity', {'hostname': 'wrong'}),
                           ('observation_id', 'different'), ('devices', ['GPU-other']), ('max_gap_s', 10)]:
            with self.subTest(key=key):
                path.write_text(json.dumps({**original, key: value}))
                with self.assertRaises(ValueError):
                    self.read(path)

    def test_raw_tamper_is_rejected(self):
        path = self.telemetry()
        (self.root/'samples.jsonl').write_text('changed')
        with self.assertRaises(ValueError):
            self.read(path)

    def test_invalid_watts_and_duplicate_timestamps_are_rejected(self):
        for points in [[(0,10),(1,-2),(2,30),(3,40)], [(0,10),(1,20),(1,30),(3,40)]]:
            with self.subTest(points=points):
                with self.assertRaises(ValueError):
                    self.read(self.telemetry(points))

    def test_missing_cost_fields_do_not_become_free_compute(self):
        path = self.root/'scenario.json'
        path.write_text(json.dumps({'schema': 'cantos.retry.cost-scenario/1', 'currency': 'USD',
            'values': {'hosting_usd_per_hour': 3.6},
            'field_sources': {'hosting_usd_per_hour': 'Explicit accounting fixture assumption'}}))
        cost = resources.read_scenario(path, 10, 3)
        self.assertEqual(cost['components']['hosting_usd'], .01)
        self.assertIsNone(cost['total_usd'])
        self.assertIsNone(cost['actual_total_cost_usd'])
        self.assertIsNone(cost['modeled_cost_per_accepted_usd'])

    def test_nonnull_cost_requires_source(self):
        path = self.root/'scenario.json'
        path.write_text(json.dumps({'schema': 'cantos.retry.cost-scenario/1', 'currency': 'USD',
            'values': {'hosting_usd_per_hour': 3.6}, 'field_sources': {}}))
        with self.assertRaises(ValueError):
            resources.read_scenario(path, 10, 3)


if __name__ == '__main__':
    unittest.main()
