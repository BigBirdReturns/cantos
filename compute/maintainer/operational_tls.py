#!/usr/bin/env python3
"""Explicitly authorized TLS certificate audit with independently pinned offline replay.

Direct TLS handshakes only, no HTTP requests, proxy use, inference, provisioning,
certificate trust override or provider-wide security assurance. Python/OpenSSL
validates the live peer chain and hostname; replay independently checks the
retained leaf DER, validity dates, fingerprint, policy and verdict. Replay does
not repeat the trust-path validation or authenticate a collector's provenance.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import socket
import ssl
import sys
import time
from urllib.parse import urlsplit

if __package__:
    from .operational_http import AuditInputError
else:
    from operational_http import AuditInputError

_HEX = frozenset("0123456789abcdef")
_HOST = re.compile(r"[a-z0-9][a-z0-9.-]{0,252}\Z")
_MAX_DER = 32768


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditInputError("invalid TLS audit: " + message)


def _digest(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in _HEX for c in value)


def _number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _utc(value: object) -> datetime:
    _require(type(value) is str and len(value) <= 40, "timestamp")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AuditInputError("invalid TLS audit timestamp") from exc
    _require(dt.utcoffset() is not None and dt.utcoffset().total_seconds() == 0,
             "timestamp must be UTC")
    return dt


def _tlv(raw: bytes, offset: int, expected: int | None = None) -> tuple[int, int, int, int]:
    """Bounded definite-length DER field: tag, content-start, content-end, next."""
    _require(0 <= offset < len(raw) and offset + 2 <= len(raw), "truncated DER field")
    tag, initial = raw[offset], raw[offset + 1]
    pos = offset + 2
    if initial & 0x80:
        count = initial & 0x7f
        _require(1 <= count <= 4 and pos + count <= len(raw), "invalid DER length")
        _require(raw[pos] != 0, "nonminimal DER length")
        size = int.from_bytes(raw[pos:pos + count], "big")
        _require(size >= 128, "nonminimal DER length")
        pos += count
    else:
        size = initial
    end = pos + size
    _require(end <= len(raw), "truncated DER value")
    if expected is not None:
        _require(tag == expected, "unexpected DER certificate field")
    return tag, pos, end, end


def _cert_time(tag: int, value: bytes) -> datetime:
    try:
        s = value.decode("ascii")
        if tag == 0x17:
            _require(len(s) == 13 and s.endswith("Z") and s[:12].isdigit(),
                     "invalid UTCTime")
            yy = int(s[:2])
            year = (1900 if yy >= 50 else 2000) + yy
            remainder = s[2:12]
        elif tag == 0x18:
            _require(len(s) == 15 and s.endswith("Z") and s[:14].isdigit(),
                     "invalid GeneralizedTime")
            year = int(s[:4])
            remainder = s[4:14]
        else:
            raise AuditInputError("invalid certificate time tag")
        return datetime(year, int(remainder[:2]), int(remainder[2:4]),
                        int(remainder[4:6]), int(remainder[6:8]),
                        int(remainder[8:10]), tzinfo=timezone.utc)
    except (ValueError, UnicodeError) as exc:
        raise AuditInputError("invalid certificate validity time") from exc


def certificate_validity(der: bytes) -> tuple[datetime, datetime]:
    """Read the X.509 TBSCertificate Validity ASN.1 sequence, without a third-party parser."""
    _require(type(der) is bytes and 0 < len(der) <= _MAX_DER, "certificate DER size")
    _, outer, outer_end, next_outer = _tlv(der, 0, 0x30)
    _require(next_outer == len(der), "trailing certificate data")
    _, tbs, tbs_end, cursor = _tlv(der, outer, 0x30)
    _require(cursor <= outer_end, "invalid TBSCertificate")
    tag, _, _, after = _tlv(der, tbs)
    if tag == 0xa0:  # Explicit X.509 version, absent in v1 certificates.
        tbs = after
    for expected in (0x02, 0x30, 0x30):  # serial, signature, issuer
        _, _, _, tbs = _tlv(der, tbs, expected)
    _, validity, end, after = _tlv(der, tbs, 0x30)
    _require(after <= tbs_end, "invalid validity boundary")
    first_tag, first_start, first_end, nxt = _tlv(der, validity)
    second_tag, second_start, second_end, nxt2 = _tlv(der, nxt)
    _require(nxt2 == end, "invalid validity sequence")
    not_before = _cert_time(first_tag, der[first_start:first_end])
    not_after = _cert_time(second_tag, der[second_start:second_end])
    _require(not_before < not_after, "reversed certificate validity")
    return not_before, not_after


def validate_origin(url: str, allow_host: str | None) -> tuple[str, int]:
    _require(type(url) is str and len(url) <= 2048, "URL")
    try:
        parsed = urlsplit(url)
        host, port = parsed.hostname, parsed.port
    except ValueError as exc:
        raise AuditInputError("invalid TLS audit origin") from exc
    _require(parsed.scheme == "https" and host is not None and parsed.netloc != "",
             "HTTPS origin required")
    _require(not parsed.username and not parsed.password
             and parsed.path in ("", "/") and not parsed.query and not parsed.fragment,
             "TLS audit accepts an HTTPS origin, not credentials, path or query")
    _require(type(allow_host) is str and bool(allow_host), "exact --allow-host required")
    _require(_HOST.fullmatch(host.lower()) is not None
             and _HOST.fullmatch(allow_host.lower()) is not None
             and host.lower() == allow_host.lower(), "unauthorized DNS host")
    _require(port is None or 1 <= port <= 65535, "invalid HTTPS port")
    return host, 443 if port is None else port


def _fetch_leaf(host: str, port: int, timeout: float) -> bytes:
    context = ssl.create_default_context()
    _require(context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname,
             "default TLS verification unavailable")
    # Direct socket and SNI: no environment proxy and no redirect.
    with socket.create_connection((host, port), timeout=timeout) as tcp:
        with context.wrap_socket(tcp, server_hostname=host) as peer:
            der = peer.getpeercert(binary_form=True)
            parsed = peer.getpeercert()
            _require(type(der) is bytes and bool(parsed), "missing verified peer cert")
            _, end = certificate_validity(der)
            _require(int(end.timestamp()) == ssl.cert_time_to_seconds(parsed["notAfter"]),
                     "peer certificate time mismatch")
            return der


def _evaluate(der: bytes, checked: datetime, expected: str | None,
              min_days: float) -> tuple[str, dict]:
    before, after = certificate_validity(der)
    fingerprint = sha256(der).hexdigest()
    days = round((after - checked).total_seconds() / 86400, 6)
    if checked < before or checked > after:
        result = "tls_certificate_outside_validity"
    elif expected is not None and fingerprint != expected:
        result = "tls_leaf_pin_mismatch"
    elif (after - checked).total_seconds() < min_days * 86400:
        result = "tls_certificate_expiring"
    else:
        result = "tls_success"
    return result, {
        "leaf_der_base64": base64.b64encode(der).decode("ascii"),
        "leaf_sha256": fingerprint,
        "valid_from_utc": before.isoformat(),
        "valid_until_utc": after.isoformat(),
        "remaining_days": days,
    }


def audit(url: str, *, allow_host: str, samples: int = 1, timeout_seconds: float = 3.0,
          min_remaining_days: float = 14., expected_leaf_sha256: str | None = None) -> dict:
    host, port = validate_origin(url, allow_host)
    _require(type(samples) is int and 1 <= samples <= 8, "sample count")
    _require(_number(timeout_seconds) and 0.1 <= timeout_seconds <= 10, "timeout")
    _require(_number(min_remaining_days) and 0 <= min_remaining_days <= 365,
             "certificate remaining-days threshold")
    _require(expected_leaf_sha256 is None or _digest(expected_leaf_sha256),
             "expected certificate SHA-256")
    rows = []
    for i in range(samples):
        t0 = time.monotonic_ns()
        der, error_type = None, None
        failure = None
        try:
            der = _fetch_leaf(host, port, timeout_seconds)
        except ssl.SSLCertVerificationError as exc:
            error_type, failure = type(exc).__name__, "tls_verification_failed"
        except ssl.SSLError as exc:
            error_type, failure = type(exc).__name__, "tls_handshake_error"
        except (OSError, TimeoutError) as exc:
            error_type, failure = type(exc).__name__, "tls_transport_error"
        except AuditInputError as exc:
            error_type, failure = type(exc).__name__, "tls_peer_certificate_invalid"
        checked = datetime.now(timezone.utc)
        row = {"index": i, "checked_at_utc": checked.isoformat(),
               "elapsed_ms": round((time.monotonic_ns() - t0) / 1_000_000, 3),
               "error_type": error_type}
        if der is not None:
            result, identity = _evaluate(der, checked, expected_leaf_sha256,
                                         min_remaining_days)
            row.update(identity)
            row["outcome"] = result
        else:
            row.update({"leaf_der_base64": None, "leaf_sha256": None,
                        "valid_from_utc": None, "valid_until_utc": None,
                        "remaining_days": None, "outcome": failure})
        rows.append(row)
    counts = dict(sorted(Counter(row["outcome"] for row in rows).items()))
    successes = counts.get("tls_success", 0)
    return {
        "schema": "cantos.operational-tls-observation/1",
        "evidence_class": "observed_direct_client_vantage",
        "origin": url,
        "host": host,
        "port": port,
        "tls_validation": "python_default_CA_hostname_SNI",
        "policy": {"samples": samples, "timeout_seconds": timeout_seconds,
                   "min_remaining_days": min_remaining_days,
                   "expected_leaf_sha256": expected_leaf_sha256},
        "observations": rows,
        "summary": {"attempts": samples, "successes": successes,
                    "outcome_counts": counts,
                    "p95_handshake_elapsed_ms":
                        sorted(row["elapsed_ms"] for row in rows)[math.ceil(.95 * samples) - 1]},
        "verdict": "pass" if successes == samples else "fail",
        "limits": [
            "One client vantage and bounded samples; not continuous availability or a provider SLA",
            "The live default CA and hostname check is not repeated by offline DER replay",
            "The pinned receipt verifies exact captured bytes and recomputation, not independent collector custody",
            "Leaf identity and expiry do not establish application behavior or full provider security posture"
        ],
    }


def verify(raw: bytes, pin: str) -> dict:
    _require(_digest(pin), "external receipt SHA-256")
    _require(0 < len(raw) <= 500000, "receipt size")
    _require(sha256(raw).hexdigest() == pin, "external receipt hash mismatch")
    try:
        doc = json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (ValueError, UnicodeError) as exc:
        raise AuditInputError("invalid TLS receipt JSON") from exc
    _require(type(doc) is dict and doc.get("schema") == "cantos.operational-tls-observation/1",
             "receipt schema")
    _require(doc.get("evidence_class") == "observed_direct_client_vantage"
             and doc.get("tls_validation") == "python_default_CA_hostname_SNI",
             "transport evidence class")
    policy = doc.get("policy")
    _require(type(policy) is dict and set(policy) ==
             {"samples", "timeout_seconds", "min_remaining_days", "expected_leaf_sha256"},
             "policy fields")
    samples, timeout, min_days, expected = (
        policy["samples"], policy["timeout_seconds"],
        policy["min_remaining_days"], policy["expected_leaf_sha256"])
    _require(type(samples) is int and 1 <= samples <= 8, "sample count")
    _require(_number(timeout) and 0.1 <= timeout <= 10, "timeout")
    _require(_number(min_days) and 0 <= min_days <= 365, "remaining-days threshold")
    _require(expected is None or _digest(expected), "expected certificate hash")
    host, port = validate_origin(doc.get("origin"), doc.get("host"))
    _require(port == doc.get("port"), "origin port")
    rows = doc.get("observations")
    _require(type(rows) is list and len(rows) == samples, "observation count")
    verdicts, latencies = [], []
    for idx, row in enumerate(rows):
        _require(type(row) is dict and row.get("index") == idx and type(row["index"]) is int,
                 "sample index")
        checked = _utc(row.get("checked_at_utc"))
        elapsed = row.get("elapsed_ms")
        _require(_number(elapsed) and elapsed >= 0, "handshake duration")
        latencies.append(elapsed)
        encoded = row.get("leaf_der_base64")
        error = row.get("error_type")
        if encoded is not None:
            _require(error is None and type(encoded) is str and len(encoded) <= 50000,
                     "leaf evidence")
            try:
                der = base64.b64decode(encoded, validate=True)
            except (ValueError, base64.binascii.Error) as exc:
                raise AuditInputError("invalid TLS receipt DER encoding") from exc
            result, expected_fields = _evaluate(der, checked, expected, min_days)
            for key, value in expected_fields.items():
                _require(row.get(key) == value, "leaf " + key)
        else:
            _require(type(error) is str and 1 <= len(error) <= 80, "transport error class")
            for field in ("leaf_sha256", "valid_from_utc", "valid_until_utc", "remaining_days"):
                _require(row.get(field) is None, "transport failure has certificate identity")
            failure_map = {"SSLCertVerificationError": "tls_verification_failed",
                           "SSLError": "tls_handshake_error",
                           "AuditInputError": "tls_peer_certificate_invalid"}
            result = failure_map.get(error, "tls_transport_error")
        _require(row.get("outcome") == result, "observation outcome")
        verdicts.append(result)
    successes = verdicts.count("tls_success")
    summary = {
        "attempts": samples,
        "successes": successes,
        "outcome_counts": dict(sorted(Counter(verdicts).items())),
        "p95_handshake_elapsed_ms": sorted(latencies)[math.ceil(.95 * samples) - 1]
    }
    _require(doc.get("summary") == summary, "summary recomputation")
    verdict = "pass" if successes == samples else "fail"
    _require(doc.get("verdict") == verdict, "verdict recomputation")
    return {"schema": "cantos.operational-tls-verification/1",
            "original_receipt_sha256": pin, "origin": doc["origin"],
            "recomputed_summary": summary, "verdict": verdict,
            "custody": "independently_pinned_receipt_leaf_DER",
            "limit": "Offline replay cannot repeat CA trust or hostname validation"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    live = sub.add_parser("collect", help="Authorized direct TLS certificate observations")
    live.add_argument("--url", required=True, help="HTTPS origin, without path/query")
    live.add_argument("--allow-host", required=True, help="Exact authorized DNS hostname")
    live.add_argument("--samples", type=int, default=1)
    live.add_argument("--timeout-seconds", type=float, default=3.0)
    live.add_argument("--min-remaining-days", type=float, default=14.0)
    live.add_argument("--expected-leaf-sha256")
    live.add_argument("--output", type=Path)
    replay = sub.add_parser("verify", help="Offline replay of externally pinned receipt")
    replay.add_argument("--receipt", type=Path, required=True)
    replay.add_argument("--expected-receipt-sha256", required=True)
    replay.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "collect":
            result = audit(args.url, allow_host=args.allow_host, samples=args.samples,
                           timeout_seconds=args.timeout_seconds,
                           min_remaining_days=args.min_remaining_days,
                           expected_leaf_sha256=args.expected_leaf_sha256)
        else:
            result = verify(args.receipt.read_bytes(), args.expected_receipt_sha256)
        data = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as dst:
                dst.write(data)
        else:
            print(data, end="")
        return 0 if result["verdict"] == "pass" else 1
    except (AuditInputError, OSError) as exc:
        print("TLS audit failed: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
