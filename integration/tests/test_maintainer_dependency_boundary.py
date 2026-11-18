"""Post-hoc grading edits reuse streamed observations; collection edits invalidate."""
import json
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
    def test_grading_edits_preserve_actual_observation_key(self):
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
                producer = {r["path"] for r in common.producer_records()}
                procedures = {p.name for p in task_maintainer._procedures()}
                for name in ("normalize.py", "evalplus_bridge.py"):
                    self.assertNotIn(name, producer)
                    self.assertNotIn(name, procedures)
                for name in ("common.py", "maintainer.py", "streaming.py"):
                    self.assertIn(name, producer)
                    self.assertIn(name, procedures)

                before = common.prepare(spec_path, "baseline")
                original = common.producer_records()
                (frozen / "normalize.py").write_text("def normalize(x): return x + '\\n'\n")
                (frozen / "evalplus_bridge.py").write_text("def bridge(x): return x\n")
                after_grading_change = common.prepare(spec_path, "baseline")
                self.assertEqual(before["observation_key"], after_grading_change["observation_key"])
                self.assertEqual(original, common.producer_records())

                streaming = frozen / "streaming.py"
                streaming.write_text(streaming.read_text() + "\n# revised stream parser\n")
                after_collector_change = common.prepare(spec_path, "baseline")
                self.assertNotEqual(before["observation_key"], after_collector_change["observation_key"])
                self.assertNotEqual(original, common.producer_records())
            finally:
                common.ROOT, task_maintainer.OWNER = old_root, old_owner


if __name__ == "__main__":
    unittest.main()
