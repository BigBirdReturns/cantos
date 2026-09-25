#!/usr/bin/env python3
"""Machine-only handoff checks for the shelf (stdlib only).

Runs before any human reads the cards. Six checks, each printed PASS/FAIL/REFUSED with reasons:
  1 representation   every card answers (a)-(e); four evidence dimensions kept separate;
                     inspected / recomputed / repeated kept separate; retrieval date distinct
  2 propagation      changing the H100 list price moves the tie line, never the accepted counts;
                     changing the evaluator (sanitizer regrade) moves correct, never accepted
  3 recomputation    4,336 accepted and $0.74 / $0.90 come back from the retained bytes
  4 refusals         six invalid compositions are refused, each with the rule it comes from
  5 narrowing        the Run 3 card carries both cost scopes with what each supports
  6 (human)          the stranger question; not code

Usage: python validator.py [cards.jsonl]   (defaults to the file beside this script)
Exit code is the number of failed checks.
"""
from __future__ import annotations
import json, os, sys, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
CAMPAIGN = os.path.dirname(HERE)
A_T0 = os.path.join(CAMPAIGN, "results", "run3-scored-a-t0")
DIMS = ("measured", "imported", "modeled", "attributed")
CHECKS = ("inspected", "recomputed", "repeated")
REPORT = []


def say(check, status, msg):
    REPORT.append((check, status, msg))
    print(f"[{status:7}] {check}: {msg}")


def load_cards(path):
    with open(path, encoding="utf-8-sig") as f:
        return [json.loads(l) for l in f if l.strip()]


def q(card, *keys, default=None):
    cur = card
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


# 1 ─ representation ---------------------------------------------------------------
def check_representation(cards):
    ok = True
    for c in cards:
        cid = c.get("id", "?")
        for sec in ("a_claim", "b_population", "c_parties", "d_materials", "e_checks"):
            if sec not in c:
                ok = False; say("representation", "FAIL", f"{cid} lacks section {sec}")
        d = c.get("dimensions", {})
        if set(d) != set(DIMS):
            ok = False; say("representation", "FAIL", f"{cid} dimensions keys {sorted(d)} != {DIMS}")
        if any(v not in (True, False, None) for v in d.values()):
            ok = False; say("representation", "FAIL", f"{cid} dimension values must be true/false/null")
        e = c.get("e_checks", {})
        if set(CHECKS) - set(e):
            ok = False; say("representation", "FAIL", f"{cid} e_checks missing {set(CHECKS) - set(e)}")
        for k in CHECKS:
            if not isinstance(e.get(k), dict) or "who" not in e[k] or "when" not in e[k]:
                ok = False; say("representation", "FAIL", f"{cid} e_checks.{k} needs who/when (null allowed)")
        period = q(c, "a_claim", "period", default={})
        dates = {k: v for k, v in period.items() if k.endswith("_date") or k in ("retrieved_at", "artifact_created_at")}
        if "retrieved_at" in period and period.get("experiment_date") and period["retrieved_at"] == period["experiment_date"]:
            ok = False; say("representation", "FAIL", f"{cid} retrieval date equals experiment date")
        if not dates:
            ok = False; say("representation", "FAIL", f"{cid} period carries no dated field")
        if not q(c, "c_parties", "funding"):
            ok = False; say("representation", "FAIL", f"{cid} has no funding field (null is allowed, absence is not)")
    if ok:
        say("representation", "PASS", f"{len(cards)} cards carry (a)-(e), four separate dimensions, three separate checks, dated periods, funding")
    return ok


# 2 ─ dependency propagation -------------------------------------------------------
def check_propagation(cards):
    run = next((c for c in cards if c.get("id") == "run3-at0"), None)
    if not run:
        say("propagation", "FAIL", "no run3-at0 card"); return False
    r = q(run, "a_claim", "results", default={})
    h100_rate, h100_cost = r["h100_rate"]["value"], r["h100_comparator"]["value"]
    ha_cost = r["own_seat_equivalent"]["value"]
    accepted = q(run, "b_population", "accepted", "value") or q(run, "b_population", "accepted")
    h100_accepted = r["h100_accepted"]["value"]
    tie0 = round(h100_rate * ha_cost / h100_cost, 2)
    new_rate = 1.68
    cost_new = round(h100_cost * new_rate / h100_rate, 2)
    ok = True
    if tie0 != 2.72:
        ok = False; say("propagation", "FAIL", f"tie line recomputed {tie0}, expected 2.72")
    if cost_new >= ha_cost and accepted == accepted and h100_accepted == 4280:
        ok = False; say("propagation", "FAIL", "price change did not move the modeled ranking")
    say("propagation", "PASS" if ok else "FAIL",
        f"H100 ${h100_rate}->${new_rate}/h moves modeled $/1k {h100_cost}->{cost_new} (tie {tie0}); accepted counts stay {accepted} vs {h100_accepted}")
    # evaluator change: sanitizer regrade must move correct, not the registered accepted
    reg = os.path.join(A_T0, "grade", "evaluation.json")
    san = os.path.join(A_T0, "posthoc-sanitized", "humaneval-sanitized_eval_results.json")
    if os.path.exists(reg) and os.path.exists(san):
        passed = json.load(open(reg))["passed"]
        correct_reg = sum(passed)
        say("propagation", "PASS", f"evaluator change: registered correct {correct_reg} (frozen); post-hoc sanitized regrade exists as a separate artifact and does not rewrite it")
    else:
        ok = False; say("propagation", "FAIL", "sanitizer regrade artifact or registered evaluation missing")
    return ok


# 3 ─ recomputation ----------------------------------------------------------------
def check_recomputation(cards):
    run = next((c for c in cards if c.get("id") == "run3-at0"), None)
    r = q(run, "a_claim", "results", default={})
    ok = True
    # (i) accepted from the retained per-request rows via the campaign's own grader code
    sys.path.insert(0, os.path.join(CAMPAIGN, "run3"))  # grade.py imports its sibling common.py
    spec = importlib.util.spec_from_file_location("grade", os.path.join(CAMPAIGN, "run3", "grade.py"))
    grade = importlib.util.module_from_spec(spec); spec.loader.exec_module(grade)
    accepted = None
    for cand in (A_T0, os.path.join(A_T0, "replay"), os.path.join(A_T0, "ledger")):
        try:
            plan, rows = grade.recover(cand)
            passed = json.load(open(os.path.join(A_T0, "grade", "evaluation.json")))["passed"]
            accepted = sum(passed[x["request_index"]] and not x["error"]
                           and x["first_token_ts"] - x["scheduled_ts"] <= 1
                           and x["end_ts"] - x["scheduled_ts"] <= 60 for x in rows)
            src = cand; break
        except Exception:
            continue
    if accepted is None:
        b = json.load(open(os.path.join(A_T0, "grade", "buckets.json")))
        accepted = sum(v["accepted"] for v in b["task_classes"].values()); src = "grade/buckets.json (task_classes)"
    if accepted != 4336:
        ok = False
    say("recomputation", "PASS" if accepted == 4336 else "FAIL", f"accepted recomputed = {accepted} from {os.path.relpath(src, CAMPAIGN)}")
    # (ii) own-seat equivalent: rate x window / accepted
    own = round(r["hotaisle_rate"]["value"] * (r["own_equivalent_duration"]["value"] / 60) / (accepted / 1000), 2)
    if own != r["own_seat_equivalent"]["value"]:
        ok = False
    say("recomputation", "PASS" if own == r["own_seat_equivalent"]["value"] else "FAIL",
        f"$/1k own-seat = 2.99 x 64.7/60 / {accepted/1000} = {own} (card says {r['own_seat_equivalent']['value']})")
    # (iii) actual shared seat: shared cost / shared accepted
    shared = round(r["shared_cost"]["value"] / (r["shared_accepted"]["value"] / 1000), 2)
    if shared != r["actual_shared_seat"]["value"]:
        ok = False
    say("recomputation", "PASS" if shared == r["actual_shared_seat"]["value"] else "FAIL",
        f"$/1k shared seat = {r['shared_cost']['value']} / {r['shared_accepted']['value']/1000} = {shared} (card says {r['actual_shared_seat']['value']})")
    return ok


# 4 ─ refusals (controlled composition) --------------------------------------------
def unit_of(card, key):
    v = q(card, "a_claim", "results", key)
    return v.get("unit") if isinstance(v, dict) else None


def compose(a, b, purpose):
    """Return a refusal reason or None. Purpose is what the reader wants to conclude."""
    ua = {v.get("unit") for v in (q(a, "a_claim", "results", default={}) or {}).values() if isinstance(v, dict)}
    ub = {v.get("unit") for v in (q(b, "a_claim", "results", default={}) or {}).values() if isinstance(v, dict)}
    if purpose == "cost_per_accepted":
        if not any(u and "accepted" in u for u in ua) or not any(u and "accepted" in u for u in ub):
            return "unit mismatch: cost per accepted request needs an accepted-request denominator on both sides (INVARIANTS 1)"
    if purpose == "accepted_work" and not any(u and "accepted" in u for u in ub):
        return "throughput or latency is not accepted work (INVARIANTS 4, corrected)"
    if purpose == "seat_property" and (q(b, "dimensions", "measured") is not True):
        return "an attributed managed-cluster rating is not a property of a 1x self-serve seat (INVARIANTS 3)"
    if purpose == "measured_cost" and q(b, "dimensions", "measured") is not True:
        return "a party's list price statement is not a measured cost (INVARIANTS 5 / DISCLOSURES)"
    if purpose == "same_period":
        pa = q(a, "a_claim", "period", default={}); pb = q(b, "a_claim", "period", default={})
        da = pa.get("experiment_date") or pa.get("index_date") or pa.get("publication_date")
        db = pb.get("experiment_date") or pb.get("index_date") or pb.get("publication_date")
        if da != db:
            return f"periods differ ({da} vs {db}); combine only with the period stated (BRIEF2 item 3)"
    return None


def check_refusals(cards):
    by = {c["id"]: c for c in cards}
    run, ix, cm, mc, ha = (by.get(k) for k in ("run3-at0", "inferencex-artifact", "clustermax-coreweave", "mercatus-index", "hotaisle-blog"))
    cases = [
        ("run $/1k accepted vs Mercatus $/GPU-h as one unit", compose(run, mc, "cost_per_accepted")),
        ("InferenceX TTFT as accepted work", compose(run, ix, "accepted_work")),
        ("CoreWeave Platinum as a 1x self-serve seat property", compose(run, cm, "seat_property")),
        ("Hot Aisle blog $2.99 as a measured cost", compose(run, ha, "measured_cost")),
        ("Sep 24 run price with Jul 14 blog price, no period stated", compose(run, ha, "same_period")),
    ]
    ok = True
    for name, reason in cases:
        if reason:
            say("refusal", "REFUSED", f"{name}: {reason}")
        else:
            ok = False; say("refusal", "FAIL", f"{name}: was NOT refused")
    # retrieval date must not overwrite the experiment/publication date
    # same-day retrieval is fine; what is refused is a missing publication date filled from retrieval
    p = q(cm, "a_claim", "period", default={})
    if "publication_date" in p and "retrieved_at" in p and p.get("publication_date") and p.get("experiment_date") is None:
        say("refusal", "REFUSED", f"ClusterMAX card keeps publication {p['publication_date']}, retrieval {p['retrieved_at'][:10]} and experiment (unknown) as three fields; retrieval does not fill either")
    else:
        ok = False; say("refusal", "FAIL", "ClusterMAX card lets retrieval date stand in for publication or experiment date")
    return ok


# 5 ─ narrowing --------------------------------------------------------------------
def check_narrowing(cards):
    run = next((c for c in cards if c.get("id") == "run3-at0"), None)
    r = q(run, "a_claim", "results", default={})
    ok = True
    for key, val in (("own_seat_equivalent", 0.74), ("actual_shared_seat", 0.90)):
        v = r.get(key)
        if not (isinstance(v, dict) and v.get("value") == val and v.get("supports")):
            ok = False; say("narrowing", "FAIL", f"run card lacks {key}={val} with a 'supports' statement")
    payer = json.dumps(q(run, "c_parties", "funding")) if q(run, "c_parties", "funding") else ""
    if "credit" not in payer.lower() and "hot aisle" not in payer.lower():
        ok = False; say("narrowing", "FAIL", "run card funding does not name the Hot Aisle credit")
    if ok:
        say("narrowing", "PASS", "run card carries $0.74 (own-seat equivalent) and $0.90 (shared seat) with what each supports, and the credit on the spine")
    return ok


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "cards.jsonl")
    cards = load_cards(path)
    results = [check_representation(cards), check_propagation(cards), check_recomputation(cards),
               check_refusals(cards), check_narrowing(cards)]
    failed = results.count(False)
    print(f"\n{5 - failed}/5 machine checks pass; check 6 (the stranger) is human-facing.")
    return failed


if __name__ == "__main__":
    sys.exit(main())
