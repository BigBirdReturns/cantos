#!/usr/bin/env python3
"""Direct HTTPS connection audit: bind verified TLS leaf to its actual HTTP response.

Collects only authorized HEAD/GET observations. Offline replay needs a receipt
SHA-256 supplied independently of the receipt; it does not reestablish CA trust.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import http.client as http_client
import json
import math
from pathlib import Path
import socket
import ssl
import sys
import time
from urllib.parse import urlsplit

from .operational_http import classify
from .operational_http_verify import _replay_observation
from .operational_tls import (_evaluate, _number, _digest, _utc, _require,
                              certificate_validity, validate_origin, AuditInputError)


def canonical(doc: dict) -> bytes:
    return (json.dumps(doc, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def validate_endpoint(url: str, host: str) -> tuple[str, int, str]:
    _require(type(url) is str and type(host) is str, "endpoint and host types")
    try:
        u = urlsplit(url)
        port = u.port
    except ValueError as exc:
        raise AuditInputError("invalid endpoint") from exc
    _require(u.scheme == "https" and u.hostname is not None and u.netloc
             and not u.username and not u.password and not u.query and not u.fragment,
             "explicit HTTPS endpoint without credentials, query or fragment required")
    _require("\\" not in url and "\r" not in url and "\n" not in url,
             "unsafe endpoint characters")
    origin = "https://" + u.netloc + "/"
    dns, verified_port = validate_origin(origin, host)
    path = u.path or "/"
    _require(path.startswith("/") and not path.startswith("//"), "absolute request path")
    return dns, verified_port, path


def policy_check(policy: dict) -> None:
    _require(type(policy) is dict and set(policy) == {
        "samples", "timeout_seconds", "method", "max_body_bytes",
        "expected_body_sha256", "expected_leaf_sha256",
        "min_remaining_days", "min_success_fraction", "max_p95_ms"}, "policy fields")
    s, timeout, method = policy["samples"], policy["timeout_seconds"], policy["method"]
    cap, days = policy["max_body_bytes"], policy["min_remaining_days"]
    fraction, limit = policy["min_success_fraction"], policy["max_p95_ms"]
    body, leaf = policy["expected_body_sha256"], policy["expected_leaf_sha256"]
    _require(type(s) is int and 1 <= s <= 8, "sample count")
    _require(_number(timeout) and 0.1 <= timeout <= 10, "timeout")
    _require(method in ("HEAD", "GET"), "method")
    _require(type(cap) is int and 1 <= cap <= 1048576, "response byte cap")
    _require(_number(days) and 0 <= days <= 365, "minimum certificate lifetime")
    _require(_number(fraction) and 0 <= fraction <= 1, "minimum success fraction")
    _require(limit is None or (_number(limit) and limit > 0), "maximum p95 latency")
    _require(leaf is None or _digest(leaf), "expected leaf hash")
    _require(body is None or (method == "GET" and _digest(body)), "expected body hash")


def empty_http(index: int, status: int | None = None,
               error_type: str | None = None) -> dict:
    return {"index": index, "http_status": status,
            "transport_error_type": error_type,
            "outcome": classify(status, error_type is not None) if status is not None or error_type else None,
            "body_sha256": None, "body_bytes": None,
            "content_length_claim": None, "content_encoding_claim": None}


def _http_result(index: int, response, policy: dict) -> dict:
    status = response.status
    result = empty_http(index, status)
    if 200 <= status < 300 and policy["method"] == "GET":
        raw_length = response.getheader("Content-Length")
        content_length = int(raw_length) if raw_length is not None and raw_length.isdecimal() else None
        encoding = response.getheader("Content-Encoding", "identity")
        body = response.read(policy["max_body_bytes"] + 1)
        n = len(body)
        over = n > policy["max_body_bytes"] or (content_length is not None and content_length > policy["max_body_bytes"])
        incomplete = not over and content_length is not None and n < content_length
        result.update(body_bytes=n, content_length_claim=content_length,
                      content_encoding_claim=encoding)
        if over:
            result["outcome"] = "http_body_limit_exceeded"
        elif incomplete:
            result["outcome"] = "http_body_incomplete"
        else:
            digest = sha256(body).hexdigest()
            result["body_sha256"] = digest
            if policy["expected_body_sha256"] is not None and digest != policy["expected_body_sha256"]:
                result["outcome"] = "http_body_mismatch"
    return result


def _summary(rows: list, policy: dict) -> tuple[dict, str]:
    n = len(rows)
    combined = [r["outcome"] for r in rows]
    counts = dict(sorted(Counter(combined).items()))
    successes = counts.get("http_success", 0)
    times = sorted(r["elapsed_ms"] for r in rows)
    p95 = times[math.ceil(.95 * n) - 1]
    summary = {"attempts": n, "successes": successes,
               "success_fraction": successes / n, "outcome_counts": counts,
               "p95_connection_and_response_ms": p95}
    invalid_body = any(r["outcome"] in {"http_body_mismatch", "http_body_incomplete",
                                       "http_body_limit_exceeded"} for r in rows)
    passed = successes / n >= policy["min_success_fraction"]
    if policy["max_p95_ms"] is not None:
        passed = passed and p95 <= policy["max_p95_ms"]
    if policy["expected_body_sha256"] is not None:
        passed = passed and successes > 0 and not invalid_body
    # A refused certificate or network failure cannot be promoted by a relaxed
    # availability threshold; a bounded all-failed probe is never a pass.
    passed = passed and successes > 0 and not any(r["tls"]["outcome"] != "tls_success" for r in rows)
    return summary, "pass" if passed else "fail"


def audit(url: str, *, allow_host: str, samples: int = 1, method: str = "GET",
          timeout_seconds: float = 3., max_body_bytes: int = 65536,
          expected_body_sha256: str | None = None,
          expected_leaf_sha256: str | None = None,
          min_remaining_days: float = 14.,
          min_success_fraction: float = 1.,
          max_p95_ms: float | None = None) -> dict:
    host, port, path = validate_endpoint(url, allow_host)
    policy = dict(samples=samples, timeout_seconds=timeout_seconds, method=method,
                  max_body_bytes=max_body_bytes, expected_body_sha256=expected_body_sha256,
                  expected_leaf_sha256=expected_leaf_sha256,
                  min_remaining_days=min_remaining_days,
                  min_success_fraction=min_success_fraction, max_p95_ms=max_p95_ms)
    policy_check(policy)
    rows = []
    for idx in range(samples):
        started = datetime.now(timezone.utc).isoformat()
        tick = time.monotonic_ns()
        tls = {"outcome": None, "leaf_der_base64": None, "leaf_sha256": None,
               "valid_from_utc": None, "valid_until_utc": None,
               "remaining_days": None, "checked_at_utc": None, "error_type": None}
        http = None
        conn = None
        try:
            context = ssl.create_default_context()
            _require(context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname,
                     "CA and hostname validation required")
            conn = http_client.HTTPSConnection(host, port=port, timeout=timeout_seconds, context=context)
            conn.connect()
            _require(conn.sock is not None, "missing TLS socket")
            der = conn.sock.getpeercert(binary_form=True)
            parsed = conn.sock.getpeercert()
            _require(type(der) is bytes and type(parsed) is dict and bool(parsed), "unverified leaf")
            before, after = certificate_validity(der)
            _require(int(after.timestamp()) == ssl.cert_time_to_seconds(parsed["notAfter"]),
                     "certificate validity mismatch")
            checked = datetime.now(timezone.utc)
            outcome, identity = _evaluate(der, checked, expected_leaf_sha256, min_remaining_days)
            tls.update(identity)
            tls["checked_at_utc"] = checked.isoformat()
            tls["outcome"] = outcome
            if outcome == "tls_success":
                conn.request(method, path, headers={
                    "User-Agent": "Cantos-direct-joint-HTTPS-audit/1",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                })
                with conn.getresponse() as response:
                    http = _http_result(idx, response, policy)
        except ssl.SSLCertVerificationError as exc:
            if tls["outcome"] == "tls_success":
                http = empty_http(idx, error_type=type(exc).__name__)
            else:
                tls.update(error_type=type(exc).__name__, outcome="tls_verification_failed")
        except ssl.SSLError as exc:
            if tls["outcome"] == "tls_success":
                http = empty_http(idx, error_type=type(exc).__name__)
            else:
                tls.update(error_type=type(exc).__name__, outcome="tls_handshake_error")
        except (socket.timeout, TimeoutError, OSError, http_client.HTTPException) as exc:
            if tls["outcome"] is None:
                tls.update(error_type=type(exc).__name__, outcome="tls_transport_error")
            else:
                http = empty_http(idx, error_type=type(exc).__name__)
        except AuditInputError as exc:
            if tls["outcome"] == "tls_success":
                http = empty_http(idx, error_type=type(exc).__name__)
            else:
                tls.update(error_type=type(exc).__name__, outcome="tls_peer_certificate_invalid")
        finally:
            if conn is not None:
                conn.close()
        if tls["outcome"] is None:
            tls.update(outcome="tls_transport_error", error_type="unknown")
        outcome = tls["outcome"] if tls["outcome"] != "tls_success" else http["outcome"]
        rows.append({"index": idx, "started_at_utc": started,
                     "elapsed_ms": round((time.monotonic_ns() - tick) / 1e6, 3),
                     "tls": tls, "http": http, "outcome": outcome})
    summary, verdict = _summary(rows, policy)
    return {"schema": "cantos.operational-https-joint/1",
            "evidence_class": "observed_single_TLS_connection_per_HTTP_sample",
            "endpoint": url, "authorized_host": allow_host,
            "tls_validation": "python_default_CA_hostname_SNI",
            "proxy_policy": "direct_socket_no_ambient_proxy",
            "redirects_followed": False, "policy": policy, "observations": rows,
            "observations_sha256": sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"),allow_nan=False).encode()).hexdigest(),
            "summary": summary, "verdict": verdict,
            "limits": ["Single client vantage and bounded observations, not provider SLA",
                       "Offline certificate DER replay does not independently repeat live CA validation",
                       "Externally pinned receipt preserves captured identities, not custody of the collector host",
                       "HTTPS response and verified TLS peer share one actual socket; no inference workload or provider rating"]}


def verify(raw: bytes, expected_sha256: str) -> dict:
    _require(_digest(expected_sha256) and sha256(raw).hexdigest() == expected_sha256,
             "externally pinned receipt SHA-256")
    _require(0 < len(raw) <= 600000, "receipt size")
    try:
        doc = json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuditInputError("invalid joint receipt JSON") from exc
    _require(type(doc) is dict and doc.get("schema") == "cantos.operational-https-joint/1",
             "schema")
    _require(doc.get("evidence_class") == "observed_single_TLS_connection_per_HTTP_sample"
             and doc.get("tls_validation") == "python_default_CA_hostname_SNI"
             and doc.get("proxy_policy") == "direct_socket_no_ambient_proxy"
             and doc.get("redirects_followed") is False, "transport policy")
    host, _, _ = validate_endpoint(doc.get("endpoint"), doc.get("authorized_host"))
    policy = doc.get("policy")
    policy_check(policy)
    rows = doc.get("observations")
    _require(type(rows) is list and len(rows) == policy["samples"], "sample count")
    _require(sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest() == doc.get("observations_sha256"), "observation journal hash")
    for i, row in enumerate(rows):
        _require(type(row) is dict and set(row) == {"index", "started_at_utc", "elapsed_ms",
                                                    "tls", "http", "outcome"} and row["index"] == i,
                 "observation identity")
        _utc(row["started_at_utc"])
        _require(_number(row["elapsed_ms"]) and row["elapsed_ms"] >= 0, "elapsed time")
        tls = row["tls"]
        _require(type(tls) is dict and set(tls) == {"outcome", "leaf_der_base64", "leaf_sha256",
            "valid_from_utc", "valid_until_utc", "remaining_days", "checked_at_utc",
            "error_type"}, "TLS evidence fields")
        der_b64 = tls["leaf_der_base64"]
        if der_b64 is not None:
            _require(type(der_b64) is str and len(der_b64) < 50000 and
                     tls["error_type"] is None, "TLS leaf evidence")
            try:
                der = base64.b64decode(der_b64, validate=True)
            except (ValueError, base64.binascii.Error) as exc:
                raise AuditInputError("invalid DER encoding") from exc
            checked = _utc(tls["checked_at_utc"])
            expected_outcome, expected_fields = _evaluate(
                der, checked, policy["expected_leaf_sha256"], policy["min_remaining_days"])
            for field, val in expected_fields.items():
                _require(tls.get(field) == val, "TLS DER evidence " + field)
            _require(tls["outcome"] == expected_outcome, "TLS result")
        else:
            _require(tls["checked_at_utc"] is None and tls["leaf_sha256"] is None
                     and tls["valid_from_utc"] is None and tls["valid_until_utc"] is None
                     and tls["remaining_days"] is None and type(tls["error_type"]) is str
                     and len(tls["error_type"]) <= 80, "TLS failure fields")
            failure_map = {"SSLCertVerificationError": "tls_verification_failed",
                           "SSLError": "tls_handshake_error",
                           "AuditInputError": "tls_peer_certificate_invalid"}
            _require(tls["outcome"] == failure_map.get(tls["error_type"], "tls_transport_error"),
                     "TLS failure class")
        http = row["http"]
        if tls["outcome"] == "tls_success":
            _require(type(http) is dict and set(http) == set(empty_http(0)),
                     "HTTP receipt fields")
            _require(http.get("index") == i, "HTTP index")
            http_policy = dict(policy, max_p95_ms=None)
            outcome = _replay_observation(http, method=policy["method"], policy=http_policy)
        else:
            _require(http is None, "HTTP request after refused TLS")
            outcome = tls["outcome"]
        _require(row["outcome"] == outcome, "combined outcome")
    summary, verdict = _summary(rows, policy)
    _require(doc.get("summary") == summary and doc.get("verdict") == verdict,
             "independent summary and verdict")
    return {"schema": "cantos.operational-https-joint-verification/1",
            "original_receipt_sha256": expected_sha256,
            "endpoint": doc["endpoint"], "host": host,
            "recomputed_summary": summary, "verdict": verdict,
            "custody": "external_sha256_verified_and_single_connection_replayed"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    a = sub.add_parser("collect")
    a.add_argument("--url", required=True)
    a.add_argument("--allow-host", required=True)
    a.add_argument("--method", choices=("HEAD", "GET"), default="GET")
    a.add_argument("--samples", type=int, default=1)
    a.add_argument("--timeout-seconds", type=float, default=3.)
    a.add_argument("--max-body-bytes", type=int, default=65536)
    a.add_argument("--expected-body-sha256")
    a.add_argument("--expected-leaf-sha256")
    a.add_argument("--min-remaining-days", type=float, default=14.)
    a.add_argument("--min-success-fraction", type=float, default=1.)
    a.add_argument("--max-p95-ms", type=float)
    a.add_argument("--output", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("--receipt", type=Path, required=True)
    v.add_argument("--expected-receipt-sha256", required=True)
    v.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == "collect":
            record = audit(args.url, allow_host=args.allow_host, method=args.method,
                           samples=args.samples, timeout_seconds=args.timeout_seconds,
                           max_body_bytes=args.max_body_bytes,
                           expected_body_sha256=args.expected_body_sha256,
                           expected_leaf_sha256=args.expected_leaf_sha256,
                           min_remaining_days=args.min_remaining_days,
                           min_success_fraction=args.min_success_fraction,
                           max_p95_ms=args.max_p95_ms)
        else:
            record = verify(args.receipt.read_bytes(), args.expected_receipt_sha256)
        with args.output.open("xb") as fp:
            fp.write(canonical(record))
        print(json.dumps({"verdict": record["verdict"], "output": str(args.output),
                          "sha256": sha256(canonical(record)).hexdigest()}))
        return 0 if record["verdict"] == "pass" else 2
    except (AuditInputError, OSError, ValueError, TypeError, KeyError) as exc:
        print("Joint HTTPS audit rejected: " + str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
