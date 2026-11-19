#!/usr/bin/env python3
"""Bounded read-only storage integrity observation for explicitly owned files.

Tests a client's present readback path and expected content identities, not
durability, redundancy, provider availability or recovery from faults. Offline
replay verifies receipt consistency and does not authenticate its collector.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import time

SCHEMA = "cantos.storage-readback/1"
PLAN_SCHEMA = "cantos.storage-readback-plan/1"
MAX_FILES = 32
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
HEX = frozenset("0123456789abcdef")
# A Windows pathlib fallback would traverse reparse points between validation
# and open; fail closed until a native handle-based secure collector is qualified.
SECURE_DIRFD = (os.open in os.supports_dir_fd
                and bool(getattr(os, "O_NOFOLLOW", 0))
                and bool(getattr(os, "O_DIRECTORY", 0)))


class StorageAuditError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def require(condition, message):
    if not condition:
        raise StorageAuditError(message)


def digest(value):
    return type(value) is str and len(value) == 64 and all(c in HEX for c in value)


def validate_plan(plan):
    require(type(plan) is dict and set(plan) == {"schema", "entries", "samples"},
            "plan fields")
    require(plan["schema"] == PLAN_SCHEMA, "plan schema")
    entries = plan["entries"]
    samples = plan["samples"]
    require(type(entries) is list and 1 <= len(entries) <= MAX_FILES, "entry count")
    require(type(samples) is int and 1 <= samples <= 3, "samples")
    seen, total = set(), 0
    for entry in entries:
        require(type(entry) is dict and set(entry) == {"path", "bytes", "sha256"},
                "entry fields")
        path, size, sha = entry["path"], entry["bytes"], entry["sha256"]
        require(type(path) is str and 1 <= len(path) <= 500
                and "\x00" not in path and "\\" not in path, "entry path")
        parts = PurePosixPath(path)
        require(not parts.is_absolute() and len(parts.parts) > 0
                and all(p not in ("", ".", "..") for p in path.split("/"))
                and parts.as_posix() == path, "unsafe relative path")
        require(path not in seen, "duplicate entry")
        seen.add(path)
        require(type(size) is int and 0 <= size <= MAX_FILE_BYTES, "size ceiling")
        require(digest(sha), "SHA-256 identity")
        total += size * samples
    require(total <= MAX_TOTAL_BYTES, "total read budget")
    return plan


def root_fd(root):
    require(SECURE_DIRFD, "secure POSIX directory-descriptor traversal unavailable")
    raw = Path(root)
    require(raw.is_absolute(), "absolute owned root required")
    require(raw.exists() and raw.is_dir() and not raw.is_symlink(),
            "owned root must be a real directory")
    require(raw.resolve() == raw, "owned root must not be redirected")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return os.open(str(raw), flags)


def _read_one(base_fd, entry):
    # Each component is opened relative to an already open directory; a
    # symlink in any intermediate or final component is rejected.
    fd = os.dup(base_fd)
    file_fd = None
    try:
        parts = entry["path"].split("/")
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        for part in parts[:-1]:
            next_fd = os.open(part, directory_flags | nofollow, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        file_fd = os.open(parts[-1], os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0), dir_fd=fd)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            return {"status": "unreadable", "error_type": "non_regular_file",
                    "bytes": None, "sha256": None}
        if before.st_size > MAX_FILE_BYTES:
            return {"status": "unreadable", "error_type": "file_over_budget",
                    "bytes": None, "sha256": None}
        size, h = 0, hashlib.sha256()
        while True:
            chunk = os.read(file_fd, min(65536, MAX_FILE_BYTES + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                return {"status": "unreadable", "error_type": "file_over_budget",
                        "bytes": None, "sha256": None}
            h.update(chunk)
        after = os.fstat(file_fd)
        reopened = os.open(parts[-1], os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0), dir_fd=fd)
        try:
            final = os.fstat(reopened)
        finally:
            os.close(reopened)
        identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        if not (identity(before) == identity(after) == identity(final)):
            return {"status": "changed_during_read", "error_type": None,
                    "bytes": size, "sha256": h.hexdigest()}
        actual = h.hexdigest()
        return {"status": "match" if size == entry["bytes"] and actual == entry["sha256"] else "mismatch",
                "error_type": None, "bytes": size, "sha256": actual}
    except OSError as exc:
        return {"status": "unreadable", "error_type": type(exc).__name__,
                "bytes": None, "sha256": None}
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(fd)


def collect(root, plan):
    plan = validate_plan(plan)
    fd = root_fd(root)
    try:
        observations = []
        for entry in plan["entries"]:
            for sample in range(plan["samples"]):
                observed_at = datetime.now(timezone.utc).isoformat()
                start = time.monotonic_ns()
                result = _read_one(fd, entry)
                duration_ms = round((time.monotonic_ns() - start) / 1e6, 3)
                observations.append({"path": entry["path"], "sample": sample,
                                     "observed_at": observed_at, "elapsed_ms": duration_ms,
                                     **result})
    finally:
        os.close(fd)
    passed = sum(o["status"] == "match" for o in observations)
    return {"schema": SCHEMA, "plan_sha256": hashlib.sha256(canonical(plan)).hexdigest(),
            "plan": plan, "root": str(root), "observations": observations,
            "summary": {"passed": passed, "total": len(observations),
                        "verdict": "pass" if passed == len(observations) else "fail"},
            "evidence_class": "observed_local_readback",
            "not_measured": ["device durability", "remote provider SLA",
                             "recovery under fault", "whole-system throughput",
                             "independent collector authenticity"]}


def verify(report, plan):
    validate_plan(plan)
    require(type(report) is dict and report.get("schema") == SCHEMA, "receipt schema")
    require(report.get("plan_sha256") == hashlib.sha256(canonical(plan)).hexdigest(),
            "source plan digest")
    require(report.get("plan") == plan, "source plan bytes")
    rows = report.get("observations")
    require(type(rows) is list and len(rows) == len(plan["entries"]) * plan["samples"],
            "observation population")
    matches = 0
    for i, row in enumerate(rows):
        entry = plan["entries"][i // plan["samples"]]
        require(type(row) is dict and set(row) == {"path", "sample", "observed_at",
                  "elapsed_ms", "status", "error_type", "bytes", "sha256"}, "row fields")
        require(row["path"] == entry["path"] and row["sample"] == i % plan["samples"],
                "sample identity and ordering")
        require(type(row["observed_at"]) is str and len(row["observed_at"]) <= 64,
                "sample timestamp")
        try:
            ts = datetime.fromisoformat(row["observed_at"])
            require(ts.utcoffset() is not None and ts.utcoffset().total_seconds() == 0,
                    "UTC observation timestamp")
        except ValueError as exc:
            raise StorageAuditError("invalid timestamp") from exc
        n = row["elapsed_ms"]
        require(type(n) in (int, float) and math.isfinite(n) and n >= 0,
                "invalid read time")
        status = row["status"]
        require(status in ("match", "mismatch", "unreadable", "changed_during_read"),
                "invalid observation status")
        if status == "unreadable":
            require(row["bytes"] is None and row["sha256"] is None
                    and type(row["error_type"]) is str, "unreadable receipt")
        else:
            require(row["error_type"] is None and type(row["bytes"]) is int
                    and 0 <= row["bytes"] <= MAX_FILE_BYTES and digest(row["sha256"]),
                    "readback receipt")
            computed_match = row["bytes"] == entry["bytes"] and row["sha256"] == entry["sha256"]
            require(status != "match" or computed_match, "falsified successful readback")
            require(status != "mismatch" or not computed_match,
                    "inconsistent mismatch classification")
        matches += status == "match"
    summary = report.get("summary")
    require(summary == {"passed": matches, "total": len(rows),
                       "verdict": "pass" if matches == len(rows) else "fail"},
            "summary disagreement")
    require(report.get("evidence_class") == "observed_local_readback", "evidence class")
    return {"verified_receipt_sha256": hashlib.sha256(canonical(report)).hexdigest(),
            "verdict": summary["verdict"], "samples": len(rows),
            "replay_scope": "receipt consistency, not collector authentication or fresh device read"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="operation", required=True)
    run = sub.add_parser("collect")
    run.add_argument("--root", required=True)
    run.add_argument("--plan", required=True)
    run.add_argument("--output", required=True)
    replay = sub.add_parser("verify")
    replay.add_argument("--plan", required=True)
    replay.add_argument("--receipt", required=True)
    args = p.parse_args()
    try:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        if args.operation == "collect":
            output = Path(args.output)
            require(not output.resolve().is_relative_to(Path(args.root).resolve()),
                    "receipt must live outside audited tree")
            report = collect(Path(args.root), plan)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(canonical(report) + b"\n")
            print(json.dumps({"verdict": report["summary"]["verdict"],
                              "receipt": str(output), "samples": report["summary"]["total"]}))
            return 0 if report["summary"]["verdict"] == "pass" else 2
        report = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
        result = verify(report, plan)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["verdict"] == "pass" else 2
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print("storage readback audit: " + str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
