#!/usr/bin/env python3
"""Machine-only handoff checks for the shelf (stdlib only).

Five machine checks print PASS/FAIL/REFUSED with reasons. They do not establish
independent human use:
  1 representation   every card answers (a)-(e); four evidence dimensions kept separate;
                     inspected / recomputed / repeated kept separate; retrieval date distinct
  2 propagation      changing the H100 list price moves the tie line, never the accepted counts;
                     changing the evaluator (sanitizer regrade) moves correct, never accepted
  3 recomputation    accepted count from the native replay/grading path;
                     $0.74 / $0.90 arithmetic from declared accounting inputs
  4 refusals         six invalid compositions are refused, each with the rule it comes from
  5 narrowing        the Run 3 card carries both cost scopes with what each supports
  6 (model handoff)  the model-stranger question; assessed separately, not code

Usage: python validator.py [cards.jsonl]   (defaults to the file beside this script)
       python validator.py --card card.json  (one filing; representation only)
Exit code is the number of failed checks.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
import re
import sys

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
def text_or_null(value):
    return value is None or isinstance(value, str) and bool(value.strip())


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def scalar(value):
    return value.get("value") if isinstance(value, dict) else value


def normalized_unit(value):
    return re.sub(r"\s+", "", value).lower() if isinstance(value, str) else ""


def validate_card(card):
    """Return filing errors for one card, without requiring the five-card shelf.

    A supplied provenance explanation is checked for presence, not certified as
    true. Inspecting that cited source remains a separate recorded check.
    """
    errors = []
    if not isinstance(card, dict):
        return ["card must be an object"]
    for sec in ("a_claim", "b_population", "c_parties", "d_materials", "e_checks"):
        if not isinstance(card.get(sec), dict):
            errors.append(f"{sec} must be an object")
    dims = card.get("dimensions")
    if not isinstance(dims, dict) or set(dims) != set(DIMS):
        errors.append(f"dimensions must contain exactly {DIMS}")
    elif any(value is not None and type(value) is not bool for value in dims.values()):
        errors.append("dimension values must be true/false/null, not integers")
    for key in CHECKS:
        check = q(card, "e_checks", key)
        if not isinstance(check, dict) or not {"who", "when"} <= set(check):
            errors.append(f"e_checks.{key} needs who/when (null allowed)")
        elif not all(text_or_null(check[k]) for k in ("who", "when")):
            errors.append(f"e_checks.{key}.who/when must be nonempty strings or null")
    period = q(card, "a_claim", "period")
    if not isinstance(period, dict):
        errors.append("a_claim.period must be an object")
    else:
        dates = {k: v for k, v in period.items()
                 if k.endswith("_date") or k in ("retrieved_at", "artifact_created_at")}
        if not dates or any(not text_or_null(v) for v in dates.values()):
            errors.append("period needs dated fields containing strings or explicit nulls")
        basis = period.get("publication_date_basis")
        if ("publication_date_basis" not in period or not text_or_null(basis)
                or period.get("publication_date") is not None and not basis):
            errors.append("publication_date_basis must cite the dated source for a publication date; retrieval is not publication evidence; use null for an unknown publication date")
        # Same-day experiment, publication and retrieval are legitimate. Their
        # provenance, rather than inequality between their values, matters.
    parties = card.get("c_parties", {})
    if not isinstance(parties, dict) or "funding" not in parties:
        errors.append("c_parties.funding is required (null is allowed)")
    benefit = q(card, "c_parties", "observer_benefit")
    if not isinstance(benefit, dict) or not {"benefits_from_outcome", "relationship", "basis"} <= set(benefit):
        errors.append("c_parties.observer_benefit needs benefits_from_outcome, relationship and basis (unknowns may be null)")
    else:
        outcome = benefit["benefits_from_outcome"]
        if outcome is not None and type(outcome) is not bool:
            errors.append("observer_benefit.benefits_from_outcome must be true/false/null, not an integer")
        if not all(text_or_null(benefit[k]) for k in ("relationship", "basis")):
            errors.append("observer_benefit.relationship/basis must be nonempty strings or null")
        if type(outcome) is bool and not benefit["basis"]:
            errors.append("observer_benefit needs a basis for a known benefit judgment")
    results = q(card, "a_claim", "results")
    if not isinstance(results, dict):
        errors.append("a_claim.results must be an object")
    else:
        # Inspect every result alias; the stranger's hourly_rate is not a
        # special case. Never silently equate a whole-seat hour with a GPU-hour.
        for key, result in results.items():
            if not isinstance(result, dict):
                continue
            unit = normalized_unit(result.get("unit"))
            hourly = unit.startswith("usd") and re.search(r"(?:hour|hr|/h$|/gpu-h$|/seat-h$)", unit)
            if hourly:
                if unit not in ("usd/gpu-hour", "usd/seat-hour"):
                    errors.append(f"results.{key}.unit: monetary hourly rate must be USD/GPU-hour or USD/seat-hour, not {result.get('unit')!r}")
                if result.get("value") is not None and (not number(result["value"]) or result["value"] < 0):
                    errors.append(f"results.{key}.value must be a finite nonnegative number, not a boolean")
                if unit == "usd/seat-hour" and result.get("value") is not None:
                    gpus = scalar(q(card, "a_claim", "conditions", "gpus"))
                    if type(gpus) is not int or gpus <= 0:
                        errors.append(f"results.{key}: USD/seat-hour requires a positive integer configuration GPU count in conditions.gpus")
    return errors


def check_representation(cards):
    ok = bool(cards)
    if not cards:
        say("representation", "FAIL", "no cards supplied")
    for card in cards:
        for error in validate_card(card):
            ok = False
            say("representation", "FAIL", f"{card.get('id', '?') if isinstance(card, dict) else '?'}: {error}")
    if ok:
        say("representation", "PASS", f"{len(cards)} cards carry (a)-(e), separate dimensions/checks, publication-date basis, observer benefit and explicit hourly units; source truth is not certified")
    return ok


# 2 ─ dependency propagation -------------------------------------------------------
def check_propagation(cards):
    run = next((c for c in cards if c.get("id") == "run3-at0"), None)
    if not run:
        say("propagation", "FAIL", "no run3-at0 card"); return False
    r = q(run, "a_claim", "results", default={})
    h100_rate, h100_cost = r["h100_rate"]["value"], r["h100_comparator"]["value"]
    ha_cost = r["own_seat_equivalent"]["value"]
    accepted = scalar(q(run, "b_population", "accepted"))
    h100_accepted = r["h100_accepted"]["value"]
    tie0 = round(h100_rate * ha_cost / h100_cost, 2)
    new_rate = 1.68
    cost_new = round(h100_cost * new_rate / h100_rate, 2)
    ok = True
    if tie0 != 2.72:
        ok = False; say("propagation", "FAIL", f"tie line recomputed {tie0}, expected 2.72")
    if cost_new >= ha_cost or type(accepted) is not int or accepted != 4336 or type(h100_accepted) is not int or h100_accepted != 4280:
        ok = False; say("propagation", "FAIL", "modeled ranking or retained accepted counts disagree with the bounded scenario")
    say("propagation", "PASS" if ok else "FAIL",
        f"H100 ${h100_rate}->${new_rate}/h moves modeled $/1k {h100_cost}->{cost_new} (tie {tie0}); accepted counts stay {accepted} vs {h100_accepted}")
    # evaluator change: sanitizer regrade must move correct, not the registered accepted
    reg = os.path.join(A_T0, "grade", "evaluation.json")
    san = os.path.join(A_T0, "posthoc-sanitized", "humaneval-sanitized_eval_results.json")
    try:
        with open(reg, encoding="utf-8") as f:
            passed = json.load(f)["passed"]
        if not isinstance(passed, list) or any(type(v) is not bool for v in passed):
            raise ValueError("registered correctness mask must contain booleans")
        totals = []
        for path in (os.path.join(A_T0, "grade", "humaneval_eval_results.json"), san):
            with open(path, encoding="utf-8") as f:
                evaluations = json.load(f)["eval"]
            entries = [v for group in evaluations.values() for v in group]
            if not entries or any(v.get("base_status") not in ("pass", "fail", "timeout")
                                  or v.get("plus_status") not in ("pass", "fail", "timeout") for v in entries):
                raise ValueError("missing or invalid HumanEval result statuses")
            totals.append((len(entries), sum(v["base_status"] == v["plus_status"] == "pass" for v in entries)))
        if totals[0][0] != totals[1][0] or totals[1][1] <= totals[0][1]:
            raise ValueError(f"retained regrade does not support a correctness increase: {totals}")
        say("propagation", "PASS", f"separate HumanEval regrade: {totals[0][1]}->{totals[1][1]} correct of {totals[0][0]}; registered full-run correct {sum(passed)} and accepted {accepted} remain separate. No post-hoc accepted count computed")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        ok = False; say("propagation", "FAIL", f"cannot compare retained sanitizer evidence: {exc}")
    return ok


# 3 ─ recomputation ----------------------------------------------------------------
def recompute_retained_run(directory=None):
    """Reconstruct the journal and rejoin retained EvalPlus results, without writes.

    This is recomputation of saved evidence, not a fresh benchmark or grader run.
    Missing or inconsistent inputs raise; aggregate summaries are never fallback.
    """
    directory = os.fspath(directory or A_T0)
    module_path = os.path.join(CAMPAIGN, "run3")
    sys.path.insert(0, module_path)  # grade.py imports its existing siblings.
    try:
        spec = importlib.util.spec_from_file_location("shelf_run3_grade", os.path.join(module_path, "grade.py"))
        grade = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(grade)
    finally:
        sys.path.remove(module_path)
    replay = os.path.join(directory, "replay")
    # recover() deliberately supports interrupted runs. An absent journal must
    # not become a zero-result stand-in for this retained completed run.
    if not os.path.isfile(os.path.join(replay, "journal.jsonl")):
        raise ValueError("retained replay/journal.jsonl is missing; summary fallback is forbidden")
    plan, rows = grade.recover(replay)
    if not rows or any(type(row.get("request_index")) is not int or row["request_index"] != i
                       for i, row in enumerate(rows)):
        raise ValueError("recovered request indices must be contiguous integers")
    detailed_path = os.path.join(directory, "detailed.json")
    detailed = grade.read_json(detailed_path)
    digest = hashlib.sha256(b"".join(grade.encoded(row) for row in rows)).hexdigest()
    if digest != detailed["metadata"]["requests_sha256"]:
        raise ValueError("recovered journal differs from the retained evaluated requests")
    # Reuse the campaign's real source/hash/order checks. Only its output writer
    # is suppressed on this private module; no retained file is changed.
    grade.write_json = lambda path, value: None
    joined = grade.join(os.path.join(directory, "tasks.json"),
                        os.path.join(replay, "requests.jsonl"), detailed_path,
                        os.path.join(directory, "grade"), None)
    saved = grade.read_json(os.path.join(directory, "grade", "evaluation.json"))
    if not isinstance(saved.get("passed"), list) or any(type(v) is not bool for v in saved["passed"]):
        raise ValueError("retained evaluation mask must contain booleans, not integers")
    if saved != joined:
        raise ValueError("retained evaluation differs from rejoined EvalPlus results")
    passed = joined["passed"]
    if len(passed) != len(rows) or any(type(v) is not bool for v in passed):
        raise ValueError("invalid evaluation mask")
    for row in rows:
        if not row["error"] and not all(number(row.get(k)) for k in ("scheduled_ts", "first_token_ts", "end_ts")):
            raise ValueError("successful request timestamps must be finite numbers, not booleans")
    accepted = sum(bucket["accepted"] for bucket in grade.buckets(plan, rows, passed))
    return {"scheduled": len(rows), "completed": sum(not row["error"] for row in rows), "accepted": accepted}


def check_recomputation(cards):
    run = next((c for c in cards if c.get("id") == "run3-at0"), None)
    if not run:
        say("recomputation", "FAIL", "no run3-at0 card")
        return False
    r = q(run, "a_claim", "results", default={})
    try:
        counts = recompute_retained_run()
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        say("recomputation", "FAIL", f"retained-byte recomputation failed: {exc}; no summary fallback")
        return False
    ok = True
    for key, computed in counts.items():
        claimed = scalar(q(run, "b_population", key))
        matches = type(claimed) is int and claimed == computed
        ok = ok and matches
        say("recomputation", "PASS" if matches else "FAIL", f"{key} = {computed} from replay journal and rejoined retained EvalPlus results; card says {claimed!r}")
    accepted = counts["accepted"]
    for key in ("hotaisle_rate", "own_equivalent_duration", "own_seat_equivalent", "shared_cost", "actual_shared_seat"):
        value = scalar(r.get(key))
        if not number(value) or value <= 0:
            say("recomputation", "FAIL", f"results.{key} must be a finite positive number, not a boolean")
            return False
    shared_count = scalar(r.get("shared_accepted"))
    if type(shared_count) is not int or shared_count <= 0 or accepted <= 0:
        say("recomputation", "FAIL", "accepted denominators must be positive integers")
        return False
    # (ii) own-seat equivalent: rate x window / accepted
    own = round(r["hotaisle_rate"]["value"] * (r["own_equivalent_duration"]["value"] / 60) / (accepted / 1000), 2)
    if own != r["own_seat_equivalent"]["value"]:
        ok = False
    say("recomputation", "PASS" if own == r["own_seat_equivalent"]["value"] else "FAIL",
        f"$/1k own-seat = {r['hotaisle_rate']['value']} x {r['own_equivalent_duration']['value']}/60 / {accepted/1000} = {own} (card says {r['own_seat_equivalent']['value']}); duration and price are declared card inputs")
    # (iii) actual shared seat: shared cost / shared accepted
    shared = round(r["shared_cost"]["value"] / (r["shared_accepted"]["value"] / 1000), 2)
    if shared != r["actual_shared_seat"]["value"]:
        ok = False
    say("recomputation", "PASS" if shared == r["actual_shared_seat"]["value"] else "FAIL",
        f"$/1k shared seat = {r['shared_cost']['value']} / {r['shared_accepted']['value']/1000} = {shared} (card says {r['actual_shared_seat']['value']}); arithmetic from attributed shared totals, not a regrade of every shared arm")
    return ok


# 4 ─ refusals (controlled composition) --------------------------------------------
def unit_of(card, key):
    v = q(card, "a_claim", "results", key)
    return v.get("unit") if isinstance(v, dict) else None


def compose(a, b, purpose):
    """Return a scoped refusal, or None if this check found none (not admission)."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return "missing operand: both source cards are required"
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
        if da is None or db is None:
            return "comparable observation/publication period unknown; retrieval does not supply it (BRIEF2 item 3)"
        if da != db:
            return f"periods differ ({da} vs {db}); combine only with the period stated (BRIEF2 item 3)"
    return None


def check_refusals(cards):
    by = {c["id"]: c for c in cards}
    run, ix, cm, mc, ha = (by.get(k) for k in ("run3-at0", "inferencex-artifact", "clustermax-coreweave", "mercatus-index", "hotaisle-blog"))
    if any(c is None for c in (run, ix, cm, mc, ha)):
        say("refusal", "FAIL", "all five named cards are required to exercise the six refusal cases")
        return False
    cases = [
        ("run $/1k accepted vs Mercatus $/GPU-h as one unit", compose(run, mc, "cost_per_accepted")),
        ("InferenceX TTFT as accepted work", compose(run, ix, "accepted_work")),
        ("CoreWeave Platinum as a 1x self-serve seat property", compose(run, cm, "seat_property")),
        ("Hot Aisle blog $2.99 as a measured cost", compose(run, ha, "measured_cost")),
        ("Sep 24 run price with blog publication unknown, no period stated", compose(run, ha, "same_period")),
    ]
    ok = True
    for name, reason in cases:
        if reason:
            say("refusal", "REFUSED", f"{name}: {reason}")
        else:
            ok = False; say("refusal", "FAIL", f"{name}: was NOT refused")
    # retrieval date must not overwrite the experiment/publication date
    # same-day retrieval is fine; what is refused is a missing publication date filled from retrieval
    invalid = copy.deepcopy(cm)
    p = invalid["a_claim"]["period"]
    p["publication_date"] = str(p.get("retrieved_at", ""))[:10]
    p["publication_date_basis"] = None
    reasons = [error for error in validate_card(invalid) if "publication_date_basis" in error]
    if reasons:
        say("refusal", "REFUSED", "retrieval copied into publication without a dated-source basis: " + reasons[0])
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
    if "credit" not in payer.lower() or "hot aisle" not in payer.lower():
        ok = False; say("narrowing", "FAIL", "run card funding does not name the Hot Aisle credit")
    spine = run.get("spine", "").lower() if isinstance(run, dict) else ""
    if "credit" not in spine or "hot aisle" not in spine:
        ok = False; say("narrowing", "FAIL", "run card spine must disclose the Hot Aisle credit")
    if ok:
        say("narrowing", "PASS", "run card carries $0.74 (own-seat equivalent) and $0.90 (shared seat) with what each supports, and the credit on the spine")
    return ok


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default=os.path.join(HERE, "cards.jsonl"))
    parser.add_argument("--card", help="validate one JSON card; filing checks only, no benchmark acceptance")
    args = parser.parse_args(argv)
    REPORT.clear()
    try:
        if args.card:
            with open(args.card, encoding="utf-8-sig") as f:
                card = json.load(f)
            valid = check_representation([card])
            print("Single-card filing check only; source truth, recomputation and independent use are not established.")
            return 0 if valid else 1
        cards = load_cards(args.path)
    except (OSError, ValueError) as exc:
        say("input", "FAIL", str(exc))
        return 1
    results = []
    for check in (check_representation, check_propagation, check_recomputation, check_refusals, check_narrowing):
        try:
            results.append(check(cards))
        except (OSError, ValueError, KeyError, TypeError, IndexError, ZeroDivisionError) as exc:
            say(check.__name__.removeprefix("check_"), "FAIL", f"{type(exc).__name__}: {exc}")
            results.append(False)
    failed = results.count(False)
    print(f"\n{5 - failed}/5 machine checks pass; the model-stranger handoff is assessed separately. Independent human use remains untested.")
    return failed


if __name__ == "__main__":
    sys.exit(main())
