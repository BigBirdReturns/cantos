#!/usr/bin/env python3
"""Import the pinned Tier-Bench artifacts into the Second Run ledger vocabulary. Stdlib only. Read-only on its inputs.

    python import_tierbench.py --tierbench-root W --router-root R [--receipts DIR ...] --out DIR
    python import_tierbench.py --fixtures --out DIR          # the excerpts under fixtures/ (offline)
    python import_tierbench.py --selftest

Inputs (entry-locked; see BRIDGE.md "Provenance"):
  W/experiments/breadth/run/ledger.jsonl   Tier-Bench Call rows (ts, account, model, tier, task_id, phase, outcome, effort,
                                           input/output/cache tokens, cost_usd, latency_ms, trial, note, extra)
  W/experiments/breadth/run/map.json       per-task min_sufficient_tier as Tier-Bench computed it (cross-checked, never trusted blindly)
  W/experiments/breadth/run/waterline.json settled_floor / judgment_residue with cost_basis (real-billed | shadow-estimated)
  W/models.json                            list prices per 1M tokens (dated "Last reviewed"), tier_ceiling hypotheses
  R/references/policy.json                 route orders (structured | code | complex) and the latency lane
  R/references/race6-results.operator-diagnostic.json   cross-vendor ladder aggregates + Codex list prices per 1M
  receipts: route.py our-auto/run@1 files  one attempt per (provider, model, effort); tokens from provider usage when present

Outputs in DIR:
  tierbench-calls.jsonl     second-run/tierbench-call@1 records, one per Call row / route attempt / race6 aggregate,
                            each with provenance {path, git_commit, sha256, line}
  tierbench-summary.json    second-run/tierbench-summary@1: per task class -> per task -> per model tier evidence;
                            min sufficient tier, cost/trial, pass rates, residue list; cross-checks against map.json/waterline.json
  tier-ladder.json          second-run/tier-ladder@1: every model tier seen or priced, with seat_kind (api | subscription | local)

Rules (BRIDGE.md "Sufficiency"): K decisive receipts (pass|fail; error and partial never decide) at a tier: K/K -> sufficient;
mixed -> unstable; 0/K -> wall; fewer than K decisive -> insufficient-evidence. Min sufficient tier = the cheapest tier on
the list-price ladder whose status is sufficient. Costs are never invented: a Call row's cost_usd is carried with its basis
(real-billed | shadow-estimated | unbilled-zero); a route attempt's cost is DERIVED from list prices x provider-reported tokens.
"""
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
K_DEFAULT = 3
DECISIVE = ("pass", "fail")
EFFORT_RANK = {"harness": 0, "none": 0, "": 0, "cheap": 0, "low": 1, "medium": 2, "high": 3, "xhigh": 4, "max": 5}
NOMINAL_IN, NOMINAL_OUT = 400, 300   # tokens per closure used ONLY for the ladder's price proxy (Knot default in ../ledger/fixtures/knots)

# task_id -> task class. Tier-Bench names difficulty tiers T0..T5 in task ids (t0_..t4_); the rest are named families.
CLASS_RULES = [
    (re.compile(r"^t([0-5])_"), lambda m: f"tierbench-T{m.group(1)}"),
    (re.compile(r"^evalplus:(HumanEval|Mbpp)/"), lambda m: f"evalplus-{m.group(1).lower()}-plus"),   # RUN3-GRID.md: Run 3 rows to come
    (re.compile(r"^(task02_wildcard|replay0\d_)"), lambda m: "breadth-task02-wildcard"),
    (re.compile(r"^task\d+_"), lambda m: "breadth-numbered"),
    (re.compile(r"^almanac_"), lambda m: "arc-c-almanac"),
    (re.compile(r"^b2_grade_"), lambda m: "arc-d-b2-grade"),
]
ROUTE_KIND_CLASS = {"structured": "router-structured", "code": "router-code", "complex": "router-complex"}
RACE6_CLASS = "race6-solving-ladder"
RACE6_MODEL = {"luna": "gpt-5.6-luna", "terra": "gpt-5.6-terra", "sol": "gpt-5.6-sol", "spark": "gpt-5.3-codex-spark",
               "haiku": "claude-haiku-4-5", "opus": "claude-opus-5"}
LOCAL_PROVIDERS = ("ollama",)
SUBSCRIPTION_PROVIDERS = ("codex",)


class ImportError_(Exception):
    pass


# ---------------------------------------------------------------- provenance
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def git(root, *args):
    try:
        r = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def provenance(path, root=None, fixture_prov=None):
    """{path, sha256, git_head, git_commit (last commit touching the file), reason when no git}."""
    path = os.path.abspath(path)
    out = {"path": path.replace("\\", "/"), "sha256": sha256_file(path), "git_head": None, "git_commit": None, "git_reason": None}
    if fixture_prov:
        src = fixture_prov.get(os.path.basename(path).replace(".excerpt", ""))
        if src:
            out["fixture_of"] = src["path"].replace("\\", "/")
            out["fixture_of_sha256"] = src["sha256"]
            out["git_head"] = src.get("git_head")
            out["git_commit"] = src.get("git_last_commit")
            out["git_reason"] = src.get("git_head_reason") or ("in pin 9693cb9" if src.get("in_pin_9693cb9") else ("post-pin commit" if src.get("in_pin_9693cb9") is False else None))
            return out
        out["git_reason"] = "synthetic fixture; no source commit"
        return out
    root = root or os.path.dirname(path)
    head = git(root, "rev-parse", "HEAD")
    if head:
        rel = os.path.relpath(path, git(root, "rev-parse", "--show-toplevel") or root).replace("\\", "/")
        out["git_head"] = head
        out["git_commit"] = git(root, "log", "-1", "--format=%H", "--", rel)
        dirty = git(root, "status", "--porcelain", "--", rel)
        if dirty:
            out["git_reason"] = "file has uncommitted changes; sha256 is of the working copy"
    else:
        out["git_reason"] = "not a git repository; sha256 is the only pin"
    return out


# ---------------------------------------------------------------- ladder
def tier_string(model, effort):
    return f"{model}@{effort or 'none'}"


def build_ladder(models, race6, policy, seen_tiers):
    """Every model tier with a price or an observation. seat_kind: api (provider bill per token), subscription (Codex plan,
    list-priced for comparison), local (ollama; provider $0, the seat cost belongs to the fabric ledger)."""
    prices = {}
    for mid, m in (models.get("models") or {}).items():
        prices[mid] = {"provider": m.get("provider"), "in": m.get("input_per_1M"), "out": m.get("output_per_1M"),
                       "source": "models.json (Last reviewed 2026-07-26)", "tier_ceiling_declared": m.get("tier_ceiling")}
    r6 = (race6 or {}).get("pricing") or {}
    for short, pr in r6.items():
        if short == "cache_discount" or not isinstance(pr, list):
            continue
        mid = RACE6_MODEL.get(short, short)
        prices.setdefault(mid, {"provider": "codex", "in": pr[0], "out": pr[1], "source": "race6-results.operator-diagnostic.json pricing (per 1M, operator diagnostic)", "tier_ceiling_declared": None})
    for kind, items in ((policy or {}).get("routes") or {}).items():
        for it in items:
            prices.setdefault(it["model"], {"provider": it["provider"], "in": 0 if it["provider"] in LOCAL_PROVIDERS else None,
                                            "out": 0 if it["provider"] in LOCAL_PROVIDERS else None,
                                            "source": "policy.json route (local: provider $0)" if it["provider"] in LOCAL_PROVIDERS else "policy.json route; NO price on file",
                                            "tier_ceiling_declared": None})
    tiers = {}
    def add(tier, model, effort):
        p = prices.get(model)
        provider = (p or {}).get("provider")
        kind = "local" if provider in LOCAL_PROVIDERS else ("subscription" if provider in SUBSCRIPTION_PROVIDERS else ("api" if provider else None))
        proxy = None
        if p and p["in"] is not None and p["out"] is not None:
            proxy = (NOMINAL_IN * p["in"] + NOMINAL_OUT * p["out"]) / 1e6
        tiers[tier] = {"tier": tier, "model": model, "effort": effort, "provider": provider, "seat_kind": kind,
                       "price_in_per_1M": (p or {}).get("in"), "price_out_per_1M": (p or {}).get("out"), "price_source": (p or {}).get("source"),
                       "price_reason": None if p else "model not in models.json, race6 pricing or policy.json; unpriced",
                       "list_usd_per_nominal_closure": round(proxy, 6) if proxy is not None else None,
                       "list_proxy_basis": f"({NOMINAL_IN} in + {NOMINAL_OUT} out tokens) x list price; ordering only, not a cost estimate",
                       "tier_ceiling_declared": (p or {}).get("tier_ceiling_declared"),
                       "cache_discount": r6.get("cache_discount") if provider == "codex" else None}
    for tier, (model, effort) in seen_tiers.items():
        add(tier, model, effort)
    for kind, items in ((policy or {}).get("routes") or {}).items():
        for it in items:
            add(tier_string(it["model"], it.get("effort")), it["model"], it.get("effort"))
    for it in (policy or {}).get("latency_cloud_order") or []:
        add(tier_string(it["model"], it.get("effort")), it["model"], it.get("effort"))
    ranked = sorted(tiers.values(), key=lambda t: (t["list_usd_per_nominal_closure"] if t["list_usd_per_nominal_closure"] is not None else 1e9,
                                                   EFFORT_RANK.get((t["effort"] or "").lower(), 9), t["tier"]))
    for i, t in enumerate(ranked):
        t["rank"] = i
        t["rank_basis"] = "list price proxy ascending, then effort; unpriced tiers last"
    return {"schema": "second-run/tier-ladder@1", "nominal_closure_tokens": {"in": NOMINAL_IN, "out": NOMINAL_OUT}, "tiers": {t["tier"]: t for t in ranked}}


# ---------------------------------------------------------------- Call rows
def parse_tier(row):
    """Tier-Bench tier strings are 'model@effort' (or a bare rung name like 'cheap'). Return (tier, model, effort)."""
    t = row.get("tier") or ""
    model = row.get("model") or ""
    if "@" in t:
        m, e = t.split("@", 1)
        return t, (model or m), (row.get("effort") or e)
    return t or tier_string(model, row.get("effort")), model, (row.get("effort") or t)


def task_class_of(task_id):
    for rx, fn in CLASS_RULES:
        m = rx.match(task_id or "")
        if m:
            return fn(m)
    return f"unclassified:{(task_id or '').split('_')[0] or 'none'}"


SHADOW_RX = re.compile(r"shadow|estimate|\best\b|split est|unbilled|keyless", re.I)
BILLED_RX = re.compile(r"real[- ]billed", re.I)


def cost_basis_for(row, waterline_index):
    """Priority: waterline.json cost_basis for (task, model) > row note > zero-cost rows. Default is shadow (never 'measured'
    without a billing receipt named somewhere)."""
    key = (row.get("task_id"), row.get("model"))
    wl = waterline_index.get(key)
    note = row.get("note") or ""
    cost = float(row.get("cost_usd") or 0)
    tokens = int(row.get("input_tokens") or 0) + int(row.get("output_tokens") or 0)
    if wl:
        return wl["cost_basis"], f"waterline.json {wl['section']}.{row.get('task_id')}: cost_basis {wl['cost_basis']}"
    if BILLED_RX.search(note):
        return "real-billed", "row note says real-billed"
    if cost == 0 and tokens == 0:
        return "unbilled-zero", "row carries cost 0 and no tokens (logged blank per ledger.py: a blank is a logged blank, not a measurement)"
    if SHADOW_RX.search(note):
        return "shadow-estimated", "row note says the tokens/cost are an estimate"
    return "shadow-estimated", "no billing receipt named in the row; treated as shadow by default"


def evidence_tier(cost_basis):
    return "tierbench-measured" if cost_basis == "real-billed" else "tierbench-shadow-estimated"


def waterline_index_of(wl):
    idx = {}
    for section in ("settled_floor", "judgment_residue"):
        for task, ent in (wl.get(section) or {}).items():
            model = ent.get("cheapest_measured")
            if model and ent.get("cost_basis"):
                idx[(task, model)] = {"cost_basis": ent["cost_basis"], "section": section, "rung": ent.get("rung"), "residue_name": ent.get("residue_name"),
                                      "floor_instability": ent.get("floor_instability"), "score": ent.get("score"), "status": ent.get("status")}
    return idx


def call_records(rows, prov, waterline_index):
    out = []
    for i, r in enumerate(rows):
        tier, model, effort = parse_tier(r)
        basis, why = cost_basis_for(r, waterline_index)
        tokens_in, tokens_out = int(r.get("input_tokens") or 0), int(r.get("output_tokens") or 0)
        rec = {
            "schema": "second-run/tierbench-call@1", "kind": "tierbench-ledger-call",
            "tier": evidence_tier(basis), "tier_reason": why,
            "task_class": task_class_of(r.get("task_id")), "task_id": r.get("task_id"),
            "model_tier": tier, "model": model, "effort": effort or None, "account": r.get("account"),
            "phase": r.get("phase"), "trial": r.get("trial"), "outcome": r.get("outcome"), "decisive": r.get("outcome") in DECISIVE,
            "outcome_basis": "Tier-Bench validators/hidden grader per row extra.validators or note; the ledger row is the record, not the grader output",
            "tokens": {"input": tokens_in, "output": tokens_out, "cache_read": int(r.get("cache_read_tokens") or 0), "cache_write": int(r.get("cache_write_tokens") or 0),
                       "basis": "exact (real-billed row)" if basis == "real-billed" else ("absent" if tokens_in + tokens_out == 0 else "estimated (subagent-reported / split estimate)")},
            "cost_usd": float(r.get("cost_usd") or 0), "cost_basis": basis, "currency": "USD",
            "cost_zero_unbilled": float(r.get("cost_usd") or 0) == 0,
            "latency_ms": float(r.get("latency_ms") or 0) or None,
            "ts": r.get("ts"), "note": r.get("note"),
            "seat": {"seat_id": None, "seat_kind": "api", "reason": "Anthropic API / Claude Code session; zero-seat provider cost, no fabric seat consumed"},
            "provenance": dict(prov, line=i),
        }
        if rec["latency_ms"] is None:
            rec["null_reasons"] = {"latency_ms": "row latency_ms is 0 (not measured for this row)"}
        out.append(rec)
    return out


# ---------------------------------------------------------------- route.py receipts
USAGE_IN = ("input_tokens", "prompt_tokens")
USAGE_OUT = ("output_tokens", "completion_tokens")
USAGE_CACHED = ("cached_input_tokens", "cache_read_input_tokens", "cached_tokens")


def _pick(d, keys):
    for k in keys:
        if k in d and d[k] is not None:
            return int(d[k]), k
    return None, None


def price_tokens(ladder, model, tin, tout, tcached):
    t = None
    for cand in ladder["tiers"].values():
        if cand["model"] == model:
            t = cand; break
    if not t or t["price_in_per_1M"] is None:
        return None, f"no list price for {model} in models.json / race6 pricing; cost not derivable"
    disc = t.get("cache_discount")
    cached = tcached or 0
    uncached = max(tin - cached, 0) if cached else tin
    usd = (uncached * t["price_in_per_1M"] + (cached * t["price_in_per_1M"] * disc if disc else cached * t["price_in_per_1M"]) + tout * t["price_out_per_1M"]) / 1e6
    return round(usd, 6), f"DERIVED: {t['price_source']}; in ${t['price_in_per_1M']}/1M x {uncached}" + (f" + cached {cached} x {disc}" if cached and disc else (f" + cached {cached} at full price (no discount on file)" if cached else "")) + f" + out ${t['price_out_per_1M']}/1M x {tout}"


def route_records(receipt, prov, ladder):
    if receipt.get("schema") != "our-auto/run@1":
        raise ImportError_(f"{prov['path']}: schema {receipt.get('schema')!r} is not our-auto/run@1")
    out = []
    cls = ROUTE_KIND_CLASS.get(receipt.get("kind"), f"router-{receipt.get('kind')}")
    task_id = f"route:{receipt.get('prompt_sha256', '')[:12]}:{receipt.get('validator_sha256', '')[:12]}"
    for a in receipt.get("attempts") or []:
        model, effort, provider = a.get("model"), a.get("effort"), a.get("provider")
        status = a.get("call_status")
        v = a.get("validator") or {}
        if status == "completed":
            outcome = "pass" if v.get("passed") is True else ("fail" if v.get("passed") is False else "partial")
        elif status == "failed":
            outcome = "error"
        else:
            outcome = "skipped"
        tin = tout = tcached = None; tok_basis = None
        if provider in LOCAL_PROVIDERS:
            tin, tout = a.get("prompt_eval_count"), a.get("eval_count")
            tok_basis = "ollama prompt_eval_count / eval_count (engine-reported)" if tin is not None else None
        elif isinstance(a.get("usage"), dict):
            tin, kin = _pick(a["usage"], USAGE_IN); tout, kout = _pick(a["usage"], USAGE_OUT); tcached, kc = _pick(a["usage"], USAGE_CACHED)
            tok_basis = f"codex usage {kin}/{kout}" + (f"/{kc}" if kc else "") + " (provider-reported)"
        cost, cost_basis = None, None
        seat_kind = "local" if provider in LOCAL_PROVIDERS else ("subscription" if provider in SUBSCRIPTION_PROVIDERS else "api")
        if outcome == "skipped":
            cost_basis = f"skipped ({a.get('reason')}); no call, no cost"
        elif tin is None or tout is None:
            cost_basis = "no provider-reported tokens on the attempt; cost not derivable"
        elif seat_kind == "local":
            cost, cost_basis = 0.0, "local ollama: provider cost $0 by construction; the seat's energy/lease cost lives in the fabric ledger (seat below)"
        else:
            cost, cost_basis = price_tokens(ladder, model, tin, tout, tcached)
        rec = {
            "schema": "second-run/tierbench-call@1", "kind": "our-auto-route-attempt",
            "tier": "tierbench-measured" if (tin is not None and outcome in DECISIVE) else "tierbench-shadow-estimated",
            "tier_reason": ("provider-reported tokens and an executable validator verdict" if (tin is not None and outcome in DECISIVE)
                            else "no provider-reported tokens or no validator verdict on this attempt"),
            "task_class": cls, "task_id": task_id, "route_kind": receipt.get("kind"),
            "model_tier": tier_string(model, effort), "model": model, "effort": effort, "provider": provider,
            "phase": "route", "trial": a.get("index"), "outcome": outcome, "decisive": outcome in DECISIVE,
            "outcome_basis": "route.py validator exit code (executable validator named in the receipt); a validator PASS is candidate-level only (SKILL.md)",
            "tokens": {"input": tin, "output": tout, "cache_read": tcached, "cache_write": None, "basis": tok_basis or "absent"},
            "cost_usd": cost, "cost_basis": cost_basis, "currency": "USD",
            "latency_ms": (a.get("elapsed_seconds") * 1000.0) if isinstance(a.get("elapsed_seconds"), (int, float)) else None,
            "ts": receipt.get("started_at_utc"), "note": a.get("reason") or a.get("error"),
            "seat": ({"seat_id": None, "seat_kind": "local", "reason": "route.py records no host: the ollama call ran on whichever GPU the router host had (policy gpu_busy_fraction probe); map to a seats.json id only with a host receipt"}
                     if seat_kind == "local" else {"seat_id": None, "seat_kind": seat_kind, "reason": f"{provider}: zero-seat provider cost, no fabric seat consumed"}),
            "validator": {"passed": v.get("passed"), "exit_code": v.get("exit_code"), "validator_sha256": receipt.get("validator_sha256")},
            "synthetic": bool(receipt.get("synthetic")),
            "provenance": dict(prov, attempt_index=a.get("index")),
        }
        nr = {}
        if cost is None:
            nr["cost_usd"] = cost_basis
        if rec["latency_ms"] is None:
            nr["latency_ms"] = "attempt has no elapsed_seconds (skipped or failed before timing)"
        if nr:
            rec["null_reasons"] = nr
        out.append(rec)
    return out


# ---------------------------------------------------------------- race6 aggregates
def race6_records(race6, prov):
    """The operator diagnostic gives per-tier totals for a 6-task ladder, not per-trial rows. One aggregate record per tier,
    n=6 decisive passes as the file states ('42/42 GPT hidden passes' across the ladder); never expanded into fake trials."""
    out = []
    solving = race6.get("solving_all_6_of_6") or {}
    for key, val in solving.items():
        if key == "claude_comparators":
            for short, usd in val.items():
                out.append(_race6_rec(RACE6_MODEL.get(short, short), "none", usd, prov, key + "." + short, "claude comparator, effort not stated"))
            continue
        short, _, eff = key.partition("@")
        eff = eff.replace("_rep", "")
        out.append(_race6_rec(RACE6_MODEL.get(short, short), eff, val.get("usd"), prov, key, "replication" if key.endswith("_rep") else None))
    return out


def _race6_rec(model, effort, usd, prov, key, note):
    return {
        "schema": "second-run/tierbench-call@1", "kind": "race6-aggregate",
        "tier": "tierbench-shadow-estimated",
        "tier_reason": "race6 operator diagnostic: subscription-derived totals, not per-call bills",
        "task_class": RACE6_CLASS, "task_id": "race6:solving-6-of-6", "model_tier": tier_string(model, effort), "model": model, "effort": effort,
        "phase": "race6", "trial": 0, "outcome": "pass", "decisive": True, "n_tasks": 6, "n_pass": 6,
        "outcome_basis": "race6 file: 'solving_all_6_of_6' + '42/42 GPT hidden passes + replication stable' (operator diagnostic, not a governed verdict)",
        "tokens": {"input": None, "output": None, "cache_read": None, "cache_write": None, "basis": "absent (aggregate)"},
        "cost_usd": usd, "cost_basis": "subscription-derived total for 6 tasks (race6 file); per-task = usd / 6", "currency": "USD",
        "latency_ms": None, "ts": None, "note": note,
        "seat": {"seat_id": None, "seat_kind": "subscription" if model.startswith("gpt") else "api", "reason": "zero-seat provider cost"},
        "provenance": dict(prov, key=key),
        "null_reasons": {"latency_ms": "aggregate row; no per-call latency", "ts": "race6 file carries no timestamps"},
    }


# ---------------------------------------------------------------- summary
def summarize(records, ladder, map_json, waterline, k=K_DEFAULT):
    wl_idx = waterline_index_of(waterline or {})
    classes = {}
    for r in records:
        if r["kind"] == "race6-aggregate":
            continue
        c = classes.setdefault(r["task_class"], {})
        t = c.setdefault(r["task_id"], {})
        e = t.setdefault(r["model_tier"], {"trials": 0, "pass": 0, "fail": 0, "error": 0, "partial": 0, "skipped": 0, "costs": [], "cost_bases": set(), "evidence_tiers": set(), "latencies": []})
        e["trials"] += 1
        e[r["outcome"] if r["outcome"] in e else "partial"] += 1
        if r.get("cost_usd") is not None and r["outcome"] != "skipped":
            e["costs"].append(float(r["cost_usd"]))
        if r.get("cost_basis"):
            e["cost_bases"].add(r["cost_basis"].split(":")[0].split(" ")[0])
        e["evidence_tiers"].add(r["tier"])
        if r.get("latency_ms"):
            e["latencies"].append(r["latency_ms"])
    summary = {"schema": "second-run/tierbench-summary@1", "k": k,
               "rule": "decisive = pass|fail. sufficient: >=K decisive and 0 fail; unstable: pass and fail both present; wall: >=K decisive and 0 pass; else insufficient-evidence. Min sufficient tier = cheapest by list-price ladder rank among sufficient tiers.",
               "classes": {}}
    for cls, tasks in sorted(classes.items()):
        cs = {"tasks": {}, "n_tasks": len(tasks), "covering_tier": None, "covering_tier_basis": None, "undetermined_tasks": [], "residue": [],
              "cost_per_trial_at_min_usd": None, "pass_rate_at_min": None}
        min_tiers, costs_at_min, pr_at_min = [], [], []
        for task_id, tiers in sorted(tasks.items()):
            ts = {}
            for tier, e in tiers.items():
                decisive = e["pass"] + e["fail"]
                if decisive >= k and e["fail"] == 0:
                    status = "sufficient"
                elif e["pass"] and e["fail"]:
                    status = "unstable"
                elif decisive >= k and e["pass"] == 0:
                    status = "wall"
                else:
                    status = "insufficient-evidence"
                nz = [c for c in e["costs"] if c > 0]
                ts[tier] = {"trials": e["trials"], "pass": e["pass"], "fail": e["fail"], "error": e["error"], "partial": e["partial"], "skipped": e["skipped"],
                            "decisive": decisive, "pass_rate": round(e["pass"] / decisive, 4) if decisive else None, "status": status,
                            "cost_per_trial_usd": round(statistics.mean(nz), 6) if nz else None,
                            "cost_per_trial_basis": (f"mean of {len(nz)} non-zero rows ({', '.join(sorted(e['cost_bases']))})" if nz else f"all {len(e['costs'])} rows carry cost 0 or null ({', '.join(sorted(e['cost_bases'])) or 'no basis'})"),
                            "evidence_tiers": sorted(e["evidence_tiers"]),
                            "latency_ms_median": round(statistics.median(e["latencies"]), 1) if e["latencies"] else None,
                            "ladder_rank": (ladder["tiers"].get(tier) or {}).get("rank")}
            suff = [t for t, v in ts.items() if v["status"] == "sufficient"]
            suff.sort(key=lambda t: (ts[t]["ladder_rank"] if ts[t]["ladder_rank"] is not None else 1e9, t))
            min_tier = suff[0] if suff else None
            unstable = [t for t, v in ts.items() if v["status"] == "unstable"]
            walls = [t for t, v in ts.items() if v["status"] == "wall"]
            entry = {"tiers": ts, "min_sufficient_tier": min_tier,
                     "min_sufficient_reason": ("cheapest sufficient tier on the ladder" if min_tier else "no tier reached K/K decisive passes: " + "; ".join(f"{t} {v['status']} ({v['pass']}/{v['decisive']})" for t, v in ts.items())),
                     "unstable_tiers": unstable, "wall_tiers": walls}
            mj = ((map_json or {}).get("tasks") or {}).get(task_id)
            if mj:
                entry["map_json_min_sufficient_tier"] = mj.get("min_sufficient_tier")
                entry["map_json_agrees"] = (mj.get("min_sufficient_tier") == min_tier)
            wl = [(m, v) for (t, m), v in wl_idx.items() if t == task_id]
            if wl:
                sealed_model, wv = wl[0]
                entry["waterline_json"] = wv
                entry["derived_min_sufficient_tier"] = min_tier
                sealed_tier = next((t for t in ts if t.split("@")[0] == sealed_model), None)
                entry["waterline_agrees"] = bool(min_tier and min_tier.split("@")[0] == sealed_model)
                if sealed_tier and sealed_tier != min_tier:
                    # waterline.json is Tier-Bench's sealed decision ("do not re-derive"): it wins; the derivation is kept beside it
                    entry["min_sufficient_reason"] = (f"SEALED by waterline.json {wv['section']} ({wv.get('status')}, rung {wv.get('rung')}, {wv.get('score')}); "
                                                      f"this importer's whole-window derivation says {min_tier} -- kept as derived_min_sufficient_tier, not used")
                    min_tier = sealed_tier
                    entry["min_sufficient_tier"] = sealed_tier
                    suff = [sealed_tier] + [t for t in suff if t != sealed_tier]
                elif not sealed_tier:
                    entry["min_sufficient_reason"] += f"; waterline.json seals {sealed_model} but no rows for it are in this ledger excerpt"
            # residue: floor unstable/walled, escalation, or no sufficient tier
            floor = min(ts, key=lambda t: (ts[t]["ladder_rank"] if ts[t]["ladder_rank"] is not None else 1e9, t)) if ts else None
            if floor and ts[floor]["status"] in ("unstable", "wall"):
                cs["residue"].append({"task_id": task_id, "floor_tier": floor, "floor_status": ts[floor]["status"], "floor_score": f"{ts[floor]['pass']}/{ts[floor]['decisive']}",
                                      "cleared_by": min_tier, "residue_name": (entry.get("waterline_json") or {}).get("residue_name"),
                                      "note": ("broker policy permits the next rung only after 0/K; this escalation left an unstable floor" if ts[floor]["status"] == "unstable" and min_tier else None)})
            elif not min_tier:
                cs["residue"].append({"task_id": task_id, "floor_tier": floor, "floor_status": ts[floor]["status"] if floor else None,
                                      "floor_score": f"{ts[floor]['pass']}/{ts[floor]['decisive']}" if floor else None, "cleared_by": None, "residue_name": None,
                                      "note": "unmapped: no tier is sufficient yet"})
            cs["tasks"][task_id] = entry
            if min_tier:
                min_tiers.append(min_tier)
                if ts[min_tier]["cost_per_trial_usd"] is not None:
                    costs_at_min.append(ts[min_tier]["cost_per_trial_usd"])
                pr_at_min.append(ts[min_tier]["pass_rate"])
            else:
                cs["undetermined_tasks"].append(task_id)
        if min_tiers:
            cov = max(min_tiers, key=lambda t: ((ladder["tiers"].get(t) or {}).get("rank") if (ladder["tiers"].get(t) or {}).get("rank") is not None else -1))
            cs["covering_tier"] = cov
            cs["covering_tier_basis"] = f"highest-ranked of the per-task min sufficient tiers ({len(min_tiers)}/{len(tasks)} tasks determined)" + (f"; {len(cs['undetermined_tasks'])} undetermined: {cs['undetermined_tasks']}" if cs["undetermined_tasks"] else "")
            cs["cost_per_trial_at_min_usd"] = round(statistics.mean(costs_at_min), 6) if costs_at_min else None
            cs["cost_per_trial_at_min_basis"] = f"mean over {len(costs_at_min)} tasks with non-zero cost at their min tier" if costs_at_min else "no non-zero cost at the min tiers (shadow/unbilled rows)"
            cs["pass_rate_at_min"] = round(statistics.mean(pr_at_min), 4) if pr_at_min else None
        else:
            cs["covering_tier_basis"] = "no task in this class has a sufficient tier"
        summary["classes"][cls] = cs
    # race6 aggregates as their own class (not per-task evidence)
    r6 = [r for r in records if r["kind"] == "race6-aggregate"]
    if r6:
        summary["classes"][RACE6_CLASS] = {"aggregate": True, "n_tasks": 6, "tiers": {r["model_tier"]: {"pass": 6, "decisive": 6, "pass_rate": 1.0, "status": "sufficient",
                                           "cost_per_trial_usd": round(r["cost_usd"] / 6, 6) if r.get("cost_usd") is not None else None,
                                           "cost_per_trial_basis": "race6 total / 6 tasks (subscription-derived)", "ladder_rank": (ladder["tiers"].get(r["model_tier"]) or {}).get("rank")} for r in r6},
                                           "covering_tier": min((r["model_tier"] for r in r6), key=lambda t: ((ladder["tiers"].get(t) or {}).get("rank") if (ladder["tiers"].get(t) or {}).get("rank") is not None else 1e9)),
                                           "covering_tier_basis": "every listed tier solved 6/6; cheapest by ladder rank", "residue": [],
                                           "note": "operator diagnostic aggregate; 'effort is pure surcharge on ceiling-saturated work' (race6 findings)"}
    return summary


# ---------------------------------------------------------------- IO
def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def run(tb_root, router_root, receipt_paths, out_dir, fixtures=False, k=K_DEFAULT):
    fp = None
    if fixtures:
        fp = load_json(os.path.join(FIXTURES, "PROVENANCE.json"))["sources"]
        paths = {"ledger": os.path.join(FIXTURES, "tierbench", "ledger.excerpt.jsonl"), "map": os.path.join(FIXTURES, "tierbench", "map.excerpt.json"),
                 "waterline": os.path.join(FIXTURES, "tierbench", "waterline.json"), "models": os.path.join(FIXTURES, "tierbench", "models.excerpt.json"),
                 "policy": os.path.join(FIXTURES, "router", "policy.json"), "race6": os.path.join(FIXTURES, "router", "race6-results.operator-diagnostic.json")}
    else:
        paths = {"ledger": os.path.join(tb_root, "experiments", "breadth", "run", "ledger.jsonl"), "map": os.path.join(tb_root, "experiments", "breadth", "run", "map.json"),
                 "waterline": os.path.join(tb_root, "experiments", "breadth", "run", "waterline.json"), "models": os.path.join(tb_root, "models.json"),
                 "policy": os.path.join(router_root, "references", "policy.json"), "race6": os.path.join(router_root, "references", "race6-results.operator-diagnostic.json")}
    for name, p in paths.items():
        if not os.path.exists(p):
            raise ImportError_(f"missing input {name}: {p}")
    prov = {name: provenance(p, root=(tb_root if name in ("ledger", "map", "waterline", "models") else router_root) if not fixtures else None, fixture_prov=fp) for name, p in paths.items()}
    rows = load_jsonl(paths["ledger"])
    map_json, waterline, models = load_json(paths["map"]), load_json(paths["waterline"]), load_json(paths["models"])
    policy, race6 = load_json(paths["policy"]), load_json(paths["race6"])
    seen = {}
    for r in rows:
        t, m, e = parse_tier(r)
        seen[t] = (m, e)
    for short, val in (race6.get("solving_all_6_of_6") or {}).items():
        if short == "claude_comparators":
            for s in val:
                seen[tier_string(RACE6_MODEL.get(s, s), "none")] = (RACE6_MODEL.get(s, s), "none")
        else:
            s, _, e = short.partition("@"); seen[tier_string(RACE6_MODEL.get(s, s), e.replace("_rep", ""))] = (RACE6_MODEL.get(s, s), e.replace("_rep", ""))
    ladder = build_ladder(models, race6, policy, seen)
    records = call_records(rows, prov["ledger"], waterline_index_of(waterline))
    records += race6_records(race6, prov["race6"])
    for rp in receipt_paths or []:
        records += route_records(load_json(rp), provenance(rp, root=router_root if not fixtures else None, fixture_prov=fp if fixtures else None), ladder)
    summary = summarize(records, ladder, map_json, waterline, k=k)
    summary["inputs"] = prov
    summary["receipts"] = [p.replace("\\", "/") for p in (receipt_paths or [])]
    summary["n_records"] = len(records)
    summary["entry_lock"] = {"W": tb_root, "R": router_root, "fixtures": fixtures}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "tierbench-calls.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    with open(os.path.join(out_dir, "tierbench-summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    with open(os.path.join(out_dir, "tier-ladder.json"), "w", encoding="utf-8") as f:
        json.dump(ladder, f, indent=1)
    return records, summary, ladder


# ---------------------------------------------------------------- self-test
def selftest():
    import tempfile
    ok = True
    def check(cond, msg):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {msg}")
        ok = ok and cond
    receipts = sorted(os.path.join(FIXTURES, "router", f) for f in os.listdir(os.path.join(FIXTURES, "router")) if f.startswith("receipt-"))
    with tempfile.TemporaryDirectory(prefix="tierbench-import-") as td:
        records, summary, ladder = run(None, None, receipts, td, fixtures=True)
        calls = [r for r in records if r["kind"] == "tierbench-ledger-call"]
        check(len(calls) == 52, f"52 fixture Call rows imported ({len(calls)})")
        check(all(r["provenance"]["git_commit"] == "da9b0a9cd1df25070e3763a1b6d1835d5b0f71e3" for r in calls), "every Call record carries the ledger.jsonl source commit da9b0a9")
        check(all(r["provenance"]["fixture_of_sha256"] == "4e26a7950999093c943c2e099e603e3cad961b2b232538b25bb5042cb5c27c1c" for r in calls), "and the source file's sha256")
        t = summary["classes"]["tierbench-T0"]["tasks"]
        check(t["t0_format_whitespace_002"]["min_sufficient_tier"] == "claude-haiku-4-5@harness" and t["t0_format_whitespace_002"]["map_json_agrees"], "T0 format_whitespace: haiku@harness sufficient 3/3, agrees with map.json")
        check(t["t0_rename_symbol_003"]["tiers"]["claude-fable-5@low"]["status"] == "sufficient" and t["t0_rename_symbol_003"]["min_sufficient_tier"] == "claude-haiku-4-5@harness", "T0 rename_symbol: both tiers sufficient, min = cheaper haiku")
        sh = [r for r in calls if r["task_id"] == "t0_format_whitespace_002"]
        check(all(r["tier"] == "tierbench-shadow-estimated" and r["cost_basis"] == "shadow-estimated" for r in sh), "subagent split-estimate rows tagged tierbench-shadow-estimated")
        w = summary["classes"]["breadth-task02-wildcard"]["tasks"]["task02_wildcard"]
        check(w["tiers"]["claude-haiku-4-5@harness"]["status"] == "unstable" and w["min_sufficient_tier"] == "claude-sonnet-5@low", f"task02: haiku floor unstable, min sufficient sonnet@low ({w['tiers']['claude-haiku-4-5@harness']['pass']}/{w['tiers']['claude-haiku-4-5@harness']['decisive']})")
        sonnet = [r for r in calls if r["task_id"] == "task02_wildcard" and r["model"] == "claude-sonnet-5"]
        check(sonnet and all(r["tier"] == "tierbench-measured" and r["cost_basis"] == "real-billed" and "waterline.json" in r["tier_reason"] for r in sonnet), "task02 sonnet rows: waterline.json says real-billed -> tierbench-measured")
        check(w["waterline_agrees"] is True and w["derived_min_sufficient_tier"] == "claude-sonnet-5@low", "task02: derivation agrees with the sealed waterline.json decision on the excerpt")
        # a sealed decision wins over the derivation: add five 'cheap' passes (as the full ledger has) and the seal must still hold
        extra = [dict(json.loads(l), tier="cheap", phase="verify", trial=i, outcome="pass", cost_usd=0.062) for i, l in enumerate(open(os.path.join(FIXTURES, "tierbench", "ledger.excerpt.jsonl"), encoding="utf-8")) if '"task02_wildcard"' in l][:5]
        L2 = json.load(open(os.path.join(FIXTURES, "tierbench", "models.excerpt.json"), encoding="utf-8"))
        wl2 = load_json(os.path.join(FIXTURES, "tierbench", "waterline.json"))
        rec2 = call_records(extra, {"path": "synthetic"}, waterline_index_of(wl2)) + [r for r in calls if r["task_id"] == "task02_wildcard"]
        lad2 = build_ladder(L2, {}, {}, {"cheap": ("claude-haiku-4-5", "cheap"), "claude-haiku-4-5@harness": ("claude-haiku-4-5", "harness"), "claude-sonnet-5@low": ("claude-sonnet-5", "low")})
        s2 = summarize(rec2, lad2, {}, wl2)["classes"]["breadth-task02-wildcard"]["tasks"]["task02_wildcard"]
        check(s2["derived_min_sufficient_tier"] == "cheap" and s2["min_sufficient_tier"] == "claude-sonnet-5@low" and s2["waterline_agrees"] is False and "SEALED" in s2["min_sufficient_reason"],
              f"sealed decision wins: derived {s2['derived_min_sufficient_tier']} (5/5 at 'cheap'), used {s2['min_sufficient_tier']}, disagreement written")
        res = summary["classes"]["breadth-task02-wildcard"]["residue"]
        check(any(x["task_id"] == "task02_wildcard" and x["residue_name"] and x["cleared_by"] == "claude-sonnet-5@low" for x in res), "task02 residue named from waterline.json and cleared by sonnet@low")
        check(any(x["task_id"] == "replay02_charclass_filter" and x["floor_status"] == "wall" and x["cleared_by"] is None for x in res), "replay02: 0/3 at the floor = wall, unmapped (no higher rung measured)")
        check(any(x["task_id"] == "replay04_count_matches" and x["floor_status"] == "unstable" for x in res), "replay04: mixed = unstable")
        a = summary["classes"]["arc-c-almanac"]["tasks"]["almanac_rule_boundary_001"]
        check(a["min_sufficient_tier"] == "claude-fable-5@low" and a["unstable_tiers"] == ["claude-haiku-4-5@harness"], "almanac rule_boundary: haiku 1/3 unstable, fable@low 3/3 sufficient")
        check(any("unstable floor" in (x.get("note") or "") for x in summary["classes"]["arc-c-almanac"]["residue"]), "almanac: escalation from an unstable floor is flagged (broker permits next rung only after 0/K)")
        p = summary["classes"]["tierbench-T3"]["tasks"]["t3_parse_duration_004"]
        check(p["tiers"]["claude-haiku-4-5@harness"]["error"] == 3 and p["tiers"]["claude-haiku-4-5@harness"]["status"] == "sufficient", "t3 parse_duration: 3 errors excluded from decisive; 3/3 passes sufficient")
        z = [r for r in calls if r["task_id"] == "almanac_rule_boundary_001"]
        check(all(r["cost_basis"] == "shadow-estimated" and r["cost_usd"] == 0 and r["cost_zero_unbilled"] for r in z), "shadow rows with tokens but cost 0 stay shadow-estimated and are flagged cost_zero_unbilled")
        b0, why0 = cost_basis_for({"task_id": "x", "model": "m", "note": "", "cost_usd": 0, "input_tokens": 0, "output_tokens": 0}, {})
        check(b0 == "unbilled-zero" and "logged blank" in why0, "a row with no tokens and no cost is unbilled-zero (a logged blank)")
        b1, _ = cost_basis_for({"task_id": "x", "model": "m", "note": "", "cost_usd": 0.5, "input_tokens": 10, "output_tokens": 1}, {})
        check(b1 == "shadow-estimated", "a priced row with no billing receipt named defaults to shadow-estimated, never measured")
        b2 = summary["classes"]["arc-d-b2-grade"]["tasks"]["b2_grade_attrs_1567_setattr_mro"]
        check(b2["min_sufficient_tier"] is None and b2["tiers"]["claude-fable-5@high"]["status"] == "insufficient-evidence" and b2["tiers"]["claude-fable-5@high"]["evidence_tiers"] == ["tierbench-measured"], "b2 grade: 2/2 real-billed but < K -> insufficient-evidence, tagged measured")
        # route receipts
        rr = [r for r in records if r["kind"] == "our-auto-route-attempt"]
        check(len(rr) == 7, f"7 route attempts from 4 synthetic receipts: 2 + 1 + 3 + 1 ({len(rr)})")
        qa = [r for r in rr if r["model"] == "qwen3.5:9b-q4_K_M"][0]
        check(qa["cost_usd"] == 0.0 and qa["seat"]["seat_kind"] == "local" and qa["seat"]["seat_id"] is None and qa["tokens"]["input"] == 46, "ollama attempt: provider $0, local seat unmapped with reason, engine token counts")
        lb = [r for r in rr if r["model"] == "gpt-5.6-luna" and r["outcome"] == "pass"][0]
        check(abs(lb["cost_usd"] - ((1200 * 1 + 600 * 1 * 0.1 + 420 * 6) / 1e6)) < 1e-9 and lb["cost_basis"].startswith("DERIVED"), f"luna pass: cost derived from race6 list price with cache discount (${lb['cost_usd']})")
        skipped = [r for r in rr if r["outcome"] == "skipped"]
        check(len(skipped) == 2 and all(r["cost_usd"] is None and "cost_usd" in r["null_reasons"] for r in skipped), "skipped attempts: null cost with a written reason")
        failed = [r for r in rr if r["outcome"] == "error"][0]
        check(failed["cost_usd"] is None and failed["tier"] == "tierbench-shadow-estimated", "failed transport: no tokens, null cost, not 'measured'")
        rc = summary["classes"]["router-code"]
        check(all(r["synthetic"] for r in rr), "route records flagged synthetic")
        # ladder
        L = ladder["tiers"]
        check(L["claude-haiku-4-5@harness"]["rank"] < L["claude-sonnet-5@low"]["rank"] < L["claude-fable-5@low"]["rank"] < L["claude-fable-5@high"]["rank"], "ladder: haiku < sonnet < fable@low < fable@high")
        check(L["qwen3.5:9b-q4_K_M@none"]["seat_kind"] == "local" and L["qwen3.5:9b-q4_K_M@none"]["list_usd_per_nominal_closure"] == 0, "ladder: ollama tier is local, $0 provider price")
        check(L["gpt-5.6-luna@low"]["seat_kind"] == "subscription" and L["gpt-5.6-luna@low"]["price_source"].startswith("race6"), "ladder: luna priced from race6, subscription seat kind")
        r6 = summary["classes"][RACE6_CLASS]
        check(r6["covering_tier"] == "claude-haiku-4-5@none" and abs(r6["tiers"]["gpt-5.6-luna@low"]["cost_per_trial_usd"] - 0.116 / 6) < 1e-6, "race6: aggregates kept as aggregates; haiku cheapest by ladder rank; luna $0.116/6 per task")
        # outputs exist and reload
        calls_path = os.path.join(td, "tierbench-calls.jsonl")
        check(len(load_jsonl(calls_path)) == len(records) and os.path.exists(os.path.join(td, "tierbench-summary.json")), "outputs written and reload")
        # refusal: wrong receipt schema
        bad = os.path.join(td, "bad.json"); json.dump({"schema": "nope"}, open(bad, "w"))
        try:
            route_records(load_json(bad), provenance(bad, fixture_prov={}), ladder); check(False, "bad receipt schema refused")
        except ImportError_ as e:
            check("our-auto/run@1" in str(e), f"bad receipt schema refused: {e}")
    print(f"import_tierbench selftest: {'all passed' if ok else 'FAILURES'}")
    return ok


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    if argv[0] == "--selftest":
        return 0 if selftest() else 1
    tb = rr = out = None; fixtures = False; receipts = []; k = K_DEFAULT
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--tierbench-root": tb = argv[i + 1]; i += 2
        elif a == "--router-root": rr = argv[i + 1]; i += 2
        elif a == "--receipts":
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                p = argv[i]
                receipts += sorted(os.path.join(p, f) for f in os.listdir(p) if f.endswith(".json")) if os.path.isdir(p) else [p]
                i += 1
        elif a == "--out": out = argv[i + 1]; i += 2
        elif a == "--fixtures": fixtures = True; i += 1
        elif a == "--k": k = int(argv[i + 1]); i += 2
        else: print(f"unknown arg {a}"); return 1
    if not out or (not fixtures and not (tb and rr)):
        print("need --out DIR and either --fixtures or --tierbench-root W --router-root R"); return 1
    if fixtures and not receipts:
        receipts = sorted(os.path.join(FIXTURES, "router", f) for f in os.listdir(os.path.join(FIXTURES, "router")) if f.startswith("receipt-"))
    try:
        records, summary, ladder = run(tb, rr, receipts, out, fixtures=fixtures, k=k)
    except (ImportError_, OSError, json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"import error: {type(e).__name__}: {e}"); return 1
    print(f"wrote {len(records)} records, {len(summary['classes'])} task classes, {len(ladder['tiers'])} ladder tiers -> {out}")
    for cls, cs in summary["classes"].items():
        print(f"  {cls}: covering tier {cs.get('covering_tier')} ({cs.get('covering_tier_basis')}); residue {len(cs.get('residue') or [])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
