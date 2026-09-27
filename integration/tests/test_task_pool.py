"""pool-purchase through work.py: execute, reuse, and re-execute on changed offers."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

INTEGRATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INTEGRATION))
import task_pool


class PoolTask(unittest.TestCase):
    def setUp(self):
        scratch = Path("S:/Scratch/Temp") if os.name == "nt" else Path(tempfile.gettempdir())
        self.temporary = tempfile.TemporaryDirectory(prefix="pool-task-", dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        shutil.copy(INTEGRATION / "examples/pool-request.json", self.base / "pool-request.json")
        shutil.copy(task_pool.ROOT / "hot-aisle/campaign/providers/providers.jsonl", self.base / "offers.jsonl")
        self.request = self.base / "work.json"
        self.request.write_text(json.dumps({"tasks": [{"id": "pool", "task_class": "pool-purchase",
                                                        "source": "pool-request.json", "offers": "offers.jsonl"}]}),
                                encoding="utf-8")

    def run_work(self):
        done = subprocess.run([sys.executable, "-B", str(INTEGRATION / "work.py"), "--request", str(self.request),
                               "--store", str(self.base / "store")], capture_output=True, text=True, check=True)
        return json.loads(done.stdout)

    def test_executes_then_reuses_then_reexecutes_on_changed_offer(self):
        self.assertEqual(self.run_work()["summary"]["executed"], 1)
        self.assertEqual(self.run_work()["summary"]["reused"], 1)
        with (self.base / "offers.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("\n")
        self.assertEqual(self.run_work()["summary"]["executed"], 1)

    def test_result_is_native_and_offers_untouched(self):
        before = (self.base / "offers.jsonl").read_bytes()
        prepared = task_pool.prepare({"task_class": "pool-purchase", "source": "pool-request.json",
                                      "offers": "offers.jsonl"}, self.base)
        result = prepared["execute"]()
        self.assertEqual(result["schema"], "capital/pool-result@1")
        self.assertFalse(result["source_rewritten"])
        self.assertEqual((self.base / "offers.jsonl").read_bytes(), before)

    def test_rejects_unknown_keys_and_missing_offers(self):
        with self.assertRaises(ValueError):
            task_pool.prepare({"task_class": "pool-purchase", "source": "pool-request.json",
                               "offers": "offers.jsonl", "purchase": True}, self.base)
        with self.assertRaises(ValueError):
            task_pool.prepare({"task_class": "pool-purchase", "source": "pool-request.json"}, self.base)


if __name__ == "__main__":
    unittest.main()
