"""Minimized filing/query failures and deterministic native-engine differentials."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest


TOOL = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("generated_shelf", TOOL / "scripts/shelf.py")
shelf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shelf)
SKELETON = json.loads((TOOL / "card.skeleton.json").read_bytes())
FIXTURE = json.loads((TOOL / "tests/fixtures/generated-regressions.json").read_bytes())


def baseline():
    card = copy.deepcopy(SKELETON)
    card["a_claim"]["period"]["experiment_date"] = "2026-09-24"
    card["a_claim"]["results"]["example_result"]["value"] = 1
    card["dimensions"]["measured"] = True
    return card


def mutate(case):
    card = baseline()
    target = card
    for key in case["path"][:-1]:
        target = target[key]
    if case.get("delete"):
        target.pop(case["path"][-1], None)
    else:
        target[case["path"][-1]] = copy.deepcopy(case["value"])
    return card


NODE = r"""
const fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync(process.argv[1],'utf8');
vm.runInThisContext(html.match(/<script id="shelf-engine">([\s\S]*?)<\/script>/)[1]);
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const values=input.cards.map(card=>({
  errors:Shelf.validateCard(card),
  which:Shelf.which([card],'USD / GPU-hour','2026-09',false),
  compose:Shelf.compose(card,input.base,'cost_per_accepted'),
  date:Shelf.observationDate(card)
}));
process.stdout.write(JSON.stringify(values));
"""


class GeneratedRegressions(unittest.TestCase):
    def test_minimized_failures_refuse_without_exceptions(self):
        for case in FIXTURE["cases"]:
            with self.subTest(case=case["name"]):
                card = mutate(case)
                self.assertTrue(any(case["error"] in e for e in shelf.validate_card(card)))
                row = shelf.which([card], "USD / GPU-hour", "2026-09")[0]
                self.assertEqual("CANNOT_USE", row["status"])
                self.assertTrue(row["reason"].startswith("invalid filing:"))
                self.assertTrue(shelf.compose(card, baseline(), "cost_per_accepted").startswith("invalid filing:"))

    def test_native_engines_agree_on_malformed_structures(self):
        cards = [baseline(), copy.deepcopy(SKELETON)] + [mutate(c) for c in FIXTURE["cases"]]
        scalars = [None, False, True, 0, 1, "", "not an object", [], [1]]
        cards += copy.deepcopy(scalars)
        for section in ("a_claim", "b_population", "c_parties", "d_materials", "e_checks"):
            for value in scalars:
                card = baseline()
                card[section] = copy.deepcopy(value)
                cards.append(card)
        for char in ("\u001c", "\u001d", "\u001e", "\u001f", "\u0085", "\ufeff"):
            for kind in ("unit", "title", "date", "check"):
                card = baseline()
                if kind == "unit":
                    card["a_claim"]["results"]["example_result"]["unit"] = "USD" + char + "/GPU-hour"
                elif kind == "title":
                    card["title"] = char
                elif kind == "date":
                    card["a_claim"]["period"]["experiment_date"] = char + "2026-09-24" + char
                else:
                    card["e_checks"]["inspected"]["who"] = char
                cards.append(card)
        integer_card = baseline()
        integer_card["filing_version"] = 2.0
        cards.append(integer_card)
        unusual_key = baseline()
        unusual_key["a_claim"]["results"]["__proto__"] = unusual_key["a_claim"]["results"].pop("example_result")
        cards.append(unusual_key)
        expected = [{"errors": shelf.validate_card(c),
                     "which": shelf.which([c], "USD / GPU-hour", "2026-09", False),
                     "compose": shelf.compose(c, baseline(), "cost_per_accepted"),
                     "date": shelf.observation_date(c)} for c in cards]
        completed = subprocess.run(["node", "-e", NODE, str(TOOL / "index.html")],
            input=json.dumps({"cards": cards, "base": baseline()}), text=True,
            encoding="utf-8", capture_output=True, check=True)
        self.assertEqual(expected, json.loads(completed.stdout))

    def test_unknown_values_and_invalid_question_never_support(self):
        self.assertEqual("CANNOT_USE", shelf.which([SKELETON], "USD / GPU-hour")[0]["status"])
        for asked in ("", "2", "2026\n", "2026-13", "2026-02-30", "2026-10-01..2026-09-01", [], 2026):
            with self.subTest(period=asked):
                self.assertFalse(shelf.in_period("2026-09-24", asked))
                self.assertEqual("CANNOT_USE", shelf.which([baseline()], "USD / GPU-hour", asked)[0]["status"])
        for unit in (None, [], 42, ""):
            self.assertEqual("CANNOT_USE", shelf.which([baseline()], unit)[0]["status"])

    def test_shared_whitespace_alphabet(self):
        for char in ("\u0085", "\ufeff", "\u00a0", " ", "\t"):
            self.assertEqual("usd/gpu-hour", shelf.normalized_unit("USD" + char + "/GPU-hour"))
        for char in ("\u001c", "\u001d", "\u001e", "\u001f"):
            self.assertEqual("usd" + char + "/gpu-hour", shelf.normalized_unit("USD" + char + "/GPU-hour"))

    def test_date_precision_is_not_invented_or_backfilled(self):
        for value in ("2026", "2026-09", "2026-02-30", "2026-09-24T25:00:00Z"):
            card = baseline()
            card["a_claim"]["period"].update(experiment_date=value,
                publication_date="2026-09-24", publication_date_basis="retained source")
            self.assertIsNone(shelf.observation_date(card))
        self.assertEqual("2024-02-29", shelf.calendar_date("2024-02-29T23:59:59.125+01:00"))
        self.assertIsNone(shelf.calendar_date("2026-09-24T12:00:00+01:60"))

    def test_duplicate_ids_refuse_locally_without_poisoning_other_cards(self):
        one, duplicate, other = baseline(), baseline(), baseline()
        other["id"] = "independent-card"
        errors = shelf.validate_cards([one, duplicate, other])
        self.assertEqual([["id must be unique on a shelf"], ["id must be unique on a shelf"], []], errors)
        rows = shelf.which([one, duplicate, other], "USD / GPU-hour")
        self.assertEqual(["CANNOT_USE", "CANNOT_USE", "SUPPORTS"], [r["status"] for r in rows])

    def test_exact_accepted_units_and_directional_purposes(self):
        good = baseline()
        good["a_claim"]["results"]["example_result"]["unit"] = "USD / 1000 accepted requests"
        for unit in ("unaccepted requests", "accepted bananas", "USD / 1000 unknown accepted things"):
            bad = copy.deepcopy(good)
            bad["a_claim"]["results"]["example_result"]["unit"] = unit
            self.assertIsNotNone(shelf.compose(good, bad, "accepted_work"))
            self.assertIsNotNone(shelf.compose(good, bad, "cost_per_accepted"))
            self.assertIsNotNone(shelf.compose(bad, good, "cost_per_accepted"))
            self.assertIsNone(shelf.compose(bad, good, "accepted_work"))
        for unit in ("accepted requests", " USD / 1000 ACCEPTED requests "):
            known = copy.deepcopy(good)
            known["a_claim"]["results"]["example_result"]["unit"] = unit
            self.assertIsNone(shelf.compose(good, known, "accepted_work"))
        unknown = copy.deepcopy(good)
        unknown["a_claim"]["results"]["example_result"]["value"] = None
        self.assertIsNotNone(shelf.compose(good, unknown, "accepted_work"))
        for purpose in (None, [], {}, 1, "arbitrary"):
            self.assertTrue(shelf.compose(good, good, purpose).startswith("unknown purpose;"))


if __name__ == "__main__":
    unittest.main()
