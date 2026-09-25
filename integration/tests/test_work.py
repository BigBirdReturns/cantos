"""Handoffs through the actual owners, with all mutations confined to scratch."""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import task_results
import work


class WorkHandoff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = Path("S:/Scratch/Temp") if os.name == "nt" else Path(tempfile.gettempdir())
        cls.temporary = tempfile.TemporaryDirectory(prefix="work-handoff-", dir=scratch)
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        cls.store = cls.directory / "shared"
        cls.base = HERE / "examples"
        cls.request = json.loads((cls.base / "work.json").read_bytes())
        cls.cold = work.run(cls.request, cls.base, cls.store)
        if cls.cold["summary"] != {"executed": 6, "reused": 0, "held": 0}:
            raise AssertionError(cls.cold)

    def value(self, task_result):
        return json.loads(Path(task_result["result"]).read_bytes())["value"]

    def test_real_material_and_explicit_synthetic_examples(self):
        values = [self.value(t) for t in self.cold["tasks"]]
        self.assertEqual(1, values[0]["offer_count"])
        self.assertEqual("latitude-h100-1", values[0]["offers"][0]["native_row"]["offer_id"])
        self.assertEqual(5, values[2]["source_file_count"])
        self.assertEqual(6, values[2]["source_row_count"])
        self.assertEqual(80, values[2]["observation_count"])
        self.assertTrue(all(row["fixture"] for row in values[2]["observations"]))
        self.assertGreater(values[2]["observation_count"], 0)
        self.assertEqual((8622, 8622, 4336), tuple(values[3][k] for k in ("scheduled", "completed", "accepted")))
        self.assertFalse(values[3]["synthetic"])
        self.assertTrue(values[4]["historical_reports_preserved"])
        self.assertTrue(values[5]["synthetic"])

    def test_another_operator_reuses_all_six_operations(self):
        request = copy.deepcopy(self.request)
        for i, task in enumerate(request["tasks"]):
            task.update(id="next-request-" + str(i), actor="operator-two")
        result = work.run(request, self.base, self.store)
        self.assertEqual({"executed": 0, "reused": 6, "held": 0}, result["summary"])
        self.assertEqual([t["key"] for t in self.cold["tasks"]], [t["key"] for t in result["tasks"]])
        self.assertEqual(0, result["model_calls"])
        self.assertEqual(0, result["gpu_runs"])

    def test_price_scenario_changes_only_its_task(self):
        request = copy.deepcopy(self.request)
        retained = {t["result"]: Path(t["result"]).read_bytes() for t in self.cold["tasks"]}
        request["tasks"][0]["price_scenario"] = {"rate_usd_per_gpu_hour": 2.0}
        result = work.run(request, self.base, self.store)
        self.assertEqual({"executed": 1, "reused": 5, "held": 0}, result["summary"])
        old_offer = self.value(self.cold["tasks"][0])["offers"][0]
        new_offer = self.value(result["tasks"][0])["offers"][0]
        self.assertEqual(old_offer["native_row"], new_offer["native_row"])
        self.assertNotEqual(old_offer["modeled_targets"], new_offer["modeled_targets"])
        self.assertEqual(4336, self.value(result["tasks"][3])["accepted"])
        for path, original in retained.items():
            self.assertEqual(original, Path(path).read_bytes())

    def test_same_source_bytes_at_another_location_reuse(self):
        task = copy.deepcopy(self.request["tasks"][0])
        source = (self.base / task["source"]).resolve()
        relocated = self.directory / "same-offers-\u00e9.jsonl"
        shutil.copy2(source, relocated)
        task.update(source=str(relocated), actor="operator-\u00e9-with-another-checkout", id="relocated")
        result = work.run({"tasks": [task]}, self.base, self.store)
        self.assertEqual("reused", result["tasks"][0]["status"])
        self.assertEqual(self.cold["tasks"][0]["key"], result["tasks"][0]["key"])

    def test_corrupt_cache_is_held_and_other_tasks_continue(self):
        for label, corruption in (("array", []), ("null", None), ("value", {"changed": True})):
            with self.subTest(label=label):
                store = self.directory / ("corrupt-" + label)
                good = self.cold["tasks"][0]
                destination = store / "results" / Path(good["result"]).name
                destination.parent.mkdir(parents=True)
                if label == "value":
                    entry = json.loads(Path(good["result"]).read_bytes())
                    entry["value"] = corruption
                    corruption = entry
                damaged = work.encoded(corruption)
                destination.write_bytes(damaged)
                second = self.cold["tasks"][1]
                shutil.copy2(second["result"], destination.parent / Path(second["result"]).name)
                result = work.run({"tasks": self.request["tasks"][:2]}, self.base, store)
                self.assertEqual({"executed": 0, "reused": 1, "held": 1}, result["summary"])
                self.assertEqual("held", result["tasks"][0]["status"])
                self.assertTrue(Path(result["receipt"]).is_file())
                self.assertEqual(damaged, destination.read_bytes())

    def test_inconsistent_grading_and_missing_evidence_cannot_reuse(self):
        task = copy.deepcopy(self.request["tasks"][3])
        original = (self.base / task["source"]).resolve()
        copied = self.directory / "retained-arm"
        prepared = task_results.prepare(task, self.base)
        for path in prepared["inputs"].values():
            if path.is_relative_to(original):
                destination = copied / path.relative_to(original)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        task["source"] = str(copied)
        prior = self.cold["tasks"][3]
        prior_bytes = Path(prior["result"]).read_bytes()
        equivalent = work.run({"tasks": [task]}, self.base, self.store)
        self.assertEqual("reused", equivalent["tasks"][0]["status"])
        evaluation_path = copied / "grade/evaluation.json"
        evaluation_bytes = evaluation_path.read_bytes()
        evaluation = json.loads(evaluation_bytes)
        evaluation["passed"][0] = not evaluation["passed"][0]
        evaluation_path.write_bytes(work.encoded(evaluation))
        changed = work.run({"tasks": [task]}, self.base, self.store)
        self.assertEqual("held", changed["tasks"][0]["status"])
        self.assertIn("differs from rejoined EvalPlus results", changed["tasks"][0]["reason"])
        evaluation_path.write_bytes(evaluation_bytes)
        # This is a test-owned scratch copy, never the retained campaign file.
        (copied / "tasks.json").unlink()
        missing = work.run({"tasks": [task]}, self.base, self.store)
        self.assertEqual("held", missing["tasks"][0]["status"])
        self.assertEqual(prior_bytes, Path(prior["result"]).read_bytes())

    def test_unknown_operation_and_change_are_held_independently(self):
        typo = copy.deepcopy(self.request["tasks"][-1])
        typo["change"] = {"prices": {"rate": 1.68}}
        request = {"tasks": [
            {"id": "unknown", "task_class": "publish-everything", "source": "unused"},
            typo, self.request["tasks"][0],
        ]}
        result = work.run(request, self.base, self.store)
        self.assertEqual({"executed": 0, "reused": 1, "held": 2}, result["summary"])
        self.assertIn("Unsupported task class", result["tasks"][0]["reason"])
        self.assertIn("unsupported fields", result["tasks"][1]["reason"])

    def test_new_retrieval_receipt_invalidates_only_import_identity(self):
        source = ROOT / "hot-aisle/campaign/backfill/fixtures/manifest.json"
        manifest = json.loads(source.read_bytes())
        entry = copy.deepcopy(manifest["files"][0])
        directory = self.directory / "retrieval-change"
        directory.mkdir()
        raw = directory / "raw.json"
        shutil.copy2(source.parent / entry["path"], raw)
        entry["path"] = raw.name
        manifest["files"] = [entry]
        local_manifest = directory / "manifest.json"
        local_manifest.write_bytes(work.encoded(manifest))
        task = {"id": "retrieval-test", "task_class": "benchmark-import", "source": str(local_manifest)}
        first = work.run({"tasks": [task]}, directory, self.store)
        self.assertEqual("executed", first["tasks"][0]["status"])
        retained = Path(first["tasks"][0]["result"]).read_bytes()
        receipt = {k: entry[k] for k in ("url", "revision", "sha256", "retrieved_at")}
        raw.with_name(raw.name + ".retrieval.json").write_bytes(work.encoded(receipt))
        second = work.run({"tasks": [task]}, directory, self.store)
        self.assertEqual("executed", second["tasks"][0]["status"])
        self.assertNotEqual(first["tasks"][0]["key"], second["tasks"][0]["key"])
        self.assertEqual(retained, Path(first["tasks"][0]["result"]).read_bytes())
        self.assertEqual(self.value(first["tasks"][0])["observations"], self.value(second["tasks"][0])["observations"])


if __name__ == "__main__":
    unittest.main()
