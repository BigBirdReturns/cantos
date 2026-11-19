#!/usr/bin/env python3
"""Offline requalification of a pinned Cantos HTTP operational receipt.

No network calls. An independently retained SHA-256 of the original receipt is
required to prevent a rewritten receipt from establishing its own authority.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

if __package__:
    from .operational_http import AuditInputError, classify
else:
    from operational_http import AuditInputError, classify

_HEX = frozenset("0123456789abcdef")


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise AuditInputError("invalid operational receipt: " + message)


def _digest(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in _HEX for c in value))


def _finite_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _replay_observation(item: dict, *, method: str, policy: dict) -> str:
    status = item.get("http_status")
    error = item.get("transport_error_type")
    _require(status is None or (type(status) is int and 100 <= status <= 599), "HTTP status")
    _require(error is None or (isinstance(error, str) and bool(error)), "transport error")
    _require(status is not None or error is not None, "missing transport outcome")
    result = classify(status, error is not None)
    b_hash = item.get("body_sha256")
    b_bytes = item.get("body_bytes")
    content_length = item.get("content_length_claim")
    encoding = item.get("content_encoding_claim")
    if method == "GET" and error is not None and status is not None and 200 <= status < 300:
        # A failed mid-stream read can retain headers set before read() raised,
        # but the collector cannot retain a complete body digest or byte count.
        _require(b_hash is None and b_bytes is None, "partial failed GET body")
        _require(content_length is None or
                 (type(content_length) is int and content_length >= 0),
                 "partial failed GET declared length")
        _require(encoding is None or (isinstance(encoding, str) and bool(encoding)),
                 "partial failed GET encoding")
    elif method != "GET" or result != "http_success":
        _require(all(v is None for v in (b_hash, b_bytes, content_length, encoding)),
                 "body metadata on non-success or HEAD")
    else:
        _require(type(b_bytes) is int and b_bytes >= 0, "GET body bytes")
        _require(content_length is None or
                 (type(content_length) is int and content_length >= 0),
                 "GET declared length")
        _require(isinstance(encoding, str) and bool(encoding), "GET content encoding")
        limit = policy["max_body_bytes"]
        over = b_bytes > limit or (content_length is not None and content_length > limit)
        incomplete = content_length is not None and b_bytes < content_length and not over
        if over or incomplete:
            _require(b_hash is None, "invalid body retains digest")
            result = "http_body_limit_exceeded" if over else "http_body_incomplete"
        else:
            _require(_digest(b_hash), "missing or invalid complete GET digest")
            if (policy["expected_body_sha256"] is not None
                    and b_hash != policy["expected_body_sha256"]):
                result = "http_body_mismatch"
    _require(item.get("outcome") == result, "outcome does not follow HTTP evidence")
    return result


def verify_receipt(raw: bytes, expected_sha256: str) -> dict:
    """Verify receipt custody, replay classifications and return a new verdict."""
    _require(_digest(expected_sha256.lower()), "expected receipt SHA-256")
    digest = sha256(raw).hexdigest()
    _require(digest == expected_sha256.lower(), "external receipt SHA-256 mismatch")
    try:
        doc = json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuditInputError("invalid operational receipt JSON") from exc
    _require(type(doc) is dict and doc.get("schema") == "cantos.operational-http-observation/1",
             "schema")
    _require(doc.get("evidence_class") == "observed_client_vantage", "evidence class")
    _require(doc.get("redirects_followed") is False, "redirect claim")
    _require(doc.get("tls_validation") == "python_standard_library_defaults", "TLS claim")
    _require(type(doc.get("endpoint")) is str and doc["endpoint"].startswith(("http://", "https://")),
             "endpoint")
    method = doc.get("method")
    _require(method in ("HEAD", "GET"), "HTTP method")
    policy = doc.get("policy")
    _require(type(policy) is dict, "policy")
    samples = policy.get("samples")
    timeout = policy.get("timeout_seconds")
    min_fraction = policy.get("min_success_fraction")
    max_p95 = policy.get("max_p95_ms")
    max_body = policy.get("max_body_bytes")
    expected_body = policy.get("expected_body_sha256")
    _require(type(samples) is int and 1 <= samples <= 30, "sample count")
    _require(_finite_number(timeout) and 0.1 <= timeout <= 10, "timeout")
    _require(_finite_number(min_fraction) and 0 <= min_fraction <= 1, "success threshold")
    _require(max_p95 is None or (_finite_number(max_p95) and max_p95 > 0), "latency threshold")
    _require(type(max_body) is int and 1 <= max_body <= 1_048_576, "body limit")
    _require(expected_body is None or (method == "GET" and _digest(expected_body)),
             "expected body identity")
    observations = doc.get("observations")
    _require(type(observations) is list and len(observations) == samples, "observations")
    try:
        canonical = json.dumps(observations, sort_keys=True, separators=(",", ":"),
                               allow_nan=False).encode()
    except (ValueError, TypeError) as exc:
        raise AuditInputError("invalid operational observation serialization") from exc
    _require(sha256(canonical).hexdigest() == doc.get("observations_sha256"),
             "observation journal SHA-256")
    outcomes, latencies = [], []
    for i, item in enumerate(observations):
        _require(type(item) is dict and type(item.get("index")) is int
                 and item["index"] == i, "observation index")
        elapsed = item.get("elapsed_ms")
        _require(_finite_number(elapsed) and elapsed >= 0, "elapsed time")
        latencies.append(elapsed)
        try:
            dt = datetime.fromisoformat(item["utc_start"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AuditInputError("invalid observation timestamp") from exc
        _require(dt.utcoffset() == timedelta(0), "UTC timestamp")
        outcomes.append(_replay_observation(item, method=method, policy=policy))
    p95 = sorted(latencies)[math.ceil(.95 * samples) - 1]
    successes = outcomes.count("http_success")
    fraction = successes / samples
    body_matches = successes if expected_body is not None else None
    valid_identity = (expected_body is None or
                      (body_matches > 0 and not any(x in {
                          "http_body_mismatch", "http_body_incomplete",
                          "http_body_limit_exceeded"} for x in outcomes)))
    passing = (fraction >= min_fraction and (max_p95 is None or p95 <= max_p95)
               and valid_identity)
    recomputed = {
        "successes": successes, "attempts": samples,
        "success_fraction": fraction,
        "body_identity_matches": body_matches,
        "p95_client_elapsed_ms": p95,
        "outcome_counts": dict(sorted(Counter(outcomes).items())),
    }
    _require(doc.get("summary") == recomputed, "summary disagrees with observations")
    verdict = "pass" if passing else "fail"
    _require(doc.get("verdict") == verdict, "verdict disagrees with replay")
    return {
        "schema": "cantos.operational-http-verification/1",
        "original_receipt_sha256": digest,
        "original_observations_sha256": doc["observations_sha256"],
        "endpoint": doc["endpoint"], "method": method,
        "recomputed_summary": recomputed, "verdict": verdict,
        "custody": "independently_pinned_exact_receipt_bytes",
        "limits": ["Offline replay checks receipt consistency and a separately retained exact-byte pin",
                   "Original sampler custody, provider identity and network observations require independent evidence",
                   "A newly calculated pin from a modified receipt is not independent custody"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--expected-receipt-sha256", required=True,
                        help="SHA-256 retained independently before this verification")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_receipt(args.receipt.read_bytes(), args.expected_receipt_sha256)
        data = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as output:
                output.write(data)
        else:
            print(data, end="")
        return 0 if result["verdict"] == "pass" else 1
    except (AuditInputError, OSError) as exc:
        print(f"operational receipt qualification failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
