"""circulate --offline, end to end, on the fixtures in circulate/fixtures/ with no network.

Asserts: overall OK; every stage OK or SKIP; the receipt validates against circulate/receipt@1; per-stage result
files exist under receipts/<date>/; the frozen files are unchanged; nothing outside circulate/ moved (git status and
file hashes before and after); and network use is impossible (the run is started with the proxy variables pointing at
a closed port and the stages refuse network in offline mode).

    python -m unittest circulate.tests.test_offline        (from the repo root)
    python circulate/tests/test_offline.py

Concurrent edits by other people to files outside circulate/ while this runs would look like a violation; run it on a
quiet tree. The run uses --date 2000-01-01 and --retained <tmp> so it never touches a real receipt, and removes the
receipt directory it created.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CIRC = Path(__file__).resolve().parents[1]
REPO = CIRC.parent
sys.path.insert(0, str(CIRC))
sys.dont_write_bytecode = True
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location('circulate_driver', CIRC / 'circulate.py')   # not `import circulate`: from the repo root that names the folder
driver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(driver)

TEST_DATE = '2000-01-01'


def porcelain() -> dict:
    """{path: sha256 or None} for every dirty/untracked file outside circulate/."""
    out = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=REPO, capture_output=True, timeout=120).stdout.decode('utf-8', 'replace')
    files = {}
    for line in out.splitlines():
        path = line[3:].strip().strip('"')
        if ' -> ' in path:
            path = path.split(' -> ')[-1]
        if path.startswith('circulate/'):
            continue
        p = REPO / path
        files[path] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    return files


class OfflineRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='circulate-offline-'))
        cls.rdir = CIRC / 'receipts' / TEST_DATE
        shutil.rmtree(cls.rdir, ignore_errors=True)
        cls.frozen_before = driver.frozen_hashes()
        cls.before = porcelain()
        env = dict(os.environ)
        for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY'):
            env[k] = 'http://127.0.0.1:9'      # closed port: any stray network call fails loudly
        env['GH_TOKEN'] = 'offline-test-invalid'
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        env['PYTHONUTF8'] = '1'
        cls.proc = subprocess.run([sys.executable, str(CIRC / 'circulate.py'), '--offline', '--retained', str(cls.tmp), '--date', TEST_DATE],
                                  cwd=str(CIRC), capture_output=True, env=env, timeout=1200)
        cls.after = porcelain()
        cls.frozen_after = driver.frozen_hashes()
        cls.out = cls.proc.stdout.decode('utf-8', 'replace') + cls.proc.stderr.decode('utf-8', 'replace')
        try:
            cls.receipt = json.loads((cls.rdir / 'RECEIPT.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            cls.receipt = None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.rdir, ignore_errors=True)
        shutil.rmtree(cls.tmp, ignore_errors=True)
        idx = CIRC / 'receipts' / 'index.json'
        if idx.exists():                       # offline runs never touch it; guard against a test leaving a fixture row
            rows = json.loads(idx.read_text(encoding='utf-8'))
            if any(r.get('date') == TEST_DATE for r in rows):
                idx.write_text(json.dumps([r for r in rows if r.get('date') != TEST_DATE], indent=1) + '\n', encoding='utf-8')

    def test_driver_exit_zero_and_overall_ok(self):
        self.assertEqual(self.proc.returncode, 0, self.out[-3000:])
        self.assertIsNotNone(self.receipt, 'no RECEIPT.json written')
        self.assertEqual(self.receipt['overall'], 'OK')
        self.assertTrue(self.receipt['complete'])
        self.assertEqual(self.receipt['mode'], 'offline')

    def test_every_stage_ran_and_is_ok_or_skip(self):
        names = [s['name'] for s in self.receipt['stages']]
        self.assertEqual(names, driver.STAGES)
        for s in self.receipt['stages']:
            self.assertIn(s['status'], ('OK', 'SKIP'), f'{s["name"]}: {s["status"]} {s.get("notes")} {s.get("error")}')
        # at least the data stages did real work on fixtures rather than skipping
        ok = {s['name'] for s in self.receipt['stages'] if s['status'] == 'OK'}
        self.assertTrue({'inferencex', 'prices', 'status', 'economics', 'delta', 'r2-standing', 'newsletter', 'packet', 'tests'} <= ok, ok)

    def test_receipt_schema_valid(self):
        self.assertEqual(driver.validate_receipt(self.receipt), [])
        md = (self.rdir / 'RECEIPT.md').read_text(encoding='utf-8')
        for word in ('Circulation receipt', 'Stages', 'Frozen files', 'Disclosure'):
            self.assertIn(word, md)
        for s in self.receipt['stages']:
            f = self.rdir / 'stages' / f'{s["name"]}.json'
            self.assertTrue(f.is_file(), f)
            one = json.loads(f.read_text(encoding='utf-8'))
            self.assertEqual({k: one[k] for k in ('name', 'status', 'finished_utc')}, {k: s[k] for k in ('name', 'status', 'finished_utc')})
            self.assertTrue((self.rdir / 'logs' / f'{s["name"]}.log').is_file())

    def test_schema_validator_rejects_a_broken_receipt(self):
        bad = json.loads(json.dumps(self.receipt))
        bad['stages'][0]['status'] = 'MAYBE'
        del bad['stages'][1]['counts']
        bad['overall'] = 'OK'
        bad['stages'][2]['status'] = 'FAIL'
        problems = driver.validate_receipt(bad)
        self.assertTrue(any('bad status' in p for p in problems))
        self.assertTrue(any('missing counts' in p for p in problems))
        self.assertTrue(any('overall OK with a FAIL' in p for p in problems))

    def test_frozen_files_unchanged(self):
        self.assertEqual(self.frozen_before, self.frozen_after)
        self.assertEqual(self.receipt['frozen']['moved'], [])
        self.assertGreaterEqual(self.receipt['frozen']['checked'], 8)

    def test_nothing_outside_circulate_was_modified(self):
        changed = {p: h for p, h in self.after.items() if self.before.get(p, 'absent') != h}
        gone = [p for p in self.before if p not in self.after]
        self.assertEqual(changed, {}, f'files outside circulate/ changed by an offline run: {sorted(changed)}')
        self.assertEqual(gone, [])
        # the committed-path outputs were written into the sandbox, not the repo
        self.assertTrue((self.tmp / 'sandbox' / 'hot-aisle/campaign/backfill/imported/history-index.json').is_file())
        self.assertEqual(self.receipt['committed_paths'], [])
        for s in self.receipt['stages']:
            for o in s['outputs']:
                self.assertFalse(o['committed'], o)

    def test_outputs_carry_hashes_that_match_the_files(self):
        for s in self.receipt['stages']:
            for o in s['outputs']:
                p = None
                for base in (self.tmp / 'sandbox', self.tmp, REPO):
                    if (base / o['path']).exists():
                        p = base / o['path']
                        break
                self.assertIsNotNone(p, f'{s["name"]}: {o["path"]} not found')
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), o['sha256'], o['path'])

    def test_offline_outputs_are_labelled_and_no_fabricated_holds(self):
        by = {s['name']: s for s in self.receipt['stages']}
        self.assertIn('OFFLINE SMOKE', by['r2-standing']['notes'])
        self.assertEqual(by['inferencex']['counts']['refused'], 0)
        self.assertEqual(by['status']['counts']['failed'], 0)
        self.assertEqual(by['packet']['counts']['validate_exit'], 0)
        self.assertGreaterEqual(by['newsletter']['counts']['appended'], 3)
        self.assertEqual(by['newsletter']['counts']['no_body'], 0)


if __name__ == '__main__':
    unittest.main()
