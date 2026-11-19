#!/usr/bin/env python3
"""Join pinned AWS CUR resource usage to independently replayed accepted work.

The output is an observed, source-bound unblended Usage *subset* per accepted
attempt. It is not an invoice, a cloud-provider attestation, full workload cost
or a total-cost comparison. No cloud credentials or inference are used.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import re

from .diagnose_grades import sha256 as digest_file
from .empirical_economics import audit as empirical_audit
from .provider_cur import (
    CURAuditError, MAX_CSV, MAX_MANIFEST, audit as cur_audit,
    pinned, require, sessions_from,
)

SCHEMA = "cantos.aws-cur-accepted-work-join/1"
JOIN_SCHEMA = "cantos.aws-cur-accepted-work-bindings/1"
MAX_JOIN = 16384
HEX = re.compile(r"[0-9a-f]{64}\Z")
ARMS = ("baseline", "candidate")


def audit(cur_bytes: bytes, cur_sha256: str, session_bytes: bytes,
          sessions_sha256: str, join_bytes: bytes, join_sha256: str,
          campaign: Path) -> dict:
    # Reconstruct the billing receipt from its original pinned inputs.
    cur = cur_audit(cur_bytes, cur_sha256, session_bytes, sessions_sha256)
    require(type(join_sha256) is str and HEX.fullmatch(join_sha256) and
            0 < len(join_bytes) <= MAX_JOIN and
            sha256(join_bytes).hexdigest() == join_sha256,
            "external bindings pin/size")
    try:
        bindings = json.loads(join_bytes.decode("utf-8"),
                              parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
    except (UnicodeError, ValueError) as exc:
        raise CURAuditError("malformed bindings manifest") from exc
    require(type(bindings) is dict and set(bindings) ==
            {"schema", "campaign_receipt_sha256", "bindings"} and
            bindings["schema"] == JOIN_SCHEMA, "bindings schema")
    campaign = Path(campaign).resolve(strict=True)
    receipt = campaign / "VLLM-EMPIRICAL-RECEIPT.json"
    require(receipt.is_file() and not receipt.is_symlink(),
            "campaign receipt must be regular nonsymlink")
    campaign_hash = digest_file(receipt)
    require(type(bindings["campaign_receipt_sha256"]) is str and
            HEX.fullmatch(bindings["campaign_receipt_sha256"]) and
            bindings["campaign_receipt_sha256"] == campaign_hash,
            "campaign receipt pin does not match")
    pairs = bindings["bindings"]
    require(type(pairs) is list and len(pairs) == 2,
            "one resource session per accepted-work arm required")
    mapping = {}
    used = set()
    for record in pairs:
        require(type(record) is dict and set(record) == {"arm", "session_id"},
                "binding fields")
        arm, sid = record["arm"], record["session_id"]
        require(type(arm) is str and arm in ARMS and arm not in mapping,
                "each arm bound exactly once")
        require(type(sid) is str and sid not in used, "resource sessions distinct")
        used.add(sid)
        mapping[arm] = sid
    require(set(mapping) == set(ARMS), "missing paired arm")
    declared = {x["session_id"]: x for x in sessions_from(session_bytes)}
    require(used <= set(declared), "unknown resource session")
    for sid in used:
        require(declared[sid]["observation_sha256"] == campaign_hash,
                "resource session does not pin independently graded campaign")
    # This replay validates original captured task outcomes and telemetry.
    observed = empirical_audit(campaign)
    arms = observed["observed"]["arms"]
    result = {}
    held_target = cur["counts"]["held_target"]
    for arm in ARMS:
        sid = mapping[arm]
        target = cur["sessions"][sid]
        accepted = arms[arm]["accepted"]
        attempts = arms[arm]["attempts"]
        require(type(accepted) is int and type(attempts) is int and
                0 <= accepted <= attempts and attempts > 0,
                "invalid independent useful-work counts")
        charge = Decimal(target["unblended_usage_usd"])
        valid_subset = target["line_items"] > 0 and held_target == 0
        ratio = str(charge / Decimal(accepted)) if accepted and valid_subset else None
        result[arm] = {
            "session_id": sid,
            "account_id": declared[sid]["account_id"],
            "resource_id": declared[sid]["resource_id"],
            "session_start_utc": declared[sid]["start_utc"],
            "session_end_utc": declared[sid]["end_utc"],
            "accepted_attempts": accepted,
            "attempts": attempts,
            "matched_usage_rows": target["line_items"],
            "matched_unblended_usage_usd": str(charge),
            "unblended_usage_subset_usd_per_accepted": ratio,
            "status": "subset_observed" if ratio is not None else "hold_uncovered_or_zero_accepted",
        }
    return {
        "schema": SCHEMA,
        "evidence_class": "operator_pinned_CUR_subset_joined_to_independently_replayed_grades",
        "sources": {
            "legacy_cur_csv_sha256": cur_sha256,
            "resource_sessions_sha256": sessions_sha256,
            "bindings_sha256": join_sha256,
            "graded_campaign_receipt_sha256": campaign_hash,
        },
        "arms": result,
        "cur_totals": cur["totals"],
        "cur_counts": cur["counts"],
        "billing_verdict": cur["verdict"],
        "not_established": [
            "AWS source authenticity or complete invoice",
            "full resource cost including credits, reservations, fees and taxes",
            "independent ownership proof for operator-declared account/resource/session windows",
            "equivalent cloud workloads or causal price/performance superiority",
            "whole-system cost, facility energy or operational SLA",
        ],
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--cur", type=Path, required=True)
    cli.add_argument("--cur-sha256", required=True)
    cli.add_argument("--sessions", type=Path, required=True)
    cli.add_argument("--sessions-sha256", required=True)
    cli.add_argument("--bindings", type=Path, required=True)
    cli.add_argument("--bindings-sha256", required=True)
    cli.add_argument("--campaign", type=Path, required=True)
    cli.add_argument("--receipt", type=Path, required=True)
    args = cli.parse_args()
    output = audit(pinned(args.cur, args.cur_sha256, MAX_CSV), args.cur_sha256,
                   pinned(args.sessions, args.sessions_sha256, MAX_MANIFEST), args.sessions_sha256,
                   pinned(args.bindings, args.bindings_sha256, MAX_JOIN), args.bindings_sha256,
                   args.campaign)
    encoded = (json.dumps(output, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    fd = os.open(args.receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(encoded)
        f.flush()
        os.fsync(f.fileno())
    print(json.dumps({"receipt_sha256": sha256(encoded).hexdigest(),
                      "arms": {k: v["status"] for k, v in output["arms"].items()}}))


if __name__ == "__main__":
    main()
