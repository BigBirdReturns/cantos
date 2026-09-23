#!/usr/bin/env python3
"""Run every offline self-test in this lane. Stdlib only. Exit 0 only if all pass. Builds go to temporary storage.

    python test_all.py
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True

TESTS = [
    ["import_tierbench.py", "--selftest"],
    ["tier_waterline.py", "--selftest"],
]


def run(cmd, label, cwd=HERE):
    print(f"=== {label}")
    r = subprocess.run([sys.executable, "-B"] + cmd, cwd=cwd, capture_output=True, text=True)
    print((r.stdout + r.stderr).rstrip())
    return r.returncode


def main():
    failed = []
    for t in TESTS:
        if run([os.path.join(HERE, t[0])] + t[1:], " ".join(t)) != 0:
            failed.append(" ".join(t))
    with tempfile.TemporaryDirectory(prefix="tierbench-bridge-testall-") as td:
        ev = os.path.join(td, "evidence")
        if run([os.path.join(HERE, "import_tierbench.py"), "--fixtures", "--out", ev], "import_tierbench.py --fixtures (into temp)") != 0:
            failed.append("import_tierbench.py --fixtures")
        for start in ("2026-09-24T18:00:00Z", "2026-09-29T10:00:00Z"):
            rc = run([os.path.join(HERE, "tier_waterline.py"), "plan", os.path.join(HERE, "fixtures", "knots", "knot-run3-evalplus-tierbench.json"),
                      "--evidence", ev, "--availability", os.path.join(HERE, "..", "ledger", "fixtures", "availability-2026-09-23.jsonl"),
                      "--start-at", start, "--json", os.path.join(td, f"plan-{start[:10]}.json")], f"tier_waterline.py plan (start {start})")
            print(f"    -> exit {rc}")
            if rc not in (0, 2):
                failed.append(f"tier_waterline plan {start}")
        # the ledger lane's own planner must still pass untouched (we import it; we never edit it)
        if run([os.path.join(HERE, "..", "ledger", "waterline.py"), "--selftest"], "../ledger/waterline.py --selftest (imported, unmodified)", cwd=os.path.join(HERE, "..", "ledger")) != 0:
            failed.append("../ledger/waterline.py --selftest")
    print()
    print("ALL PASSED" if not failed else "FAILED: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
