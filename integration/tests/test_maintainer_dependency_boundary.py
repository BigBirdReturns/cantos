"""Offline grading and export preserve observation keys; collection edits invalidate."""
import json
import re
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "compute/maintainer"))
sys.path.insert(0, str(ROOT / "integration"))
import common
import task_maintainer


def configured(value):
    if isinstance(value, dict):
        return {k: configured(v) for k, v in value.items()}
    if isinstance(value, list):
        return [configured(v) for v in value]
    if isinstance(value, str):
        if value == "your-served-model-id":
            return "explicitly-declared-local-model"
        if "REPLACE_WITH" in value:
            return "explicitly-declared-identity"
    return value


class DependencyBoundary(unittest.TestCase):
    def test_offline_edits_preserve_native_and_second_run_observation_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            frozen = root / "instrument"
            shutil.copytree(ROOT / "compute/maintainer", frozen,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            spec_dir = root / "declared"
            spec_dir.mkdir()
            examples = ROOT / "compute/maintainer/examples"
            shutil.copyfile(examples / "workload.json", spec_dir / "workload.json")
            spec_path = spec_dir / "spec.json"
            spec_path.write_text(json.dumps(configured(
                json.loads((examples / "spec.json").read_text()))))
            old_root, old_owner = common.ROOT, task_maintainer.OWNER
            try:
                common.ROOT = frozen
                task_maintainer.OWNER = frozen / "maintainer.py"
                observe = {"id": "observe-baseline", "task_class": "maintainer-observe",
                           "source": spec_path.name, "arm": "baseline", "observation_id": "bound-epoch"}

                def second_run_identity():
                    task = task_maintainer.prepare(observe, spec_dir)
                    inputs = {role: task_maintainer._sha(path) for role, path in task["inputs"].items()}
                    return task["parameters"], inputs

                before = common.prepare(spec_path, "baseline")
                producer = {r["path"] for r in before["identity"]["producer_files"]}
                collector_files = {Path(path).name for path in before["dependencies"]}
                procedures = {p.name for p in task_maintainer._procedures()}
                self.assertNotIn("packets.py", producer)
                self.assertNotIn("packets.py", collector_files)
                self.assertIn("packets.py", procedures)
                for name in ("normalize.py", "evalplus_bridge.py"):
                    self.assertNotIn(name, producer)
                    self.assertNotIn(name, procedures)
                for name in ("common.py", "maintainer.py", "streaming.py"):
                    self.assertIn(name, producer)
                    self.assertIn(name, procedures)

                second_run_before = second_run_identity()
                self.assertEqual(before["identity"], second_run_before[0]["declared_observation"])
                original = common.producer_records()
                original_packet_record = next(record for record in original if record["path"] == "packets.py")
                (frozen / "normalize.py").write_text("def normalize(x): return x + '\\n'\n")
                (frozen / "evalplus_bridge.py").write_text("def bridge(x): return x\n")
                after_grading_change = common.prepare(spec_path, "baseline")
                self.assertEqual(before["observation_key"], after_grading_change["observation_key"])
                self.assertEqual(original, common.producer_records())
                self.assertEqual(second_run_before, second_run_identity())

                packets = frozen / "packets.py"
                revised, count = re.subn(
                    r'(?m)^BUNDLE_SHA256 = "([0-9a-f]{64})"$',
                    lambda match: 'BUNDLE_SHA256 = "' + ("1" if match[1] == "0" * 64 else "0") * 64 + '"',
                    packets.read_text(encoding="utf-8"))
                self.assertEqual(count, 1)
                packets.write_text(revised, encoding="utf-8")
                after_packet_change = common.prepare(spec_path, "baseline")
                self.assertEqual(before["observation_key"], after_packet_change["observation_key"])
                self.assertEqual(second_run_before, second_run_identity())
                new_packet_record = next(record for record in common.producer_records() if record["path"] == "packets.py")
                self.assertNotEqual(original_packet_record["sha256"], new_packet_record["sha256"])

                streaming = frozen / "streaming.py"
                streaming.write_text(streaming.read_text() + "\n# revised stream parser\n")
                after_collector_change = common.prepare(spec_path, "baseline")
                self.assertNotEqual(before["observation_key"], after_collector_change["observation_key"])
                self.assertNotEqual(original, common.producer_records())
                second_run_after = second_run_identity()
                self.assertNotEqual(second_run_before[0], second_run_after[0])
                self.assertNotEqual(second_run_before[1], second_run_after[1])
            finally:
                common.ROOT, task_maintainer.OWNER = old_root, old_owner


if __name__ == "__main__":
    unittest.main()
