"""The estate's own capture lanes become a Cantos collection: rows, packets, history, next attempt."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from corpus import estate_bundle  # noqa: E402
from corpus.reader import Collection, producer_links  # noqa: E402
from corpus.query import select_rows  # noqa: E402


def observation(index, source="inferencemax", **overrides):
    row = {
        "schema": "imported-observation@1", "tier": "imported", "fixture": True, "source": source,
        "id": hashlib.sha256(f"{source}-{index}".encode()).hexdigest(),
        "hardware": "B200" if source == "inferencemax" else "NVIDIA H100-SXM-80GB", "gpus": 8,
        "framework": "sglang" if source == "inferencemax" else "TensorRT 10.0, CUDA 12.4",
        "model": "deepseek-ai/DeepSeek-R1" if source == "inferencemax" else "llama2-70b-99",
        "precision": "FP4" if source == "inferencemax" else "FP8",
        "metric": {"name": "median_ttft_ms", "value": 120.5 + index, "units": "ms"},
        "config": {"scenario_type": "agentic-coding", "conc": 32, "tp": 8, "pp": 1} if source == "inferencemax"
                  else {"loadgen": {"Scenario": "Offline", "Result is": "VALID"}},
        "provenance": ({"artifact_id": 10002250391 + index, "head_sha": "e52162e5c4805ccf6933199034dbf2f7ba9f5b55",
                        "revision": "e52162e5c4805ccf6933199034dbf2f7ba9f5b55", "retrieved_at": "2026-09-24T00:01:58Z",
                        "sha256": "f22ce4ded4effb7d2e88c429eea1c7bd0137e6c45e94c4a3e8835db9fc2b5f9d",
                        "url": f"https://api.github.com/repos/SemiAnalysisAI/InferenceX/actions/artifacts/{10002250391 + index}",
                        "workflow_run_id": 34075605579}
                       if source == "inferencemax" else
                       {"url": "https://raw.githubusercontent.com/mlcommons/inference_results_v5.1/5ea4f62e/closed/X/results/a/llama2-70b-99/Offline/performance/run_1/mlperf_log_summary.txt",
                        "revision": "5ea4f62e", "repo": "mlcommons/inference_results_v5.1", "release": "v5.1",
                        "retrieved_at": "2026-09-29T20:07:39Z",
                        "systems_json_url": "https://raw.githubusercontent.com/mlcommons/inference_results_v5.1/5ea4f62e/closed/X/systems/a.json"}),
        "observed_at": "2026-09-07T02:31:45Z", "workload": "fixture", "warnings": [], "success_rate": 1.0,
        "num_requests_successful": 100, "num_requests_total": 100, "outcome": "ok", "gates": "UNVERIFIED",
    }
    row.update(overrides)
    return row


def issue(index):
    return {"source": "github-issues", "repo": "vllm-project/vllm", "number": 19000 + index,
            "title": f"[Bug] B200 regression {index}", "state": "closed", "state_reason": "completed",
            "labels": ["bug"], "created_at": "2026-09-20T00:00:00Z", "closed_at": "2026-09-22T00:00:00Z",
            "updated_at": "2026-09-22T00:00:00Z", "author_association": "NONE", "comments": 3,
            "is_pull_request": False, "url": f"https://github.com/vllm-project/vllm/issues/{19000 + index}",
            "hardware": ["B200"], "model_family": ["deepseek"], "error_class": "performance regression",
            "error_classes_all": ["performance regression"], "fix_reference": None,
            "provenance": {"url": "https://api.github.com/repos/vllm-project/vllm/issues?page=1", "sha256": "ab" * 32, "retrieved_at": "2026-09-29"}}


def write_lane(root, name, rows, manifest_entries, jsonl_manifest=False):
    lane = root / "lanes" / name
    (lane / "rows").mkdir(parents=True)
    with (lane / "rows" / f"{name}.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    if jsonl_manifest:
        with (lane / "manifest.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
            for entry in manifest_entries:
                stream.write(json.dumps(entry) + "\n")
    else:
        (lane / "manifest.json").write_text(json.dumps(manifest_entries), encoding="utf-8")
    (lane / "REPORT.md").write_text(f"# Lane {name}\n\nFixture lane.\n", encoding="utf-8")
    return lane


class EstateBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name) / "capture-20260929"
        self.inferencex = write_lane(root, "inferencex-history",
            [observation(0), observation(1), observation(2, metric={"name": "output_throughput_per_gpu", "value": 512.0, "units": "tokens/s/GPU"})],
            [{"url": "https://api.github.com/repos/SemiAnalysisAI/InferenceX/actions/artifacts/1/zip", "sha256": "00" * 32,
              "retrieved_utc": "2026-09-29T20:18:00+00:00", "license": "Apache-2.0 (repo README)"},
             {"url": "https://api.github.com/repos/SemiAnalysisAI/InferenceX/actions/artifacts/2/zip", "sha256": "01" * 32,
              "retrieved_utc": "2026-09-23T23:40:00+00:00", "license": "Apache-2.0 (repo README)"}], jsonl_manifest=True)
        self.mlperf = write_lane(root, "mlperf", [observation(0, source="mlperf"), observation(1, source="mlperf")],
            [{"url": "https://raw.githubusercontent.com/mlcommons/inference_results_v5.1/5ea4f62e/closed/X/systems/a.json",
              "sha256": "02" * 32, "retrieved_utc": "2026-09-29T20:07:39.015911+00:00", "license": "Apache-2.0 (repo LICENSE)"}])
        self.issues = write_lane(root, "github-issues", [issue(0), issue(1)],
            [{"url": "https://api.github.com/repos/vllm-project/vllm/issues?page=1", "sha256": "03" * 32,
              "retrieved_utc": "2026-09-29T20:06:03Z", "license": "GitHub REST API"}])
        self.out = Path(self.temporary.name) / "collection"
        self.state = Path(self.temporary.name) / "attempts"
        self.estate = estate_bundle.build([self.inferencex, self.mlperf, self.issues], self.out, actor="Fixture assembler", log=lambda *_: None)

    def test_lanes_become_one_verified_collection(self):
        self.assertTrue(self.estate["all_pass"])
        self.assertEqual(7, self.estate["rows"])
        self.assertEqual({"benchmark": 5, "producer_issue": 2}, self.estate["by_kind"])
        self.assertEqual(3, self.estate["packets"])
        verify = json.loads((self.out / "verification" / "VERIFY.json").read_text(encoding="utf-8"))
        self.assertTrue(verify["all_pass"])
        self.assertIn("full re-import is byte-identical", [c["name"] for c in verify["checks"]])
        manifest = json.loads((self.out / "inputs" / "manifest.json").read_text(encoding="utf-8"))
        origins = [s["origin"] for s in manifest["sources"]]
        self.assertEqual(["capture-20260929/inferencex-history", "capture-20260929/mlperf", "capture-20260929/github-issues"], origins)
        inferencex = manifest["sources"][0]
        self.assertEqual("2026-09-29T20:18:00+00:00", inferencex["retrieved_at"])
        self.assertEqual("Apache-2.0 (repo README)", inferencex["license"])
        self.assertEqual("https://api.github.com/repos/SemiAnalysisAI/InferenceX/actions/artifacts/", inferencex["url"])
        self.assertEqual("manifest.jsonl", inferencex["lane"]["manifest_file"])
        index = json.loads((self.out / "research-packets" / "INDEX.json").read_text(encoding="utf-8"))
        for entry in index["batches"]:
            self.assertLessEqual(entry["first_row_id"], entry["last_row_id"])
            self.assertEqual(1, len(entry["origins"]))

    def test_projection_keeps_units_and_producer_conditions(self):
        db = self.out / "corpus" / "corpus.sqlite"
        latency = select_rows(db, kind="benchmark", unit="ms", hardware="B200")
        self.assertEqual(2, latency["matching_rows"])
        row = latency["rows"][0]
        self.assertEqual("agentic-coding", row["scope"]["Scenario"])
        self.assertEqual("SGLang", row["engine"])
        self.assertEqual("FP4", row["quant"])
        self.assertEqual(8, row["hardware_count"])
        self.assertIsNone(row["throughput"])
        self.assertEqual("ms", row["latency"]["unit"])
        self.assertEqual("e52162e5c4805ccf6933199034dbf2f7ba9f5b55", row["scope"]["producer_revision"])
        self.assertEqual(row["native"]["config"], {"scenario_type": "agentic-coding", "conc": 32, "tp": 8, "pp": 1})
        throughput = select_rows(db, kind="benchmark", unit="tokens/s/GPU")
        self.assertEqual(1, throughput["matching_rows"])
        self.assertEqual(512.0, throughput["rows"][0]["throughput"]["value"])
        mlperf = select_rows(db, kind="benchmark", scenario="Offline")
        self.assertEqual(2, mlperf["matching_rows"])
        self.assertEqual("MLPerf v5.1", mlperf["rows"][0]["outcome"]["contract"])
        issues = select_rows(db, kind="producer_issue", hardware="b200")
        self.assertEqual(2, issues["matching_rows"])
        self.assertEqual("vLLM", issues["rows"][0]["engine"])
        self.assertEqual("performance regression", issues["rows"][0]["scope"]["error_class"])

    def test_history_links_reach_the_producing_work(self):
        db = self.out / "corpus" / "corpus.sqlite"
        collection = Collection(self.out, self.state)
        inferencex = select_rows(db, kind="benchmark", hardware="B200", unit="ms")["rows"][0]
        labels = {link["label"]: link["url"] for link in collection.history(inferencex["row_id"])["links"]}
        self.assertEqual("https://github.com/SemiAnalysisAI/InferenceX/commit/e52162e5c4805ccf6933199034dbf2f7ba9f5b55", labels["Producing commit"])
        self.assertEqual("https://github.com/SemiAnalysisAI/InferenceX/actions/runs/34075605579", labels["Producing workflow run"])
        self.assertIn("Producer record", labels)
        mlperf = select_rows(db, kind="benchmark", scenario="Offline")["rows"][0]
        labels = {link["label"]: link["url"] for link in collection.history(mlperf["row_id"])["links"]}
        self.assertEqual("https://github.com/mlcommons/inference_results_v5.1/commit/5ea4f62e", labels["Producing commit"])
        self.assertIn("Producer system description", labels)
        issue_row = select_rows(db, kind="producer_issue")["rows"][0]
        labels = {link["label"]: link["url"] for link in collection.history(issue_row["row_id"])["links"]}
        self.assertEqual("https://github.com/vllm-project/vllm/issues/19000", labels["Issue or pull request"])
        self.assertEqual([], producer_links({"source": {"url": "ftp://not-http"}, "native": {}, "scope": {}}))

    def test_next_attempt_extends_the_native_history(self):
        db = self.out / "corpus" / "corpus.sqlite"
        collection = Collection(self.out, self.state)
        row = select_rows(db, kind="benchmark", hardware="B200", unit="ms")["rows"][0]
        self.assertEqual([], collection.history(row["row_id"])["attempts"])
        result = collection.attempt(row["row_id"], "Stranger with the tools")
        self.assertTrue(result["matches_current_projection"])
        history = collection.history(row["row_id"])
        self.assertEqual(1, len(history["attempts"]))
        self.assertEqual(result["id"], history["attempts"][0]["id"])
        exported = json.loads(collection.export(row["row_id"], result["id"]).read_text(encoding="utf-8"))
        self.assertEqual("second-run/research-packet@1", exported["schema"])
        self.assertEqual(3, len(exported["workspace"]["events"]))
        second = collection.attempt(row["row_id"], "Second stranger")
        self.assertEqual(result["packet_sha256"], second["predecessor_sha256"])
        self.assertEqual(2, len(collection.history(row["row_id"])["attempts"]))

    def test_existing_collection_and_bad_lanes_are_refused(self):
        with self.assertRaises(FileExistsError):
            estate_bundle.build([self.inferencex], self.out, log=lambda *_: None)
        root = Path(self.temporary.name) / "bad"
        lane = write_lane(root, "unknown", [{"schema": "something-else@1"}], [])
        with self.assertRaisesRegex(ValueError, "unsupported lane row schema"):
            estate_bundle.build([lane], Path(self.temporary.name) / "never", log=lambda *_: None)
        shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()
