"""Tests for the three importer changes ported from the public-tail 2026-09-29 lane.

Fixtures are byte-identical copies of real InferenceX artifacts 8024546098 and 8027554070.
Run: python -B hot-aisle/campaign/backfill/tests/test_lane_2026_09_29.py
"""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import importer  # noqa: E402

FIX = HERE.parent / "fixtures"
FLAT = FIX / "inferencex-8024546098-flat-agentic.json"
TP0 = FIX / "inferencex-8027554070-tp0.json"
SIDECAR = FIX / "inferencex-8027554070-artifact.json"


def entry(name, raw):
    return {"source": "inferencemax", "url": "https://example.invalid/" + name, "revision": "a" * 40,
            "retrieved_at": "2026-09-29T00:00:00Z", "observed_at": None, "path": name, "sha256": importer.digest(raw)}


class FlatAgenticSchema(unittest.TestCase):
    def test_flat_rows_import_with_mapped_metrics(self):
        raw = FLAT.read_bytes()
        rows = importer.inferencemax(entry("flat", raw), raw, "0" * 64, True)
        src = json.loads(raw)
        self.assertTrue(rows)
        self.assertEqual({r["row_index"] for r in rows}, set(range(len(src))))
        names = {r["metric"]["name"] for r in rows}
        for want in ("mean_ttft_ms", "p90_e2el_ms", "p95_tpot_ms", "output_throughput", "window_mean_qps", "successful_requests"):
            self.assertIn(want, names)
        self.assertNotIn("median_ttft_ms", names)  # no p50 in the flat schema
        first = next(r for r in rows if r["row_index"] == 0 and r["metric"]["name"] == "mean_ttft_ms")
        self.assertAlmostEqual(first["metric"]["value"], src[0]["mean_ttft"] * 1000)
        self.assertEqual(first["metric"]["units"], "ms")
        self.assertTrue(any("Flat agentic schema" in w for w in first["warnings"]))
        qps = next(r for r in rows if r["row_index"] == 0 and r["metric"]["name"] == "window_mean_qps")
        self.assertAlmostEqual(qps["metric"]["value"], src[0]["mean_qps"])

    def test_nested_schema_unchanged(self):
        raw = json.dumps([{"hw": "h100-x", "model": "m", "precision": "fp8", "framework": "vllm", "conc": 4,
                           "scenario_type": "agentic-coding", "isl": 1, "osl": 1, "tp": 1, "pp": 1,
                           "request_metrics": {"latency": {"ttft": {"p50": 0.5}}}}]).encode()
        rows = importer.inferencemax(entry("nested", raw), raw, "0" * 64, True)
        self.assertIn("median_ttft_ms", {r["metric"]["name"] for r in rows})
        self.assertFalse(any("Flat agentic" in w for r in rows for w in r["warnings"]))


class ZeroGpuCount(unittest.TestCase):
    def test_gpu_count_unit(self):
        self.assertEqual(importer.gpu_count({"tp": 0, "pp": 1}), (None, "UNVERIFIED (tp/pp zero or absent)"))
        self.assertEqual(importer.gpu_count({"tp": 0, "pp": None, "is_multinode": True})[0], None)
        self.assertEqual(importer.gpu_count({"num_prefill_gpu": 0, "num_decode_gpu": 0})[0], None)
        self.assertEqual(importer.gpu_count({"num_gpus": 0})[0], None)
        self.assertEqual(importer.gpu_count({"tp": 4, "pp": 1})[0], 4)
        self.assertEqual(importer.gpu_count({"num_gpus": 8})[0], 8)

    def test_invalid_counts_still_abort(self):
        for bad in ({"num_gpus": 1.5}, {"num_gpus": -2}, {"num_prefill_gpu": 1.5, "num_decode_gpu": 1}):
            with self.assertRaises(ValueError):
                importer.gpu_count(bad)

    def test_tp0_artifact_imports_with_null_gpus(self):
        raw = TP0.read_bytes()
        rows = importer.inferencemax(entry("tp0", raw), raw, "0" * 64, True)  # previously raised ValueError
        self.assertTrue(rows)
        self.assertTrue(all(r["gpus"] is None for r in rows))
        self.assertTrue(all(r["gpu_count_rule"].startswith("UNVERIFIED") for r in rows))


class RetrievedAt(unittest.TestCase):
    def build(self, sidecar):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        d = tmp / "results_bmk_8027554070"
        d.mkdir()
        shutil.copy(TP0, d / "agg_bmk.json")
        (d / "artifact.json").write_text(json.dumps(sidecar), encoding="utf-8")
        return importer.raw_manifest(tmp, "2026-09-23T23:40:00Z")["files"][0]

    def test_sidecar_retrieved_at_wins(self):
        sidecar = json.loads(SIDECAR.read_bytes())
        self.assertEqual(self.build(sidecar)["retrieved_at"], sidecar["retrieved_at"])

    def test_missing_sidecar_retrieved_at_uses_declared(self):
        sidecar = json.loads(SIDECAR.read_bytes())
        del sidecar["retrieved_at"]
        self.assertEqual(self.build(sidecar)["retrieved_at"], "2026-09-23T23:40:00Z")

    def test_sidecar_hash_binds_raw(self):
        sidecar = json.loads(SIDECAR.read_bytes())
        sidecar["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.build(sidecar)


class DeltaSourceKey(unittest.TestCase):
    def test_mlperf_rows_without_raw_sha_are_countable(self):
        import datetime
        import delta
        row = {"schema": "imported-observation@1", "tier": "imported", "fixture": False, "id": "x", "source": "mlperf",
               "provenance": {"path": "closed/x/mlperf_log_summary.txt", "url": "u", "revision": "r"}, "row_index": 0,
               "hardware": "H100", "gpus": 8, "model": "m", "model_class": None, "precision": "FP8",
               "workload": {"scenario": "Offline"}, "metric": {"name": "output_throughput", "value": 1.0, "units": "tokens/s"},
               "observed_at": None}
        out = delta.report([row], [], datetime.date(2026, 9, 29))
        self.assertEqual(out["imported_source_rows"], 1)


if __name__ == "__main__":
    unittest.main()
