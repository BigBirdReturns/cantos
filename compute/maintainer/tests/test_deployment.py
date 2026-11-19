"""Layered decision fixtures exercise semantics, never claim model or host success."""
import copy
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from compute.maintainer import deployment as D


def quantity(value, basis="modeled"):
    return {"value": value, "basis": basis, "source": "unit-fixture / explicit assumption", "source_sha256": "a" * 64}


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.job = {"schema": "cantos.deployment-job/1", "id": "fixture-deployment", "comparison": {},
                    "arms": {side: {} for side in D.ARMS}, "decision": {"objective": "min_cost_per_accepted", "economics_required": True, "operational_requirements": []}}
        self.run_data, self.paths = {}, {}
        for side in D.ARMS:
            self.run_data[side] = {"declared_identity": {"hardware": {"id": "fixture-" + side}},
                                   "started_at": "2026-11-18T01:00:00Z", "ended_at": "2026-11-18T02:00:00Z", "duration_s": 3600}
            self.paths[side] = self.root / (side + ".json")
            self.paths[side].write_text(json.dumps(self.run_data[side]))
        self.native = {"verdict": "pass", "policy": {"min_baseline_acceptance": .8, "min_candidate_acceptance": .8},
                       "baseline": {"accepted_tasks": 100, "total_tasks": 100, "acceptance_rate": 1},
                       "candidate": {"accepted_tasks": 100, "total_tasks": 100, "acceptance_rate": 1}, "reasons": []}
        self.resources = {side: self.resource(side, 10 if side == "baseline" else 5) for side in D.ARMS}

    def tearDown(self):
        self.tmp.cleanup()

    def binding(self, side):
        run = self.run_data[side]
        return {"run_sha256": D.sha(self.paths[side].read_bytes()),
                "resource_identity_sha256": D.sha(run["declared_identity"]["hardware"]),
                "observed_window": {"start": run["started_at"], "end": run["ended_at"]}}

    def resource(self, side, hosting):
        values = {"capex_usd": 0, "residual_usd": 0, "life_hours": 100, "utilization": 1,
                  "financing_usd_per_hour": 0, "hosting_usd_per_hour": hosting, "operations_usd_per_hour": 0,
                  "maintenance_usd_per_hour": 0, "network_usd_per_hour": 0, "electricity_usd_per_kwh": 0,
                  "pue": 1, "intervention_seconds": 0, "intervention_usd_per_hour": 0, "average_it_power_w": 0}
        return {"schema": "cantos.resource-binding/1", "binding": self.binding(side),
                "accounting": {"mode": "measured_trials", "window": self.binding(side)["observed_window"]},
                "scenario": {key: quantity(value) for key, value in values.items()},
                "additional_costs": [{**quantity(0), "category": category, "unit": "USD", "includes_in_scenario": False}
                                     for category in ("verification", "retry", "operator", "idle")]}

    def decide(self, native=None, resources=None, operations=None, parent=None):
        native = native or self.native
        # These are decision-join unit fixtures. Native stream/grade validation
        # remains covered separately by the real comparison/import suite.
        with patch.object(D, "_checked_native", return_value=(copy.deepcopy(native), copy.deepcopy(self.run_data))):
            return D.decide_deployment(self.job, native, self.paths, operations,
                                       self.resources if resources is None else resources, parent)

    def requirement(self):
        self.job["decision"]["operational_requirements"] = [{"id": "recovery", "check_id": "owned_loopback.recovery_max_s",
            "operator": "lte", "threshold": 2, "required": True, "max_age_s": 3600, "allowed_basis": ["observed"]}]

    def operations(self):
        return {side: [{"schema": "cantos.operation-binding/1", "check_id": "owned_loopback.recovery_max_s",
                        "basis": "observed", "binding": self.binding(side)}] for side in D.ARMS}

    def test_native_incomparable_cannot_rank_despite_apparent_cost_winner(self):
        native = copy.deepcopy(self.native)
        native["verdict"] = "incomparable"
        result = self.decide(native)
        self.assertEqual(result["state"], "INCOMPARABLE")
        self.assertEqual(result["native"], native)
        self.assertNotIn("winner", result)
        self.assertNotIn("ranked", result)
        self.assertEqual(result["layers"]["economics"]["candidate"]["cost_per_accepted_range"], [.05, .05])

    def test_required_unknown_is_not_a_pass_or_failure(self):
        self.requirement()
        result = self.decide()
        self.assertEqual(result["state"], "UNDETERMINED")
        self.assertEqual(result["layers"]["operations"]["candidate"]["gates"][0]["status"], "unknown")
        result = self.decide(resources={})
        self.assertTrue(any(u["layer"] == "economics" and u["required"] for u in result["unknowns"]))

    def test_self_declared_observed_pass_is_not_verified(self):
        self.requirement()
        operations = self.operations()
        for arm in operations.values():
            arm[0].update(claimed_value=0, verification="trusted", accepted=True)
        result = self.decide(operations=operations)
        self.assertEqual(result["state"], "UNDETERMINED")
        self.assertEqual(result["layers"]["operations"]["candidate"]["gates"][0]["status"], "unknown")

    def test_verified_gate_failure_changes_selection(self):
        self.requirement()
        operations = self.operations()
        # Isolate decision gating from the separately source-pinned raw verifier.
        def checked(attachment):
            candidate = attachment["binding"]["run_sha256"] == D.sha(self.paths["candidate"].read_bytes())
            return (3 if candidate else 1), {"verifier": "unit-fixture", "observed_window": attachment["binding"]["observed_window"]}
        with patch.object(D, "_operation_value", side_effect=checked):
            result = self.decide(operations=operations)
        self.assertEqual(result["state"], "KEEP-BASELINE")
        self.assertEqual(result["native_verdict"], "pass")
        with patch.object(D, "_operation_value", side_effect=lambda a: (3, {"verifier": "unit-fixture", "observed_window": a["binding"]["observed_window"]})):
            result = self.decide(operations=operations)
        self.assertEqual(result["state"], "NO-ELIGIBLE")

    def test_ranges_and_reversal_conditions(self):
        self.resources["candidate"]["scenario"]["hosting_usd_per_hour"] = {
            "range": [5, 15], "basis": "modeled", "source": "fixture range", "source_sha256": "b" * 64}
        result = self.decide()
        self.assertEqual(result["state"], "UNDETERMINED")
        self.assertEqual(result["layers"]["economics"]["candidate"]["cost_per_accepted_range"], [.05, .15])
        self.assertTrue(any("overlap" in condition for condition in result["reversal_conditions"]))

    def test_board_energy_does_not_become_whole_host(self):
        self.job["decision"]["objective"] = "min_energy_per_accepted"
        samples = json.dumps({"schema": "cantos.power-samples/1", "time_basis": "capture_monotonic_s",
                              "samples": [{"t_s": 100, "watts": 1}, {"t_s": 3700, "watts": 1}]}).encode()
        for side in D.ARMS:
            self.run_data[side]["trials"] = [{"started_monotonic_s": 100, "ended_monotonic_s": 3700, "duration_s": 3600}]
            self.resources[side]["energy"] = {"scope": "gpu_board", "basis": "observed", "max_gap_s": 3600,
                "source": "fixture board samples", "source_sha256": D.sha(samples), "allocation_fraction": 1,
                "samples_base64": __import__("base64").b64encode(samples).decode()}
        result = self.decide()
        self.assertEqual(result["state"], "UNDETERMINED")
        self.assertEqual(result["layers"]["economics"]["candidate"]["energy_per_accepted_range"], [36, 36])
        self.assertTrue(any(u["id"] == "whole_system_energy" for u in result["unknowns"]))

    def test_mixed_it_and_facility_boundaries_cannot_be_ranked(self):
        self.job["decision"]["objective"] = "min_energy_per_accepted"
        for side, scope, joules in (("baseline", "it_equipment", 100), ("candidate", "facility", 50)):
            self.resources[side]["energy"] = {"joules": joules, "scope": scope, "basis": "modeled",
                "source": "fixture scoped scenario", "source_sha256": "c" * 64, "allocation_fraction": 1}
        result = self.decide()
        self.assertEqual(result["state"], "UNDETERMINED")
        self.assertTrue(any(u["id"] == "energy_boundary_mismatch" for u in result["unknowns"]))

    def test_claimed_observed_joules_without_raw_are_unknown(self):
        self.resources["candidate"]["energy"] = {"joules": 50, "scope": "gpu_board", "basis": "observed",
            "source": "unverified claimed meter", "source_sha256": "c" * 64, "allocation_fraction": 1}
        result = self.decide()
        self.assertEqual(result["state"], "UNDETERMINED")
        self.assertIsNone(result["layers"]["economics"]["candidate"]["energy_per_accepted_range"])

    def test_required_unknown_preserves_native_quality_refusal(self):
        self.requirement()
        native = copy.deepcopy(self.native)
        native["verdict"] = "incomparable"
        native["baseline"].update(accepted_tasks=21, total_tasks=96, acceptance_rate=21/96)
        native["candidate"].update(accepted_tasks=21, total_tasks=96, acceptance_rate=21/96)
        result = self.decide(native, resources={})
        self.assertEqual(result["state"], "INCOMPARABLE")
        self.assertTrue(result["unknowns"])
        self.assertTrue(any("77" in condition for condition in result["reversal_conditions"]))

    def test_price_change_only_creates_child_and_keeps_observation_hashes(self):
        first = self.decide()
        self.assertEqual(first["state"], "SELECT-CANDIDATE")
        before = copy.deepcopy(first)
        self.resources["candidate"]["scenario"]["hosting_usd_per_hour"] = quantity(20)
        second = self.decide(parent=first)
        self.assertEqual(second["state"], "KEEP-BASELINE")
        self.assertTrue(second["post_hoc"])
        self.assertEqual(second["parent_id"], first["decision_identity"])
        self.assertEqual(second["dependencies"]["runs"], first["dependencies"]["runs"])
        self.assertEqual(first, before)

    def test_wrong_resource_and_stale_operations_are_unknown(self):
        self.requirement()
        operations = self.operations()
        operations["candidate"][0]["binding"]["resource_identity_sha256"] = "f" * 64
        with patch.object(D, "_operation_value", return_value=(1, {})):
            result = self.decide(operations=operations)
        self.assertEqual(result["state"], "UNDETERMINED")
        self.assertIn("different declared resource", result["layers"]["operations"]["candidate"]["gates"][0]["reason"])
        self.resources["candidate"]["binding"]["run_sha256"] = "e" * 64
        self.assertEqual(self.decide()["layers"]["economics"]["candidate"]["status"], "unknown")

    def test_missing_extra_costs_do_not_become_zero(self):
        self.resources["candidate"]["additional_costs"] = []
        result = self.decide()
        self.assertEqual(result["state"], "UNDETERMINED")
        self.assertIsNone(result["layers"]["economics"]["candidate"]["cost_per_accepted_range"])

    def test_retained_source_window_cannot_be_relabelled_as_current(self):
        self.requirement()
        operations = self.operations()
        old = {"start": "2026-11-17T01:00:00Z", "end": "2026-11-17T02:00:00Z"}
        with patch.object(D, "_operation_value", return_value=(1, {
                "observed_window": old, "window_rule": "exact_collector_window"})):
            result = self.decide(operations=operations)
        self.assertEqual(result["state"], "UNDETERMINED")
        self.assertIn("retained source timestamps", result["layers"]["operations"]["candidate"]["gates"][0]["reason"])

    def test_recovery_packet_binds_source_raw_summary_and_original_window(self):
        raw, summary = b'{"fixture":"raw"}', b'{"fixture":"summary"}'
        window = self.binding("baseline")["observed_window"]
        packet = {"schema": "ocl.instrument-packet/1",
            "provenance": {"source_sha256": "a" * 64, "captured_at": window["start"], "completed_at": window["end"]},
            "files": [{"path": path, "sha256": D.sha(data), "bytes": len(data)} for path, data in
                (("recovery/raw.json", raw), ("recovery/summary.json", summary))],
            "operations": {"service_recovery": json.loads(summary)}}
        attachment = {"check_id": "owned_loopback.recovery_max_s",
            "raw_base64": base64.b64encode(raw).decode(), "summary_base64": base64.b64encode(summary).decode()}
        def check():
            attachment["packet_base64"] = base64.b64encode(json.dumps(packet).encode()).decode()
            with patch.object(D, "load", return_value={"operational_collector": {"sha256": "a" * 64}}), \
                    patch.object(D.recovery_verifier, "verify", return_value={"injected_recovery_trials": [{"stop_to_recovered_s": 1}], "limits": []}):
                return D._operation_value(attachment)
        value, proof = check()
        self.assertEqual(value, 1)
        self.assertEqual(proof["observed_window"], window)
        packet["files"][0]["sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "does not bind"):
            check()
        packet["files"][0]["sha256"] = D.sha(raw)
        packet["provenance"]["source_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "pinned operational collector"):
            check()

    def test_empty_arm_defaults_have_one_identity(self):
        with patch.object(D, "_checked_native", return_value=(copy.deepcopy(self.native), copy.deepcopy(self.run_data))):
            omitted = D.decide_deployment(self.job, self.native, self.paths)
            explicit = D.decide_deployment(self.job, self.native, self.paths,
                {"baseline": [], "candidate": []}, {"baseline": None, "candidate": None})
        self.assertEqual(omitted["decision_identity"], explicit["decision_identity"])

    def test_posthoc_chain_preserves_original_and_required_unknown(self):
        first = self.decide()
        self.requirement()
        second = self.decide(parent=first)
        third = self.decide(parent=second)
        self.assertEqual(third["state"], "UNDETERMINED")
        self.assertTrue(third["post_hoc"])
        self.assertEqual(third["original_id"], first["decision_identity"])
        self.assertEqual(third["parent_id"], second["decision_identity"])

    def test_absent_retry_preserves_exact_output_and_identity(self):
        first = self.decide()
        with patch.object(D, "_checked_native", return_value=(copy.deepcopy(self.native), copy.deepcopy(self.run_data))), \
                patch.object(D.deployment_retry, "join") as joined:
            second = D.decide_deployment(self.job, self.native, self.paths, resources=self.resources, retry_evidence={})
        joined.assert_not_called()
        self.assertEqual(first, second)
        self.assertNotIn("retry", first["layers"])

    def test_optional_retry_cannot_repair_native_incomparable_or_required_unknown(self):
        self.job["retry"] = {"required": True, "economics": True}
        layer = {"status": "complete", "controls": self.job["retry"], "unknowns": [], "dependencies": {},
            "arms": {side: {"status": "complete", "window": self.binding(side)["observed_window"],
                "metrics": {"offered_tasks": 100, "accepted_tasks": 100},
                "allocations": {"cost_per_accepted_range": [.1, .1] if side == "baseline" else [.01, .01]}}
                for side in D.ARMS}}
        with patch.object(D.deployment_retry, "join", return_value=layer):
            native = copy.deepcopy(self.native)
            native["verdict"] = "incomparable"
            result = self.decide(native)
        self.assertEqual(result["state"], "INCOMPARABLE")
        self.assertEqual(result["native"], native)
        layer["status"] = "unknown"
        layer["unknowns"] = ["candidate: missing full-cost allocations"]
        with patch.object(D.deployment_retry, "join", return_value=layer):
            result = self.decide()
        self.assertEqual(result["state"], "UNDETERMINED")
        self.assertEqual(result["economic_population"], "retry_campaign")

    def test_retry_analyzer_provenance_does_not_change_identity_but_evidence_does(self):
        self.job["retry"] = {"required": False, "economics": False}
        def layer(source, campaign_hash="a" * 64):
            return {"status": "complete", "controls": self.job["retry"], "unknowns": [],
                "dependencies": {"baseline": {"campaign": campaign_hash}},
                "arms": {"baseline": {"resources": {"campaign": {"path": "retry-campaign.json", "sha256": campaign_hash},
                    "source_code": {"sha256": source, "producer_files": [{"path": "packets.py", "sha256": source}]}}}}}
        with patch.object(D.deployment_retry, "join", return_value=layer("b" * 64)):
            original = self.decide()
        with patch.object(D.deployment_retry, "join", return_value=layer("c" * 64)):
            relocated = self.decide()
        self.assertNotEqual(original["layers"]["retry"]["arms"]["baseline"]["resources"]["source_code"],
                            relocated["layers"]["retry"]["arms"]["baseline"]["resources"]["source_code"])
        self.assertEqual(original["decision_identity"], relocated["decision_identity"])
        with patch.object(D.deployment_retry, "join", return_value=layer("c" * 64, "d" * 64)):
            changed_evidence = self.decide()
        self.assertNotEqual(original["decision_identity"], changed_evidence["decision_identity"])


if __name__ == "__main__":
    unittest.main()
