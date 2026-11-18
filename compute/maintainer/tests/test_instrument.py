"""Protocol/decision contract tests. The fixture is not a GPU or model benchmark."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import maintainer as m
from common import closure, load, prepare, sha256_file, write
from owner_ocl.core import validate_record


class Endpoint:
    def __init__(self, mode="good", delay=0.002):
        self.mode, self.delay, self.requests = mode, delay, 0
        outer = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                body = {"version": "fixture-1"} if self.path == "/version" else {"data": [{"id": "fixture-model"}]}
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def do_POST(self):
                outer.requests += 1
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if not body["stream"]:
                    raise AssertionError("client failed to request streaming")
                if outer.mode == "http":
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b'{"error":"fixture failure"}')
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                model = "wrong-model" if outer.mode == "model" else "fixture-model"
                def event(delta, finish=None):
                    return b"data: " + json.dumps({"model": model, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}).encode() + b"\n\n"
                self.wfile.write(event({"role": "assistant"}))
                self.wfile.write(event({"reasoning_content": "reasoning is not answer content"}))
                self.wfile.flush()
                time.sleep(outer.delay)
                text = '{"value": 3}' if outer.mode == "wrong" else '{"value": 2}'
                question = body["messages"][-1]["content"]
                if (outer.mode == "mixed_a" and question == "hard") or (outer.mode == "mixed_b" and question == "easy"):
                    text = '{"value": 3}'
                if outer.mode == "duplicate":
                    text = '{"value": 3, "value": 2}'
                if outer.mode == "external":
                    text = "def f():\n    return 2\n"
                if outer.mode == "empty":
                    text = ""
                finish = "length" if outer.mode == "length" else "stop"
                self.wfile.write(event({"content": text}, finish))
                if outer.mode == "malformed":
                    self.wfile.write(b"data: {badjson}\n\n")
                self.wfile.write(b'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":4}}\n\n')
                if outer.mode != "missing_done":
                    # Deliberately split the DONE frame before its final blank line.
                    self.wfile.write(b"data: [DONE]\n")
                    self.wfile.flush()
                    time.sleep(0.001)
                    self.wfile.write(b"\n")
                self.wfile.flush()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port) + "/v1"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class Instrument(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.a, self.b = Endpoint(), Endpoint()
        identity = {"implementation": {"name": "fixture", "revision": "1"},
                    "model": {"revision": "1", "sha256": "a" * 64},
                    "tokenizer": {"revision": "1"}, "hardware": {"id": "fixture", "description": "CPU protocol fixture, no GPU claim"},
                    "precision": "fixture", "context_limit": 4096, "settings": {"cache": False}}
        arm = {"base_url": self.a.url, "model": "fixture-model", "identity": identity}
        self.spec = {"schema": "cantos.maintainer.spec/1", "workload": "workload.json", "policy": "policy.json",
                     "protocol": {"trials": 2, "repeats": 1, "concurrency": 1, "timeout_s": 2, "max_tokens": 100},
                     "baseline": copy.deepcopy(arm), "candidate": copy.deepcopy(arm)}
        self.spec["candidate"]["base_url"] = self.b.url
        self.work = {"schema": "cantos.maintainer.workload/1", "name": "protocol fixture", "version": "1",
                     "cases": [{"id": "case", "messages": [{"role": "user", "content": "Return value 2 as JSON"}],
                                "expect": {"kind": "json_exact", "value": {"value": 2}}}]}
        self.pol = {"schema": "cantos.maintainer.policy/1", "min_trials": 2,
                    "max_p95_latency_increase": 100, "max_p95_ttft_increase": 100,
                    "max_accepted_throughput_drop": 1, "require_observed_version": True}
        self.save()

    def save(self):
        for name, value in (("spec", self.spec), ("workload", self.work), ("policy", self.pol)):
            (self.root / (name + ".json")).write_text(json.dumps(value))

    def run_pair(self, name="pair"):
        self.save()
        return m.run(self.root / "spec.json", self.root / name)

    def analyze(self, name="again", **kwargs):
        self.save()
        return m.analyze_receipts(self.root / "pair/baseline/run.json", self.root / "pair/candidate/run.json",
                                  self.root / "policy.json", self.root / name, **kwargs)

    def tearDown(self):
        self.a.close()
        self.b.close()
        self.tmp.cleanup()

    def test_streamed_paired_pass_and_raw_timing(self):
        result = self.run_pair()
        self.assertEqual(result["verdict"], "pass", result)
        self.assertTrue(result["paired_trials"])
        self.assertEqual((self.a.requests, self.b.requests), (2, 2))
        run = m.validate_receipt(self.root / "pair/baseline/run.json")
        self.assertEqual([t["paired_position"] for t in run["trials"]], [0, 1])
        attempt = run["observations"][0]["attempts"][0]
        self.assertGreaterEqual(attempt["ttft_s"], self.a.delay)
        self.assertEqual(attempt["response_text"], '{"value": 2}')
        self.assertEqual(attempt["output_tokens"], 4)
        self.assertEqual(len(attempt["content_chunk_times_s"]), 1)
        self.assertEqual(result["baseline"]["peak_request_concurrency"], 1)

    def test_native_ocl_export_keeps_source_and_policy_identity(self):
        result = self.run_pair()
        self.assertEqual(result["ocl_exports"]["status"], "exported")
        native = load(self.root / "pair/analysis/baseline.ocl.json")
        self.assertEqual(validate_record(native), [])
        self.assertEqual(native["observations"][0]["attempts"][-1]["stage"], "final")
        self.assertEqual(native["observations"][0]["attempts"][-1]["source_stage"], "step_0")
        self.assertEqual(native["provenance"]["maintainer_evidence"]["source_run_sha256"], sha256_file(self.root / "pair/baseline/run.json"))
        self.assertIsNone(native["cost"])
        self.assertEqual(native["provenance"]["maintainer_evidence"]["new_inference_requests"], 0)

    def test_packet_export_rejects_an_unpinned_bundle_before_loading_code(self):
        import packets
        self.run_pair()
        bad = self.root / "untrusted.zip"
        bad.write_bytes(b"not the pinned workbench source")
        with self.assertRaisesRegex(ValueError, "pinned .*workbench ZIP SHA256"):
            packets.export_packets(self.root / "pair/analysis", bad, self.root / "export")
        self.assertFalse((self.root / "export").exists())

    def test_changed_native_export_blocks_packet_generation(self):
        import packets
        self.run_pair()
        path = self.root / "pair/analysis/baseline.ocl.json"
        value = load(path)
        value["observations"][0]["accepted"] = False
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "analysis export changed"):
            packets._checked_analysis(self.root / "pair/analysis")

    def test_quality_regression_even_when_every_candidate_response_is_http_200(self):
        self.b.mode = "wrong"
        result = self.run_pair()
        self.assertEqual(result["verdict"], "regression", result)
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["candidate"]["accepted_tasks"], 0)

    def test_duplicate_json_keys_never_pass(self):
        self.b.mode = "duplicate"
        self.assertEqual(self.run_pair()["verdict"], "regression")

    def test_balanced_wins_and_losses_do_not_hide_new_failures(self):
        self.a.mode, self.b.mode = "mixed_a", "mixed_b"
        self.work["cases"] = [{"id": name, "messages": [{"role": "user", "content": name}],
                               "expect": {"kind": "json_exact", "value": {"value": 2}}} for name in ("easy", "hard")]
        self.pol.update({"min_baseline_acceptance": 0.5, "min_candidate_acceptance": 0.5})
        result = self.run_pair()
        self.assertEqual(result["baseline"]["accepted_tasks"], result["candidate"]["accepted_tasks"])
        self.assertEqual(result["verdict"], "regression", result)
        self.assertEqual(result["native_ocl_comparison"]["paired_counts"]["a_only"], 2)
        self.assertEqual(result["baseline"]["matched_accepted_tasks"], 0)
        self.assertIsNone(result["baseline"]["p95_latency_s"])

    def test_all_failed_reference_is_incomparable(self):
        self.a.mode = self.b.mode = "wrong"
        result = self.run_pair()
        self.assertEqual(result["verdict"], "incomparable", result)

    def test_http_failure_is_error_and_raw_body_survives(self):
        self.b.mode = "http"
        result = self.run_pair()
        self.assertEqual(result["verdict"], "error", result)
        run = m.validate_receipt(self.root / "pair/candidate/run.json")
        raw = load(self.root / "pair/candidate" / run["observations"][0]["attempts"][0]["raw_path"])
        self.assertEqual(raw["http_status"], 500)
        self.assertIn("http_error_body_b64", raw)

    def test_unfinished_stream_is_error_even_with_correct_visible_answer(self):
        self.b.mode = "missing_done"
        result = self.run_pair()
        self.assertEqual(result["verdict"], "error", result)

    def test_malformed_stream_is_error(self):
        self.b.mode = "malformed"
        self.assertEqual(self.run_pair()["verdict"], "error")

    def test_length_finish_requires_explicit_policy_acceptance(self):
        self.b.mode = "length"
        result = self.run_pair()
        self.assertEqual(result["verdict"], "regression", result)
        self.pol["acceptance"] = {"finish_reasons": ["stop", "length"]}
        self.assertEqual(self.analyze()["verdict"], "pass")
        self.assertEqual(self.b.requests, 2)

    def test_unmatched_conditions_and_explicit_changed_factor(self):
        self.spec["candidate"]["identity"]["settings"]["cache"] = True
        result = self.run_pair()
        self.assertEqual(result["verdict"], "incomparable", result)
        self.pol["allowed_changes"] = ["identity.settings.cache"]
        result = self.analyze()
        self.assertEqual(result["verdict"], "pass", result)
        self.assertEqual(result["changed_factors"][0]["factor"], "identity.settings.cache")
        self.assertEqual((self.a.requests, self.b.requests), (2, 2))

    def test_observed_model_mismatch_blocks_pass(self):
        self.b.mode = "model"
        self.assertEqual(self.run_pair()["verdict"], "incomparable")

    def test_missing_identity_blocks_pass(self):
        self.spec["candidate"]["identity"]["model"]["sha256"] = "unknown"
        self.pol["allowed_changes"] = ["identity.model.sha256"]
        self.assertEqual(self.run_pair()["verdict"], "incomparable")

    def test_price_and_other_arm_do_not_invalidate_observation(self):
        (self.root / "implementation.py").write_text("revision=1\n")
        self.spec["candidate"]["implementation_files"] = ["implementation.py"]
        self.save()
        baseline = prepare(self.root / "spec.json", "baseline")
        candidate = prepare(self.root / "spec.json", "candidate")
        self.pol["prices"] = {"baseline_per_hour": 4, "candidate_per_hour": 8}
        self.spec["baseline"]["identity"]["implementation"]["revision"] = "2"
        self.save()
        self.assertEqual(candidate["identity"], prepare(self.root / "spec.json", "candidate")["identity"])
        self.assertNotEqual(baseline["identity"], prepare(self.root / "spec.json", "baseline")["identity"])
        (self.root / "implementation.py").write_text("revision=2\n")
        self.assertNotEqual(candidate["identity"], prepare(self.root / "spec.json", "candidate")["identity"])
        self.assertNotIn(str(self.root / "spec.json"), candidate["dependencies"])
        self.assertNotIn(str(self.root / "policy.json"), candidate["dependencies"])

    def test_price_only_reanalysis_makes_no_requests(self):
        self.run_pair()
        self.pol["prices"] = {"baseline_per_hour": 1, "candidate_per_hour": 100}
        self.pol["max_cost_per_accepted_increase"] = 0
        result = self.analyze()
        self.assertEqual(result["verdict"], "regression", result)
        self.assertEqual(result["baseline"]["accepted_tasks"], result["candidate"]["accepted_tasks"])
        self.assertEqual((self.a.requests, self.b.requests), (2, 2))

    def test_unpriced_work_stays_unknown_until_price_is_explicit(self):
        result = self.run_pair()
        for arm in ("baseline", "candidate"):
            self.assertIsNone(result[arm]["cost_assumption_per_hour"])
            self.assertIsNone(result[arm]["estimated_cost"])
            self.assertIsNone(result[arm]["cost_per_accepted"])
        self.assertIn("| cost_per_accepted | unpriced | unpriced |", (self.root / "pair/report.md").read_text())
        self.pol["prices"] = {"baseline_per_hour": 0, "candidate_per_hour": 0}
        result = self.analyze()
        self.assertEqual(result["candidate"]["estimated_cost"], 0)
        self.assertEqual(result["candidate"]["cost_per_accepted"], 0)
        self.assertEqual((self.a.requests, self.b.requests), (2, 2))

    def test_tampered_response_or_grade_cannot_false_pass(self):
        self.b.mode = "wrong"
        self.run_pair()
        path = self.root / "pair/candidate/run.json"
        r = load(path)
        r["observations"][0]["accepted"] = True
        path.write_text(json.dumps(r))
        self.assertEqual(self.analyze()["verdict"], "error")

    def test_missing_raw_artifact_is_error(self):
        self.run_pair()
        r = load(self.root / "pair/candidate/run.json")
        (self.root / "pair/candidate" / r["observations"][0]["attempts"][0]["raw_path"]).unlink()
        self.assertEqual(self.analyze()["verdict"], "error")

    def test_performance_threshold_detects_real_fixture_delay(self):
        self.b.delay = 0.06
        self.pol["max_p95_latency_increase"] = 1
        self.pol["max_p95_ttft_increase"] = 1
        self.assertEqual(self.run_pair()["verdict"], "regression")

    def test_external_grades_bound_to_response_workload_and_grader(self):
        grader = {"name": "fixture application grader", "revision": "1", "artifact_sha256": "1" * 64,
                  "reference_sha256": "2" * 64, "criterion": "exact fixture result", "normalizer_sha256": "3" * 64}
        self.work["cases"][0]["expect"] = {"kind": "external", "grader": grader}
        self.a.mode = self.b.mode = "external"
        result = self.run_pair()
        self.assertEqual(result["verdict"], "incomparable", result)
        self.assertEqual(result["ocl_exports"]["status"], "awaiting_external_grades")
        self.assertFalse((self.root / "pair/analysis/baseline.ocl.json").exists())
        grade_paths = {}
        for arm in ("baseline", "candidate"):
            run_path = self.root / "pair" / arm / "run.json"
            run = load(run_path)
            out = self.root / (arm + "-grades")
            out.mkdir()
            write(out / "grader-results.json", {"fixture": True, "accepted": True})
            receipt = {"schema": "cantos.maintainer.grades/1", "run_sha256": sha256_file(run_path),
                       "workload_sha256": run["workload_sha256"], "grader": grader,
                       "results": [{"task_id": o["task_id"], "trial": o["trial"], "repetition": o["repetition"],
                                    "response_sha256": o["attempts"][-1]["response_sha256"], "accepted": True,
                                    "evidence": ["grader-results.json"]} for o in run["observations"]],
                       "artifacts": closure(out)}
            write(out / "grades.json", receipt)
            grade_paths[arm + "_grades"] = out / "grades.json"
        result = self.analyze(**grade_paths)
        self.assertEqual(result["verdict"], "pass", result)
        grade = load(grade_paths["candidate_grades"])
        grade["results"][0]["response_sha256"] = "0" * 64
        grade_paths["candidate_grades"].write_text(json.dumps(grade))
        self.assertEqual(self.analyze("bad-grades", **grade_paths)["verdict"], "error")

    def test_cli_regression_exit_and_no_remeasurement(self):
        self.b.mode = "wrong"
        self.run_pair()
        result = subprocess.run([sys.executable, "-B", str(Path(m.__file__)), "analyze",
                                 "--baseline", str(self.root / "pair/baseline/run.json"),
                                 "--candidate", str(self.root / "pair/candidate/run.json"),
                                 "--policy", str(self.root / "policy.json"), "--out", str(self.root / "cli")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["verdict"], "regression")
        self.assertEqual((self.a.requests, self.b.requests), (2, 2))


if __name__ == "__main__":
    unittest.main()
