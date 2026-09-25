"""Source-operation checks using the existing staged offer and real-byte fixtures."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import task_sources


class SourceTasks(unittest.TestCase):
    def setUp(self):
        scratch = Path("S:/Scratch/Temp") if os.name == "nt" else Path(tempfile.gettempdir())
        self.temporary = tempfile.TemporaryDirectory(prefix="source-tasks-", dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        native = task_sources.CAMPAIGN / "providers/providers.jsonl"
        self.offer = next(json.loads(line) for line in native.read_text(encoding="utf-8-sig").splitlines()
                          if json.loads(line)["offer_id"] == "latitude-h100-1")

    def offer_source(self, row=None):
        source = self.base / "offer.jsonl"
        source.write_text(json.dumps(self.offer if row is None else row) + "\n", encoding="utf-8")
        return {"id": "caller-one", "task_class": "provider-intake", "source": source.name,
                "offer_id": "latitude-h100-1"}

    def benchmark_source(self, empty=False):
        fixtures = task_sources.CAMPAIGN / "backfill/fixtures"
        manifest = json.loads((fixtures / "manifest.json").read_bytes())
        entry = copy.deepcopy(next(e for e in manifest["files"] if e["source"] == "inferencemax"))
        original = fixtures / entry["path"]
        entry["path"] = "raw/agg_bmk.json"
        raw = self.base / entry["path"]
        raw.parent.mkdir()
        if empty:
            raw.write_bytes(b"[]\n")
            entry["sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
        else:
            shutil.copy2(original, raw)
        manifest["files"] = [entry]
        (self.base / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        return {"task_class": "benchmark-import", "source": "manifest.json"}, entry, raw

    def test_price_scenario_preserves_quote_and_native_row(self):
        task = self.offer_source()
        before = (self.base / task["source"]).read_bytes()
        original = task_sources.prepare(task, self.base)["execute"]()["offers"][0]
        task["price_scenario"] = {"rate_usd_per_gpu_hour": 2.0}
        op = task_sources.prepare(task, self.base)
        changed = op["execute"]()["offers"][0]
        self.assertEqual(self.offer, changed["native_row"])
        self.assertEqual(1.68, changed["declared_rate"]["value"])
        self.assertEqual(self.offer["source_quote"], changed["declared_rate"]["source_quote"])
        self.assertIsNone(changed["declared_rate"]["publication_date"])
        self.assertFalse(changed["declared_rate"]["semantic_source_validation"])
        self.assertEqual(0.46, original["modeled_targets"]["values"]["modeled_per_1k_accepted"])
        self.assertEqual(0.54, changed["modeled_targets"]["values"]["modeled_per_1k_accepted"])
        self.assertEqual(before, (self.base / task["source"]).read_bytes())
        self.assertEqual(task_sources.HERE, op["inputs"]["adapter_code"])
        self.assertEqual(task_sources.PROVIDER_OWNER, op["inputs"]["provider_owner_code"])

    def test_caller_identity_is_not_a_parameter_and_extra_keys_fail(self):
        task = self.offer_source()
        first = task_sources.prepare(task, self.base)["parameters"]
        task["id"] = "another-caller"
        task["actor"] = "another-operator"
        self.assertEqual(first, task_sources.prepare(task, self.base)["parameters"])
        task["actor"] = "third-operator"
        self.assertEqual(first, task_sources.prepare(task, self.base)["parameters"])
        task["operator"] = "not-a-source-parameter"
        with self.assertRaisesRegex(ValueError, "unsupported task keys"):
            task_sources.prepare(task, self.base)

    def test_absolute_and_relative_sources_have_same_semantic_parameters(self):
        task = self.offer_source()
        relative = task_sources.prepare(task, self.base)
        task["source"] = str((self.base / task["source"]).resolve())
        absolute = task_sources.prepare(task, self.base)
        self.assertEqual(relative["parameters"], absolute["parameters"])
        self.assertEqual(relative["inputs"], absolute["inputs"])
        self.assertEqual(relative["execute"](), absolute["execute"]())

    def test_boolean_prices_counts_and_scenarios_fail(self):
        for key in ("gpus", "rate_usd_per_gpu_hour"):
            row = copy.deepcopy(self.offer)
            row[key] = True
            task = self.offer_source(row)
            with self.assertRaisesRegex(ValueError, "not a boolean"):
                task_sources.prepare(task, self.base)["execute"]()
        task = self.offer_source()
        task["price_scenario"] = {"rate_usd_per_gpu_hour": True}
        with self.assertRaisesRegex(ValueError, "not a boolean"):
            task_sources.prepare(task, self.base)

    def test_instance_scope_requires_matching_arithmetic(self):
        row = copy.deepcopy(self.offer)
        row.update(rate_basis="per_instance_hour", instance_rate_usd_per_hour=7.4,
                   gpus=2, rate_usd_per_gpu_hour=1.68)
        task = self.offer_source(row)
        with self.assertRaisesRegex(ValueError, "contradicts"):
            task_sources.prepare(task, self.base)["execute"]()
        row.update(gpus=None, rate_usd_per_gpu_hour=None)
        task = self.offer_source(row)
        result = task_sources.prepare(task, self.base)["execute"]()["offers"][0]
        self.assertIsNone(result["declared_rate"]["value"])
        self.assertTrue(any("allocation unknown" in h for h in result["holds"]))
        self.assertTrue(all(v is None for v in result["modeled_targets"]["values"].values()))

    def test_native_import_identity_and_dependencies_are_preserved(self):
        task, _, raw = self.benchmark_source()
        op = task_sources.prepare(task, self.base)
        output = op["execute"]()
        native = task_sources._owner(task_sources.BENCHMARK_OWNER).import_manifest(self.base / "manifest.json", offline=True)
        self.assertEqual(native, output["observations"])
        self.assertGreater(output["observation_count"], 0)
        self.assertTrue(all(o["fixture"] for o in output["observations"]))
        self.assertEqual(raw.resolve(), op["inputs"]["benchmark_raw_0000"])
        self.assertIsNone(op["inputs"]["benchmark_raw_0000_retrieval"])
        self.assertEqual({}, op["parameters"])

    def test_new_retrieval_receipt_requires_preparing_again(self):
        task, entry, raw = self.benchmark_source()
        op = task_sources.prepare(task, self.base)
        receipt = raw.with_name(raw.name + ".retrieval.json")
        receipt.write_text(json.dumps({k: entry[k] for k in ("url", "revision", "sha256", "retrieved_at")}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed after prepare"):
            op["execute"]()
        fresh = task_sources.prepare(task, self.base)
        self.assertEqual(receipt.resolve(), fresh["inputs"]["benchmark_raw_0000_retrieval"])
        self.assertGreater(fresh["execute"]()["observation_count"], 0)

    def test_corrupt_raw_fails_native_hash_check(self):
        task, _, raw = self.benchmark_source()
        op = task_sources.prepare(task, self.base)
        raw.write_bytes(raw.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "raw SHA-256 mismatch"):
            op["execute"]()

    def test_empty_archives_survive_with_zero_observations(self):
        task, entry, _ = self.benchmark_source(empty=True)
        output = task_sources.prepare(task, self.base)["execute"]()
        self.assertEqual([], output["observations"])
        self.assertEqual([entry], output["empty_archives"])
        self.assertEqual(1, output["source_file_count"])
        self.assertEqual(0, output["source_row_count"])


if __name__ == "__main__":
    unittest.main()
