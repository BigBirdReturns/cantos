#!/usr/bin/env python3
"""Offline, source-pinned legacy AWS CUR attribution; no AWS authentication.

Only USD Usage rows contained by one observed resource session are attributed.
Fees, discounts, missing IDs, incomplete windows remain unallocated. This does
not prove export completeness, invoice truth or cost per accepted task.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import stat

SCHEMA = "cantos.aws-cur-resource-audit/1"
SESSION_SCHEMA = "cantos.aws-cur-resource-sessions/1"
MAX_CSV = 8 * 1024 * 1024
MAX_MANIFEST = 131072
MAX_ROWS = 50000
HEX = re.compile(r"[0-9a-f]{64}\Z")
ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
REQUIRED = (
    "identity/LineItemId", "lineItem/UsageAccountId", "lineItem/ResourceId",
    "lineItem/LineItemType", "lineItem/UsageStartDate", "lineItem/UsageEndDate",
    "lineItem/CurrencyCode", "lineItem/UnblendedCost"
)


class CURAuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise CURAuditError(message)


def pinned(path, expected, limit):
    require(type(expected) is str and HEX.fullmatch(expected), "external pin required")
    p = Path(path)
    require(p.is_file() and not p.is_symlink(), "regular nonsymlink input required")
    require(0 < p.stat().st_size <= limit, "input size limit")
    fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as f:
        before = os.fstat(f.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit,
                "not a regular budgeted file")
        raw = f.read(limit + 1)
        after = os.fstat(f.fileno())
    fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    require(len(raw) <= limit and fields(before) == fields(after),
            "source changed during read")
    require(sha256(raw).hexdigest() == expected, "source SHA-256 mismatch")
    return raw


def utc(value):
    require(type(value) is str and ISO.fullmatch(value), "strict UTC timestamp")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise CURAuditError("invalid UTC timestamp") from exc


def decimal(value):
    require(type(value) is str and 0 < len(value) <= 45, "missing decimal cost")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise CURAuditError("invalid decimal cost") from exc
    require(number.is_finite() and abs(number) < Decimal("1e12"), "nonfinite/excessive cost")
    return number


def sessions_from(raw):
    try:
        doc = json.loads(raw.decode("utf-8"),
                         parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
    except (UnicodeError, ValueError) as exc:
        raise CURAuditError("malformed session manifest") from exc
    require(type(doc) is dict and set(doc) == {"schema", "sessions"} and
            doc["schema"] == SESSION_SCHEMA, "session manifest schema")
    entries = doc["sessions"]
    require(type(entries) is list and 1 <= len(entries) <= 64, "session count")
    result = []
    seen = set()
    for item in entries:
        require(type(item) is dict and set(item) == {
            "session_id", "account_id", "resource_id", "start_utc", "end_utc",
            "observation_sha256"}, "session fields")
        sid = item["session_id"]
        account, resource = item["account_id"], item["resource_id"]
        require(type(sid) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", sid)
                and sid not in seen, "session identity unique")
        seen.add(sid)
        require(type(account) is str and re.fullmatch(r"\d{12}", account),
                "account ID")
        require(type(resource) is str and 1 <= len(resource) <= 256 and
                not any(c.isspace() for c in resource), "resource ID")
        require(type(item["observation_sha256"]) is str and
                HEX.fullmatch(item["observation_sha256"]), "observed session pin")
        start, end = utc(item["start_utc"]), utc(item["end_utc"])
        require(start < end, "session interval")
        result.append({**item, "_start": start, "_end": end})
    for i, left in enumerate(result):
        for right in result[i + 1:]:
            if (left["account_id"], left["resource_id"]) == (right["account_id"], right["resource_id"]):
                require(left["_end"] <= right["_start"] or right["_end"] <= left["_start"],
                        "overlapping resource sessions")
    return result


def audit(csv_bytes, csv_pin, session_bytes, session_pin):
    require(type(csv_pin) is str and HEX.fullmatch(csv_pin) and
            0 < len(csv_bytes) <= MAX_CSV and sha256(csv_bytes).hexdigest() == csv_pin,
            "CUR SHA-256 pin/size")
    require(type(session_pin) is str and HEX.fullmatch(session_pin) and
            0 < len(session_bytes) <= MAX_MANIFEST and
            sha256(session_bytes).hexdigest() == session_pin, "session SHA-256 pin/size")
    windows = sessions_from(session_bytes)
    try:
        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"), newline=""),
                                strict=True)
        header = reader.fieldnames
    except UnicodeError as exc:
        raise CURAuditError("UTF-8 CSV required") from exc
    require(header is not None and len(header) <= 256 and len(set(header)) == len(header)
            and set(REQUIRED).issubset(header), "AWS CUR CSV columns")
    targets = {(s["account_id"], s["resource_id"]) for s in windows}
    accounts = {s["account_id"] for s in windows}
    results = {s["session_id"]: {"usd": Decimal(0), "rows": 0} for s in windows}
    counts = dict(total=0, matched=0, held_target=0, other_account_or_resource=0,
                  missing_resource_id=0, other_charge_type=0)
    reasons = {}
    types = {}
    total = matched = Decimal(0)
    seen = set()
    try:
        for row in reader:
            counts["total"] += 1
            require(counts["total"] <= MAX_ROWS, "row count limit")
            require(None not in row and all(v is not None for v in row.values()),
                    "CSV field count")
            key = row["identity/LineItemId"]
            require(bool(key) and len(key) <= 256 and key not in seen,
                    "missing/duplicate line item")
            seen.add(key)
            require(re.fullmatch(r"\d{12}", row["lineItem/UsageAccountId"]),
                    "CUR account ID")
            require(row["lineItem/CurrencyCode"] == "USD", "USD-only audit")
            amount = decimal(row["lineItem/UnblendedCost"])
            total += amount
            kind = row["lineItem/LineItemType"]
            if kind != "Usage":
                counts["other_charge_type"] += 1
                types[kind] = types.get(kind, 0) + 1
                continue
            account, resource = row["lineItem/UsageAccountId"], row["lineItem/ResourceId"]
            if not resource:
                if account in accounts:
                    counts["missing_resource_id"] += 1
                continue
            if (account, resource) not in targets:
                counts["other_account_or_resource"] += 1
                continue
            start, end = utc(row["lineItem/UsageStartDate"]), utc(row["lineItem/UsageEndDate"])
            require(start < end, "CUR interval")
            possible = [w for w in windows if (w["account_id"], w["resource_id"]) ==
                        (account, resource) and start >= w["_start"] and end <= w["_end"]]
            if len(possible) == 1:
                record = results[possible[0]["session_id"]]
                record["usd"] += amount
                record["rows"] += 1
                matched += amount
                counts["matched"] += 1
            else:
                counts["held_target"] += 1
                reason = "partial_or_outside_session" if not possible else "ambiguous_session"
                reasons[reason] = reasons.get(reason, 0) + 1
    except (csv.Error, UnicodeError) as exc:
        raise CURAuditError("malformed CSV") from exc
    require(counts["total"] > 0, "empty CUR")
    held = total - matched
    direct = (counts["held_target"] == counts["missing_resource_id"] ==
              counts["other_charge_type"] == 0)
    return {
        "schema": SCHEMA, "evidence_class": "externally_pinned_operator_export_not_AWS_authenticated",
        "sources": {"legacy_cur_csv_sha256": csv_pin, "session_manifest_sha256": session_pin,
                    "cur_bytes": len(csv_bytes), "session_bytes": len(session_bytes)},
        "scope": {"resource_sessions": [
            {k: w[k] for k in ("session_id", "account_id", "resource_id",
                                "start_utc", "end_utc", "observation_sha256")}
            for w in windows], "export_completeness": "unknown"},
        "counts": counts, "held_charge_types": types, "held_reasons": reasons,
        "sessions": {sid: {"unblended_usage_usd": str(v["usd"]), "line_items": v["rows"]}
                     for sid, v in results.items()},
        "currency": "USD",
        "totals": {"file_unblended_usd": str(total),
                   "direct_usage_usd": str(matched),
                   "unattributed_usd": str(held)},
        "verdict": "direct_usage_subset" if direct else "hold_unresolved_allocation",
        "not_established": ["AWS export authenticity", "complete invoice or billing month",
                            "discounts/RI/Savings Plan/fees/taxes",
                            "session observation authenticity", "accepted-task economics",
                            "provider reliability or SLA"],
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--cur", type=Path, required=True)
    cli.add_argument("--cur-sha256", required=True)
    cli.add_argument("--sessions", type=Path, required=True)
    cli.add_argument("--sessions-sha256", required=True)
    cli.add_argument("--receipt", type=Path, required=True)
    args = cli.parse_args()
    result = audit(pinned(args.cur, args.cur_sha256, MAX_CSV), args.cur_sha256,
                   pinned(args.sessions, args.sessions_sha256, MAX_MANIFEST),
                   args.sessions_sha256)
    encoded = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    fd = os.open(args.receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(encoded)
        out.flush()
        os.fsync(out.fileno())
    print(json.dumps({"receipt_sha256": sha256(encoded).hexdigest(),
                      "verdict": result["verdict"], "counts": result["counts"]}))


if __name__ == "__main__":
    main()
