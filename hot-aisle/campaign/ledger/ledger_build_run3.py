#!/usr/bin/env python3
"""Assemble a run-ledger@1 record from one Run 3 arm directory (lane A's arm.py output) plus, optionally,
the operator's closure file (what arm.py cannot know: t_request, t_released, acquisition attempts, invoice).
Stdlib only. Reads run3/ outputs; never writes there.

    python ledger_build_run3.py <arm-dir> [--closure closure.json] [--out DIR] [--identity ../identity.json]
    python ledger_build_run3.py --selftest          builds fixtures/run3-mini/arm-amd-t0 into a temp dir and checks the numbers

Inputs inside <arm-dir> (names as arm.py / replay.py / convert.py / grade.py write them):
  ledger.json           flat arm summary: schema second-run/run3-arm-summary@1 (or the transitional second-run/run-ledger@1 flat form)
                        keys: status, arm (A|N), tier, timestamps, hourly_list_usd, funding, restarts, attempted, completed, failed, lost
  ledger-times.json     t_request, t_ssh, t_ready, t_work_start, t_work_end, t_released, t_script_start, t_script_end (isoformat, +00:00 or Z)
  env.json              kind, tier, image, model, revision, gpu_count, tensor_parallel, attention_backend[], linear_kernel[], vllm_version
  invocation.json       rate_factor, trace_sha256, trace_start, tasks_sha256, watchdog_s
  detailed.json         page-engine detailed schema: num_prompts, completed, failed, errors[], ttfts[], latencies[], queue_times[], synthetic, metadata{}
  replay/plan.json      duration_s, start_ts, requests[]      replay/replay-status.json   interrupted
  replay/buckets.json   [{offset_s, duration_s, attempted, completed, failed, correct, accepted, completed_per_s}]  (accepted null until graded)
  grade/evaluation.json hot-aisle/request-evaluation@1: passed[], evaluator, criterion_id, source_sha256 (sha of detailed.json)
  grade/buckets.json    grade.summary: buckets[] as above with accepted filled, task_classes{}, minimum/median accepted per s
  MANIFEST.sha256       every retained file; recomputed here
Closure file (second-run/run-closure@1): run_id, campaign, seat_id, provider, region, sku, host, t_request, t_released,
  attempts[] (availability delivered-row shape: layer delivered, method api-create|console-create|tui-provision), billed_usd, billed_ref,
  credits_usd, payer, prereg_commit.
"""
import json
import os
import statistics
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CAMPAIGN = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import knot_lifecycle  # noqa: E402
import ledger_validate  # noqa: E402
from ledger_common import (ATTEMPT_METHODS, any_iso, attempt_from_observation, classify_observation, iso,  # noqa: E402
                           parse_iso, read_manifest, receipt_kind, sha256_file, tmpdir, verify_manifest)

ACCEPTED_SUMMARY_SCHEMAS = ("second-run/run3-arm-summary@1", "second-run/run-ledger@1")
SEAT_BY_KIND = {
    "amd": {"seat_id": "hotaisle-mi300x-1x-enc1", "provider": "hotaisle", "region": "enc1", "sku": "vm-mi300x-1x"},
    "nvidia": {"seat_id": "do-h100-nyc2", "provider": "digitalocean", "region": "nyc2", "sku": "gpu-h100x1-80gb"},
}
TTFT_GATE_S, E2E_GATE_S = 1.0, 60.0          # run3/PREREG.md gates, from the SCHEDULED arrival
REQUIRED_WINDOW_S, BUCKET_S = 3600, 300


class BuildError(Exception):
    pass


def _load(path, required=True):
    if not os.path.exists(path):
        if required:
            raise BuildError(f"missing {path}")
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise BuildError(f"{path}: not JSON ({e})")


def _rel(p, base):
    try:
        return os.path.relpath(p, base).replace("\\", "/")
    except ValueError:
        return p.replace("\\", "/")


def build(arm_dir, closure=None, identity=None, rel_base=None, events_path=None):
    arm_dir = os.path.abspath(arm_dir)
    rel_base = rel_base or os.path.dirname(CAMPAIGN)
    R = lambda p: _rel(p, rel_base)
    summary = _load(os.path.join(arm_dir, "ledger.json"))
    if summary.get("schema") not in ACCEPTED_SUMMARY_SCHEMAS or "timestamps" not in summary or "hourly_list_usd" not in summary:
        raise BuildError(f"ledger.json is not a Run 3 arm summary (schema {summary.get('schema')!r}); expected {ACCEPTED_SUMMARY_SCHEMAS}")
    times = _load(os.path.join(arm_dir, "ledger-times.json"))
    env = _load(os.path.join(arm_dir, "env.json"), required=False) or {}
    invocation = _load(os.path.join(arm_dir, "invocation.json"), required=False) or {}
    detailed = _load(os.path.join(arm_dir, "detailed.json"), required=False)
    plan = _load(os.path.join(arm_dir, "replay", "plan.json"), required=False)
    status = _load(os.path.join(arm_dir, "replay", "replay-status.json"), required=False)
    replay_buckets = _load(os.path.join(arm_dir, "replay", "buckets.json"), required=False)
    sidecar = _load(os.path.join(arm_dir, "grade", "evaluation.json"), required=False)
    gsum = _load(os.path.join(arm_dir, "grade", "buckets.json"), required=False)
    manifest = read_manifest(os.path.join(arm_dir, "MANIFEST.sha256"))
    verified = verify_manifest(arm_dir, manifest)
    closure = closure or {}
    kind = env.get("kind") or {"A": "amd", "N": "nvidia"}.get(summary.get("arm"))
    seat = SEAT_BY_KIND.get(kind)
    if not seat:
        raise BuildError(f"unknown arm kind {kind!r}")
    tier = summary.get("tier") or env.get("tier")
    arm_label = f"{summary.get('arm')}/{tier}"
    ident = identity or _load(os.path.join(CAMPAIGN, "identity.json"), required=False) or {}
    model_bytes = (ident.get("model") or {}).get("bytes")
    notes = []
    synthetic = bool((detailed or {}).get("synthetic") or (plan or {}).get("synthetic") or closure.get("synthetic"))
    if synthetic:
        notes.append("SYNTHETIC: this record was built from fixture evidence; it establishes no result.")

    # ---- clocks -------------------------------------------------------------
    clocks = {k: None for k in ("t_request", "t_ssh", "t_ready", "t_work_start", "t_work_end", "t_released")}
    for k in ("t_ssh", "t_ready", "t_work_start", "t_work_end"):
        clocks[k] = any_iso(times.get(k))
    clocks["t_request"] = any_iso(closure.get("t_request") or times.get("t_request"))
    clocks["t_released"] = any_iso(closure.get("t_released") or times.get("t_released"))
    clocks["sources"] = {
        "t_request": {"source": "closure.json (operator: when the create/provision was requested)" if closure.get("t_request") else "ledger-times.json", "precision": "operator-recorded"},
        "t_ssh": {"source": "arm.py --t-ssh (observed before the script started)", "precision": "1 s"},
        "t_ready": {"source": "ledger-times.json: /v1/models listed the model", "precision": "1 s"},
        "t_work_start": {"source": "ledger-times.json: replay child started", "precision": "1 s"},
        "t_work_end": {"source": "ledger-times.json: replay child exited (or the finally-block stamp after an interrupt)", "precision": "1 s"},
        "t_released": {"source": closure.get("t_released_source") or "closure.json (provider confirmation; container stop is not release)", "precision": "operator-recorded"},
        "t_script_start": any_iso(times.get("t_script_start")), "t_script_end": any_iso(times.get("t_script_end")),
    }
    clocks["null_reasons"] = {}
    for k in ("t_request", "t_ssh", "t_ready", "t_work_start", "t_work_end", "t_released"):
        if clocks[k] is None:
            clocks["null_reasons"][k] = {
                "t_request": "not in closure.json: arm.py cannot observe the capacity request; the operator must supply it",
                "t_released": "not in closure.json: provider release is external to the seat (arm.py note: container stop is not release)",
            }.get(k, f"ledger-times.json has null {k} (arm status {summary.get('status')!r})")

    # ---- acquisition ---------------------------------------------------------
    raw_attempts = closure.get("attempts") or []
    attempts = []
    for o in raw_attempts:
        layer = classify_observation(o)
        if layer != "delivered":
            raise BuildError(f"closure attempt {o.get('attempt_id')!r} is layer {layer!r}: only delivered-layer rows are attempts (a listing is not an attempt)")
        a = attempt_from_observation(o, "closure.json")
        if a["method"] not in ATTEMPT_METHODS:
            raise BuildError(f"closure attempt {o.get('attempt_id')!r} has method {o.get('method')!r}; use one of {list(ATTEMPT_METHODS)} (lane C renamed create-attempt)")
        attempts.append(a)
    n_alloc = sum(1 for a in attempts if a["provisioned"])
    acquisition = {"attempts": attempts, "n_attempts": len(attempts), "n_allocations": n_alloc,
                   "yield": (n_alloc / len(attempts)) if attempts else None}
    if not attempts:
        acquisition["null_reasons"] = {"yield": "no attempts in closure.json (arm.py writes acquisition_attempts null: acquisition is external to the seat)"}
        notes.append("Acquisition attempts are not in this record: supply them in closure.json from availability/observations.jsonl delivered rows.")

    # ---- work ---------------------------------------------------------------
    n = (detailed or {}).get("num_prompts") if detailed else summary.get("attempted")
    completed = (detailed or {}).get("completed") if detailed else summary.get("completed")
    errors = (detailed or {}).get("errors") or []
    lost = sum(1 for e in errors if e == "lost_or_unsent_after_interrupt") if detailed else summary.get("lost")
    unsent_note = "replay marks never-sent and sent-but-unanswered requests alike as lost_or_unsent_after_interrupt; 'lost' here counts that label (schema: sent and unanswered)"
    correct = accepted = None
    evaluator = None
    task_classes = None
    if sidecar:
        if sidecar.get("schema") != "hot-aisle/request-evaluation@1":
            raise BuildError(f"grade/evaluation.json schema {sidecar.get('schema')!r} is not hot-aisle/request-evaluation@1")
        if detailed is None:
            raise BuildError("grade/evaluation.json present but detailed.json missing")
        actual = sha256_file(os.path.join(arm_dir, "detailed.json"))
        if sidecar.get("source_sha256") != actual:
            raise BuildError(f"grade sidecar is bound to detailed.json sha {sidecar.get('source_sha256')}, on disk {actual}: refusing to join grades to different bytes")
        passed = sidecar.get("passed") or []
        if len(passed) != n or any(type(v) is not bool for v in passed):
            raise BuildError("sidecar passed[] length/type does not match detailed.json")
        correct = sum(passed)
        q, t, l = detailed["queue_times"], detailed["ttfts"], detailed["latencies"]
        accepted = sum(1 for i in range(n) if passed[i] and not errors[i] and q[i] + t[i] <= TTFT_GATE_S and q[i] + l[i] <= E2E_GATE_S)
        evaluator = {"name": sidecar.get("evaluator"), "frozen": True, "ref": f"{sidecar.get('criterion_id')} ; sidecar sha256:{sha256_file(os.path.join(arm_dir, 'grade', 'evaluation.json'))}",
                     "criterion_id": sidecar.get("criterion_id"), "result_sha256": sidecar.get("result_sha256")}
        if gsum and gsum.get("task_classes"):
            task_classes = gsum["task_classes"]
            g_acc = sum(v.get("accepted") or 0 for v in task_classes.values())
            if g_acc != accepted:
                raise BuildError(f"accepted recomputed from detailed.json + sidecar = {accepted}, but grade/buckets.json task_classes sum to {g_acc}")
    work = {
        "unit": "request", "evaluator": evaluator,
        "acceptance_rule": {"basis": "run3/PREREG.md: accepted = completed AND EvalPlus base+plus pass AND first text <= 1 s AND end <= 60 s from the SCHEDULED arrival (queue_time + ttft, queue_time + latency in detailed.json)",
                            "ttft_ms": 1000, "e2e_ms": 60000, "correctness": sidecar is not None, "queue": True},
        "attempted": n, "completed": completed, "correct": correct, "accepted": accepted,
        "lost": lost, "restarts": summary.get("restarts"), "cells": None, "task_classes": task_classes,
        "null_reasons": {"cells": "replay run, not a cell sweep"},
    }
    if sidecar is None:
        work["null_reasons"].update({"evaluator": "no grade/evaluation.json: the arm is ungraded (status " + str(summary.get("status")) + ")",
                                     "correct": "ungraded: no frozen evaluator sidecar bound to detailed.json",
                                     "accepted": "ungraded: acceptance requires correctness (PREREG); latency alone does not accept"})
    if task_classes is None:
        work["null_reasons"]["task_classes"] = "grade/buckets.json (grade.summary) not present"
    if lost is None:
        work["null_reasons"]["lost"] = "no detailed.json and no lost count in the arm summary"
    if work["restarts"] is None:
        work["null_reasons"]["restarts"] = "arm summary has no restarts field"
    notes.append(unsent_note)

    # ---- sustained ----------------------------------------------------------
    src_b = (gsum or {}).get("buckets") if gsum else None
    graded_buckets = src_b is not None
    if src_b is None:
        src_b = replay_buckets
    buckets = None
    if src_b:
        buckets = [{"index": i, "start_s": b["offset_s"], "duration_s": b["duration_s"], "attempted": b.get("attempted"),
                    "completed": b.get("completed"), "correct": b.get("correct"), "accepted": b.get("accepted")} for i, b in enumerate(src_b)]
    window_s = (plan or {}).get("duration_s")
    interrupted = (status or {}).get("interrupted") if status else None
    sustained = {"required_window_s": REQUIRED_WINDOW_S, "bucket_s": BUCKET_S, "window_s": window_s,
                 "meets_required_window": bool(window_s is not None and window_s >= REQUIRED_WINDOW_S and interrupted is False and graded_buckets),
                 "interrupted": interrupted, "buckets": buckets,
                 "min_accepted_per_bucket": None, "median_accepted_per_bucket": None, "last_q_over_first_q": None,
                 "note": "buckets are by SCHEDULED arrival (replay.buckets); accepted is filled only after grading (grade.summary)", "null_reasons": {}}
    if buckets and graded_buckets:
        counts = [b["accepted"] for b in buckets]
        sustained["min_accepted_per_bucket"] = min(counts)
        sustained["median_accepted_per_bucket"] = statistics.median(counts)
        q = max(1, len(counts) // 4)
        first, last = sum(counts[:q]), sum(counts[-q:])
        sustained["last_q_over_first_q"] = (last / first) if first else None
        if first == 0:
            sustained["null_reasons"]["last_q_over_first_q"] = "first quarter had zero accepted (PREREG: null, not zero)"
        sustained["source_summary"] = {k: gsum.get(k) for k in ("minimum_accepted_per_s", "median_accepted_per_s", "last_quarter_over_first_quarter", "zero_first_quarter")}
    else:
        for k in ("min_accepted_per_bucket", "median_accepted_per_bucket", "last_q_over_first_q"):
            sustained["null_reasons"][k] = "ungraded: accepted per bucket needs the grade sidecar"
        if buckets is None:
            sustained["null_reasons"]["buckets"] = "no replay/buckets.json or grade/buckets.json"
    if window_s is None:
        sustained["null_reasons"]["window_s"] = "no replay/plan.json"
    if interrupted is None:
        sustained["null_reasons"]["interrupted"] = "no replay/replay-status.json"
    if sustained["meets_required_window"] is False and window_s and window_s >= REQUIRED_WINDOW_S:
        sustained["note"] += "; window long enough but " + ("interrupted" if interrupted else "ungraded") + ", so it does not qualify as sustained"

    # ---- traversal ----------------------------------------------------------
    traversal = {"path": "resident-hbm", "footprint_bytes": model_bytes,
                 "footprint_bytes_basis": "resident checkpoint bytes (identity.json); allocated weights, not traversed bytes" if model_bytes else None,
                 "bytes_per_traversal": None, "bytes_per_traversal_basis": None, "traversals": None, "traversals_basis": None,
                 "seconds_per_traversal": None, "seconds_per_traversal_basis": None,
                 "accepted_closures_per_traversal": None, "accepted_closures_per_traversal_basis": None, "by_depth": None,
                 "null_reasons": {k: "Run 3 does not instrument weight traversals (PREREG: token counts do not substitute for measured traversals)"
                                  for k in ("bytes_per_traversal", "bytes_per_traversal_basis", "traversals", "traversals_basis", "seconds_per_traversal",
                                            "seconds_per_traversal_basis", "accepted_closures_per_traversal", "accepted_closures_per_traversal_basis", "by_depth")}}
    if model_bytes is None:
        traversal["null_reasons"]["footprint_bytes"] = "identity.json not available to the builder"
        traversal["null_reasons"]["footprint_bytes_basis"] = "see footprint_bytes"

    # ---- money --------------------------------------------------------------
    rate = summary.get("hourly_list_usd")
    gpus = env.get("gpu_count") or 1
    full = None
    if clocks["t_request"] and clocks["t_released"]:
        full = (parse_iso(clocks["t_released"]) - parse_iso(clocks["t_request"])).total_seconds() / 60.0
    lb_from = clocks["t_request"] or clocks["t_ssh"] or clocks["t_ready"]
    lb_to = clocks["t_released"] or clocks["t_work_end"] or any_iso(times.get("t_script_end"))
    lb = (parse_iso(lb_to) - parse_iso(lb_from)).total_seconds() / 60.0 if lb_from and lb_to else None
    money = {"currency": "USD", "list_rate_per_gpu_hr": rate,
             "billing": {"amd": "per-minute", "nvidia": "per-second-5min-min"}[kind],
             "payer": closure.get("payer") or "self (PREREG declaration: " + str(summary.get("funding")) + ")",
             "modeled_minutes": round(full, 2) if full is not None else None,
             "modeled_minutes_basis": "t_request -> t_released from closure.json (the buyer's window)" if full is not None else None,
             "modeled_usd": round(rate * gpus * full / 60.0, 4) if full is not None and rate is not None else None,
             "modeled_lower_bound_minutes": round(lb, 2) if lb is not None else None,
             "modeled_lower_bound_usd": round(rate * gpus * lb / 60.0, 4) if lb is not None and rate is not None else None,
             "modeled_lower_bound_basis": (f"{'t_request' if clocks['t_request'] else ('t_ssh' if clocks['t_ssh'] else 't_ready')} -> {'t_released' if clocks['t_released'] else ('t_work_end' if clocks['t_work_end'] else 't_script_end')} at list; "
                                          + ("equals the full window" if full is not None else "release and/or request unknown, so the billable window is at least this long")) if lb is not None else None,
             "billed_usd": closure.get("billed_usd"), "billed_ref": closure.get("billed_ref"), "credits_usd": closure.get("credits_usd"),
             "energy": {"watts_mean": None, "kwh": None, "tariff_usd_per_kwh": None, "usd": None, "meter": None, "reason": "cloud seat; no meter"},
             "null_reasons": {}}
    if full is None:
        money["null_reasons"].update({"modeled_minutes": "t_request and/or t_released unknown (closure.json)", "modeled_minutes_basis": "see modeled_minutes",
                                      "modeled_usd": "buyer's window unknown; see modeled_lower_bound_usd"})
    if lb is None:
        money["null_reasons"].update({"modeled_lower_bound_minutes": "no usable clocks", "modeled_lower_bound_usd": "no usable clocks", "modeled_lower_bound_basis": "no usable clocks"})
    for k, why in (("billed_usd", "invoice not posted / not entered in closure.json"), ("billed_ref", "see billed_usd"), ("credits_usd", "not entered in closure.json (PREREG: credit, modeled and invoice are three fields)")):
        if money[k] is None:
            money["null_reasons"][k] = why

    # ---- derived ------------------------------------------------------------
    work_s = None
    if clocks["t_work_start"] and clocks["t_work_end"]:
        work_s = (parse_iso(clocks["t_work_end"]) - parse_iso(clocks["t_work_start"])).total_seconds()
    cost_basis = "modeled" if money["modeled_usd"] is not None else "modeled-lower-bound"
    cost = money["modeled_usd"] if cost_basis == "modeled" else money["modeled_lower_bound_usd"]
    derived = {"usd_per_accepted": (cost / accepted) if (cost is not None and accepted) else None,
               "usd_per_1k_accepted": (cost / accepted * 1000) if (cost is not None and accepted) else None,
               "cost_basis": cost_basis,
               "wall_s_per_accepted": (full * 60.0 / accepted) if (full is not None and accepted) else None,
               "work_s_per_accepted": (work_s / accepted) if (work_s is not None and accepted) else None,
               "accepted_per_work_s": (accepted / work_s) if (work_s and accepted is not None) else None,
               "null_reasons": {}}
    if derived["usd_per_accepted"] is None:
        derived["null_reasons"]["usd_per_accepted"] = "accepted is null (ungraded) or zero (PREREG: zero accepted => null cost per unit)" if not accepted else "no cost figure"
        derived["null_reasons"]["usd_per_1k_accepted"] = "see usd_per_accepted"
    if derived["wall_s_per_accepted"] is None:
        derived["null_reasons"]["wall_s_per_accepted"] = "buyer's clock needs t_request and t_released (closure.json) and accepted > 0; work time is not a substitute"
    if derived["work_s_per_accepted"] is None:
        derived["null_reasons"]["work_s_per_accepted"] = "accepted null/zero or work clocks missing"
    if derived["accepted_per_work_s"] is None:
        derived["null_reasons"]["accepted_per_work_s"] = "accepted null or work clocks missing"

    # ---- identity / receipts ------------------------------------------------
    image = env.get("image") or ((detailed or {}).get("metadata") or {}).get("runtime_digest") or "UNVERIFIED"
    identity_g = {
        "run_id": closure.get("run_id") or f"run3/{arm_label}", "campaign": closure.get("campaign") or "run3-2026-09", "run": "run3",
        "arm": arm_label, "tier": tier, "knot_id": closure.get("knot_id"),
        "seat_id": closure.get("seat_id") or seat["seat_id"], "provider": closure.get("provider") or seat["provider"],
        "region": closure.get("region") or seat["region"], "sku": closure.get("sku") or seat["sku"], "gpus": gpus, "host": closure.get("host"),
        "model": {"id": env.get("model") or (plan or {}).get("model"), "revision": env.get("revision") or (plan or {}).get("revision"), "precision": "FP8", "bytes": model_bytes},
        "runtime": {"image": image.split("@")[0], "digest": image.split("@")[1] if "@" in image else None, "engine": "vllm", "engine_version": env.get("vllm_version"),
                    "attention_backend": env.get("attention_backend"), "linear_kernel": env.get("linear_kernel")},
        "workload_id": ((detailed or {}).get("metadata") or {}).get("workload_id") or ("sha256:" + invocation["tasks_sha256"] if invocation.get("tasks_sha256") else "UNVERIFIED"),
        "prereg": {"path": R(os.path.join(CAMPAIGN, "run3", "PREREG.md")), "commit": closure.get("prereg_commit"),
                   "trace_sha256": invocation.get("trace_sha256"), "trace_start": invocation.get("trace_start"), "rate_factor": invocation.get("rate_factor")},
        "null_reasons": {},
    }
    if identity_g["knot_id"] is None:
        identity_g["null_reasons"]["knot_id"] = "no knot_id in closure.json"
    if identity_g["host"] is None:
        identity_g["null_reasons"]["host"] = "arm.py does not record the hostname; supply in closure.json"
    items = []
    for name, (exp, act) in sorted(verified.items()):
        items.append({"kind": receipt_kind(name), "path": R(os.path.join(arm_dir, name)), "sha256": exp, "sha256_verified": exp == act})
    items.append({"kind": "manifest", "path": R(os.path.join(arm_dir, "MANIFEST.sha256"))})
    items.append({"kind": "prereg", "path": identity_g["prereg"]["path"]})
    if closure:
        items.append({"kind": "closure", "path": closure.get("_path", "closure.json")})
    if events_path:
        items.append({"kind": "event_log", "path": R(events_path)})
    manifest_verified = bool(verified) and all(e == a for e, a in verified.values())
    if not manifest_verified:
        notes.append("MANIFEST.sha256 did NOT verify for every file: " + ", ".join(k for k, (e, a) in verified.items() if e != a)[:300])
    notes.append(f"arm.py status: {summary.get('status')}; funding declaration: {summary.get('funding')}")
    notes.append(f"Declared rate factor {invocation.get('rate_factor')} on the frozen trace; PREREG: at 0.10 the run measures price and correctness under real arrivals, not capacity.")
    if kind == "amd":
        notes.append("AMD T0 carries VLLM_ROCM_USE_AITER=1 with the attention backend auto-selected; 'auto' is not 'default' (env.json names the selection).")

    record = {"schema": "second-run/run-ledger@1", "identity": identity_g, "clocks": clocks, "acquisition": acquisition, "work": work,
              "sustained": sustained, "traversal": traversal, "money": money, "derived": derived,
              "receipts": {"items": items, "manifest_verified": manifest_verified}, "notes": notes,
              "built_by": {"tool": "ledger/ledger_build_run3.py", "at": iso(datetime.now(timezone.utc)), "inputs": [R(arm_dir)] + ([closure.get("_path", "closure.json")] if closure else [])}}
    return record


def write_events(path, record):
    """Reconstructed Knot log for the arm, as far as the receipts go."""
    if os.path.exists(path):
        os.remove(path)
    kid = record["identity"]["run_id"]; c = record["clocks"]; seat = record["identity"]["seat_id"]; w = record["work"]
    Rr = {"reconstructed": True, "source": "ledger_build_run3.py"}
    knot_lifecycle.new_knot(path, kid, "ledger_build_run3", {"workload_id": record["identity"]["workload_id"], **Rr}, ts=c["t_request"] or c["t_ssh"])
    for a in record["acquisition"]["attempts"]:
        if not a["provisioned"]:
            knot_lifecycle.append_event(path, kid, "RESERVED", "ledger_build_run3", seat, {"attempt_id": a.get("attempt_id"), **Rr}, ts=a["ts"])
            knot_lifecycle.append_event(path, kid, "PROVISIONING_FAILED", "ledger_build_run3", seat, {"reason": a.get("outcome"), **Rr}, ts=a["ts"])
            knot_lifecycle.append_event(path, kid, "ISSUED", "ledger_build_run3", None, {"retry": True, **Rr}, ts=a["ts"])
    if c["t_ready"] or c["t_ssh"]:
        knot_lifecycle.append_event(path, kid, "PROVISIONED", "ledger_build_run3", seat, {"seat_id": seat, "t_ssh_or_ready": c["t_ready"] or c["t_ssh"], **Rr}, ts=c["t_ready"] or c["t_ssh"])
    if c["t_work_start"]:
        knot_lifecycle.append_event(path, kid, "RUNNING", "ledger_build_run3", seat, {"t_work_start": c["t_work_start"], **Rr}, ts=c["t_work_start"])
    if c["t_work_end"] and w["attempted"] is not None:
        knot_lifecycle.append_event(path, kid, "DELIVERED", "ledger_build_run3", seat, {"attempted": w["attempted"], "completed": w["completed"], "t_work_end": c["t_work_end"], **Rr}, ts=c["t_work_end"])
        if w["correct"] is not None:
            knot_lifecycle.append_event(path, kid, "KNOT_VERIFIED", "ledger_build_run3", seat, {"evaluator": w["evaluator"]["name"], "correct": w["correct"], "accepted": w["accepted"], **Rr}, ts=c["t_work_end"])
    if c["t_released"]:
        knot_lifecycle.append_event(path, kid, "RELEASED", "ledger_build_run3", seat, {"t_released": c["t_released"], **Rr}, ts=c["t_released"])
    return knot_lifecycle.verify(knot_lifecycle.read_log(path))


def build_to(arm_dir, closure_path, out_dir, identity_path=None):
    closure = None
    if closure_path:
        closure = _load(closure_path)
        closure["_path"] = _rel(os.path.abspath(closure_path), os.path.dirname(CAMPAIGN))
    identity = _load(identity_path) if identity_path else None
    os.makedirs(out_dir, exist_ok=True)
    tag = os.path.basename(os.path.normpath(arm_dir))
    ev_path = os.path.join(out_dir, f"run3-{tag}.events.jsonl")
    rec = build(arm_dir, closure, identity, events_path=ev_path)
    ev_errs = write_events(ev_path, rec)
    out = os.path.join(out_dir, f"run3-{tag}.ledger.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1, ensure_ascii=False); f.write("\n")
    errs = ledger_validate.validate(rec)
    return rec, errs, ev_errs, out


# ---------------------------------------------------------------- self-test
def selftest():
    fx = os.path.join(HERE, "fixtures", "run3-mini")
    arm = os.path.join(fx, "arm-amd-t0")
    ok = True
    def check(cond, msg):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {msg}")
        ok = ok and cond
    with tmpdir("run3-selftest-") as td:
        rec, errs, ev_errs, _ = build_to(arm, os.path.join(fx, "closure.json"), td)
        check(not errs, f"graded + closed record validates ({errs[:2] if errs else 'no errors'})")
        w = rec["work"]
        check((w["attempted"], w["completed"], w["correct"], w["accepted"], w["lost"]) == (6, 5, 3, 2, 0), f"work counts attempted/completed/correct/accepted/lost = {w['attempted']}/{w['completed']}/{w['correct']}/{w['accepted']}/{w['lost']} (expected 6/5/3/2/0: index 2 misses the 1 s TTFT gate from the scheduled arrival, index 4 is a transport error)")
        check(w["evaluator"]["frozen"] is True and "evalplus-0.3.1" in w["evaluator"]["ref"], "evaluator frozen with criterion id and sidecar sha in ref")
        s = rec["sustained"]
        check(len(s["buckets"]) == 12 and s["buckets"][0]["start_s"] == 0 and s["buckets"][1]["start_s"] == 300 and sum(b["accepted"] for b in s["buckets"]) == 2, "12 buckets mapped offset_s -> start_s with accepted summing to 2")
        check(s["meets_required_window"] is True and s["interrupted"] is False and s["window_s"] == 3600, "3600 s uninterrupted graded window meets the requirement")
        m = rec["money"]
        check(m["list_rate_per_gpu_hr"] == 2.99 and abs(m["modeled_minutes"] - 100.0) < 0.01 and abs(m["modeled_usd"] - 4.9833) < 0.001, f"hourly_list_usd -> list rate; modeled over request->release = {m['modeled_minutes']} min = ${m['modeled_usd']}")
        d = rec["derived"]
        check(d["cost_basis"] == "modeled" and abs(d["usd_per_accepted"] - 4.9833 / 2) < 1e-3, f"$/accepted {d['usd_per_accepted']:.4f} on the full window")
        check(abs(d["wall_s_per_accepted"] - 3000) < 1e-6 and abs(d["work_s_per_accepted"] - 3605 / 2) < 1e-6, f"buyer wall clock {d['wall_s_per_accepted']} s/accepted (request->release) vs work {d['work_s_per_accepted']} s/accepted kept separate")
        a = rec["acquisition"]
        check(a["n_attempts"] == 2 and a["n_allocations"] == 1 and a["yield"] == 0.5 and all(x["layer"] == "delivered" for x in a["attempts"]), "two delivered-layer attempts, one allocation, yield 0.5")
        check(rec["receipts"]["manifest_verified"] is True and any(i["kind"] == "evaluation" for i in rec["receipts"]["items"]), "MANIFEST recomputed and matched; sidecar listed as a receipt")
        check(rec["traversal"]["footprint_bytes"] == 31187041238 and rec["traversal"]["bytes_per_traversal"] is None, "footprint from identity.json; traversed bytes null (unmeasured)")
        check(not ev_errs and knot_lifecycle.current_states(knot_lifecycle.read_log(os.path.join(td, "run3-arm-amd-t0.events.jsonl")))[rec["identity"]["run_id"]][0] == "RELEASED", "reconstructed Knot log ends RELEASED (failed attempt, retry, provisioned, verified)")
        check(any("SYNTHETIC" in n for n in rec["notes"]), "synthetic fixture flagged in notes")
        # without closure: buyer clock unknown, lower bound only
        rec2, errs2, _, _ = build_to(arm, None, td)
        check(not errs2 and rec2["money"]["modeled_usd"] is None and rec2["derived"]["wall_s_per_accepted"] is None and rec2["money"]["modeled_lower_bound_usd"] is not None, f"no closure: modeled null, wall clock null, lower bound ${rec2['money']['modeled_lower_bound_usd']} over {rec2['money']['modeled_lower_bound_basis'].split(' at list')[0]}")
        # ungraded arm: copy without grade/
        import shutil
        ung = os.path.join(td, "arm-ungraded"); shutil.copytree(arm, ung); shutil.rmtree(os.path.join(ung, "grade"))
        rec3, errs3, _, _ = build_to(ung, None, td)
        check(not errs3 and rec3["work"]["correct"] is None and rec3["work"]["accepted"] is None and rec3["sustained"]["meets_required_window"] is False, "ungraded arm: correct/accepted null with reasons, not sustained-qualified; still validates")
        # legacy flat schema name accepted during transition
        leg = os.path.join(td, "arm-legacy"); shutil.copytree(arm, leg)
        p = os.path.join(leg, "ledger.json"); j = json.load(open(p)); j["schema"] = "second-run/run-ledger@1"; json.dump(j, open(p, "w"))
        rec4, errs4, _, _ = build_to(leg, os.path.join(fx, "closure.json"), td)
        check(not errs4 and rec4["work"]["accepted"] == 2, "transitional flat 'second-run/run-ledger@1' arm summary accepted")
        # tampered detailed.json: sidecar binding refuses
        tam = os.path.join(td, "arm-tampered"); shutil.copytree(arm, tam)
        with open(os.path.join(tam, "detailed.json"), "a") as f: f.write("\n")
        try:
            build_to(tam, None, td); check(False, "sidecar bound to different detailed.json bytes refused")
        except BuildError as e:
            check("refusing to join grades" in str(e), "sidecar bound to different detailed.json bytes refused")
        # create-attempt method refused with the rename named
        cl = json.load(open(os.path.join(fx, "closure.json"))); cl["attempts"][1]["method"] = "create-attempt"
        cp = os.path.join(td, "closure-bad.json"); json.dump(cl, open(cp, "w"))
        try:
            build_to(arm, cp, td); check(False, "closure attempt with method create-attempt refused")
        except BuildError as e:
            check("renamed create-attempt" in str(e), "closure attempt with method create-attempt refused, rename named")
        # a listed row in attempts refused
        cl = json.load(open(os.path.join(fx, "closure.json"))); cl["attempts"][0].update({"layer": "listed", "method": "api"})
        json.dump(cl, open(cp, "w"))
        try:
            build_to(arm, cp, td); check(False, "listed-layer row as an attempt refused")
        except BuildError as e:
            check("listing is not an attempt" in str(e), "listed-layer row as an attempt refused")
    print(f"ledger_build_run3 selftest: {'all passed' if ok else 'FAILURES'}")
    return ok


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    if argv[0] == "--selftest":
        return 0 if selftest() else 1
    arm_dir = argv[0]; closure = None; out = os.path.join(HERE, "examples"); identity = None
    i = 1
    while i < len(argv):
        if argv[i] == "--closure": closure = argv[i + 1]; i += 2
        elif argv[i] == "--out": out = argv[i + 1]; i += 2
        elif argv[i] == "--identity": identity = argv[i + 1]; i += 2
        else: print(f"unknown arg {argv[i]}"); return 1
    try:
        rec, errs, ev_errs, path = build_to(arm_dir, closure, out, identity)
    except BuildError as e:
        print(f"REFUSED: {e}"); return 2
    w, d = rec["work"], rec["derived"]
    print(f"{rec['identity']['run_id']}: attempted {w['attempted']} completed {w['completed']} correct {w['correct']} accepted {w['accepted']}  "
          f"cost basis {d['cost_basis']} $/accepted {d['usd_per_accepted']}  wall s/accepted {d['wall_s_per_accepted']}  -> {path}  "
          f"validate: {'ok' if not errs else errs}  events: {'ok' if not ev_errs else ev_errs}")
    return 0 if not errs and not ev_errs else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
