"""Generator-driver self-tests, separate from native-engine qualification.

The fake bridge below deliberately disagrees only to test witness shrinking and
replay. Its injected result is never evidence of a native engine discrepancy.
All generated campaign outputs are disposable, under typed scratch on Windows.
"""
from __future__ import annotations

import collections
import contextlib
import copy
import importlib.util
import io
import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("shelf_generated_driver_selftest", HERE / "generated.py")
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)

EXPECTED_FAULTS = {
    "dimension-integer", "dimension-string", "dimension-extra", "funding-missing",
    "benefit-missing", "benefit-integer", "benefit-basis", "period-missing",
    "publication-basis", "hourly-ambiguous", "hourly-short", "hourly-hr",
    "rate-boolean", "rate-negative", "seat-count-missing", "seat-count-boolean",
    "check-object", "check-who", "check-when", "id-uppercase", "id-long",
    "title-multiline", "spine-empty", "version-missing", "results-array",
    "parties-array", "dimensions-array", "claim-array", "population-missing",
    "materials-missing", "check-missing", "version-boolean",
}


class DeliberatelyDivergentBridge:
    """Test-only double: append an error when a synthetic trigger survives."""

    def __init__(self):
        self.calls = 0

    def ask(self, request):
        self.calls += 1
        result = copy.deepcopy(G.native(request))
        argument = request["args"][0]
        if (request["operation"] == "validate" and isinstance(argument, dict)
                and "driver_selftest_trigger" in argument and result["ok"]):
            result["value"].append("Deliberately injected driver self-test disagreement")
        return result

    def close(self):
        pass


class GeneratedDriver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = Path("S:/Scratch/Runs") if os.name == "nt" else Path(tempfile.gettempdir())
        scratch.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix="shelf-generated-driver-", dir=scratch)
        cls.output = Path(cls.temporary.name)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @staticmethod
    def sample(seed):
        pool, facts = G.composition_pool(seed, 10)
        return {
            "pool": pool, "facts": facts,
            "valid": list(G.validation_cases(seed, 20)),
            "faults": list(G.validation_cases(seed, 64, True)),
            "transitions": list(G.transition_cases(seed, 20)),
            "pairs": list(G.composition_cases(seed, 100, pool, facts)),
        }

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(HERE / "generated.py"), *map(str, args)],
                              cwd=G.TOOL.parent, capture_output=True, text=True,
                              encoding="utf-8", timeout=120)

    def witness(self, name, case, **extra):
        path = self.output / name
        path.write_bytes(G.encoded({"generator": G.VERSION, "seed": 20260924,
                                   "phase": "driver-selftest", "reason": "driver-selftest",
                                   "case": case, **extra}) + b"\n")
        return path

    def test_same_seed_reproduces_all_case_families_without_mutating_retained_cards(self):
        before = G.encoded(G.BASES)
        self.assertEqual(G.encoded(self.sample(20260924)), G.encoded(self.sample(20260924)))
        self.assertEqual(G.encoded(G.BASES), before)

    def test_different_seed_changes_semantic_variation_beyond_generated_ids(self):
        first = [G.variant(17, index) for index in range(12)]
        second = [G.variant(18, index) for index in range(12)]
        for card in first + second:
            del card["id"]
        self.assertNotEqual(G.encoded(first), G.encoded(second))
        self.assertNotEqual(G.encoded(self.sample(17)), G.encoded(self.sample(18)))

    def test_all_32_fault_families_are_generated_and_actually_refused(self):
        self.assertEqual(len(G.FAULTS), 32)
        self.assertEqual(set(G.FAULTS), EXPECTED_FAULTS)
        cases = list(G.validation_cases(20260924, 96, True))
        self.assertEqual(collections.Counter(case["label"] for case in cases),
                         collections.Counter({label: 3 for label in EXPECTED_FAULTS}))
        for case in cases:
            with self.subTest(fault=case["label"], index=case["index"]):
                self.assertEqual(G.native({"operation": "validate", "args": [
                    G.variant(20260924, case["index"])]}), {"ok": True, "value": []})
                outputs = [G.native(request) for request in case["requests"]]
                self.assertTrue(outputs[0]["ok"])
                self.assertTrue(outputs[0]["value"])
                self.assertEqual(outputs[1]["value"][0]["status"], "CANNOT_USE")
                self.assertIsNone(G.property_failure(case, outputs))

    def test_full_pair_schedule_is_a_permutation_at_small_sizes_and_million_scale(self):
        # Exhaustive small schedules exercise the real generator; the coprime
        # stride proves uniqueness at the declared million-pair size cheaply.
        for size, seed in itertools.product((10, 11, 16, 25), (0, 20260924)):
            with self.subTest(size=size, seed=seed):
                pool, facts = G.composition_pool(seed, size)
                cases = list(G.composition_cases(seed, size * size, pool, facts))
                pairs = [tuple(case["requests"][0]["refs"]) for case in cases]
                self.assertEqual(len(pairs), size * size)
                self.assertEqual(set(pairs), set(itertools.product(range(size), repeat=2)))
                self.assertEqual({case["label"] for case in cases}, set(G.PURPOSES))
                self.assertEqual(cases, list(G.composition_cases(seed, size * size, pool, facts)))
        population = G.PROFILES["full"]["pairs"]
        self.assertEqual(population, 1_000_000)
        size = math.isqrt(population)
        self.assertEqual(size * size, population)
        self.assertEqual(math.gcd(size + 1, population), 1)

    def test_property_oracle_rejects_agreement_on_wrong_answers(self):
        success = lambda value: {"ok": True, "value": value}
        cases = [
            ({"expect": "valid"}, [success(["unexpected error"])], "validity"),
            ({"expect": "invalid"}, [success([]), success([])], "one-fault-not-refused"),
            ({"expect": "invalid"}, [success(["error"]), success([{"status": "SUPPORTS"}])],
             "invalid-filing-query-support"),
            ({"expect": "refusal"}, [success(None)], "refusal"),
            ({"expect": "no-refusal"}, [success("refused")], "unexpected-refusal"),
            ({"expect": "transition", "label": "measurement-boundary"},
             [success([{"status": "SUPPORTS"}]), success([{"status": "SUPPORTS"}])], "query-boundary"),
        ]
        for case, outputs, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(G.property_failure(case, outputs), expected)

    def test_json_parity_preserves_boolean_types_and_array_order(self):
        self.assertTrue(G.same_json({"a": 1, "b": [None, 2]}, {"b": [None, 2.0], "a": 1.0}))
        self.assertFalse(G.same_json({"value": True}, {"value": 1}))
        self.assertFalse(G.same_json({"value": False}, {"value": 0.0}))
        self.assertFalse(G.same_json([1, 2], [2, 1]))
        self.assertFalse(G.same_json({"a": None}, {}))
        self.assertFalse(G.same_json([1], [1, 2]))

    def test_shrinker_reduces_a_test_only_disagreement_and_preserves_arity(self):
        card = G.variant(20260924, 0)
        card["driver_selftest_trigger"] = "synthetic harness marker"
        request = {"operation": "validate", "args": [card]}
        original = G.encoded(request)
        bridge = DeliberatelyDivergentBridge()
        reduced, attempts = G.shrink_parity(request, bridge, budget=150)
        self.assertEqual(G.encoded(request), original)
        self.assertEqual(reduced["operation"], "validate")
        self.assertEqual(len(reduced["args"]), 1)
        self.assertIn("driver_selftest_trigger", reduced["args"][0])
        self.assertLess(len(G.encoded(reduced)), len(original))
        self.assertGreater(attempts, 0)
        self.assertLessEqual(attempts, 150)
        self.assertEqual(bridge.calls, attempts)
        python, injected = G.native(reduced), bridge.ask(reduced)
        self.assertTrue(python["ok"] and injected["ok"])
        self.assertNotEqual(python, injected)

    def test_two_real_smoke_runs_have_identical_case_streams_and_coverage(self):
        reports = []
        for index in range(2):
            output = self.output / f"smoke-{index}"
            run = self.cli("--profile", "smoke", "--seed", 20260924, "--out", output)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            report = json.loads((output / "report.json").read_bytes())
            self.assertEqual(report["failures"], [])
            self.assertEqual(report["observed"]["failures"], 0)
            for phase, count in G.PROFILES["smoke"].items():
                self.assertEqual(report["observed"][phase], count)
            self.assertEqual(report["observed"]["engine_comparisons"], 1900)
            self.assertEqual({key.removeprefix("faults:") for key in report["coverage"]
                              if key.startswith("faults:")}, EXPECTED_FAULTS)
            self.assertTrue(report["source_stable"])
            reports.append(report)
        for key in ("seed", "counts", "observed", "coverage", "case_stream_sha256", "pool_sha256"):
            self.assertEqual(reports[0][key], reports[1][key], key)

    def test_real_replay_needs_no_output_directory_and_reports_property_failure(self):
        card = G.variant(20260924, 0)
        # The claim of invalidity is deliberately false: this tests replay's
        # failure exit status, not a failure of either native engine.
        path = self.witness("false-property.json", {
            "label": "driver-selftest-deliberately-false-expectation", "index": 0,
            "expect": "invalid", "requests": [
                {"operation": "validate", "args": [card]},
                {"operation": "which", "args": [[card], "USD / GPU-hour", None, False]},
            ],
        })
        run = self.cli("--replay", path)
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertTrue(run.stdout.strip())
        self.assertNotIn("--out", run.stderr)

    def test_replay_does_not_report_success_for_test_only_persistent_parity_failure(self):
        card = G.variant(20260924, 0)
        card["driver_selftest_trigger"] = "synthetic harness marker"
        path = self.witness("injected-parity.json", {
            "label": "driver-selftest-injected-disagreement", "index": 0,
            "expect": "valid", "requests": [{"operation": "validate", "args": [card]}],
        })
        with mock.patch.object(G, "Bridge", DeliberatelyDivergentBridge), \
                mock.patch.object(sys, "argv", [str(HERE / "generated.py"), "--replay", str(path)]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(G.main(), 1)

    def test_replay_checks_minimized_witness_as_well_as_original(self):
        card = G.variant(20260924, 0)
        reduced = {"operation": "validate", "args": [{"driver_selftest_trigger": ""}]}
        path = self.witness("injected-minimized-parity.json", {
            "label": "driver-selftest-minimized-disagreement", "index": 0,
            "expect": "valid", "requests": [{"operation": "validate", "args": [card]}],
        }, minimized=reduced)
        output = io.StringIO()
        with mock.patch.object(G, "Bridge", DeliberatelyDivergentBridge), \
                mock.patch.object(sys, "argv", [str(HERE / "generated.py"), "--replay", str(path)]), \
                contextlib.redirect_stdout(output):
            self.assertEqual(G.main(), 1)
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["python"], rows[0]["browser"])
        self.assertTrue(rows[1]["minimized"])
        self.assertNotEqual(rows[1]["python"], rows[1]["browser"])


if __name__ == "__main__":
    unittest.main()
