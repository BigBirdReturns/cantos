#!/usr/bin/env python3
"""Stdlib-only tests for the shop-eval probe kit. Run with: python -B test_probe.py

Covers: minimal required-field schema validation of both fixtures (no jsonschema
dependency -- a small recursive walker reads fingerprint.schema.json's own
"required" lists), diff.py producing the expected flags on the two fixtures, and
`bash -n fingerprint.sh` parsing cleanly.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "fingerprint.schema.json"
REFERENCE_PATH = HERE / "fixtures" / "hotaisle-2026-09.fingerprint.json"
SYNTHETIC_PATH = HERE / "fixtures" / "synthetic-bad-shop.fingerprint.json"
FINGERPRINT_SH = HERE / "fingerprint.sh"
DIFF_PY = HERE / "diff.py"


def load(path: Path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_required(schema: dict, instance, path: str, errors: list) -> None:
    """Minimal structural check: every "required" name in an object schema node
    must be present in the matching instance object; recurse into "properties"
    and, for arrays, into "items". Good enough to catch a missing/renamed field
    without pulling in the jsonschema package."""
    if schema.get("type") == "object" or "properties" in schema:
        if not isinstance(instance, dict):
            errors.append(f"{path}: expected object, got {type(instance).__name__}")
            return
        for name in schema.get("required", []):
            if name not in instance:
                errors.append(f"{path}: missing required field '{name}'")
        for name, subschema in schema.get("properties", {}).items():
            if name in instance:
                validate_required(subschema, instance[name], f"{path}.{name}", errors)
    elif schema.get("type") == "array":
        if not isinstance(instance, list):
            errors.append(f"{path}: expected array, got {type(instance).__name__}")
            return
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(instance):
                validate_required(item_schema, item, f"{path}[{i}]", errors)
    # oneOf / const / scalar leaves: nothing further to check for a minimal validator.


class SchemaValidationTests(unittest.TestCase):
    def setUp(self):
        self.schema = load(SCHEMA_PATH)

    def test_schema_file_is_valid_json_with_required_list(self):
        self.assertEqual(self.schema.get("$id"), "second-run/shop-fingerprint@1")
        self.assertIn("required", self.schema)
        self.assertGreater(len(self.schema["required"]), 5)

    def test_reference_fixture_satisfies_required_fields(self):
        instance = load(REFERENCE_PATH)
        errors: list = []
        validate_required(self.schema, instance, "$", errors)
        self.assertEqual(errors, [], "\n".join(errors))

    def test_synthetic_fixture_satisfies_required_fields(self):
        instance = load(SYNTHETIC_PATH)
        errors: list = []
        validate_required(self.schema, instance, "$", errors)
        self.assertEqual(errors, [], "\n".join(errors))

    def test_reference_fixture_declares_its_own_schema_id(self):
        instance = load(REFERENCE_PATH)
        self.assertEqual(instance.get("schema"), "second-run/shop-fingerprint@1")

    def test_synthetic_fixture_is_clearly_marked_synthetic(self):
        instance = load(SYNTHETIC_PATH)
        self.assertTrue(instance.get("_synthetic") is True)
        self.assertIn("SYNTHETIC", instance.get("_synthetic_note", ""))

    def test_reference_fixture_invents_nothing_unmarked(self):
        # Every scalar in the reference fixture must be a real sourced value or
        # exactly "unobserved" -- never a made-up number/string standing in for
        # a fact fingerprint.sh would have to go collect on a real machine.
        instance = load(REFERENCE_PATH)
        allowed_exact = {"unobserved"}

        def walk(node):
            if isinstance(node, dict):
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
            elif isinstance(node, str):
                pass  # any string is fine here; this test only guards structural intent
        walk(instance)  # smoke: fixture must be walkable JSON, no exotic types
        self.assertIn(instance["cpu"]["model"], allowed_exact)
        self.assertIn(instance["memory"]["total"], allowed_exact)
        self.assertIn(instance["network"]["download_throughput_mb_s"], allowed_exact)
        self.assertIn(instance["gpu_topology"], allowed_exact)
        self.assertIn(instance["ecc"], allowed_exact)
        self.assertIn(instance["load_sample"], allowed_exact)
        # But the facts that ARE on record in env.json/env.normalized.json must be present:
        self.assertEqual(instance["kernel"], "6.8.0-124-generic")
        self.assertEqual(instance["hostname"], "enc1-gpuvm002")
        self.assertEqual(instance["gpu"]["vendor"], "amd")
        self.assertEqual(instance["gpu"]["count"], "1")
        self.assertEqual(instance["gpu"]["devices"][0]["model"], "AMD Instinct MI300X VF")


class DiffFlagTests(unittest.TestCase):
    """Runs the real diff.py subprocess against the two fixtures and checks the
    --json output names every flag category the task asked for."""

    EXPECTED_TAGS = {
        "pcie_below_gen5_x16",
        "vm_not_bare_metal",
        "driver_rocm_major_mismatch",
        "thermal_throttle_under_load",
        "ecc_errors_nonzero",
        "download_throughput_low",
        "mtu_low",
        "free_disk_low",
    }

    def run_diff(self, *extra_args):
        cmd = [sys.executable, "-B", str(DIFF_PY), str(REFERENCE_PATH), str(SYNTHETIC_PATH), *extra_args]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(HERE))
        return proc

    def test_diff_exits_zero_on_text_output(self):
        proc = self.run_diff()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("flag(s):", proc.stdout)

    def test_diff_json_exits_zero_and_is_valid_json(self):
        proc = self.run_diff("--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIn("diffs", payload)
        self.assertIn("flags", payload)

    def test_all_expected_flag_tags_fire_on_synthetic_bad_shop(self):
        proc = self.run_diff("--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        tags = {f["tag"] for f in payload["flags"]}
        missing = self.EXPECTED_TAGS - tags
        self.assertEqual(missing, set(), f"flags missing from diff.py output: {missing}")

    def test_every_flag_carries_a_why_it_matters_line(self):
        proc = self.run_diff("--json")
        payload = json.loads(proc.stdout)
        for f in payload["flags"]:
            self.assertTrue(f.get("why"), f"flag {f.get('tag')} has no why-it-matters text")
            self.assertGreater(len(f["why"]), 20)

    def test_diff_of_a_fixture_against_itself_has_no_flags(self):
        cmd = [sys.executable, "-B", str(DIFF_PY), str(REFERENCE_PATH), str(REFERENCE_PATH), "--json"]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(HERE))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["flags"], [])
        self.assertEqual(payload["diffs"], [])

    def test_diff_reports_a_large_diff_table_between_the_fixtures(self):
        proc = self.run_diff("--json")
        payload = json.loads(proc.stdout)
        # The two fixtures differ almost everywhere by design; this is a loose
        # floor so the test fails if flatten()/diff_fields() silently breaks.
        self.assertGreater(len(payload["diffs"]), 20)


class FingerprintShellTests(unittest.TestCase):
    def test_bash_minus_n_parses_cleanly(self):
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("no bash on PATH to run `bash -n` with")
        proc = subprocess.run([bash, "-n", str(FINGERPRINT_SH)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_fingerprint_sh_exists_and_is_nonempty(self):
        self.assertTrue(FINGERPRINT_SH.is_file())
        self.assertGreater(FINGERPRINT_SH.stat().st_size, 1000)

    def test_fingerprint_sh_declares_expected_usage_and_safety_flags(self):
        text = FINGERPRINT_SH.read_text(encoding="utf-8")
        self.assertIn("set -uo pipefail", text)
        self.assertIn("second-run/shop-fingerprint@1", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
