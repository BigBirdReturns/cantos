#!/usr/bin/env python3
"""Regenerate the validator fixtures from the built Run 1 example (schema r2). Stdlib only.

    python fixtures/ledger/REGENERATE.py        (run after ledger_build_run1.py has rebuilt examples/)

valid-*.json must validate; each invalid-*.json carries "_expect", a substring the validator must report.
"""
import copy
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LANE = os.path.dirname(os.path.dirname(HERE))


def dump(name, rec):
    with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
        f.write("\n")


def main():
    for n in os.listdir(HERE):
        if n.endswith(".json"):
            os.remove(os.path.join(HERE, n))
    src = json.load(open(os.path.join(LANE, "examples", "run1-do-h100.ledger.json"), encoding="utf-8"))
    v = copy.deepcopy(src)
    v["receipts"]["items"] = v["receipts"]["items"][:3]
    v["_fixture"] = "trimmed copy of examples/run1-do-h100.ledger.json (schema r2)"
    dump("valid-run1-do-h100.json", v)

    # a fully populated estate record: frozen evaluator, release known, energy cost, traversals measured
    e = copy.deepcopy(v)
    e["identity"].update({"run_id": "fixture/estate-w01-3090", "arm": "estate", "tier": None, "knot_id": "knot-fixture", "seat_id": "estate-w01-3090",
                          "provider": "estate", "region": "OCTO-W01", "sku": "rtx-3090-24gb", "host": "OCTO-W01"})
    e["identity"]["null_reasons"] = {"tier": "estate arm has no tuning tiers"}
    e["clocks"].update({"t_request": "2026-09-29T10:00:00Z", "t_ssh": "2026-09-29T10:00:05Z", "t_ready": "2026-09-29T10:03:00Z",
                        "t_work_start": "2026-09-29T10:04:00Z", "t_work_end": "2026-09-29T11:04:00Z", "t_released": "2026-09-29T11:05:00Z"})
    e["clocks"]["null_reasons"] = {}
    e["acquisition"] = {"attempts": [{"ts": "2026-09-29T10:00:00Z", "provider": "estate", "region": "OCTO-W01", "sku": "rtx-3090-24gb", "layer": "delivered",
                                      "method": "tui-provision", "outcome": "available", "provisioned": True, "attempt_id": "fixture-lease-1"}],
                        "n_attempts": 1, "n_allocations": 1, "yield": 1.0}
    e["work"].update({"unit": "task", "evaluator": {"name": "evalplus-humaneval-plus", "frozen": True, "ref": "evalplus-0.3.1-human-v0.1.10 sidecar sha256:fixture"},
                      "attempted": 164, "completed": 160, "correct": 120, "accepted": 118, "lost": 4, "restarts": 0, "cells": None, "task_classes": None})
    e["work"]["acceptance_rule"]["correctness"] = True
    e["work"]["null_reasons"] = {"cells": "task run, no cells", "task_classes": "single class in this fixture"}
    e["sustained"].update({"window_s": 3600.0, "meets_required_window": True, "interrupted": False,
                           "buckets": [{"index": i, "start_s": i * 300, "accepted": 10 if i < 11 else 8} for i in range(12)],   # sums to 118 = accepted
                           "min_accepted_per_bucket": 8, "median_accepted_per_bucket": 10, "last_q_over_first_q": 28 / 30})
    e["sustained"].pop("null_reasons", None)
    e["traversal"] = {"path": "split-vram-ram", "footprint_bytes": 33745206528, "footprint_bytes_basis": "llama.cpp load log: CUDA0 + CPU model buffer bytes (allocated)",
                      "bytes_per_traversal": None, "bytes_per_traversal_basis": None, "traversals": 49200, "traversals_basis": "llama-server n_decode_total delta",
                      "seconds_per_traversal": 0.0732, "seconds_per_traversal_basis": "decode wall / n_decode",
                      "accepted_closures_per_traversal": 118 / 49200, "accepted_closures_per_traversal_basis": "accepted / traversals", "by_depth": None,
                      "null_reasons": {"by_depth": "single depth in this fixture", "bytes_per_traversal": "MoE active bytes unmeasured; footprint is not a substitute",
                                       "bytes_per_traversal_basis": "see bytes_per_traversal"}}
    money_nulls = ["list_rate_per_gpu_hr", "modeled_minutes", "modeled_minutes_basis", "modeled_usd", "modeled_lower_bound_minutes", "modeled_lower_bound_usd",
                   "modeled_lower_bound_basis", "billed_usd", "billed_ref", "credits_usd"]
    e["money"] = {"currency": "USD", "billing": "owned-energy-only", "payer": "self",
                  "energy": {"watts_mean": 310.0, "kwh": 0.3358, "tariff_usd_per_kwh": 0.30, "usd": 0.10074, "meter": "fixture-plug-meter"},
                  "null_reasons": {k: "owned seat: energy only" for k in money_nulls}}
    for k in money_nulls:
        e["money"][k] = None
    e["derived"] = {"usd_per_accepted": 0.10074 / 118, "usd_per_1k_accepted": 0.10074 / 118 * 1000, "cost_basis": "energy",
                    "wall_s_per_accepted": 3900 / 118, "work_s_per_accepted": 3600 / 118, "accepted_per_work_s": 118 / 3600}
    e["notes"] = ["fixture: hypothetical fully-populated estate record; not a measurement"]
    dump("valid-estate-full.json", e)

    def bad(name, expect, mut, base=v):
        b = copy.deepcopy(base)
        mut(b)
        b["_expect"] = expect
        dump(f"invalid-{name}.json", b)

    bad("null-without-reason", "null without a reason", lambda b: b["clocks"]["null_reasons"].pop("t_released"))
    bad("clock-order", "is earlier than", lambda b: b["clocks"].update({"t_work_end": "2026-09-23T17:00:00Z"}))
    bad("accepted-gt-completed", "accepted", lambda b: b["work"].update({"accepted": b["work"]["completed"] + 5}))
    bad("yield-mismatch", "yield", lambda b: b["acquisition"].update({"yield": 0.5}))
    bad("listing-as-attempt", "is not one of", lambda b: b["acquisition"]["attempts"][0].update({"method": "console-plan-list"}))
    bad("create-attempt-method", "renamed", lambda b: b["acquisition"]["attempts"][0].update({"method": "create-attempt"}))
    bad("listed-layer-attempt", "layer must be", lambda b: b["acquisition"]["attempts"][0].update({"layer": "listed"}))
    bad("lower-bound-wrong", "modeled_lower_bound_usd", lambda b: b["money"].update({"modeled_lower_bound_usd": 99.0}))

    def modeled_without_release(b):
        b["money"].update({"modeled_usd": 2.0, "modeled_minutes": 30.0})
        b["money"]["null_reasons"].pop("modeled_usd"); b["money"]["null_reasons"].pop("modeled_minutes")
    bad("modeled-without-release", "not both known", modeled_without_release)
    bad("derived-mismatch", "usd_per_accepted", lambda b: b["derived"].update({"usd_per_accepted": 0.5}))

    def wall_from_work(b):
        b["derived"].update({"wall_s_per_accepted": 0.394}); b["derived"]["null_reasons"].pop("wall_s_per_accepted")
    bad("wall-from-work-time", "wall_s_per_accepted", wall_from_work)
    bad("bad-sha", "sha256", lambda b: b["receipts"]["items"][0].update({"sha256": "nothex"}))
    bad("missing-group", "missing group", lambda b: b.pop("traversal"))
    bad("bad-enum", "not in", lambda b: b["traversal"].update({"path": "teleport"}))
    bad("sustained-flag", "meets_required_window", lambda b: b["sustained"].update({"meets_required_window": True}))

    def correct_without_evaluator(b):
        b["work"].update({"correct": 2400}); b["work"]["null_reasons"].pop("correct")
    bad("correct-without-evaluator", "no evaluator", correct_without_evaluator)
    bad("evaluator-not-frozen", "frozen", lambda b: b["work"]["evaluator"].update({"frozen": False}), base=e)
    bad("evaluator-no-ref", "ref must name", lambda b: b["work"]["evaluator"].update({"ref": ""}), base=e)
    bad("closures-ratio", "accepted_closures_per_traversal", lambda b: b["traversal"].update({"accepted_closures_per_traversal": 999}), base=e)

    def footprint_as_traversed(b):
        b["traversal"].update({"bytes_per_traversal": 33745206528, "bytes_per_traversal_basis": "model buffer bytes"})
        b["traversal"]["null_reasons"].pop("bytes_per_traversal"); b["traversal"]["null_reasons"].pop("bytes_per_traversal_basis")
    bad("footprint-as-traversed", "footprint is not traversed", footprint_as_traversed, base=e)

    def ungraded_sustained(b):
        b["work"].update({"accepted": None, "correct": None}); b["work"]["null_reasons"].update({"accepted": "x", "correct": "x"})
        keys = ("usd_per_accepted", "usd_per_1k_accepted", "wall_s_per_accepted", "work_s_per_accepted", "accepted_per_work_s")
        b["derived"].update({k: None for k in keys}); b["derived"]["null_reasons"] = {k: "x" for k in keys}
        b["traversal"].update({"accepted_closures_per_traversal": None}); b["traversal"]["null_reasons"].update({"accepted_closures_per_traversal": "x"})
    bad("ungraded-sustained", "ungraded window", ungraded_sustained, base=e)
    bad("reason-for-nonnull", "reason given but field is not null", lambda b: b["clocks"]["null_reasons"].update({"t_ready": "x"}))
    print(len([n for n in os.listdir(HERE) if n.endswith(".json")]), "fixtures written")


if __name__ == "__main__":
    main()
