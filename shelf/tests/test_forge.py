#!/usr/bin/env python3
"""The forge at small scale is a regression: every invariant must survive the seed-derived
population on every commit. Set AXM_GENESIS to the canonical axm-genesis checkout to include
the kernel regime (IDENTITY, NON-TRANSFER and SUCCESSION through native Genesis shards).
Run: python -m unittest discover -s shelf/tests -p 'test_forge.py' -v"""
from __future__ import annotations
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("forge", os.path.join(TOOL, "scripts", "forge.py"))
forge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(forge)
GENESIS = os.environ.get("AXM_GENESIS") or None


class Forge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = forge.run(seed=1, scale="small", record=False, quiet=True, genesis=GENESIS if GENESIS and os.path.isdir(GENESIS) else None)

    def test_no_invariant_fails_on_the_seeded_population(self):
        self.assertEqual(self.rec["failures"], 0, self.rec["failure_records"][:3])

    def test_population_is_the_declared_size(self):
        c = self.rec["counts"]
        self.assertEqual(c["valid"], forge.SCALES["small"]["valid"])
        self.assertEqual(c["one_fault"], forge.SCALES["small"]["faults"])
        self.assertEqual(c["pairs"], forge.SCALES["small"]["pairs"])
        self.assertEqual(c["parity_cases"]["compose"], forge.SCALES["small"]["pairs"])
        self.assertGreater(c["fault_regimes"].get("illegal", 0), 0)
        self.assertGreater(c["fault_regimes"].get("boundary", 0), 0)
        self.assertGreater(c["fault_regimes"].get("benign", 0), 0)

    def test_record_names_the_tested_bytes(self):
        for k in ("shelf_sha256", "engine_sha256", "cards_sha256", "seed", "generator_version"):
            self.assertTrue(self.rec[k])

    def test_seed_is_reproducible(self):
        again = forge.run(seed=1, scale="small", record=False, quiet=True, genesis=None)
        a = {k: self.rec[k] for k in ("counts", "failures")}
        b = {k: again[k] for k in ("counts", "failures")}
        a["counts"].pop("mutators", None); b["counts"].pop("mutators", None)
        self.assertEqual(a, b)

    def test_a_planted_bug_is_caught_and_minimized(self):
        """Break the engine's period rule in a copy of shelf.py and the forge must report REFUSAL with a minimized card."""
        import copy
        original = forge.shelf.in_period
        try:
            forge.shelf.in_period = lambda date, asked: True  # every date now falls in every period
            F = forge.Failures()
            rng = forge.random.Random(3)
            valid = forge.real_cards() + forge.gen_valid(rng, 60)
            for c in valid[:5]:
                c["archetype"] = "real"
            faults = forge.gen_faults(rng, valid, 600)
            forge.check_locality_and_refusal(valid, faults, F)
            forge.shrink_failures(F)
            hits = [f for f in F if f["invariant"] == "REFUSAL" and f["detail"].get("mutator") == "m_date_shift"]
            self.assertTrue(hits, "the planted period bug went unreported")
            self.assertIn("minimized", hits[0])
            self.assertLessEqual(len(hits[0]["minimized"]["a_claim"]["results"]), len(hits[0]["counterexample"]["mutated"]["a_claim"]["results"]))
        finally:
            forge.shelf.in_period = original

    @unittest.skipUnless(GENESIS and os.path.isdir(GENESIS), "AXM_GENESIS not set")
    def test_genesis_regime_bound_every_sampled_card(self):
        g = self.rec["genesis"]
        self.assertEqual(g["bound"], g["cards"])
        self.assertIn("native Genesis", self.rec["invariants"]["SUCCESSION"])


if __name__ == "__main__":
    unittest.main()
