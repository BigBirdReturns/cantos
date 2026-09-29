#!/usr/bin/env python3
"""Run every circulate probe and write PROBES.json.

    python circulate/probes/run_probes.py [--out PATH] [--only p03 p07 ...] [--offline]

Default --out is circulate/receipts/<today UTC>/PROBES.json. Exit 0 only if no probe FAILed
(PASS, SKIP and HOLD do not fail the run). Each probe is p??_<name>.py exposing run(ctx) -> ProbeResult.
"""
import argparse
import datetime as dt
import importlib.util
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import _common as C  # noqa: E402


def discover(only=None):
    mods = []
    for f in sorted(HERE.glob("p[0-9][0-9]_*.py")):
        if only and not any(f.name.startswith(o) for o in only):
            continue
        mods.append(f)
    return mods


def load_and_run(f, ctx):
    name = f.stem
    try:
        spec = importlib.util.spec_from_file_location("circulate_probe_" + name, f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.run(ctx)
    except Exception as e:  # a probe that cannot even load is a FAIL
        now = C.utc_now()
        return {"name": name, "status": "FAIL", "started_utc": now, "finished_utc": now, "seconds": 0.0, "observed": {},
                "expected": None, "notes": "", "error": "probe failed to load/run: %s: %s" % (type(e).__name__, e)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--only", nargs="*", default=None, help="probe file prefixes, e.g. p03 p07")
    ap.add_argument("--offline", action="store_true", help="no network: p05 returns HOLD without a request")
    a = ap.parse_args(argv)
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    out = a.out or (C.CIRCULATE / "receipts" / today / "PROBES.json")
    ctx = {"root": str(C.ROOT), "date": today, "offline": a.offline}
    t0, started = time.time(), C.utc_now()
    frozen_before = C.frozen_hashes()
    results = [load_and_run(f, ctx) for f in discover(a.only)]
    frozen_after = C.frozen_hashes()
    moved = sorted(k for k in frozen_before if frozen_before[k] != frozen_after[k])
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    failed = counts.get("FAIL", 0) > 0 or bool(moved)
    doc = {"schema": "circulate/probes@1", "date": today, "started_utc": started, "finished_utc": C.utc_now(),
           "seconds": round(time.time() - t0, 3), "overall": "FAIL" if failed else ("PASS" if set(counts) <= {"PASS"} else "PASS_WITH_HOLDS"),
           "counts": counts, "frozen_files": {"checked": len(frozen_before), "moved": moved, "sha256": frozen_after},
           "probes": results}
    C.write_json(out, doc)
    for r in results:
        print("%-4s %-24s %7.2fs  %s" % (r["status"], r["name"], r["seconds"], (r.get("error") or "")[:110]))
    print("wrote", out, "| counts", counts, "| frozen moved", moved or "none")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
