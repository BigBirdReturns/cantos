#!/usr/bin/env python3
"""Bounded, source-described HTTP operational observations from one client vantage.

A successful probe is not a provider SLA, network capacity, or security certification.
Only explicit endpoints may be examined. This collector never sends model requests.
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
from urllib.request import HTTPRedirectHandler, Request, build_opener


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
          timeout_seconds: float = 3.0, min_success_fraction: float = 1.0,
          max_p95_ms: float | None = None) -> dict:
    validate_target(url, allow_host)
    if not 1 <= samples <= 30:
        raise AuditInputError("samples must be between 1 and 30")
    if not 0.1 <= timeout_seconds <= 10.0:
        raise AuditInputError("timeout must be between 0.1 and 10 seconds")
    if not 0 <= min_success_fraction <= 1:
        raise AuditInputError("min_success_fraction must be between zero and one")
    if max_p95_ms is not None and (not math.isfinite(max_p95_ms) or max_p95_ms <= 0):
        raise AuditInputError("max_p95_ms must be positive and finite")
    opener = build_opener(NoRedirect())
    observations = []
    for index in range(samples):
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic_ns()
        status, error_type = None, None
        try:
            request = Request(url, method="HEAD", headers={"User-Agent": "Cantos-observed-HTTP-audit/1"})
            with opener.open(request, timeout=timeout_seconds) as response:
                status = response.status
        except HTTPError as exc:
            status = exc.code
            exc.close()
        except (URLError, socket.timeout, TimeoutError, ConnectionError, OSError, HTTPException) as exc:
            error_type = type(exc).__name__
        elapsed_ms = round((time.monotonic_ns() - t0) / 1_000_000, 3)
        observations.append({
            "index": index, "utc_start": started, "elapsed_ms": elapsed_ms,
            "http_status": status, "transport_error_type": error_type,
            "outcome": classify(status, error_type is not None),
        })
    latencies = sorted(x["elapsed_ms"] for x in observations)
    p95 = latencies[math.ceil(.95 * len(latencies)) - 1]
    successes = sum(x["outcome"] == "http_success" for x in observations)
    fraction = successes / len(observations)
    passing = fraction >= min_success_fraction and (max_p95_ms is None or p95 <= max_p95_ms)
    receipt_bytes = json.dumps(observations, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {
        "schema": "cantos.operational-http-observation/1",
        "evidence_class": "observed_client_vantage",
        "endpoint": url, "method": "HEAD",
        "redirects_followed": False, "tls_validation": "python_standard_library_defaults",
        "observations_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "policy": {"samples": samples, "timeout_seconds": timeout_seconds,
                   "min_success_fraction": min_success_fraction, "max_p95_ms": max_p95_ms},
        "observations": observations,
        "summary": {"successes": successes, "attempts": samples, "success_fraction": fraction,
                    "p95_client_elapsed_ms": p95,
                    "outcome_counts": dict(sorted(Counter(x["outcome"] for x in observations).items()))},
        "verdict": "pass" if passing else "fail",
        "limits": ["One client vantage and short window; no representative SLA or cloud-provider rating",
                   "HEAD measures endpoint availability, not inference, storage, GPU or application quality",
                   "No network-throughput, lifecycle recovery or remote-host security claim"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--allow-host", help="Exact DNS hostname for authorized public HTTPS endpoint")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=float, default=3.0)
    parser.add_argument("--min-success-fraction", type=float, default=1.0)
    parser.add_argument("--max-p95-ms", type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = audit(args.url, allow_host=args.allow_host, samples=args.samples,
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
