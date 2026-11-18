"""Actual Second Run/native instrument contract over a labelled local SSE fixture.

These tests count HTTP inference requests. They qualify integration and stream
handling, not model quality or physical GPU performance.
"""
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import work


class MaintainerWork(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="maintainer-work-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.store = self.base / "retained"
        self.calls = []
        self.calls_lock = threading.Lock()
        self.block = None
        self.entered = threading.Event()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path.endswith("/models"):
                    value = {"object": "list", "data": [{"id": "fixture-model", "object": "model", "owned_by": "protocol-fixture"}]}
                elif self.path.endswith("/version"):
                    value = {"version": "protocol-fixture-1"}
                else:
                    value = {"status": "ok"}
                data = json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with owner.calls_lock:
                    owner.calls.append(payload)
                owner.entered.set()
                if owner.block is not None:
                    owner.block.wait(timeout=8)
                answer = payload["messages"][-1]["content"]
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.end_headers()
                chunks = [
                    {"model": "fixture-model", "choices": [{"index": 0, "delta": {"role": "assistant", "content": answer}, "finish_reason": None}]},
                    {"model": "fixture-model", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
                ]
                for chunk in chunks:
                    self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                    self.wfile.flush()
                    time.sleep(0.002)
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base_url = "http://127.0.0.1:" + str(self.server.server_address[1]) + "/v1"
        self.policy = {"schema": "cantos.maintainer.policy/1", "allowed_changes": ["identity.implementation.revision", "implementation_inputs"],
                       "min_trials": 1, "min_baseline_acceptance": 1, "min_candidate_acceptance": 1,
                       "max_p95_latency_increase": 1000, "max_p95_ttft_increase": 1000,
                       "max_accepted_throughput_drop": 1, "prices": {"baseline_per_hour": 1, "candidate_per_hour": 1}}
        identity = {"implementation": {"name": "labelled-protocol-fixture", "revision": "baseline-1"},
                    "model": {"revision": "fixture-1", "sha256": "1" * 64},
                    "tokenizer": {"revision": "fixture-1"},
                    "hardware": {"id": "fixture-cpu", "description": "Synthetic HTTP protocol fixture; no inference engine or GPU"},
                    "precision": "fixture", "context_limit": 1024, "settings": {}}
        self.spec = {"schema": "cantos.maintainer.spec/1", "workload": "workload.json", "policy": "policy.json",
                     "protocol": {"trials": 1, "repeats": 1, "concurrency": 1, "seed": 123, "timeout_s": 10, "max_tokens": 32, "warmup": 0, "extra_body": {}},
                     "baseline": {"base_url": self.base_url, "model": "fixture-model", "identity": copy.deepcopy(identity), "implementation_files": ["baseline-implementation.txt"]},
                     "candidate": {"base_url": self.base_url, "model": "fixture-model", "identity": copy.deepcopy(identity), "implementation_files": ["candidate-implementation.txt"]}}
        self.spec["candidate"]["identity"]["implementation"]["revision"] = "candidate-1"
        (self.base / "baseline-implementation.txt").write_text("baseline fixture implementation\n")
        (self.base / "candidate-implementation.txt").write_text("candidate fixture implementation\n")
        self.write("workload.json", {"schema": "cantos.maintainer.workload/1", "name": "labelled-sse-protocol-fixture", "version": "1", "cases": [
            {"id": "alpha", "messages": [{"role": "user", "content": "alpha"}], "expect": {"kind": "text_exact", "value": "alpha"}},
            {"id": "bravo", "messages": [{"role": "user", "content": "bravo"}], "expect": {"kind": "text_exact", "value": "bravo"}}]})
        self.write("policy.json", self.policy)
        self.write("spec.json", self.spec)
        self.request = {"tasks": [
            {"id": "baseline", "task_class": "maintainer-observe", "source": "spec.json", "arm": "baseline", "observation_id": "protocol-fixture-epoch-1"},
            {"id": "candidate", "task_class": "maintainer-observe", "source": "spec.json", "arm": "candidate", "observation_id": "protocol-fixture-epoch-1"},
            {"id": "compare", "task_class": "maintainer-compare", "baseline": {"task": "baseline"}, "candidate": {"task": "candidate"}, "policy": "policy.json"}]}

    def write(self, name, value):
        (self.base / name).write_text(json.dumps(value, indent=2) + "\n")

    def run_work(self, request=None, **kwargs):
        result = work.run(request or self.request, self.base, self.store, **kwargs)
        self.assertEqual(0, result["summary"]["held"], result)
        return result

    def test_new_observations_then_no_change_reuse_preserves_dates(self):
        cold = self.run_work()
        self.assertEqual({"executed": 3, "reused": 0, "held": 0}, cold["summary"])
        self.assertEqual(4, len(self.calls))
        self.assertEqual(4, cold["model_calls"])
        self.assertEqual(2, cold["new_observations"])
        self.assertIsNone(cold["gpu_runs"])
        another_operator = copy.deepcopy(self.request)
        for task in another_operator["tasks"]:
            task["actor"] = "second-operator"
        retained = self.run_work(another_operator)
        self.assertEqual({"executed": 0, "reused": 3, "held": 0}, retained["summary"])
        self.assertEqual(4, len(self.calls))
        self.assertEqual(0, retained["model_calls"])
        self.assertEqual(0, retained["new_observations"])
        for previous, current in zip(cold["tasks"][:2], retained["tasks"][:2]):
            self.assertEqual(previous["observation"]["observed_at"], current["observation"]["observed_at"])
            self.assertEqual("retained-observation", current["observation"]["status"])

    def test_price_only_recomputes_analysis_without_inference(self):
        cold = self.run_work()
        original_results = {t["result"]: Path(t["result"]).read_bytes() for t in cold["tasks"]}
        self.policy["prices"]["candidate_per_hour"] = 9
        self.write("policy.json", self.policy)
        result = self.run_work()
        self.assertEqual(["reused", "reused", "executed"], [t["status"] for t in result["tasks"]])
        self.assertEqual(4, len(self.calls))
        self.assertEqual(0, result["model_calls"])
        self.assertEqual([t["key"] for t in cold["tasks"][:2]], [t["key"] for t in result["tasks"][:2]])
        self.assertNotEqual(cold["tasks"][2]["key"], result["tasks"][2]["key"])
        for path, content in original_results.items():
            self.assertEqual(content, Path(path).read_bytes())

    def test_explicit_external_regrade_reuses_both_captures(self):
        captured_grader = {"name": "fixture grader", "revision": "1", "artifact_sha256": "1" * 64,
                           "reference_sha256": "2" * 64, "normalizer_sha256": "3" * 64}
        workload_path = self.base / "workload.json"
        workload = json.loads(workload_path.read_bytes())
        for case in workload["cases"]:
            case["expect"] = {"kind": "external", "grader": captured_grader}
        self.write("workload.json", workload)
        cold = self.run_work()
        self.assertEqual("incomparable", cold["tasks"][2]["native_verdict"])
        self.assertEqual(4, len(self.calls))
        revised_grader = {**captured_grader, "revision": "2", "artifact_sha256": "4" * 64,
                          "normalizer_sha256": "5" * 64}
        contract = {"schema": "cantos.maintainer.grading-contract/1",
                    "workload_sha256": hashlib.sha256(workload_path.read_bytes()).hexdigest(),
                    "grader": revised_grader}
        self.write("regrade.json", contract)
        contract_bytes = (self.base / "regrade.json").read_bytes()
        contract_sha = hashlib.sha256(contract_bytes).hexdigest()
        observation_bytes = {}
        comparison = self.request["tasks"][2]
        comparison["grading_contract"] = "regrade.json"
        for step in cold["tasks"][:2]:
            side = step["id"]
            run_path = Path(step["observation"]["receipt"])
            observation_bytes[run_path] = run_path.read_bytes()
            observed = json.loads(observation_bytes[run_path])
            archive = self.base / (side + "-graded")
            archive.mkdir()
            (archive / "grading-contract.json").write_bytes(contract_bytes)
            fixture = b"Authored acceptance fixture. No application was executed.\n"
            (archive / "fixture-grade.log").write_bytes(fixture)
            results = [{"task_id": row["task_id"], "trial": row["trial"], "repetition": row["repetition"],
                        "response_sha256": row["attempts"][-1]["response_sha256"], "accepted": True,
                        "evidence": ["fixture-grade.log"]} for row in observed["observations"]]
            receipt = {"schema": "cantos.maintainer.grades/1", "workload_sha256": observed["workload_sha256"],
                       "run_sha256": hashlib.sha256(observation_bytes[run_path]).hexdigest(),
                       "grader": revised_grader, "grading_contract_sha256": contract_sha, "results": results,
                       "artifacts": [{"path": "grading-contract.json", "sha256": contract_sha, "bytes": len(contract_bytes)},
                                     {"path": "fixture-grade.log", "sha256": hashlib.sha256(fixture).hexdigest(), "bytes": len(fixture)}]}
            grade_path = archive / "grades.json"
            self.write(grade_path.relative_to(self.base), receipt)
            comparison[side + "_grades"] = str(grade_path.relative_to(self.base))

        graded = self.run_work()
        self.assertEqual(["reused", "reused", "executed"], [t["status"] for t in graded["tasks"]])
        self.assertEqual("pass", graded["tasks"][2]["native_verdict"])
        self.assertEqual(0, graded["model_calls"])
        self.assertEqual(0, graded["new_observations"])
        self.assertEqual(4, len(self.calls))
        result = json.loads(Path(graded["tasks"][2]["verdict_receipt"]).read_bytes())
        self.assertEqual(contract_sha, result["grading_contract"]["sha256"])
        self.assertEqual(2, result["baseline"]["accepted_tasks"])
        self.assertEqual(2, result["candidate"]["accepted_tasks"])
        for path, raw in observation_bytes.items():
            self.assertEqual(raw, path.read_bytes())
        retained = self.run_work()
        self.assertEqual(["reused"] * 3, [t["status"] for t in retained["tasks"]])
        self.assertEqual(4, len(self.calls))

        candidate_grade = self.base / comparison["candidate_grades"]
        mismatched = json.loads(candidate_grade.read_bytes())
        mismatched["grading_contract_sha256"] = "f" * 64
        self.write(candidate_grade.relative_to(self.base), mismatched)
        rejected = self.run_work()
        self.assertEqual(["reused", "reused", "executed"], [t["status"] for t in rejected["tasks"]])
        self.assertEqual("incomparable", rejected["tasks"][2]["native_verdict"])
        self.assertEqual(2, rejected["tasks"][2]["native_exit_code"])
        self.assertEqual(0, rejected["model_calls"])
        self.assertEqual(4, len(self.calls))

    def test_candidate_implementation_change_only_reobserves_candidate(self):
        cold = self.run_work()
        (self.base / "candidate-implementation.txt").write_text("candidate fixture implementation revision two\n")
        result = self.run_work()
        self.assertEqual(["reused", "executed", "executed"], [t["status"] for t in result["tasks"]])
        self.assertEqual(6, len(self.calls))
        self.assertEqual(2, result["model_calls"])
        self.assertEqual(1, result["new_observations"])
        self.assertEqual(cold["tasks"][0]["key"], result["tasks"][0]["key"])
        self.assertNotEqual(cold["tasks"][1]["key"], result["tasks"][1]["key"])
        self.spec["candidate"]["identity"]["context_limit"] = 2048
        self.write("spec.json", self.spec)
        changed_config = self.run_work()
        self.assertEqual(["reused", "executed", "executed"], [t["status"] for t in changed_config["tasks"]])
        self.assertEqual(8, len(self.calls))
        self.assertEqual("incomparable", changed_config["tasks"][2]["native_verdict"])

    def test_fresh_epoch_and_explicit_reconnect_identity(self):
        cold = self.run_work()
        fresh = self.run_work(fresh=True)
        self.assertEqual(["executed"] * 3, [t["status"] for t in fresh["tasks"]])
        self.assertEqual(8, len(self.calls))
        self.assertEqual(2, fresh["new_observations"])
        recorded = json.loads(Path(fresh["request_record"]).read_bytes())
        epoch = recorded["fresh_observation_id"]
        self.assertTrue(epoch.startswith("fresh-"))
        self.assertNotEqual(cold["tasks"][0]["observation"]["id"], epoch)
        resumed = self.run_work(fresh=epoch)
        self.assertEqual(["reused"] * 3, [t["status"] for t in resumed["tasks"]])
        self.assertEqual(8, len(self.calls))
        self.assertEqual(0, resumed["new_observations"])

    def test_reused_regression_still_fails_ci_gate(self):
        self.run_work()
        self.policy["prices"]["candidate_per_hour"] = 1000
        self.policy["max_cost_per_accepted_increase"] = 0
        self.write("policy.json", self.policy)
        changed = self.run_work()
        self.assertEqual("regression", changed["tasks"][2]["native_verdict"])
        self.write("request.json", self.request)
        process = subprocess.run([sys.executable, "-B", str(HERE / "work.py"),
                                  "--request", str(self.base / "request.json"),
                                  "--store", str(self.store), "--require-maintainer-pass"],
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(1, process.returncode, process.stdout + process.stderr)
        reused = json.loads(process.stdout)
        self.assertEqual(["reused"] * 3, [t["status"] for t in reused["tasks"]])
        self.assertEqual("regression", reused["tasks"][2]["native_verdict"])
        self.assertEqual(4, len(self.calls))
        self.assertEqual(0, reused["model_calls"])

    def test_corrupt_raw_artifact_holds_reuse_and_dependents(self):
        cold = self.run_work()
        entry = json.loads(Path(cold["tasks"][1]["result"]).read_bytes())
        value = entry["value"]
        artifact = Path(value["artifact_root"]) / value["artifacts"][0]["path"]
        artifact.write_bytes(artifact.read_bytes() + b" ")
        result = work.run(self.request, self.base, self.store)
        self.assertEqual(["reused", "held", "held"], [t["status"] for t in result["tasks"]])
        self.assertEqual(4, len(self.calls))
        self.assertIn("checksum", result["tasks"][1]["reason"])
        self.assertEqual(0, result["model_calls"])

    def test_external_grade_addition_and_damage_never_repeat_inference(self):
        workload = json.loads((self.base / "workload.json").read_bytes())
        grader = {"name": "labelled-fixture-grader", "revision": "1",
                  "artifact_sha256": "2" * 64, "reference_sha256": "3" * 64}
        for case in workload["cases"]:
            case["expect"] = {"kind": "external", "grader": grader}
        self.write("workload.json", workload)
        initial = self.run_work()
        self.assertEqual("incomparable", initial["tasks"][2]["native_verdict"])
        request = copy.deepcopy(self.request)
        evidence_paths = []
        for index, name in enumerate(("baseline", "candidate")):
            envelope = json.loads(Path(initial["tasks"][index]["result"]).read_bytes())
            run_path = Path(envelope["value"]["receipt"])
            run = json.loads(run_path.read_bytes())
            directory = self.base / (name + "-grading")
            directory.mkdir()
            evidence = directory / "fixture-results.json"
            evidence.write_text(json.dumps({"evidence_class": "synthetic protocol test", "outcomes": [o["task_id"] for o in run["observations"]]}))
            evidence_paths.append(evidence)
            grades = {"schema": "cantos.maintainer.grades/1", "grader": grader,
                      "run_sha256": hashlib.sha256(run_path.read_bytes()).hexdigest(),
                      "workload_sha256": run["workload_sha256"],
                      "artifacts": [{"path": evidence.name, "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(), "bytes": evidence.stat().st_size}],
                      "results": [{"task_id": o["task_id"], "trial": o["trial"], "repetition": o["repetition"],
                                   "response_sha256": o["attempts"][-1]["response_sha256"], "accepted": True,
                                   "evidence": [evidence.name]} for o in run["observations"]]}
            grades_path = directory / "grades.json"
            grades_path.write_text(json.dumps(grades))
            request["tasks"][2][name + "_grades"] = str(grades_path)
        graded = self.run_work(request)
        self.assertEqual(["reused", "reused", "executed"], [t["status"] for t in graded["tasks"]])
        self.assertEqual("pass", graded["tasks"][2]["native_verdict"])
        self.assertEqual(4, len(self.calls))
        self.assertEqual(0, graded["model_calls"])
        evidence_paths[1].write_text("altered external grader evidence\n")
        damaged = work.run(request, self.base, self.store)
        self.assertEqual(["reused", "reused", "held"], [t["status"] for t in damaged["tasks"]])
        self.assertEqual(4, len(self.calls))
        self.assertEqual(0, damaged["model_calls"])

    def test_same_epoch_concurrent_attempt_cannot_duplicate_live_requests(self):
        self.block = threading.Event()
        one = {"tasks": self.request["tasks"][:1]}
        result = {}
        thread = threading.Thread(target=lambda: result.update(work.run(one, self.base, self.store)))
        thread.start()
        try:
            self.assertTrue(self.entered.wait(timeout=10), "first live request never started")
            duplicate = work.run(one, self.base, self.store)
            self.assertEqual("held", duplicate["tasks"][0]["status"], duplicate)
            self.assertIn("already claimed", duplicate["tasks"][0]["reason"])
            self.assertEqual(0, duplicate["model_calls"])
        finally:
            self.block.set()
            thread.join(timeout=15)
        self.assertFalse(thread.is_alive())
        self.assertEqual(0, result["summary"]["held"], result)
        self.assertEqual(2, len(self.calls))
        terminal = Path(result["tasks"][0]["result"])
        self.assertEqual("second-run/computation@1", json.loads(terminal.read_bytes())["schema"])
        self.assertFalse(list(terminal.parent.glob(".work-publish-*")))


if __name__ == "__main__":
    unittest.main()
