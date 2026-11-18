"""Qualification of refusal and provenance boundaries; no model or GPU execution."""
import copy
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import preflight
import render_recipe


class ReadinessTests(unittest.TestCase):
    def test_retained_w03_refuses_unsupported_gpus_and_missing_image(self):
        runtime = preflight.native.load(ROOT / "runtime.json")
        inventory = preflight.native.load(ROOT / "hardware-observed.json")
        checks = {c["id"]: c for c in preflight.assess_inventory(inventory, runtime)}
        self.assertEqual(checks["documented_gpu_family"]["status"], "blocked")
        self.assertEqual(checks["selected_recipe_topology"]["observed_count"], 2)
        self.assertEqual(checks["local_pinned_image"]["status"], "blocked")
        self.assertFalse(preflight.make_report(inventory, "retained_metadata")["ready_to_launch"])

    def test_synthetic_compatible_inventory_still_cannot_claim_benchmark_readiness(self):
        runtime = preflight.native.load(ROOT / "runtime.json")
        inventory = copy.deepcopy(preflight.native.load(ROOT / "hardware-observed.json"))
        inventory["host"] = "synthetic-eight-h200-fixture"
        inventory["gpu_probe"]["stdout"] = "\n".join(
            f"{i}, NVIDIA H200, GPU-00000000-0000-0000-0000-{i:012d}, 143771, 0, synthetic, 9.0, 0, 700, 30"
            for i in range(8)) + "\n"
        inventory["container_probe"] = {"exit_code": 0, "stdout": json.dumps([
            runtime["image_repository"] + "@" + runtime["image_digest"]])}
        report = preflight.make_report(inventory, "synthetic_fixture")
        checks = {c["id"]: c for c in report["checks"]}
        self.assertEqual(checks["documented_gpu_family"]["status"], "pass")
        self.assertEqual(checks["selected_recipe_topology"]["status"], "pass")
        self.assertFalse(report["ready_to_launch"])
        self.assertFalse(report["hy4_inference_observed"])
        self.assertEqual(report["status"], "blocked")

    def test_consumer_blackwell_name_does_not_qualify_as_data_center_recipe(self):
        runtime = preflight.native.load(ROOT / "runtime.json")
        inventory = copy.deepcopy(preflight.native.load(ROOT / "hardware-observed.json"))
        inventory["gpu_probe"]["stdout"] = "0, NVIDIA RTX PRO 5000 Blackwell, GPU-synthetic, 73728, 0, synthetic, 12.0, 0, 300, 30\n"
        checks = {c["id"]: c for c in preflight.assess_inventory(inventory, runtime)}
        self.assertEqual(checks["documented_gpu_family"]["status"], "blocked")

    def test_changed_source_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="cantos-hy4-test-") as tmp:
            target = Path(tmp) / "package"
            shutil.copytree(ROOT, target)
            p = target / "snapshots/fp8.recipe.json"
            p.write_bytes(p.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "changed source artifact"):
                preflight.verify_package(target)

    def test_native_templates_refuse_and_bound_synthetic_copy_prepares(self):
        result = preflight.verify_package()
        self.assertEqual(set(result["native_template_refusal"]), {"baseline", "candidate"})
        with tempfile.TemporaryDirectory(prefix="cantos-hy4-native-schema-") as tmp:
            target = Path(tmp)
            for name in ["workload.smoke.json", "policy.precision.json"]:
                shutil.copy2(ROOT / name, target / name)
            spec = preflight.native.load(ROOT / "spec.precision.template.json")
            for arm in ("baseline", "candidate"):
                spec[arm]["identity"]["model"]["sha256"] = "0" * 64
                spec[arm]["identity"]["hardware"] = {"id": "synthetic-schema-only", "description": "authored validation fixture"}
                spec[arm]["identity"]["settings"]["prefix_cache"] = False
                spec[arm]["identity"]["settings"]["co_tenancy"] = "synthetic-schema-only"
                spec[arm]["identity"]["settings"]["power_and_cooling"] = "synthetic-schema-only"
                spec[arm]["identity"]["settings"]["effective_runtime"] = "synthetic-schema-only"
            path = target / "spec.json"
            path.write_text(json.dumps(spec))
            for arm in ("baseline", "candidate"):
                prepared = preflight.native.prepare(path, arm)
                self.assertEqual(prepared["protocol"]["concurrency"], 1)
                self.assertEqual(len(prepared["workload"]["cases"]), 4)

    @unittest.skipUnless(os.name == "posix", "retained Docker command renderer requires POSIX mount paths")
    def test_command_rendering_is_offline_pinned_and_excludes_base(self):
        ids = [f"GPU-00000000-0000-0000-0000-{i:012d}" for i in range(8)]
        result = render_recipe.render("instruct-fp8", "/synthetic/unexecuted/snapshot", ids)
        self.assertEqual(result["status"], "unexecuted")
        self.assertIn("--pull=never", result["argv"])
        self.assertNotIn("--privileged", result["argv"])
        self.assertNotIn("--speculative-config", result["argv"])
        self.assertTrue(any("vllm/vllm-openai@sha256:" in x for x in result["argv"]))
        with self.assertRaisesRegex(ValueError, "Base"):
            render_recipe.render("base-bf16", "/synthetic/snapshot", ids)
        with self.assertRaisesRegex(ValueError, "eight distinct"):
            render_recipe.render("instruct-fp8", "/synthetic/snapshot", ids[:2])


if __name__ == "__main__":
    unittest.main()
