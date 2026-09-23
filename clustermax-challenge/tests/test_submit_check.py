import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import submit_check as sc  # noqa: E402
from make_demo import build  # noqa: E402

DISCLOSURE = '## Disclosure\n\nNo relationship with any rated provider.\n'


class SubmitCheckTests(unittest.TestCase):
    def _write_submission(self, sub_dir: Path, include_disclosure=True, drop=None):
        sub_dir.mkdir(parents=True)
        plan_bytes, binding_bytes, outcomes_bytes = build()
        if drop != 'plan.json':
            (sub_dir / 'plan.json').write_bytes(plan_bytes)
        if drop != 'binding.json':
            (sub_dir / 'binding.json').write_bytes(binding_bytes)
        if drop != 'outcomes.json':
            (sub_dir / 'outcomes.json').write_bytes(outcomes_bytes)
        if drop != 'SUBMITTER.md':
            text = '# Submitter\n\n' + (DISCLOSURE if include_disclosure else 'No section here.\n')
            (sub_dir / 'SUBMITTER.md').write_text(text, encoding='utf-8')

    def test_valid_submission_passes(self):
        with tempfile.TemporaryDirectory() as td:
            sub_dir = Path(td) / 'example'
            self._write_submission(sub_dir)
            report = sc.check_submission(sub_dir)
            self.assertTrue(report['ok'], report)
            # Deliberately not asserting an exact status string here: challenge.py
            # is owned and versioned by a concurrent workstream, and submit_check.py
            # only needs to distinguish HOLD from everything else.
            self.assertNotEqual(report['status'], 'HOLD')
            self.assertEqual(set(report['hashes']), {'plan.json', 'binding.json', 'outcomes.json', 'SUBMITTER.md'})

    def test_missing_binding_fails(self):
        with tempfile.TemporaryDirectory() as td:
            sub_dir = Path(td) / 'example'
            self._write_submission(sub_dir, drop='binding.json')
            report = sc.check_submission(sub_dir)
            self.assertFalse(report['ok'])
            self.assertTrue(any('binding.json' in p for p in report['problems']))

    def test_missing_disclosure_fails(self):
        with tempfile.TemporaryDirectory() as td:
            sub_dir = Path(td) / 'example'
            self._write_submission(sub_dir, include_disclosure=False)
            report = sc.check_submission(sub_dir)
            self.assertFalse(report['ok'])
            self.assertTrue(any('disclosure' in p for p in report['problems']))

    def test_missing_file_fails(self):
        with tempfile.TemporaryDirectory() as td:
            sub_dir = Path(td) / 'example'
            self._write_submission(sub_dir, drop='outcomes.json')
            report = sc.check_submission(sub_dir)
            self.assertFalse(report['ok'])
            self.assertTrue(any('outcomes.json' in p for p in report['problems']))

    def test_cli_exit_code_matches_ok(self):
        with tempfile.TemporaryDirectory() as td:
            sub_dir = Path(td) / 'example'
            self._write_submission(sub_dir)
            self.assertEqual(sc.main([str(sub_dir)]), 0)
            self._write_submission(Path(td) / 'bad', include_disclosure=False)
            self.assertEqual(sc.main([str(Path(td) / 'bad')]), 1)


if __name__ == '__main__':
    unittest.main()
