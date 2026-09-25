#!/usr/bin/env python3
"""TIER WATERLINE: model tier before seat. Stdlib only. Imports ../ledger/waterline.py (never edits it).

    python tier_waterline.py plan <knot.json> --evidence DIR [--seats seats.json] [--availability observations.jsonl]
                                              [--local-models local_models.json] [--start-at 2026-09-29T10:00:00Z] [--json out.json]
    python tier_waterline.py --selftest

Two axes. Tier-Bench answers "which model tier is the cheapest that is SUFFICIENT for this task class" (K/K decisive passes
at the cheapest rung; docs/residue-broker.md). The fabric ledger answers "which seat runs that tier fastest / cheapest / most
efficiently" (../ledger/waterline.py). This module joins them for one Knot:

  1. knot.tierbench.task_classes (or the default map for knot.task_class) names the Tier-Bench classes whose receipts count.
  2. From DIR/tierbench-summary.json (import_tierbench.py output) every model tier gets a class verdict: sufficient on every
     measured task (with coverage = measured tasks / class tasks), unstable, wall, or unmeasured.
  3. The cheapest sufficient tier by DIR/tier-ladder.json rank is chosen. Ties and partial coverage are written down.
  4. Seat side:
       api / subscription tiers  -> a ZERO-SEAT plan: provider cost = count x recorded cost per trial (basis carried),
                                    wall = count x median latency / concurrency (declared), grader seats from seats.json.
       local / open-weight tiers -> the Knot's model (or local_models.json's spec for that tier) goes through the fabric
                                    WATERLINE: fastest / cheapest / most-efficient seat plans with their assumptions.
  5. The Knot's own open-weight tier (knot.tierbench.open_weight_tier) is always planned on the fabric so the grid row exists,
     and its tier verdict is written honestly (usually UNMEASURED until Run 3 produces receipts).

Every missing piece of evidence is a written reason, never a default. Exit 0 = a tier was chosen; 2 = no sufficient tier
(fabric plans may still be listed for unmeasured tiers); 1 = error.
"""
import json
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAMPAIGN = os.path.dirname(HERE)
LEDGER = os.path.join(CAMPAIGN, "ledger")
sys.path.insert(0, LEDGER)
import waterline as fabric  # noqa: E402  (lane B's planner, imported, not edited)
from ledger_common import load_jsonl, parse_iso  # noqa: E402

DEFAULT_SEATS = os.path.join(LEDGER, "seats.json")
DEFAULT_AVAIL = os.path.join(CAMPAIGN, "availability", "observations.jsonl")
DEFAULT_LOCAL_MODELS = os.path.join(HERE, "local_models.json")
DEFAULT_CLASS_MAP = {
    "graded-coding": (["tierbench-T1"], "default map: EvalPlus implement-from-docstring is the shape of Tier-Bench t1_*; an analogy, not a measured equivalence (RUN3-GRID.md)"),
}


# ---------------------------------------------------------------- tier verdicts
def class_verdicts(summary, classes):
    """For every model tier seen in the named classes: status across tasks, coverage, cost/trial, pass rate, latency."""
    tiers = {}
    missing = []
    for c in classes:
        cs = (summary.get("classes") or {}).get(c)
        if not cs:
            missing.append(f"no Tier-Bench receipts for class '{c}' in the evidence (classes present: {sorted((summary.get('classes') or {}).keys())})")
            continue
        if cs.get("aggregate"):
            for tier, v in cs["tiers"].items():
                t = tiers.setdefault(tier, {"tier": tier, "classes": {}, "statuses": [], "costs": [], "cost_bases": [], "pass_rates": [], "latencies": [], "measured_tasks": 0, "class_tasks": 0})
                t["classes"][c] = {"status": v["status"], "measured_tasks": cs["n_tasks"], "class_tasks": cs["n_tasks"], "aggregate": True}
                t["statuses"].append(v["status"]); t["measured_tasks"] += cs["n_tasks"]; t["class_tasks"] += cs["n_tasks"]
                if v.get("cost_per_trial_usd") is not None:
                    t["costs"].append(v["cost_per_trial_usd"]); t["cost_bases"].append(v.get("cost_per_trial_basis"))
                t["pass_rates"].append(v.get("pass_rate"))
            continue
        n_tasks = cs.get("n_tasks") or len(cs.get("tasks") or {})
        seen = {}
        for task_id, te in (cs.get("tasks") or {}).items():
            for tier, v in te["tiers"].items():
                s = seen.setdefault(tier, {"statuses": [], "costs": [], "bases": [], "prs": [], "lats": [], "tasks": 0})
                s["tasks"] += 1; s["statuses"].append(v["status"])
                if v.get("cost_per_trial_usd") is not None:
                    s["costs"].append(v["cost_per_trial_usd"]); s["bases"].append(v.get("cost_per_trial_basis"))
                if v.get("pass_rate") is not None:
                    s["prs"].append(v["pass_rate"])
                if v.get("latency_ms_median") is not None:
                    s["lats"].append(v["latency_ms_median"])
        for tier, s in seen.items():
            if "wall" in s["statuses"]:
                status = "wall"
            elif "unstable" in s["statuses"]:
                status = "unstable"
            elif all(x == "sufficient" for x in s["statuses"]):
                status = "sufficient"
            elif "sufficient" in s["statuses"]:
                status = "partly-sufficient"   # sufficient on some tasks, < K on others
            else:
                status = "insufficient-evidence"
            t = tiers.setdefault(tier, {"tier": tier, "classes": {}, "statuses": [], "costs": [], "cost_bases": [], "pass_rates": [], "latencies": [], "measured_tasks": 0, "class_tasks": 0})
            t["classes"][c] = {"status": status, "measured_tasks": s["tasks"], "class_tasks": n_tasks}
            t["statuses"].append(status); t["measured_tasks"] += s["tasks"]; t["class_tasks"] += n_tasks
            t["costs"] += s["costs"]; t["cost_bases"] += s["bases"]; t["pass_rates"] += s["prs"]; t["latencies"] += s["lats"]
    for t in tiers.values():
        st = t["statuses"]
        t["status"] = "wall" if "wall" in st else ("unstable" if "unstable" in st else ("sufficient" if all(x == "sufficient" for x in st) else ("partly-sufficient" if "sufficient" in st else "insufficient-evidence")))
        t["coverage"] = round(t["measured_tasks"] / t["class_tasks"], 3) if t["class_tasks"] else None
        t["covers_all_classes"] = all(c in t["classes"] for c in classes)
        t["cost_per_trial_usd"] = round(statistics.mean(t["costs"]), 6) if t["costs"] else None
        t["cost_per_trial_basis"] = ("; ".join(sorted(set(b for b in t["cost_bases"] if b))) or "no basis") if t["costs"] else "no non-zero cost at this tier (shadow/unbilled rows or no rows)"
        t["pass_rate"] = round(statistics.mean([p for p in t["pass_rates"] if p is not None]), 4) if any(p is not None for p in t["pass_rates"]) else None
        t["latency_ms_median"] = round(statistics.median(t["latencies"]), 1) if t["latencies"] else None
        for k in ("statuses", "costs", "cost_bases", "pass_rates", "latencies"):
            del t[k]
    return tiers, missing


def choose_tier(verdicts, ladder, classes):
    """Cheapest (ladder rank) tier that is sufficient in EVERY named class with full coverage; else the best partial, written."""
    def rank(t):
        r = (ladder["tiers"].get(t) or {}).get("rank")
        return r if r is not None else 1e9
    full = [t for t, v in verdicts.items() if v["status"] == "sufficient" and v["covers_all_classes"]
            and v["class_tasks"] > 0 and v["measured_tasks"] == v["class_tasks"]]
    partial = [t for t, v in verdicts.items() if v["status"] in ("sufficient", "partly-sufficient") and t not in full]
    reasons = []
    if full:
        full.sort(key=rank)
        chosen = full[0]
        reasons.append(f"{chosen}: sufficient (K/K decisive) on every measured task of {classes}, full coverage; cheapest such tier on the ladder (rank {rank(chosen)})")
        if len(full) > 1:
            reasons.append(f"also sufficient, dearer: {full[1:]}")
        return chosen, "full", reasons
    if partial:
        partial.sort(key=lambda t: (-(verdicts[t]["coverage"] or 0), rank(t)))
        chosen = partial[0]
        v = verdicts[chosen]
        reasons.append(f"NO tier is sufficient with full coverage. Best partial: {chosen} ({v['status']}, coverage {v['coverage']}, classes {v['classes']}); collect the missing K trials before relying on it")
        return chosen, "partial", reasons
    for t, v in sorted(verdicts.items(), key=lambda kv: rank(kv[0])):
        reasons.append(f"{t}: {v['status']} on {v['classes']}")
    reasons.append("no tier reached K/K on the named classes; the next allowed action is more trials at the cheapest rung (residue-broker: never escalate before 0/K)" if verdicts else "no receipts at all for the named classes")
    return None, "none", reasons


# ---------------------------------------------------------------- seat plans
def api_plan(knot, tier, verdict, ladder, seats):
    def usable_rate(rate):
        try:
            return type(rate) in (int, float) and math.isfinite(rate) and rate >= 0
        except OverflowError:
            return False
    lt = ladder["tiers"].get(tier) or {}
    count = knot["count"]
    conc = ((knot.get("policy") or {}).get("api_concurrency")) or 1
    cost = usd_basis = None
    if verdict.get("cost_per_trial_usd") is not None:
        cost = round(verdict["cost_per_trial_usd"] * count, 4)
        usd_basis = f"{count} x recorded cost/trial ${verdict['cost_per_trial_usd']} ({verdict['cost_per_trial_basis']}); Tier-Bench trials, not this Knot's prompts"
    elif all(usable_rate(lt.get(key)) for key in ("price_in_per_1M", "price_out_per_1M")):
        per = (knot.get("tokens_in_per_closure", 400) * lt["price_in_per_1M"] + knot.get("tokens_out_per_closure", 300) * lt["price_out_per_1M"]) / 1e6
        cost = round(per * count, 4)
        usd_basis = f"LIST PROXY: {count} x ({knot.get('tokens_in_per_closure', 400)} in + {knot.get('tokens_out_per_closure', 300)} out tokens) at {lt.get('price_source')}; no recorded cost/trial at this tier"
    else:
        usd_basis = "tier lacks usable input/output list prices and has no recorded cost: cost unestimated"
    lat = verdict.get("latency_ms_median")
    wall = round(count * lat / 1000.0 / conc, 1) if lat else None
    wall_basis = (f"{count} x median Tier-Bench trial latency {lat} ms / concurrency {conc} (declared, not measured for this provider under load)" if lat
                  else "no latency in the receipts at this tier; wall unestimated")
    deadline = knot["deadline_s"]
    need_conc = math.ceil(count * lat / 1000.0 / deadline) if lat else None
    graders = fabric.grader_seats(seats, knot)
    plan = {"kind": "zero-seat", "tier": tier, "seat_kind": lt.get("seat_kind"), "provider": lt.get("provider"),
            "usd": cost, "cost_basis": usd_basis, "wall_s": wall, "wall_basis": wall_basis, "concurrency": conc,
            "concurrency_needed_for_deadline": need_conc, "deadline_s": deadline, "deadline_margin_s": round(deadline - wall, 1) if wall is not None else None,
            "expected_accepted": round(count * verdict["pass_rate"], 1) if verdict.get("pass_rate") is not None else None,
            "accept_basis": f"Tier-Bench pass rate {verdict.get('pass_rate')} at this tier on the named classes" if verdict.get("pass_rate") is not None else "no pass rate",
            "seat_id": None, "seat_reason": "API / subscription tier: no fabric seat is consumed for inference; the seat cost is $0 and the provider bill is the cost",
            "grader_seats": graders, "grader_note": "grading still needs a fabric seat with the grader role (evaluator.needs_seat_role)" if (knot.get("evaluator") or {}).get("needs_seat_role") else None,
            "assumptions": [a for a in [
                "recorded cost/trial is from Tier-Bench receipts on other prompts, not this Knot's" if verdict.get("cost_per_trial_usd") is not None else None,
                "latency is a Tier-Bench trial median, not a provider SLA" if lat else None,
                f"concurrency {conc} declared; provider rate limits not modeled",
                "subscription tiers (Codex) are list-priced for comparison; the plan's marginal cost is the subscription window" if lt.get("seat_kind") == "subscription" else None,
            ] if a]}
    if wall is not None and wall > deadline:
        plan["deadline_note"] = f"exceeds the deadline at concurrency {conc}; needs >= {need_conc} concurrent requests"
    return plan


def fabric_plan(knot, tier, model_spec, seats, obs, start_at, kwh_usd):
    k = json.loads(json.dumps(knot))
    if model_spec != "self":
        k["model"] = model_spec
    k["knot_id"] = f"{knot['knot_id']}::{tier}"
    p = fabric.plan(k, seats, obs, start_at=start_at, kwh_usd=kwh_usd)
    p["kind"] = "fabric"; p["tier"] = tier; p["model_id"] = k["model"]["id"]
    return p


# ---------------------------------------------------------------- plan
def plan(knot, evidence_dir, seats, obs, local_models, start_at=None, kwh_usd=None):
    summary = json.load(open(os.path.join(evidence_dir, "tierbench-summary.json"), encoding="utf-8"))
    ladder = json.load(open(os.path.join(evidence_dir, "tier-ladder.json"), encoding="utf-8"))
    tb = knot.get("tierbench") or {}
    reasons = []
    classes = tb.get("task_classes")
    class_basis = tb.get("basis")
    if not classes:
        m = DEFAULT_CLASS_MAP.get(knot.get("task_class"))
        if m:
            classes, class_basis = m
        else:
            classes, class_basis = [], None
            reasons.append(f"Knot task_class '{knot.get('task_class')}' has no tierbench.task_classes and no default map; tier sufficiency cannot be judged")
    verdicts, missing = class_verdicts(summary, classes) if classes else ({}, [])
    reasons += missing
    chosen, mode, why = choose_tier(verdicts, ladder, classes) if classes else (None, "none", [])
    reasons += why
    start_at = start_at or (parse_iso(knot["start_at"]) if knot.get("start_at") else None)
    kwh_usd = kwh_usd if kwh_usd is not None else (knot.get("policy") or {}).get("kwh_usd")
    out = {"schema": "second-run/tier-waterline-plan@1", "knot_id": knot["knot_id"], "task_class": knot.get("task_class"),
           "tierbench_classes": classes, "class_basis": class_basis, "evidence_dir": evidence_dir.replace("\\", "/"),
           "evidence_inputs": summary.get("inputs"), "k": summary.get("k"),
           "chosen_tier": chosen, "chosen_mode": mode, "verdicts": verdicts, "reasons": reasons, "plans": {}, "grid": [], "refused": chosen is None}
    # seat plans: for the chosen tier, every sufficient tier, and the Knot's own open-weight tier
    grid_tiers = []
    for t, v in sorted(verdicts.items(), key=lambda kv: ((ladder["tiers"].get(kv[0]) or {}).get("rank") if (ladder["tiers"].get(kv[0]) or {}).get("rank") is not None else 1e9)):
        grid_tiers.append(t)
    ow = tb.get("open_weight_tier")
    if ow and ow not in grid_tiers:
        grid_tiers.append(ow)
    for t in grid_tiers:
        v = verdicts.get(t) or {"status": "unmeasured", "classes": {}, "coverage": None, "cost_per_trial_usd": None, "pass_rate": None, "latency_ms_median": None}
        lt = ladder["tiers"].get(t) or {}
        kind = lt.get("seat_kind")
        row = {"tier": t, "tier_status": v["status"], "coverage": v.get("coverage"), "seat_kind": kind, "ladder_rank": lt.get("rank")}
        if v["status"] == "unmeasured":
            row["tier_reason"] = f"no Tier-Bench receipts for {t} on classes {classes}: the seat plan below is a SEAT plan only; sufficiency is UNMEASURED"
        lm = (local_models.get("tiers") or {}).get(t)
        if kind in ("api", "subscription"):
            row["plan"] = api_plan(knot, t, v, ladder, seats)
        elif lm or kind == "local" or t == ow:
            if lm:
                spec = lm["model"]
                row["local_model_note"] = lm.get("evidence_note")
                row["resource_key"] = lm.get("resource_key")
                if spec == "self":
                    spec = "self"
                row["plan"] = fabric_plan(knot, t, spec, seats, obs, start_at, kwh_usd)
            elif t == ow:
                row["plan"] = fabric_plan(knot, t, "self", seats, obs, start_at, kwh_usd)
            else:
                row["plan"] = None
                row["plan_reason"] = f"{t} is a local tier with no entry in local_models.json: the fabric planner needs a model spec (class, formats, bytes, recipes)"
        else:
            row["plan"] = None
            row["plan_reason"] = f"{t}: seat kind unknown (unpriced / unregistered tier); neither a zero-seat nor a fabric plan can be built"
        out["grid"].append(row)
    if chosen:
        out["plans"]["chosen"] = next(r for r in out["grid"] if r["tier"] == chosen)
    if ow:
        out["plans"]["open_weight"] = next(r for r in out["grid"] if r["tier"] == ow)
    return out


# ---------------------------------------------------------------- render
def _fmt_usd(u):
    return f"${u:.2f}" if isinstance(u, (int, float)) else "unestimated"


def render(p):
    L = [f"TIER WATERLINE for {p['knot_id']}  (task class {p['task_class']} -> Tier-Bench {p['tierbench_classes']})"]
    if p.get("class_basis"):
        L.append(f"  class basis: {p['class_basis']}")
    L.append("")
    L.append("Tier verdicts (cheapest first):")
    for row in p["grid"]:
        v = p["verdicts"].get(row["tier"]) or {}
        L.append(f"  - {row['tier']} [{row['seat_kind'] or '?'}] {row['tier_status']}" + (f", coverage {row['coverage']}" if row.get("coverage") is not None else "") +
                 (f", cost/trial ${v['cost_per_trial_usd']}" if v.get("cost_per_trial_usd") is not None else "") + (f", pass {v['pass_rate']}" if v.get("pass_rate") is not None else ""))
        if row.get("tier_reason"):
            L.append(f"      {row['tier_reason']}")
    L.append("")
    L.append(("CHOSEN: " + p["chosen_tier"] + f" ({p['chosen_mode']} coverage)") if p["chosen_tier"] else "NO TIER CHOSEN")
    for r in p["reasons"]:
        L.append(f"  - {r}")
    for name in ("chosen", "open_weight"):
        row = p["plans"].get(name)
        if not row:
            continue
        pl = row.get("plan")
        L.append("")
        L.append(f"{name.upper()} tier {row['tier']} ({row['tier_status']}):")
        if pl is None:
            L.append(f"  no plan: {row.get('plan_reason')}"); continue
        if pl["kind"] == "zero-seat":
            L.append(f"  zero-seat plan: cost {_fmt_usd(pl['usd'])} ({pl['cost_basis']})")
            L.append(f"  wall {fabric.fmt_s(pl['wall_s'])} ({pl['wall_basis']})" + (f"; {pl['deadline_note']}" if pl.get("deadline_note") else ""))
            L.append(f"  expected accepted {pl['expected_accepted']} ({pl['accept_basis']}); grader seats {pl['grader_seats'] or 'NONE'}")
            L.append(f"  assumptions: {'; '.join(pl['assumptions'])}")
        else:
            L.append("  fabric plan (../ledger/waterline.py):")
            for line in fabric.render(pl).splitlines():
                L.append("    " + line)
    return "\n".join(L)


# ---------------------------------------------------------------- self-test
def selftest():
    import subprocess
    import tempfile
    ok = True
    def check(cond, msg):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {msg}")
        ok = ok and cond
    seats = json.load(open(DEFAULT_SEATS, encoding="utf-8"))["seats"]
    obs = load_jsonl(os.path.join(LEDGER, "fixtures", "availability-2026-09-23.jsonl"))
    local_models = json.load(open(DEFAULT_LOCAL_MODELS, encoding="utf-8"))
    knot = json.load(open(os.path.join(HERE, "fixtures", "knots", "knot-run3-evalplus-tierbench.json"), encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="tier-waterline-") as td:
        r = subprocess.run([sys.executable, "-B", os.path.join(HERE, "import_tierbench.py"), "--fixtures", "--out", td], capture_output=True, text=True)
        check(r.returncode == 0, "evidence built from fixtures by import_tierbench.py")
        # 1. Run 3 Knot on 09-24: T1 evidence -> haiku@harness; open-weight tier unmeasured but fabric-planned
        p = plan(knot, td, seats, obs, local_models)
        check(p["chosen_tier"] == "claude-haiku-4-5@harness" and p["chosen_mode"] == "full", f"graded-coding -> tierbench-T1: cheapest sufficient tier is haiku@harness ({p['chosen_tier']}, {p['chosen_mode']})")
        ch = p["plans"]["chosen"]["plan"]
        check(ch["kind"] == "zero-seat" and ch["seat_id"] is None and ch["usd"] is not None and "shadow" in ch["cost_basis"], f"chosen plan is zero-seat, cost {_fmt_usd(ch['usd'])} carried as shadow-estimated")
        check("recorded cost/trial" in ch["cost_basis"] and "measured cost/trial" not in ch["cost_basis"] and "shadow-estimated" in ch["cost_basis"], "historical shadow cost is labeled recorded, never measured; its evidence basis is retained")
        check(ch["wall_s"] > knot["deadline_s"] and ch["concurrency_needed_for_deadline"] >= 2 and "deadline_note" in ch, f"serial API wall {fabric.fmt_s(ch['wall_s'])} exceeds the deadline; concurrency {ch['concurrency_needed_for_deadline']} needed, written")
        check("estate-w01-cpu" in ch["grader_seats"], "zero-seat plan still names grader seats")
        ow = p["plans"]["open_weight"]
        check(ow["tier_status"] == "unmeasured" and "UNMEASURED" in ow["tier_reason"], "open-weight 30B tier: sufficiency UNMEASURED with a written reason")
        fp = ow["plan"]
        check(fp["kind"] == "fabric" and not fp["refused"] and fp["plans"]["cheapest"]["seat_id"] == "hotaisle-mi300x-1x-enc1", f"30B fabric plan via ../ledger/waterline.py: cheapest {fp['plans']['cheapest']['seat_id']} ${fp['plans']['cheapest']['usd']}")
        grid_tiers = [row["tier"] for row in p["grid"]]
        check(set(grid_tiers) == set(p["verdicts"]) | {knot["tierbench"]["open_weight_tier"]} and grid_tiers[-1] == knot["tierbench"]["open_weight_tier"], f"grid: every verdict tier plus the open-weight tier, cheapest first ({grid_tiers})")
        check(p["evidence_inputs"]["ledger"]["git_commit"] == "da9b0a9cd1df25070e3763a1b6d1835d5b0f71e3", "plan carries the evidence provenance (ledger.jsonl commit)")
        # 2. unknown task class -> no tier, reasons, fabric plan still produced for the open-weight tier
        k2 = json.loads(json.dumps(knot)); k2["task_class"] = "video-upscale"; del k2["tierbench"]["task_classes"]
        p2 = plan(k2, td, seats, obs, local_models)
        check(p2["refused"] and any("no default map" in r for r in p2["reasons"]) and p2["plans"]["open_weight"]["plan"]["kind"] == "fabric", "unknown task class: refused with reason; open-weight fabric plan still listed")
        # 3. residue class: floor unstable -> sonnet@low
        k3 = json.loads(json.dumps(knot)); k3["tierbench"]["task_classes"] = ["breadth-task02-wildcard"]
        p3 = plan(k3, td, seats, obs, local_models)
        v = p3["verdicts"]
        check(v["claude-haiku-4-5@harness"]["status"] in ("unstable", "wall") and p3["chosen_tier"] == "claude-sonnet-5@low" and p3["chosen_mode"] == "partial", f"task02 class: haiku {v['claude-haiku-4-5@harness']['status']}; sonnet@low chosen with PARTIAL coverage ({v['claude-sonnet-5@low']['coverage']}) and it says so")
        check(any("NO tier is sufficient with full coverage" in r for r in p3["reasons"]), "partial coverage written as a reason")
        # 4. pooled classes T0+T1 -> haiku, fable@low dearer
        k4 = json.loads(json.dumps(knot)); k4["tierbench"]["task_classes"] = ["tierbench-T0", "tierbench-T1"]
        p4 = plan(k4, td, seats, obs, local_models)
        check(p4["chosen_tier"] == "claude-haiku-4-5@harness" and p4["verdicts"]["claude-fable-5@low"]["covers_all_classes"] is False, "pooled T0+T1: haiku covers both; fable@low measured on T0 only, not chosen")
        # 5. missing class named
        k5 = json.loads(json.dumps(knot)); k5["tierbench"]["task_classes"] = ["tierbench-T9"]
        p5 = plan(k5, td, seats, obs, local_models)
        check(p5["refused"] and any("no Tier-Bench receipts for class 'tierbench-T9'" in r for r in p5["reasons"]), "missing class: written reason naming the classes present")
        # 6. local tier through the fabric after 09-28: qwen 9B plan exists, unmeasured, with the routing-evidence note
        k6 = json.loads(json.dumps(knot)); k6["tierbench"]["open_weight_tier"] = "qwen3.5:9b-q4_K_M@none"
        p6 = plan(k6, td, seats, obs, local_models, start_at=parse_iso("2026-09-29T10:00:00Z"))
        row = p6["plans"]["open_weight"]
        check(row["plan"]["kind"] == "fabric" and row["plan"]["model_id"] == "Qwen/Qwen3.5-9B" and "estate-w01-3090" in row["plan"]["feasible_seats"] and "SyntaxError" in row["local_model_note"], f"qwen 9B local tier: fabric plan on the estate 3090 ({row['plan']['feasible_seats']}), routing-evidence caveat carried")
        check(row["plan"]["plans_measured"] is False, "qwen 9B plan rests on borrowed/assumed curves -> marked unmeasured by the fabric planner")
        # 7. a local tier in the evidence (router-structured: qwen3.5:9b) with no registry entry -> no plan, written reason
        k7 = json.loads(json.dumps(knot)); k7["tierbench"]["task_classes"] = ["router-structured"]
        p7 = plan(k7, td, seats, obs, {"tiers": {}})
        q = next(r for r in p7["grid"] if r["tier"] == "qwen3.5:9b-q4_K_M@none")
        check(q["seat_kind"] == "local" and q["plan"] is None and "local_models.json" in q["plan_reason"], "local tier without a registry entry: no plan, written reason")
        check(p7["refused"] and q["tier_status"] == "insufficient-evidence", "router-structured: one synthetic pass < K -> insufficient-evidence, no tier chosen")
        # 8. render does not crash and names the chosen tier
        txt = render(p)
        check("CHOSEN: claude-haiku-4-5@harness" in txt and "OPEN_WEIGHT tier" in txt and "WATERLINE plan for" in txt, "render: chosen tier, open-weight row and the embedded fabric plan")
        # 9. Rounded display coverage must not turn a missing task into full coverage.
        sparse = {"classes": {"boundary": {"n_tasks": 2001, "tasks": {
            str(i): {"tiers": {"candidate": {"status": "sufficient"}}} for i in range(2000)}}}}
        boundary_ladder = {"tiers": {"candidate": {"rank": 0}}}
        verdicts, _ = class_verdicts(sparse, ["boundary"])
        chosen, mode, _ = choose_tier(verdicts, boundary_ladder, ["boundary"])
        check(verdicts["candidate"]["coverage"] == 1.0 and mode == "partial", "2000/2001 tasks may display 1.0 coverage but remain partial")
        sparse["classes"]["boundary"]["tasks"]["2000"] = {"tiers": {"candidate": {"status": "sufficient"}}}
        verdicts, _ = class_verdicts(sparse, ["boundary"])
        chosen, mode, _ = choose_tier(verdicts, boundary_ladder, ["boundary"])
        check(chosen == "candidate" and mode == "full", "the final measured task, not display rounding, completes full coverage")
        # 10. A partial or unusable list price is unknown; zero is a usable rate.
        unknown_cost = {"cost_per_trial_usd": None, "latency_ms_median": None, "pass_rate": None}
        bad_rates = (None, True, -1, "1", float("nan"), float("inf"))
        null_prices = []
        for bad in bad_rates:
            for prices in ((1, bad), (bad, 1)):
                prices_ladder = {"tiers": {"candidate": {"price_in_per_1M": prices[0], "price_out_per_1M": prices[1]}}}
                pp = api_plan(knot, "candidate", unknown_cost, prices_ladder, seats)
                null_prices.append(pp["usd"] is None and "unestimated" in pp["cost_basis"])
        check(all(null_prices), "missing, boolean, negative, nonnumeric and nonfinite rates on either side leave cost unestimated")
        zero_ladder = {"tiers": {"candidate": {"price_in_per_1M": 0, "price_out_per_1M": 0}}}
        check(api_plan(knot, "candidate", unknown_cost, zero_ladder, seats)["usd"] == 0.0, "two explicit zero list rates remain a zero-cost proxy")
    print(f"tier_waterline selftest: {'all passed' if ok else 'FAILURES'}")
    return ok


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    if argv[0] == "--selftest":
        return 0 if selftest() else 1
    if argv[0] != "plan" or len(argv) < 2:
        print(__doc__); return 1
    knot_path = argv[1]
    ev = seats_path = None; avail_path, lm_path, start_at, out_json = DEFAULT_AVAIL, DEFAULT_LOCAL_MODELS, None, None
    seats_path = DEFAULT_SEATS
    i = 2
    try:
        while i < len(argv):
            if argv[i] == "--evidence": ev = argv[i + 1]; i += 2
            elif argv[i] == "--seats": seats_path = argv[i + 1]; i += 2
            elif argv[i] == "--availability": avail_path = argv[i + 1]; i += 2
            elif argv[i] == "--local-models": lm_path = argv[i + 1]; i += 2
            elif argv[i] == "--start-at": start_at = parse_iso(argv[i + 1]); i += 2
            elif argv[i] == "--json": out_json = argv[i + 1]; i += 2
            else: print(f"unknown arg {argv[i]}"); return 1
        if not ev:
            print("--evidence DIR (import_tierbench.py output) is required"); return 1
        knot = json.load(open(knot_path, encoding="utf-8"))
        seats = json.load(open(seats_path, encoding="utf-8"))["seats"]
        obs = load_jsonl(avail_path) if os.path.exists(avail_path) else []
        lm = json.load(open(lm_path, encoding="utf-8"))
        p = plan(knot, ev, seats, obs, lm, start_at=start_at)
    except (OSError, json.JSONDecodeError, KeyError, ValueError, IndexError) as e:
        print(f"input error: {type(e).__name__}: {e}"); return 1
    print(render(p))
    if out_json:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=1)
    return 2 if p["refused"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
