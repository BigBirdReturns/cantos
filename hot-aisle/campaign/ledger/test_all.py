#!/usr/bin/env python3
"""Run every offline self-test in this directory. Stdlib only. Exit 0 only if all pass.
All builds go to temporary storage; examples/ is never written by this runner.

    python test_all.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
from ledger_common import tmpdir  # noqa: E402

TESTS = [
    ["ledger_validate.py", "--selftest"],
    ["knot_lifecycle.py", "--selftest"],
    ["ledger_build_run1.py", "--selftest"],
    ["ledger_build_run3.py", "--selftest"],
    ["waterline.py", "check-seats"],
    ["waterline.py", "--selftest"],
]


def run(cmd, label):
    print(f"=== {label}")
    r = subprocess.run([sys.executable, "-B"] + cmd, cwd=HERE, capture_output=True, text=True)
    print((r.stdout + r.stderr).rstrip())
    return r.returncode == 0


def main():
    failed = []
    for t in TESTS:
        if not run([os.path.join(HERE, t[0])] + t[1:], " ".join(t)):
            failed.append(" ".join(t))
    with tmpdir("ledger-testall-") as td:
        # the worked example must rebuild from the real results dir (into temp storage) when it exists
        if os.path.isdir(os.path.join(os.path.dirname(HERE), "results", "do-h100")):
            if not run([os.path.join(HERE, "ledger_build_run1.py"), "--out", td], "ledger_build_run1.py (full build from ../results into temp)"):
                failed.append("ledger_build_run1.py full build")
        fx = os.path.join(HERE, "fixtures", "run3-mini")
        if not run([os.path.join(HERE, "ledger_build_run3.py"), os.path.join(fx, "arm-amd-t0"), "--closure", os.path.join(fx, "closure.json"), "--out", td],
                   "ledger_build_run3.py (fixture arm + closure into temp)"):
            failed.append("ledger_build_run3.py fixture build")
        for k in ("knot-30b-coding", "knot-70b-dense", "knot-estate-arm-120b"):
            r = subprocess.run([sys.executable, "-B", os.path.join(HERE, "waterline.py"), "plan", os.path.join(HERE, "fixtures", "knots", k + ".json"),
                                "--availability", os.path.join(HERE, "fixtures", "availability-2026-09-23.jsonl"), "--start-at", "2026-09-29T10:00:00Z",
                                "--json", os.path.join(td, k + ".plan.json")], cwd=HERE, capture_output=True, text=True)
            print(f"=== waterline.py plan {k} (09-29) -> exit {r.returncode}")
            if r.returncode not in (0, 2):
                print(r.stdout + r.stderr); failed.append(f"waterline plan {k}")
    print()
    print("ALL PASSED" if not failed else "FAILED: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
