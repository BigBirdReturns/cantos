#!/usr/bin/env python3
"""Assemble run-ledger records for Run 1's two arms from the files the campaign already retained. Stdlib only.

    python ledger_build_run1.py [--out DIR]      writes DIR/run1-<arm>.ledger.json + .events.jsonl (default examples/), then validates
    python ledger_build_run1.py --selftest       builds from fixtures/run1-mini/ into a temp dir and checks the numbers

Inputs (read-only): ../results/<arm>/{cell-*.json, env.normalized.json, MANIFEST.sha256, image.txt, *.log},
../identity.json, ../availability/observations.jsonl, ../results/run1-engine/<arm>.ttft1000.json.
Fields Run 1 cannot supply are null with a reason. Nothing here asserts a result; it records one.
"""
import glob
import json
import os
import statistics
import subprocess
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CAMPAIGN = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import knot_lifecycle  # noqa: E402
import ledger_validate  # noqa: E402
from ledger_common import (attempt_from_observation, classify_observation, iso, parse_iso,  # noqa: E402
                           read_manifest, tmpdir, verify_manifest)

ARMS = {
    "do-h100": {
        "provider": "digitalocean", "region": "nyc2", "sku": "gpu-h100x1-80gb", "seat_id": "do-h100-nyc2",
        "payer": "self", "engine": "vllm",
        "obs_match": lambda o: o.get("provider") == "digitalocean" and o.get("sku") == "gpu-h100x1-80gb",
    },
    "hotaisle-mi300x": {
        "provider": "hotaisle", "region": "enc1", "sku": "vm-mi300x-1x", "seat_id": "hotaisle-mi300x-1x-enc1",
        "payer": "credit:hotaisle", "engine": "vllm",
        "obs_match": lambda o: o.get("provider") == "hotaisle" and o.get("sku") == "vm-mi300x-1x",
    },
}
BUCKET_S = 300
REQUIRED_WINDOW_S = 3600


def parse_bench_date(s):
    # vLLM bench writes local time of the container; both Run 1 hosts ran UTC (env.recorded_at agrees)
    return datetime.strptime(s, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)


def git_sha_of(path):
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%H", "--", path], cwd=os.path.dirname(CAMPAIGN),
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except Exception:
        return None


def per_request_completion(cell):
    """(start_s, ttft_s, completion_s) per request on the bench's monotonic clock. AMD files lack
    'latencies', so e2e is derived as ttft + sum(itl) (DISCLOSURES: supporting evidence, not a restored gate)."""
    starts, ttfts, itls = cell["start_times"], cell["ttfts"], cell["itls"]
    lats = cell.get("latencies")
    out = []
    for i in range(len(starts)):
        e2e = lats[i] if lats else ttfts[i] + sum(itls[i])
        out.append((starts[i], ttfts[i], starts[i] + e2e))
    return out


def build_arm(arm, results_dir, identity, observations, engine_out_path=None, rel=lambda p: p, events_path=None):
    cfg = ARMS[arm]
    env = json.load(open(os.path.join(results_dir, "env.normalized.json"), encoding="utf-8"))
    manifest = read_manifest(os.path.join(results_dir, "MANIFEST.sha256"))
    verified = verify_manifest(results_dir, manifest)
    cells = []
    for f in sorted(glob.glob(os.path.join(results_dir, "cell-*.json"))):
        cells.append((os.path.basename(f), json.load(open(f, encoding="utf-8"))))
    if not cells:
        raise SystemExit(f"{arm}: no cell files in {results_dir}")
    req = identity["requirements"]
    ttft_gate_s = req["max_p95_ttft_ms"] / 1000.0
    arm_price = identity["arms"][arm]
    obs_src = rel(os.path.join(CAMPAIGN, "availability", "observations.jsonl"))

    # ---- acquisition (delivered-layer rows only) ----------------------------
    attempts = [attempt_from_observation(o, obs_src) for o in observations
                if cfg["obs_match"](o) and classify_observation(o) == "delivered"]
    n_alloc = sum(1 for a in attempts if a["provisioned"])
    acquisition = {
        "attempts": attempts, "n_attempts": len(attempts), "n_allocations": n_alloc,
        "yield": (n_alloc / len(attempts)) if attempts else None,
        "note": "Run 1 made exactly one create per arm and it succeeded; the same evening's listings (H200, DO MI300X out of capacity; H100 selectable at 19:14) are probes, not attempts, and belong to other arms.",
    }
    if not attempts:
        acquisition["null_reasons"] = {"yield": "no delivered-layer observation for this arm"}

    # ---- clocks ------------------------------------------------------------
    first = attempts[0] if attempts else None
    t_request = parse_iso(first["ts"]) if first else None
    t_ssh = (t_request + timedelta(seconds=first["time_to_ssh_s"])) if first and first.get("time_to_ssh_s") else None
    t_ready = parse_iso(env["recorded_at"])
    starts = [parse_bench_date(c["date"]) for _, c in cells]
    ends = [parse_bench_date(c["date"]) + timedelta(seconds=c["duration"]) for _, c in cells]
    t_work_start, t_work_end = min(starts), max(ends)
    clocks = {
        "t_request": iso(t_request) if t_request else None,
        "t_ssh": iso(t_ssh) if t_ssh else None,
        "t_ready": iso(t_ready),
        "t_work_start": iso(t_work_start),
        "t_work_end": iso(t_work_end),
        "t_released": None,
        "sources": {
            "t_request": {"source": obs_src, "precision": "approximate to a few minutes (availability/README.md: times before 19:00 UTC)"},
            "t_ssh": {"source": "observation time_to_ssh_s added to t_request", "precision": "approximate"} if t_ssh else {"source": None, "precision": None},
            "t_ready": {"source": "env.json recorded_at; arm.sh writes it after health AND the unrecorded warm-up, so true health is earlier by the warm-up (~30-60 s)", "precision": "1 s, upper bound"},
            "t_work_start": {"source": "earliest cell 'date' (vLLM bench start, container clock assumed UTC; consistent with env.recorded_at)", "precision": "1 s"},
            "t_work_end": {"source": "latest cell 'date' + 'duration'", "precision": "1 s"},
            "t_released": {"source": None, "precision": None},
        },
        "null_reasons": {},
    }
    if not t_request:
        clocks["null_reasons"]["t_request"] = "no delivered-layer observation for this arm in availability/observations.jsonl"
    if not t_ssh:
        clocks["null_reasons"]["t_ssh"] = "Run 1 did not record the first ssh time for this seat (Hot Aisle TUI provision; no time_to_ssh_s in the observation)"
    clocks["null_reasons"]["t_released"] = "Run 1 did not record the seat deletion time; the console/TUI delete was not logged (container stop is not release)"

    # ---- work --------------------------------------------------------------
    attempted = completed = accepted = failed = 0
    cell_rows = []
    all_reqs = []
    by_depth = {}
    for name, c in cells:
        reqs = per_request_completion(c)
        all_reqs.extend(reqs)
        acc = sum(1 for _, t, _ in reqs if t <= ttft_gate_s)
        attempted += c["num_prompts"]; completed += c["completed"]; failed += c["failed"]; accepted += acc
        conc = c["max_concurrency"]
        p95_e2e = c.get("p95_e2el_ms") if c.get("latencies") else None
        qualifies = (c["p95_ttft_ms"] <= req["max_p95_ttft_ms"]
                     and (p95_e2e is None or p95_e2e <= req["max_p95_e2e_ms"])
                     and c["failed"] <= req["max_failure_rate"] * c["num_prompts"])
        med_itl_s = c["median_itl_ms"] / 1000.0
        est_traversals = c["duration"] / med_itl_s
        exp, act = verified.get(name, (None, None))
        cell_rows.append({
            "cell": name.replace(".json", ""), "concurrency": conc, "attempted": c["num_prompts"], "completed": c["completed"],
            "failed": c["failed"], "accepted_ttft_gate": acc, "duration_s": round(c["duration"], 3),
            "request_throughput": round(c["request_throughput"], 4), "p95_ttft_ms": round(c["p95_ttft_ms"], 1),
            "p95_e2e_ms": round(p95_e2e, 1) if p95_e2e is not None else None,
            "e2e_gate": "applied" if p95_e2e is not None else "held (no per-request latencies in this image's output)",
            "registered_cell_qualifies": qualifies, "median_itl_ms": round(c["median_itl_ms"], 3),
            "sha256": exp, "sha256_verified": (exp is not None and exp == act),
        })
        d = by_depth.setdefault(conc, {"depth": conc, "s": [], "acc": 0, "trav": 0.0})
        d["s"].append(med_itl_s); d["acc"] += acc; d["trav"] += est_traversals
    work = {
        "unit": "request",
        "evaluator": None,
        "acceptance_rule": {
            "basis": "post-hoc per-request rule declared in DISCLOSURES.md (Run 1): a request is accepted if it completed and its own TTFT <= gate. The registered rule was cell-level (p95 TTFT, p95 E2E, failed <= 1%) and is kept per cell in work.cells.registered_cell_qualifies. Latency-only: no correctness.",
            "ttft_ms": req["max_p95_ttft_ms"], "e2e_ms": None, "correctness": False,
            "e2e_note": "E2E gate held on both arms for symmetry: the ROCm image (vLLM 0.27.1-dev) writes no per-request latencies.",
        },
        "attempted": attempted, "completed": completed, "correct": None, "accepted": accepted,
        "lost": failed, "restarts": None,
        "cells": cell_rows, "task_classes": None,
        "null_reasons": {
            "evaluator": "Run 1 ran no evaluator (identity.json not_in_this_run: correctness sidecar)",
            "correct": "Run 1 ran no evaluator; identity.json lists the correctness sidecar under not_in_this_run",
            "restarts": "Run 1 recorded no restart counter and serve.log was not collected (DISCLOSURES: unequal software note)",
            "task_classes": "random-token workload; no task classes",
        },
    }

    # ---- sustained ---------------------------------------------------------
    all_reqs.sort()
    t0 = all_reqs[0][0]
    t_last = max(c for _, _, c in all_reqs)
    window_s = t_last - t0
    n_buckets = int(window_s // BUCKET_S) + 1
    buckets = [{"index": i, "start_s": i * BUCKET_S, "accepted": 0, "completed": 0} for i in range(n_buckets)]
    for s, t, c in all_reqs:
        b = buckets[int((c - t0) // BUCKET_S)]
        b["completed"] += 1
        if t <= ttft_gate_s:
            b["accepted"] += 1
    acc_counts = [b["accepted"] for b in buckets]
    q = max(1, n_buckets // 4)
    first_q, last_q = sum(acc_counts[:q]), sum(acc_counts[-q:])
    sustained = {
        "required_window_s": REQUIRED_WINDOW_S, "bucket_s": BUCKET_S, "window_s": round(window_s, 1),
        "meets_required_window": window_s >= REQUIRED_WINDOW_S, "interrupted": False,
        "buckets": buckets,
        "min_accepted_per_bucket": min(acc_counts), "median_accepted_per_bucket": statistics.median(acc_counts),
        "last_q_over_first_q": (last_q / first_q) if first_q else None,
        "note": ("Run 1's recorded window is the 12-cell sweep (c1 x3 first, c64 x3 last) with ~30 s bench start-up gaps between cells; "
                 "bucket counts follow the concurrency schedule, not a steady arrival process. The last bucket is partial. "
                 "Completion times on the AMD arm are ttft + sum(itl). This does not meet the 60-minute sustained requirement."),
    }
    if sustained["last_q_over_first_q"] is None:
        sustained["null_reasons"] = {"last_q_over_first_q": "first quarter had zero accepted"}

    # ---- traversal ---------------------------------------------------------
    c1 = by_depth.get(1)
    curve = []
    for depth in sorted(by_depth):
        d = by_depth[depth]
        curve.append({
            "depth": depth, "seconds_per_traversal": round(statistics.median(d["s"]), 6),
            "accepted_closures_per_traversal": round(d["acc"] / d["trav"], 6) if d["trav"] else None,
            "basis": "estimated: seconds/traversal = median ITL at this concurrency (one decode step ~ one traversal); traversals ~ cell duration / median ITL, prefill steps not separated; closures = accepted requests",
        })
    traversal = {
        "path": "resident-hbm",
        "footprint_bytes": identity["model"]["bytes"],
        "footprint_bytes_basis": "resident checkpoint bytes from identity.json (allocated weights); NOT the bytes read per step",
        "bytes_per_traversal": None, "bytes_per_traversal_basis": None,
        "traversals": None, "traversals_basis": None,
        "seconds_per_traversal": round(statistics.median(c1["s"]), 6) if c1 else None,
        "seconds_per_traversal_basis": "median inter-token latency at concurrency 1 across repeats (decode step ~ one full traversal from HBM); estimated, not a forward-pass counter" if c1 else None,
        "accepted_closures_per_traversal": None, "accepted_closures_per_traversal_basis": None,
        "by_depth": curve,
        "null_reasons": {
            "bytes_per_traversal": "MoE (30B-A3B): bytes actually read per decode step are the active experts plus shared weights, not measured; footprint_bytes is not a substitute",
            "bytes_per_traversal_basis": "see bytes_per_traversal",
            "traversals": "vLLM 0.27/0.30 bench output does not count forward passes; by_depth carries a duration/ITL estimate that is not a measurement",
            "traversals_basis": "see traversals",
            "accepted_closures_per_traversal": "not measured (traversals unmeasured); by_depth carries estimates per concurrency",
            "accepted_closures_per_traversal_basis": "see accepted_closures_per_traversal",
        },
    }
    if not c1:
        traversal["null_reasons"]["seconds_per_traversal"] = "no concurrency-1 cell in this results set"
        traversal["null_reasons"]["seconds_per_traversal_basis"] = "see seconds_per_traversal"

    # ---- money -------------------------------------------------------------
    rate = arm_price["list_rate"]
    lb_start = t_request or t_ready
    lb_minutes = (t_work_end - lb_start).total_seconds() / 60.0
    lb_usd = round(rate * env["gpus"] * lb_minutes / 60.0, 4)
    money = {
        "currency": "USD", "list_rate_per_gpu_hr": rate, "billing": arm_price["billing"], "payer": cfg["payer"],
        "modeled_minutes": None, "modeled_minutes_basis": None, "modeled_usd": None,
        "modeled_lower_bound_minutes": round(lb_minutes, 2), "modeled_lower_bound_usd": lb_usd,
        "modeled_lower_bound_basis": (("t_request" if t_request else "t_ready") + " -> t_work_end at list rate; t_released is unknown, so the billable window is at least this long (the seat kept billing until deleted)"),
        "billed_usd": None, "billed_ref": None, "credits_usd": None,
        "energy": {"watts_mean": None, "kwh": None, "tariff_usd_per_kwh": None, "usd": None, "meter": None,
                   "reason": "cloud seat; the buyer sees no meter"},
        "null_reasons": {
            "modeled_minutes": "t_released unknown: the buyer's window (request -> release) cannot be modeled; see modeled_lower_bound_*",
            "modeled_minutes_basis": "see modeled_minutes",
            "modeled_usd": "t_released unknown; modeled_lower_bound_usd is the request -> work_end floor",
            "billed_usd": "invoice not yet posted / not yet entered (DISCLOSURES: billed invoices not measured)",
            "billed_ref": "see billed_usd",
            "credits_usd": ("credit consumption not yet read from the Hot Aisle balance; compute ran on the $200 credit (DISCLOSURES)"
                            if cfg["payer"].startswith("credit") else "no credit applied to this arm (self-funded at list)"),
        },
    }
    # the record's clocks are whole seconds; derive from the same values the validator will read
    work_window_s = (parse_iso(clocks["t_work_end"]) - parse_iso(clocks["t_work_start"])).total_seconds()
    derived = {
        "usd_per_accepted": lb_usd / accepted if accepted else None,
        "usd_per_1k_accepted": lb_usd / accepted * 1000 if accepted else None,
        "cost_basis": "modeled-lower-bound",
        "wall_s_per_accepted": None,
        "work_s_per_accepted": work_window_s / accepted if accepted else None,
        "accepted_per_work_s": accepted / work_window_s if work_window_s else None,
        "null_reasons": {"wall_s_per_accepted": "t_released unknown: the buyer's clock (request -> release) per accepted cannot be computed; work_s_per_accepted is work time only and is not a substitute"},
        "note": ("$/accepted here is a LOWER BOUND over the whole arm (request -> work end, all 12 cells including the slow c1 cells, no release time). "
                 "It is a different aggregation from the DISCLOSURES headline (list rate / throughput at each arm's cheapest qualifying cell), "
                 "and neither is an invoice or a correctness result."),
    }

    # ---- receipts ----------------------------------------------------------
    items = [{"kind": "cell", "path": rel(os.path.join(results_dir, n)), "sha256": verified.get(n, (None, None))[0],
              "sha256_verified": verified.get(n, (None, None))[0] is not None and verified[n][0] == verified[n][1]} for n, _ in cells]
    items += [{"kind": "log", "path": rel(p)} for p in sorted(glob.glob(os.path.join(results_dir, "cell-*.log")))]
    for kind, fn in [("env", "env.json"), ("env_normalized", "env.normalized.json"), ("image", "image.txt"), ("manifest", "MANIFEST.sha256")]:
        p = os.path.join(results_dir, fn)
        if os.path.exists(p):
            exp, act = verified.get(fn, (None, None))
            items.append({"kind": kind, "path": rel(p), "sha256": exp, "sha256_verified": (exp is not None and exp == act) if exp else None})
    if engine_out_path and os.path.exists(engine_out_path):
        items.append({"kind": "engine_output", "path": rel(engine_out_path)})
    items.append({"kind": "availability", "path": obs_src})
    items.append({"kind": "prereg", "path": rel(os.path.join(CAMPAIGN, "identity.json"))})
    if events_path:
        items.append({"kind": "event_log", "path": rel(events_path)})
    manifest_verified = bool(verified) and all(e == a for e, a in verified.values())

    lb_note = {
        "do-h100": "Lower-bound $/1k accepted here is $0.980 (H100, $2.222 / 2,267). Beside the MI300X's $0.925 that is a 5.7 % gap, against the 53 % DISCLOSURES headline: different aggregations (all cells plus setup vs each arm's cheapest qualifying cell), not a contradiction.",
        "hotaisle-mi300x": "Lower-bound $/1k accepted here is $0.925 (MI300X, $2.220 / 2,400). Beside the H100's $0.980 that is a 5.7 % gap, against the 53 % DISCLOSURES headline: different aggregations (all cells plus setup vs each arm's cheapest qualifying cell), not a contradiction.",
    }[arm]

    record = {
        "schema": "second-run/run-ledger@1",
        "identity": {
            "run_id": f"run1/{arm}", "campaign": identity["campaign"], "run": "run1", "arm": arm, "tier": None, "knot_id": None,
            "seat_id": cfg["seat_id"], "provider": cfg["provider"], "region": cfg["region"], "sku": cfg["sku"],
            "gpus": env["gpus"], "host": env["host"],
            "model": {"id": identity["model"]["id"], "revision": identity["model"]["revision"], "precision": identity["model"]["precision"], "bytes": identity["model"]["bytes"]},
            "runtime": {"image": env["image"].split("@")[0], "digest": env["image"].split("@")[1] if "@" in env["image"] else None,
                        "engine": cfg["engine"], "engine_version": env["vllm_version"], "gpu": env["gpu"], "driver_or_rocm": env["driver_or_rocm"], "kernel": env.get("kernel")},
            "workload_id": identity["workload"]["workload_id"],
            "prereg": {"path": rel(os.path.join(CAMPAIGN, "identity.json")), "commit": git_sha_of(os.path.join(CAMPAIGN, "identity.json")),
                       "note": "local, unpushed commits (DISCLOSURES 'Timestamps'): privately recorded before the data, not publicly timestamped"},
            "null_reasons": {"knot_id": "Run 1 predates the Knot lifecycle; the reconstructed event log uses knot id run1/" + arm,
                             "tier": "Run 1 declared no tuning tiers (DISCLOSURES: unequal software)"},
        },
        "clocks": clocks, "acquisition": acquisition, "work": work, "sustained": sustained,
        "traversal": traversal, "money": money, "derived": derived,
        "receipts": {"items": items, "manifest_verified": manifest_verified},
        "notes": [
            "Funding: " + ("Hot Aisle arm ran on a $200 credit given by Hot Aisle; costs are modeled at undiscounted list ($2.99/GPU-hr)." if arm == "hotaisle-mi300x" else "DigitalOcean arm self-funded at list ($4.41/GPU-hr)."),
            "Unequal software (DISCLOSURES): CUDA arm vLLM 0.30.0 default FP8 MoE config; ROCm arm vLLM 0.27.1-dev whose image includes a tuned MI300X MoE config. serve.log not collected.",
            "Acceptance is the declared post-hoc per-request TTFT rule; the registered cell-level rule is kept per cell. Latency-only: no correctness was measured.",
            "One unrecorded warm-up pass (32 prompts at concurrency 8) preceded the first cell; not in any count.",
            "Arm C (DigitalOcean MI300X, $2.59) did not run; no claim that Hot Aisle is the cheapest MI300X.",
            "Clocks before 19:00 UTC are approximate to a few minutes (availability/README.md). Release time is missing, so no buyer-clock figure exists for Run 1.",
            lb_note,
        ],
        "built_by": {"tool": "ledger/ledger_build_run1.py", "at": iso(datetime.now(timezone.utc)), "inputs": [rel(results_dir), rel(os.path.join(CAMPAIGN, "identity.json")), obs_src]},
    }
    return record


def write_events(path, record):
    """Reconstructed Knot event log for one arm: ISSUED -> PROVISIONED -> RUNNING -> DELIVERED. Not contemporaneous."""
    if os.path.exists(path):
        os.remove(path)
    kid = record["identity"]["run_id"]
    c = record["clocks"]
    seat = record["identity"]["seat_id"]
    R = {"reconstructed": True, "source": "ledger_build_run1.py from retained files"}
    knot_lifecycle.new_knot(path, kid, "ledger_build_run1", {"workload_id": record["identity"]["workload_id"], **R}, ts=c["t_request"] or c["t_ready"])
    knot_lifecycle.append_event(path, kid, "PROVISIONED", "ledger_build_run1", seat, {"seat_id": seat, "t_ssh_or_ready": c["t_ready"], **R}, ts=c["t_ready"])
    knot_lifecycle.append_event(path, kid, "RUNNING", "ledger_build_run1", seat, {"t_work_start": c["t_work_start"], **R}, ts=c["t_work_start"])
    knot_lifecycle.append_event(path, kid, "DELIVERED", "ledger_build_run1", seat,
                                {"attempted": record["work"]["attempted"], "completed": record["work"]["completed"], "t_work_end": c["t_work_end"],
                                 "note": "no evaluator ran (KNOT_VERIFIED impossible); no invoice posted (SETTLED impossible); release time unrecorded (RELEASED impossible)", **R},
                                ts=c["t_work_end"])
    return knot_lifecycle.verify(knot_lifecycle.read_log(path))


def load_inputs(campaign):
    identity = json.load(open(os.path.join(campaign, "identity.json"), encoding="utf-8"))
    obs = [json.loads(l) for l in open(os.path.join(campaign, "availability", "observations.jsonl"), encoding="utf-8") if l.strip()]
    return identity, obs


def rel_to_campaign(p):
    try:
        return os.path.relpath(p, os.path.dirname(CAMPAIGN)).replace("\\", "/")
    except ValueError:
        return p.replace("\\", "/")


def build_all(campaign=CAMPAIGN, out_dir=os.path.join(HERE, "examples"), arms=tuple(ARMS), quiet=False):
    identity, obs = load_inputs(campaign)
    os.makedirs(out_dir, exist_ok=True)
    results = {}
    for arm in arms:
        rd = os.path.join(campaign, "results", arm)
        eng = os.path.join(campaign, "results", "run1-engine", f"{arm}.ttft1000.json")
        ev_path = os.path.join(out_dir, f"run1-{arm}.events.jsonl")
        rec = build_arm(arm, rd, identity, obs, eng, rel=rel_to_campaign, events_path=os.path.join(HERE, "examples", f"run1-{arm}.events.jsonl"))
        ev_errs = write_events(ev_path, rec)
        out = os.path.join(out_dir, f"run1-{arm}.ledger.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1, ensure_ascii=False)
            f.write("\n")
        errs = ledger_validate.validate(rec)
        results[arm] = (rec, errs, ev_errs)
        if not quiet:
            w, d, m = rec["work"], rec["derived"], rec["money"]
            print(f"{arm}: accepted {w['accepted']}/{w['attempted']}  lower-bound ${m['modeled_lower_bound_usd']:.2f} over {m['modeled_lower_bound_minutes']:.1f} min  "
                  f"${d['usd_per_1k_accepted']:.4f}/1k accepted (lower bound)  work {d['work_s_per_accepted']:.3f} s/accepted  buyer clock: unknown (no t_released)  "
                  f"window {rec['sustained']['window_s']:.0f}s (meets 60 min: {rec['sustained']['meets_required_window']})  "
                  f"manifest verified: {rec['receipts']['manifest_verified']}  validate: {'ok' if not errs else errs}  events: {'ok' if not ev_errs else ev_errs}")
    return results


# ---------------------------------------------------------------- self-test
def selftest():
    """Build from fixtures/run1-mini (two real cells per arm, generated texts stripped) into a temp dir
    and check the arithmetic against hand-computed values."""
    fx = os.path.join(HERE, "fixtures", "run1-mini")
    identity, obs = load_inputs(fx)
    ok = True
    def check(cond, msg):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {msg}")
        ok = ok and cond
    expect = json.load(open(os.path.join(fx, "expected.json"), encoding="utf-8"))
    with tmpdir("run1-selftest-") as td:
        for arm in ARMS:
            rd = os.path.join(fx, "results", arm)
            rec = build_arm(arm, rd, identity, obs, None, rel=lambda p: os.path.relpath(p, fx).replace("\\", "/"))
            errs = ledger_validate.validate(rec)
            check(not errs, f"{arm}: mini ledger validates ({errs[:2] if errs else 'no errors'})")
            e = expect[arm]
            check(rec["work"]["attempted"] == e["attempted"] and rec["work"]["accepted"] == e["accepted"], f"{arm}: attempted/accepted = {rec['work']['attempted']}/{rec['work']['accepted']} (expected {e['attempted']}/{e['accepted']})")
            check(rec["clocks"]["t_work_start"] == e["t_work_start"] and rec["clocks"]["t_work_end"] == e["t_work_end"], f"{arm}: work clocks {rec['clocks']['t_work_start']} .. {rec['clocks']['t_work_end']}")
            check(abs(rec["money"]["modeled_lower_bound_usd"] - e["modeled_usd"]) < 0.01 and rec["money"]["modeled_usd"] is None, f"{arm}: lower bound ${rec['money']['modeled_lower_bound_usd']} (expected {e['modeled_usd']}); full modeled null (no release)")
            check(rec["derived"]["wall_s_per_accepted"] is None and rec["derived"]["null_reasons"].get("wall_s_per_accepted") and rec["derived"]["work_s_per_accepted"] > 0, f"{arm}: buyer wall clock null with reason; work-time throughput kept separately")
            check(rec["clocks"]["t_released"] is None and "t_released" in rec["clocks"]["null_reasons"], f"{arm}: t_released null with reason")
            check(rec["work"]["correct"] is None and rec["work"]["null_reasons"].get("correct"), f"{arm}: correct null with reason")
            check(rec["sustained"]["meets_required_window"] is False, f"{arm}: sustained window {rec['sustained']['window_s']}s does not meet 3600 s")
            check(abs(rec["traversal"]["seconds_per_traversal"] - e["seconds_per_traversal"]) < 1e-6, f"{arm}: seconds/traversal {rec['traversal']['seconds_per_traversal']} (median ITL at c1)")
            check(rec["traversal"]["footprint_bytes"] == identity["model"]["bytes"] and rec["traversal"]["bytes_per_traversal"] is None, f"{arm}: footprint recorded, traversed bytes null (MoE unmeasured)")
            check(all(a["layer"] == "delivered" and a["method"] in ("console-create", "tui-provision") for a in rec["acquisition"]["attempts"]) and rec["acquisition"]["n_attempts"] == 1, f"{arm}: one delivered-layer attempt, listings excluded")
            check(rec["receipts"]["manifest_verified"] is True, f"{arm}: MANIFEST sha256 recomputed and matched")
            ev = os.path.join(td, f"{arm}.events.jsonl")
            ev_errs = write_events(ev, rec)
            st = knot_lifecycle.current_states(knot_lifecycle.read_log(ev))
            check(not ev_errs and st[rec["identity"]["run_id"]][0] == "DELIVERED", f"{arm}: reconstructed events verify and end at DELIVERED")
            bad = json.loads(json.dumps(rec)); bad["work"]["accepted"] = bad["work"]["completed"] + 1
            check(any("accepted" in x for x in ledger_validate.validate(bad)), f"{arm}: validator rejects accepted > completed")
        # a listing-shaped observation must never become an attempt
        fake = [dict(o, method="api", layer="listed", outcome="available") for o in obs]
        rec = build_arm("do-h100", os.path.join(fx, "results", "do-h100"), identity, fake, None, rel=lambda p: p)
        check(rec["acquisition"]["n_attempts"] == 0 and rec["clocks"]["t_request"] is None, "listed-layer rows produce no attempt and no t_request")
    print(f"ledger_build_run1 selftest: {'all passed' if ok else 'FAILURES'}")
    return ok


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    out = os.path.join(HERE, "examples")
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
    res = build_all(out_dir=out)
    sys.exit(0 if all(not e and not ev for _, e, ev in res.values()) else 1)
