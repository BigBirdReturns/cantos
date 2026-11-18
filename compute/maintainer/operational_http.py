#!/usr/bin/env python3
"""Bounded, source-described HTTP operational observations from one client vantage.

A successful probe is not a provider SLA, network capacity, or security certification.
Only explicit endpoints may be examined. This collector sends HEAD or bounded GET, never an inference POST.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from http.client import HTTPException
import json
import math
from pathlib import Path
import socket
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class AuditInputError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_target(url: str, allow_host: str | None = None) -> str:
    try:
        target = urlsplit(url)
        hostname = target.hostname
        port = target.port
    except ValueError as exc:
        raise AuditInputError("invalid endpoint") from exc
    if target.scheme not in ("http", "https") or not hostname or not target.netloc:
        raise AuditInputError("an explicit HTTP(S) endpoint is required")
    if target.username or target.password or target.query or target.fragment:
        raise AuditInputError("credentials, query parameters and fragments are prohibited")
    if port is not None and not 1 <= port <= 65535:
        raise AuditInputError("invalid port")
    local = hostname.lower() in ("localhost", "127.0.0.1", "::1")
    if not local and (target.scheme != "https" or hostname.lower() != (allow_host or "").lower()):
        raise AuditInputError("non-loopback probes require HTTPS and an exact --allow-host")
    if allow_host and not local and ("/" in allow_host or ":" in allow_host or "@" in allow_host):
        raise AuditInputError("--allow-host must name one exact DNS host")
    return url


def classify(status: int | None, transport_error: bool) -> str:
    if transport_error:
        return "transport_error"
    if status is None:
        raise ValueError("missing HTTP status")
    if 200 <= status < 300:
        return "http_success"
    if status == 429:
        return "http_throttled"
    if 500 <= status < 600:
        return "http_server_failure"
    if 300 <= status < 400:
        return "http_redirect_not_followed"
    if 400 <= status < 500:
        return "http_client_failure"
    return "http_other"


def audit(url: str, *, allow_host: str | None = None, samples: int = 3,
          method: str = "HEAD", expected_body_sha256: str | None = None,
          max_body_bytes: int = 65536,
          timeout_seconds: float = 3.0, min_success_fraction: float = 1.0,
          max_p95_ms: float | None = None) -> dict:
    validate_target(url, allow_host)
    if method not in ("HEAD", "GET"):
        raise AuditInputError("only HEAD or GET probes are allowed")
    if not isinstance(max_body_bytes, int) or not 1 <= max_body_bytes <= 1_048_576:
        raise AuditInputError("max_body_bytes must be between 1 and 1048576")
    if expected_body_sha256 is not None:
        if method != "GET":
            raise AuditInputError("body identity requires method GET")
        expected_body_sha256 = expected_body_sha256.lower()
        if len(expected_body_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_body_sha256):
            raise AuditInputError("expected_body_sha256 must be a SHA-256 hex digest")
    if not 1 <= samples <= 30:
        raise AuditInputError("samples must be between 1 and 30")
    if not 0.1 <= timeout_seconds <= 10.0:
        raise AuditInputError("timeout must be between 0.1 and 10 seconds")
    if not 0 <= min_success_fraction <= 1:
        raise AuditInputError("min_success_fraction must be between zero and one")
    if max_p95_ms is not None and (not math.isfinite(max_p95_ms) or max_p95_ms <= 0):
        raise AuditInputError("max_p95_ms must be positive and finite")
    # The exact authorized target must be contacted directly, independently of
    # ambient HTTP(S)_PROXY variables that can redirect its network request.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    observations = []
    for index in range(samples):
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic_ns()
        status, error_type = None, None
        body_sha256, body_bytes, declared_content_length = None, None, None
        body_content_encoding = None
        body_over_limit = False
        body_incomplete = False
        try:
            request = Request(url, method=method, headers={
                "User-Agent": "Cantos-observed-HTTP-audit/1",
                "Accept-Encoding": "identity",
            })
            with opener.open(request, timeout=timeout_seconds) as response:
                status = response.status
                if method == "GET" and 200 <= status < 300:
                    # A GET receipt records the bounded HTTP entity bytes returned
                    # by the client library after transfer framing, without
                    # content-decoding. No streamed secrets or raw body are retained.
                    length_header = response.headers.get("Content-Length")
                    if length_header is not None and length_header.isdecimal():
                        declared_content_length = int(length_header)
                    body_content_encoding = response.headers.get("Content-Encoding", "identity")
                    body = response.read(max_body_bytes + 1)
                    body_bytes = len(body)
                    body_over_limit = body_bytes > max_body_bytes or (
                        declared_content_length is not None and declared_content_length > max_body_bytes
                    )
                    body_incomplete = (
                        declared_content_length is not None and body_bytes < declared_content_length
                        and not body_over_limit
                    )
                    if not body_over_limit and not body_incomplete:
                        body_sha256 = hashlib.sha256(body).hexdigest()
        except HTTPError as exc:
            status = exc.code
            exc.close()
        except (URLError, socket.timeout, TimeoutError, ConnectionError, OSError, HTTPException) as exc:
            error_type = type(exc).__name__
        elapsed_ms = round((time.monotonic_ns() - t0) / 1_000_000, 3)
        outcome = classify(status, error_type is not None)
        if outcome == "http_success" and method == "GET":
            if body_over_limit:
                outcome = "http_body_limit_exceeded"
            elif body_incomplete:
                outcome = "http_body_incomplete"
            elif expected_body_sha256 is not None and body_sha256 != expected_body_sha256:
                outcome = "http_body_mismatch"
        observations.append({
            "index": index, "utc_start": started, "elapsed_ms": elapsed_ms,
            "http_status": status, "transport_error_type": error_type,
            "outcome": outcome,
            "body_sha256": body_sha256, "body_bytes": body_bytes,
            "content_length_claim": declared_content_length,
            "content_encoding_claim": body_content_encoding,
        })
    latencies = sorted(x["elapsed_ms"] for x in observations)
    p95 = latencies[math.ceil(.95 * len(latencies)) - 1]
    successes = sum(x["outcome"] == "http_success" for x in observations)
    fraction = successes / len(observations)
    passing = fraction >= min_success_fraction and (max_p95_ms is None or p95 <= max_p95_ms)
    receipt_bytes = json.dumps(observations, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    body_matches = (sum(x["outcome"] == "http_success" for x in observations)
                    if expected_body_sha256 is not None else None)
    if expected_body_sha256 is not None:
        # An explicit identity requirement is an invariant, not a tunable
        # availability percentage. Even a 0% success threshold cannot
        # promote a wrong, truncated or oversized successful HTTP response.
        identity_invalid = {"http_body_mismatch", "http_body_incomplete",
                            "http_body_limit_exceeded"}
        passing = passing and body_matches > 0 and not any(
            x["outcome"] in identity_invalid for x in observations
        )
    return {
        "schema": "cantos.operational-http-observation/1",
        "evidence_class": "observed_client_vantage",
        "endpoint": url, "method": method,
        "redirects_followed": False, "tls_validation": "python_standard_library_defaults",
        "observations_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "policy": {"samples": samples, "timeout_seconds": timeout_seconds,
                   "expected_body_sha256": expected_body_sha256,
                   "max_body_bytes": max_body_bytes,
                   "min_success_fraction": min_success_fraction, "max_p95_ms": max_p95_ms},
        "observations": observations,
        "summary": {"successes": successes, "attempts": samples, "success_fraction": fraction,
                    "body_identity_matches": body_matches,
                    "p95_client_elapsed_ms": p95,
                    "outcome_counts": dict(sorted(Counter(x["outcome"] for x in observations).items()))},
        "verdict": "pass" if passing else "fail",
        "limits": ["One client vantage and short window; no representative SLA or cloud-provider rating",
                   "HEAD measures endpoint availability, not inference, storage, GPU or application quality",
                   "GET hashes bounded HTTP entity bytes; neither server claims nor unsigned receipts authenticate a provider",
                   "No network-throughput, lifecycle recovery or remote-host security claim"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--allow-host", help="Exact DNS hostname for authorized public HTTPS endpoint")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--method", choices=("HEAD", "GET"), default="HEAD")
    parser.add_argument("--expected-body-sha256", help="Required exact content digest for a passing GET")
    parser.add_argument("--max-body-bytes", type=int, default=65536)
    parser.add_argument("--timeout-seconds", type=float, default=3.0)
    parser.add_argument("--min-success-fraction", type=float, default=1.0)
    parser.add_argument("--max-p95-ms", type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = audit(args.url, allow_host=args.allow_host, samples=args.samples,
                       method=args.method, expected_body_sha256=args.expected_body_sha256,
                       max_body_bytes=args.max_body_bytes,
                       timeout_seconds=args.timeout_seconds,
                       min_success_fraction=args.min_success_fraction, max_p95_ms=args.max_p95_ms)
        data = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as file:
                file.write(data)
        else:
            print(data, end="")
        return 0 if result["verdict"] == "pass" else 1
    except (AuditInputError, OSError) as exc:
        print(f"operational audit input/output error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
