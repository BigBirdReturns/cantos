#!/usr/bin/env python3
"""Reconcile separately pinned same-socket TLS/HTTP observations across time.

Every input receipt is independently replayed from its DER certificate and HTTP
response. Ordered client-vantage samples do not measure uptime between probes,
provider-wide reliability, or facility security.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import timedelta
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import sys

if __package__:
    from .operational_https_joint import AuditInputError, validate_endpoint, verify
    from .operational_tls import _utc
else:
    from operational_https_joint import AuditInputError, validate_endpoint, verify
    from operational_tls import _utc

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.json\Z")
_HEX = frozenset("0123456789abcdef")
_MAX_RECEIPTS = 128


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AuditInputError("invalid HTTPS temporal ledger: " + message)


def valid_digest(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(x in _HEX for x in value)


def parse(raw: bytes) -> dict:
    try:
        doc = json.loads(raw, parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuditInputError("invalid ledger JSON") from exc
    require(type(doc) is dict, "JSON object required")
    return doc


def reconcile(manifest_raw: bytes, expected_manifest_sha256: str, evidence_directory: Path) -> dict:
    """Replay each receipt, require a nonoverlapping complete ordered inventory."""
    require(valid_digest(expected_manifest_sha256), "external manifest digest")
    require(0 < len(manifest_raw) <= 131072, "bounded manifest")
    require(sha256(manifest_raw).hexdigest() == expected_manifest_sha256,
            "external manifest digest mismatch")
    manifest = parse(manifest_raw)
    require(set(manifest) == {"schema", "endpoint", "authorized_host", "method", "receipts"},
            "manifest fields")
    require(manifest["schema"] == "cantos.operational-https-ledger-manifest/1", "schema")
    endpoint, host, method = manifest["endpoint"], manifest["authorized_host"], manifest["method"]
    validate_endpoint(endpoint, host)
    require(method in ("GET", "HEAD"), "method")
    entries = manifest["receipts"]
    require(type(entries) is list and 1 <= len(entries) <= _MAX_RECEIPTS, "receipt count")
    root = evidence_directory.resolve(strict=True)
    require(root.is_dir(), "evidence directory")

    names, digests, receipts, samples = set(), set(), [], []
    common_policy = None
    for entry in entries:
        require(type(entry) is dict and set(entry) == {"file", "sha256"}, "entry fields")
        name, digest = entry["file"], entry["sha256"]
        require(type(name) is str and _NAME.fullmatch(name) is not None, "safe filename")
        require(valid_digest(digest), "receipt SHA256")
        require(name not in names and digest not in digests, "duplicate receipt identity")
        names.add(name)
        digests.add(digest)
        path = root / name
        require(not path.is_symlink() and path.is_file() and
                path.resolve(strict=True).parent == root, "receipt custody path")
        require(0 < path.stat().st_size <= 600000, "bounded receipt size")
        raw = path.read_bytes()
        checked = verify(raw, digest)
        receipt = parse(raw)
        require(checked["endpoint"] == endpoint and checked["host"] == host
                and receipt["authorized_host"] == host, "mixed endpoint or authorized host")
        policy = receipt["policy"]
        require(policy["method"] == method, "mixed method")
        shared = {k: v for k, v in policy.items() if k != "samples"}
        if common_policy is None:
            common_policy = shared
        else:
            require(shared == common_policy, "mixed audit policy")
        rows = receipt["observations"]
        receipts.append({"file": name, "sha256": digest, "verdict": checked["verdict"],
                         "observations": len(rows),
                         "successes": checked["recomputed_summary"]["successes"]})
        for row in rows:
            started = _utc(row["started_at_utc"])
            elapsed = row["elapsed_ms"]
            ended = started + timedelta(milliseconds=elapsed)
            require(ended >= started, "negative elapsed")
            tls_checked = row["tls"]["checked_at_utc"]
            if tls_checked is not None:
                timestamp = _utc(tls_checked)
                require(started - timedelta(seconds=1) <= timestamp <= ended + timedelta(seconds=1),
                        "TLS verification timestamp outside HTTP probe interval")
            samples.append((started, ended, row["outcome"], row["tls"]["leaf_sha256"]))
    previous_end = None
    gaps = []
    for started, ended, *_ in samples:
        if previous_end is not None:
            require(started >= previous_end, "overlapping or out-of-order observations")
            gaps.append((started - previous_end).total_seconds())
        previous_end = ended
    first, last = samples[0][0], samples[-1][1]
    observed = sum((end - start).total_seconds() for start, end, *_ in samples)
    window = (last - first).total_seconds()
    require(observed <= window + 1e-6, "observation exceeds window")
    counts = dict(sorted(Counter(x[2] for x in samples).items()))
    accepted = counts.get("http_success", 0)
    streak = longest = incidents = 0
    for _, _, outcome, _ in samples:
        if outcome == "http_success":
            streak = 0
        else:
            if streak == 0:
                incidents += 1
            streak += 1
            longest = max(longest, streak)
    latencies = sorted((end-start).total_seconds()*1000 for start, end, *_ in samples)
    fingerprints = sorted({leaf for _, _, _, leaf in samples if leaf is not None})
    return {
        "schema": "cantos.operational-https-temporal-ledger/1",
        "manifest_sha256": expected_manifest_sha256,
        "endpoint": endpoint, "authorized_host": host, "method": method,
        "receipt_count": len(receipts), "receipts": receipts,
        "window": {"first_start_utc": first.isoformat(), "last_end_utc": last.isoformat(),
                   "elapsed_seconds": round(window, 6),
                   "observed_probe_seconds": round(observed, 6),
                   "unobserved_gap_seconds": round(sum(gaps), 6),
                   "maximum_gap_seconds": round(max(gaps, default=0.0), 6)},
        "samples": {"attempts": len(samples), "successes": accepted,
                    "sampled_success_fraction": accepted/len(samples),
                    "outcome_counts": counts,
                    "p95_client_elapsed_ms": round(latencies[math.ceil(.95*len(samples))-1], 3),
                    "sampled_failure_incidents": incidents,
                    "longest_consecutive_failure_samples": longest,
                    "observed_distinct_TLS_leaf_sha256": fingerprints},
        "verdict": "pass" if all(x["verdict"] == "pass" for x in receipts) else "fail",
        "custody": "externally_pinned_manifest_and_each_same_socket_TLS_HTTP_receipt",
        "limits": ["Sparse client-vantage observations, not a provider-wide SLA or uptime estimate",
                   "Unobserved intervals retain unknown availability",
                   "Offline replay preserves DER and HTTP evidence but cannot rerun live CA verification",
                   "Receipt pins alone do not authenticate the original collector host"],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--expected-manifest-sha256", required=True)
    p.add_argument("--evidence-directory", type=Path, required=True)
    p.add_argument("--output", type=Path)
    a = p.parse_args(argv)
    try:
        result = reconcile(a.manifest.read_bytes(), a.expected_manifest_sha256, a.evidence_directory)
        raw = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if a.output:
            with a.output.open("x", encoding="utf-8") as f:
                f.write(raw)
        else:
            print(raw, end="")
        return 0 if result["verdict"] == "pass" else 1
    except (AuditInputError, OSError, ValueError, OverflowError, TypeError, KeyError) as exc:
        print("HTTPS temporal qualification rejected: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
