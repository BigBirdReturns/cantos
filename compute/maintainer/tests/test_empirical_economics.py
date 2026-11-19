"""Negative controls for source-bound board energy and graded economic scenarios."""
from __future__ import annotations

import json
import math
import unittest

from compute.maintainer.diagnose_grades import EvidenceError, sha256
from compute.maintainer.empirical_economics import audit
from compute.maintainer.tests import test_diagnose_grades as fixture


class EmpiricalEconomicsTests(unittest.TestCase):
    def setUp(self):
        # Existing fully source-bound two-arm external grading fixture.
        fixture.CodingDiagnosisTests.setUp(self)
        self.journal = self.root / "vllm-serving/board-samples.jsonl"
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        self.samples = [{"monotonic_s": i, "watts": 100.0, "uuid": "GPU-test"}
                        for i in range(6)]
        self.save_samples()
        for arm, start in (("baseline", 1), ("candidate", 3)):
            run_name = f"vllm-capture/{arm}/run.json"
            grade_name = f"grade-{arm}/grades.json"
            run_file = self.root / run_name
            grade_file = self.root / grade_name
            run = json.loads(run_file.read_text())
            run["trials"] = [{"trial": 0, "started_monotonic_s": start,
                              "ended_monotonic_s": start + 1, "duration_s": 1}]
            fixture.write_json(run_file, run)
            grade = json.loads(grade_file.read_text())
            grade["run_sha256"] = sha256(run_file)
            fixture.write_json(grade_file, grade)
            self.receipt["sources"][run_name] = sha256(run_file)
            self.receipt["sources"][grade_name] = sha256(grade_file)
            self.receipt.setdefault("arms", {})[arm] = {
                "accepted": 1, "tasks": 2, "acceptance_rate": .5,
                "board_joules": 100, "board_wh": 100 / 3600,
                "joules_per_accepted": 100,
                "per_trial": [{"trial": 0, "accepted": 1, "tasks": 2,
                               "board_joules": 100, "board_wh": 100 / 3600,
                               "duration_s": 1, "joules_per_accepted": 100}],
            }
        self.receipt["max_telemetry_gap_s"] = 1.0
        self.save_receipt()

    def save_receipt(self):
        fixture.write_json(self.root / "VLLM-EMPIRICAL-RECEIPT.json", self.receipt)

    def save_samples(self):
        self.journal.write_text("".join(json.dumps(x) + "\n" for x in self.samples), encoding="utf-8")
        self.receipt["sources"]["vllm-serving/board-samples.jsonl"] = sha256(self.journal)

    def scenario(self):
        return {
            "electricity_usd_per_kwh": .2,
            "it_to_facility_multiplier": 1.3,
            "fixed_usd_per_hour": 3.6,
            "verification_usd_per_attempt": .05,
            "intervention_seconds_per_attempt": 60,
            "intervention_usd_per_hour": 36,
        }

    def test_recomputed_energy_and_accepted_work_are_source_bound(self):
        result = audit(self.root)
        self.assertIsNone(result["scenario"])
        self.assertEqual(result["observed"]["arms"]["baseline"]["board_joules"], 100)
        self.assertEqual(result["observed"]["arms"]["candidate"]["board_joules_per_accepted"], 100)
        self.assertEqual(result["observed"]["arms"]["baseline"]["accepted"], 1)
        self.assertNotIn("return True", json.dumps(result))

    def test_receipt_energy_promotion_rejected(self):
        self.receipt["arms"]["baseline"]["board_joules"] = 1
        self.save_receipt()
        with self.assertRaisesRegex(EvidenceError, "board joules"):
            audit(self.root)

    def test_source_telemetry_change_rejected(self):
        self.samples[2]["watts"] = 500
        self.journal.write_text("".join(json.dumps(x) + "\n" for x in self.samples))
        with self.assertRaisesRegex(EvidenceError, "SHA-256"):
            audit(self.root)

    def test_mixed_gpu_identity_rejected_even_with_updated_hash(self):
        self.samples[-1]["uuid"] = "GPU-other"
        self.save_samples()
        self.save_receipt()
        with self.assertRaisesRegex(EvidenceError, "mixed GPU"):
            audit(self.root)

    def test_missing_bracket_rejected_even_with_updated_hash(self):
        self.samples = self.samples[:-2]
        self.save_samples()
        self.save_receipt()
        with self.assertRaisesRegex(EvidenceError, "bracket"):
            audit(self.root)

    def test_fabricated_grade_acceptance_denominator_rejected(self):
        self.receipt["arms"]["candidate"]["accepted"] = 2
        self.save_receipt()
        with self.assertRaisesRegex(EvidenceError, "accepted"):
            audit(self.root)

    def test_requires_finite_declared_assumptions(self):
        for mutation in [{"electricity_usd_per_kwh": -1},
                         {"it_to_facility_multiplier": 0.5},
                         {"intervention_usd_per_hour": float("nan")},
                         {"extra": 1}]:
            scenario = {**self.scenario(), **mutation}
            with self.subTest(mutation=mutation), self.assertRaises(EvidenceError):
                audit(self.root, scenario)

    def test_price_axis_sensitivity_from_pinned_board_evidence(self):
        # Candidate power changes only within its captured trial window.
        self.samples[3]["watts"] = 130.0
        self.samples[4]["watts"] = 130.0
        self.save_samples()
        cand = self.receipt["arms"]["candidate"]
        cand["board_joules"] = 130.0
        cand["board_wh"] = 130.0 / 3600
        cand["joules_per_accepted"] = 130.0
        cand["per_trial"][0].update({
            "board_joules": 130.0,
            "board_wh": 130.0 / 3600,
            "joules_per_accepted": 130.0,
        })
        self.save_receipt()
        assumptions = self.scenario()
        result = audit(self.root, assumptions)
        effect = result["sensitivity"]
        self.assertEqual(effect["status"], "conditional_price_axis_sensitivity")
        electricity = effect["axes"]["electricity_usd_per_kwh"]
        self.assertAlmostEqual(electricity["gap_slope_usd_per_accepted_per_unit"],
                               30.0 / 3_600_000 * 1.3)
        self.assertAlmostEqual(electricity["zero_gap_assumption"], 0.0)
        self.assertEqual(electricity["status"], "conditional_in_domain_crossing")
        self.assertEqual(effect["axes"]["verification_usd_per_attempt"]["status"],
                         "gap_invariant_on_axis")
        changed = {**assumptions, "electricity_usd_per_kwh": 0.4}
        revised = audit(self.root, changed)
        self.assertEqual(result["source_sha256"], revised["source_sha256"])
        self.assertAlmostEqual(revised["sensitivity"]["candidate_minus_baseline_usd_per_accepted"],
                               2 * effect["candidate_minus_baseline_usd_per_accepted"])

    def test_sensitivity_undefined_without_accepted_tasks(self):
        from compute.maintainer.empirical_economics import scenario_sensitivity
        arms = {"baseline": {"accepted": 0},
                "candidate": {"accepted": 1}}
        self.assertEqual(scenario_sensitivity(arms, self.scenario())["status"],
                         "undefined_without_accepted_work")

    def test_scenario_reuses_observations_without_promoting_to_invoices(self):
        a, b = self.scenario(), self.scenario()
        b["electricity_usd_per_kwh"] = .4
        left = audit(self.root, a)
        right = audit(self.root, b)
        self.assertEqual(left["source_sha256"], right["source_sha256"])
        observed = left["observed"]["arms"]["baseline"]
        self.assertEqual(observed["board_joules"], right["observed"]["arms"]["baseline"]["board_joules"])
        expected = (100 / 3_600_000 * .2 * 1.3 + 1 / 3600 * 3.6 + 2 * .05 + 2 * 60 / 3600 * 36)
        self.assertAlmostEqual(observed["scenario_usd"]["total_modeled"], expected)
        self.assertGreater(right["observed"]["arms"]["baseline"]["scenario_usd"]["total_modeled"], expected)
        self.assertIn("never observed invoices", " ".join(left["limits"]))


if __name__ == "__main__":
    unittest.main()
