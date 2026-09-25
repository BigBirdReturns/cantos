#!/usr/bin/env python3
"""Regressions for scripts/shelf.py. Run: python -m unittest discover -s shelf/tests -v"""
from __future__ import annotations
import copy
import datetime as dt
import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("shelf", os.path.join(TOOL, "scripts", "shelf.py"))
shelf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shelf)

with open(os.path.join(HERE, "cases.json"), encoding="utf-8") as f:
    CASES = json.load(f)
CARDS = shelf.read_cards(os.path.join(TOOL, "data", "cards.jsonl"))
BY_ID = {c["id"]: c for c in CARDS}


class Reading(unittest.TestCase):
    def test_json_object_list_and_jsonl(self):
        card = BY_ID["run3-at0"]
        self.assertEqual(shelf.parse_cards(json.dumps(card))[0]["id"], "run3-at0")
        self.assertEqual(len(shelf.parse_cards(json.dumps([card, card]))), 2)
        self.assertEqual(len(shelf.parse_cards("﻿" + "\n".join(json.dumps(c) for c in CARDS))), 5)

    def test_shelf_copy_matches_retained_campaign_record(self):
        same, a, b, _ = shelf.sync_check()
        self.assertTrue(same, f"{a} != {b}")


class Validate(unittest.TestCase):
    def test_five_shelf_cards_pass(self):
        for c in CARDS:
            self.assertEqual(shelf.validate_card(c), [], c["id"])

    def test_fixture_cases(self):
        for case in CASES["validate"]:
            card = shelf.read_cards(os.path.join(HERE, case["file"]))[0]
            errors = shelf.validate_card(card)
            self.assertEqual(len(errors), case["expect_errors"], (case["file"], errors))
            for needle in case.get("contains", []):
                self.assertTrue(any(needle in e for e in errors), (needle, errors))

    def test_integer_is_not_a_boolean(self):
        c = copy.deepcopy(BY_ID["run3-at0"])
        c["dimensions"]["measured"] = 1
        self.assertIn("dimension values must be true/false/null, not integers", shelf.validate_card(c))

    def test_publication_date_needs_a_basis(self):
        c = copy.deepcopy(BY_ID["mercatus-index"])
        c["a_claim"]["period"]["publication_date"] = "2026-09-24"
        self.assertTrue(any("publication_date_basis" in e for e in shelf.validate_card(c)))

    def test_known_benefit_needs_a_basis(self):
        c = copy.deepcopy(BY_ID["run3-at0"])
        c["c_parties"]["observer_benefit"] = {"benefits_from_outcome": True, "relationship": "x", "basis": None}
        self.assertIn("observer_benefit needs a basis for a known benefit judgment", shelf.validate_card(c))

    def test_seat_hour_needs_gpu_count(self):
        c = copy.deepcopy(BY_ID["hotaisle-blog"])
        c["a_claim"]["results"]["new_rate"]["unit"] = "USD / seat-hour"
        self.assertTrue(any("conditions.gpus" in e for e in shelf.validate_card(c)))

    def test_id_is_a_slug(self):
        c = copy.deepcopy(BY_ID["run3-at0"])
        c["id"] = "Run 3!"
        self.assertIn("id must be a short lowercase slug", shelf.validate_card(c))


class Compose(unittest.TestCase):
    def test_fixture_cases(self):
        for case in CASES["compose"]:
            got = shelf.compose(BY_ID[case["a"]], BY_ID[case["b"]], case["purpose"])
            self.assertEqual(got, case["expect"], case)

    def test_unknown_purpose_refuses(self):
        self.assertIn("unknown purpose", shelf.compose(BY_ID["run3-at0"], BY_ID["run3-at0"], "rank"))

    def test_missing_operand_refuses(self):
        self.assertIn("missing operand", shelf.compose(BY_ID["run3-at0"], None, "same_period"))


class Which(unittest.TestCase):
    def test_fixture_cases(self):
        for case in CASES["which"]:
            rows = shelf.which(CARDS, case["unit"], case["period"], case["measured"])
            got = {r["id"]: r["status"] for r in rows}
            self.assertEqual(got, case["expect"], case["name"])
            for cid, needle in case.get("reason_contains", {}).items():
                row = next(r for r in rows if r["id"] == cid)
                self.assertIn(needle, row["reason"], case["name"])

    def test_support_carries_limits_and_checks_not_a_rank(self):
        row = shelf.which(CARDS, "USD / 1000 accepted requests", "2026-09", True)[0]
        self.assertEqual(row["id"], "run3-at0")
        self.assertEqual(set(row["results"]), {"own_seat_equivalent", "actual_shared_seat", "h100_comparator"})
        self.assertEqual(len(row["limits"]), 3)
        self.assertIn("not repeated", row["how_far"])
        self.assertIn("Nothing here ranks", row["how_far"])

    def test_retrieval_never_supplies_the_period(self):
        c = copy.deepcopy(BY_ID["hotaisle-blog"])
        c["a_claim"]["period"]["retrieved_at"] = "2026-09-24"
        self.assertIsNone(shelf.observation_date(c))

    def test_period_forms(self):
        self.assertTrue(shelf.in_period("2026-09-24", "2026"))
        self.assertTrue(shelf.in_period("2026-09-24", "2026-09"))
        self.assertTrue(shelf.in_period("2026-09-24", "2026-09-24"))
        self.assertFalse(shelf.in_period("2026-09-24", "2026-08"))
        self.assertTrue(shelf.in_period("2026-09-24", "2026-09-01..2026-09-30"))
        self.assertFalse(shelf.in_period("2026-10-01", "2026-09-01..2026-09-30"))


class Pull(unittest.TestCase):
    def test_local_pull_enters_staging_as_candidate(self):
        src = os.path.join(HERE, "fixtures", "card7-voltagepark.json")
        with tempfile.TemporaryDirectory() as tmp:
            folder, prov = shelf.pull(src, "Second Stranger", staging=tmp, now=dt.datetime(2026, 9, 25, 3, 0, 0, tzinfo=dt.timezone.utc))
            self.assertTrue(folder.startswith(os.path.join(tmp, "second-stranger")))
            self.assertEqual(prov["standing"], "imported/candidate")
            self.assertEqual(prov["cards"], 1)
            self.assertEqual(prov["filings"][0]["errors"], [])
            self.assertEqual(sorted(os.listdir(folder)), ["cards.jsonl", "provenance.json", "source.bytes"])
            with open(os.path.join(folder, "source.bytes"), "rb") as f, open(src, "rb") as g:
                self.assertEqual(f.read(), g.read())
            with self.assertRaises(FileExistsError):
                shelf.pull(src, "Second Stranger", staging=tmp, now=dt.datetime(2026, 9, 25, 3, 0, 0, tzinfo=dt.timezone.utc))

    def test_pull_records_filing_errors_without_refusing_the_import(self):
        src = os.path.join(HERE, "fixtures", "card6-latitude-h100.json")
        with tempfile.TemporaryDirectory() as tmp:
            _, prov = shelf.pull(src, "first-stranger", staging=tmp)
            self.assertEqual(len(prov["filings"][0]["errors"]), 4)

    def test_pull_never_touches_the_shelf(self):
        before = open(shelf.CARDS, "rb").read()
        with tempfile.TemporaryDirectory() as tmp:
            shelf.pull(os.path.join(HERE, "fixtures", "card7-voltagepark.json"), "x", staging=tmp)
        self.assertEqual(open(shelf.CARDS, "rb").read(), before)


class Cli(unittest.TestCase):
    def test_validate_exit_code_counts_failures(self):
        self.assertEqual(shelf.main(["validate", os.path.join(TOOL, "data", "cards.jsonl")]), 0)
        self.assertEqual(shelf.main(["validate", os.path.join(HERE, "fixtures", "card6-latitude-h100.json")]), 1)

    def test_compose_exit_code(self):
        scratch = r"S:\Scratch\Temp" if os.name == "nt" else None
        with tempfile.TemporaryDirectory(prefix="shelf-cli-", dir=scratch) as tmp:
            run = os.path.join(tmp, "run3-at0.json")
            with open(run, "w", encoding="utf-8") as f:
                json.dump(BY_ID["run3-at0"], f)
            self.assertEqual(shelf.main(["compose", run, os.path.join(HERE, "fixtures", "card7-voltagepark.json"), "--for", "measured_cost"]), 2)
            self.assertEqual(shelf.main(["compose", run, run, "--for", "cost_per_accepted"]), 0)


if __name__ == "__main__":
    unittest.main()
