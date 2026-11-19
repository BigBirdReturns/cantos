"""Local Git-backed promotion controls. No network credentials or side effects."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.check_release_promotion import inspect


class PromotionPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base / "src"
        self.repo.mkdir()
        self.remote = self.base / "public.git"
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Cantos Test")
        self.git("config", "user.email", "test@localhost.invalid")
        kit = self.repo / "public" / "open-compute" / "maintainer-kit.zip"
        kit.parent.mkdir(parents=True)
        kit.write_bytes(b"pinned recipient artifact")
        self.kit = kit
        self.kit_sha = hashlib.sha256(kit.read_bytes()).hexdigest()
        self.size = kit.stat().st_size
        self.commit("base")
        self.git("clone", "-q", "--bare", str(self.repo), str(self.remote), cwd=self.base)
        self.git("checkout", "-q", "-b", "root")
        (self.repo / "root.txt").write_text("retained accepted root source")
        self.commit("root")
        self.root = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        (self.repo / "public.txt").write_text("public integration")
        self.commit("public")
        self.public = self.git("rev-parse", "HEAD")
        self.git("push", "-q", str(self.remote), "main:main")

    def git(self, *args, cwd=None):
        p = subprocess.run(["git", *args], cwd=cwd or self.repo,
                           check=True, capture_output=True, text=True)
        return p.stdout.strip()

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def audit(self, candidate=None, **kwargs):
        params = {
            "repo": self.repo,
            "candidate": candidate or self.git("rev-parse", "HEAD"),
            "expected_public": self.public,
            "protected_root": self.root,
            "remote": str(self.remote),
            "kit": "public/open-compute/maintainer-kit.zip",
            "expected_sha": self.kit_sha,
            "expected_bytes": self.size,
        }
        params.update(kwargs)
        return inspect(**params)

    def merge(self):
        self.git("merge", "-q", "--no-ff", "-m", "retained root", "root")

    def test_qualifies_joined_exact_lineage(self):
        self.merge()
        result = self.audit()
        self.assertEqual(result["verdict"], "PASS")
        self.assertTrue(all(check["pass"] for check in result["checks"]))

    def test_rejects_public_only_without_root(self):
        report = self.audit()
        self.assertEqual(report["verdict"], "HOLD")
        self.assertFalse(next(x for x in report["checks"]
                              if x["name"] == "root_owner_lineage_preserved")["pass"])

    def test_rejects_root_only_without_public(self):
        self.git("checkout", "-q", "root")
        report = self.audit()
        self.assertEqual(report["verdict"], "HOLD")
        self.assertFalse(next(x for x in report["checks"]
                              if x["name"] == "public_lineage_preserved")["pass"])

    def test_rejects_live_public_ref_move(self):
        self.merge()
        self.git("push", "-q", str(self.remote), "HEAD:main")
        report = self.audit()
        self.assertEqual(report["verdict"], "HOLD")
        self.assertNotEqual(report["observed_public_main"], self.public)

    def test_rejects_modified_tracked_artifact(self):
        self.merge()
        self.kit.write_bytes(b"changed artifact")
        report = self.audit()
        self.assertEqual(report["verdict"], "HOLD")
        checks = {x["name"]: x["pass"] for x in report["checks"]}
        self.assertFalse(checks["tracked_tree_clean"])
        self.assertFalse(checks["exact_kit_bytes_and_sha256"])
        self.assertFalse(checks["kit_matches_committed_blob"])

    def test_rejects_nonexistent_candidate(self):
        self.merge()
        report = self.audit(candidate="0" * 40)
        self.assertEqual(report["verdict"], "HOLD")
        self.assertFalse(next(x for x in report["checks"]
                              if x["name"] == "exact_candidate_head")["pass"])

    def test_rejects_unsafe_kit_path(self):
        self.merge()
        report = self.audit(kit="../outside")
        self.assertEqual(report["verdict"], "HOLD")
        self.assertEqual(report["checks"][0]["name"], "bounded_inputs")
        self.assertFalse(report["checks"][0]["pass"])

    def test_rejects_missing_public_remote(self):
        self.merge()
        report = self.audit(remote=str(self.base / "absent.git"))
        self.assertEqual(report["verdict"], "HOLD")
        self.assertIsNone(report["observed_public_main"])


if __name__ == "__main__":
    unittest.main()
