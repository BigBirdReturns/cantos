#!/usr/bin/env python3
"""counter_record.py -- validate, score and compare "the counter" evaluation records.

Records follow counter_record.schema.json ("second-run/counter-record@1"): the
customer-facing side of a shop evaluation, from signing up through releasing
the machine, without touching the GPU. Python 3.9+ standard library only, no
jsonschema dependency -- validate() does required-field and type checks by hand.

Usage:
    python -B counter_record.py validate <file.json>
    python -B counter_record.py score    <file.json>
    python -B counter_record.py compare  <ref.json> <cand.json>

Every field the evaluator did not actually observe must hold the exact string
"unobserved". validate() accepts that sentinel in place of the field's normal
type everywhere except provenance (always known) and the notes fields
(free text, may be empty string).
"""

from __future__ import annotations

import json
import sys
from statistics import mean
from typing import Any

SCHEMA_ID = "second-run/counter-record@1"
UNOBSERVED = "unobserved"

# ---------------------------------------------------------------------------
# Scoring weights -- the single table. Every dimension's weight lives here and
# only here; they must sum to 100. Any record carrying one or more entries in
# disqualifying_observations has its final weighted score capped at
# DISQUALIFYING_CAP regardless of what the table below computes.
# ---------------------------------------------------------------------------
WEIGHTS: dict[str, int] = {
    "account_creation":     10,
    "price_transparency":   10,
    "provisioning":         15,
    "availability_honesty": 15,
    "api_cli_tui_quality":  10,
    "billing_granularity":  15,
    "tenant_hygiene":       10,
    "network_path":          5,
    "support_path":          5,
    "termination":           5,
}
assert sum(WEIGHTS.values()) == 100, "WEIGHTS must sum to 100"

DISQUALIFYING_CAP = 40

# ---------------------------------------------------------------------------
# Field specs for validate(). Each dimension maps field name -> expected type
# ("bool", "number", "string"). Every one of these fields accepts the literal
# string "unobserved" in place of its type. "notes" is always a plain string
# (may be empty) and is added automatically -- it is never "unobserved" itself
# (an evaluator who observed nothing still writes notes: "").
# ---------------------------------------------------------------------------
DIMENSION_FIELDS: dict[str, dict[str, str]] = {
    "account_creation": {
        "kyc_required": "bool",
        "card_required": "bool",
        "quota_gate": "string",
        "sales_gate": "bool",
        "signup_to_active_account_s": "number",
    },
    "price_transparency": {
        "published": "bool",
        "per_gpu_hour_usd": "number",
        "minimum_billing": "string",
        "egress_rate": "string",
        "storage_rate": "string",
    },
    "api_cli_tui_quality": {
        "token_issuance": "string",
        "list_op": "bool",
        "create_op": "bool",
        "delete_op": "bool",
        "idempotent_create": "bool",
        "idempotent_delete": "bool",
    },
    "billing_granularity": {
        "billing_quantum": "string",
        "stop_on_delete_verified": "bool",
        "invoice_matches_balance": "bool",
    },
    "tenant_hygiene": {
        "fresh_disk": "bool",
        "previous_tenant_residue": "bool",
        "default_users_keys_present": "bool",
    },
    "network_path": {
        "public_ip_assigned": "bool",
        "firewall_default": "string",
        # open_ports_first_boot handled separately: list[int] or "unobserved"
    },
    "support_path": {
        "channel": "string",
        "first_response_time_s": "number",
        "sales_required": "bool",
    },
    "termination": {
        "method": "string",
        "billing_stopped_confirmed": "bool",
        "time_to_confirm_s": "number",
    },
    # provisioning and availability_honesty are list-shaped; handled separately.
}

PROVENANCE_FIELDS = {
    "evaluator": "string",
    "evaluated_at": "string",
    "account_used": "string",
    "money_spent_usd": "number",
    "disclosure": "string",
}

PROVISIONING_ATTEMPT_FIELDS = {
    "request_ts": "string",
    "ssh_ready_ts": "string",
    "time_to_ssh_s": "number",
}

LEDGER_ATTEMPT_FIELDS = {
    "ts": "string",
    "sku": "string",
    "region": "string",
    "method": "string",
    "outcome": "string",
    "provisioned": "bool",
}

TOP_LEVEL_REQUIRED = [
    "schema_id", "provider_id", "provider_name", "provenance",
    "account_creation", "price_transparency", "provisioning",
    "availability_honesty", "api_cli_tui_quality", "billing_granularity",
    "tenant_hygiene", "network_path", "support_path", "termination",
    "disqualifying_observations",
]


def _type_ok(value: Any, expected: str) -> bool:
    if value == UNOBSERVED:
        return True
    if expected == "bool":
        return isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    return False


def validate(record: Any) -> list[str]:
    """Return a list of error strings; empty list means the record is valid."""
    errors: list[str] = []

    if not isinstance(record, dict):
        return ["record is not a JSON object"]

    for key in TOP_LEVEL_REQUIRED:
        if key not in record:
            errors.append(f"missing top-level field: {key}")
    if errors:
        return errors  # nothing else is safe to check yet

    if record.get("schema_id") != SCHEMA_ID:
        errors.append(f"schema_id must be {SCHEMA_ID!r}, got {record.get('schema_id')!r}")
    if not isinstance(record.get("provider_id"), str) or not record["provider_id"]:
        errors.append("provider_id must be a non-empty string")
    if not isinstance(record.get("provider_name"), str) or not record["provider_name"]:
        errors.append("provider_name must be a non-empty string")

    prov = record.get("provenance")
    if not isinstance(prov, dict):
        errors.append("provenance must be an object")
    else:
        for field, expected in PROVENANCE_FIELDS.items():
            if field not in prov:
                errors.append(f"provenance missing field: {field}")
                continue
            value = prov[field]
            # provenance is never "unobserved" -- it describes the evaluation itself
            if expected == "string" and not isinstance(value, str):
                errors.append(f"provenance.{field} must be a string")
            elif expected == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
                errors.append(f"provenance.{field} must be a number")

    for dim, fields in DIMENSION_FIELDS.items():
        block = record.get(dim)
        if not isinstance(block, dict):
            errors.append(f"{dim} must be an object")
            continue
        if "notes" not in block or not isinstance(block["notes"], str):
            errors.append(f"{dim}.notes must be a string")
        for field, expected in fields.items():
            if field not in block:
                errors.append(f"{dim}.{field} is missing")
                continue
            if not _type_ok(block[field], expected):
                errors.append(f"{dim}.{field} must be {expected} or 'unobserved', got {block[field]!r}")

    # network_path.open_ports_first_boot: list[int] or "unobserved"
    npath = record.get("network_path")
    if isinstance(npath, dict):
        ports = npath.get("open_ports_first_boot", "__missing__")
        if ports == "__missing__":
            errors.append("network_path.open_ports_first_boot is missing")
        elif ports != UNOBSERVED:
            if not isinstance(ports, list) or not all(
                isinstance(p, int) and not isinstance(p, bool) for p in ports
            ):
                errors.append("network_path.open_ports_first_boot must be a list of integers or 'unobserved'")

    # provisioning: attempts[] + measured_3x + total_cost_usd
    provn = record.get("provisioning")
    if not isinstance(provn, dict):
        errors.append("provisioning must be an object")
    else:
        if "notes" not in provn or not isinstance(provn["notes"], str):
            errors.append("provisioning.notes must be a string")
        if not _type_ok(provn.get("measured_3x", "__missing__"), "bool"):
            errors.append("provisioning.measured_3x must be bool or 'unobserved'")
        if not _type_ok(provn.get("total_cost_usd", "__missing__"), "number"):
            errors.append("provisioning.total_cost_usd must be a number or 'unobserved'")
        attempts = provn.get("attempts")
        if not isinstance(attempts, list):
            errors.append("provisioning.attempts must be a list")
        else:
            for i, a in enumerate(attempts):
                if not isinstance(a, dict):
                    errors.append(f"provisioning.attempts[{i}] must be an object")
                    continue
                for field, expected in PROVISIONING_ATTEMPT_FIELDS.items():
                    if field not in a:
                        errors.append(f"provisioning.attempts[{i}].{field} is missing")
                    elif not _type_ok(a[field], expected):
                        errors.append(f"provisioning.attempts[{i}].{field} must be {expected} or 'unobserved'")

    # availability_honesty: ledger_attempts[]
    avail = record.get("availability_honesty")
    if not isinstance(avail, dict):
        errors.append("availability_honesty must be an object")
    else:
        if "notes" not in avail or not isinstance(avail["notes"], str):
            errors.append("availability_honesty.notes must be a string")
        attempts = avail.get("ledger_attempts")
        if not isinstance(attempts, list):
            errors.append("availability_honesty.ledger_attempts must be a list")
        else:
            for i, a in enumerate(attempts):
                if not isinstance(a, dict):
                    errors.append(f"availability_honesty.ledger_attempts[{i}] must be an object")
                    continue
                for field, expected in LEDGER_ATTEMPT_FIELDS.items():
                    if field not in a:
                        errors.append(f"availability_honesty.ledger_attempts[{i}].{field} is missing")
                    elif not _type_ok(a[field], expected):
                        errors.append(
                            f"availability_honesty.ledger_attempts[{i}].{field} must be {expected} or 'unobserved'"
                        )

    dq = record.get("disqualifying_observations")
    if not isinstance(dq, list) or not all(isinstance(x, str) for x in dq):
        errors.append("disqualifying_observations must be a list of strings")

    return errors


# ---------------------------------------------------------------------------
# Scoring. Each score_* function returns (score_0_100, [rule strings]) where
# each rule string is the exact arithmetic that produced the score, printed
# verbatim by `score`. "All fields unobserved" always scores 50/100: neither
# credit nor penalty for a dimension nobody looked at.
# ---------------------------------------------------------------------------

def _all_unobserved(block: dict, fields: list[str]) -> bool:
    return all(block.get(f) == UNOBSERVED for f in fields)


def score_account_creation(d: dict) -> tuple[int, list[str]]:
    fields = ["kyc_required", "card_required", "quota_gate", "sales_gate", "signup_to_active_account_s"]
    if _all_unobserved(d, fields):
        return 50, ["all fields unobserved: neutral 50"]
    score, reasons = 100, []
    if d["kyc_required"] is True:
        score -= 25; reasons.append("kyc_required=True: -25")
    if d["sales_gate"] is True:
        score -= 40; reasons.append("sales_gate=True (must talk to sales before self-serve): -40")
    qg = d["quota_gate"]
    if qg == "hard":
        score -= 25; reasons.append("quota_gate=hard: -25")
    elif qg == "soft":
        score -= 10; reasons.append("quota_gate=soft (ticket needed to raise a default limit): -10")
    if d["card_required"] is False:
        score -= 5; reasons.append("card_required=False (weaker accountability signal): -5")
    score = max(0, min(100, score))
    reasons.append(f"= {score}/100")
    return score, reasons


def score_price_transparency(d: dict) -> tuple[int, list[str]]:
    fields = ["published", "per_gpu_hour_usd", "minimum_billing", "egress_rate", "storage_rate"]
    if _all_unobserved(d, fields):
        return 50, ["all fields unobserved: neutral 50"]
    score, reasons = 100, []
    if d["published"] is False:
        score -= 50; reasons.append("published=False (price not public without login): -50")
    for f in ("minimum_billing", "egress_rate", "storage_rate"):
        if d[f] == UNOBSERVED:
            score -= 5; reasons.append(f"{f} unobserved: -5")
    score = max(0, min(100, score))
    reasons.append(f"= {score}/100")
    return score, reasons


def score_provisioning(d: dict) -> tuple[int, list[str]]:
    attempts = d["attempts"]
    times = [a["time_to_ssh_s"] for a in attempts if a.get("time_to_ssh_s") != UNOBSERVED]
    failed = sum(1 for a in attempts if a.get("ssh_ready_ts") == UNOBSERVED and a.get("request_ts") != UNOBSERVED)
    if not times and not attempts:
        return 50, ["no attempts recorded: neutral 50"]
    if not times:
        return 20, [f"{len(attempts)} attempt(s) recorded, none reached SSH: 20"]
    avg = mean(times)
    if avg <= 180:
        score = 100
    elif avg <= 600:
        score = 80
    elif avg <= 1800:
        score = 60
    elif avg <= 3600:
        score = 40
    else:
        score = 20
    reasons = [f"mean time_to_ssh_s={avg:.0f}s over {len(times)} attempt(s): base {score}"]
    if failed:
        penalty = min(40, 20 * failed)
        score -= penalty
        reasons.append(f"{failed} attempt(s) never reached SSH: -{penalty}")
    if d["measured_3x"] is not True:
        score -= 10
        reasons.append("measured_3x is not True (fewer than 3 timed attempts): -10")
    score = max(0, min(100, score))
    reasons.append(f"= {score}/100")
    return score, reasons


def score_availability_honesty(d: dict) -> tuple[int, list[str]]:
    attempts = [a for a in d["ledger_attempts"] if a.get("outcome") != UNOBSERVED]
    if not attempts:
        return 50, ["no resolved ledger attempts: neutral 50"]
    delivered = sum(1 for a in attempts if a.get("outcome") == "available" and a.get("provisioned") is True)
    rate = delivered / len(attempts)
    score = round(rate * 100)
    reasons = [f"{delivered}/{len(attempts)} attempts delivered (outcome=available, provisioned=True): {score}/100"]
    return score, reasons


def score_api_cli_tui_quality(d: dict) -> tuple[int, list[str]]:
    fields = ["token_issuance", "list_op", "create_op", "delete_op", "idempotent_create", "idempotent_delete"]
    if _all_unobserved(d, fields):
        return 50, ["all fields unobserved: neutral 50"]
    score, reasons = 100, []
    ti = d["token_issuance"]
    if ti == "none":
        score -= 40; reasons.append("token_issuance=none: -40")
    elif ti not in ("self-serve", UNOBSERVED):
        score -= 15; reasons.append(f"token_issuance={ti!r} (not self-serve): -15")
    for op in ("list_op", "create_op", "delete_op"):
        if d[op] is False:
            score -= 20; reasons.append(f"{op}=False: -20")
        elif d[op] == UNOBSERVED:
            score -= 5; reasons.append(f"{op} unobserved: -5")
    for op in ("idempotent_create", "idempotent_delete"):
        if d[op] is False:
            score -= 10; reasons.append(f"{op}=False: -10")
    score = max(0, min(100, score))
    reasons.append(f"= {score}/100")
    return score, reasons


def score_billing_granularity(d: dict) -> tuple[int, list[str]]:
    fields = ["billing_quantum", "stop_on_delete_verified", "invoice_matches_balance"]
    if _all_unobserved(d, fields):
        return 50, ["all fields unobserved: neutral 50"]
    score, reasons = 100, []
    sod = d["stop_on_delete_verified"]
    if sod is False:
        score -= 60; reasons.append("stop_on_delete_verified=False (billing kept running past delete): -60, see disqualifying cap")
    elif sod == UNOBSERVED:
        score -= 25; reasons.append("stop_on_delete_verified unobserved: -25")
    imb = d["invoice_matches_balance"]
    if imb is False:
        score -= 30; reasons.append("invoice_matches_balance=False: -30")
    elif imb == UNOBSERVED:
        score -= 10; reasons.append("invoice_matches_balance unobserved: -10")
    if d["billing_quantum"] == UNOBSERVED:
        score -= 5; reasons.append("billing_quantum unobserved: -5")
    score = max(0, min(100, score))
    reasons.append(f"= {score}/100")
    return score, reasons


def score_tenant_hygiene(d: dict) -> tuple[int, list[str]]:
    fields = ["fresh_disk", "previous_tenant_residue", "default_users_keys_present"]
    if _all_unobserved(d, fields):
        return 50, ["all fields unobserved: neutral 50"]
    if d["previous_tenant_residue"] is True:
        return 0, ["previous_tenant_residue=True: hard fail, 0/100, see disqualifying cap"]
    score, reasons = 100, []
    if d["fresh_disk"] is False:
        score -= 50; reasons.append("fresh_disk=False: -50")
    elif d["fresh_disk"] == UNOBSERVED:
        score -= 15; reasons.append("fresh_disk unobserved: -15")
    if d["default_users_keys_present"] is True:
        score -= 30; reasons.append("default_users_keys_present=True: -30")
    elif d["default_users_keys_present"] == UNOBSERVED:
        score -= 10; reasons.append("default_users_keys_present unobserved: -10")
    score = max(0, min(100, score))
    reasons.append(f"= {score}/100")
    return score, reasons


def score_network_path(d: dict) -> tuple[int, list[str]]:
    ports = d.get("open_ports_first_boot", UNOBSERVED)
    core_fields = ["public_ip_assigned", "firewall_default"]
    if _all_unobserved(d, core_fields) and ports == UNOBSERVED:
        return 50, ["all fields unobserved: neutral 50"]
    score, reasons = 100, []
    if d["public_ip_assigned"] == UNOBSERVED:
        score -= 10; reasons.append("public_ip_assigned unobserved: -10")
    fw = d["firewall_default"]
    if fw == "open":
        score -= 20; reasons.append("firewall_default=open: -20")
    elif fw == UNOBSERVED:
        score -= 10; reasons.append("firewall_default unobserved: -10")
    if ports == UNOBSERVED:
        score -= 10; reasons.append("open_ports_first_boot unobserved: -10")
    elif isinstance(ports, list):
        extra = max(0, len(ports) - 2)  # SSH plus one more tolerated by default
        if extra:
            penalty = min(40, 10 * extra)
            score -= penalty
            reasons.append(f"{len(ports)} ports open on first boot (>2 baseline): -{penalty}")
    score = max(0, min(100, score))
    reasons.append(f"= {score}/100")
    return score, reasons


def score_support_path(d: dict) -> tuple[int, list[str]]:
    fields = ["channel", "first_response_time_s", "sales_required"]
    if _all_unobserved(d, fields):
        return 50, ["all fields unobserved: neutral 50"]
    score, reasons = 100, []
    if d["sales_required"] is True:
        score -= 50; reasons.append("sales_required=True: -50")
    ch = d["channel"]
    if ch == "none found":
        score -= 40; reasons.append("channel='none found': -40")
    elif ch == UNOBSERVED:
        score -= 10; reasons.append("channel unobserved: -10")
    t = d["first_response_time_s"]
    if t == UNOBSERVED:
        score -= 10; reasons.append("first_response_time_s unobserved: -10")
    else:
        if t > 86400:
            score -= 35; reasons.append(f"first_response_time_s={t}s (>24h): -35")
        elif t > 3600:
            score -= 15; reasons.append(f"first_response_time_s={t}s (>1h): -15")
    score = max(0, min(100, score))
    reasons.append(f"= {score}/100")
    return score, reasons


def score_termination(d: dict) -> tuple[int, list[str]]:
    fields = ["method", "billing_stopped_confirmed", "time_to_confirm_s"]
    if _all_unobserved(d, fields):
        return 50, ["all fields unobserved: neutral 50"]
    score, reasons = 100, []
    bsc = d["billing_stopped_confirmed"]
    if bsc is False:
        score -= 70; reasons.append("billing_stopped_confirmed=False: -70, see disqualifying cap")
    elif bsc == UNOBSERVED:
        score -= 25; reasons.append("billing_stopped_confirmed unobserved: -25")
    if d["method"] == UNOBSERVED:
        score -= 5; reasons.append("method unobserved: -5")
    t = d["time_to_confirm_s"]
    if t != UNOBSERVED and t > 3600:
        score -= 15; reasons.append(f"time_to_confirm_s={t}s (>1h): -15")
    score = max(0, min(100, score))
    reasons.append(f"= {score}/100")
    return score, reasons


SCORERS = {
    "account_creation": score_account_creation,
    "price_transparency": score_price_transparency,
    "provisioning": score_provisioning,
    "availability_honesty": score_availability_honesty,
    "api_cli_tui_quality": score_api_cli_tui_quality,
    "billing_granularity": score_billing_granularity,
    "tenant_hygiene": score_tenant_hygiene,
    "network_path": score_network_path,
    "support_path": score_support_path,
    "termination": score_termination,
}


def compute_score(record: dict) -> dict:
    """Return {'total': int, 'capped': bool, 'dimensions': {name: {...}}}."""
    dims = {}
    weighted_total = 0.0
    for dim, weight in WEIGHTS.items():
        dim_score, reasons = SCORERS[dim](record[dim])
        contribution = dim_score * weight / 100
        weighted_total += contribution
        dims[dim] = {
            "score": dim_score,
            "weight": weight,
            "contribution": round(contribution, 2),
            "rules": reasons,
        }
    raw_total = round(weighted_total)
    dq = record.get("disqualifying_observations", [])
    capped = len(dq) > 0
    total = min(raw_total, DISQUALIFYING_CAP) if capped else raw_total
    return {
        "total": total,
        "raw_total": raw_total,
        "capped": capped,
        "disqualifying_observations": dq,
        "dimensions": dims,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def cmd_validate(path: str) -> int:
    record = _load(path)
    errors = validate(record)
    if errors:
        print(f"INVALID: {path}")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"VALID: {path}")
    return 0


def cmd_score(path: str) -> int:
    record = _load(path)
    errors = validate(record)
    if errors:
        print(f"INVALID, cannot score: {path}")
        for e in errors:
            print(f"  - {e}")
        return 1
    result = compute_score(record)
    print(f"{record['provider_name']} ({record['provider_id']}) counter score: {result['total']}/100")
    if result["capped"]:
        print(
            f"  DISQUALIFYING: raw weighted score {result['raw_total']}/100 capped at {DISQUALIFYING_CAP}"
            f" because disqualifying_observations is non-empty:"
        )
        for obs in result["disqualifying_observations"]:
            print(f"    - {obs}")
    print()
    print(f"{'dimension':<22} {'weight':>6} {'score':>6} {'contrib':>8}  rule")
    for dim, weight in WEIGHTS.items():
        info = result["dimensions"][dim]
        rule_line = info["rules"][-1] if info["rules"] else ""
        print(f"{dim:<22} {weight:>5}% {info['score']:>6} {info['contribution']:>8.2f}  {rule_line}")
        for r in info["rules"][:-1]:
            print(f"{'':<22} {'':>6} {'':>6} {'':>8}  - {r}")
    return 0


def cmd_compare(ref_path: str, cand_path: str) -> int:
    ref = _load(ref_path)
    cand = _load(cand_path)
    ref_errors = validate(ref)
    cand_errors = validate(cand)
    if ref_errors or cand_errors:
        if ref_errors:
            print(f"INVALID reference: {ref_path}")
            for e in ref_errors:
                print(f"  - {e}")
        if cand_errors:
            print(f"INVALID candidate: {cand_path}")
            for e in cand_errors:
                print(f"  - {e}")
        return 1
    ref_result = compute_score(ref)
    cand_result = compute_score(cand)
    print(f"reference: {ref['provider_name']} = {ref_result['total']}/100")
    print(f"candidate: {cand['provider_name']} = {cand_result['total']}/100")
    delta = cand_result["total"] - ref_result["total"]
    print(f"delta (candidate - reference): {delta:+d}")
    print()
    print(f"{'dimension':<22} {'weight':>6} {'ref':>6} {'cand':>6} {'delta':>6}")
    for dim, weight in WEIGHTS.items():
        r = ref_result["dimensions"][dim]["score"]
        c = cand_result["dimensions"][dim]["score"]
        print(f"{dim:<22} {weight:>5}% {r:>6} {c:>6} {c - r:>+6}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "validate" and len(argv) == 3:
        return cmd_validate(argv[2])
    if cmd == "score" and len(argv) == 3:
        return cmd_score(argv[2])
    if cmd == "compare" and len(argv) == 4:
        return cmd_compare(argv[2], argv[3])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
