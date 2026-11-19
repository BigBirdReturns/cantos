#!/usr/bin/env python3
"""Read-only, identity-bound Linux process-continuity samples for owned services.

Observation captures process identity at sample instants, not uptime between
samples, an HTTP health check, restart SLA, or authenticated collector custody.
Never sends signals to a target or changes its workload or service configuration.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time

PLAN_SCHEMA = "cantos.process-continuity-plan/1"
SCHEMA = "cantos.process-continuity/1"
HEX = frozenset("0123456789abcdef")


class ContinuityError(ValueError):
    pass


def require(value, message):
    if not value:
        raise ContinuityError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def valid_hash(value):
    return type(value) is str and len(value) == 64 and all(c in HEX for c in value)


def validate_plan(plan):
    require(type(plan) is dict and set(plan) ==
            {"schema", "pidfile", "executable", "samples", "interval_ms"}, "plan fields")
    require(plan["schema"] == PLAN_SCHEMA, "plan schema")
    require(type(plan["samples"]) is int and 2 <= plan["samples"] <= 128, "sample budget")
    require(type(plan["interval_ms"]) is int and 20 <= plan["interval_ms"] <= 5000,
            "sample interval")
    require((plan["samples"] - 1) * plan["interval_ms"] <= 120000,
            "total duration budget")
    for key in ("pidfile", "executable"):
        s = plan[key]
        require(type(s) is str and 1 <= len(s) <= 500
                and "\x00" not in s and Path(s).is_absolute()
                and ".." not in Path(s).parts, key + " absolute path")
    return plan


def _pidfile(path):
    # Walk every parent from a pinned directory descriptor, refusing symlinks
    # in each component. A realpath precheck alone is racy if a parent moves.
    # Never import command lines, environment variables or process memory.
    require(sys.platform.startswith("linux") and hasattr(os, "O_NOFOLLOW"),
            "Linux no-follow directory support required")
    parts = Path(path).parts
    require(Path(path).is_absolute() and len(parts) >= 2, "PID path invalid")
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    parent_fd = os.open("/", dir_flags)
    try:
        for component in parts[1:-1]:
            next_fd = os.open(component, dir_flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = next_fd
        fd = os.open(parts[-1], file_flags, dir_fd=parent_fd)
    finally:
        os.close(parent_fd)
    try:
        st = os.fstat(fd)
        require(stat.S_ISREG(st.st_mode), "PID file is not regular")
        require(st.st_uid == os.geteuid(), "PID file is not owned by observer")
        raw = os.read(fd, 32)
        require(re.fullmatch(rb"[1-9][0-9]{0,6}\n?", raw) is not None,
                "PID file is not a bounded numeric PID")
        return int(raw)
    finally:
        os.close(fd)


def _process(pid):
    # /proc/PID/stat's comm may contain spaces and closing parentheses.
    raw = Path("/proc") / str(pid) / "stat"
    data = raw.read_text(encoding="utf-8")
    close = data.rfind(")")
    require(close > 0, "invalid proc stat")
    fields = data[close + 2:].split()
    require(len(fields) >= 20, "truncated proc stat")
    require(fields[0] not in ("Z", "X", "x"), "dead process")
    start = int(fields[19])  # Linux field 22, starttime in clock ticks.
    require(start > 0, "invalid process start")
    exe = os.readlink("/proc/" + str(pid) + "/exe")
    return start, exe


def observe(plan):
    path = plan["pidfile"]
    try:
        pid = _pidfile(path)
    except FileNotFoundError:
        return "missing", None, None, None, "pidfile_missing"
    except (OSError, ValueError):
        return "unreadable", None, None, None, "pidfile_invalid_or_unreadable"
    try:
        start, exe = _process(pid)
    except (FileNotFoundError, ProcessLookupError):
        return "missing", pid, None, None, "process_missing"
    except (OSError, ValueError):
        return "unreadable", pid, None, None, "process_unreadable"
    if exe != plan["executable"]:
        return "wrong_executable", pid, start, exe, "executable_identity_mismatch"
    return "observed", pid, start, exe, None


def summarize(rows):
    identities = {(r["pid"], r["start_ticks"], r["executable"])
                  for r in rows if r["status"] == "observed"}
    observed = sum(r["status"] == "observed" for r in rows)
    missing = sum(r["status"] == "missing" for r in rows)
    unreadable = sum(r["status"] == "unreadable" for r in rows)
    wrong = sum(r["status"] == "wrong_executable" for r in rows)
    verdict = ("observed_transition" if len(identities) > 1 else
               "stable_observed" if observed == len(rows) else "incomplete")
    return {"observed": observed, "missing": missing, "unreadable": unreadable,
            "wrong_executable": wrong, "distinct_matching_identities": len(identities),
            "total": len(rows), "verdict": verdict}


def collect(plan):
    validate_plan(plan)
    require(sys.platform.startswith("linux")
            and Path("/proc/sys/kernel/random/boot_id").is_file(),
            "Linux procfs observation required")
    require(os.path.realpath(plan["pidfile"]) == plan["pidfile"],
            "PID file path may not traverse symlinks")
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    require(re.fullmatch(r"[0-9a-f-]{36}", boot) is not None, "boot identity unavailable")
    clock = time.monotonic()
    rows = []
    for index in range(plan["samples"]):
        due = clock + index * plan["interval_ms"] / 1000
        time.sleep(max(0, due - time.monotonic()))
        instant = time.monotonic()
        status, pid, start, exe, error = observe(plan)
        rows.append({"index": index,
                     "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                     "elapsed_ms": round((instant - clock) * 1000, 3),
                     "status": status, "pid": pid, "start_ticks": start,
                     "executable": exe, "error_type": error})
    require(Path("/proc/sys/kernel/random/boot_id").read_text().strip() == boot,
            "host boot identity changed during observation")
    return {"schema": SCHEMA, "plan": plan,
            "plan_sha256": sha256(canonical(plan)).hexdigest(),
            "boot_id": boot, "rows": rows, "summary": summarize(rows),
            "evidence_class": "observed_owned_linux_process_samples",
            "not_measured": ["availability between samples", "endpoint health",
                             "provider restart SLA", "collector authenticity",
                             "whole-system energy"]}


def verify(raw_receipt, plan, expected_sha256):
    validate_plan(plan)
    require(valid_hash(expected_sha256), "external receipt SHA256 required")
    require(type(raw_receipt) is bytes and 0 < len(raw_receipt) <= 131072,
            "bounded receipt bytes")
    require(sha256(raw_receipt).hexdigest() == expected_sha256,
            "receipt digest mismatch")
    receipt = json.loads(raw_receipt)
    require(type(receipt) is dict and raw_receipt == canonical(receipt) + b"\n",
            "canonical receipt bytes")
    require(receipt.get("schema") == SCHEMA and receipt.get("plan") == plan
            and receipt.get("plan_sha256") == sha256(canonical(plan)).hexdigest(),
            "plan identity mismatch")
    require(type(receipt.get("boot_id")) is str and
            re.fullmatch(r"[0-9a-f-]{36}", receipt["boot_id"]), "boot identity")
    rows = receipt.get("rows")
    require(type(rows) is list and len(rows) == plan["samples"], "sample population")
    previous_elapsed = -1.
    previous_utc = None
    for i, row in enumerate(rows):
        require(type(row) is dict and set(row) ==
                {"index", "observed_at_utc", "elapsed_ms", "status",
                 "pid", "start_ticks", "executable", "error_type"}, "row fields")
        require(type(row["index"]) is int and row["index"] == i, "sample order")
        try:
            ts = datetime.fromisoformat(row["observed_at_utc"])
            require(ts.utcoffset() is not None and ts.utcoffset().total_seconds() == 0,
                    "UTC timestamp required")
        except (TypeError, ValueError) as exc:
            raise ContinuityError("timestamp invalid") from exc
        require(previous_utc is None or ts >= previous_utc, "UTC regression")
        previous_utc = ts
        elapsed = row["elapsed_ms"]
        require(type(elapsed) in (int, float) and math.isfinite(elapsed) and
                elapsed >= previous_elapsed and elapsed >= 0, "monotonic elapsed")
        previous_elapsed = elapsed
        status = row["status"]
        require(status in ("observed", "missing", "unreadable", "wrong_executable"),
                "unknown sample status")
        if status in ("observed", "wrong_executable"):
            require(type(row["pid"]) is int and 0 < row["pid"] <= 9999999
                    and type(row["start_ticks"]) is int and row["start_ticks"] > 0
                    and type(row["executable"]) is str, "process identity")
            require((row["executable"] == plan["executable"]) ==
                    (status == "observed"), "executable classification")
            require(row["error_type"] is None if status == "observed"
                    else row["error_type"] == "executable_identity_mismatch",
                    "identity error")
        else:
            require(row["start_ticks"] is None and row["executable"] is None
                    and (row["pid"] is None or
                         type(row["pid"]) is int and 0 < row["pid"] <= 9999999)
                    and type(row["error_type"]) is str, "missing/unreadable row")
    require(previous_elapsed <= (plan["samples"] - 1) * plan["interval_ms"] +
            30000, "collection exceeded elapsed time ceiling")
    require(receipt.get("summary") == summarize(rows), "summary mismatch")
    require(receipt.get("evidence_class") ==
            "observed_owned_linux_process_samples", "evidence class")
    require(receipt.get("not_measured") ==
            ["availability between samples", "endpoint health",
             "provider restart SLA", "collector authenticity",
             "whole-system energy"], "scope statement")
    return {"verdict": receipt["summary"]["verdict"],
            "receipt_sha256": expected_sha256,
            "replay_scope": "receipt consistency, not authenticated observation"}


def write_receipt_once(target, payload):
    """Create a private, fsynced receipt exactly once, never replace evidence."""
    require(type(payload) is bytes and 0 < len(payload) <= 131072,
            "bounded receipt bytes")
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return sha256(payload).hexdigest()


def read_receipt_bounded(target):
    """Limit memory use and reject filesystem redirections while replaying."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(target, flags)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= 131072,
                "receipt must be a bounded regular file")
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            payload = stream.read(131073)
    finally:
        if fd >= 0:
            os.close(fd)
    require(len(payload) <= 131072, "receipt size budget")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--plan", required=True)
    c.add_argument("--receipt", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--plan", required=True)
    v.add_argument("--receipt", required=True)
    v.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    try:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        if args.operation == "collect":
            # Exclusivity is enforced by O_EXCL at the write, not a racy exists check.
            result = collect(plan)
            target = Path(args.receipt)
            receipt_sha = write_receipt_once(target, canonical(result) + b"\n")
            print(json.dumps({"verdict": result["summary"]["verdict"],
                              "receipt": str(target),
                              "sha256": receipt_sha}))
            return 0 if result["summary"]["verdict"] == "stable_observed" else 2
        raw = read_receipt_bounded(args.receipt)
        print(json.dumps(verify(raw, plan, args.expected_sha256)))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("process continuity: " + str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
