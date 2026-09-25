#!/usr/bin/env python3
"""Forge: drive a generated population of cards, faults, queries and compositions
through the shelf's algebra, in both engines, and keep only what fails. Stdlib only.

  python forge.py --scale small            # CI: seconds
  python forge.py --scale full --record    # 10k valid / 100k one-fault / 1m pairs; writes ../FORGE-VERIFICATION.json
  python forge.py --seed 7 --scale small --json

Everything is derived from one seed and GENERATOR_VERSION. A failure is reported
with its regime, seed, case index, the minimized counterexample and the invariant
it broke. Nothing here is stored except the seed and the failures.

Invariants (the ten in the record):
  VALIDITY        every generated valid card validates, in Python and in the browser engine
  LOCALITY        a one-field mutation changes only the `which` consequences that field governs
  REFUSAL         every boundary fault flips `which` to CANNOT_USE naming the crossed variable;
                  every illegal filing fails `validate` with the named rule;
                  every illegal composition is refused with its rule
  NON-TRANSFER    pulling identical bytes from any number of hubs leaves every copy
                  imported/candidate and never writes the shelf
  IDENTITY        a staged import's cards.jsonl must be the canonical rendering of its
                  source.bytes; an edited staged card is caught
  PARITY          Python and the embedded browser engine produce byte-identical canonical
                  output for every validate, which and compose case
  MONOTONICITY    adding evidence (a flag null->true, a check, a known date) never removes
                  support; nothing else can add it
  PROVENANCE      funding, access and observer-benefit edits never change measured values
                  or `which` results
  SUCCESSION      not implemented on this surface (promotions only); recorded as untested
  QUERY SOUNDNESS every SUPPORTS row has a result in exactly the asked unit, is measured
                  when required, and has a known observation date inside the period
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
import platform
import random
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
GENERATOR_VERSION = "1"
spec = importlib.util.spec_from_file_location("shelf", os.path.join(HERE, "shelf.py"))
shelf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shelf)

SCALES = {
    "small": {"valid": 300, "faults": 3000, "pairs": 20000, "queries": 40, "hubs": 3, "genesis": 8},
    "medium": {"valid": 2000, "faults": 20000, "pairs": 200000, "queries": 80, "hubs": 5, "genesis": 40},
    "full": {"valid": 10000, "faults": 100000, "pairs": 1000000, "queries": 120, "hubs": 8, "genesis": 120},
}
UNITS = ["USD / 1000 accepted requests", "USD / GPU-hour", "USD / seat-hour", "milliseconds", "requests", "percent utilized"]
PROVIDERS = ["Hot Aisle", "DigitalOcean", "Voltage Park", "Latitude.sh", "Nebius", "RunPod", "CoreWeave", "Lambda", "Crusoe", "Scaleway"]
HARDWARE = ["MI300X", "H100", "H200", "B200", "MI325X", "L40S", "A100"]
WHO = ["Astra, shelf chair", "Codex parent", "a Haiku stranger", "gpt-6-luna", "the operator", "an outside reviewer"]


# -- canonical output shared with the browser harness ----------------------
def canon(value):
    def fix(v):
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        if isinstance(v, list):
            return [fix(x) for x in v]
        return v
    return json.dumps(fix(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(items):
    h = hashlib.sha256()
    for s in items:
        h.update(s.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


# -- archetype grammar -------------------------------------------------------
def iso(rng, start=dt.date(2025, 6, 1), span=600):
    return (start + dt.timedelta(days=rng.randrange(span))).isoformat()


def valued(v, unit, rng, supports=None):
    return {"value": v, "unit": unit, "source": rng.choice(["https://example.org/src", "retained/results.md", "provider page"]),
            "source_date": rng.choice([None, iso(rng)]), **({"supports": supports} if supports else {})}


def parties(rng, funded=None):
    interested = rng.random() < 0.4
    benefit_known = rng.random() < 0.6
    ob = {"benefits_from_outcome": (interested if benefit_known else None),
          "relationship": rng.choice([None, "sales prospect", "credit-funded", "provider speaking about itself", "no relationship stated"]),
          "basis": ("disclosed by the filer" if benefit_known else rng.choice([None, "unstated"]))}
    if ob["benefits_from_outcome"] is not None and not ob["basis"]:
        ob["basis"] = "disclosed by the filer"
    return {"observer": rng.choice(["the filer", "provider page", "outside benchmark"]),
            "conditions_controller": rng.choice([None, "provider", "the filer"]),
            "access": {"provider": rng.choice(PROVIDERS), "mode": rng.choice(["self-serve VM", "public page", "managed"]), "account_class": None},
            "funding": rng.choice([None, {"payer": "the filer", "relationship": "cash at list price"},
                                   {"payer": "provider credit", "relationship": "credit-funded; sales prospect"}]) if funded is None else funded,
            "observer_benefit": ob}


def checks(rng, strength=None):
    s = rng.random() if strength is None else strength
    out = {}
    for i, k in enumerate(shelf.CHECKS):
        done = s > (0.3 + 0.25 * i)
        out[k] = {"who": rng.choice(WHO) if done else None, "when": iso(rng) if done and rng.random() < 0.8 else None, "scope": None}
    return out


def base_card(rng, cid, archetype):
    """Valid card of one archetype. Periods carry an observation date unless archetype says unknown."""
    period = {"publication_date": None, "publication_date_basis": None, "retrieved_at": rng.choice([None, iso(rng) + "T12:00:00Z"])}
    dims = {"measured": None, "imported": None, "modeled": None, "attributed": None}
    conditions = {"provider": rng.choice(PROVIDERS), "hardware": rng.choice(HARDWARE),
                  "gpus": {"value": rng.choice([1, 1, 1, 8]), "unit": "GPU", "source": "env.json", "source_date": None}}
    results, limits, b = {}, [], {"population": None, "denominator": None, "acceptance_rule": None, "exclusions": None}
    if archetype == "measured-run":
        period["experiment_date"] = iso(rng)
        dims.update(measured=True, imported=False, modeled=rng.choice([True, False]), attributed=False)
        acc = rng.randrange(500, 9000)
        results["cost_per_accepted"] = valued(round(rng.uniform(0.2, 5.0), 2), UNITS[0], rng, "conditional comparison under the stated accounting")
        results["rate"] = valued(round(rng.uniform(0.9, 6.0), 2), UNITS[1], rng)
        results["accepted"] = valued(acc, "requests", rng)
        b.update(population="cycled tasks under trace replay", scheduled=valued(acc + rng.randrange(0, 4000), "requests", rng), accepted=valued(acc, "requests", rng),
                 acceptance_rule="tests pass; TTFT within 1 s; done within 60 s")
        limits = ["No repeated run per arm."] + rng.sample(["Invoices unreconciled.", "No claim that cheaper offers preserve the ranking.", "Single configuration."], rng.randrange(0, 3))
    elif archetype == "price-observation":
        period["experiment_date"] = None
        if rng.random() < 0.5:
            period["publication_date"] = iso(rng); period["publication_date_basis"] = "page displays the date; inspected"
        dims.update(measured=None, imported=True, modeled=False, attributed=True)
        unit = UNITS[2] if rng.random() < 0.25 else UNITS[1]
        results["starting_price"] = valued(round(rng.uniform(0.9, 6.0), 2), unit, rng, "a stated starting price, not an obtainable seat")
        b.update(population="pricing statement for one product")
    elif archetype == "index":
        period["index_date"] = iso(rng)
        dims.update(measured=None, imported=True, modeled=True, attributed=True)
        results["h100"] = valued(round(rng.uniform(2.0, 5.0), 2), UNITS[1], rng)
        results["mi300x"] = valued(round(rng.uniform(2.0, 5.0), 2), UNITS[1], rng)
        b.update(population="volume-weighted on-demand index", weights="withheld")
    elif archetype == "latency-artifact":
        period["artifact_created_at"] = iso(rng) + "T19:49:39Z"
        dims.update(measured=True, imported=True, modeled=False, attributed=True)
        results["mean_ttft"] = valued(round(rng.uniform(80, 9000), 2), UNITS[3], rng)
        b.update(population="profiled requests", total=valued(rng.randrange(100, 5000), "requests", rng))
    elif archetype == "rating":
        period["publication_date"] = iso(rng); period["publication_date_basis"] = "report heading displays the date"
        dims.update(measured=None, imported=True, modeled=None, attributed=True)
        results["medal"] = rng.choice(["Platinum", "Gold", "Silver"])  # a bare string, as the real ClusterMAX card files it
        b.update(population="managed clusters reviewed", denominator_limit="withheld")
    elif archetype == "self-statement":
        period["experiment_date"] = None
        period["reported_publication_date"] = iso(rng); period["reported_publication_date_basis"] = "user task specification"
        dims.update(measured=None, imported=True, modeled=False, attributed=True)
        results["new_rate"] = valued(round(rng.uniform(1.0, 4.0), 2), UNITS[1], rng)
        results["claimed_capacity"] = valued(rng.randrange(50, 100), UNITS[5], rng)
        results["queue"] = {"value": None, "unit": "customers waiting; count unknown", "source": "blog", "source_date": None}
    else:
        raise ValueError(archetype)
    card = {"id": cid, "title": f"{archetype} {cid}", "spine": f"{archetype} | generated | seed-derived", "dimensions": dims,
            "a_claim": {"statement": f"A generated {archetype} claim.", "period": period, "conditions": conditions, "results": results,
                        "limits": limits, "does_not_establish": rng.choice([None, "anything beyond the stated conditions"])},
            "b_population": b, "c_parties": parties(rng), "d_materials": {"sources": [], "obtainable": rng.choice([None, "the cited page"]), "procedure": None, "missing": []},
            "e_checks": checks(rng), "filing_version": 2}
    card["archetype"] = archetype
    return card


ARCHETYPES = ["measured-run", "price-observation", "index", "latency-artifact", "rating", "self-statement"]


def real_cards():
    return shelf.read_cards(os.path.join(TOOL, "data", "cards.jsonl"))


def gen_valid(rng, n):
    cards = []
    for i in range(n):
        cards.append(base_card(rng, f"gen-{i:06d}", ARCHETYPES[i % len(ARCHETYPES)]))
    return cards


def gen_queries(rng, n):
    qs = []
    for i in range(n):
        unit = UNITS[i % len(UNITS)]
        form = rng.choice(["none", "year", "month", "day", "range"])
        d = dt.date(2025, 6, 1) + dt.timedelta(days=rng.randrange(600))
        period = {"none": None, "year": d.isoformat()[:4], "month": d.isoformat()[:7], "day": d.isoformat(),
                  "range": f"{d.isoformat()}..{(d + dt.timedelta(days=rng.randrange(1, 120))).isoformat()}"}[form]
        qs.append({"unit": unit, "period": period, "measured": rng.random() < 0.5})
    return qs


# -- one-fault mutators ------------------------------------------------------
# Each returns (mutated_card, regime, expectation). Regimes:
#   benign    : which output unchanged except the named allowed keys (LOCALITY/PROVENANCE)
#   boundary  : for a query the card supported, which flips to CANNOT_USE with reason containing `needle` (REFUSAL)
#   illegal   : validate must fail and some error must contain `needle` (REFUSAL, hostile-but-plausible filings)
def first_result(card):
    return next((k for k, v in card["a_claim"]["results"].items() if isinstance(v, dict)), None)


def m_retrieved(c, rng):  c["a_claim"]["period"]["retrieved_at"] = iso(rng) + "T00:00:00Z"; return "benign", {"allowed": set()}
def m_funding(c, rng):    c["c_parties"]["funding"] = {"payer": rng.choice(["provider credit", "the filer", "a grant"]), "relationship": "changed"}; return "benign", {"allowed": set()}
def m_observer(c, rng):   c["c_parties"]["observer_benefit"] = {"benefits_from_outcome": rng.choice([True, False]), "relationship": "changed", "basis": "disclosed"}; return "benign", {"allowed": set()}
def m_access(c, rng):     c["c_parties"]["access"] = {"provider": rng.choice(PROVIDERS), "mode": "changed", "account_class": "new"}; return "benign", {"allowed": set()}
def m_title(c, rng):      c["title"] = "renamed"; c["spine"] = "respun"; return "benign", {"allowed": set()}
def m_obtainable(c, rng): c["d_materials"]["obtainable"] = "changed"; c["d_materials"]["missing"] = ["x"]; return "benign", {"allowed": set()}
def m_limit(c, rng):      c["a_claim"]["limits"] = list(c["a_claim"].get("limits") or []) + ["An added limit."]; return "benign", {"allowed": {"limits"}}
def m_check(c, rng):      c["e_checks"]["repeated"] = {"who": rng.choice(WHO), "when": iso(rng), "scope": None}; return "benign", {"allowed": {"checks", "how_far"}}
def m_value(c, rng):
    k = first_result(c)
    if k is None:
        return None
    r = c["a_claim"]["results"][k]
    if not isinstance(r.get("value"), (int, float)) or isinstance(r["value"], bool):
        return None
    r["value"] = round(r["value"] * rng.choice([0.5, 1.5, 2.0]) + 0.01, 2)
    return "benign", {"allowed": {"results"}, "results_key": k}


def m_unit_swap(c, rng):
    k = first_result(c)
    if k is None:
        return None
    unit = c["a_claim"]["results"][k].get("unit")
    other = [u for u in UNITS if u != unit and u not in (UNITS[2],)]
    new_unit = rng.choice(other)
    for r in c["a_claim"]["results"].values():  # every result in that unit moves, so no sibling keeps the match
        if isinstance(r, dict) and r.get("unit") == unit:
            r["unit"] = new_unit
    return "boundary", {"needle": "INVARIANTS 1/4", "variable": "unit"}


def m_unmeasure(c, rng):
    if c["dimensions"]["measured"] is not True:
        return None
    c["dimensions"]["measured"] = rng.choice([None, False]); return "boundary", {"needle": "INVARIANTS 3/5", "variable": "measured", "requires_measured": True}


def m_date_shift(c, rng):
    p = c["a_claim"]["period"]
    for k in shelf.DATE_KEYS:
        if isinstance(p.get(k), str):
            p[k] = (dt.date.fromisoformat(p[k][:10]) + dt.timedelta(days=rng.choice([-400, 400, 800]))).isoformat() + p[k][10:]
            return "boundary", {"needle": "BRIEF2 item 3", "variable": "period", "requires_period": True}
    return None


def m_date_unknown(c, rng):
    p = c["a_claim"]["period"]; hit = False
    for k in shelf.DATE_KEYS:
        if p.get(k) is not None:
            p[k] = None; hit = True
    if "publication_date_basis" in p:
        p["publication_date_basis"] = None
    return ("boundary", {"needle": "BRIEF2 item 3", "variable": "period", "requires_period": True}) if hit else None


def m_int_flag(c, rng):     c["dimensions"]["measured"] = 1; return "illegal", {"needle": "not integers"}
def m_drop_ob(c, rng):      del c["c_parties"]["observer_benefit"]; return "illegal", {"needle": "observer_benefit"}
def m_ob_no_basis(c, rng):  c["c_parties"]["observer_benefit"] = {"benefits_from_outcome": True, "relationship": "sales prospect", "basis": None}; return "illegal", {"needle": "needs a basis"}
def m_pub_no_basis(c, rng): c["a_claim"]["period"]["publication_date"] = iso(rng); c["a_claim"]["period"]["publication_date_basis"] = None; return "illegal", {"needle": "publication_date_basis"}
def m_retrieval_as_pub(c, rng):
    p = c["a_claim"]["period"]; p["retrieved_at"] = iso(rng) + "T09:00:00Z"; p["publication_date"] = p["retrieved_at"][:10]; p["publication_date_basis"] = None
    return "illegal", {"needle": "retrieval is not publication evidence"}
def m_usd_hour(c, rng):
    k = first_result(c)
    if k is None:
        return None
    c["a_claim"]["results"][k]["unit"] = rng.choice(["USD/hour", "USD/h", "usd per hr", "USD / hr", "USD/GPU-h"]); return "illegal", {"needle": "USD/GPU-hour or USD/seat-hour"}
def m_seat_no_gpus(c, rng):
    k = first_result(c)
    if k is None:
        return None
    r = c["a_claim"]["results"][k]
    if not isinstance(r.get("value"), (int, float)):
        r["value"] = 2.5
    r["unit"] = "USD / seat-hour"; c["a_claim"]["conditions"]["gpus"] = {"value": None, "unit": "GPU", "source": None, "source_date": None}
    return "illegal", {"needle": "conditions.gpus"}
def m_bad_id(c, rng):       c["id"] = rng.choice(["Run 3!", "UPPER", "", "x" * 70]); return "illegal", {"needle": "slug"}
def m_empty_who(c, rng):    c["e_checks"]["inspected"] = {"who": "", "when": None}; return "illegal", {"needle": "who/when"}
def m_drop_funding(c, rng): del c["c_parties"]["funding"]; return "illegal", {"needle": "funding"}
def m_bool_value(c, rng):
    k = first_result(c)
    if k is None:
        return None
    r = c["a_claim"]["results"][k]
    if shelf.normalized_unit(r.get("unit")) not in ("usd/gpu-hour", "usd/seat-hour"):
        r["unit"] = "USD / GPU-hour"
    r["value"] = True; return "illegal", {"needle": "not a boolean"}


MUTATORS = [m_retrieved, m_funding, m_observer, m_access, m_title, m_obtainable, m_limit, m_check, m_value,
            m_unit_swap, m_unmeasure, m_date_shift, m_date_unknown,
            m_int_flag, m_drop_ob, m_ob_no_basis, m_pub_no_basis, m_retrieval_as_pub, m_usd_hour, m_seat_no_gpus, m_bad_id, m_empty_who, m_drop_funding, m_bool_value]


def supporting_query(card):
    """A query this card supports, or None."""
    for k, r in card["a_claim"]["results"].items():
        unit = r.get("unit") if isinstance(r, dict) else None
        if not unit:
            continue
        date = shelf.observation_date(card)
        q = {"unit": unit, "period": date[:7] if date else None, "measured": card["dimensions"]["measured"] is True}
        if shelf.which([card], **q)[0]["status"] == "SUPPORTS":
            return q
    return None


def gen_faults(rng, valid, n):
    faults = []
    i = 0
    while len(faults) < n:
        base = valid[i % len(valid)]; mut = MUTATORS[(i // len(valid) + i) % len(MUTATORS)]; i += 1
        c = copy.deepcopy(base); c.pop("archetype", None)
        out = mut(c, rng)
        if out is None:
            continue
        regime, exp = out
        faults.append({"base": base["id"], "mutator": mut.__name__, "regime": regime, "exp": exp, "card": c})
    return faults


# -- invariant checks --------------------------------------------------------
class Failures(list):
    def add(self, invariant, regime, index, detail, counterexample):
        self.append({"invariant": invariant, "regime": regime, "index": index, "detail": detail, "counterexample": counterexample})


def strip(card):
    c = copy.deepcopy(card); c.pop("archetype", None); return c


def which_view(card, q):
    row = shelf.which([card], q["unit"], q["period"], q["measured"])[0]
    return row


def check_validity(valid, F):
    for i, c in enumerate(valid):
        errs = shelf.validate_card(strip(c))
        if errs:
            F.add("VALIDITY", "valid", i, errs, strip(c))


def check_locality_and_refusal(valid, faults, F):
    by = {c["id"]: c for c in valid}
    for i, f in enumerate(faults):
        base = strip(by[f["base"]]); c = f["card"]; exp = f["exp"]
        if f["regime"] == "illegal":
            errs = shelf.validate_card(c)
            if not errs or not any(exp["needle"] in e for e in errs):
                F.add("REFUSAL", "illegal", i, {"mutator": f["mutator"], "expected": exp["needle"], "errors": errs}, c)
            continue
        if shelf.validate_card(c):
            F.add("VALIDITY", f["regime"], i, {"mutator": f["mutator"], "errors": shelf.validate_card(c)}, c)
            continue
        q = supporting_query(base)
        if q is None:
            continue
        if f["regime"] == "benign":
            a, b = which_view(base, q), which_view(c, q)
            changed = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
            if changed - exp["allowed"] - {"id"}:
                inv = "PROVENANCE" if f["mutator"] in ("m_funding", "m_observer", "m_access") else "LOCALITY"
                F.add(inv, "benign", i, {"mutator": f["mutator"], "changed": sorted(changed), "allowed": sorted(exp["allowed"])}, {"base": base, "mutated": c, "query": q})
            if f["mutator"] == "m_value" and b["status"] == "SUPPORTS":
                k = exp["results_key"]
                other_a = {kk: v for kk, v in a["results"].items() if kk != k}; other_b = {kk: v for kk, v in b["results"].items() if kk != k}
                if other_a != other_b or c["b_population"] != base["b_population"]:
                    F.add("LOCALITY", "benign", i, {"mutator": "m_value", "detail": "a price change moved something other than its own value"}, {"base": base, "mutated": c})
        elif f["regime"] == "boundary":
            qq = dict(q)
            if exp.get("requires_measured"):
                qq["measured"] = True
            if exp.get("requires_period") and qq["period"] is None:
                continue
            if which_view(base, qq)["status"] != "SUPPORTS":
                continue
            row = which_view(c, qq)
            if row["status"] != "CANNOT_USE" or exp["needle"] not in row["reason"]:
                F.add("REFUSAL", "boundary", i, {"mutator": f["mutator"], "expected": exp["needle"], "got": row}, {"base": base, "mutated": c, "query": qq})


def check_soundness(valid, queries, F):
    cards = [strip(c) for c in valid]
    for qi, q in enumerate(queries):
        for row in shelf.which(cards, q["unit"], q["period"], q["measured"]):
            if row["status"] != "SUPPORTS":
                continue
            card = next(c for c in cards if c["id"] == row["id"])
            units = {shelf.normalized_unit(v.get("unit")) for v in card["a_claim"]["results"].values() if isinstance(v, dict)}
            ok = shelf.normalized_unit(q["unit"]) in units
            ok = ok and (not q["measured"] or card["dimensions"]["measured"] is True)
            d = shelf.observation_date(card)
            ok = ok and (q["period"] is None or (d is not None and shelf.in_period(d, q["period"])))
            ok = ok and all(shelf.normalized_unit(v["unit"]) == shelf.normalized_unit(q["unit"]) for v in row["results"].values())
            if not ok:
                F.add("QUERY SOUNDNESS", "query", qi, {"query": q, "row": row}, card)


def check_monotonicity(valid, queries, F):
    """Adding evidence never removes support; removing it never adds support."""
    for i, c0 in enumerate(valid[: max(50, len(valid) // 10)]):
        c = strip(c0); q = queries[i % len(queries)]
        before = which_view(c, q)["status"]
        up = copy.deepcopy(c)
        for k in shelf.DIMS:
            if up["dimensions"][k] is None:
                up["dimensions"][k] = True
        for k in shelf.CHECKS:
            if not up["e_checks"][k]["who"]:
                up["e_checks"][k] = {"who": "a named reviewer", "when": "2026-09-24"}
        if shelf.observation_date(up) is None and q["period"]:
            up["a_claim"]["period"]["experiment_date"] = (q["period"].split("..")[0] + "-01-01")[:10] if len(q["period"]) == 4 else (q["period"].split("..")[0] + "-01")[:10]
        after = which_view(up, q)["status"]
        if before == "SUPPORTS" and after != "SUPPORTS":
            F.add("MONOTONICITY", "monotone", i, {"query": q, "before": before, "after": after}, {"card": c, "stronger": up})
        down = copy.deepcopy(c)
        down["dimensions"]["measured"] = None
        for k in shelf.CHECKS:
            down["e_checks"][k] = {"who": None, "when": None}
        after_down = which_view(down, q)["status"]
        if before != "SUPPORTS" and after_down == "SUPPORTS":
            F.add("MONOTONICITY", "monotone", i, {"query": q, "before": before, "after_weaker": after_down}, {"card": c, "weaker": down})


def gen_pairs(rng, valid, n):
    m = len(valid)
    for i in range(n):
        yield (rng.randrange(m), rng.randrange(m), shelf.PURPOSES[i % len(shelf.PURPOSES)])


def check_compositions(valid, pairs, F):
    cards = [strip(c) for c in valid]
    outs = []
    for i, (a, b, p) in enumerate(pairs):
        ca, cb = cards[a], cards[b]
        r = shelf.compose(ca, cb, p)
        outs.append(canon(r))
        def accepted(card):
            return any(shelf.normalized_unit(v.get("unit")) in ("usd/1000acceptedrequests", "acceptedrequests")
                       and shelf.number(v.get("value")) and v["value"] >= 0
                       for v in card["a_claim"]["results"].values() if isinstance(v, dict))
        must_refuse = None
        if shelf.validate_card(ca) or shelf.validate_card(cb): must_refuse = "invalid filing"
        elif p == "cost_per_accepted" and not (accepted(ca) and accepted(cb)): must_refuse = "INVARIANTS 1"
        elif p == "accepted_work" and not accepted(cb): must_refuse = "INVARIANTS 4"
        elif p in ("seat_property", "measured_cost") and cb["dimensions"]["measured"] is not True: must_refuse = "INVARIANTS"
        elif p == "same_period":
            da, db = shelf.observation_date(ca), shelf.observation_date(cb)
            if da is None or db is None or da != db: must_refuse = "BRIEF2 item 3"
        if must_refuse and (r is None or must_refuse not in r):
            F.add("REFUSAL", "composition", i, {"purpose": p, "expected_rule": must_refuse, "got": r}, {"a": ca, "b": cb})
        if not must_refuse and r is not None:
            F.add("REFUSAL", "composition", i, {"purpose": p, "detail": "refused a composition no rule forbids", "got": r}, {"a": ca, "b": cb})
    return outs


def check_federation(valid, hubs, F, rng):
    """NON-TRANSFER and IDENTITY over real pull() calls and the staging/promotion checker."""
    sample = [strip(c) for c in valid if c.get("archetype") != "real"][:25]  # real cards are already on the shelf
    quiet = lambda *a: None
    cs = load_check_staging()
    with tempfile.TemporaryDirectory() as tmp:
        staging = os.path.join(tmp, "staging"); promos = os.path.join(tmp, "promotions.jsonl")
        src = os.path.join(tmp, "cards.jsonl")
        with open(src, "w", encoding="utf-8", newline="\n") as f:
            for c in sample:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        before = open(shelf.CARDS, "rb").read()
        shas, folders = set(), []
        for h in range(hubs):
            folder, prov = shelf.pull(src, f"hub-{h}", staging=staging, now=dt.datetime(2026, 9, 25, 0, 0, h, tzinfo=dt.timezone.utc))
            shas.add(prov["sha256"]); folders.append(folder)
            if prov["standing"] != "imported/candidate" or prov["cards"] != len(sample):
                F.add("NON-TRANSFER", "federation", h, prov, {"hub": h})
            for fl in prov["filings"]:
                if fl["errors"]:
                    F.add("NON-TRANSFER", "federation", h, {"detail": "a valid card failed the filing check on import", "filing": fl}, {"hub": h})
        if len(shas) != 1:
            F.add("IDENTITY", "federation", 0, {"detail": "identical bytes hashed differently across hubs", "shas": sorted(shas)}, {})
        if open(shelf.CARDS, "rb").read() != before:
            F.add("NON-TRANSFER", "federation", 0, {"detail": "pull wrote to the shelf"}, {})
        if cs.main_for(staging, shelf.CARDS, promos, say=quiet) != 0:
            F.add("IDENTITY", "federation", 0, {"detail": "clean staging failed check_staging"}, {})
        # NON-TRANSFER: a staged card copied onto the shelf needs one valid promotion; forged ones are refused
        fake_shelf = os.path.join(tmp, "fake-cards.jsonl")
        open(fake_shelf, "w", encoding="utf-8", newline="\n").write(before.decode("utf-8").rstrip("\n") + "\n" + json.dumps(sample[1], ensure_ascii=False, sort_keys=True) + "\n")
        hub1 = os.path.relpath(folders[1], staging).replace(os.sep, "/")
        sha1 = json.load(open(os.path.join(folders[1], "provenance.json"), encoding="utf-8"))["sha256"]
        good = {"id": sample[1]["id"], "from": hub1, "sha256": sha1, "who": "forge", "when": "2026-09-25T00:00:00Z", "why": "forge test admission for this captured input only"}
        cases = [("unrecorded", None), ("wrong sha", dict(good, sha256="f" * 64)), ("wrong capture", dict(good, **{"from": "nowhere/20260101T000000Z"})),
                 ("blank who", dict(good, who=" ")), ("bad when", dict(good, when="yesterday")), ("other id", dict(good, id="someone-else")), ("id only", {"id": good["id"]})]
        for label, rec in cases:
            open(promos, "w", encoding="utf-8", newline="\n").write("" if rec is None else json.dumps(rec) + "\n")
            if cs.main_for(staging, fake_shelf, promos, say=quiet) == 0:
                F.add("NON-TRANSFER", "federation", 1, {"detail": f"promotion case '{label}' was accepted"}, {"card": sample[1]["id"], "record": rec})
        open(promos, "w", encoding="utf-8", newline="\n").write(json.dumps(good) + "\n")
        if cs.main_for(staging, fake_shelf, promos, say=quiet) != 0:
            F.add("NON-TRANSFER", "federation", 1, {"detail": "a complete, matching promotion record was refused"}, {"record": good})
        # IDENTITY: an edited staged card must be caught
        open(promos, "w").close()
        victim = os.path.join(folders[0], "cards.jsonl")
        rows = open(victim, encoding="utf-8").read().splitlines()
        edited = json.loads(rows[0]); k = first_result(edited)
        if k:
            edited["a_claim"]["results"][k]["value"] = 0.01
        else:
            edited["title"] = "edited"
        rows[0] = json.dumps(edited, ensure_ascii=False, sort_keys=True)
        open(victim, "w", encoding="utf-8", newline="\n").write("\n".join(rows) + "\n")
        if cs.main_for(staging, shelf.CARDS, promos, say=quiet) == 0:
            F.add("IDENTITY", "federation", 0, {"detail": "an edited staged card passed check_staging"}, {"file": "cards.jsonl"})


def load_check_staging():
    s = importlib.util.spec_from_file_location("check_staging", os.path.join(HERE, "check_staging.py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


# -- differential harness (PARITY) -------------------------------------------
def node_run(doc):
    node = os.environ.get("NODE", "node")
    p = subprocess.run([node, os.path.join(TOOL, "tests", "differential.cjs")], input=json.dumps(doc, ensure_ascii=False).encode("utf-8"),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:2000])
    return json.loads(p.stdout.decode("utf-8"))


def check_parity(valid, faults, queries, pairs, compose_outs, F, chunk=2000):
    cards = [strip(c) for c in valid] + [f["card"] for f in faults]
    py_validate = [canon(shelf.validate_card(c)) for c in cards]
    py_which = [canon(shelf.which(cards[: min(len(cards), 400)], q["unit"], q["period"], q["measured"])) for q in queries]
    sections = {"validate": py_validate, "which": py_which, "compose": compose_outs}
    py_digests = {k: [digest(v[i:i + chunk]) for i in range(0, len(v), chunk)] for k, v in sections.items()}
    doc = {"cards": cards, "queries": queries, "which_n": min(len(cards), 400), "pairs": [list(p) for p in pairs], "chunk": chunk, "verbose": False}
    js = node_run(doc)
    for k in sections:
        if js["digests"][k] != py_digests[k]:
            bad = [i for i, (a, b) in enumerate(zip(js["digests"][k], py_digests[k])) if a != b] or [min(len(js["digests"][k]), len(py_digests[k]))]
            ci = bad[0]
            sub = {"cards": cards, "queries": queries, "which_n": doc["which_n"], "pairs": doc["pairs"], "chunk": chunk, "verbose": True, "only": {"section": k, "chunk": ci}}
            raw = node_run(sub)["items"]
            mine = sections[k][ci * chunk:(ci + 1) * chunk]
            for j, (a, b) in enumerate(zip(mine, raw)):
                if a != b:
                    idx = ci * chunk + j
                    ce = {"validate": lambda: cards[idx], "which": lambda: queries[idx], "compose": lambda: {"pair": doc["pairs"][idx], "a": cards[doc["pairs"][idx][0]], "b": cards[doc["pairs"][idx][1]]}}[k]()
                    F.add("PARITY", k, idx, {"python": a[:500], "browser": b[:500]}, ce)
                    break
            else:
                F.add("PARITY", k, ci * chunk, {"detail": "chunk length differs", "python": len(mine), "browser": len(raw)}, {})
    return {k: len(v) for k, v in sections.items()}


# -- shrinking ---------------------------------------------------------------
def shrink_card(card, still_fails):
    """ddmin over optional structure: drop result keys, condition keys, limits, sources while the failure persists."""
    c = copy.deepcopy(card)
    for path in (("a_claim", "results"), ("a_claim", "conditions"), ("b_population",), ("d_materials",)):
        node = c
        for k in path:
            node = node.get(k, {}) if isinstance(node, dict) else {}
        if not isinstance(node, dict):
            continue
        for key in list(node.keys()):
            trial = copy.deepcopy(c)
            t = trial
            for k in path:
                t = t[k]
            if len(t) <= 1:
                break
            del t[key]
            if still_fails(trial):
                c = trial
    if c["a_claim"].get("limits"):
        trial = copy.deepcopy(c); trial["a_claim"]["limits"] = []
        if still_fails(trial):
            c = trial
    return c


def shrink_failures(F):
    for f in F:
        ce = f["counterexample"]
        if f["invariant"] == "VALIDITY" and isinstance(ce, dict) and "a_claim" in ce:
            f["minimized"] = shrink_card(ce, lambda c: bool(shelf.validate_card(c)))
        elif f["invariant"] == "REFUSAL" and f["regime"] == "boundary":
            q = ce["query"]; needle = f["detail"]["expected"]
            def fails(c, q=q, needle=needle):
                r = shelf.which([c], q["unit"], q["period"], q["measured"])[0]
                return not (r["status"] == "CANNOT_USE" and needle in r["reason"])
            f["minimized"] = shrink_card(ce["mutated"], fails)


# -- main --------------------------------------------------------------------
def run(seed, scale, record=False, quiet=False, genesis=None):
    t0 = time.time(); rng = random.Random(seed); S = SCALES[scale]
    F = Failures()
    real = real_cards()
    valid = real + gen_valid(rng, S["valid"] - len(real))
    for c in real:
        c["archetype"] = "real"
    queries = gen_queries(rng, S["queries"])
    faults = gen_faults(rng, valid, S["faults"])
    pairs = list(gen_pairs(rng, valid, S["pairs"]))
    say = (lambda *a: None) if quiet else (lambda *a: print(*a, flush=True))
    say(f"forge seed={seed} scale={scale} generator={GENERATOR_VERSION}: {len(valid)} valid, {len(faults)} one-fault, {len(queries)} queries, {len(pairs)} pairs")
    check_validity(valid, F); say("  VALIDITY", len(F))
    check_locality_and_refusal(valid, faults, F); say("  LOCALITY / PROVENANCE / REFUSAL(faults)", len(F))
    check_soundness(valid, queries, F); say("  QUERY SOUNDNESS", len(F))
    check_monotonicity(valid, queries, F); say("  MONOTONICITY", len(F))
    compose_outs = check_compositions(valid, pairs, F); say("  REFUSAL(compositions)", len(F))
    check_federation(valid, S["hubs"], F, rng); say("  NON-TRANSFER / IDENTITY", len(F))
    parity_counts = check_parity(valid, faults, queries, pairs, compose_outs, F); say("  PARITY", len(F), parity_counts)
    genesis_stats = None
    if genesis:
        gspec = importlib.util.spec_from_file_location("forge_genesis", os.path.join(HERE, "forge_genesis.py"))
        fgen = importlib.util.module_from_spec(gspec); gspec.loader.exec_module(fgen)
        genesis_stats = fgen.check_genesis(valid, genesis, S["genesis"], F, rng, strip); say("  GENESIS bind / non-transfer / identity / succession", len(F), genesis_stats)
    shrink_failures(F)
    regimes = {}
    for f in faults:
        regimes[f["regime"]] = regimes.get(f["regime"], 0) + 1
    rec = {"generator_version": GENERATOR_VERSION, "seed": seed, "scale": scale, "counts": {"valid": len(valid), "one_fault": len(faults), "fault_regimes": regimes,
           "queries": len(queries), "pairs": len(pairs), "hubs": S["hubs"], "parity_cases": parity_counts, "mutators": len(MUTATORS), "archetypes": ARCHETYPES + ["real"]},
           "invariants": {"VALIDITY": "checked", "LOCALITY": "checked", "REFUSAL": "checked", "NON-TRANSFER": "checked", "IDENTITY": "checked", "PARITY": "checked",
                          "MONOTONICITY": "checked", "PROVENANCE": "checked", "SUCCESSION": ("checked through native Genesis lineage (supersedes + lineage@1)" if genesis else "shelf surface has promotions only; run with --genesis to check succession through the kernel"), "QUERY SOUNDNESS": "checked"},
           "genesis": genesis_stats,
           "failures": len(F), "failure_records": F[:50], "elapsed_s": round(time.time() - t0, 1),
           "python": platform.python_version(), "node": node_version(), "shelf_sha256": sha_file(os.path.join(HERE, "shelf.py")), "engine_sha256": engine_sha(),
           "cards_sha256": sha_file(shelf.CARDS), "run_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "scope": "Generated cards are synthetic and seed-derived; the five real cards are included unchanged. Passing establishes that the implemented algebra keeps these invariants over this population. It does not establish source truth, human usability, or standing."}
    if record:
        out = os.path.join(TOOL, "FORGE-VERIFICATION.json")
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(rec, f, indent=2, ensure_ascii=False); f.write("\n")
        say("recorded", out)
    return rec


def node_version():
    try:
        return subprocess.run([os.environ.get("NODE", "node"), "--version"], stdout=subprocess.PIPE).stdout.decode().strip()
    except OSError:
        return None


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def engine_sha():
    html = open(os.path.join(TOOL, "index.html"), encoding="utf-8").read()
    i = html.index('<script id="shelf-engine">') + len('<script id="shelf-engine">'); j = html.index("</script>", i)
    return hashlib.sha256(html[i:j].encode("utf-8")).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--scale", choices=SCALES, default="small")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--genesis", help="path to the canonical axm-genesis checkout; enables the kernel regime")
    a = ap.parse_args(argv)
    rec = run(a.seed, a.scale, a.record, quiet=a.json, genesis=a.genesis)
    if a.json:
        print(json.dumps(rec, indent=2, ensure_ascii=False))
    else:
        print(f"{rec['failures']} failure(s) in {rec['elapsed_s']} s")
        for f in rec["failure_records"]:
            print(json.dumps({k: f[k] for k in ("invariant", "regime", "index", "detail")}, ensure_ascii=False)[:600])
    return 1 if rec["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
