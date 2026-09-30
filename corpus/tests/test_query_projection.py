import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import bulk_import
import projection
import query


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.bundle = Path(self.temporary.name)
        (self.bundle / "inputs" / "raw").mkdir(parents=True)
        (self.bundle / "corpus").mkdir()
        self.raw_path = self.bundle / "inputs" / "raw" / "mlperf.json"
        native = [
            {
                "ID": "5.1-test-a",
                "Accelerator": "NVIDIA H100-SXM-80GB",
                "Model": "llama2-70b-99",
                "Performance_Result": 124879.0,
                "Performance_Units": "Tokens/s",
                "Scenario": "Offline",
                "Accuracy": "ROUGE1: 44.5",
                "compliance": 1,
                "errors": 0,
                "version": "v5.1",
                "a#": 8,
            },
            {
                "ID": "5.1-test-b",
                "Accelerator": "NVIDIA H100-SXM-80GB",
                "Model": "llama2-70b-99",
                "Performance_Result": 124880.0,
                "Performance_Units": "Tokens/s",
                "Scenario": "Offline",
                "Accuracy": "ROUGE1: 44.5",
                "compliance": 1,
                "errors": 0,
                "version": "v5.1",
                "a#": 8,
            },
        ]
        self.raw_path.write_text(json.dumps(native), encoding="utf-8")
        raw = self.raw_path.read_bytes()
        manifest = {
            "sources": [
                {
                    "origin": "mlperf-test",
                    "format": "mlperf-summary",
                    "path": "raw/mlperf.json",
                    "url": "https://example.invalid/mlperf.json",
                    "revision": "test-revision",
                    "retrieved_at": "2026-09-29T16:49:23.573643+00:00",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "evidence_class": "synthetic",
                    "license": "test-only",
                    "time_basis": "fixture source time",
                }
            ]
        }
        self.manifest = self.bundle / "inputs" / "manifest.json"
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        self.import_report = bulk_import.ingest(self.manifest, self.bundle / "corpus")
        self.db = self.bundle / "corpus" / "corpus.sqlite"

    def test_query_filters_pages_and_exact_row_lookup(self):
        first = query.select_rows(
            self.db, kind="benchmark", hardware="H100",
            model="llama2-70b-99", scenario="Offline", unit="Tokens/s",
            limit=1, offset=0,
        )
        second = query.select_rows(
            self.db, kind="benchmark", hardware="H100",
            model="llama2-70b-99", scenario="Offline", unit="Tokens/s",
            limit=1, offset=1,
        )
        self.assertEqual(2, first["matching_rows"])
        self.assertEqual(0, first["selection"]["offset"])
        self.assertNotEqual(first["rows"][0]["row_id"], second["rows"][0]["row_id"])
        self.assertEqual(first["rows"][0], query.row_by_id(self.db, first["rows"][0]["row_id"]))
        with self.assertRaises(KeyError):
            query.row_by_id(self.db, "missing")

    def test_projection_replays_source_and_preserves_synthetic_evidence(self):
        selected = query.select_rows(self.db, kind="benchmark", limit=1)["rows"][0]
        receipt = projection.reproject(self.bundle, selected["row_id"], actor="Test operator")
        self.assertTrue(receipt["matches_current_projection"])
        self.assertEqual(selected, receipt["before"])
        self.assertEqual(selected, receipt["rebuilt"])
        self.assertEqual("synthetic", receipt["source"]["evidence_class"])
        self.assertTrue(all(receipt["checks"].values()))
        self.assertFalse(receipt["outcome"]["benchmark_executed"])
        self.assertIsNone(receipt["outcome"]["accepted_work"])

    def test_projection_difference_is_a_reimport_correction_not_a_measurement(self):
        selected = query.select_rows(self.db, kind="benchmark", limit=1)["rows"][0]
        db = sqlite3.connect(self.db)
        db.execute(
            "UPDATE rows SET json = json_set(json, '$.measurement.value', 1) WHERE row_id = ?",
            (selected["row_id"],),
        )
        db.commit()
        db.close()
        receipt = projection.reproject(self.bundle, selected["row_id"])
        self.assertFalse(receipt["matches_current_projection"])
        self.assertEqual(1, receipt["before"]["measurement"]["value"])
        self.assertEqual(124879.0, receipt["rebuilt"]["measurement"]["value"])
        self.assertEqual("reimport", receipt["outcome"]["kind"])
        self.assertFalse(receipt["outcome"]["benchmark_executed"])

    def test_changed_raw_bytes_fail_closed(self):
        selected = query.select_rows(self.db, kind="benchmark", limit=1)["rows"][0]
        self.raw_path.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "raw source SHA-256 mismatch"):
            projection.reproject(self.bundle, selected["row_id"])

    def test_changed_source_metadata_fails_closed(self):
        selected = query.select_rows(self.db, kind="benchmark", limit=1)["rows"][0]
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        manifest["sources"][0]["revision"] = "different-revision"
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source metadata differs"):
            projection.reproject(self.bundle, selected["row_id"])


if __name__ == "__main__":
    unittest.main()
