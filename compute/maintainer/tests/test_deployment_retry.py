"""Real local HTTP protocol fixtures, not model or GPU qualification."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import deployment_retry as R
import deployment as D
import maintainer
from common import load, policy, sha256_file
import test_retry as fixtures


class DeploymentRetryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RetryCampaign()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.native_runs, self.paths, self.evidence = {}, {}, {}
        for side in R.ARMS:
            native_dir = self.root / ("native-" + side)
            self.native_runs[side] = maintainer.observe(self.root / "spec.json", side, native_dir, "native-" + side)
            self.paths[side] = native_dir / "run.json"
            self.campaign(side)

    def campaign(self, side, suffix=""):
        root = self.root / ("retry-" + side + suffix)
        self.fixture.save()
        R.retry.run(self.root / "spec.json", side, self.root / "retry-policy.json", root, side + suffix)
        self.evidence[side] = {"campaign": root / "retry-campaign.json"}

    def joined(self, **kw):
        return R.join(self.native_runs, self.evidence, kw or {"required": True}, policy({}))

    def scenario(self, side):
        path = self.root / (side + "-cost.json")
        values = {key: 0 for key in R.retry_resources.SCENARIO_FIELDS}
        values.update(life_hours=100, utilization=1, pue=1, hosting_usd_per_hour=10)
        path.write_text(json.dumps({"schema": "cantos.retry.cost-scenario/1", "currency": "USD",
            "values": values, "field_sources": {key: "Explicit unit fixture assumption" for key in values}}))
        self.evidence[side]["scenario"] = path

    def allocations(self, side):
        path = self.root / (side + "-allocations.json")
        path.write_text(json.dumps({"schema": "cantos.retry.allocations/1",
            "campaign_sha256": sha256_file(self.evidence[side]["campaign"]),
            "additional_costs": [{"category": category, "value": 0, "unit": "USD", "basis": "modeled",
                "source": "Explicit fixture allocation", "source_sha256": "a" * 64,
                "rationale": "Fixture campaign scenario explicitly includes this category", "includes_in_scenario": True,
                "scenario_fields": ["hosting_usd_per_hour"]} for category in ("verification", "retry", "operator", "idle")]}))
        self.evidence[side]["allocations"] = path

    def telemetry(self, side):
        campaign = load(self.evidence[side]["campaign"])
        root = self.evidence[side]["campaign"].parent
        start, end = campaign["started_monotonic_s"], campaign["ended_monotonic_s"]
        journal = root / "power.jsonl"
        head = {"kind": "sampler_started", "clock_identity": campaign["clock_identity"],
                "devices": ["fixture-board"], "max_gap_s": 600, "producer": {"sha256": "a" * 64}}
        rows = [head] + [{"kind": "power_sample", "t_s": time, "readings": [{"device_uuid": "fixture-board", "watts": 10}]}
                         for time in (start - .01, end + .01)] + [{"kind": "sampler_ended"}]
        journal.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        path = root / "telemetry.json"
        path.write_text(json.dumps({"schema": "cantos.retry.telemetry/1", "campaign_sha256": sha256_file(self.evidence[side]["campaign"]),
            "observation_id": campaign["observation_id"], "clock_identity": campaign["clock_identity"],
            "devices": head["devices"], "max_gap_s": 600, "producer": head["producer"],
            "samples": {"path": journal.name, "sha256": sha256_file(journal), "bytes": journal.stat().st_size},
            "evidence_class": "synthetic accounting fixture"}))
        self.evidence[side]["telemetry"] = path
        return path, journal

    def test_complete_campaign_costs_have_separate_denominator_and_window(self):
        for side in R.ARMS:
            self.scenario(side)
            self.allocations(side)
        result = self.joined(economics=True)
        self.assertEqual(result["status"], "complete")
        facts = result["arms"]["baseline"]
        costs = facts["resources"]["economics"]
        self.assertEqual(facts["denominator"], "retry_campaign_accepted_tasks")
        self.assertEqual(costs["accepted_tasks"], facts["metrics"]["accepted_tasks"])
        self.assertAlmostEqual(costs["total_usd"], facts["resources"]["campaign_duration_s"] * 10 / 3600)
        self.assertAlmostEqual(facts["allocations"]["cost_per_accepted_range"][0], costs["total_usd"])
        self.assertIn("not added", result["accounting"])

    def test_missing_full_cost_allocations_never_become_zero(self):
        for side in R.ARMS:
            self.scenario(side)
        result = self.joined(economics=True)
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(any("verification/retry/operator/idle" in reason for reason in result["unknowns"]))
        self.allocations("baseline")
        path = self.evidence["baseline"]["allocations"]
        data = load(path)
        data["campaign_sha256"] = "f" * 64
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "different campaign"):
            self.joined(economics=True)

    def test_campaign_and_nested_raw_tampering_are_rejected(self):
        path = self.evidence["baseline"]["campaign"]
        campaign = load(path)
        campaign["metrics"]["accepted_tasks"] = 999
        original = path.read_bytes()
        path.write_text(json.dumps(campaign))
        with self.assertRaisesRegex(ValueError, "summary"):
            self.joined()
        path.write_bytes(original)
        raw = next((path.parent / "attempts").rglob("raw/**/*.json"))
        raw.write_text("{}")
        with self.assertRaises(ValueError):
            self.joined()

    def test_native_identity_and_paired_policy_mismatch(self):
        changed = copy.deepcopy(self.native_runs)
        changed["baseline"]["observation_identity"]["configuration"]["model"] = "another-model"
        with self.assertRaisesRegex(ValueError, "configuration"):
            R.join(changed, self.evidence)
        self.fixture.rp["max_attempts"] += 1
        self.campaign("candidate", "-different-policy")
        result = self.joined()
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(any("retry_policy differs" in reason for reason in result["unknowns"]))

    def test_telemetry_campaign_clock_and_raw_hash_are_validated(self):
        path, journal = self.telemetry("baseline")
        self.assertEqual(self.joined()["status"], "complete")
        original = path.read_bytes()
        value = load(path)
        value["clock_identity"] = {"fixture": "wrong"}
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "clock"):
            self.joined()
        path.write_bytes(original)
        journal.write_text("changed")
        with self.assertRaisesRegex(ValueError, "missing or changed"):
            self.joined()

    def test_unresolved_campaign_cannot_get_resource_ratios(self):
        real_validate = R.retry.validate_campaign
        def unresolved(path):
            value = real_validate(path)
            value["status"] = "unresolved"
            value["metrics"]["unresolved_tasks"] = 1
            return value
        self.scenario("baseline")
        with patch.object(R.retry, "validate_campaign", side_effect=unresolved), patch.object(R.retry_resources, "summarize") as summarize:
            result = self.joined(economics=True)
        summarize.assert_not_called()
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["arms"]["baseline"]["resources"])

    def test_failed_attempts_do_not_become_accepted_work(self):
        self.fixture.endpoint.mode = "wrong"
        self.campaign("candidate", "-failed")
        result = self.joined()
        metrics = result["arms"]["candidate"]["metrics"]
        self.assertEqual(metrics["accepted_tasks"], 0)
        self.assertEqual(metrics["total_task_attempts"], 3)
        self.assertEqual(metrics["retries_total"], 2)


if __name__ == "__main__":
    unittest.main()
