import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from launch_ledger import (  # noqa: E402
    validate_ledger, build_binding_draft, InvalidLedger, main,
    LEDGER_SCHEMA, FIELDS, STATUSES,
)
from make_demo import build  # noqa: E402


def make_field(status):
    if status == 'SUPPLIED':
        return {'status': 'SUPPLIED', 'value': 'example value',
                'source': {'url': 'https://example.invalid/evidence',
                           'sha256': 'a' * 64, 'retrieved_utc': '2026-01-01T00:00:00Z'}}
    if status == 'OMITTED':
        return {'status': 'OMITTED', 'omitted_claim': 'The release does not publish this for this provider.'}
    return {'status': 'NOT_YET_RELEASED'}


class LaunchLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        plan_bytes, binding_bytes, outcomes_bytes = build()
        cls.plan_bytes = plan_bytes
        cls.plan = json.loads(plan_bytes)
        cls.provider_ids = sorted({t['provider_id'] for t in cls.plan['trials']})

    def _ledger(self, status='SUPPLIED', providers=None):
        providers = self.provider_ids if providers is None else providers
        medals = {}
        for pid in providers:
            medals[pid] = {'medal': 'Gold', **{f: make_field(status) for f in FIELDS}}
        return {
            'schema': LEDGER_SCHEMA,
            'release_name': 'ClusterMAX 3.0 (synthetic test fixture)',
            'medal_table_source': {'url': 'https://example.invalid/medals',
                                    'sha256': 'b' * 64, 'retrieved_utc': '2026-01-01T00:00:00Z'},
            'rubric_source': {'url': 'https://example.invalid/rubric',
                               'sha256': 'c' * 64, 'retrieved_utc': '2026-01-01T00:00:00Z'},
            'medals': medals,
        }

    # -- validate_ledger ---------------------------------------------------
    def test_supplied_ledger_validates(self):
        report = validate_ledger(self._ledger('SUPPLIED'))
        self.assertTrue(report['has_sources'])
        self.assertEqual(report['unevaluable'], [])
        for field in FIELDS:
            self.assertEqual(report['field_status_counts'][field]['SUPPLIED'], len(self.provider_ids))

    def test_omitted_ledger_lists_unevaluable_claims(self):
        report = validate_ledger(self._ledger('OMITTED'))
        self.assertEqual(len(report['unevaluable']), len(self.provider_ids) * len(FIELDS))
        for item in report['unevaluable']:
            self.assertIn(item['field'], FIELDS)
            self.assertTrue(item['claim'])

    def test_not_yet_released_ledger_validates_with_no_sources_required(self):
        ledger = self._ledger('NOT_YET_RELEASED')
        del ledger['medal_table_source']
        del ledger['rubric_source']
        report = validate_ledger(ledger)
        self.assertFalse(report['has_sources'])
        self.assertEqual(report['unevaluable'], [])

    def test_wrong_schema_rejected(self):
        ledger = self._ledger('SUPPLIED')
        ledger['schema'] = 'not-the-schema'
        with self.assertRaises(InvalidLedger):
            validate_ledger(ledger)

    def test_unknown_status_rejected(self):
        ledger = self._ledger('SUPPLIED')
        ledger['medals'][self.provider_ids[0]]['scope']['status'] = 'MAYBE'
        with self.assertRaises(InvalidLedger):
            validate_ledger(ledger)

    def test_unknown_medal_tier_rejected(self):
        ledger = self._ledger('SUPPLIED')
        ledger['medals'][self.provider_ids[0]]['medal'] = 'Diamond'
        with self.assertRaises(InvalidLedger):
            validate_ledger(ledger)

    def test_supplied_without_source_rejected(self):
        ledger = self._ledger('SUPPLIED')
        del ledger['medals'][self.provider_ids[0]]['scope']['source']
        with self.assertRaises(InvalidLedger):
            validate_ledger(ledger)

    def test_supplied_without_value_rejected(self):
        ledger = self._ledger('SUPPLIED')
        del ledger['medals'][self.provider_ids[0]]['scope']['value']
        with self.assertRaises(InvalidLedger):
            validate_ledger(ledger)

    def test_omitted_without_claim_rejected(self):
        ledger = self._ledger('OMITTED')
        del ledger['medals'][self.provider_ids[0]]['scope']['omitted_claim']
        with self.assertRaises(InvalidLedger):
            validate_ledger(ledger)

    def test_source_block_non_hex_sha_rejected(self):
        ledger = self._ledger('SUPPLIED')
        ledger['medal_table_source']['sha256'] = 'not-hex'
        report = validate_ledger(ledger)  # top-level source blocks are optional/best-effort
        self.assertFalse(report['has_sources'])

    def test_empty_medals_rejected(self):
        ledger = self._ledger('SUPPLIED')
        ledger['medals'] = {}
        with self.assertRaises(InvalidLedger):
            validate_ledger(ledger)

    # -- build_binding_draft -------------------------------------------------
    def test_binding_draft_emission(self):
        ledger = self._ledger('SUPPLIED')
        plan_hash = hashlib.sha256(self.plan_bytes).hexdigest()
        draft = build_binding_draft(ledger, self.plan, plan_hash)
        self.assertEqual(draft['schema'], 'secondrun.rating-binding.v2')
        self.assertEqual(draft['plan_sha256'], plan_hash)
        self.assertEqual(draft['rating_name'], self.plan['rating_name'])
        self.assertEqual(draft['rating_version'], self.plan['rating_version'])
        self.assertEqual(set(draft['medals']), set(self.provider_ids))
        self.assertTrue(all(v == 'Gold' for v in draft['medals'].values()))
        self.assertEqual(draft['source']['url'], ledger['medal_table_source']['url'])
        self.assertEqual(draft['rubric']['url'], ledger['rubric_source']['url'])
        self.assertIn('bound_at', draft)

    def test_binding_draft_missing_provider_rejected(self):
        ledger = self._ledger('SUPPLIED')
        del ledger['medals'][self.provider_ids[0]]
        plan_hash = hashlib.sha256(self.plan_bytes).hexdigest()
        with self.assertRaises(InvalidLedger):
            build_binding_draft(ledger, self.plan, plan_hash)

    # -- CLI ------------------------------------------------------------
    def test_cli_summary_only(self):
        with tempfile.TemporaryDirectory() as td:
            ledger_path = Path(td) / 'ledger.json'
            ledger_path.write_text(json.dumps(self._ledger('SUPPLIED')), encoding='utf-8')
            self.assertEqual(main([str(ledger_path)]), 0)

    def test_cli_invalid_ledger_exit_code(self):
        with tempfile.TemporaryDirectory() as td:
            ledger_path = Path(td) / 'ledger.json'
            bad = self._ledger('SUPPLIED')
            bad['schema'] = 'wrong'
            ledger_path.write_text(json.dumps(bad), encoding='utf-8')
            self.assertEqual(main([str(ledger_path)]), 2)

    def test_cli_emits_binding_draft_with_plan(self):
        with tempfile.TemporaryDirectory() as td:
            ledger_path = Path(td) / 'ledger.json'
            ledger_path.write_text(json.dumps(self._ledger('SUPPLIED')), encoding='utf-8')
            plan_path = Path(td) / 'plan.json'
            plan_path.write_bytes(self.plan_bytes)
            out_path = Path(td) / 'binding-draft.json'
            rc = main([str(ledger_path), '--plan', str(plan_path), '--output', str(out_path)])
            self.assertEqual(rc, 0)
            draft = json.loads(out_path.read_text(encoding='utf-8'))
            self.assertEqual(draft['schema'], 'secondrun.rating-binding.v2')
            self.assertEqual(set(draft['medals']), set(self.provider_ids))

    def test_cli_no_draft_without_sources(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = self._ledger('NOT_YET_RELEASED')
            del ledger['medal_table_source']
            del ledger['rubric_source']
            ledger_path = Path(td) / 'ledger.json'
            ledger_path.write_text(json.dumps(ledger), encoding='utf-8')
            plan_path = Path(td) / 'plan.json'
            plan_path.write_bytes(self.plan_bytes)
            out_path = Path(td) / 'binding-draft.json'
            rc = main([str(ledger_path), '--plan', str(plan_path), '--output', str(out_path)])
            self.assertEqual(rc, 0)
            self.assertFalse(out_path.exists())

    def test_template_file_validates(self):
        template_path = ROOT / 'launch' / 'claims-3.0.template.json'
        ledger = json.loads(template_path.read_text(encoding='utf-8'))
        report = validate_ledger(ledger)
        self.assertEqual(report['unevaluable'], [])

    def test_statuses_constant(self):
        self.assertEqual(set(STATUSES), {'NOT_YET_RELEASED', 'SUPPLIED', 'OMITTED'})


if __name__ == '__main__':
    unittest.main()
