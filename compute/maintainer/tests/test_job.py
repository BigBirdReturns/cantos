"""Job orchestration tests use local streamed HTTP fixtures, never a model or GPU."""
import copy
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
import base64
import socket

from compute.maintainer import job
from compute.maintainer import retry


class Endpoint:
    def __init__(self):
        self.requests = 0
        outer = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                value = {"version": "fixture-1"} if self.path == "/version" else {"data": [{"id": "fixture-model"}]}
                body = json.dumps(value).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            def do_POST(self):
                outer.requests += 1
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                frames = [
                    {"model": "fixture-model", "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]},
                    {"model": "fixture-model", "choices": [{"index": 0, "delta": {"content": '{"ok":true}'}, "finish_reason": "stop"}]},
                    {"choices": [], "usage": {"prompt_tokens": 2, "completion_tokens": 2}},
                ]
                for value in frames:
                    self.wfile.write(b"data: " + json.dumps(value).encode() + b"\n\n")
                self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port) + "/v1"
    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()


class JobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.a, self.b = Endpoint(), Endpoint()
        ident = {"implementation": {"name": "fixture", "revision": "1"},
                 "model": {"revision": "1", "sha256": "a" * 64}, "tokenizer": {"revision": "1"},
                 "hardware": {"id": "local-cpu-fixture", "description": "CPU HTTP test only"},
                 "precision": "fixture", "context_limit": 128, "settings": {"cache": False}}
        arm = {"base_url": self.a.url, "model": "fixture-model", "identity": ident, "implementation_files": ["untrusted.py"]}
        self.spec = {"schema": "cantos.maintainer.spec/1", "workload": "workload.json", "policy": "policy.json",
                     "protocol": {"trials": 1, "repeats": 1, "concurrency": 1, "timeout_s": 2, "max_tokens": 16},
                     "baseline": copy.deepcopy(arm), "candidate": copy.deepcopy(arm)}
        self.spec["candidate"]["base_url"] = self.b.url
        self.workload = {"schema": "cantos.maintainer.workload/1", "name": "job fixture", "version": "1",
                         "cases": [{"id": "case", "messages": [{"role": "user", "content": "Return JSON"}],
                                    "expect": {"kind": "json_exact", "value": {"ok": True}}}]}
        self.policy = {"schema": "cantos.maintainer.policy/1", "min_trials": 1,
                       "max_p95_latency_increase": 10, "max_p95_ttft_increase": 10,
                       "max_accepted_throughput_drop": 1}
        for name, value in (("spec.json", self.spec), ("workload.json", self.workload), ("policy.json", self.policy)):
            (self.root / name).write_text(json.dumps(value), encoding="utf-8")
        (self.root / "untrusted.py").write_text("from pathlib import Path\nPath('SHOULD_NOT_EXIST').write_text('executed')\n", encoding="utf-8")
        self.manifest = {"schema": "cantos.deployment-job/1", "id": "job-fixture",
                         "comparison": {"spec": "spec.json"},
                         "decision": {"objective": "min_cost_per_accepted", "economics_required": True,
                                      "operational_requirements": []},
                         "arms": {side: {"operations": [], "resources": side + "-resource-template.json"} for side in ("baseline", "candidate")}}
        self.manifest["external_grading"] = {"execute": False, "reference": "grade-reference.json"}
        (self.root / "grade-reference.json").write_text("{}", encoding="utf-8")
        for side in ("baseline", "candidate"):
            template = {"schema": "cantos.resource-template/1",
                        "resource_identity_sha256": job.deployment.sha(ident["hardware"]),
                        "accounting_mode": "measured_trials", "scenario": {}, "additional_costs": []}
            (self.root / (side + "-resource-template.json")).write_text(json.dumps(template), encoding="utf-8")
        (self.root / "deployment-job.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def tearDown(self):
        self.a.close(); self.b.close(); self.tmp.cleanup()

    def test_paired_job_export_import_and_reprice_are_no_inference_on_reanalysis(self):
        run_dir = self.root / "retained"
        from unittest.mock import patch
        with patch.object(job.external_grader, "grade_pair", side_effect=AssertionError("Docker grader must be opt-in")) as grade_pair:
            job.run_job(self.root / "deployment-job.json", run_dir)
            grade_pair.assert_not_called()
        self.assertEqual((self.a.requests, self.b.requests), (1, 1))
        for side in ("baseline", "candidate"):
            run_path = run_dir / "native" / "capture" / side / "run.json"
            resource_ref = json.loads((run_dir / "job.json").read_text())["arms"][side]["resources"]
            bound = json.loads((run_dir / resource_ref).read_text())
            self.assertEqual(bound["binding"]["run_sha256"], hashlib.sha256(run_path.read_bytes()).hexdigest())
            self.assertEqual(bound["accounting"]["window"], bound["binding"]["observed_window"])
        self.assertFalse((run_dir / "SHOULD_NOT_EXIST").exists())
        bundle = self.root / "bundle"
        job.export_job(run_dir, bundle)
        with patch.object(job.external_grader, "grade_pair", side_effect=AssertionError("import must never execute a grader")) as grade_pair:
            imported = job.import_job(bundle, self.root / "imported")
        grade_pair.assert_not_called()
        self.assertEqual(imported["decision_identity"], json.loads((run_dir / "decision.json").read_text())["decision_identity"])
        self.assertEqual((self.a.requests, self.b.requests), (1, 1))

        revised = self.root / "revised-source"
        shutil.copytree(run_dir, revised)
        policy_path = revised / "inputs" / "policy.json"
        policy = json.loads(policy_path.read_text()); policy["min_candidate_acceptance"] = 0.95
        policy_path.write_text(json.dumps(policy))
        child = job.decide_job(revised, self.root / "child")
        self.assertTrue(child["post_hoc"])
        self.assertEqual(child["parent_id"], json.loads((revised / "decision.json").read_text())["decision_identity"])
        self.assertEqual(child["execution"]["inference_requests"], 0)
        self.assertEqual((self.a.requests, self.b.requests), (1, 1))
        job.export_job(self.root / "child", self.root / "child-bundle")
        child_import = job.import_job(self.root / "child-bundle", self.root / "child-import")
        self.assertEqual(child_import["decision_identity"], child["decision_identity"])
        revised_again = self.root / "revised-again"
        shutil.copytree(self.root / "child", revised_again)
        policy_path = revised_again / "inputs" / "policy.json"
        policy = json.loads(policy_path.read_text()); policy["min_candidate_acceptance"] = 0.9
        policy_path.write_text(json.dumps(policy))
        grandchild = job.decide_job(revised_again, self.root / "grandchild")
        self.assertEqual(grandchild["parent_id"], child["decision_identity"])
        job.export_job(self.root / "grandchild", self.root / "grandchild-bundle")
        grandchild_import = job.import_job(self.root / "grandchild-bundle", self.root / "grandchild-import")
        self.assertEqual(grandchild_import["decision_identity"], grandchild["decision_identity"])
        self.assertEqual((self.a.requests, self.b.requests), (1, 1))

    def test_serving_change_requires_capture(self):
        run_dir = self.root / "retained"
        job.run_job(self.root / "deployment-job.json", run_dir)
        changed = self.root / "changed-source"
        shutil.copytree(run_dir, changed)
        spec_path = changed / "inputs" / "spec.json"
        spec = json.loads(spec_path.read_text()); spec["candidate"]["identity"]["settings"]["cache"] = True
        spec_path.write_text(json.dumps(spec))
        with self.assertRaisesRegex(ValueError, "capture_required"):
            job.decide_job(changed, self.root / "changed-child")

    def test_collected_attachment_is_retained_once_through_child_and_import(self):
        spec = json.loads((self.root / "spec.json").read_text())
        host_hash = hashlib.sha256(socket.gethostname().encode("utf-8")).hexdigest()
        for side in ("baseline", "candidate"):
            hardware = spec[side]["identity"]["hardware"]
            hardware.update({"audit_host_label": "fixture-host", "audit_host_id_sha256": host_hash})
            template_path = self.root / (side + "-resource-template.json")
            template = json.loads(template_path.read_text())
            template["resource_identity_sha256"] = job.deployment.sha(hardware)
            template_path.write_text(json.dumps(template))
        (self.root / "spec.json").write_text(json.dumps(spec))
        requirement = {"id": "loopback-recovery", "check_id": "owned_loopback.recovery_verified",
                       "operator": "eq", "threshold": True, "required": True, "max_age_s": 3600,
                       "allowed_basis": ["observed"]}
        manifest = json.loads((self.root / "deployment-job.json").read_text())
        manifest["decision"]["operational_requirements"] = [requirement]
        for side in ("baseline", "candidate"):
            acquisition = {"schema": "cantos.local-operation-acquisition/1", "arm": side,
                           "host_label": "fixture-host", "host_id_sha256": host_hash,
                           "hardware_identity_sha256": job.deployment.sha(spec[side]["identity"]["hardware"]),
                           "observed_window": {"start": "2026-11-18T00:00:00Z", "end": "2026-11-18T00:00:01Z"},
                           "check_id": "owned_loopback.recovery", "raw_base64": base64.b64encode(b"{}").decode(),
                           "summary_base64": base64.b64encode(b"{}").decode(), "packet_base64": base64.b64encode(b"{}").decode()}
            (self.root / (side + "-acquisition.json")).write_text(json.dumps(acquisition))
            manifest["arms"][side]["collection"] = side + "-acquisition.json"
        (self.root / "collected-job.json").write_text(json.dumps(manifest))
        retained = self.root / "collected-retained"
        job.run_job(self.root / "collected-job.json", retained)
        for side in ("baseline", "candidate"):
            operation_ref = json.loads((retained / "job.json").read_text())["arms"][side]["operations"][-1]
            attachments = json.loads((retained / operation_ref).read_text())
            self.assertEqual([item["check_id"] for item in attachments], ["owned_loopback.recovery_verified"])
        child = self.root / "collected-child"
        job.decide_job(retained, child)
        for side in ("baseline", "candidate"):
            operation_ref = json.loads((child / "job.json").read_text())["arms"][side]["operations"][-1]
            attachments = json.loads((child / operation_ref).read_text())
            self.assertEqual(len(attachments), 1)
        job.export_job(child, self.root / "collected-bundle")
        imported = job.import_job(self.root / "collected-bundle", self.root / "collected-import")
        self.assertEqual(imported["decision_identity"], json.loads((child / "decision.json").read_text())["decision_identity"])

    def test_explicit_external_grader_is_one_shot_and_retained_data_only(self):
        from unittest.mock import patch
        manifest = json.loads((self.root / "deployment-job.json").read_text())
        manifest["external_grading"] = {"execute": True, "reference": "grade-reference.json"}
        (self.root / "external-job.json").write_text(json.dumps(manifest))

        def fake_grade_pair(runs, config, closure_root, out_dir):
            out = Path(out_dir); out.mkdir(parents=True)
            receipts = {}
            for side in ("baseline", "candidate"):
                path = out / (side + "-grades.json")
                path.write_text(json.dumps({"artifacts": []}))
                receipts[side] = path
            return {**receipts, "execution": {"inference_requests": 0, "grader_executions": 2}, "artifacts": []}

        def fake_native(*args, **kwargs):
            result = {"verdict": "incomparable", "baseline": {}, "candidate": {}, "policy": {}, "inputs": {}}
            if len(args) > 3:
                output = Path(args[3]); output.mkdir(parents=True, exist_ok=True)
                (output / "verdict.json").write_text(json.dumps(result))
                (output / "report.md").write_text("fixture")
            return result

        def fake_decision(contract, native, runs, operations=None, resources=None, parent=None, *, retry_evidence=None):
            parent_id = parent.get("decision_identity") if parent else None
            return {"schema": "cantos.deployment-decision/1", "decision_identity": "b" * 64 if parent else "a" * 64,
                    "state": "INCOMPARABLE", "native_verdict": "incomparable", "post_hoc": parent is not None,
                    "parent_id": parent_id, "original_id": parent.get("original_id", parent_id) if parent else None,
                    "native": native, "execution": {"inference_requests": 0, "grader_executions": 0}}

        run_dir = self.root / "external-retained"
        with patch.object(job.external_grader, "grade_pair", side_effect=fake_grade_pair) as grader, \
                patch.object(job.maintainer, "analyze_receipts", side_effect=fake_native), \
                patch.object(job.deployment, "decide_deployment", side_effect=fake_decision):
            job.run_job(self.root / "external-job.json", run_dir)
            grader.assert_called_once()
            retained = json.loads((run_dir / "job.json").read_text())
            self.assertFalse(retained["external_grading"]["execute"])
            self.assertTrue((run_dir / "execution-plan.json").is_file())
            for side in ("baseline", "candidate"):
                grade_path = run_dir / retained["comparison"][side + "_grades"]
                self.assertTrue(grade_path.is_file())
            child = self.root / "external-child"
            job.decide_job(run_dir, child)
            job.export_job(child, self.root / "external-bundle")
            job.import_job(self.root / "external-bundle", self.root / "external-import")
            grader.assert_called_once()
        self.assertEqual((self.a.requests, self.b.requests), (1, 1))

    def test_failed_posthoc_child_cannot_export_copied_parent_decision(self):
        from unittest.mock import patch
        retained = self.root / "retained-for-failure"
        job.run_job(self.root / "deployment-job.json", retained)
        partial = self.root / "partial-child"
        with patch.object(job.deployment, "decide_deployment", side_effect=RuntimeError("fixture decision failure")):
            with self.assertRaisesRegex(RuntimeError, "fixture decision failure"):
                job.decide_job(retained, partial)
        self.assertTrue((partial / "decision.json").is_file())  # copied parent remains for recovery
        self.assertEqual(json.loads((partial / "decision-status.json").read_text())["status"], "in_progress")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            job.export_job(partial, self.root / "must-not-export")

    def test_retry_campaign_closure_survives_child_export_import_without_requests(self):
        retry_policy = {"schema": "cantos.maintainer.retry-policy/1", "max_attempts": 2,
                        "backoff_s": 0, "retry_on": ["rejected", "transport_error"], "attempt_seed_stride": 1}
        retry_policy_path = self.root / "retry-policy.json"
        retry_policy_path.write_text(json.dumps(retry_policy))
        campaigns = {}
        telemetry_paths = {}
        for side in ("baseline", "candidate"):
            folder = self.root / (side + "-campaign")
            retry.run(self.root / "spec.json", side, retry_policy_path, folder, "campaign-" + side)
            campaigns[side] = folder
            campaign_path = folder / "retry-campaign.json"
            campaign = json.loads(campaign_path.read_text())
            telemetry_root = self.root / (side + "-telemetry")
            telemetry_root.mkdir()
            sample_path = telemetry_root / "samples.jsonl"
            start, end = campaign["started_monotonic_s"], campaign["ended_monotonic_s"]
            producer = {"name": "recipient fixture sampler"}
            events = [
                {"kind": "sampler_started", "clock_identity": campaign["clock_identity"],
                 "devices": ["GPU-fixture"], "max_gap_s": 2.5, "producer": producer},
                {"kind": "power_sample", "t_s": start - 0.1,
                 "readings": [{"device_uuid": "GPU-fixture", "watts": 100.0}]},
                {"kind": "power_sample", "t_s": end + 0.1,
                 "readings": [{"device_uuid": "GPU-fixture", "watts": 100.0}]},
                {"kind": "sampler_ended"},
            ]
            sample_path.write_text("".join(json.dumps(event) + "\n" for event in events))
            telemetry_path = telemetry_root / "telemetry.json"
            telemetry = {"schema": "cantos.retry.telemetry/1",
                         "campaign_sha256": hashlib.sha256(campaign_path.read_bytes()).hexdigest(),
                         "observation_id": campaign["observation_id"], "clock_identity": campaign["clock_identity"],
                         "devices": ["GPU-fixture"], "max_gap_s": 2.5,
                         "samples": {"path": sample_path.name, "sha256": hashlib.sha256(sample_path.read_bytes()).hexdigest(),
                                     "bytes": sample_path.stat().st_size},
                         "sensor": "fixture", "attribution": "gross_board",
                         "producer": producer, "observed_at": "2026-11-18T00:00:00Z", "evidence_class": "fixture"}
            telemetry_path.write_text(json.dumps(telemetry))
            telemetry_paths[side] = telemetry_path
        manifest = json.loads((self.root / "deployment-job.json").read_text())
        manifest["retry"] = {"required": True, "economics": False}
        for side, folder in campaigns.items():
            manifest["arms"][side]["retry"] = {
                "campaign": (folder / "retry-campaign.json").relative_to(self.root).as_posix(),
                "telemetry": telemetry_paths[side].relative_to(self.root).as_posix()}
        manifest_path = self.root / "retry-job.json"
        manifest_path.write_text(json.dumps(manifest))
        retained = self.root / "retry-retained"
        result = job.run_job(manifest_path, retained)
        self.assertEqual(result["layers"]["retry"]["status"], "complete")
        for side in ("baseline", "candidate"):
            ref = json.loads((retained / "job.json").read_text())["arms"][side]["retry"]["campaign"]
            campaign_copy = retained / ref
            self.assertTrue(campaign_copy.is_file())
            self.assertTrue((campaign_copy.parent / "events.jsonl").is_file())
            retry_item = json.loads((retained / "job.json").read_text())["arms"][side]["retry"]
            telemetry_copy = retained / retry_item["telemetry"]
            samples_ref = json.loads(telemetry_copy.read_text())["samples"]["path"]
            self.assertTrue((telemetry_copy.parent / samples_ref).is_file())
        requests = (self.a.requests, self.b.requests)
        child = self.root / "retry-child"
        child_result = job.decide_job(retained, child)
        self.assertTrue(child_result["post_hoc"])
        self.assertEqual(child_result["parent_id"], result["decision_identity"])
        self.assertEqual(child_result["layers"]["retry"]["status"], "complete")
        job.export_job(child, self.root / "retry-bundle")
        imported = job.import_job(self.root / "retry-bundle", self.root / "retry-import")
        self.assertEqual(imported["decision_identity"], child_result["decision_identity"])
        self.assertEqual((self.a.requests, self.b.requests), requests)

    def test_collection_preflight_passes_original_packet_to_raw_verifier(self):
        raw, summary = b'{"fixture":"raw"}', b'{"fixture":"summary"}'
        packet = {"schema": "ocl.instrument-packet/1",
                  "provenance": {"source_sha256": "a" * 64, "captured_at": "2026-11-18T00:00:00Z",
                                 "completed_at": "2026-11-18T00:00:01Z"},
                  "files": [{"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                            for name, data in (("recovery/raw.json", raw), ("recovery/summary.json", summary))],
                  "operations": {"service_recovery": json.loads(summary)}}
        packet_bytes = json.dumps(packet).encode()
        from unittest.mock import patch
        seen = {}
        original = job.deployment._operation_value
        def capture_attachment(attachment):
            seen.update(attachment)
            return original(attachment)
        with patch.object(job.deployment, "load", return_value={"operational_collector": {"sha256": "a" * 64}}), \
                patch.object(job.deployment.recovery_verifier, "verify", return_value={"injected_recovery_trials": [{"stop_to_recovered_s": 1}], "limits": []}), \
                patch.object(job.deployment, "_operation_value", side_effect=capture_attachment):
            job._verify_recovery_collection(raw, summary, packet_bytes)
        self.assertEqual(base64.b64decode(seen["packet_base64"]), packet_bytes)

    def test_adversarial_protocol_is_rejected_before_native_validator(self):
        path = self.root / "forged-run.json"
        path.write_text(json.dumps({"protocol": {"trials": 10**12, "repeats": 10**12}, "observations": []}))
        from unittest.mock import patch
        with patch.object(job.maintainer, "validate_receipt", side_effect=AssertionError("must not be reached")) as validator:
            with self.assertRaisesRegex(ValueError, "bounded exact integers"):
                job._validate_runs_against_spec(self.root / "spec.json", 1, {"baseline": path})
            validator.assert_not_called()

    def test_manifest_paths_reject_traversal(self):
        from unittest.mock import patch
        with self.assertRaisesRegex(ValueError, "stay inside"):
            job._inside(self.root, "../outside.json", "bad reference")


if __name__ == "__main__":
    unittest.main()
