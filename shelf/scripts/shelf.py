#!/usr/bin/env python3
"""The shelf: file, check, compose and import claims about compute. Stdlib only.

A card answers five questions about one claim. This tool checks that a filing
carries the answers, refuses compositions the format does not license, says
which cards on a shelf can support a stated question and how far, and pulls
other people's shelves into staging without granting them standing.

  python shelf.py validate <card.json | cards.jsonl>
  python shelf.py compose <a.json> <b.json> --for <purpose>
  python shelf.py which [cards.jsonl] --unit "USD / 1000 accepted requests" --period 2026-09 [--measured]
  python shelf.py pull <url | path> --hub <name>
  python shelf.py sync --check

Nothing here certifies that a cited source warrants a value, that a populated
disclosure is complete, or that a claim is true. Those remain recorded human
checks (e_checks) and are reported, never inferred.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
DATA = os.path.join(TOOL, "data")
CARDS = os.path.join(DATA, "cards.jsonl")
DIMS = ("measured", "imported", "modeled", "attributed")
CHECKS = ("inspected", "recomputed", "repeated")
PURPOSES = ("cost_per_accepted", "accepted_work", "seat_property", "measured_cost", "same_period")
FILING_VERSION = 2


# -- reading -----------------------------------------------------------------
def read_cards(path):
    """A .json file holds one card or a list; a .jsonl file holds one card per line."""
    with open(path, encoding="utf-8-sig") as f:
        return parse_cards(f.read())


def parse_cards(text):
    """One JSON document (object or list) or one object per line."""
    text = text.lstrip("﻿")
    try:
        value = json.loads(text)
        return value if isinstance(value, list) else [value]
    except ValueError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def q(card, *keys, default=None):
    cur = card
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def text_or_null(value):
    return value is None or isinstance(value, str) and bool(value.strip())


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def scalar(value):
    return value.get("value") if isinstance(value, dict) else value


def normalized_unit(value):
    return re.sub(r"\s+", "", value).lower() if isinstance(value, str) else ""


# -- 1 validate: does the filing carry the five answers? ---------------------
def validate_card(card):
    """Filing errors for one card. Presence is checked; truth is not certified."""
    errors = []
    if not isinstance(card, dict):
        return ["card must be an object"]
    if not isinstance(card.get("id"), str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", card["id"]):
        errors.append("id must be a short lowercase slug")
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


# -- 2 compose: what two cards may not be combined into ----------------------
def compose(a, b, purpose):
    """A scoped refusal, or None when this check found none. None is not admission."""
    if purpose not in PURPOSES:
        return f"unknown purpose {purpose!r}; known: {', '.join(PURPOSES)}"
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
        da, db = observation_date(a), observation_date(b)
        if da is None or db is None:
            return "comparable observation/publication period unknown; retrieval does not supply it (BRIEF2 item 3)"
        if da != db:
            return f"periods differ ({da} vs {db}); combine only with the period stated (BRIEF2 item 3)"
    return None


# -- 3 which: which cards can support a stated question, and how far ---------
DATE_KEYS = ("experiment_date", "index_date", "artifact_created_at", "publication_date")


def observation_date(card):
    """The date the observation is about, in order of preference. Retrieval never counts."""
    period = q(card, "a_claim", "period", default={}) or {}
    for key in DATE_KEYS:
        value = scalar(period.get(key))
        if isinstance(value, str) and value.strip():
            return value.strip()[:10]
    return None


def in_period(date, asked):
    """asked: YYYY, YYYY-MM, YYYY-MM-DD or START..END (inclusive ISO dates)."""
    if ".." in asked:
        start, end = asked.split("..", 1)
        return start <= date <= end
    return date.startswith(asked)


def how_far(checks):
    done = [k for k in CHECKS if checks[k]["who"]]
    missing = [k for k in CHECKS if not checks[k]["who"]]
    parts = []
    if done:
        parts.append("; ".join(f"{k} by {checks[k]['who']}" + (f" ({checks[k]['when']})" if checks[k]["when"] else "") for k in done))
    if missing:
        parts.append("not " + ", not ".join(missing))
    return ". ".join(parts) + ". Nothing here ranks it against another card."


def which(cards, unit, period=None, measured=False):
    """Per card: SUPPORTS with results, limits and recorded checks, or CANNOT_USE with the rule."""
    want = normalized_unit(unit)
    out = []
    for card in cards:
        cid = card.get("id", "?") if isinstance(card, dict) else "?"
        results = q(card, "a_claim", "results", default={}) or {}
        hits = {k: v for k, v in results.items() if isinstance(v, dict) and normalized_unit(v.get("unit")) == want}
        if not hits:
            out.append({"id": cid, "status": "CANNOT_USE", "reason": f"no result in the unit '{unit}'; a different unit is different evidence (INVARIANTS 1/4)"})
            continue
        if measured and q(card, "dimensions", "measured") is not True:
            out.append({"id": cid, "status": "CANNOT_USE", "reason": "not measured; an imported, modeled or attributed statement is not a measurement (INVARIANTS 3/5)"})
            continue
        date = observation_date(card)
        if period is not None:
            if date is None:
                out.append({"id": cid, "status": "CANNOT_USE", "reason": "observation period unknown; retrieval does not supply it (BRIEF2 item 3)"})
                continue
            if not in_period(date, period):
                out.append({"id": cid, "status": "CANNOT_USE", "reason": f"observation date {date} is outside {period}; combine only with the period stated (BRIEF2 item 3)"})
                continue
        checks = {k: {"who": q(card, "e_checks", k, "who"), "when": q(card, "e_checks", k, "when")} for k in CHECKS}
        out.append({
            "id": cid, "status": "SUPPORTS", "date": date,
            "dimensions": q(card, "dimensions"),
            "results": {k: {"value": v.get("value"), "unit": v.get("unit"), "supports": v.get("supports")} for k, v in hits.items()},
            "limits": q(card, "a_claim", "limits", default=[]) or [],
            "does_not_establish": q(card, "a_claim", "does_not_establish"),
            "checks": checks,
            "how_far": how_far(checks),
        })
    return out


# -- 4 pull: bring another shelf into staging; standing stays candidate ------
def fetch(location, timeout=30):
    if re.match(r"^https?://", location):
        req = urllib.request.Request(location, headers={"User-Agent": "axm-shelf/1 (stdlib urllib)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    with open(location, "rb") as f:
        return f.read()


def pull(location, hub, staging=None, now=None):
    raw = fetch(location)
    retrieved = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = hashlib.sha256(raw).hexdigest()
    cards = parse_cards(raw.decode("utf-8"))
    filings = [{"id": c.get("id") if isinstance(c, dict) else None, "errors": validate_card(c)} for c in cards]
    hub_slug = re.sub(r"[^a-z0-9._-]+", "-", hub.lower()).strip("-")
    if not hub_slug:
        raise ValueError("hub name must contain letters or digits")
    folder = os.path.join(staging or os.path.join(DATA, "staging"), hub_slug, retrieved.replace(":", "").replace("-", ""))
    os.makedirs(folder, exist_ok=False)
    with open(os.path.join(folder, "source.bytes"), "wb") as f:
        f.write(raw)
    with open(os.path.join(folder, "cards.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n")
    provenance = {
        "hub": hub, "location": location, "retrieved_at": retrieved, "sha256": digest,
        "cards": len(cards), "filings": filings,
        "standing": "imported/candidate",
        "note": "Imported cards enter staging only. Adding one to data/cards.jsonl is a recorded human decision; it does not carry standing, inspection or repetition from the source hub.",
    }
    with open(os.path.join(folder, "provenance.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(provenance, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return folder, provenance


# -- 5 sync: this shelf's copy and the retained campaign record must not drift
def sync_check(here=CARDS, upstream=None):
    upstream = upstream or os.path.join(os.path.dirname(TOOL), "hot-aisle", "campaign", "shelf", "cards.jsonl")
    with open(here, "rb") as f:
        a = f.read()
    with open(upstream, "rb") as f:
        b = f.read()
    return a == b, hashlib.sha256(a).hexdigest(), hashlib.sha256(b).hexdigest(), upstream


# -- CLI ---------------------------------------------------------------------
def print_which(rows):
    for r in rows:
        if r["status"] == "SUPPORTS":
            print(f"[SUPPORTS] {r['id']} ({r['date'] or 'date unknown'})")
            for k, v in r["results"].items():
                line = f"           {k}: {v['value']} {v['unit']}"
                if v.get("supports"):
                    line += f" | supports: {v['supports']}"
                print(line)
            for lim in r["limits"]:
                print(f"           limit: {lim}")
            if r["does_not_establish"]:
                print(f"           does not establish: {r['does_not_establish']}")
            print(f"           how far: {r['how_far']}")
        else:
            print(f"[CANNOT ] {r['id']}: {r['reason']}")
    n = sum(r["status"] == "SUPPORTS" for r in rows)
    print(f"{n}/{len(rows)} cards can support the question as stated. Support is bounded by each card's limits and recorded checks; nothing here ranks.")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="shelf.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="filing check for one card or a shelf")
    v.add_argument("path")
    c = sub.add_parser("compose", help="refuse or pass one composition of two cards")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("--for", dest="purpose", required=True, choices=PURPOSES)
    w = sub.add_parser("which", help="which cards can support a question in this unit and period")
    w.add_argument("path", nargs="?", default=CARDS)
    w.add_argument("--unit", required=True)
    w.add_argument("--period")
    w.add_argument("--measured", action="store_true")
    w.add_argument("--json", action="store_true")
    p = sub.add_parser("pull", help="import another shelf into data/staging (candidate standing only)")
    p.add_argument("location")
    p.add_argument("--hub", required=True)
    p.add_argument("--staging")
    s = sub.add_parser("sync", help="check this shelf's copy against the retained campaign record")
    s.add_argument("--check", action="store_true", required=True)
    args = parser.parse_args(argv)

    if args.cmd == "validate":
        cards = read_cards(args.path)
        bad = 0
        for card in cards:
            errors = validate_card(card)
            cid = card.get("id", "?") if isinstance(card, dict) else "?"
            if errors:
                bad += 1
                for e in errors:
                    print(f"[FAIL   ] {cid}: {e}")
            else:
                print(f"[PASS   ] {cid}: carries (a)-(e), four dimensions, three checks, publication-date basis, observer benefit and explicit hourly units")
        print(f"{len(cards) - bad}/{len(cards)} filings pass. Structure only; source truth, recomputation and independent use are not established.")
        return bad
    if args.cmd == "compose":
        a, b = read_cards(args.a)[0], read_cards(args.b)[0]
        reason = compose(a, b, args.purpose)
        if reason:
            print(f"[REFUSED] {args.purpose}: {reason}")
            return 2
        print(f"[PASS   ] {args.purpose}: no refusal found. This is not admission; a reviewer still checks the cited sources.")
        return 0
    if args.cmd == "which":
        rows = which(read_cards(args.path), args.unit, args.period, args.measured)
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            print_which(rows)
        return 0
    if args.cmd == "pull":
        folder, prov = pull(args.location, args.hub, args.staging)
        bad = sum(bool(f["errors"]) for f in prov["filings"])
        print(f"pulled {prov['cards']} card(s) from {args.location} into {folder}")
        print(f"sha256 {prov['sha256']}; {prov['cards'] - bad} pass the filing check; standing {prov['standing']}")
        return 0
    if args.cmd == "sync":
        same, ha, hb, upstream = sync_check()
        print(("[PASS   ] " if same else "[FAIL   ] ") + f"data/cards.jsonl {ha[:12]} vs retained campaign record {hb[:12]} ({upstream})")
        return 0 if same else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
