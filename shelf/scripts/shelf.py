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
disclosure is complete, or that a claim is true. Evidence checks are attributed
to their named person or procedure (e_checks), never inferred from filing.
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
# Shared with the browser: Unicode White_Space plus the text BOM. U+001C..1F
# are separators, not whitespace in this filing/query normalization alphabet.
WHITESPACE = "\u0009\u000a\u000b\u000c\u000d\u0020\u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"


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
    return value is None or isinstance(value, str) and bool(trim_text(value))


def trim_text(value):
    return value.strip(WHITESPACE)


def number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def scalar(value):
    return value.get("value") if isinstance(value, dict) else value


def integer(value):
    """JSON integer value, including 2.0; booleans are never numbers."""
    return number(value) and value % 1 == 0


def normalized_unit(value):
    return value.translate({ord(c): None for c in WHITESPACE}).lower() if isinstance(value, str) else ""


def quote_text(value):
    """Stable diagnostic quoting shared with JavaScript, including controls."""
    escaped = []
    for char in value:
        if char in ("\\", "'"):
            escaped.append("\\" + char)
        elif char in "\t\n\r":
            escaped.append({"\t": "\\t", "\n": "\\n", "\r": "\\r"}[char])
        elif ord(char) < 32 or 127 <= ord(char) <= 159:
            escaped.append("\\x" + format(ord(char), "02x"))
        else:
            escaped.append(char)
    return "'" + "".join(escaped) + "'"


def calendar_date(value):
    """A complete, real calendar date; a timestamp retains its stated date."""
    if not isinstance(value, str):
        return None
    value = trim_text(value)
    match = re.fullmatch(r"([0-9]{4})-([0-9]{2})-([0-9]{2})(?:T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]+)?(?:Z|[+-]([0-9]{2}):([0-9]{2}))?)?", value)
    if not match:
        return None
    try:
        date = dt.date.fromisoformat(value[:10])
        if any(v is not None and int(v) > limit for v, limit in zip(match.groups()[3:], (23, 59, 59, 23, 59))):
            return None
        return date.isoformat()
    except ValueError:
        return None


def valid_period(asked):
    if not isinstance(asked, str):
        return False
    if re.fullmatch(r"[0-9]{4}", asked):
        return 1 <= int(asked) <= 9999
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}", asked):
        return calendar_date(asked + "-01") is not None
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", asked):
        return calendar_date(asked) is not None
    if asked.count("..") == 1:
        start, end = asked.split("..")
        return (len(start) == len(end) == 10 and calendar_date(start) is not None
                and calendar_date(end) is not None and start <= end)
    return False


# -- 1 validate: does the filing carry the five answers? ---------------------
def validate_card(card):
    """Filing errors for one card. Presence is checked; truth is not certified."""
    errors = []
    if not isinstance(card, dict):
        return ["card must be an object"]
    if not isinstance(card.get("id"), str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", card["id"]):
        errors.append("id must be a short lowercase slug")
    for key in ("title", "spine"):
        value = card.get(key)
        if not isinstance(value, str) or not trim_text(value) or any(c in value for c in "\n\r\u0085\u2028\u2029"):
            errors.append(f"{key} must be a nonempty single-line string")
    if not integer(card.get("filing_version")) or card["filing_version"] != FILING_VERSION:
        errors.append("filing_version must be integer 2")
    for sec in ("a_claim", "b_population", "c_parties", "d_materials", "e_checks"):
        if not isinstance(card.get(sec), dict):
            errors.append(f"{sec} must be an object")
    claim = card.get("a_claim")
    if isinstance(claim, dict):
        if "limits" in claim and (not isinstance(claim["limits"], list)
                or any(not isinstance(v, str) or not trim_text(v) for v in claim["limits"])):
            errors.append("a_claim.limits must be a list of nonempty strings")
        if "does_not_establish" in claim and not text_or_null(claim["does_not_establish"]):
            errors.append("a_claim.does_not_establish must be a nonempty string or null")
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
        for key, value in dates.items():
            if isinstance(value, str) and trim_text(value) and calendar_date(value) is None:
                errors.append(f"period.{key} must be a complete valid ISO date or timestamp, or null")
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
                if result is not None and not isinstance(result, str):
                    errors.append(f"results.{key} must be a sourced value object, descriptive string or null")
                continue
            if "unit" in result and result["unit"] is not None and (not isinstance(result["unit"], str) or not trim_text(result["unit"])):
                errors.append(f"results.{key}.unit must be a nonempty string or null")
            unit = normalized_unit(result.get("unit"))
            if ("value" in result and result["value"] is not None
                    and not number(result["value"])):
                errors.append(f"results.{key}.value must be a finite number or null, not a boolean")
            hourly = unit.startswith("usd") and re.search(r"(?:hour|hr|/h$|/gpu-h$|/seat-h$)", unit)
            if hourly:
                if unit not in ("usd/gpu-hour", "usd/seat-hour"):
                    errors.append(f"results.{key}.unit: monetary hourly rate must be USD/GPU-hour or USD/seat-hour, not {quote_text(result['unit'])}")
                if number(result.get("value")) and result["value"] < 0:
                    errors.append(f"results.{key}.value must be a finite nonnegative number, not a boolean")
                if unit == "usd/seat-hour" and result.get("value") is not None:
                    gpus = scalar(q(card, "a_claim", "conditions", "gpus"))
                    if not integer(gpus) or not 0 < gpus <= 9007199254740991:
                        errors.append(f"results.{key}: USD/seat-hour requires a positive integer configuration GPU count in conditions.gpus")
    return errors


def validate_cards(cards):
    """Per-card errors, including collection-local identity collisions."""
    if not isinstance(cards, list):
        return [["shelf must be a list of cards"]]
    ids = [c.get("id") for c in cards if isinstance(c, dict) and isinstance(c.get("id"), str)]
    duplicates = {cid for cid in ids if ids.count(cid) > 1}
    return [validate_card(card) + (["id must be unique on a shelf"]
            if isinstance(card, dict) and isinstance(card.get("id"), str) and card["id"] in duplicates else [])
            for card in cards]


# -- 2 compose: what two cards may not be combined into ----------------------
def compose(a, b, purpose):
    """A scoped refusal, or None when this check found none. None is not admission."""
    if purpose not in PURPOSES:
        return "unknown purpose; known: " + ", ".join(PURPOSES)
    if not isinstance(a, dict) or not isinstance(b, dict):
        return "missing operand: both source cards are required"
    if validate_card(a) or validate_card(b):
        return "invalid filing: both source cards must pass validation before composition"
    def accepted(card):
        return any(normalized_unit(v.get("unit")) in ("usd/1000acceptedrequests", "acceptedrequests")
                   and number(v.get("value")) and v["value"] >= 0
                   for v in card["a_claim"]["results"].values() if isinstance(v, dict))
    if purpose == "cost_per_accepted":
        if not accepted(a) or not accepted(b):
            return "unit mismatch: cost per accepted request needs an accepted-request denominator on both sides (INVARIANTS 1)"
    if purpose == "accepted_work" and not accepted(b):
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
    period = q(card, "a_claim", "period", default={})
    if not isinstance(period, dict):
        return None
    for key in DATE_KEYS:
        value = period.get(key)
        if value is not None:
            return calendar_date(value)
    return None


def in_period(date, asked):
    """asked: YYYY, YYYY-MM, YYYY-MM-DD or START..END (inclusive ISO dates)."""
    if calendar_date(date) is None or len(date) != 10 or not valid_period(asked):
        return False
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
    if not isinstance(cards, list):
        return [{"id": "?", "status": "CANNOT_USE", "reason": "shelf must be a list of cards"}]
    for card, errors in zip(cards, validate_cards(cards)):
        cid = card.get("id", "?") if isinstance(card, dict) else "?"
        reason = ("invalid filing: " + "; ".join(errors) if errors else
                  "query unit must be a nonempty string" if not want else
                  "query measured must be a boolean" if type(measured) is not bool else
                  "invalid period query; expected YYYY, YYYY-MM, YYYY-MM-DD or START..END"
                  if period is not None and not valid_period(period) else None)
        if reason:
            out.append({"id": cid, "status": "CANNOT_USE", "reason": reason})
            continue
        results = q(card, "a_claim", "results", default={}) or {}
        hits = {k: v for k, v in results.items() if isinstance(v, dict)
                and normalized_unit(v.get("unit")) == want and number(v.get("value"))}
        if not hits:
            out.append({"id": cid, "status": "CANNOT_USE", "reason": "no known numeric result in the requested unit; a different or unknown value is different evidence (INVARIANTS 1/4)"})
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


def hub_slug(hub):
    if not isinstance(hub, str):
        raise ValueError("hub name must be a string containing letters or digits")
    slug = re.sub(r"[^a-z0-9._-]+", "-", hub.lower()).strip("-")
    if not re.search(r"[a-z0-9]", slug):
        raise ValueError("hub name must contain letters or digits")
    return slug


def pull(location, hub, staging=None, now=None):
    slug = hub_slug(hub)
    raw = fetch(location)
    retrieved = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = hashlib.sha256(raw).hexdigest()
    cards = parse_cards(raw.decode("utf-8"))
    filings = [{"id": c.get("id") if isinstance(c, dict) else None, "errors": errors}
               for c, errors in zip(cards, validate_cards(cards))]
    folder = os.path.join(staging or os.path.join(DATA, "staging"), slug, retrieved.replace(":", "").replace("-", ""))
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
        "note": "Imported cards enter staging only. Adding one to data/cards.jsonl requires a recorded local admission decision for this captured input by an authorized person or procedure. Source assertions remain attributed to their source; import does not establish local inspection, recomputation or repetition.",
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
        for card, errors in zip(cards, validate_cards(cards)):
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
        print(f"[PASS   ] {args.purpose}: no refusal found. This is not admission; source checks remain separate.")
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
