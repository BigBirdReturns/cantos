"""Boundary checks against the real native Run 3 shard; fixtures stay in scratch."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import join


GENESIS = Path("D:/Projects/Organs/AXM/axm-genesis/main")
SCRATCH = Path("S:/Scratch/Runs/run3-shelf-join")
BUNDLE = join.HERE / "run3-v3"


class JoinChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        cls.work = tempfile.TemporaryDirectory(prefix="boundary-tests-", dir=SCRATCH)
        cls.root = Path(cls.work.name)

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def copy_bundle(self, label):
        destination = self.root / label
        shutil.copytree(BUNDLE, destination)
        return destination

    def inspect(self, bundle=BUNDLE, campaign=join.CAMPAIGN, context=None):
        return join.inspect(bundle, GENESIS, campaign, context)

    def test_binding_candidate_and_applicability_are_distinct(self):
        result = self.inspect()
        self.assertEqual(result["native_verifier"]["status"], "PASS")
        self.assertEqual(result["binding"], "bound")
        self.assertEqual(result["standing"], "filed/candidate")
        self.assertEqual(result["applicability"], "PASS")
        self.assertFalse(result["authorized_reuse"])

    def test_native_source_byte_tamper_is_rejected(self):
        bundle = self.copy_bundle("tamper")
        source = bundle / "shard/content/source.txt"
        source.write_bytes(source.read_bytes().replace(b"4336", b"4337", 1))
        result = self.inspect(bundle)
        self.assertEqual(result["binding"], "unbound")
        self.assertEqual(result["applicability"], "REFUSE")
        self.assertEqual(result["native_verifier"]["status"], "FAIL")
        self.assertIn("E_MERKLE_MISMATCH", {e["code"] for e in result["native_verifier"]["errors"]})

    def test_missing_binding_is_refused(self):
        bundle = self.copy_bundle("missing-binding")
        (bundle / "binding.json").unlink()
        result = self.inspect(bundle)
        self.assertEqual(result["binding"], "unbound")
        self.assertEqual(result["applicability"], "REFUSE")
        self.assertIn("Missing binding.json", result["reasons"])

    def test_changed_dependency_preserves_binding_but_refuses_applicability(self):
        campaign = self.root / "changed-campaign"
        dependencies = join.read(BUNDLE / "shard/content/dependency-scope.json")["dependencies"]
        for dependency in dependencies:
            target = campaign / dependency["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(join.CAMPAIGN / dependency["path"], target)
        (campaign / "shelf").mkdir()
        shutil.copyfile(join.SHELF / "cards.jsonl", campaign / "shelf/cards.jsonl")
        evaluator = campaign / "run3/grade.py"
        evaluator.write_bytes(evaluator.read_bytes() + b"\n# changed evaluator\n")
        result = self.inspect(campaign=campaign)
        self.assertEqual(result["binding"], "bound")
        self.assertEqual(result["standing"], "filed/candidate")
        self.assertEqual(result["applicability"], "REFUSE")
        self.assertEqual(result["reasons"], ["Changed dependency: run3/grade.py"])

    def test_changed_period_and_evaluator_context_are_refused(self):
        original = join.context_for(join.read(BUNDLE / "card.json"))
        for field in ("period", "acceptance"):
            with self.subTest(field=field):
                context = copy.deepcopy(original)
                context[field] = {"changed": True}
                result = self.inspect(context=context)
                self.assertEqual(result["binding"], "bound")
                self.assertEqual(result["applicability"], "REFUSE")
                self.assertFalse(result["authorized_reuse"])

    def test_editing_candidate_to_accepted_grants_no_authority(self):
        bundle = self.copy_bundle("forged-standing")
        standing = join.read(bundle / "standing.json")
        standing["policy"]["standing"] = "accepted"
        join.write(bundle / "standing.json", standing)
        result = self.inspect(bundle)
        self.assertEqual(result["binding"], "bound")
        self.assertEqual(result["standing"], "unknown")
        self.assertEqual(result["applicability"], "REFUSE")
        self.assertFalse(result["authorized_reuse"])

    def test_invented_claim_id_is_refused(self):
        bundle = self.copy_bundle("invented-claim")
        binding = join.read(bundle / "binding.json")
        binding["claims"][0]["claim_id"] = "c1_" + "a" * 52
        join.write(bundle / "binding.json", binding)
        result = self.inspect(bundle)
        self.assertEqual(result["native_verifier"]["status"], "PASS")
        self.assertEqual(result["binding"], "unbound")
        self.assertEqual(result["applicability"], "REFUSE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
