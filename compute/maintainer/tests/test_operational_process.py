"""Controlled disposable-process recovery and recipient replay tests."""
import copy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
import unittest

from compute.maintainer import operational_process as audit


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux procfs required")
class ProcessContinuityTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="cantos-pid-audit-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pidfile = self.root / "service.pid"
        self.procs = []
        self.start()
        self.plan = {
            "schema": audit.PLAN_SCHEMA, "pidfile": str(self.pidfile),
            "executable": os.readlink("/proc/" + str(self.procs[-1].pid) + "/exe"),
            "samples": 3, "interval_ms": 20}

    def start(self):
        p = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"],
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.procs.append(p)
        self.addCleanup(self.stop, p)
        self.pidfile.write_text(str(p.pid) + "\n")

    def stop(self, p):
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=2)

    def report(self, plan=None):
        plan = plan or self.plan
        return audit.collect(plan)

    def replay(self, report, plan=None):
        raw = audit.canonical(report) + b"\n"
        return audit.verify(raw, plan or self.plan, sha256(raw).hexdigest())

    def test_stable_process(self):
        r = self.report()
        self.assertEqual(r["summary"]["verdict"], "stable_observed")
        self.assertEqual(r["summary"]["observed"], 3)
        self.assertEqual(r["summary"]["distinct_matching_identities"], 1)
        self.assertEqual(self.replay(r)["verdict"], "stable_observed")

    def test_replaced_owned_process(self):
        plan = dict(self.plan, samples=11, interval_ms=40)
        def replace():
            time.sleep(.13)
            self.stop(self.procs[-1])
            self.pidfile.unlink()
            time.sleep(.1)
            self.start()
        t = threading.Thread(target=replace)
        t.start()
        try:
            result = self.report(plan)
        finally:
            t.join(timeout=3)
        self.assertFalse(t.is_alive())
        self.assertEqual(result["summary"]["verdict"], "observed_transition")
        self.assertEqual(result["summary"]["distinct_matching_identities"], 2)
        self.assertGreaterEqual(result["summary"]["missing"], 1)
        self.assertEqual(self.replay(result, plan)["verdict"], "observed_transition")

    def test_missing_pid(self):
        self.pidfile.unlink()
        r = self.report()
        self.assertEqual(r["summary"]["verdict"], "incomplete")
        self.assertEqual(r["summary"]["missing"], 3)
        self.assertEqual(self.replay(r)["verdict"], "incomplete")

    def test_wrong_executable(self):
        p = dict(self.plan, executable="/definitely/not/our/python")
        r = self.report(p)
        self.assertEqual(r["summary"]["wrong_executable"], 3)
        self.assertEqual(r["summary"]["verdict"], "incomplete")
        self.replay(r, p)

    def test_symlink_pidfile_rejected(self):
        real = self.root / "actual.pid"
        self.pidfile.rename(real)
        self.pidfile.symlink_to(real)
        with self.assertRaises(audit.ContinuityError):
            self.report()

    def test_tamper_and_external_digest(self):
        r = self.report()
        h = sha256(audit.canonical(r) + b"\n").hexdigest()
        bad = copy.deepcopy(r)
        bad["summary"]["observed"] = 1
        tampered = audit.canonical(bad) + b"\n"
        with self.assertRaisesRegex(audit.ContinuityError, "digest"):
            audit.verify(tampered, self.plan, h)
        with self.assertRaisesRegex(audit.ContinuityError, "summary"):
            audit.verify(tampered, self.plan, sha256(tampered).hexdigest())

    def test_changed_observation_identity(self):
        r = self.report()
        forged = copy.deepcopy(r)
        forged["rows"][1]["status"] = "wrong_executable"
        with self.assertRaises(audit.ContinuityError):
            self.replay(forged)

    def test_plan_guards(self):
        for change in ({"samples": 129}, {"samples": 1},
                       {"interval_ms": 1}, {"interval_ms": 5001},
                       {"pidfile": "../relative"},
                       {"executable": "relative"}):
            with self.subTest(change=change):
                with self.assertRaises(audit.ContinuityError):
                    audit.validate_plan(dict(self.plan, **change))

    def test_receipt_creation_is_exclusive_private_and_replayable(self):
        target = self.root / "receipt-immutable.json"
        report = self.report()
        payload = audit.canonical(report) + b"\n"
        digest = audit.write_receipt_once(target, payload)
        self.assertEqual(digest, sha256(payload).hexdigest())
        self.assertEqual(audit.read_receipt_bounded(target), payload)
        self.assertEqual(self.replay(report)["verdict"], "stable_observed")
        self.assertEqual(target.stat().st_mode & 0o077, 0)
        with self.assertRaises(FileExistsError):
            audit.write_receipt_once(target, b"replacement")
        self.assertEqual(target.read_bytes(), payload)

    def test_preexisting_symlink_never_overwrites_referenced_file(self):
        victim = self.root / "victim.json"
        victim.write_bytes(b"preserve-original")
        link = self.root / "receipt-link.json"
        link.symlink_to(victim)
        with self.assertRaises(OSError):
            audit.write_receipt_once(link, b"malicious-replacement")
        self.assertEqual(victim.read_bytes(), b"preserve-original")
        with self.assertRaises(OSError):
            audit.read_receipt_bounded(link)

    def test_replay_read_is_bounded_and_requires_regular_file(self):
        oversized = self.root / "oversized.json"
        oversized.write_bytes(b"x" * 131073)
        with self.assertRaisesRegex(audit.ContinuityError, "bounded regular"):
            audit.read_receipt_bounded(oversized)
        with self.assertRaisesRegex(audit.ContinuityError, "bounded regular"):
            audit.read_receipt_bounded(self.root)
        with self.assertRaisesRegex(audit.ContinuityError, "bounded receipt"):
            audit.write_receipt_once(self.root / "too-big.json", b"x" * 131073)
        self.assertFalse((self.root / "too-big.json").exists())

    def test_cli_and_extracted_invocation(self):
        r = self.root / "receipt.json"
        p = self.root / "plan.json"
        p.write_text(json.dumps(self.plan))
        mod = "compute.maintainer.operational_process"
        collected = subprocess.run(
            [sys.executable, "-B", "-m", mod, "collect", "--plan", str(p),
             "--receipt", str(r)], capture_output=True, text=True, timeout=15)
        self.assertEqual(collected.returncode, 0, collected.stderr)
        digest = json.loads(collected.stdout)["sha256"]
        checked = subprocess.run(
            [sys.executable, "-B", "-m", mod, "verify", "--plan", str(p),
             "--receipt", str(r), "--expected-sha256", digest],
            capture_output=True, text=True, timeout=15)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["verdict"], "stable_observed")


if __name__ == "__main__":
    unittest.main()
