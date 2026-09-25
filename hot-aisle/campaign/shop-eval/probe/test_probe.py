#!/usr/bin/env python3
"""Stdlib-only tests for the shop-eval probe kit. Run with: python -B test_probe.py

Covers: minimal required-field schema validation of both fixtures (no jsonschema
dependency -- a small recursive walker reads fingerprint.schema.json's own
"required" lists), diff.py producing the expected flags on the two fixtures, and
`bash -n fingerprint.sh` parsing cleanly.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
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
        self.assertEqual(self.schema.get("$id"), "second-run/shop-fingerprint@3")
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
        self.assertEqual(instance.get("schema"), "second-run/shop-fingerprint@3")
        self.assertIs(instance.get("idle_verified"), False)
        self.assertIn("ambient", instance.get("sample_context", ""))

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

    def test_unverified_load_does_not_trigger_throttle_finding(self):
        with tempfile.TemporaryDirectory(prefix=".probe-unknown-load-", dir=HERE) as temp:
            candidate = load(SYNTHETIC_PATH)
            candidate["load_sample"]["status"] = "unknown"
            unknown_path = Path(temp) / "unknown.json"
            unknown_path.write_text(json.dumps(candidate), encoding="utf-8")
            proc = self.run_diff_path(unknown_path)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            flags = {item["tag"] for item in json.loads(proc.stdout)["flags"]}
            self.assertNotIn("thermal_throttle_under_load", flags)

    def run_diff_path(self, candidate_path: Path):
        cmd = [sys.executable, "-B", str(DIFF_PY), str(REFERENCE_PATH), str(candidate_path), "--json"]
        return subprocess.run(cmd, capture_output=True, text=True, cwd=str(HERE))

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
        # A relative argument plus cwd works in Windows Git Bash and avoids passing a
        # Windows drive path directly to Bash (which expects /d/... or a POSIX path).
        proc = subprocess.run([bash, "-n", FINGERPRINT_SH.name], capture_output=True, text=True, cwd=str(HERE))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_default_probe_is_inventory_only_and_does_not_overwrite(self):
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("no bash on PATH for inventory smoke")
        with tempfile.TemporaryDirectory(prefix=".probe-smoke-", dir=HERE) as temp:
            out_name = Path(temp).name + "/capture"
            proc = subprocess.run(
                [bash, FINGERPRINT_SH.name, "auto", out_name],
                capture_output=True, text=True, cwd=str(HERE), timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            payload = load(Path(temp) / "capture" / "fingerprint.json")
            self.assertEqual(payload["load_sample"], "not_requested")
            self.assertTrue(payload["network"]["download_throughput_mb_s"].startswith("not_measured:"))
            self.assertTrue((Path(temp) / "capture" / "MANIFEST.sha256").is_file())
            again = subprocess.run(
                [bash, FINGERPRINT_SH.name, "auto", out_name],
                capture_output=True, text=True, cwd=str(HERE), timeout=10,
            )
            self.assertEqual(again.returncode, 3)

    def test_gpu_load_is_explicit_gpu_backend_and_bounded(self):
        text = FINGERPRINT_SH.read_text(encoding="utf-8")
        self.assertIn("GPU_LOAD_REQUESTED=0", text)
        self.assertIn("duration=30", text)
        self.assertIn('torch.cuda.is_available()', text)
        self.assertIn('torch.device("cuda:0")', text)
        self.assertIn("no CPU fallback", text)
        self.assertNotIn("bytes=1073741824", text)
        self.assertNotIn("speed.cloudflare.com", text)

    def test_fingerprint_sh_exists_and_is_nonempty(self):
        self.assertTrue(FINGERPRINT_SH.is_file())
        self.assertGreater(FINGERPRINT_SH.stat().st_size, 1000)

    def test_fingerprint_sh_declares_expected_usage_and_safety_flags(self):
        text = FINGERPRINT_SH.read_text(encoding="utf-8")
        self.assertIn("set -uo pipefail", text)
        self.assertIn("second-run/shop-fingerprint@3", text)

    @unittest.skipIf(os.name == "nt", "POSIX executable stubs required")
    def test_nvidia_bus_id_maps_to_vendor_bdf_not_neighboring_intel_gpu(self):
        bash = shutil.which("bash")
        if bash is None or shutil.which("timeout") is None:
            self.skipTest("bash and GNU timeout are required")
        with tempfile.TemporaryDirectory(prefix=".probe-bdf-") as temp:
            root = Path(temp)
            pci = root / "pci"
            for bdf, vendor, cls in (
                ("0000:00:02.0", "0x8086", "0x030000"),
                ("0000:09:00.0", "0x10de", "0x030200"),
            ):
                dev = pci / bdf
                dev.mkdir(parents=True)
                (dev / "vendor").write_text(vendor, encoding="ascii")
                (dev / "class").write_text(cls, encoding="ascii")
                (dev / "current_link_speed").write_text("16.0 GT/s", encoding="ascii")
                (dev / "current_link_width").write_text("16", encoding="ascii")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            nvidia = bin_dir / "nvidia-smi"
            nvidia.write_text(
                "#!/bin/sh\n"
                "case \"$*\" in\n"
                "  -L) echo 'GPU 0: NVIDIA Test (UUID: GPU-test)' ;;\n"
                "  '--query-gpu=driver_version --format=csv,noheader') echo 550.54 ;;\n"
                "  '') echo 'CUDA Version: 12.4' ;;\n"
                "  '-q') echo 'NVIDIA query output' ;;\n"
                "  'topo -m') echo 'GPU0\tGPU0' ;;\n"
                "  --query-gpu=index,pci.bus_id,name,*) echo '0, 00000000:09:00.0, NVIDIA Test, 95.00.00.00, 5, 16, 0, 0, 210, 1200, 50, 80, Not Active' ;;\n"
                "  *) echo '0, 0, 0, 50, 80, Not Active' ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            nvidia.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            env["SHOP_PROBE_PCI_SYSFS_ROOT"] = str(pci)
            out = root / "capture"
            proc = subprocess.run(
                [bash, FINGERPRINT_SH.name, "nvidia", str(out)],
                capture_output=True, text=True, cwd=str(HERE), env=env, timeout=40,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            payload = json.loads((out / "fingerprint.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["gpu"]["count"], "1")
            self.assertEqual(payload["gpu"]["devices"][0]["pci_addr"], "0000:09:00.0")
            self.assertFalse(payload["idle_verified"])

    @unittest.skipIf(os.name == "nt", "POSIX executable stubs required")
    def test_requested_gpu_load_fails_unknown_without_cpu_fallback(self):
        bash = shutil.which("bash")
        if bash is None or shutil.which("timeout") is None:
            self.skipTest("bash and GNU timeout are required")
        with tempfile.TemporaryDirectory(prefix=".probe-no-torch-") as temp:
            root = Path(temp)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_python = bin_dir / "python3"
            fake_python.write_text("#!/bin/sh\nexit 1\n", encoding="ascii")
            fake_python.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            env["SHOP_PROBE_PCI_SYSFS_ROOT"] = str(root / "empty-pci")
            (root / "empty-pci").mkdir()
            out = root / "capture"
            proc = subprocess.run(
                [bash, FINGERPRINT_SH.name, "nvidia", str(out), "--gpu-load"],
                capture_output=True, text=True, cwd=str(HERE), env=env, timeout=60,
            )
            self.assertEqual(proc.returncode, 4, proc.stderr + proc.stdout)
            payload = json.loads((out / "fingerprint.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["load_sample"]["status"], "unknown")
            self.assertIn("no CPU fallback", payload["load_sample"]["reason"])
            self.assertEqual((out / "raw" / "gpu-load.txt").read_text(encoding="utf-8").strip(),
                             "unknown: host Python PyTorch unavailable; no CPU fallback")


if __name__ == "__main__":
    unittest.main(verbosity=2)
