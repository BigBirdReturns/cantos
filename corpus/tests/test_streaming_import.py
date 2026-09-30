import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import bulk_import
import projection
import query


def imported_row(model, value):
    return {
        "schema": "imported-observation@1",
        "source": "mlperf",
        "data_kind": "inference",
        "workload": "test-workload",
        "observed_at": "2026-09-30T00:00:00Z",
        "hardware": "NVIDIA H100",
        "gpus": 1,
        "model": model,
        "precision": "bf16",
        "framework": "vllm",
        "metric": {"name": "Throughput", "value": value, "units": "Tokens/s"},
        "config": {"scenario_type": "Offline", "loadgen": {"Scenario": "Offline"}},
        "provenance": {"revision": "test-commit", "release": "fixture"},
        "outcome": {"state": "reported"},
    }


def source_for(origin, fmt, relative_path, raw):
    return {
        "origin": origin,
        "format": fmt,
        "path": relative_path,
        "url": "https://example.invalid/" + origin,
        "revision": "test-revision",
        "retrieved_at": "2026-09-30T00:00:00Z",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "evidence_class": "synthetic",
        "license": "test-only",
        "time_basis": "fixture source time",
    }


class StreamingSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cantos-streaming-test-")
        self.addCleanup(self.temporary.cleanup)
        self.bundle = Path(self.temporary.name)
        (self.bundle / "inputs" / "raw").mkdir(parents=True)
        (self.bundle / "corpus").mkdir()
        self.raw_path = self.bundle / "inputs" / "raw" / "observations.jsonl"
        self.rows = [imported_row("model-alpha", 12.5), imported_row("model-beta", 27.0)]
        raw = (json.dumps(self.rows[0], separators=(",", ":")).encode("utf-8") + b"\r\n" +
               b"  \r\n" +
               json.dumps(self.rows[1], separators=(",", ":")).encode("utf-8") + b"\n")
        self.raw_path.write_bytes(raw)
        self.raw = raw
        self.source = source_for("test-lane", "imported-observation-jsonl", "raw/observations.jsonl", raw)
        self.manifest_path = self.bundle / "inputs" / "manifest.json"
        self.manifest_path.write_text(json.dumps({"sources": [self.source]}), encoding="utf-8")

    def test_streaming_jsonl_is_byte_compatible_and_projection_reads_only_one_pass(self):
        legacy = list(bulk_import.ADAPTERS[self.source["format"]](self.source, self.raw))
        self.assertEqual([0, 1], [row["source"]["row_index"] for row in legacy])

        original_open = Path.open
        raw_opens = []

        def counted_open(path, *args, **kwargs):
            if path.resolve() == self.raw_path.resolve() and args and args[0] == "rb":
                raw_opens.append("open")
            return original_open(path, *args, **kwargs)

        original_read_bytes = Path.read_bytes

        def guarded_read_bytes(path):
            if path.resolve() == self.raw_path.resolve():
                self.fail("JSONL raw source must not be loaded with read_bytes")
            return original_read_bytes(path)

        with patch.object(Path, "open", counted_open), patch.object(Path, "read_bytes", guarded_read_bytes):
            report = bulk_import.ingest(self.manifest_path, self.bundle / "corpus")
        self.assertEqual(1, len(raw_opens))
        self.assertEqual(2, report["sources"][0]["source_rows"])
        self.assertEqual(2, report["rows"])

        rows_file = self.bundle / "corpus" / "rows.jsonl"
        self.assertEqual(hashlib.sha256(rows_file.read_bytes()).hexdigest(), report["rows_sha256"])
        imported = [query.row_by_id(self.bundle / "corpus" / "corpus.sqlite", row["row_id"]) for row in legacy]
        self.assertEqual(legacy, imported)

        raw_opens.clear()
        with patch.object(Path, "open", counted_open), patch.object(Path, "read_bytes", guarded_read_bytes):
            for row in imported:
                receipt = projection.reproject(self.bundle, row["row_id"], actor="stream test")
                self.assertTrue(receipt["matches_current_projection"])
                self.assertEqual(row, receipt["rebuilt"])
                self.assertTrue(all(receipt["checks"].values()))
        self.assertEqual(2, len(raw_opens))
        self.assertEqual([0, 1], [row["source"]["row_index"] for row in imported])

    def test_streamed_hash_mismatch_rolls_back_all_rows_from_source(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["sources"][0]["sha256"] = "0" * 64
        bad_manifest = self.bundle / "inputs" / "bad-manifest.json"
        bad_manifest.write_text(json.dumps(manifest), encoding="utf-8")
        destination = self.bundle / "failed-corpus"
        with self.assertRaisesRegex(ValueError, "Raw hash mismatch"):
            bulk_import.ingest(bad_manifest, destination)
        db = sqlite3.connect(destination / "corpus.sqlite")
        try:
            self.assertEqual(0, db.execute("SELECT count(*) FROM rows").fetchone()[0])
        finally:
            db.close()

    def test_selected_row_parses_only_target_and_still_hashes_to_eof(self):
        calls = []
        real_loads = json.loads
        def counted(value, *args, **kwargs):
            calls.append(value)
            return real_loads(value, *args, **kwargs)
        with patch.object(bulk_import.json, "loads", counted):
            selected = bulk_import.jsonl_native_at(self.raw_path, 1, self.source["sha256"])
        self.assertEqual(1, len(calls))
        self.assertEqual(self.rows[1], selected)
        self.raw_path.write_bytes(self.raw + b"{}\n")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            bulk_import.jsonl_native_at(self.raw_path, 0, self.source["sha256"])

    def test_importer_cli_round_trip_matches_rows_and_projection_hash(self):
        destination = self.bundle / "cli-corpus"
        result = subprocess.run(
            [sys.executable, str(HERE / "bulk_import.py"), "--manifest",
             str(self.manifest_path), "--out", str(destination)],
            check=True, capture_output=True, text=True, encoding="utf-8")
        report = json.loads(result.stdout)
        rows_path = destination / "rows.jsonl"
        self.assertEqual(report["rows_sha256"], hashlib.sha256(rows_path.read_bytes()).hexdigest())
        imported = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
        expected = list(bulk_import.ADAPTERS[self.source["format"]](self.source, self.raw))
        self.assertEqual(sorted(expected, key=lambda row: row["row_id"]), imported)
        rebuilt = [bulk_import.rebuild_source_row(self.source, self.raw_path, i) for i in range(len(expected))]
        self.assertEqual(expected, rebuilt)

    def test_bytes_adapter_compatibility_for_producer_issue_jsonl(self):
        raw_rows = [
            {"source": "github-issues", "repo": "vllm-project/vllm", "number": 1,
             "title": "H100 issue", "is_pull_request": False, "hardware": ["H100"],
             "labels": ["bug"], "state": "closed", "url": "https://example.invalid/1"},
            {"source": "github-issues", "repo": "sgl-project/sglang", "number": 2,
             "title": "MI300 issue", "is_pull_request": True, "hardware": ["MI300X"],
             "labels": ["fix"], "state": "open", "url": "https://example.invalid/2"},
        ]
        raw = (json.dumps(raw_rows[0]).encode("utf-8") + b"\n\n" +
               json.dumps(raw_rows[1]).encode("utf-8") + b"\n")
        path = self.bundle / "inputs" / "raw" / "issues.jsonl"
        path.write_bytes(raw)
        source = source_for("issue-lane", "github-issues-jsonl", "raw/issues.jsonl", raw)
        expected = list(bulk_import.ADAPTERS[source["format"]](source, raw))
        actual = list(bulk_import.iter_source_rows(source, path))
        self.assertEqual(expected, actual)
        self.assertEqual([0, 1], [row["source"]["row_index"] for row in actual])


if __name__ == "__main__":
    unittest.main()
