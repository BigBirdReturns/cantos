#!/usr/bin/env python3
"""Run every offline self-test in this directory. Stdlib only. Exit 0 only if all pass.

    python test_all.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = [
    ["ledger_validate.py", "--selftest"],
    ["knot_lifecycle.py", "--selftest"],
    ["ledger_build_run1.py", "--selftest"],
    ["waterline.py", "check-seats"],
    ["waterline.py", "--selftest"],
]


def main():
    failed = []
    for t in TESTS:
        print(f"=== {' '.join(t)}")
        r = subprocess.run([sys.executable, os.path.join(HERE, t[0])] + t[1:], cwd=HERE, capture_output=True, text=True)
        out = (r.stdout + r.stderr).rstrip()
        print(out)
        if r.returncode != 0:
            failed.append(" ".join(t))
    # the worked example must rebuild and validate from the real results dir when it exists
    if os.path.isdir(os.path.join(os.path.dirname(HERE), "results", "do-h100")):
        print("=== ledger_build_run1.py (full build from ../results)")
        r = subprocess.run([sys.executable, os.path.join(HERE, "ledger_build_run1.py")], cwd=HERE, capture_output=True, text=True)
        print((r.stdout + r.stderr).rstrip())
        if r.returncode != 0:
            failed.append("ledger_build_run1.py full build")
    print()
    print("ALL PASSED" if not failed else "FAILED: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
