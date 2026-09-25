#!/usr/bin/env python3
"""diagnose.py -- shop evaluation diagnosis kit.

Evaluates a GPU compute shop against Hot Aisle as the reference operator, using up
to three optional inputs (a counter record, a node fingerprint, a workload bench)
plus a reference bundle. Every rule and layer is documented in RUBRIC.md; this file
implements it. Python 3.9+, standard library only.

Usage:
    python diagnose.py --counter <file> --fingerprint <file> --bench <engine table
        or cells dir> --reference reference/hotaisle-2026-09.json --out REPORT.md
        [--json]

Every input is optional. A missing input produces, per layer, a note explaining
what to run to get it, instead of a crash.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from adapt import adapt_counter, adapt_fingerprint  # noqa: E402
DEFAULT_REFERENCE = os.path.join(SCRIPT_DIR, "reference", "hotaisle-2026-09.json")

# ---------------------------------------------------------------------------
# Rule impact weights (higher = more leverage on $/1k accepted, throughput or
# uptime). Used only to rank "first three things to change". See RUBRIC.md.
# ---------------------------------------------------------------------------
RULE_WEIGHT = {
    "PRICE-02": 100, "STK-01": 90, "HW-01": 85, "PWR-01": 80, "HEALTH-01": 75,
    "FLEET-01": 70, "STK-02": 65, "HW-03": 60, "TEN-01": 55, "PRICE-01": 50,
    "HW-02": 45, "PRICE-03": 40, "TEN-02": 35, "HEALTH-02": 30, "CNT-01": 25,
    "CNT-02": 20, "PROOF-01": 15, "PROOF-02": 10,
}

HOWTO = {
    "counter": (
        "fill a record per `../counter/PROTOCOL.md` into `../counter/records/<shop>-<yyyy-mm>.json`, "
        "check it with `python ../counter/counter_record.py validate <file>`, then pass `--counter <that file>` "
        "(it is scored here; `public_proof` is an optional block, see RUBRIC.md)."
    ),
    "fingerprint": (
        "run `bash ../probe/fingerprint.sh auto <outdir>` on the rented machine "
        "(with torch importable or the vllm container running for the 60 s load sample) "
        "and pass `--fingerprint <outdir>/fingerprint.json`."
    ),
    "bench": (
        "produce it with `node engine_table.cjs <resultsDir> <rate> <ttft_ms> "
        "<e2e_ms> > table.json` and pass `--bench table.json`, or point `--bench` "
        "at a directory of raw `cell-<name>-r<n>.json` files."
    ),
    "reference": (
        "pass `--reference reference/hotaisle-2026-09.json` (shipped with this kit)."
    ),
}


def howto_for(missing_what: str) -> str:
    for key in ("counter", "fingerprint", "bench", "reference"):
        if missing_what.startswith(key):
            return HOWTO[key]
    return "see RUBRIC.md for how to produce this input."


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_json_file(path):
    """Returns (data, error_string_or_None)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, f"file not found: {path}"
    except json.JSONDecodeError as e:
        return None, f"invalid JSON in {path}: {e}"
    except OSError as e:
        return None, f"could not read {path}: {e}"


def load_counter(path):
    if not path:
        return None, None
    data, err = load_json_file(path)
    if err:
        return None, err
    try:
        return adapt_counter(data), None
    except Exception as e:  # a raw counter record that fails its own scorer
        return None, f"counter record could not be scored: {e}"


def load_fingerprint(path, counter=None):
    if not path:
        return None, None
    data, err = load_json_file(path)
    if err:
        return None, err
    try:
        return adapt_fingerprint(data, counter), None
    except Exception as e:
        return None, f"fingerprint could not be adapted: {e}"


def load_reference(path):
    if not path:
        return None, None
    data, err = load_json_file(path)
    if err:
        return None, err
    return data, None


def normalize_engine_table(data, source):
    cells = []
    for c in data.get("cells", []):
        completed = c.get("completed")
        attempted = c.get("attempted")
        if attempted is not None and completed is not None:
            failed = attempted - completed
        else:
            failed = None
        cells.append({
            "cell": c.get("cell"),
            "completed": completed,
            "attempted": attempted,
            "failed": failed,
            "accepted": c.get("accepted"),
            "accepted_pct": c.get("accepted_pct"),
            "cost_per_1k": c.get("cost_per_1k"),
            "ttft_p50_ms": None,
            "ttft_p95_ms": None,
            "ttft_p99_ms": None,
        })
    return {
        "kind": "engine_table",
        "source": source,
        "gates": data.get("gates"),
        "engine": data.get("engine"),
        "cells": cells,
    }


def aggregate_raw_cells(cellfiles, source):
    groups = OrderedDict()
    for fp in sorted(cellfiles):
        base = os.path.basename(fp)
        key = re.sub(r"-r\d+\.json$", "", base)
        groups.setdefault(key, []).append(fp)

    cells = []
    for key, files in groups.items():
        completed = failed = attempted = 0
        p50s, p95s, p99s = [], [], []
        for fp in sorted(files):
            d, err = load_json_file(fp)
            if err or d is None:
                continue
            c = d.get("completed") or 0
            fl = d.get("failed") or 0
            completed += c
            failed += fl
            np_ = d.get("num_prompts")
            attempted += np_ if np_ is not None else (c + fl)
            for field, bucket in (
                ("p50_ttft_ms", p50s), ("p95_ttft_ms", p95s), ("p99_ttft_ms", p99s)
            ):
                v = d.get(field)
                if v is not None:
                    bucket.append(v)
        cells.append({
            "cell": key,
            "completed": completed,
            "attempted": attempted,
            "failed": failed,
            # Raw benchmark cells carry no correctness grading (that requires the
            # report engine in ../index.html against an EvalPlus-style oracle), so
            # acceptance/cost are unobserved from this input shape.
            "accepted": None,
            "accepted_pct": None,
            "cost_per_1k": None,
            "ttft_p50_ms": (sum(p50s) / len(p50s)) if p50s else None,
            "ttft_p95_ms": (sum(p95s) / len(p95s)) if p95s else None,
            "ttft_p99_ms": (sum(p99s) / len(p99s)) if p99s else None,
        })
    return {"kind": "raw_cells", "source": source, "gates": None, "engine": None, "cells": cells}


def load_bench(path):
    if not path:
        return None, None
    if os.path.isdir(path):
        for name in ("table.json", "engine-table.json", "engine_table.json"):
            cand = os.path.join(path, name)
            if os.path.isfile(cand):
                data, err = load_json_file(cand)
                if err:
                    return None, err
                if isinstance(data, dict) and "cells" in data:
                    return normalize_engine_table(data, cand), None
        cellfiles = glob.glob(os.path.join(path, "cell-*.json"))
        if not cellfiles:
            return None, f"no engine-table json or cell-*.json files found under {path}"
        return aggregate_raw_cells(cellfiles, path), None
    else:
        data, err = load_json_file(path)
        if err:
            return None, err
        if isinstance(data, dict) and "cells" in data:
            return normalize_engine_table(data, path), None
        return None, f"{path} is not a recognized engine-table JSON (no 'cells' key)"


# ---------------------------------------------------------------------------
# Small dict-path helper
# ---------------------------------------------------------------------------

def g(d, *path, default=None):
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def missing(what):
    return {"status": "MISSING", "reason": what}


def wrong(observation, action, effect):
    return {"status": "WRONG", "observation": observation, "action": action, "effect": effect}


def right(observation):
    return {"status": "RIGHT", "observation": observation}


# ---------------------------------------------------------------------------
# Rules. Each takes (counter, fingerprint, bench, reference) and returns a
# result dict from missing()/wrong()/right(). See RUBRIC.md for prose.
# ---------------------------------------------------------------------------

def rule_cnt_01(counter, fp, bench, ref):
    if not counter:
        return missing("counter record")
    score = counter.get("score")
    if score is None:
        return missing("counter.score field")
    if score < 70:
        return wrong(
            f"counter score {score} (< 70)",
            "fix the single lowest-scoring dimension first (see CNT-02), then "
            "re-run `counter_record.py score`.",
            "overall counter score rises",
        )
    return right(f"counter score {score} (>= 70)")


def rule_cnt_02(counter, fp, bench, ref):
    if not counter:
        return missing("counter record")
    dims = counter.get("dimensions") or {}
    scores = {
        k: v.get("score") for k, v in dims.items()
        if isinstance(v, dict) and isinstance(v.get("score"), (int, float))
    }
    if len(scores) < 2:
        return missing("counter.dimensions with at least 2 scored dimensions")
    avg = sum(scores.values()) / len(scores)
    worst_name = min(scores, key=lambda k: scores[k])
    worst = scores[worst_name]
    spread = avg - worst
    if spread > 30:
        return wrong(
            f"dimension spread {spread:.1f} pts (avg {avg:.1f} vs '{worst_name}' at {worst:.1f})",
            f"put effort into the '{worst_name}' dimension specifically rather than "
            "a broad pass; re-score and confirm the spread narrows.",
            "overall counter score rises faster per unit of effort than an "
            "across-the-board pass would",
        )
    return right(f"dimension spread {spread:.1f} pts (<= 30)")


def rule_pwr_01(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    gpus = fp.get("gpus") or []
    if not gpus:
        return missing("fingerprint.gpus")
    if not any(gpu.get("sustained_60s") for gpu in gpus):
        return missing("fingerprint.gpus[].sustained_60s (60s sustained-load sample)")
    bad = []
    for i, gpu in enumerate(gpus):
        s = gpu.get("sustained_60s") or {}
        if s.get("throttled") is True:
            bad.append(f"gpu{i}: throttled=true")
            continue
        c0, c1 = s.get("clock_mhz_start"), s.get("clock_mhz_end")
        if c0 and c1 is not None and c0 > 0:
            drop = (c0 - c1) / c0
            if drop > 0.15:
                bad.append(f"gpu{i}: clock dropped {drop * 100:.0f}% over 60s ({c0}->{c1} MHz)")
    if bad:
        return wrong(
            "; ".join(bad),
            "fix airflow/PSU headroom or raise the BIOS power/thermal limit; "
            "re-run the 60s sustained sample and confirm clocks stay flat.",
            "bench TTFT p99 and accepted_pct at high concurrency improve; "
            "$/1k accepted falls",
        )
    return right("sustained clocks held within 15% across the 60s sample on all GPUs, not throttled")


def rule_hw_01(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    gpus = fp.get("gpus") or []
    if not gpus:
        return missing("fingerprint.gpus")
    bad = []
    for i, gpu in enumerate(gpus):
        gen, gen_max = gpu.get("pcie_gen"), gpu.get("pcie_gen_max")
        width, width_max = gpu.get("pcie_width"), gpu.get("pcie_width_max")
        if gen is None or gen_max is None or width is None or width_max is None:
            continue
        if gen < gen_max or width < width_max:
            bad.append(f"gpu{i}: negotiated gen{gen} x{width} of a gen{gen_max} x{width_max} part")
    if not any(
        gpu.get("pcie_gen") is not None and gpu.get("pcie_gen_max") is not None
        for gpu in gpus
    ):
        return missing("fingerprint.gpus[].pcie_gen/pcie_gen_max/pcie_width/pcie_width_max")
    if bad:
        return wrong(
            "; ".join(bad),
            "reseat the card, update host BIOS, check slot bifurcation; re-read "
            "pcie_gen/pcie_width from a fresh fingerprint and re-run the "
            "plateaued bench cell.",
            "throughput ceiling and accepted_per_s rise at the same concurrency",
        )
    return right("all GPUs negotiated at full rated PCIe generation and width")


def rule_hw_02(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    gpus = fp.get("gpus") or []
    if not gpus:
        return missing("fingerprint.gpus")
    bad = []
    any_reported = False
    for i, gpu in enumerate(gpus):
        age = gpu.get("firmware_age_days")
        if age is None:
            continue
        any_reported = True
        if age > 270:
            bad.append(f"gpu{i}: firmware_age_days={age} (> 270)")
    if not any_reported:
        return missing("fingerprint.gpus[].firmware_age_days (VBIOS is in the fingerprint; the age needs the vendor release date, fill it by hand)")
    if bad:
        return wrong(
            "; ".join(bad),
            "update to the vendor-qualified VBIOS/firmware matching the "
            "driver/ROCm branch in use; re-read the fingerprint and soak-test.",
            "RAS error counters and TTFT p99 drop; firmware age resets to near zero",
        )
    return right("firmware age reported and within 270 days on all GPUs")


def rule_hw_03(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    gpus = fp.get("gpus") or []
    if not gpus:
        return missing("fingerprint.gpus")
    if not any(
        gpu.get("ras_errors_uncorrectable") is not None
        or gpu.get("ras_errors_correctable") is not None
        for gpu in gpus
    ):
        return missing("fingerprint.gpus[].ras_errors_correctable/ras_errors_uncorrectable")
    bad = []
    for i, gpu in enumerate(gpus):
        unc = gpu.get("ras_errors_uncorrectable") or 0
        cor = gpu.get("ras_errors_correctable") or 0
        if unc > 0:
            bad.append(f"gpu{i}: {unc} uncorrectable RAS error(s)")
        elif cor > 100:
            bad.append(f"gpu{i}: {cor} correctable RAS errors (> 100)")
    if bad:
        return wrong(
            "; ".join(bad),
            "RMA or reseat the card; re-sample RAS counters over a repeat 60s "
            "window and confirm flat.",
            "bench `failed` count converges to 0; accepted_pct rises",
        )
    return right("no uncorrectable RAS errors, correctable counts low on all GPUs")


def rule_stk_01(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    ref_version = g(ref, "stack", "driver_or_rocm_version")
    if not ref_version:
        return missing("reference.stack.driver_or_rocm_version")
    gpus = fp.get("gpus") or []
    if not gpus:
        return missing("fingerprint.gpus")
    bad = []
    any_reported = False
    for i, gpu in enumerate(gpus):
        v = gpu.get("driver_or_rocm_version")
        if not v:
            continue
        any_reported = True
        if v != ref_version:
            bad.append(f"gpu{i}: {v} (qualified reference is {ref_version})")
    if not any_reported:
        return missing("fingerprint.gpus[].driver_or_rocm_version")
    if bad:
        return wrong(
            "; ".join(bad),
            "upgrade to the qualified ROCm/CUDA + matching serving-image digest; "
            "re-read the fingerprint driver version and re-run the same bench cell.",
            "output_throughput/accepted_per_s rise, cost_per_1k falls",
        )
    return right(f"driver/ROCm version matches the qualified reference ({ref_version}) on all GPUs")


def rule_stk_02(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    backend = g(fp, "observed_backend", "attention_backend")
    if backend is None:
        return missing("fingerprint.observed_backend.attention_backend (record the serving backend, e.g. VLLM_ATTENTION_BACKEND, next to the fingerprint)")
    if str(backend).strip() == "" or str(backend).lower() == "unknown":
        return wrong(
            "fingerprint.observed_backend.attention_backend is missing/unknown",
            "have the shop expose backend/runtime identity in a per-session "
            "capture (own env.json-equivalent); diff it across runs.",
            "reproducible TTFT tail; regressions become attributable instead of mysterious",
        )
    return right(f"observed attention backend reported: {backend}")


def rule_fleet_01(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    seconds = g(fp, "provisioning", "seconds_to_ssh")
    if seconds is None:
        return missing("fingerprint.provisioning.seconds_to_ssh")
    ref_seconds = g(ref, "provisioning", "seconds_to_ssh")
    ref_note = f" (reference: {ref_seconds}s)" if ref_seconds is not None else ""
    if seconds > 300:
        return wrong(
            f"seconds_to_ssh={seconds}{ref_note}",
            "pre-warm golden images / automate the fleet provisioner instead of "
            "manual console steps; re-time request-to-SSH-ready on a fresh seat.",
            "whole-window $/1k accepted moves toward the own-window figure",
        )
    return right(f"seconds_to_ssh={seconds}{ref_note}, within the 5-minute bound")


def rule_health_01(counter, fp, bench, ref):
    if not bench:
        return missing("bench")
    cells = bench.get("cells") or []
    if not cells:
        return missing("bench cells")
    total_failed = 0
    any_known = False
    for c in cells:
        if c.get("failed") is not None:
            any_known = True
            total_failed += c["failed"]
    if not any_known:
        return missing("bench cell failed/attempted-completed counts")
    if total_failed > 0:
        return wrong(
            f"{total_failed} failed request(s) across bench cells",
            "pull serve logs for the failing cell, fix the OOM/timeout/config "
            "cause, re-run.",
            "completed/attempted and accepted_pct converge upward",
        )
    return right("zero failed requests across bench cells")


def rule_health_02(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    gpus = fp.get("gpus") or []
    if not gpus:
        return missing("fingerprint.gpus")
    bad = []
    any_checked = False
    for i, gpu in enumerate(gpus):
        idle_w = gpu.get("idle_power_w")
        loaded_w = g(gpu, "sustained_60s", "power_w_end") or g(gpu, "sustained_60s", "power_w_start")
        if idle_w is None or loaded_w is None or loaded_w <= 0:
            continue
        any_checked = True
        if idle_w > 0.6 * loaded_w:
            bad.append(f"gpu{i}: idle reading {idle_w}W is {idle_w / loaded_w * 100:.0f}% of the loaded reading {loaded_w}W (not idle before the sample)")
    if not any_checked:
        return missing("fingerprint.gpus[].idle_power_w and sustained_60s.power_w_end")
    if bad:
        return wrong(
            "; ".join(bad),
            "get the shop to confirm exclusive single-tenant allocation; "
            "re-sample idle power after confirming nothing else is scheduled.",
            "std_ttft_ms on low-concurrency cells shrinks",
        )
    return right("each GPU was idle before the sustained-load sample (idle power well below loaded power)")


def rule_ten_01(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    virt = fp.get("virtualization")
    if virt is None:
        return missing("fingerprint.virtualization")
    if virt != "vm":
        return right(f"virtualization={virt} (ACS/hugepages check only applies to VMs)")
    acs = fp.get("acs_enabled")
    huge = fp.get("hugepages_enabled")
    if acs is None and huge is None:
        return missing("fingerprint.acs_enabled/hugepages_enabled")
    if acs is False or huge is False:
        bad = []
        if acs is False:
            bad.append("acs_enabled=false")
        if huge is False:
            bad.append("hugepages_enabled=false")
        return wrong(
            "virtualization=vm, " + ", ".join(bad),
            "enable the ACS override patch and reserve hugepages at boot; "
            "re-read the fingerprint flags.",
            "std_itl_ms/std_tpot_ms drop",
        )
    return right("virtualization=vm with ACS override and hugepages both enabled")


def rule_ten_02(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    numa_nodes = g(fp, "cpu", "numa_nodes")
    if not isinstance(numa_nodes, (int, float)):
        return missing("fingerprint.cpu.numa_nodes")
    if numa_nodes <= 1:
        return right(f"numa_nodes={numa_nodes} (single NUMA node, pinning not applicable)")
    pinned = g(fp, "container_runtime", "numa_pinning")
    if pinned is None:
        return missing("fingerprint.container_runtime.numa_pinning")
    if pinned is False:
        return wrong(
            f"numa_nodes={numa_nodes}, container_runtime.numa_pinning=false",
            "pin the serving process/container to the local NUMA node and "
            "enable cgroup limits; re-read container_runtime.numa_pinning.",
            "p95/p99 TTFT and TPOT tail tighten",
        )
    return right(f"numa_nodes={numa_nodes}, serving process pinned to local NUMA node")


def rule_price_01(counter, fp, bench, ref):
    if not counter:
        return missing("counter record")
    billing = counter.get("billing_granularity")
    if not billing:
        return missing("counter.billing_granularity")
    if billing in ("per-hour", "unknown"):
        return wrong(
            f"billing_granularity={billing}",
            "negotiate or enable sub-hour billing; check invoice line-item "
            "granularity after the change.",
            "whole-window $/1k accepted moves toward own-window $/1k accepted",
        )
    return right(f"billing_granularity={billing} (sub-hour)")


def rule_price_02(counter, fp, bench, ref):
    if not bench:
        return missing("bench")
    ref_val = g(ref, "run3_a_t0", "cost_per_1k_accepted_own_window_usd")
    if ref_val is None:
        return missing("reference.run3_a_t0.cost_per_1k_accepted_own_window_usd")
    candidates = [
        c for c in (bench.get("cells") or [])
        if c.get("cost_per_1k") is not None and c.get("accepted_pct") is not None
    ]
    if not candidates:
        return missing(
            "bench cell cost_per_1k/accepted_pct (raw cell-*.json files carry no "
            "correctness grading; run engine_table.cjs to get these)"
        )
    best = max(candidates, key=lambda c: (c["accepted_pct"], -c["cost_per_1k"]))
    if best["cost_per_1k"] > ref_val * 1.05:
        return wrong(
            f"best-qualifying cell '{best.get('cell')}': cost_per_1k=${best['cost_per_1k']:.4f} "
            f"at {best['accepted_pct']}% accepted, vs reference ${ref_val:.2f}",
            "attack this via the other WRONG findings ranked above it (rate, "
            "known-good-stack tuning, fleet-automation provisioning waste) "
            "rather than price alone; re-run engine_table.cjs after each fix.",
            "cost_per_1k falls directly and proportionally",
        )
    return right(
        f"best-qualifying cell '{best.get('cell')}': cost_per_1k=${best['cost_per_1k']:.4f} "
        f"at {best['accepted_pct']}% accepted, at/under reference ${ref_val:.2f}"
    )


def rule_price_03(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    listed = g(fp, "provisioning", "listed_available")
    provisioned = g(fp, "provisioning", "provisioned")
    if listed is None or provisioned is None:
        return missing("fingerprint.provisioning.listed_available/provisioned")
    if listed is True and provisioned is False:
        return wrong(
            "provisioning.listed_available=true but provisioning.provisioned=false",
            "reconcile the capacity dashboard against real inventory in real "
            "time; re-check the listing after the fix and confirm a "
            "provisioning attempt succeeds.",
            "uptime/availability rate on provisioning attempts rises",
        )
    return right("listed availability and actual provisioning success agree")


def rule_proof_01(counter, fp, bench, ref):
    if not counter:
        return missing("counter record")
    proof = g(counter, "dimensions", "proof")
    if proof is None:
        return missing("counter.dimensions.proof")
    flags = {
        "has_manifest_hash": proof.get("has_manifest_hash"),
        "has_disclosure": proof.get("has_disclosure"),
        "has_pinned_commit": proof.get("has_pinned_commit"),
    }
    missing_or_false = [k for k, v in flags.items() if v is not True]
    if missing_or_false:
        return wrong(
            f"not confirmed: {', '.join(missing_or_false)}",
            "publish a per-result SHA-256 manifest, a disclosure of "
            "funding/relationship and methodology caveats, and a pinned "
            "commit/build identity for the numbers being published.",
            "counter proof-dimension score rises; this does not move bench "
            "throughput/latency/$-per-1k",
        )
    return right("manifest hash, disclosure and pinned commit all confirmed")


def rule_proof_02(counter, fp, bench, ref):
    if not counter:
        return missing("counter record")
    proof = g(counter, "dimensions", "proof")
    if proof is None:
        return missing("counter.dimensions.proof")
    publishes = proof.get("publishes_whole_window_cost")
    if publishes is None:
        return missing("counter.dimensions.proof.publishes_whole_window_cost")
    if publishes is False:
        return wrong(
            "publishes_whole_window_cost=false",
            "publish both the best-qualifying-cell number and the whole-window "
            "number every time either is quoted.",
            "no bench number moves; this is a disclosure fix",
        )
    return right("publishes both best-cell and whole-window cost figures")


LAYERS = [
    ("counter", "Counter (external trust/reputation score)", [
        ("CNT-01", rule_cnt_01), ("CNT-02", rule_cnt_02),
    ]),
    ("site_power", "Site / power (inferred from sustained-load sample)", [
        ("PWR-01", rule_pwr_01),
    ]),
    ("hardware_lifecycle", "Hardware lifecycle", [
        ("HW-01", rule_hw_01), ("HW-02", rule_hw_02), ("HW-03", rule_hw_03),
    ]),
    ("known_good_stack", "Known-good stack", [
        ("STK-01", rule_stk_01), ("STK-02", rule_stk_02),
    ]),
    ("fleet_automation", "Fleet automation (inferred from provisioning behavior)", [
        ("FLEET-01", rule_fleet_01),
    ]),
    ("health_availability", "Health and availability", [
        ("HEALTH-01", rule_health_01), ("HEALTH-02", rule_health_02), ("PRICE-03", rule_price_03),
    ]),
    ("tenant_hygiene", "Tenant hygiene and isolation", [
        ("TEN-01", rule_ten_01), ("TEN-02", rule_ten_02),
    ]),
    ("pricing_capacity", "Pricing and capacity", [
        ("PRICE-01", rule_price_01), ("PRICE-02", rule_price_02),
    ]),
    ("public_proof", "Public proof", [
        ("PROOF-01", rule_proof_01), ("PROOF-02", rule_proof_02),
    ]),
]

ALL_RULE_IDS = [rid for _, _, rules in LAYERS for rid, _ in rules]


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(counter, fp, bench, ref):
    results = OrderedDict()
    for layer_id, title, rules in LAYERS:
        layer_results = OrderedDict()
        for rid, fn in rules:
            try:
                layer_results[rid] = fn(counter, fp, bench, ref)
            except Exception as e:  # keep one bad rule from sinking the report
                layer_results[rid] = missing(f"internal error evaluating {rid}: {e}")
        results[layer_id] = {"title": title, "rules": layer_results}
    return results


def verdict_line(bench, ref):
    ref_val = g(ref, "run3_a_t0", "cost_per_1k_accepted_own_window_usd")
    if not bench:
        return "Insufficient data for a $/1k accepted verdict -- no --bench provided."
    if ref_val is None:
        return "Insufficient data for a $/1k accepted verdict -- reference cost figure unobserved."
    candidates = [
        c for c in (bench.get("cells") or [])
        if c.get("cost_per_1k") is not None and c.get("accepted_pct") is not None
    ]
    if not candidates:
        return (
            "Insufficient data for a $/1k accepted verdict -- bench has no "
            "cost_per_1k/accepted_pct (raw cell files only; run engine_table.cjs)."
        )
    best = max(candidates, key=lambda c: (c["accepted_pct"], -c["cost_per_1k"]))
    ratio = best["cost_per_1k"] / ref_val
    direction = "more expensive than" if ratio > 1 else ("cheaper than" if ratio < 1 else "equal to")
    return (
        f"{ratio:.2f}x Hot Aisle on $/1k accepted "
        f"(${best['cost_per_1k']:.4f} at {best['accepted_pct']}% accepted, "
        f"cell '{best.get('cell')}', vs Hot Aisle's ${ref_val:.2f}) -- {direction} reference"
    )


def top_three(results):
    wrongs = []
    for layer_id, layer in results.items():
        for rid, res in layer["rules"].items():
            if res["status"] == "WRONG":
                wrongs.append((rid, layer_id, res))
    wrongs.sort(key=lambda t: RULE_WEIGHT.get(t[0], 0), reverse=True)
    return wrongs[:3]


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_markdown(results, verdict, top3, provenance):
    lines = []
    lines.append("# Shop diagnosis report")
    lines.append("")
    lines.append(f"**Verdict:** {verdict}")
    lines.append("")
    for layer_id, layer in results.items():
        lines.append(f"## {layer['title']}")
        lines.append("")
        statuses = {rid: res["status"] for rid, res in layer["rules"].items()}
        if all(s == "MISSING" for s in statuses.values()):
            first = next(iter(layer["rules"].values()))
            what = first["reason"]
            lines.append(f"Not evaluated -- missing {what}. {howto_for(what)}")
            lines.append("")
            continue
        for rid, res in layer["rules"].items():
            if res["status"] == "WRONG":
                lines.append(f"- **WRONG [{rid}]** {res['observation']}")
                lines.append(f"  - COULD DO BETTER: {res['action']}")
                lines.append(f"  - Expected effect: {res['effect']}")
            elif res["status"] == "RIGHT":
                lines.append(f"- RIGHT [{rid}] {res['observation']}")
            else:
                lines.append(f"- not evaluated [{rid}] -- missing {res['reason']}. {howto_for(res['reason'])}")
        lines.append("")

    lines.append("## First three things to change")
    lines.append("")
    if not top3:
        lines.append("No WRONG findings to rank -- either every evaluated rule is RIGHT, "
                      "or too few inputs were supplied to evaluate any rule. See layers above.")
    else:
        for i, (rid, layer_id, res) in enumerate(top3, 1):
            lines.append(f"{i}. **[{rid}]** {res['observation']}")
            lines.append(f"   - Change: {res['action']}")
            lines.append(f"   - Expected effect: {res['effect']}")
    lines.append("")

    lines.append("## Provenance")
    lines.append("")
    for k, v in provenance.items():
        lines.append(f"- **{k}:** {v}")
    lines.append("")
    return "\n".join(lines)


def build_json_report(results, verdict, top3, provenance):
    return {
        "verdict": verdict,
        "layers": results,
        "top_three": [
            {"rule_id": rid, "layer": layer_id, **res}
            for rid, layer_id, res in top3
        ],
        "provenance": provenance,
    }


def build_provenance(args, counter, counter_err, fp, fp_err, bench, bench_err, ref, ref_err):
    prov = OrderedDict()
    prov["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prov["counter_input"] = args.counter or "(not provided)"
    if counter_err:
        prov["counter_input"] += f" -- ERROR: {counter_err}"
    prov["fingerprint_input"] = args.fingerprint or "(not provided)"
    if fp_err:
        prov["fingerprint_input"] += f" -- ERROR: {fp_err}"
    prov["bench_input"] = args.bench or "(not provided)"
    if bench_err:
        prov["bench_input"] += f" -- ERROR: {bench_err}"
    elif bench:
        prov["bench_input"] += f" (kind={bench['kind']}, cells={len(bench['cells'])}, resolved source={bench['source']})"
    prov["reference_input"] = args.reference or "(not provided)"
    if ref_err:
        prov["reference_input"] += f" -- ERROR: {ref_err}"
    elif ref:
        prov["reference_input"] += f" (assembled_at={ref.get('assembled_at', 'unknown')})"
    prov["rubric"] = "RUBRIC.md, same directory as this script"
    return prov


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser():
    p = argparse.ArgumentParser(
        description="Diagnose a GPU compute shop against Hot Aisle as the reference operator."
    )
    p.add_argument("--counter", default=None, help="path to a second-run/counter-record@1 JSON file")
    p.add_argument("--fingerprint", default=None, help="path to a second-run/shop-fingerprint@1 JSON file")
    p.add_argument("--bench", default=None, help="path to an engine_table.cjs JSON table, or a directory of cell-*.json files (or a table.json inside one)")
    p.add_argument("--reference", default=DEFAULT_REFERENCE, help="path to the reference bundle JSON (default: shipped reference/hotaisle-2026-09.json)")
    p.add_argument("--out", default="REPORT.md", help="output report path (default: REPORT.md)")
    p.add_argument("--json", action="store_true", help="also write a JSON report next to --out (same stem, .json extension)")
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    counter, counter_err = load_counter(args.counter)
    fp, fp_err = load_fingerprint(args.fingerprint, counter)
    bench, bench_err = load_bench(args.bench)
    ref, ref_err = load_reference(args.reference)

    results = evaluate(counter, fp, bench, ref)
    verdict = verdict_line(bench, ref)
    top3 = top_three(results)
    provenance = build_provenance(args, counter, counter_err, fp, fp_err, bench, bench_err, ref, ref_err)

    md = render_markdown(results, verdict, top3, provenance)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)

    if args.json:
        json_path = os.path.splitext(args.out)[0] + ".json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(build_json_report(results, verdict, top3, provenance), f, indent=2)

    print(f"wrote {args.out}" + (f" and {os.path.splitext(args.out)[0] + '.json'}" if args.json else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
