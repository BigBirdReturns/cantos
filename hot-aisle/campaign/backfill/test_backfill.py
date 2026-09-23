"""Offline tests; python -B test_backfill.py (also both CLI --self-test switches)."""
import copy
import datetime as dt
import json
from pathlib import Path
import uuid
import unittest
from unittest.mock import patch, MagicMock
import importer as I
import delta as D


class BackfillTests(unittest.TestCase):
    def setUp(self):
        self.manifest = I.BASE / "fixtures/manifest.json"
        self.rows = I.import_manifest(self.manifest, offline=True)
        self.row = copy.deepcopy(self.rows[0])
        self.cell = {"id": "synthetic/cell", "hardware": "MI300X", "gpus": 1,
                     "model": self.row["model"], "model_class": self.row["model_class"], "precision": "FP8",
                     "precision_detail": "FP8-dynamic", "framework": "vllm", "framework_version": "0.30.0",
                     "backend": "ROCM_AITER_FA", "model_revision": I.UNKNOWN, "image_digest": I.UNKNOWN,
                     "config": {}, "gates": {}, "posthoc": False, "workload": dict(self.row["workload"]),
                     "raw": {"output_throughput": 200}, "provenance": {"fixture": True}}
        self.today = dt.date(2026, 9, 23)

    def test_fixture_import_and_units(self):
        self.assertEqual(9, len(self.rows))
        self.assertTrue(all(r["tier"] == "imported" and r["fixture"] for r in self.rows))
        self.assertEqual(2500, next(r["metric"]["value"] for r in self.rows if r["metric"]["name"] == "p95_ttft_ms"))
        self.assertEqual(9, len({r["id"] for r in self.rows}))

    def test_repeat_import_stable(self):
        self.assertEqual(self.rows, I.import_manifest(self.manifest, True))

    def test_offline_never_networks(self):
        with patch("urllib.request.build_opener", side_effect=AssertionError("network")):
            self.assertEqual(9, len(I.import_manifest(self.manifest, True)))

    def test_hash_mismatch(self):
        m = json.loads(self.manifest.read_bytes())
        e = dict(m["files"][0], sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            I.acquire(e, self.manifest.parent, True, True)

    def test_offline_missing(self):
        e = dict(json.loads(self.manifest.read_bytes())["files"][0], path="absent.json")
        with patch("urllib.request.build_opener", side_effect=AssertionError("network")):
            with self.assertRaisesRegex(ValueError, "offline cache miss"):
                I.acquire(e, self.manifest.parent, True, True)

    def test_path_escape(self):
        with self.assertRaises(ValueError):
            I.local_path(I.BASE, "../escaped.json")

    def test_live_download_mock_and_pin(self):
        raw = b"example"
        entry = {"path": "raw.txt", "url": "https://raw.githubusercontent.com/org/repo/v1/raw.txt",
                 "revision": "v1", "sha256": I.digest(raw), "retrieved_at": "2026-09-23T00:00:00Z"}
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = raw
        response.geturl.return_value = entry["url"]
        opener = MagicMock()
        opener.open.return_value = response
        folder = I.BASE / ("test-cache-" + uuid.uuid4().hex)
        folder.mkdir()
        try:
            with patch("urllib.request.build_opener", return_value=opener):
                self.assertEqual(raw, I.acquire(entry, Path(folder), False, False))
                self.assertEqual(raw, (Path(folder) / "raw.txt").read_bytes())
                receipt = json.loads((folder / "raw.txt.retrieval.json").read_bytes())
                self.assertEqual(entry["retrieved_at"], receipt["retrieved_at"])
                self.assertNotEqual("2026-09-23T00:00:00Z", receipt["retrieved_at"])
                self.assertEqual(raw, I.acquire(entry, Path(folder), True, False))
            entry["revision"] = "main"
            with self.assertRaises(ValueError):
                I.acquire(entry, Path(folder), True, False)
        finally:
            (folder / "raw.txt").unlink(missing_ok=True)
            (folder / "raw.txt.retrieval.json").unlink(missing_ok=True)
            folder.rmdir()

    def test_invalid_mlperf_rejected(self):
        e = json.loads(self.manifest.read_bytes())["files"][1]
        raw = (self.manifest.parent / e["path"]).read_bytes().replace(b"VALID", b"INVALID")
        with self.assertRaises(ValueError):
            I.mlperf(e, raw, "test", True)

    def test_server_tokens_and_inferred_not_equated(self):
        e = json.loads(self.manifest.read_bytes())["files"][1]
        raw = b"Scenario : Server\nResult is : VALID\nCompleted tokens per second: 200\nCompleted tokens per second (inferred): 300\n"
        rows = I.mlperf(e, raw, "test", True)
        self.assertEqual(["output_throughput", "inferred_output_throughput"], [r["metric"]["name"] for r in rows])

    def test_nonfinite_and_negative_rejected(self):
        for n in ("NaN", "Infinity", -1, True):
            with self.subTest(n=n), self.assertRaises(ValueError):
                I.number(n)

    def test_two_to_one_ratio(self):
        r = D.report([self.row], [self.cell], self.today, True)
        self.assertEqual(2, r["gaps"][0]["ours_div_theirs"])
        self.assertIn("framework_version differs or is UNVERIFIED", r["gaps"][0]["not_like_for_like"])
        self.assertFalse(r["unreproduced"][0]["reproduced"])

    def test_fixture_default_refused(self):
        with self.assertRaisesRegex(ValueError, "fixture"):
            D.report([self.row], [self.cell], self.today)

    def test_no_cross_hardware_precision_or_gpu_ratio(self):
        for key, value in (("hardware", "H200"), ("precision", "BF16"), ("gpus", 8)):
            row = dict(self.row, **{key: value})
            with self.subTest(key=key):
                self.assertFalse(D.report([row], [self.cell], self.today, True)["gaps"])

    def test_unknown_or_different_shape_refused(self):
        for key in ("input_tokens", "output_tokens", "concurrency", "scenario"):
            for value in (None, "different"):
                row = copy.deepcopy(self.row)
                row["workload"][key] = value
                self.assertFalse(D.report([row], [self.cell], self.today, True)["gaps"])

    def test_model_class_caveat(self):
        self.row["model"] = "meta-llama/Llama-2-70b"
        r = D.report([self.row], [self.cell], self.today, True)
        self.assertTrue(any("model class only" in c for c in r["gaps"][0]["not_like_for_like"]))

    def test_zero_denominator(self):
        self.row["metric"]["value"] = 0
        r = D.report([self.row], [self.cell], self.today, True)
        self.assertFalse(r["gaps"])
        self.assertIn("zero source denominator", r["unreproduced"][0]["blockers"])

    def test_wrong_units(self):
        self.row["metric"]["units"] = "samples/s"
        self.assertFalse(D.report([self.row], [self.cell], self.today, True)["gaps"])

    def test_age_is_not_retrieval_date(self):
        self.row["observed_at"] = None
        r = D.report([self.row], [self.cell], self.today, True)
        self.assertIsNone(r["unreproduced"][0]["age_days"])

    def test_rank_gap_and_age(self):
        a = copy.deepcopy(self.row)
        a["id"] = "older"
        a["observed_at"] = "2025-01-01T00:00:00Z"
        r = D.report([self.row, a], [self.cell], self.today, True)
        self.assertEqual("older", r["unreproduced"][0]["imported_id"])

    def test_outcome_hold(self):
        self.row["comparison_hold"] = "review failed outcome"
        self.assertFalse(D.report([self.row], [self.cell], self.today, True)["gaps"])

    def test_tier_and_duplicates(self):
        with self.assertRaises(ValueError):
            D.report([dict(self.row, tier="measured")], [self.cell], self.today, True)
        with self.assertRaises(ValueError):
            D.report([self.row, self.row], [self.cell], self.today, True)

    def test_mlperf_not_random(self):
        rows = [r for r in self.rows if r["source"] == "mlperf"]
        r = D.report(rows, [self.cell], self.today, True)
        self.assertFalse(r["gaps"])
        self.assertEqual(3, len(r["unreproduced"]))

    def test_measured_reader_offline_fixture(self):
        cells = D.measured_cells(I.BASE / "fixtures/results")
        self.assertEqual(1, len(cells))
        self.assertEqual(8192, cells[0]["workload"]["input_tokens"])
        self.assertEqual("ROCM_AITER_FA", cells[0]["backend"])
        self.assertTrue(cells[0]["posthoc"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
