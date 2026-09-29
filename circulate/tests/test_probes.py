"""Tests for circulate/probes. Stdlib unittest; run with:  python -m unittest circulate/tests/test_probes.py -v

The slow, real-tool probes (p01..p08, p10) are exercised by running the whole set once (probes/run_probes.py);
here they are loaded and run once each against the real tree (all sub-second to a few seconds), and the
harness pieces (frozen-hash guard, p09 with a fake driver, p11 against a planted secret, exit codes) are
tested against temp fixtures so a FAIL can be seen to happen.
"""
import datetime as dt
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
PROBES = Path(__file__).resolve().parents[1] / "probes"
sys.path.insert(0, str(PROBES))
import _common as C  # noqa: E402

REQUIRED = {"name", "status", "started_utc", "finished_utc", "seconds", "observed", "expected", "notes", "error"}
VALID = {"PASS", "FAIL", "SKIP", "HOLD"}


def load(stem):
    spec = importlib.util.spec_from_file_location("t_" + stem, PROBES / (stem + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def shape_ok(tc, r, name):
    tc.assertEqual(REQUIRED, REQUIRED & set(r), "missing keys")
    tc.assertEqual(r["name"], name)
    tc.assertIn(r["status"], VALID)
    tc.assertIsInstance(r["seconds"], float)
    tc.assertEqual(r["observed"]["frozen_files_moved"], [])


class ProbeFiles(unittest.TestCase):
    def test_eleven_probes_named_per_contract(self):
        names = sorted(p.stem for p in PROBES.glob("p[0-9][0-9]_*.py"))
        self.assertEqual(names, ["p01_packet_tamper", "p02_evidence_tamper", "p03_price_shift", "p04_bad_artifact", "p05_gated_source",
                                 "p06_stale_kit", "p07_r2_perturb", "p08_platform_mislabel", "p09_kill_resume", "p10_dup_artifact",
                                 "p11_secret_scan"])

    def test_every_probe_exposes_run(self):
        for p in PROBES.glob("p[0-9][0-9]_*.py"):
            self.assertTrue(callable(getattr(load(p.stem), "run", None)), p.name)


class RealToolProbes(unittest.TestCase):
    """Each probe against the real tree. They must PASS here; a FAIL means a joint really is not holding."""

    def check(self, stem, allow=("PASS",)):
        r = load(stem).run({"root": str(C.ROOT)})
        shape_ok(self, r, stem)
        self.assertIn(r["status"], allow, r["error"])

    def test_p01(self): self.check("p01_packet_tamper")
    def test_p02(self): self.check("p02_evidence_tamper")
    def test_p03(self): self.check("p03_price_shift", ("PASS", "SKIP"))
    def test_p04(self): self.check("p04_bad_artifact")
    def test_p05(self): self.check("p05_gated_source", ("PASS", "HOLD", "SKIP"))
    def test_p06(self): self.check("p06_stale_kit")
    def test_p07(self): self.check("p07_r2_perturb")
    def test_p08(self): self.check("p08_platform_mislabel")
    def test_p10(self): self.check("p10_dup_artifact")


class Harness(unittest.TestCase):
    def test_p05_offline_is_hold_not_fail(self):
        r = load("p05_gated_source").run({"root": str(C.ROOT), "offline": True})
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["observed"]["attempts"], 0)

    def test_frozen_file_movement_fails_the_probe(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            for rel in C.FROZEN:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("x")

            def body(ctx, work):
                (root / C.FROZEN[0]).write_text("moved")
                return {"observed": {}}
            r = C.execute("pXX_test", body, {"root": str(root)})
            self.assertEqual(r["status"], "FAIL")
            self.assertEqual(r["observed"]["frozen_files_moved"], [C.FROZEN[0]])
            self.assertIn("frozen files moved", r["error"])

    def test_exception_in_probe_is_fail_not_pass(self):
        def body(ctx, work):
            raise RuntimeError("boom")
        r = C.execute("pXX_test", body, {"root": str(C.ROOT)})
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("boom", r["error"])

    def test_work_dir_is_removed(self):
        seen = []

        def body(ctx, work):
            seen.append(work)
            (work / "f").write_text("x")
            return {}
        C.execute("pXX_test", body, {"root": str(C.ROOT)})
        self.assertFalse(seen[0].exists())

    def test_flip_byte_changes_exactly_one_byte(self):
        raw = b'{"a": 1, "html_sha256": "abcdef0123"}'
        out = C.flip_byte_in_json_value(raw, b'"html_sha256": "')
        self.assertEqual(sum(x != y for x, y in zip(raw, out)), 1)
        json.loads(out)

    def test_run_probes_exit_codes_and_shape(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "PROBES.json"
            p = subprocess.run([sys.executable, str(PROBES / "run_probes.py"), "--only", "p10", "p09", "--out", str(out)],
                               capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            doc = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual([x["name"] for x in doc["probes"]], ["p09_kill_resume", "p10_dup_artifact"])
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(doc["frozen_files"]["moved"], [])
            self.assertEqual(doc["frozen_files"]["checked"], 11)


class P11(unittest.TestCase):
    def repo(self, t, content):
        root = Path(t)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        for d in ("circulate", "hot-aisle", "clustermax-challenge", "research-desk"):
            (root / d).mkdir()
            (root / d / "ok.txt").write_text("nothing here\n")
        (root / "hot-aisle" / "leak.txt").write_text(content)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        return root

    def test_clean_tree_passes(self):
        with tempfile.TemporaryDirectory() as t:
            r = load("p11_secret_scan").run({"root": str(self.repo(t, "clean\n"))})
            self.assertEqual(r["status"], "PASS", r["error"])
            self.assertEqual(r["observed"]["hits"], 0)

    def test_each_pattern_is_caught(self):
        # secrets are built from fragments so this test file itself stays clean
        samples = {"slack_webhook_host": "https://hooks" + ".slack.com/services/T0/B0/x",
                   "aws_access_key_id": "AK" + "IA" + "ABCDEFGHIJKLMNOP",
                   "github_pat": "gh" + "p_" + "a" * 36,
                   "slack_token": "xo" + "xb-123",
                   "stripe_live_key": "sk_" + "live_abc",
                   "private_key_block": "-----" + "BEGIN " + "RSA KEY-----"}
        for pattern, text in samples.items():
            with tempfile.TemporaryDirectory() as t:
                r = load("p11_secret_scan").run({"root": str(self.repo(t, "x\n" + text + "\n"))})
                self.assertEqual(r["status"], "FAIL", pattern)
                self.assertEqual(r["observed"]["hit_locations"][0]["pattern"], pattern)
                self.assertNotIn(text, json.dumps(r), "the matched secret must not be echoed")


FAKE_DRIVER = textwrap.dedent('''
    import argparse, datetime as dt, json, os, sys, time
    from pathlib import Path
    ap = argparse.ArgumentParser(); ap.add_argument("--offline", action="store_true"); ap.add_argument("--resume"); ap.add_argument("--retained")
    a = ap.parse_args()
    here = Path(__file__).resolve().parent
    date = a.resume or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    d = here / "receipts" / date; d.mkdir(parents=True, exist_ok=True)
    now = lambda: dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stages = ["alpha", "beta"]
    inj = os.environ.get("CIRCULATE_INJECT_SLEEP_STAGE")
    if inj: name, secs = inj.split(":"); stages.append(name)
    for s in stages:
        f = d / ("stage-" + s + ".json")
        if f.exists() and json.loads(f.read_text())["status"] in ("OK", "HOLD", "SKIP"): continue
        print("stage", s, flush=True)
        t0 = now()
        if inj and s == name: (d / ("started-" + s + ".txt")).write_text(t0); time.sleep(float(secs))
        time.sleep(1.1 if s != name else 0)
        f.write_text(json.dumps({"name": s, "status": "OK", "started_utc": t0, "finished_utc": now(), "seconds": 0.0}))
    recs = [json.loads((d / ("stage-" + s + ".json")).read_text()) for s in stages]
    (d / "RECEIPT.json").write_text(json.dumps({"date": date, "overall": "OK", "stages": recs}))
''')


class P09(unittest.TestCase):
    def test_skip_when_driver_absent(self):
        r = load("p09_kill_resume").run({"root": str(C.ROOT), "circulate_py": str(Path(tempfile.gettempdir()) / "no-such-circulate.py")})
        self.assertEqual(r["status"], "SKIP")
        self.assertIn("does not exist", r["notes"])

    def test_kill_and_resume_against_fake_driver(self):
        with tempfile.TemporaryDirectory() as t:
            drv = Path(t) / "circulate.py"
            drv.write_text(FAKE_DRIVER)
            r = load("p09_kill_resume").run({"root": str(C.ROOT), "circulate_py": str(drv), "sleep_seconds": 60, "wait_start_seconds": 30})
            self.assertEqual(r["status"], "PASS", r["error"])
            o = r["observed"]
            self.assertEqual(sorted(o["reused_by_hash"]), ["alpha", "beta"])
            self.assertEqual(o["completed_stages_rerun"], [])
            self.assertEqual(o["killed_stage_after_resume"]["status"], "OK")
            # restored: no receipts left behind
            today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            self.assertFalse((Path(t) / "receipts" / today).exists())

    def test_fails_when_driver_reruns_completed_stages(self):
        bad = FAKE_DRIVER.replace('if f.exists() and json.loads(f.read_text())["status"] in ("OK", "HOLD", "SKIP"): continue', "pass")
        with tempfile.TemporaryDirectory() as t:
            drv = Path(t) / "circulate.py"
            drv.write_text(bad)
            r = load("p09_kill_resume").run({"root": str(C.ROOT), "circulate_py": str(drv), "sleep_seconds": 60, "wait_start_seconds": 30})
            self.assertEqual(r["status"], "FAIL")
            self.assertIn("re-run", r["error"])


if __name__ == "__main__":
    unittest.main()
