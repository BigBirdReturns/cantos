"""Offline buyer-placement regressions. Two-tier examples are synthetic mechanics."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import tier_waterline as owner


class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="buyer-placement-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.knot = {"knot_id": "synthetic-buyer", "task_class": "synthetic",
                     "count": 10, "deadline_s": 10, "policy": {"max_usd": 1},
                     "evaluator": {"needs_seat_role": "grader"},
                     "tierbench": {"task_classes": ["synthetic"]}}
        self.seats = {"synthetic-grader": {"roles": ["grader"]}}
        self.summary = {"schema": "second-run/tierbench-summary@1", "classes": {
            "synthetic": {"n_tasks": 1, "tasks": {"example": {"tiers": {
                "cheap-slow": {"status": "sufficient", "pass_rate": 1,
                               "cost_per_trial_usd": .01, "latency_ms_median": 2000,
                               "cost_per_trial_basis": "SYNTHETIC"},
                "dearer-fast": {"status": "sufficient", "pass_rate": 1,
                                "cost_per_trial_usd": .02, "latency_ms_median": 500,
                                "cost_per_trial_basis": "SYNTHETIC"}}}}}}}
        self.ladder = {"schema": "second-run/tier-ladder@1", "tiers": {
            "cheap-slow": {"rank": 0, "seat_kind": "api"},
            "dearer-fast": {"rank": 1, "seat_kind": "api"}}}

    def run_plan(self):
        for name, value in (("tierbench-summary.json", self.summary), ("tier-ladder.json", self.ladder)):
            (self.base / name).write_text(json.dumps(value), encoding="utf-8")
        return owner.plan(self.knot, str(self.base), self.seats, [], {"tiers": {}})

    def trial(self, tier="dearer-fast"):
        return self.summary["classes"]["synthetic"]["tasks"]["example"]["tiers"][tier]

    def test_selects_feasible_tier_without_changing_evidence_choice(self):
        original = copy.deepcopy((self.knot, self.summary, self.seats))
        p = self.run_plan()
        self.assertEqual(p["chosen_tier"], "cheap-slow")
        self.assertEqual(p["placement"]["chosen_tier"], "dearer-fast")
        self.assertEqual(p["grid"][0]["placement"]["status"], "refused")
        self.assertFalse(p["placement"]["execution_authorized"])
        self.assertEqual(original, (self.knot, self.summary, self.seats))
        self.assertIn("PLACEMENT: modeled-feasible", owner.render(p))
        self.assertIn("PLACEMENT tier dearer-fast", owner.render(p))
        self.assertEqual(p["plans"]["placement"]["plan"]["wall_s"], 5)

    def test_concurrency_and_exact_budget_boundary(self):
        self.knot["policy"].update(api_concurrency=2, max_usd=.1)
        p = self.run_plan()
        self.assertEqual(p["placement"]["chosen_tier"], "cheap-slow")
        self.assertEqual(p["grid"][1]["placement"]["status"], "refused")
        self.knot["policy"]["max_usd"] = 0
        self.assertIsNone(self.run_plan()["placement"]["chosen_tier"])

    def test_display_rounding_does_not_hide_deadline_or_budget_failure(self):
        self.trial().update(latency_ms_median=1000.001, cost_per_trial_usd=.100001)
        p = self.run_plan()
        r = p["grid"][1]
        self.assertEqual(r["plan"]["wall_s"], 10.0)
        self.assertEqual(r["plan"]["usd"], 1.0)
        self.assertEqual(len(r["placement"]["failures"]), 2)
        self.assertIsNone(p["placement"]["chosen_tier"])

    def test_unknown_cost_or_latency_is_unresolved(self):
        for field in ("cost_per_trial_usd", "latency_ms_median"):
            with self.subTest(field=field):
                original = self.trial()[field]
                self.trial()[field] = None
                p = self.run_plan()
                self.assertEqual(p["grid"][1]["placement"]["status"], "unresolved")
                self.assertIsNone(p["placement"]["chosen_tier"])
                self.trial()[field] = original

    def test_partial_coverage_cannot_become_placement(self):
        self.summary["classes"]["synthetic"]["n_tasks"] = 2
        p = self.run_plan()
        self.assertEqual(p["chosen_mode"], "partial")
        self.assertIsNone(p["placement"]["chosen_tier"])

    def test_missing_evaluator_role_refuses_every_candidate(self):
        self.seats = {}
        p = self.run_plan()
        self.assertIsNone(p["placement"]["chosen_tier"])
        self.assertTrue(all("evaluator role" in " ".join(r["placement"]["failures"]) for r in p["grid"]))

    def test_unregistered_sufficient_tier_is_unresolved(self):
        self.ladder["tiers"]["dearer-fast"]["seat_kind"] = "local"
        p = self.run_plan()
        self.assertIsNone(p["placement"]["chosen_tier"])
        self.assertIn("local_models.json", " ".join(p["grid"][1]["placement"]["unresolved"]))

    def test_bad_constraints_are_input_errors(self):
        for key, values in (("api_concurrency", [0, -1, True, 1.5, None]),
                            ("max_usd", [-1, True, float("nan"), float("inf"), None])):
            for value in values:
                with self.subTest(key=key, value=value):
                    self.knot["policy"] = {key: value}
                    with self.assertRaises(ValueError):
                        self.run_plan()
        for value in (0, -1, True, float("nan")):
            self.knot["deadline_s"] = value
            with self.assertRaises(ValueError):
                self.run_plan()

    def test_native_fabric_refusal_and_unmeasured_timing_survive(self):
        verdict = {"status": "sufficient", "covers_all_classes": True, "class_tasks": 1, "measured_tasks": 1}
        p = {"kind": "fabric", "refused": True, "refusal_reasons": ["native refusal"]}
        self.assertEqual(owner.placement_for({"plan": p}, verdict, self.knot)["status"], "refused")
        p.update(refused=False, grader_seats=["synthetic-grader"], plans_measured=False,
                 plans={"cheapest": {"wall_s": 5, "usd": .1}})
        self.assertEqual(owner.placement_for({"plan": p}, verdict, self.knot)["status"], "unresolved")
        p["plans_measured"] = True
        self.assertEqual(owner.placement_for({"plan": p}, verdict, self.knot)["status"], "modeled-feasible")
        # Native budget checks precede rounding: an accepted $0.099999 can
        # display as $0.1000 against a $0.0999995 budget. Preserve its verdict.
        self.knot["policy"]["max_usd"] = .0999995
        self.assertEqual(owner.placement_for({"plan": p}, verdict, self.knot)["status"], "modeled-feasible")

    def test_cli_requires_placement_only_when_requested(self):
        self.knot["policy"]["max_usd"] = 0
        self.run_plan()
        for name, value in (("knot.json", self.knot), ("seats.json", {"seats": self.seats}), ("models.json", {"tiers": {}})):
            (self.base / name).write_text(json.dumps(value), encoding="utf-8")
        (self.base / "availability.jsonl").write_text("", encoding="utf-8")
        cmd = [sys.executable, "-B", owner.__file__, "plan", str(self.base / "knot.json"),
               "--evidence", str(self.base), "--seats", str(self.base / "seats.json"),
               "--availability", str(self.base / "availability.jsonl"), "--local-models", str(self.base / "models.json")]
        self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        checked = subprocess.run(cmd + ["--require-placement"], capture_output=True, text=True)
        self.assertEqual(checked.returncode, 2, checked.stdout + checked.stderr)
        self.assertIn("no-modeled-feasible-placement", checked.stdout)


if __name__ == "__main__":
    unittest.main()
