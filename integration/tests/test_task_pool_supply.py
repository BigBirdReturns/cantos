"""Real retained staging exposes date defects; synthetic cases test their isolation."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import task_pool
import task_sources
import work


class PoolSupply(unittest.TestCase):
    def setUp(self):
        scratch = Path('S:/Scratch/Temp') if os.name == 'nt' else Path(tempfile.gettempdir())
        self.temp = tempfile.TemporaryDirectory(prefix='pool-supply-', dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = ROOT / 'hot-aisle/campaign/providers/providers.jsonl'
        self.rows = [json.loads(line) for line in self.source.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
        self.review = {'as_of': '2026-09-28T03:31:28.099669Z', 'max_age_hours': 24}
        self.task = {'id': 'pool', 'task_class': 'pool-purchase', 'offers': str(self.source),
                     'source': str(HERE / 'examples/pool-request.json'), 'availability_review': self.review}

    def test_real_catalog_retains_future_and_undated_observations(self):
        before = self.source.read_bytes()
        output = task_sources.prepare({'task_class': 'provider-intake', 'source': str(self.source),
                                       'availability_review': self.review}, self.base)['execute']()
        offers = {offer['offer_id']: offer for offer in output['offers']}
        self.assertEqual(len(offers), len(self.rows))
        for oid in ('nebius-h100-oct1', 'hot-aisle-mi300x-1'):
            check = offers[oid]
            self.assertEqual(check['availability_review']['status'], 'invalid_observation')
            self.assertTrue(check['holds'])
            self.assertEqual(check['native_row'], next(r for r in self.rows if r['offer_id'] == oid))
        self.assertEqual(offers['latitude-h100-1']['availability_review']['status'], 'stale_observation')
        self.assertEqual(self.source.read_bytes(), before)

    def test_one_bad_observation_keeps_a_good_peer_usable(self):
        good = copy.deepcopy(next(r for r in self.rows if r['offer_id'] == 'latitude-h100-1'))
        good['availability_ts'] = self.review['as_of']
        good['notes'] = 'Synthetic time change for mechanical isolation test.'
        bad = dict(good, offer_id='synthetic-undated', availability_ts=None)
        source = self.base / 'two.jsonl'
        source.write_text('\n'.join(json.dumps(r) for r in (bad, good)), encoding='utf-8')
        output = task_sources.prepare({'task_class': 'provider-intake', 'source': str(source),
                                       'availability_review': self.review}, self.base)['execute']()
        broken, valid = output['offers']
        self.assertTrue(broken['holds'])
        self.assertEqual(valid['availability_review']['status'], 'observed_available_within_window')
        self.assertEqual(valid['holds'], [])
        self.assertFalse(valid['availability_review']['rentable_now'])

    def test_supply_qualifications_reach_references_without_repricing(self):
        output = task_pool.prepare(self.task, self.base)['execute']()
        owner = task_pool._owner(task_pool.POOL_OWNER)
        original = owner.plan(json.loads(Path(self.task['source']).read_bytes()), self.rows)
        self.assertEqual(output['plan_count'], original['plan_count'])
        prior = {p['offer_id']: p for p in original['plans']}
        for plan in output['plans']:
            self.assertFalse(plan['bindable_at_list'] or plan['execution_authority'])
            self.assertEqual(plan['all_accepting']['schedule'], prior[plan['offer_id']]['all_accepting']['schedule'])
            self.assertEqual(plan['coalition_saving_usd'], prior[plan['offer_id']]['coalition_saving_usd'])
        self.assertTrue(all(ref is None for ref in output['standalone_unqualified'].values()))
        self.assertTrue(all(ref['qualifications'] for ref in output['standalone'].values() if ref))
        self.assertFalse(output['supply']['ready'])
        self.assertEqual(output['supply']['intake']['offer_count'], len(self.rows))

    def test_no_review_does_not_erase_missing_age_evidence(self):
        task = dict(self.task)
        del task['availability_review']
        result = task_pool.prepare(task, self.base)['execute']()
        offered = next(o for o in result['supply']['intake']['offers'] if o['offer_id'] == 'latitude-h100-1')
        self.assertEqual(offered['availability_review']['status'], 'age_not_assessed')
        self.assertTrue(offered['holds'])
        self.assertTrue(all(ref is None for ref in result['standalone_unqualified'].values()))

    def test_native_owner_refuses_unbound_qualification_ids(self):
        owner = task_pool._owner(task_pool.POOL_OWNER)
        with self.assertRaisesRegex(ValueError, 'exact unique offer_id'):
            owner.plan(json.loads(Path(self.task['source']).read_bytes()), self.rows, source_holds={'wrong': []})

    def test_review_window_changes_pool_identity_but_not_independent_import(self):
        store = self.base / 'work-store'
        other = {'id': 'import', 'task_class': 'benchmark-import',
                 'source': str(ROOT / 'hot-aisle/campaign/backfill/fixtures/manifest.json')}
        first = work.run({'tasks': [self.task, other]}, self.base, store)
        self.assertEqual(first['summary'], {'executed': 2, 'reused': 0, 'held': 0})
        again = work.run({'tasks': [dict(self.task, actor='fresh-process-label'), other]}, self.base, store)
        self.assertEqual(again['summary'], {'executed': 0, 'reused': 2, 'held': 0})
        changed = copy.deepcopy(self.task)
        changed['availability_review']['max_age_hours'] = 168
        third = work.run({'tasks': [changed, other]}, self.base, store)
        self.assertEqual(third['summary'], {'executed': 1, 'reused': 1, 'held': 0})
        self.assertEqual(first['tasks'][1]['key'], third['tasks'][1]['key'])
        self.assertNotEqual(first['tasks'][0]['key'], third['tasks'][0]['key'])
        self.assertEqual(third['model_calls'], 0)
        self.assertEqual(third['gpu_runs'], 0)
        relocated = self.base / 'same-offers.jsonl'
        relocated.write_bytes(self.source.read_bytes())
        fourth = work.run({'tasks': [dict(self.task, offers=str(relocated))]}, self.base, store)
        self.assertEqual(fourth['summary'], {'executed': 0, 'reused': 1, 'held': 0})

    def test_documentation_shape_never_contributes_a_price_alternative(self):
        # Authored mechanical fixture, not a captured marketplace response.
        raw = {'offers': [{'id': 7, 'num_gpus': 8, 'gpu_name': 'MI300X', 'resource_type': 'gpu',
                          'search': {'gpuCostPerHour': 4}, 'rentable': True, 'rented': False}]}
        source = self.base / 'sample.json'
        source.write_text(json.dumps(raw), encoding='utf-8')
        task = dict(self.task, offers=str(source), marketplace_snapshot={
            'source_url': 'https://docs.vast.ai/api-reference/search/search-offers',
            'captured_at': '2026-09-28T00:00:00Z', 'evidence_class': 'official_documentation_sample'})
        result = task_pool.prepare(task, self.base)['execute']()
        self.assertEqual(result['plan_count'], 0)
        self.assertEqual(result['offers_considered'], 0)
        self.assertEqual(result['supply']['intake']['offer_count'], 1)
        self.assertEqual(result['supply']['intake']['offers'][0]['marketplace_evidence']['raw_offer'], raw['offers'][0])
        self.assertIn('fictional', result['offers_excluded'][0]['reason'])
        self.assertTrue(all(v is None for v in result['standalone'].values()))
        self.assertFalse(result['supply']['execution_authorized'])


if __name__ == '__main__':
    unittest.main()
