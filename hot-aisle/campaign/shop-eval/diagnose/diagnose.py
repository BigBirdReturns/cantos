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
import hashlib
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
        "(with torch importable or the vllm container running for a verified load sample) "
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
        "rate": data.get("rate"),
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
    return {"status": "UNKNOWN", "reason": what}


def wrong(observation, action, effect):
    return {"status": "WRONG", "observation": observation, "action": action, "effect": effect}


def signal(observation, reason):
    return {"status": "SIGNAL", "observation": observation, "reason": reason}


def right(observation):
    return {"status": "RIGHT", "observation": observation}


def sustained_load(gpu):
    # Read the old rule-facing fixture name for compatibility; new probe records use
    # duration-neutral `sustained_load` because sample duration is not fixed at 60 s.
    return gpu.get("sustained_load") or gpu.get("sustained_60s")


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
    return signal(f"counter composite score {score}/100", "a composite counter score is a rubric heuristic, not a provider-quality verdict; inspect source-backed dimensions and evidence individually")


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
    return signal(f"counter dimension spread {spread:.1f} pts (avg {avg:.1f} vs '{worst_name}' at {worst:.1f})", "the spread can prioritize questions but does not prove compute quality; verify each dimension against its cited observation")


def rule_pwr_01(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    gpus = fp.get("gpus") or []
    if not gpus:
        return missing("fingerprint.gpus")
    if not all(isinstance(sustained_load(gpu), dict) for gpu in gpus):
        return missing("fingerprint.gpus[].verified sustained_load sample; failed/unknown load is not a GPU result")
    bad = []
    for i, gpu in enumerate(gpus):
        s = sustained_load(gpu) or {}
        c0, c1 = s.get("clock_mhz_start"), s.get("clock_mhz_end")
        if s.get("throttled") is None or c0 is None or c1 is None:
            return missing(f"gpu{i} sustained sample needs throttle state and both clock readings")
        if s.get("throttled") is True:
            bad.append(f"gpu{i}: throttled=true")
            continue
        if c0 > 0:
            drop = (c0 - c1) / c0
            if drop > 0.15:
                duration = s.get("actual_duration_s")
                window = f"over {duration:g}s" if isinstance(duration, (int, float)) else "over the recorded sample"
                bad.append(f"gpu{i}: clock dropped {drop * 100:.0f}% {window} ({c0}->{c1} MHz)")
    if bad:
        return signal("; ".join(bad), "possible power/thermal limitation; clock slope and throttle flags do not identify host cooling, PSU, configured limits, sharing, or workload behavior. Repeat a bounded supported load, compare vendor throttle telemetry, and ask the operator to inspect host-side evidence before any reversible, approved change.")
    return right("observed load-sample clocks held within 15%, with throttle state false on all GPUs")


def rule_hw_01(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    gpus = fp.get("gpus") or []
    if not gpus:
        return missing("fingerprint.gpus")
    bad = []
    if any(any(gpu.get(k) is None for k in ("pcie_gen", "pcie_gen_max", "pcie_width", "pcie_width_max")) for gpu in gpus):
        return missing("PCIe current and model-specific maximum generation/width are required for every GPU")
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
        return signal("; ".join(bad), "possible PCIe/topology constraint; idle negotiated link alone does not establish impact. Compare supported model/platform specifications and a bounded transfer workload; host operator can inspect slot, riser, and NUMA topology records. Any change needs an approved rollback plan.")
    return right("all GPUs negotiated at full rated PCIe generation and width")


def rule_hw_02(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    gpus = fp.get("gpus") or []
    if not gpus:
        return missing("fingerprint.gpus")
    bad = []
    for i, gpu in enumerate(gpus):
        age = gpu.get("firmware_age_days")
        if age is None:
            return missing(f"gpu{i} firmware age is unobserved; vendor release-date evidence is needed")
        if age > 270:
            bad.append(f"gpu{i}: firmware_age_days={age} (> 270)")
    if bad:
        return signal("; ".join(bad), "firmware age alone does not establish a fault. Verify the exact GPU board, vendor release notes, supported driver branch, and RAS trend; firmware changes require host-operator authorization and a recovery plan.")
    return right("firmware age reported and within 270 days on all GPUs")


def rule_hw_03(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    gpus = fp.get("gpus") or []
    if not gpus:
        return missing("fingerprint.gpus")
    bad = []
    for i, gpu in enumerate(gpus):
        unc = gpu.get("ras_errors_uncorrectable")
        cor = gpu.get("ras_errors_correctable")
        if unc is None or cor is None:
            return missing(f"gpu{i} requires both correctable and uncorrectable RAS counters")
        if unc > 0:
            bad.append(f"gpu{i}: {unc} uncorrectable RAS error(s)")
        elif cor > 100:
            bad.append(f"gpu{i}: {cor} correctable RAS errors (> 100)")
    if bad:
        return signal("; ".join(bad), "possible hardware health issue; inspect counter semantics, baseline/delta, and vendor RAS documentation, then correlate with a scoped repeat workload. Do not infer RMA or reseat from one snapshot.")
    return right("no uncorrectable RAS errors, correctable counts low on all GPUs")


def rule_stk_01(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    ref_vendor = g(ref, "stack", "gpu_vendor")
    ref_version = g(ref, "stack", "driver_or_rocm_version")
    if not ref_version:
        return missing("reference.stack.driver_or_rocm_version")
    gpus = fp.get("gpus") or []
    if not gpus:
        return missing("fingerprint.gpus")
    candidate_vendor = str(fp.get("requested_gpu_vendor") or fp.get("gpu_vendor") or "").lower()
    if not candidate_vendor:
        models = [str(g.get("model") or "").lower() for g in gpus]
        if models and all("amd" in model or "mi300" in model or "mi325" in model for model in models):
            candidate_vendor = "amd"
        elif models and all(any(x in model for x in ("nvidia", "h100", "h200", "b200", "a100")) for model in models):
            candidate_vendor = "nvidia"
    if ref_vendor and candidate_vendor != str(ref_vendor).lower():
        return {"status": "NOT_COMPARABLE", "reason": "driver/ROCm versions are vendor-specific and cannot be compared across GPU vendors"}
    bad = []
    for i, gpu in enumerate(gpus):
        v = gpu.get("driver_or_rocm_version")
        if not v:
            return missing(f"gpu{i} driver/runtime version is unobserved")
        if v != ref_version:
            bad.append(f"gpu{i}: {v} (qualified reference is {ref_version})")
    if bad:
        return signal("; ".join(bad), "version differences are not evidence of a defect; check vendor support matrices and test a matched workload before attributing performance")
    return right(f"driver/runtime version matches the same-vendor reference ({ref_version}) on all GPUs")


def rule_stk_02(counter, fp, bench, ref):
    if not fp:
        return missing("fingerprint")
    backend = g(fp, "observed_backend", "attention_backend")
    if backend is None:
        return missing("fingerprint.observed_backend.attention_backend (record the serving backend, e.g. VLLM_ATTENTION_BACKEND, next to the fingerprint)")
    if str(backend).strip() == "" or str(backend).lower() == "unknown":
        return missing("fingerprint.observed_backend.attention_backend is explicitly unknown")
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
    for c in cells:
        if c.get("failed") is None or c.get("attempted") is None or c.get("completed") is None:
            return missing(f"cell {c.get('cell')} requires attempted, completed, and failed counts")
        total_failed += c["failed"]
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
        if gpu.get("idle_verified") is not True or str(gpu.get("sample_context") or "").lower() not in ("idle", "verified_idle"):
            return missing(f"gpu{i} power sample is not verified idle; ambient or unknown power is not an idle baseline")
        sample = sustained_load(gpu) or {}
        loaded_w = sample.get("power_w_end") or sample.get("power_w_start")
        if idle_w is None or loaded_w is None or loaded_w <= 0:
            return missing(f"gpu{i} requires idle and sustained-load power readings")
        any_checked = True
        if idle_w > 0.6 * loaded_w:
            bad.append(f"gpu{i}: idle reading {idle_w}W is {idle_w / loaded_w * 100:.0f}% of the loaded reading {loaded_w}W (not idle before the sample)")
    if not any_checked:
        return missing("fingerprint.gpus[].verified idle_power_w and sustained_load power")
    if bad:
        return wrong(
            "; ".join(bad),
            "repeat the idle/load capture in an authorized, isolated window and compare with per-device utilization and scheduler/job records; ask the operator whether other work was scheduled before inferring sharing.",
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
    if acs is None or huge is None:
        return missing("VM ACS and hugepage state are incomplete; unavailable telemetry is unknown")
    return signal(f"virtualization=vm, acs_enabled={acs}, hugepages_enabled={huge}",
                  "these settings alone do not establish a performance or isolation defect; compare a scoped job-local memory/collective test and request host topology evidence. Do not use ACS override as a generic fix.")


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
        return signal(f"numa_nodes={numa_nodes}, container_runtime.numa_pinning=false",
                      "verify GPU-to-NUMA locality and compare a bounded job-local pinned/unpinned run before changing scheduler defaults")
    return right(f"numa_nodes={numa_nodes}, serving process pinned to local NUMA node")


def rule_price_01(counter, fp, bench, ref):
    if not counter:
        return missing("counter record")
    billing = counter.get("billing_granularity")
    if not billing:
        return missing("counter.billing_granularity")
    if billing == "unknown":
        return missing("counter.billing_granularity is unknown")
    if billing == "per-hour":
        return wrong(
            f"billing_granularity={billing}",
            "negotiate or enable sub-hour billing; check invoice line-item "
            "granularity after the change.",
            "whole-window $/1k accepted moves toward own-window $/1k accepted",
        )
    if billing in ("per-minute", "per-second", "per-second-with-minimum"):
        return right(f"billing_granularity={billing} (sub-hour)")
    return missing(f"billing granularity {billing!r} is not recognized")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_unknown_value(value):
    if value is None or value == "":
        return True
    text = str(value).strip().lower()
    return text in {"unknown", "unobserved", "unavailable"} or "_unobserved" in text or "unobserved_" in text


SCOPE_IDENTITY_FIELDS = (
    "workload_id", "model_revision", "tokenizer_revision", "precision",
    "cache_policy", "load_profile_id", "cost_scope",
)
SCOPE_ACCEPTANCE_FIELDS = (
    "rule_id", "quality_rule", "ttft_ms", "e2e_ms",
)
CONFIGURATION_FIELDS = (
    "gpu_model", "gpu_count", "runtime_digest", "server_version",
    "backend", "kernel", "tensor_parallel",
)


def assess_comparison(bench, ref, candidate_scope, reference_scope_id, requested_label=None):
    """Fail closed unless the scored table is bound to an evidenced, like-scoped record."""
    result = {
        "label": "not comparable",
        "economic_comparison": "unavailable",
        "operator_causality": "not established",
        "reasons": [],
        "reference_scope_id": reference_scope_id,
    }
    if not bench:
        result["reasons"].append("no scored benchmark input")
        return result
    if not isinstance(candidate_scope, dict):
        result["reasons"].append("candidate scope evidence was not supplied")
        return result
    scopes = ref.get("comparison_scopes") if isinstance(ref, dict) else None
    reference_scope = scopes.get(reference_scope_id) if isinstance(scopes, dict) else None
    if not isinstance(reference_scope, dict):
        result["reasons"].append(f"reference scope {reference_scope_id!r} is absent")
        return result

    for side, scope in (("candidate", candidate_scope), ("reference", reference_scope)):
        missing_fields = [k for k in SCOPE_IDENTITY_FIELDS if is_unknown_value(scope.get(k))]
        if not scope.get("observation_date"):
            missing_fields.append("observation_date")
        acceptance = scope.get("acceptance")
        if not isinstance(acceptance, dict):
            missing_fields.append("acceptance")
        else:
            missing_fields.extend(f"acceptance.{k}" for k in SCOPE_ACCEPTANCE_FIELDS
                                  if acceptance.get(k) is None and k != "e2e_ms")
            if "e2e_ms" not in acceptance:
                missing_fields.append("acceptance.e2e_ms")
            if is_unknown_value(acceptance.get("evidence")):
                missing_fields.append("acceptance.evidence")
        if not scope.get("evidence"):
            missing_fields.append("evidence")
        config_details = scope.get("configuration")
        if not isinstance(config_details, dict):
            missing_fields.append("configuration")
        else:
            missing_fields.extend(f"configuration.{k}" for k in CONFIGURATION_FIELDS
                                  if is_unknown_value(config_details.get(k)))
        if side == "candidate":
            digest = scope.get("bench_sha256")
            source = bench.get("source")
            if not isinstance(digest, str) or len(digest) != 64:
                missing_fields.append("bench_sha256")
            elif not source or not os.path.isfile(source):
                missing_fields.append("scored table file for digest verification")
            else:
                try:
                    if sha256_file(source) != digest.lower():
                        result["reasons"].append("candidate scope bench_sha256 does not match the scored table")
                except OSError:
                    missing_fields.append("readable scored table for digest verification")
        if missing_fields:
            result["reasons"].append(f"{side} scope is incomplete: {', '.join(missing_fields)}")

    for key in SCOPE_IDENTITY_FIELDS:
        if candidate_scope.get(key) != reference_scope.get(key):
            result["reasons"].append(f"scope mismatch for {key}")
    for key in SCOPE_ACCEPTANCE_FIELDS:
        if candidate_scope.get("acceptance", {}).get(key) != reference_scope.get("acceptance", {}).get(key):
            result["reasons"].append(f"acceptance mismatch for {key}")

    gates = bench.get("gates") or {}
    acceptance = candidate_scope.get("acceptance") or {}
    if gates.get("ttft_ms") != acceptance.get("ttft_ms"):
        result["reasons"].append("scored table TTFT gate does not match candidate scope")
    if gates.get("e2e_ms") != acceptance.get("e2e_ms"):
        result["reasons"].append("scored table E2E gate does not match candidate scope")
    if not isinstance(bench.get("rate"), (int, float)) or bench.get("rate") <= 0:
        result["reasons"].append("scored table does not contain a positive numeric rate")
    if not isinstance(candidate_scope.get("rate"), (int, float)) or candidate_scope.get("rate") <= 0:
        result["reasons"].append("candidate scope does not contain a positive numeric rate")
    if candidate_scope.get("rate") != bench.get("rate"):
        result["reasons"].append("candidate scope rate does not match the scored table")
    if candidate_scope.get("configuration") != reference_scope.get("configuration"):
        result["configuration_differs"] = True

    config = candidate_scope.get("configuration_id")
    ref_config = reference_scope.get("configuration_id")
    if not config or not ref_config:
        result["reasons"].append("candidate or reference configuration identity is absent")
    if requested_label == "not comparable":
        result["reasons"].append("comparison was explicitly marked not comparable")
    if result["reasons"]:
        return result

    if requested_label == "historical":
        if candidate_scope.get("observation_date") == reference_scope.get("observation_date"):
            result["reasons"].append("historical label requires distinct dated observations")
            return result
        result["label"] = "historical"
    elif requested_label == "matched":
        if candidate_scope.get("configuration") != reference_scope.get("configuration"):
            result["reasons"].append("matched label requires identical complete configuration fields")
            return result
        result["label"] = "matched"
    elif requested_label == "different complete configuration":
        if candidate_scope.get("configuration") == reference_scope.get("configuration"):
            result["reasons"].append("different-complete-configuration label requires a documented configuration difference")
            return result
        result["label"] = "different complete configuration"
    elif candidate_scope.get("configuration") == reference_scope.get("configuration"):
        result["label"] = "matched"
    else:
        result["label"] = "different complete configuration"
    result["economic_comparison"] = "allowed for this workload, acceptance rule, and cost scope"
    result["operator_causality"] = "not established; configuration effects are not isolated"
    return result


def rule_price_02(counter, fp, bench, ref, comparison=None):
    if not bench:
        return missing("bench")
    if not comparison or comparison.get("economic_comparison") != "allowed for this workload, acceptance rule, and cost scope":
        why = "; ".join((comparison or {}).get("reasons") or ["scope comparison was not validated"])
        return missing(f"economic comparison refused: {why}")
    reference_scope_id = comparison["reference_scope_id"]
    if reference_scope_id == "run1-cell-c64":
        ref_val = g(ref, "run1_best_cell", "cost_per_1k_usd")
    elif reference_scope_id == "run3-own-window":
        ref_val = g(ref, "run3_a_t0", "cost_per_1k_accepted_own_window_usd")
    elif reference_scope_id == "run3-whole-seat":
        ref_val = g(ref, "run3_whole_seat", "cost_per_1k_accepted_usd")
    else:
        return missing(f"reference cost metric for scope {reference_scope_id!r} is not implemented")
    if ref_val is None:
        return missing(f"reference cost metric for scope {reference_scope_id!r} is absent")
    if not bench.get("cells") or any(c.get("accepted_pct") is None or c.get("cost_per_1k") is None
                                      for c in bench.get("cells", [])):
        return missing("each scored cell needs accepted_pct and modeled cost under the declared acceptance rule")
    candidates = [c for c in bench["cells"] if c.get("accepted_pct") > 0
                  and c.get("accepted") is not None and c.get("attempted") is not None
                  and c.get("attempted") > 0 and not c.get("holds")]
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
            "inspect rate, accepted-work yield, workload mix, and the declared cost window; run matched repeated cells while changing one customer-visible serving parameter at a time.",
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
    if listed is False:
        return missing("no listed offer means no provisioning attempt denominator; availability is unknown for this observation")
    if provisioned is True:
        return right("a listed offer provisioned successfully in this observation")
    return missing("listing/provisioning state is insufficient to evaluate an attempt")


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
    unavailable = [k for k, v in flags.items() if v is None]
    if unavailable:
        return missing(f"public proof fields unobserved: {', '.join(unavailable)}")
    missing_or_false = [k for k, v in flags.items() if v is False]
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

FINDING_METHOD = {
    "FLEET-01": {
        "competing_causes": "provider queue, image startup, control-plane delay, network readiness, or customer-side SSH timing",
        "discriminating_test": "repeat request-to-SSH timing on several authorized fresh allocations and retain provider timestamps alongside client timestamps",
        "bounded_change": "change one provisioning step or image cache setting in a canary; accept only if repeated readiness time improves without breaking health checks",
        "acceptance": "repeated readiness time improves with unchanged health checks",
        "rollback": "restore the prior image/provisioning setting and compare against the same readiness check",
        "access_needed": "customer timestamps; provider control-plane and image logs to separate causes",
    },
    "HEALTH-01": {
        "competing_causes": "server OOM/timeout, model/runtime fault, request cancellation, client/network loss, or benchmark accounting",
        "discriminating_test": "join failed request IDs and timestamps to client output and server logs for one failing cell",
        "bounded_change": "replay only the failing cases in an isolated job after identifying one configuration cause; require zero unexplained failures and unchanged accepted-work semantics",
        "acceptance": "zero unexplained failures and unchanged accepted-work semantics",
        "rollback": "restore the saved runtime/config and stop replay if error rate rises",
        "access_needed": "client request IDs and provider server logs; hidden host/RAS data may require operator access",
    },
    "PRICE-03": {
        "competing_causes": "stale listing, transient quota, region/SKU mismatch, account entitlement, or provisioning service fault",
        "discriminating_test": "retain each listing snapshot and actual authorized provisioning attempt, outcome, SKU, region, timestamp, and denominator",
        "bounded_change": "recheck the exact listed SKU/region and retry only within the customer's approved attempt budget",
        "acceptance": "recorded attempt succeeds on the same listed SKU/region",
        "rollback": "stop attempts and return to the last known provisionable SKU/region if failures repeat",
        "access_needed": "customer listing and attempt evidence; provider inventory/quota logs to identify cause",
    },
    "PRICE-01": {
        "competing_causes": "hourly billing, minimum duration, rounding, setup charges, or a mismatch between modeled and billed windows",
        "discriminating_test": "compare dated plan terms with the actual invoice for one bounded seat window, including minimums and fees",
        "bounded_change": "model the same accepted work under the documented finer billing option; change plans only through normal commercial authorization",
        "acceptance": "invoice matches the documented billing quantum and total modeled cost does not rise",
        "rollback": "retain prior plan terms and revert at the next permitted billing boundary if total cost worsens",
        "access_needed": "customer contract/order and invoice; provider plan terms",
    },
    "PRICE-02": {
        "competing_causes": "rate, utilization, accepted-work yield, window attribution, or incomplete cost inputs",
        "discriminating_test": "verify the table hash and scope; recompute one cell from its accepted count, duration, rate, and declared cost window",
        "bounded_change": "vary one serving or workload parameter in matched repeated cells; accept only if same-rule cost per accepted 1,000 falls without quality or reliability regression",
        "acceptance": "same-rule cost falls without quality or reliability regression",
        "rollback": "restore the recorded prior parameter and retain both results if acceptance or error rate worsens",
        "access_needed": "scored table and cost evidence; provider invoice is required for actual billed cost",
    },
    "PROOF-01": {
        "competing_causes": "manifest omission, inaccessible evidence, stale source revision, or incomplete disclosure",
        "discriminating_test": "independently verify each artifact hash and resolve the cited revision/disclosure",
        "bounded_change": "publish a corrected evidence manifest and disclosure for this run only",
        "acceptance": "every referenced artifact hash and disclosure resolves and verifies",
        "rollback": "withdraw the affected claim if any artifact fails verification; retain prior versions",
        "access_needed": "result artifacts and public/private disclosure location",
    },
    "PROOF-02": {
        "competing_causes": "best-cell-only reporting, missing setup clocks, unpriced idle gaps, or billing minimums",
        "discriminating_test": "reconcile one complete request-to-release timeline with modeled rate and invoice lines",
        "bounded_change": "add a labeled whole-seat estimate alongside the existing cell and arm-window figures",
        "acceptance": "all cost views state distinct windows, denominator, and modeled/billed status",
        "rollback": "withdraw any unreconciled figure and keep source-level windows separate",
        "access_needed": "allocation/release timestamps, accepted counts, plan terms, invoice",
    },
}


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(counter, fp, bench, ref, comparison=None):
    results = OrderedDict()
    for layer_id, title, rules in LAYERS:
        layer_results = OrderedDict()
        for rid, fn in rules:
            try:
                if rid == "PRICE-02":
                    layer_results[rid] = fn(counter, fp, bench, ref, comparison)
                else:
                    layer_results[rid] = fn(counter, fp, bench, ref)
                if layer_results[rid].get("status") == "WRONG":
                    layer_results[rid]["diagnostic"] = FINDING_METHOD.get(rid, {
                        "competing_causes": "multiple causes can produce this observation; the input alone does not establish root cause",
                        "discriminating_test": "repeat a fixed, scoped observation and inspect the source evidence named by this rule",
                        "bounded_change": layer_results[rid].get("action", "change one variable only after evidence identifies it"),
                        "acceptance": "compare the same stated metric and scope before and after the change",
                        "rollback": "restore the recorded prior setting if the acceptance metric regresses",
                        "access_needed": "customer-visible evidence plus provider operator logs for hidden host state",
                    })
            except Exception as e:  # keep one bad rule from sinking the report
                layer_results[rid] = missing(f"internal error evaluating {rid}: {e}")
        results[layer_id] = {"title": title, "rules": layer_results}
    return results


def verdict_line(bench, ref, comparison=None):
    if not bench:
        return "Insufficient data for a $/1k accepted verdict -- no --bench provided."
    if not comparison or comparison.get("economic_comparison") != "allowed for this workload, acceptance rule, and cost scope":
        reasons = "; ".join((comparison or {}).get("reasons") or ["no validated comparison scope"])
        return f"Not comparable to Hot Aisle -- no $/1k ratio. {reasons}"
    scope_id = comparison["reference_scope_id"]
    if scope_id == "run1-cell-c64":
        ref_val = g(ref, "run1_best_cell", "cost_per_1k_usd")
    elif scope_id == "run3-own-window":
        ref_val = g(ref, "run3_a_t0", "cost_per_1k_accepted_own_window_usd")
    elif scope_id == "run3-whole-seat":
        ref_val = g(ref, "run3_whole_seat", "cost_per_1k_accepted_usd")
    else:
        ref_val = None
    if ref_val is None:
        return f"Not comparable to Hot Aisle -- no supported cost metric for scope {scope_id!r}."
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
        f"{comparison['label']}: {ratio:.2f}x Hot Aisle on $/1k accepted "
        f"(${best['cost_per_1k']:.4f} at {best['accepted_pct']}% accepted, "
        f"cell '{best.get('cell')}', vs Hot Aisle's ${ref_val:.4f}) -- {direction}; "
        f"cost scope {comparison['reference_scope_id']}; operator causality not established"
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
        if all(s == "UNKNOWN" for s in statuses.values()):
            first = next(iter(layer["rules"].values()))
            what = first["reason"]
            lines.append(f"UNKNOWN -- missing {what}. {howto_for(what)}")
            lines.append("")
            continue
        for rid, res in layer["rules"].items():
            if res["status"] == "WRONG":
                lines.append(f"- **WRONG [{rid}]** {res['observation']}")
                lines.append(f"  - COULD DO BETTER: {res['action']}")
                lines.append(f"  - Expected effect: {res['effect']}")
                diag = res.get("diagnostic", {})
                for label, key in (("Competing causes", "competing_causes"), ("Discriminating test", "discriminating_test"),
                                   ("Bounded change", "bounded_change"), ("Acceptance", "acceptance"), ("Rollback", "rollback"),
                                   ("Access needed", "access_needed")):
                    if diag.get(key):
                        lines.append(f"  - {label}: {diag[key]}")
            elif res["status"] == "SIGNAL":
                lines.append(f"- **SIGNAL (hypothesis only) [{rid}]** {res.get('observation', '')}")
                lines.append(f"  - Discriminating evidence: {res.get('reason', '')}")
            elif res["status"] == "RIGHT":
                lines.append(f"- RIGHT [{rid}] {res['observation']}")
            elif res["status"] == "NOT_COMPARABLE":
                lines.append(f"- NOT COMPARABLE [{rid}] {res['reason']}")
            else:
                lines.append(f"- UNKNOWN [{rid}] -- {res['reason']}. {howto_for(res['reason'])}")
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
            diag = res.get("diagnostic", {})
            if diag:
                lines.append(f"   - Test: {diag['discriminating_test']}")
                lines.append(f"   - Bounded change: {diag['bounded_change']}")
                lines.append(f"   - Acceptance / rollback: {diag['acceptance']} / {diag['rollback']}")
    lines.append("")

    lines.append("## Provenance")
    lines.append("")
    for k, v in provenance.items():
        lines.append(f"- **{k}:** {v}")
    lines.append("")
    return "\n".join(lines)


def build_json_report(results, verdict, top3, provenance, comparison):
    return {
        "verdict": verdict,
        "comparison": comparison,
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
    prov["candidate_scope_input"] = args.scope or "(not provided; economic comparison refused)"
    prov["reference_scope_id"] = args.reference_scope_id or "(not provided)"
    prov["comparison_label_requested"] = args.comparison_label or "(derive only after scope validation)"
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
    p.add_argument("--scope", default=None, help="candidate scope JSON (workload, acceptance, cost window, complete config, table SHA-256)")
    p.add_argument("--reference-scope-id", default=None, help="scope id from reference comparison_scopes")
    p.add_argument("--comparison-label", choices=("matched", "different complete configuration", "historical", "not comparable"), default=None,
                   help="optional declared label; validated against scope identity before any ratio")
    p.add_argument("--out", default="REPORT.md", help="output report path (default: REPORT.md)")
    p.add_argument("--json", action="store_true", help="also write a JSON report next to --out (same stem, .json extension)")
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    counter, counter_err = load_counter(args.counter)
    fp, fp_err = load_fingerprint(args.fingerprint, counter)
    bench, bench_err = load_bench(args.bench)
    ref, ref_err = load_reference(args.reference)
    scope, scope_err = load_json_file(args.scope) if args.scope else (None, None)

    comparison = assess_comparison(bench, ref, scope, args.reference_scope_id, args.comparison_label)
    if scope_err:
        comparison["reasons"].append(f"candidate scope could not be loaded: {scope_err}")
        comparison["economic_comparison"] = "unavailable"
        comparison["label"] = "not comparable"
    results = evaluate(counter, fp, bench, ref, comparison)
    verdict = verdict_line(bench, ref, comparison)
    top3 = top_three(results)
    provenance = build_provenance(args, counter, counter_err, fp, fp_err, bench, bench_err, ref, ref_err)

    md = render_markdown(results, verdict, top3, provenance)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)

    if args.json:
        json_path = os.path.splitext(args.out)[0] + ".json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(build_json_report(results, verdict, top3, provenance, comparison), f, indent=2)

    print(f"wrote {args.out}" + (f" and {os.path.splitext(args.out)[0] + '.json'}" if args.json else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
