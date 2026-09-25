"""Shared-runner tier planning from retained historical Tier-Bench excerpts.

The native importer receives no synthetic router receipts. Its 52 retained Call
rows and nine diagnostic aggregates remain historical evidence. The supplied
Run 3 Knot is a planning example with an explicit task-class analogy, not a new
model qualification or authorization to execute its chosen route.
"""
from __future__ import annotations

import collections
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
OWNER = ROOT / "hot-aisle/campaign/tierbench-bridge"
sys.path.insert(0, str(HERE))
import work

spec = importlib.util.spec_from_file_location("tier_import_for_runner_tests", OWNER / "import_tierbench.py")
IMPORTER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(IMPORTER)


class TierPlanTasks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = Path("S:/Scratch/Temp") if os.name == "nt" else Path(tempfile.gettempdir())
        scratch.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix="tier-plan-tasks-", dir=scratch)
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.base = Path(cls.temporary.name)
        cls.store = cls.base / "shared"
        cls.evidence = cls.base / "evidence"
        cls.records, cls.summary, cls.ladder = IMPORTER.run(
            None, None, [], str(cls.evidence), fixtures=True)
        copies = {
            "knot.json": OWNER / "fixtures/knots/knot-run3-evalplus-tierbench.json",
            "seats.json": ROOT / "hot-aisle/campaign/ledger/seats.json",
            "availability.jsonl": ROOT / "hot-aisle/campaign/availability/observations.jsonl",
            "local-models.json": OWNER / "local_models.json",
        }
        for name, source in copies.items():
            shutil.copy2(source, cls.base / name)
        cls.source_bytes = (cls.base / "knot.json").read_bytes()
        cls.knot = json.loads(cls.source_bytes)
        cls.task = {
            "id": "tier-plan-first", "task_class": "tier-plan", "actor": "operator-one",
            "source": "knot.json", "evidence": "evidence", "seats": "seats.json",
            "availability": "availability.jsonl", "local_models": "local-models.json",
        }
        cls.recompute = {
            "id": "run3-actual-counts", "task_class": "run-recompute",
            "source": str(ROOT / "hot-aisle/campaign/results/run3-scored-a-t0"),
        }
        cls.cold = work.run({"tasks": [cls.task, cls.recompute]}, cls.base, cls.store)
        if cls.cold["summary"] != {"executed": 2, "reused": 0, "held": 0}:
            raise AssertionError(cls.cold)
        cls.plan_result, cls.recompute_result = cls.cold["tasks"]

    @staticmethod
    def value(result):
        return json.loads(Path(result["result"]).read_bytes())["value"]

    def execute(self, *tasks, store=None):
        result = work.run({"tasks": list(tasks)}, self.base, store or self.store)
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["gpu_runs"], 0)
        return result

    def test_historical_native_plan_keeps_analogy_deadline_and_authority_limits(self):
        self.assertEqual(collections.Counter(row["kind"] for row in self.records),
                         {"tierbench-ledger-call": 52, "race6-aggregate": 9})
        self.assertEqual(self.summary["receipts"], [])
        self.assertFalse(any(row.get("synthetic") for row in self.records))
        self.assertTrue(all(row["ts"].startswith("2026-07-") for row in self.records
                            if row["kind"] == "tierbench-ledger-call"))
        value = self.value(self.plan_result)
        self.assertEqual(value["basis"], "supplied-tierbench-plan")
        self.assertIs(value["execution_authorized"], False)
        self.assertIs(value["new_model_measurement"], False)
        plan = value["plan"]
        self.assertIn("ANALOGY", plan["class_basis"])
        self.assertEqual(plan["evidence_inputs"], self.summary["inputs"])
        self.assertEqual(plan["chosen_mode"], "full")
        chosen = plan["plans"]["chosen"]["plan"]
        self.assertIn("shadow-estimated", chosen["cost_basis"])
        self.assertLess(chosen["deadline_margin_s"], 0)
        self.assertIn("exceeds the deadline", chosen["deadline_note"])
        self.assertIn("not a provider SLA", " ".join(chosen["assumptions"]))
        open_weight = plan["plans"]["open_weight"]
        self.assertEqual(open_weight["tier_status"], "unmeasured")
        self.assertIn("sufficiency is UNMEASURED", open_weight["tier_reason"])
        self.assertEqual(open_weight["plan"]["start_at"].replace("+00:00", "Z"), self.knot["start_at"])
        self.assertEqual((self.base / "knot.json").read_bytes(), self.source_bytes)

    def test_cli_catalog_drives_another_actor_reuse_without_catalog_side_effects(self):
        before = {p.relative_to(self.base) for p in self.base.rglob("*")}
        listing = subprocess.run([sys.executable, "-B", str(HERE / "work.py"), "--catalog"],
                                 cwd=self.base, capture_output=True, text=True,
                                 encoding="utf-8", check=True)
        catalog = json.loads(listing.stdout)
        operation = next(item for item in catalog["operations"] if item["task_class"] == "tier-plan")
        self.assertEqual(before, {p.relative_to(self.base) for p in self.base.rglob("*")})
        self.assertEqual(catalog["effects"], {"model_calls": 0, "gpu_runs": 0,
                                             "resource_acquisition": False})
        task = dict(self.task, id="tier-plan-second", actor="operator-two",
                    task_class=operation["task_class"])
        request = self.base / "catalog-selected-request.json"
        request.write_bytes(work.encoded({"tasks": [task]}))
        execution = subprocess.run([sys.executable, "-B", str(HERE / "work.py"),
                                    "--request", str(request), "--store", str(self.store)],
                                   cwd=self.base, capture_output=True, text=True,
                                   encoding="utf-8", check=True)
        receipt = json.loads(execution.stdout)
        self.assertEqual(receipt["model_calls"], 0)
        self.assertEqual(receipt["gpu_runs"], 0)
        result = receipt["tasks"][0]
        self.assertEqual(result["status"], "reused")
        self.assertEqual(result["key"], self.plan_result["key"])
        self.assertEqual(result["actor"], "operator-two")
        self.assertIs(self.value(result)["execution_authorized"], False)

    def test_identical_evidence_at_a_different_location_reuses(self):
        relocated = self.base / "relocated-evidence-\u00e9"
        relocated.mkdir()
        for name in ("tierbench-summary.json", "tier-ladder.json"):
            shutil.copy2(self.evidence / name, relocated / name)
        task = dict(self.task, id="relocated", actor="another-seat", evidence=relocated.name)
        result = self.execute(task)["tasks"][0]
        self.assertEqual(result["status"], "reused")
        self.assertEqual(result["key"], self.plan_result["key"])
        plan = self.value(result)["plan"]
        self.assertNotIn(str(self.base).replace("\\", "/"), plan["evidence_dir"])

    def test_seat_price_replans_without_invalidating_real_accepted_counts(self):
        changed_path = self.base / "seats-price-scenario.json"
        seats = json.loads((self.base / "seats.json").read_bytes())
        seats["seats"]["hotaisle-mi300x-1x-enc1"]["price"]["list_rate_per_gpu_hr"] = 10.0
        # Keep registry insertion order so only the declared price changes;
        # the native owner intentionally preserves grader-seat ordering.
        changed_path.write_text(json.dumps(seats), encoding="utf-8")
        task = dict(self.task, id="seat-price-change", seats=changed_path.name)
        retained = Path(self.plan_result["result"]).read_bytes()
        result = self.execute(task, self.recompute)
        self.assertEqual(result["summary"], {"executed": 1, "reused": 1, "held": 0})
        new_plan, same_counts = result["tasks"]
        self.assertNotEqual(new_plan["key"], self.plan_result["key"])
        self.assertEqual(same_counts["key"], self.recompute_result["key"])
        self.assertEqual(self.value(same_counts)["accepted"], 4336)
        before, after = self.value(self.plan_result)["plan"], self.value(new_plan)["plan"]
        self.assertEqual(before["verdicts"], after["verdicts"])
        self.assertEqual(before["plans"]["chosen"], after["plans"]["chosen"])
        self.assertNotEqual(before["plans"]["open_weight"]["plan"]["plans"]["cheapest"],
                            after["plans"]["open_weight"]["plan"]["plans"]["cheapest"])
        self.assertIs(self.value(new_plan)["execution_authorized"], False)
        self.assertEqual(Path(self.plan_result["result"]).read_bytes(), retained)

    def test_missing_evidence_and_unknown_argument_are_held_independently(self):
        incomplete = self.base / "missing-summary"
        incomplete.mkdir()
        shutil.copy2(self.evidence / "tier-ladder.json", incomplete / "tier-ladder.json")
        missing = dict(self.task, id="missing-summary", evidence=incomplete.name)
        unknown = dict(self.task, id="unknown-argument", execution_authorized=True)
        result = self.execute(missing, unknown, self.task)
        self.assertEqual(result["summary"], {"executed": 0, "reused": 1, "held": 2})
        self.assertIn("tierbench-summary.json", result["tasks"][0]["reason"])
        self.assertIn("execution_authorized", result["tasks"][1]["reason"])

    def test_corrupt_cached_plan_is_held_without_overwriting_either_copy(self):
        store = self.base / "corrupt-cache"
        destination = store / "results" / Path(self.plan_result["result"]).name
        destination.parent.mkdir(parents=True)
        original = Path(self.plan_result["result"]).read_bytes()
        entry = json.loads(original)
        entry["value"]["execution_authorized"] = True
        damaged = work.encoded(entry)
        destination.write_bytes(damaged)
        result = self.execute(self.task, store=store)["tasks"][0]
        self.assertEqual(result["status"], "held")
        self.assertIn("checksum failed", result["reason"])
        self.assertEqual(destination.read_bytes(), damaged)
        self.assertEqual(Path(self.plan_result["result"]).read_bytes(), original)

    def test_source_byte_change_invalidates_reuse_without_rewriting_dates(self):
        changed = self.base / "knot-new-bytes.json"
        changed.write_bytes(self.source_bytes + b"\n")
        task = dict(self.task, id="changed-knot-bytes", source=changed.name)
        result = self.execute(task)["tasks"][0]
        self.assertEqual(result["status"], "executed")
        self.assertNotEqual(result["key"], self.plan_result["key"])
        self.assertEqual(self.value(result), self.value(self.plan_result))
        self.assertEqual(json.loads(changed.read_bytes())["start_at"], self.knot["start_at"])


if __name__ == "__main__":
    unittest.main()
