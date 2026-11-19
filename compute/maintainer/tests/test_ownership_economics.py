"""Negative controls and algebra for honest reserved-capacity ownership economics."""
import copy
import json
import math
import unittest

from compute.maintainer.diagnose_grades import EvidenceError
from compute.maintainer.ownership_economics import audit
from compute.maintainer.tests import test_empirical_economics as empirical_fixture


class OwnershipEconomicsTests(unittest.TestCase):
    def setUp(self):
        empirical_fixture.EmpiricalEconomicsTests.setUp(self)

    def save_samples(self):
        empirical_fixture.EmpiricalEconomicsTests.save_samples(self)

    def save_receipt(self):
        empirical_fixture.EmpiricalEconomicsTests.save_receipt(self)

    def scenario_full(self):
        arm = {
            "hardware_usd": 9000, "service_life_calendar_hours": 17520,
            "utilization_fraction": .5, "availability_fraction": .8,
            "operations_usd_per_calendar_hour": .1,
            "network_storage_usd_per_active_hour": .02,
            "unmetered_active_watts_assumed": 60,
            "whole_host_idle_watts_assumed": 80,
        }
        return {
            "electricity_usd_per_kwh": .25,
            "it_to_facility_multiplier": 1.2,
            "acceptance_floor": .8,
            "verification_usd_per_attempt": .01,
            "recovery_usd_per_failed_attempt": .10,
            "operator_seconds_per_failed_attempt": 30,
            "operator_usd_per_hour": 36,
            "arms": {"baseline": dict(arm), "candidate": dict(arm)},
        }

    def test_replay_cost_includes_failures_idle_and_ownership(self):
        result = audit(self.root, self.scenario_full())
        a = result["arms"]["baseline"]
        self.assertEqual(a["observed"]["attempts"], 2)
        self.assertEqual(a["observed"]["accepted"], 1)
        self.assertEqual(a["observed"]["failed"], 1)
        self.assertAlmostEqual(a["modeled"]["reserved_calendar_hours"], 2.5 / 3600)
        self.assertAlmostEqual(a["modeled"]["idle_calendar_hours"], 1.5 / 3600)
        components = a["modeled"]["components_usd"]
        self.assertAlmostEqual(components["post_failure_recovery"], .1)
        self.assertAlmostEqual(components["post_failure_operator"], .3)
        self.assertAlmostEqual(components["verification"], .02)
        self.assertGreater(components["amortized_hardware"], 0)
        self.assertGreater(components["assumed_whole_host_idle_electricity"], 0)
        self.assertAlmostEqual(a["modeled"]["total_usd"], math.fsum(components.values()))
        self.assertEqual(result["comparison"]["decision"],
                         "hold_both_below_observed_acceptance_floor")
        self.assertEqual(result["comparison"]["candidate_minus_baseline_usd_per_accepted"], 0)

    def test_hardware_price_axis_and_parity(self):
        scenario = self.scenario_full()
        scenario["acceptance_floor"] = .4
        scenario["arms"]["candidate"]["hardware_usd"] = 11000
        result = audit(self.root, scenario)
        delta = result["comparison"]["candidate_minus_baseline_usd_per_accepted"]
        self.assertGreater(delta, 0)
        self.assertEqual(result["comparison"]["decision"],
                         "conditional_sample_price_baseline")
        self.assertAlmostEqual(
            result["comparison"]["candidate_hardware_usd_at_conditional_cost_parity"], 9000)
        self.assertAlmostEqual(delta, 2000 * 2.5 / 3600 / 17520)

    def test_price_change_reuses_pinned_source(self):
        scenario = self.scenario_full()
        first = audit(self.root, scenario)
        scenario["electricity_usd_per_kwh"] = .5
        second = audit(self.root, scenario)
        self.assertEqual(first["original_source_sha256"], second["original_source_sha256"])
        self.assertNotEqual(first["scenario_sha256"], second["scenario_sha256"])
        self.assertGreater(second["arms"]["baseline"]["modeled"]["total_usd"],
                           first["arms"]["baseline"]["modeled"]["total_usd"])

    def test_invalid_scenarios_rejected(self):
        edits = (
            ("utilization_fraction", 0), ("availability_fraction", 1.01),
            ("service_life_calendar_hours", 0), ("hardware_usd", -1),
            ("whole_host_idle_watts_assumed", float("nan")),
            ("unmetered_active_watts_assumed", float("inf")),
            ("operations_usd_per_calendar_hour", True),
        )
        for field, value in edits:
            with self.subTest(field=field):
                scenario = self.scenario_full()
                scenario["arms"]["baseline"][field] = value
                with self.assertRaises(EvidenceError):
                    audit(self.root, scenario)
        for field, value in (("it_to_facility_multiplier", .9),
                             ("acceptance_floor", 0),
                             ("electricity_usd_per_kwh", -1),
                             ("recovery_usd_per_failed_attempt", True)):
            with self.subTest(field=field):
                scenario = self.scenario_full()
                scenario[field] = value
                with self.assertRaises(EvidenceError):
                    audit(self.root, scenario)
        scenario = self.scenario_full()
        scenario["arms"]["candidate"].pop("hardware_usd")
        with self.assertRaises(EvidenceError):
            audit(self.root, scenario)

    def test_original_telemetry_tamper_rejected(self):
        scenario = self.scenario_full()
        self.samples[3]["watts"] += 90
        self.journal.write_text("".join(json.dumps(x) + "\n" for x in self.samples))
        with self.assertRaisesRegex(EvidenceError, "SHA-256"):
            audit(self.root, scenario)


if __name__ == "__main__":
    unittest.main()
