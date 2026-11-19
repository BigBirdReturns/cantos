"""Read-only storage observation, replay, and negative-control qualification."""
import copy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from compute.maintainer import operational_storage as storage


class StorageReadbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="cantos-storage-test-")
        self.addCleanup(self.tmp.cleanup)
        self.parent = Path(self.tmp.name)
        self.root = self.parent / "owned"
        (self.root / "nested").mkdir(parents=True)
        self.expected = b"recipient-readback-evidence\x00" * 40
        (self.root / "nested" / "evidence.bin").write_bytes(self.expected)
        self.plan = {"schema": storage.PLAN_SCHEMA, "samples": 2,
                     "entries": [{"path": "nested/evidence.bin",
                                  "bytes": len(self.expected),
                                  "sha256": sha256(self.expected).hexdigest()}]}

    def test_collector_and_independent_receipt_replay(self):
        receipt = storage.collect(self.root, self.plan)
        self.assertEqual(receipt["summary"], {"passed": 2, "total": 2, "verdict": "pass"})
        for row in receipt["observations"]:
            self.assertEqual(row["bytes"], len(self.expected))
            self.assertEqual(row["sha256"], sha256(self.expected).hexdigest())
            self.assertGreaterEqual(row["elapsed_ms"], 0)
        replay = storage.verify(receipt, self.plan)
        self.assertEqual(replay["verdict"], "pass")
        self.assertIn("not collector authentication", replay["replay_scope"])

    def test_real_corruption_fails_and_offline_replays(self):
        (self.root / "nested" / "evidence.bin").write_bytes(b"tamper")
        receipt = storage.collect(self.root, self.plan)
        self.assertEqual(receipt["summary"]["verdict"], "fail")
        self.assertTrue(all(o["status"] == "mismatch" for o in receipt["observations"]))
        self.assertEqual(storage.verify(receipt, self.plan)["verdict"], "fail")

    def test_missing_file_is_failed_observation(self):
        (self.root / "nested" / "evidence.bin").unlink()
        receipt = storage.collect(self.root, self.plan)
        self.assertEqual(receipt["summary"]["verdict"], "fail")
        self.assertEqual(receipt["observations"][0]["status"], "unreadable")
        self.assertEqual(storage.verify(receipt, self.plan)["verdict"], "fail")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "requires no-follow open")
    def test_symlink_file_and_directory_are_not_followed(self):
        secret = self.parent / "secret.txt"
        secret.write_text("private", encoding="utf-8")
        (self.root / "nested" / "evidence.bin").unlink()
        (self.root / "nested" / "evidence.bin").symlink_to(secret)
        r = storage.collect(self.root, self.plan)
        self.assertEqual(r["observations"][0]["status"], "unreadable")
        (self.root / "nested" / "evidence.bin").unlink()
        (self.root / "nested").rmdir()
        (self.root / "nested").symlink_to(self.parent, target_is_directory=True)
        self.assertEqual(storage.collect(self.root, self.plan)["observations"][0]["status"],
                         "unreadable")

    def test_unsafe_paths_and_read_budgets_rejected(self):
        bad = ("../secret", "/etc/passwd", "nested/../secret", "nested//file",
               "nested\\file", "./nested", "nested/.", "nested/evidence.bin/")
        for path in bad:
            with self.subTest(path=path):
                plan = copy.deepcopy(self.plan)
                plan["entries"][0]["path"] = path
                with self.assertRaises(storage.StorageAuditError):
                    storage.validate_plan(plan)
        plan = copy.deepcopy(self.plan)
        plan["entries"][0]["bytes"] = storage.MAX_FILE_BYTES + 1
        with self.assertRaises(storage.StorageAuditError):
            storage.validate_plan(plan)
        plan = copy.deepcopy(self.plan)
        plan["entries"] *= 2
        with self.assertRaises(storage.StorageAuditError):
            storage.validate_plan(plan)

    def test_invalid_root_symlink_rejected(self):
        redirect = self.parent / "redirect"
        redirect.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(storage.StorageAuditError):
            storage.collect(redirect, self.plan)

    def test_forged_success_fails_replay(self):
        receipt = storage.collect(self.root, self.plan)
        attacks = []
        altered = copy.deepcopy(receipt)
        altered["observations"][0]["sha256"] = "0" * 64
        attacks.append(altered)
        altered = copy.deepcopy(receipt)
        altered["summary"]["passed"] = 1
        attacks.append(altered)
        altered = copy.deepcopy(receipt)
        altered["observations"][0]["sample"] = 1
        attacks.append(altered)
        altered = copy.deepcopy(receipt)
        altered["observations"][0]["elapsed_ms"] = float("nan")
        attacks.append(altered)
        altered = copy.deepcopy(receipt)
        altered["plan_sha256"] = "0" * 64
        attacks.append(altered)
        for i, tampered in enumerate(attacks):
            with self.subTest(i=i), self.assertRaises(storage.StorageAuditError):
                storage.verify(tampered, self.plan)

    def test_cli_collect_and_verify_from_package(self):
        plan_path = self.parent / "plan.json"
        receipt_path = self.parent / "result.json"
        plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        script = Path(storage.__file__)
        one = subprocess.run([sys.executable, "-B", str(script), "collect",
                              "--root", str(self.root), "--plan", str(plan_path),
                              "--output", str(receipt_path)], capture_output=True, text=True)
        self.assertEqual(one.returncode, 0, one.stderr)
        two = subprocess.run([sys.executable, "-B", str(script), "verify",
                              "--plan", str(plan_path), "--receipt", str(receipt_path)],
                             capture_output=True, text=True)
        self.assertEqual(two.returncode, 0, two.stderr)
        self.assertIn("verified_receipt_sha256", two.stdout)
        negative = subprocess.run([sys.executable, "-B", str(script), "collect",
                                   "--root", str(self.root), "--plan", str(plan_path),
                                   "--output", str(self.root / "forbidden.json")],
                                  capture_output=True, text=True)
        self.assertEqual(negative.returncode, 3)
        self.assertFalse((self.root / "forbidden.json").exists())


if __name__ == "__main__":
    unittest.main()
