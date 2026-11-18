#!/usr/bin/env python3
"""Replay repeated, separately pinned HTTP audits without extrapolating an SLA.

The manifest and each receipt require independently retained SHA-256 pins.
A sparse client-vantage sequence establishes sampled outcomes and observed gaps,
not provider-wide uptime, availability guarantees, or elapsed-time availability.
No network calls, inference requests, credentials or body bytes are used.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import sys

if __package__:
    from .operational_http import AuditInputError
    from .operational_http_verify import verify_receipt
else:
    from operational_http import AuditInputError
    from operational_http_verify import verify_receipt

_HEX = frozenset("0123456789abcdef")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.json\Z")
_MAX_RECEIPTS = 128
_MAX_RECEIPT_BYTES = 262144
_MAX_MANIFEST_BYTES = 131072


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise AuditInputError("invalid HTTP temporal ledger: " + message)


def _valid_digest(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in _HEX for c in value)


def _load_json(raw: bytes) -> dict:
    try:
        doc = json.loads(raw, parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuditInputError("invalid HTTP temporal ledger JSON") from exc
    _require(type(doc) is dict, "JSON object")
    return doc


def reconcile(manifest_bytes: bytes, expected_manifest_sha256: str, evidence_directory: Path) -> dict:
    """Require an externally pinned complete inventory, replay all original receipts."""
    _require(_valid_digest(expected_manifest_sha256), "external manifest pin")
    _require(0 < len(manifest_bytes) <= _MAX_MANIFEST_BYTES, "manifest size")
    _require(sha256(manifest_bytes).hexdigest() == expected_manifest_sha256,
             "external manifest SHA-256 mismatch")
    manifest = _load_json(manifest_bytes)
    _require(set(manifest) == {"schema", "endpoint", "method", "receipts"}, "manifest fields")
    _require(manifest["schema"] == "cantos.operational-http-ledger-manifest/1", "schema")
    endpoint, method = manifest["endpoint"], manifest["method"]
    _require(type(endpoint) is str and endpoint.startswith(("http://", "https://")), "endpoint")
    _require(method in ("HEAD", "GET"), "method")
    entries = manifest["receipts"]
    _require(type(entries) is list and 1 <= len(entries) <= _MAX_RECEIPTS,
             "receipt count")
    root = evidence_directory.resolve(strict=True)
    _require(root.is_dir(), "evidence directory")
    seen_names, seen_digests = set(), set()
    result_rows, timeline, all_outcomes = [], [], []
    for index, entry in enumerate(entries):
        _require(type(entry) is dict and set(entry) == {"file", "sha256"},
                 "receipt inventory entry")
        name, pin = entry["file"], entry["sha256"]
        _require(type(name) is str and _NAME.fullmatch(name) is not None, "receipt filename")
        _require(_valid_digest(pin), "receipt pin")
        _require(name not in seen_names and pin not in seen_digests,
                 "duplicate receipt identity")
        seen_names.add(name)
        seen_digests.add(pin)
        file = root / name
        _require(not file.is_symlink() and file.is_file()
                 and file.resolve(strict=True).parent == root, "unsafe receipt path")
        _require(file.stat().st_size <= _MAX_RECEIPT_BYTES, "receipt size")
        raw = file.read_bytes()
        verified = verify_receipt(raw, pin)
        source = _load_json(raw)
        _require(verified["endpoint"] == endpoint and verified["method"] == method,
                 "mixed endpoint or method")
        samples = source["observations"]
        _require(bool(samples), "empty receipt")
        for sample in samples:
            start = datetime.fromisoformat(sample["utc_start"])
            elapsed = sample["elapsed_ms"]
            end = start + timedelta(milliseconds=elapsed)
            timeline.append((start, end, sample["outcome"], name, sample["index"]))
            all_outcomes.append(sample["outcome"])
        result_rows.append({
            "file": name, "sha256": pin, "verdict": verified["verdict"],
            "observations": len(samples),
            "successes": verified["recomputed_summary"]["successes"],
            "first_start_utc": samples[0]["utc_start"],
            "last_start_utc": samples[-1]["utc_start"],
        })
    # A collector issues probes sequentially. A mixed, copied or clock-reversed
    # journal cannot establish an ordered campaign across retained receipts.
    previous_end = None
    gaps = []
    for start, end, outcome, filename, observation in timeline:
        _require(end >= start, "negative probe interval")
        if previous_end is not None:
            _require(start >= previous_end, "overlapping or out-of-order observation windows")
            gaps.append((start - previous_end).total_seconds())
        previous_end = end
    counts = dict(sorted(Counter(all_outcomes).items()))
    successes = counts.get("http_success", 0)
    attempts = len(all_outcomes)
    streak = longest_streak = incidents = 0
    for outcome in all_outcomes:
        if outcome != "http_success":
            if streak == 0:
                incidents += 1
            streak += 1
            longest_streak = max(longest_streak, streak)
        else:
            streak = 0
    first_start = timeline[0][0]
    last_end = timeline[-1][1]
    observed_seconds = sum((end - start).total_seconds() for start, end, *_ in timeline)
    window_seconds = (last_end - first_start).total_seconds()
    _require(observed_seconds <= window_seconds + 1e-6, "observation coverage exceeds window")
    latencies = sorted((end - start).total_seconds() * 1000 for start, end, *_ in timeline)
    verdict = "pass" if all(row["verdict"] == "pass" for row in result_rows) else "fail"
    return {
        "schema": "cantos.operational-http-temporal-ledger/1",
        "manifest_sha256": expected_manifest_sha256,
        "endpoint": endpoint, "method": method,
        "receipt_count": len(entries), "receipts": result_rows,
        "window": {"first_start_utc": first_start.isoformat(),
                   "last_end_utc": last_end.isoformat(),
                   "elapsed_seconds": round(window_seconds, 6),
                   "observed_probe_seconds": round(observed_seconds, 6),
                   "unobserved_gap_seconds": round(sum(gaps), 6),
                   "maximum_gap_seconds": round(max(gaps, default=0.0), 6)},
        "samples": {"attempts": attempts, "successes": successes,
                    "success_fraction": successes / attempts,
                    "outcome_counts": counts,
                    "p95_client_elapsed_ms": round(latencies[math.ceil(.95 * attempts) - 1], 3),
                    "sampled_failure_streaks": incidents,
                    "longest_consecutive_failure_samples": longest_streak},
        "verdict": verdict,
        "custody": "externally_pinned_inventory_and_each_original_receipt",
        "limits": [
            "Only selected client-vantage probes in a sparse observation window",
            "Unobserved gaps do not count as successful or failed service time",
            "Receipt custody does not authenticate the original sampler, provider, or remote host",
            "Repeated correlated probes are not independent uptime trials or an SLA estimate",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True,
                        help="SHA-256 retained independently before this audit")
    parser.add_argument("--evidence-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = reconcile(args.manifest.read_bytes(),
                           args.expected_manifest_sha256, args.evidence_directory)
        data = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as file:
                file.write(data)
        else:
            print(data, end="")
        return 0 if result["verdict"] == "pass" else 1
    except (AuditInputError, OSError, OverflowError) as exc:
        print(f"operational temporal ledger qualification failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
