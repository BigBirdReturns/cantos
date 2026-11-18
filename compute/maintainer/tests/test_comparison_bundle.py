"""Data-only comparison export contracts using the authored local SSE fixture."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
from comparison_bundle import export_comparison
import test_instrument as fixture


class ComparisonBundle(unittest.TestCase):
    # Reuse fixture lifecycle without inheriting its unrelated instrument tests.
    setUp = fixture.Instrument.setUp
    tearDown = fixture.Instrument.tearDown
    save = fixture.Instrument.save
    run_pair = fixture.Instrument.run_pair

    def test_exact_workloads_export_complete_bound_raw_and_deterministic_zip(self):
        self.work['cases'].append({
            'id': 'text-case', 'messages': [{'role': 'user', 'content': 'Return value 2 as JSON'}],
            'expect': {'kind': 'text_exact', 'value': '{"value": 2}'}})
        result = self.run_pair()
        self.assertEqual(result['verdict'], 'pass', result)
        requests = (self.a.requests, self.b.requests)
        self.assertEqual(requests, (4, 4))
        first, second = self.root / 'first.zip', self.root / 'second.zip'
        exported = export_comparison(self.root / 'pair/analysis', first)
        cli = subprocess.run([
            sys.executable, '-B', str(Path(fixture.m.__file__)), 'export-comparison',
            '--analysis', str(self.root / 'pair/analysis/verdict.json'), '--out', str(second)],
            capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        cli_receipt = json.loads(cli.stdout)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(exported['sha256'], hashlib.sha256(first.read_bytes()).hexdigest())
        self.assertEqual(cli_receipt['sha256'], exported['sha256'])
        self.assertEqual(exported['new_inference_requests'], 0)
        self.assertEqual((self.a.requests, self.b.requests), requests)
        with zipfile.ZipFile(first) as archive:
            manifest = json.loads(archive.read('comparison.json'))
            self.assertEqual(manifest['schema'], 'cantos.comparison-bundle/1')
            self.assertEqual(set(manifest['inputs']), {'baseline', 'candidate', 'policy'})
            declared = {entry['path']: entry for entry in manifest['files']}
            self.assertEqual(set(declared), set(archive.namelist()) - {'comparison.json'})
            for name, entry in declared.items():
                raw = archive.read(name)
                self.assertEqual(entry['bytes'], len(raw), name)
                self.assertEqual(entry['sha256'], hashlib.sha256(raw).hexdigest(), name)
            self.assertEqual(archive.read(manifest['original_analysis']),
                             (self.root / 'pair/analysis/verdict.json').read_bytes())
            for arm in ('baseline', 'candidate'):
                source = self.root / 'pair' / arm / 'run.json'
                run = common.load(source)
                self.assertEqual(archive.read(manifest['inputs'][arm]), source.read_bytes())
                # The complete source closure is retained, including every raw SSE
                # capture, not merely a display summary or selected successful task.
                for entry in run['artifacts']:
                    name = arm + '/' + entry['path']
                    raw = archive.read(name)
                    self.assertEqual(raw, (source.parent / entry['path']).read_bytes())
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), entry['sha256'])
                for obs in run['observations']:
                    for attempt in obs['attempts']:
                        self.assertIn(arm + '/' + attempt['raw_path'], declared)

    def test_changed_native_verdict_is_rejected_before_archive_creation(self):
        self.run_pair()
        path = self.root / 'pair/analysis/verdict.json'
        verdict = common.load(path)
        verdict['verdict'] = 'regression'
        path.write_text(json.dumps(verdict), encoding='utf-8')
        destination = self.root / 'invalid-verdict.zip'
        with self.assertRaisesRegex(ValueError, 'analysis changed.*verdict'):
            export_comparison(path, destination)
        self.assertFalse(destination.exists())

    def test_changed_source_receipt_is_rejected_before_archive_creation(self):
        self.run_pair()
        path = self.root / 'pair/candidate/run.json'
        receipt = common.load(path)
        receipt['observation_id'] = 'changed-after-analysis'
        path.write_text(json.dumps(receipt), encoding='utf-8')
        destination = self.root / 'invalid-receipt.zip'
        with self.assertRaisesRegex(ValueError, 'retained analysis input changed: candidate'):
            export_comparison(self.root / 'pair/analysis', destination)
        self.assertFalse(destination.exists())

    def test_changed_raw_stream_is_rejected_before_archive_creation(self):
        self.run_pair()
        receipt = common.load(self.root / 'pair/baseline/run.json')
        raw_path = self.root / 'pair/baseline' / receipt['observations'][0]['attempts'][0]['raw_path']
        raw_path.write_bytes(raw_path.read_bytes() + b'\n ')
        destination = self.root / 'invalid-raw.zip'
        with self.assertRaisesRegex(ValueError, 'missing or changed evidence'):
            export_comparison(self.root / 'pair/analysis', destination)
        self.assertFalse(destination.exists())

    def test_exporter_only_source_change_does_not_change_observation_key(self):
        producers = self.root / 'isolated-producer-sources'
        producers.mkdir()
        exporter = producers / 'comparison_bundle.py'
        exporter.write_text('# exporter edition one\n', encoding='utf-8')
        (producers / 'maintainer.py').write_text('# unchanged capture source\n', encoding='utf-8')
        with mock.patch.object(common, 'ROOT', producers):
            before = common.prepare(self.root / 'spec.json', 'baseline')
            analysis_before = common.producer_records()
            exporter.write_text('# exporter edition two has changed bytes\n', encoding='utf-8')
            after = common.prepare(self.root / 'spec.json', 'baseline')
            analysis_after = common.producer_records()
        self.assertEqual(before['observation_key'], after['observation_key'])
        self.assertEqual(before['identity'], after['identity'])
        self.assertNotIn(str(exporter), before['dependencies'])
        self.assertNotEqual(analysis_before, analysis_after)
        self.assertEqual((self.a.requests, self.b.requests), (0, 0))


if __name__ == '__main__':
    unittest.main()
