"""Recipient transport must retain large evidence and reject altered inputs."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from compute.maintainer.deployment_bundle import export_bundle, import_bundle, validate_manifest


class DeploymentBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job = self.root / 'job'
        self.job.mkdir()
        (self.job / 'decision.json').write_text('{"state":"UNDETERMINED"}', encoding='utf-8')

    def test_large_roundtrip_and_independent_restart(self):
        # Incompressible data exceeds the old 8 MiB ZIP path.
        raw = os.urandom(9 * 1024 * 1024)
        (self.job / 'raw-stream.bin').write_bytes(raw)
        manifest = export_bundle(self.job, self.root / 'bundle')
        self.assertGreater(manifest['archive_bytes'], 8 * 1024 * 1024)
        self.assertEqual(len(manifest['parts']), 3)
        result = import_bundle(self.root / 'bundle/bundle.json', self.root / 'imported')
        self.assertEqual(hashlib.sha256((Path(result['root']) / 'raw-stream.bin').read_bytes()).digest(), hashlib.sha256(raw).digest())
        self.assertEqual(json.loads(Path(result['record']).read_text()), {'state': 'UNDETERMINED'})

    def test_missing_or_changed_part_never_creates_import(self):
        manifest = export_bundle(self.job, self.root / 'bundle')
        path = self.root / 'bundle' / manifest['parts'][0]['path']
        path.write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError, 'altered'):
            import_bundle(self.root / 'bundle', self.root / 'imported')
        self.assertFalse((self.root / 'imported').exists())

    def test_expanded_hash_checked_even_with_valid_part_hash(self):
        manifest = export_bundle(self.job, self.root / 'bundle')
        manifest['files'][0]['sha256'] = '0' * 64
        (self.root / 'bundle/bundle.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'member hash'):
            import_bundle(self.root / 'bundle', self.root / 'imported')
        self.assertFalse((self.root / 'imported').exists())

    def test_hash_valid_non_archive_is_a_data_error(self):
        manifest = export_bundle(self.job, self.root / 'bundle')
        raw = b'this is not an archive'
        path = self.root / 'bundle' / manifest['parts'][0]['path']
        path.write_bytes(raw)
        manifest['parts'][0].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        manifest.update(archive_bytes=len(raw), archive_sha256=hashlib.sha256(raw).hexdigest())
        (self.root / 'bundle/bundle.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'Invalid or unsupported deployment archive'):
            import_bundle(self.root / 'bundle', self.root / 'imported')
        self.assertFalse((self.root / 'imported').exists())

    def test_traversal_case_collision_and_unbounded_values_rejected(self):
        manifest = export_bundle(self.job, self.root / 'bundle')
        for unsafe in ('../outside', '/absolute', 'C:drive', 'CON', 'sub\\bad', 'file.', 'sub/../bad'):
            changed = json.loads(json.dumps(manifest))
            changed['files'][0]['path'] = unsafe
            with self.assertRaises(ValueError):
                validate_manifest(changed)
        changed = json.loads(json.dumps(manifest))
        changed['files'].append({**changed['files'][0], 'path': 'DECISION.JSON'})
        with self.assertRaisesRegex(ValueError, 'colliding'):
            validate_manifest(changed)
        changed = json.loads(json.dumps(manifest))
        changed['parts'][0]['bytes'] = 2 ** 40
        with self.assertRaises(ValueError):
            validate_manifest(changed)

    def test_export_and_import_preserve_existing_destinations(self):
        export_bundle(self.job, self.root / 'bundle')
        with self.assertRaises(FileExistsError):
            export_bundle(self.job, self.root / 'bundle')
        with self.assertRaises(FileExistsError):
            import_bundle(self.root / 'bundle', self.job)
        self.assertEqual((self.job / 'decision.json').read_text(), '{"state":"UNDETERMINED"}')


if __name__ == '__main__':
    unittest.main()
