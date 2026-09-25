"""Focused regressions from the stranger filing and retained-byte false pass.

Run: python -m unittest test_validator -v
Mutations use disposable copies under S:/Scratch/Temp on Windows. No retained
card, replay, evaluation or stranger output is modified.
"""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import validator


class ShelfValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = validator.load_cards(os.path.join(validator.HERE, "cards.jsonl"))
        cls.by_id = {card["id"]: card for card in cls.cards}

    def quiet(self, function, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = function(*args)
        return result, output.getvalue()

    def temporary(self):
        root = Path("S:/Scratch/Temp") if os.name == "nt" else Path(tempfile.gettempdir())
        self.assertTrue(root.is_dir(), "typed scratch location must already exist")
        return tempfile.TemporaryDirectory(prefix="shelf-validator-", dir=root)

    def test_current_cards_and_native_recomputation(self):
        for card in self.cards:
            self.assertEqual([], validator.validate_card(card), card["id"])
        counts = validator.recompute_retained_run()
        self.assertEqual({"scheduled": 8622, "completed": 8622, "accepted": 4336}, counts)

    def test_original_stranger_has_exact_three_filing_errors(self):
        path = Path(validator.HERE) / "stranger-2026-09-24/card6-latitude-h100.json"
        original = path.read_bytes()
        errors = validator.validate_card(json.loads(original))
        self.assertEqual(3, len(errors), errors)
        for field in ("publication_date_basis", "observer_benefit", "USD/GPU-hour"):
            self.assertTrue(any(field in error for error in errors), errors)
        self.assertEqual(original, path.read_bytes())

    def test_same_day_is_allowed_with_declared_publication_source(self):
        card = copy.deepcopy(self.by_id["clustermax-coreweave"])
        period = card["a_claim"]["period"]
        period["experiment_date"] = period["publication_date"]
        period["retrieved_at"] = period["publication_date"]
        self.assertTrue(period["publication_date_basis"])
        self.assertEqual([], validator.validate_card(card))
        period["publication_date_basis"] = None
        self.assertTrue(any("publication_date_basis" in e for e in validator.validate_card(card)))

    def test_unknowns_and_null_funding_are_valid(self):
        card = copy.deepcopy(self.by_id["inferencex-artifact"])
        card["c_parties"]["funding"] = None
        card["a_claim"]["results"]["unresolved_rate"] = {"value": None, "unit": None}
        self.assertEqual([], validator.validate_card(card))

    def test_boolean_dimension_and_benefit_are_not_integer_flags(self):
        for value in (0, 1):
            card = copy.deepcopy(self.by_id["run3-at0"])
            card["dimensions"]["measured"] = value
            card["c_parties"]["observer_benefit"]["benefits_from_outcome"] = value
            errors = validator.validate_card(card)
            self.assertTrue(any("dimension values" in error for error in errors))
            self.assertTrue(any("benefits_from_outcome" in error for error in errors))

    def test_hourly_aliases_and_seat_gpu_denominator(self):
        for alias in ("hourly_rate", "price", "new_rate"):
            card = copy.deepcopy(self.by_id["run3-at0"])
            card["a_claim"]["results"][alias] = {"value": 1.68, "unit": "USD/hour"}
            self.assertTrue(any(f"results.{alias}.unit" in e for e in validator.validate_card(card)))
        card = copy.deepcopy(self.by_id["run3-at0"])
        rate = card["a_claim"]["results"]["hotaisle_rate"]
        rate["unit"] = "USD / seat-hour"
        self.assertEqual([], validator.validate_card(card))
        card["a_claim"]["conditions"]["gpus"]["value"] = True
        self.assertTrue(any("GPU count" in e for e in validator.validate_card(card)))
        rate["value"] = True
        self.assertTrue(any("not a boolean" in e for e in validator.validate_card(card)))

    def test_altered_accepted_card_count_fails_real_recomputation(self):
        for value in (4335, True):
            cards = copy.deepcopy(self.cards)
            next(c for c in cards if c["id"] == "run3-at0")["b_population"]["accepted"]["value"] = value
            result, output = self.quiet(validator.check_recomputation, cards)
            self.assertFalse(result)
            self.assertIn("[FAIL   ] recomputation: accepted = 4336", output)

    def make_stale_summary(self, root):
        grade = root / "grade"
        grade.mkdir()
        shutil.copy2(Path(validator.A_T0) / "grade/buckets.json", grade / "buckets.json")

    def test_missing_journal_fails_even_with_passing_summary(self):
        with self.temporary() as temporary:
            root = Path(temporary)
            self.make_stale_summary(root)
            with patch.object(validator, "A_T0", str(root)):
                result, output = self.quiet(validator.check_recomputation, self.cards)
            self.assertFalse(result)
            self.assertIn("journal.jsonl is missing", output)
            self.assertIn("no summary fallback", output)

    def test_corrupt_journal_fails_native_recovery(self):
        with self.temporary() as temporary:
            root = Path(temporary)
            self.make_stale_summary(root)
            replay = root / "replay"
            replay.mkdir()
            original = Path(validator.A_T0) / "replay"
            shutil.copy2(original / "plan.json", replay / "plan.json")
            with (original / "journal.jsonl").open(encoding="utf-8") as f:
                row = json.loads(f.readline())
            row["task_id"] = "corrupt-task-identity"
            (replay / "journal.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
            with patch.object(validator, "A_T0", str(root)):
                result, output = self.quiet(validator.check_recomputation, self.cards)
            self.assertFalse(result)
            self.assertIn("Journal does not match frozen schedule", output)
            self.assertIn("no summary fallback", output)

    def test_six_refusals_require_their_actual_cards(self):
        result, output = self.quiet(validator.check_refusals, self.cards)
        self.assertTrue(result, output)
        self.assertEqual(6, output.count("[REFUSED]"))
        result, _ = self.quiet(validator.check_refusals, self.cards[:1])
        self.assertFalse(result)

    def test_unknown_dates_do_not_establish_same_period(self):
        card = copy.deepcopy(self.by_id["inferencex-artifact"])
        self.assertIn("unknown", validator.compose(card, card, "same_period"))

    def test_narrowing_requires_credit_provider_and_spine_disclosure(self):
        for funding, spine in (("provider credit", "Hot Aisle credit-funded"),
                                ("Hot Aisle", "Hot Aisle credit-funded"),
                                ("Hot Aisle credit", "Hot Aisle run")):
            cards = copy.deepcopy(self.cards)
            run = next(c for c in cards if c["id"] == "run3-at0")
            run["c_parties"]["funding"] = funding
            run["spine"] = spine
            result, _ = self.quiet(validator.check_narrowing, cards)
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
