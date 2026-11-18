"""Owned network unit fixtures: mocked transport only, no remote probe/service."""
import base64
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from compute.maintainer import deployment as D, job
from compute.maintainer.owner_ocl import network_health as N

CERT = b"synthetic-peer-DER-unit-fixture-not-a-real-certificate"
COLLECTOR = N.sha(b"unit-collector-host")
RESPONDER = N.sha(b"unit-responder-host")


def fixture():
    hardware = {"id": "fixture-resource", "audit_host_id_sha256": RESPONDER}
    expected = {"id": "owned-fixture-route", "url": "https://192.0.2.2:19443/owned-health",
        "collector_host_id_sha256": COLLECTOR, "responder_host_id_sha256": RESPONDER,
        "responder_instance_id": "17a98094-feb8-46f7-a82d-0840c12a9174",
        "responder_source_sha256": N.sha(Path(N.__file__).read_bytes()), "tls_certificate_sha256": N.sha(CERT),
        "resource_identity_sha256": D.sha(hardware), "scope": "owned_named_health_route"}
    settings = {"samples": 2, "timeout_s": 1, "interval_s": 0}
    events = []
    def exchange(target, nonce, timeout):
        return {"request_sent": True, "error": None, "peer_certificate_base64": base64.b64encode(CERT).decode(),
            "response": {"status": 200, "headers": [["Content-Type", "application/json"]],
                         "body_base64": base64.b64encode(N.response_body(target, nonce)).decode()}}
    with patch.object(socket, "gethostname", return_value="unit-collector-host"):
        raw = N.acquire(expected, settings, N.sha(N.canonical(expected)), exchange=exchange, on_event=events.append)
    return hardware, expected, settings, raw, events


def closure(raw, expected, settings, events=None, *, collector_pin=None):
    sources = json.loads((D.ROOT / "SOURCES.json").read_text())
    producer_pin = next(item["sha256"] for item in sources["files"] if item["path"] == "owner_ocl/network_health.py")
    summary = N.verify(raw, expected, settings, producer_sha256=producer_pin)
    if events is None:
        events = []
        for row in raw["attempts"]:
            events.extend([{"event": "attempt_started", **{key: row[key] for key in
                ("index", "nonce", "started_at", "started_monotonic_s", "request")}},
                {"event": "attempt_completed", "attempt": row}])
    blobs = {"raw": N.canonical(raw), "summary": N.canonical(summary),
             "events": b"".join(N.canonical(row) + b"\n" for row in events)}
    packet = {"schema": "ocl.instrument-packet/1", "status": "collected",
        "provenance": {"source_sha256": collector_pin or sources["operational_collector"]["sha256"],
                       "network_module_sha256": producer_pin, "captured_at": raw["started_at"], "completed_at": raw["ended_at"]},
        "operations": {"owned_network": summary}, "files": [{"path": "network/" + filename,
            "sha256": N.sha(blobs[key]), "bytes": len(blobs[key])} for key, filename in
            (("raw", "raw.json"), ("summary", "summary.json"), ("events", "attempt-events.jsonl"))]}
    blobs["packet"] = N.canonical(packet)
    return blobs, summary


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.hardware, self.target, self.protocol, self.raw, self.events = fixture()

    def verify(self, raw=None, expected=None, settings=None):
        return N.verify(raw or self.raw, expected or self.target, settings or self.protocol,
                        producer_sha256=N.sha(Path(N.__file__).read_bytes()))

    def requirement(self, check="owned_network.failure_count"):
        return {"id": check, "check_id": check, "operator": "lte", "threshold": 0 if check.endswith("count") else 1000,
            "required": True, "max_age_s": 3600, "allowed_basis": ["observed"],
            "network_target": self.target, "network_protocol": self.protocol}

    def bound(self, raw=None, **kwargs):
        blobs, _ = closure(raw or self.raw, self.target, self.protocol, **kwargs)
        start = datetime.fromisoformat(self.raw["ended_at"].replace("Z", "+00:00")) + timedelta(seconds=10)
        run = {"declared_identity": {"hardware": self.hardware}, "started_at": start.isoformat(),
               "ended_at": (start + timedelta(seconds=10)).isoformat()}
        attachment = {"schema": "cantos.operation-binding/1", "check_id": "owned_network.failure_count", "basis": "observed",
            "binding": {"run_sha256": "a" * 64, "resource_identity_sha256": D.sha(self.hardware),
                "observed_window": {"start": self.raw["started_at"], "end": self.raw["ended_at"]}},
            **{key + "_base64": base64.b64encode(value).decode() for key, value in blobs.items()}}
        return run, attachment

    def gates(self, run, attachment, requirements=None):
        requirements = requirements or [self.requirement(), self.requirement("owned_network.latency_p95_ms")]
        other = {**attachment, "check_id": "owned_network.latency_p95_ms"}
        return D._operations(requirements, [attachment, other], run, "a" * 64)

    def test_complete_population_nonce_route_and_exact_identity(self):
        result = self.verify()
        self.assertEqual((result["attempts"], result["successes"], result["failure_count"]), (2, 2, 0))
        self.assertIsNotNone(result["latency_p95_ms"])
        self.assertNotEqual(self.raw["attempts"][0]["nonce"], self.raw["attempts"][1]["nonce"])
        self.assertEqual(len(self.events), 4)
        run, attachment = self.bound(events=self.events)
        self.assertEqual(self.gates(run, attachment)["status"], "pass")

    def test_missing_or_duplicated_attempts_and_changed_protocol_refused(self):
        for mode in ("missing", "duplicate", "changed-latency", "wrong-clock"):
            raw = copy.deepcopy(self.raw)
            if mode == "missing": raw["attempts"].pop()
            elif mode == "duplicate": raw["attempts"][1]["nonce"] = raw["attempts"][0]["nonce"]
            elif mode == "changed-latency": raw["attempts"][0]["latency_ms"] += 10
            else: raw["ended_monotonic_s"] += 100
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.verify(raw)
        with self.assertRaises(ValueError): self.verify(settings={**self.protocol, "samples": 3})

    def test_declared_inter_attempt_interval_is_verified_from_raw_clock(self):
        settings = {**self.protocol, "interval_s": 1}
        raw = copy.deepcopy(self.raw)
        raw["protocol"] = settings
        with self.assertRaisesRegex(ValueError, "cadence"):
            self.verify(raw, settings=settings)
        # A source-bound synthetic clock fixture with a genuine declared gap.
        # Do not sleep or contact an endpoint to test offline arithmetic.
        for key in ("started_monotonic_s", "ended_monotonic_s"):
            raw["attempts"][1][key] += 1
        for key in ("started_at", "ended_at"):
            raw["attempts"][1][key] = (N.date(raw["attempts"][1][key]) + timedelta(seconds=1)).isoformat()
        raw["ended_monotonic_s"] += 1
        raw["ended_at"] = (N.date(raw["ended_at"]) + timedelta(seconds=1)).isoformat()
        checked = self.verify(raw, settings=settings)
        self.assertEqual(checked["failure_count"], 0)

    def test_response_replay_wrong_instance_cert_redirect_body_fail_all_attempt_denominator(self):
        for mode in ("replay", "instance", "certificate", "redirect", "trailing-json", "duplicate-json"):
            raw = copy.deepcopy(self.raw)
            row = raw["attempts"][1]
            if mode == "replay": row["response"]["body_base64"] = raw["attempts"][0]["response"]["body_base64"]
            elif mode == "instance": row["response"]["body_base64"] = base64.b64encode(N.response_body({**self.target, "responder_instance_id": "foreign"}, row["nonce"])).decode()
            elif mode == "certificate": row["peer_certificate_base64"] = base64.b64encode(b"other cert").decode()
            elif mode == "redirect": row["response"]["status"] = 302
            else:
                body = base64.b64decode(row["response"]["body_base64"])
                body = body + b"{}" if mode == "trailing-json" else body[:-1] + b',"healthy":true}'
                row["response"]["body_base64"] = base64.b64encode(body).decode()
            result = self.verify(raw)
            self.assertEqual(result["attempts"], 2)
            self.assertEqual(result["failure_count"], 1)
            self.assertIsNone(result["latency_p95_ms"])
            run, attachment = self.bound(raw)
            gates = self.gates(run, attachment)
            self.assertEqual(gates["status"], "fail")
            self.assertEqual(gates["gates"][1]["status"], "unknown")

    def test_unknown_missing_source_tamper_stale_future_or_unbound_hardware_cannot_pass(self):
        for mode in ("tampered", "collector", "stale", "future", "missing-host", "target"):
            run, attachment = self.bound(collector_pin="0" * 64 if mode == "collector" else None)
            requirements = [self.requirement()]
            if mode == "tampered": attachment["raw_base64"] = base64.b64encode(b"{}").decode()
            elif mode == "stale": requirements[0]["max_age_s"] = 0
            elif mode == "future": run["ended_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            elif mode == "missing-host": run["declared_identity"]["hardware"] = {"id": "fixture-resource"}
            elif mode == "target": requirements = copy.deepcopy(requirements); requirements[0]["network_target"]["responder_instance_id"] = "62a970fe-2030-4b1f-a6a4-7ad2e1a119fb"
            with self.subTest(mode=mode): self.assertEqual(self.gates(run, attachment, requirements)["status"], "unknown")

    def test_explicit_exact_authorization_and_address_policy_before_transport(self):
        for data in (b'{"nested":{"overflow":1e309}}', b'{"value":NaN}', b'{"value":1,"value":2}', b'{}{}'):
            with self.assertRaises(ValueError): N.strict(data)
        with patch.object(N, "probe_one") as transport:
            with self.assertRaises(ValueError): N.acquire(self.target, self.protocol, "wrong")
            transport.assert_not_called()
        for url in ("http://192.0.2.2:19443/owned-health", "https://localhost:19443/owned-health",
                    "https://127.0.0.1:19443/owned-health", "https://192.0.2.2:443/owned-health",
                    "https://user:secret@192.0.2.2:19443/owned-health", "https://192.0.2.2:19443/owned-health?next=x"):
            with self.subTest(url=url), self.assertRaises(ValueError): N.target({**self.target, "url": url})

    def test_transport_checks_cert_before_get_and_does_not_follow_redirect(self):
        connection = Mock()
        raw, tls, context = Mock(), Mock(), Mock()
        context.wrap_socket.return_value = tls
        tls.getpeercert.return_value = b"wrong-cert"
        with patch.object(N.http.client, "HTTPConnection", return_value=connection) as connect, \
             patch.object(N.socket, "socket", return_value=raw), patch.object(N.ssl, "SSLContext", return_value=context):
            result = N.probe_one(self.target, "f" * 64, 1)
            connect.assert_called_once()
            self.assertEqual(connect.call_args.args, ("192.0.2.2", 19443))
            connection.putrequest.assert_not_called()
            raw.connect.assert_called_once_with(("192.0.2.2", 19443))
            context.wrap_socket.assert_called_once_with(raw, do_handshake_on_connect=False)
            self.assertFalse(result["request_sent"])
        connection = Mock()
        tls.getpeercert.return_value = CERT
        response = Mock(status=302)
        response.getheaders.return_value = [("Content-Type", "application/json"), ("Location", "https://foreign/")]
        response.read1.return_value = b""
        connection.getresponse.return_value = response
        with patch.object(N.http.client, "HTTPConnection", return_value=connection), \
             patch.object(N.socket, "socket", return_value=raw), patch.object(N.ssl, "SSLContext", return_value=context):
            result = N.probe_one(self.target, "f" * 64, 1)
            self.assertEqual(result["response"]["status"], 302)
            connection.putrequest.assert_called_once_with("GET", "/owned-health", skip_host=True, skip_accept_encoding=True)
            self.assertEqual(connection.auto_open, 0)

    def test_absolute_deadline_covers_tcp_tls_and_late_socket_ownership_race(self):
        for phase in ("tcp", "tls", "wrap-race"):
            stopped = threading.Event()
            raw, tls, context, connection = Mock(), Mock(), Mock(), Mock()
            raw.shutdown.side_effect = lambda *_: stopped.set()
            tls.shutdown.side_effect = lambda *_: stopped.set()
            context.wrap_socket.return_value = tls
            def blocked(*args, **kwargs):
                self.assertTrue(stopped.wait(.3), "Absolute watchdog did not close owned socket")
                raise OSError("synthetic deadline shutdown")
            if phase == "tcp": raw.connect.side_effect = blocked
            elif phase == "tls": tls.do_handshake.side_effect = blocked
            else:
                def wrapped_late(*args, **kwargs):
                    time.sleep(.04)
                    return tls
                context.wrap_socket.side_effect = wrapped_late
            with self.subTest(phase=phase), patch.object(N.socket, "socket", return_value=raw), \
                 patch.object(N.ssl, "SSLContext", return_value=context), \
                 patch.object(N.http.client, "HTTPConnection", return_value=connection):
                start = time.monotonic()
                result = N.probe_one(self.target, "f" * 64, .02)
                self.assertLess(time.monotonic() - start, .2)
                self.assertIsNotNone(result["error"])
                self.assertFalse(result["request_sent"])
                connection.putrequest.assert_not_called()
                raw.close.assert_called()
                if phase != "tcp": tls.close.assert_called()
                if phase == "wrap-race": tls.do_handshake.assert_not_called()

    def test_readiness_publication_is_atomic_new_and_never_replaces(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ready.json"
            N.publish_new(path, {"state": "ready"})
            original = path.read_bytes()
            with self.assertRaises(FileExistsError): N.publish_new(path, {"state": "foreign"})
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(temporary).iterdir()), [path])

    def test_finite_responder_handshake_and_header_deadlines_without_sockets(self):
        for phase in ("handshake", "headers"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                cert, key = root / "cert.pem", root / "key.pem"
                cert.write_text("unit fixture"); key.write_text("unit fixture")
                server, context, raw = Mock(), Mock(), Mock()
                server.get_request.return_value = (raw, ("192.0.2.1", 12345))
                handlers = []
                def construct(address, handler):
                    self.assertEqual(address, ("192.0.2.2", 19443))
                    handlers.append(handler)
                    return server
                stopped = threading.Event()
                connection = Mock()
                connection.shutdown.side_effect = lambda *_: stopped.set()
                def handle_request():
                    if phase == "handshake": server.get_request()
                    else:
                        handler = object.__new__(handlers[0]); handler.connection = connection
                        handler.handle()
                def slow_read(self):
                    self_test.assertTrue(stopped.wait(1.3), "Owner deadline did not stop header read")
                self_test = self
                server.handle_request.side_effect = handle_request
                context.wrap_socket.side_effect = TimeoutError("synthetic TLS timeout")
                with patch.object(N.socket, "gethostname", return_value="unit-responder-host"), \
                     patch.object(N.ssl, "PEM_cert_to_DER_cert", return_value=CERT), \
                     patch.object(N.ssl, "SSLContext", return_value=context), \
                     patch.object(N.http.server, "HTTPServer", side_effect=construct), \
                     patch.object(N.http.server.BaseHTTPRequestHandler, "handle", slow_read):
                    started = time.monotonic()
                    if phase == "handshake":
                        with self.assertRaises(TimeoutError):
                            N.serve(self.target, cert, key, N.sha(N.canonical(self.target)), max_seconds=1, ready_file=root / "ready.json")
                        raw.close.assert_called_once()
                        self.assertLessEqual(raw.settimeout.call_args.args[0], 1)
                    else:
                        N.serve(self.target, cert, key, N.sha(N.canonical(self.target)), max_seconds=1, ready_file=root / "ready.json")
                        connection.close.assert_called_once()
                    self.assertLess(time.monotonic() - started, 1.5)
                server.server_close.assert_called_once()
                self.assertEqual(N.strict((root / "ready.json").read_bytes())["state"], "ready")
                self.assertEqual(N.strict((root / "ready.json.terminal.json").read_bytes())["state"], "stopped")

    def test_packet_journal_missing_or_rehashed_summary_fails_offline(self):
        run, attachment = self.bound(events=self.events[:-1])
        self.assertEqual(self.gates(run, attachment)["status"], "unknown")
        run, attachment = self.bound()
        packet = N.strict(base64.b64decode(attachment["packet_base64"]))
        packet["operations"]["owned_network"]["failure_count"] = 123
        attachment["packet_base64"] = base64.b64encode(N.canonical(packet)).decode()
        self.assertEqual(self.gates(run, attachment)["status"], "unknown")

    def test_job_template_binds_exact_run_and_price_reanalysis_does_not_recollect(self):
        run, attachment = self.bound()
        template = {key: value for key, value in attachment.items() if key != "binding"}
        template["schema"] = "cantos.operation-template/1"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths, operation_paths = {}, {}
            template_path = root / "template.json"; template_path.write_bytes(N.canonical(template))
            for side in D.ARMS:
                paths[side] = root / (side + "-run.json"); paths[side].write_bytes(N.canonical(run))
                operation_paths[side] = [template_path]
            contract = {"decision": {"operational_requirements": [self.requirement()]}}
            ops, _, derived, _ = job._bind_job_evidence(contract, paths, {}, operation_paths, {}, root / "first")
            self.assertEqual(ops["baseline"][0]["binding"]["run_sha256"], N.sha(paths["baseline"].read_bytes()))
            self.assertEqual(ops["baseline"][0]["binding"]["resource_identity_sha256"], D.sha(self.hardware))
            retained_paths = {side: [template_path] + derived[side] for side in D.ARMS}
            with patch.object(N, "acquire", side_effect=AssertionError("No recollection")):
                child_ops, _, child_derived, _ = job._bind_job_evidence(contract, paths, {}, retained_paths, {}, root / "child")
            self.assertEqual(child_ops, ops)
            self.assertEqual(child_derived, {side: [] for side in D.ARMS})
            template["basis"] = "changed"
            template_path.write_bytes(N.canonical(template))
            with self.assertRaisesRegex(ValueError, "stale bound"):
                job._bind_job_evidence(contract, paths, {}, retained_paths, {}, root / "changed")

    def test_native_job_network_gate_child_and_data_only_import(self):
        # Reuse the owner's real streamed HTTP fixture and native validator.
        # Responses are authored synthetic SSE, never a model qualification.
        from compute.maintainer.tests.test_job import JobTests
        case = JobTests("test_manifest_paths_reject_traversal")
        case.setUp()
        self.addCleanup(case.tearDown)
        for side in D.ARMS:
            case.spec[side]["identity"]["hardware"] = copy.deepcopy(self.hardware)
            path = case.root / (side + "-resource-template.json")
            resource = json.loads(path.read_text())
            resource["resource_identity_sha256"] = D.sha(self.hardware)
            path.write_bytes(N.canonical(resource))
            case.manifest["arms"][side]["operations"] = ["network-template.json"]
        case.manifest["decision"]["operational_requirements"] = [self.requirement(), self.requirement("owned_network.latency_p95_ms")]
        case.root.joinpath("spec.json").write_bytes(N.canonical(case.spec))
        case.root.joinpath("deployment-job.json").write_bytes(N.canonical(case.manifest))
        _, attachment = self.bound()
        template = {key: value for key, value in attachment.items() if key != "binding"}
        template["schema"] = "cantos.operation-template/1"
        other = {**template, "check_id": "owned_network.latency_p95_ms"}
        case.root.joinpath("network-template.json").write_bytes(N.canonical([template, other]))
        with patch.object(N, "acquire", side_effect=AssertionError("No acquisition on run/import/child")):
            result = job.run_job(case.root / "deployment-job.json", case.root / "network-job")
            self.assertTrue(all(result["layers"]["operations"][side]["status"] == "pass" for side in D.ARMS))
            job.export_job(case.root / "network-job", case.root / "network-bundle")
            imported = job.import_job(case.root / "network-bundle", case.root / "network-import")
            self.assertEqual(imported["decision_identity"], result["decision_identity"])
            import shutil
            shutil.copytree(case.root / "network-job", case.root / "changed-target-source")
            manifest_path = case.root / "changed-target-source/job.json"
            changed = json.loads(manifest_path.read_text())
            for req in changed["decision"]["operational_requirements"]:
                req["network_target"]["responder_instance_id"] = "62a970fe-2030-4b1f-a6a4-7ad2e1a119fb"
            manifest_path.write_bytes(N.canonical(changed))
            child = job.decide_job(case.root / "changed-target-source", case.root / "network-child")
            self.assertTrue(child["post_hoc"])
            self.assertEqual(child["parent_id"], result["decision_identity"])
            self.assertNotEqual(child["decision_identity"], result["decision_identity"])
            self.assertTrue(all(child["layers"]["operations"][side]["status"] == "unknown" for side in D.ARMS))
            self.assertEqual(child["execution"], {"inference_requests": 0, "grader_executions": 0})
            job.export_job(case.root / "network-child", case.root / "network-child-bundle")
            imported_child = job.import_job(case.root / "network-child-bundle", case.root / "network-child-import")
            self.assertEqual(imported_child["decision_identity"], child["decision_identity"])
        self.assertEqual((case.a.requests, case.b.requests), (1, 1))

    def test_retained_approved_recovery_bundle_import_regression(self):
        bundle = os.environ.get("CANTOS_RETAINED_RECOVERY_BUNDLE")
        if not bundle:
            self.skipTest("Set CANTOS_RETAINED_RECOVERY_BUNDLE to the original approved data-only bundle for the retained-evidence regression")
        # The owner supplies existing evidence, never an invented replacement.
        # Exact prior native/decision identity must survive current analysis.
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(N, "acquire", side_effect=AssertionError("Retained import cannot acquire")):
            result = job.import_job(Path(bundle), Path(temporary) / "imported")
            self.assertEqual(result["execution"], {"inference_requests": 0, "grader_executions": 0})
            self.assertEqual(result["native_verdict"], "incomparable")
            for side in D.ARMS:
                recovery = [gate for gate in result["layers"]["operations"][side]["gates"]
                            if gate["check_id"].startswith("owned_loopback.recovery")]
                self.assertTrue(recovery, "Actual retained original recovery gates must be exercised")
                self.assertTrue(all(gate["status"] == "pass" for gate in recovery))


if __name__ == "__main__":
    unittest.main()
