#!/usr/bin/env python3
"""Shared stdlib helpers for the ledger lane: observation classification, manifests, temp dirs, clocks."""
import contextlib
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

# Acquisition attempts: real create / provision actions that could have delivered a seat.
# Lane C writes delivered rows with one of these methods and layer "delivered".
ATTEMPT_METHODS = ("api-create", "console-create", "tui-provision")
# Listings: the provider said yes/no to a query. Never an attempt, never in the delivered denominator.
LISTING_METHODS = ("api", "console-plan-list", "tui-provision-list", "prior-session-note")
LISTED_OUTCOMES = ("available", "out_of_capacity", "out_of_stock")   # "unknown" is excluded and counted separately
LEGACY_METHOD_MAP = {"tui-provision-list": "tui-provision", "console-create": "console-create", "api": "api-create"}


def parse_iso(s):
    if "." in s:
        return datetime.strptime(s.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z")
    return datetime.strptime(s.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def any_iso(s):
    """Accept 'Z' or '+00:00' forms (run3 writes isoformat with +00:00) and return the 'Z' whole-second form."""
    if s is None:
        return None
    s = s.strip()
    if s.endswith("Z"):
        return iso(parse_iso(s))
    return iso(datetime.fromisoformat(s))


def classify_observation(o):
    """Return 'delivered' (a real attempt), 'listed' (a probe), or None (ignored: synthetic / unknown shape).

    New rows carry `layer`. Legacy rows (2026-09-23 seed) carry only `method`; a legacy row is an
    attempt only if its method is a create method or it is a TUI provision that actually delivered."""
    if not isinstance(o, dict) or o.get("synthetic"):
        return None
    layer = o.get("layer")
    if layer in ("delivered", "listed"):
        return layer
    m = o.get("method")
    if m in ATTEMPT_METHODS or m == "create-attempt":
        return "delivered"
    if m == "tui-provision-list" and o.get("provisioned") is True:
        return "delivered"
    if m in LISTING_METHODS:
        return "listed"
    return None


def attempt_from_observation(o, source=None):
    """Normalize one delivered observation into the ledger's acquisition.attempts item shape."""
    method = o.get("method")
    if method == "tui-provision-list":
        method = "tui-provision"
    elif method == "create-attempt":
        method = None   # transitional lane C name; the builder must be told which real method it was
    return {
        "ts": o["ts"], "provider": o["provider"], "region": o.get("region"), "sku": o["sku"],
        "layer": "delivered", "method": method, "outcome": o.get("outcome"),
        "provisioned": bool(o.get("provisioned") or o.get("ssh_reached")),
        "time_to_ssh_s": o.get("time_to_ssh_s"), "attempt_id": o.get("attempt_id"), "note": o.get("note") or o.get("evidence"),
        "source": source,
    }


def read_manifest(path):
    out = {}
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            parts = ln.rstrip("\n").split("  ", 1)
            if len(parts) == 2 and SHA_RE.match(parts[0]):
                out[parts[1].lstrip("*")] = parts[0]
    return out


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_manifest(directory, manifest):
    """{name: (expected_sha, actual_sha or None)}; actual None when the file is missing."""
    out = {}
    for name, expected in manifest.items():
        p = os.path.join(directory, name)
        out[name] = (expected, sha256_file(p) if os.path.exists(p) else None)
    return out


RECEIPT_KINDS = [
    (re.compile(r"^cell-.*\.json$"), "cell"), (re.compile(r"^cell-.*\.log$"), "log"),
    (re.compile(r"^env\.normalized\.json$"), "env_normalized"), (re.compile(r"^env\.json$"), "env"),
    (re.compile(r"^image(-inspect)?\.(txt|json)$"), "image"), (re.compile(r"^MANIFEST\.sha256$"), "manifest"),
    (re.compile(r"^serve.*\.log$"), "serve_log"), (re.compile(r".*\.log$"), "log"),
    (re.compile(r"^detailed\.json$"), "engine_output"), (re.compile(r"^(grade/)?(evaluation|.*sidecar).*\.json$"), "evaluation"),
    (re.compile(r"^ledger-times\.json$"), "clocks"), (re.compile(r"^ledger\.json$"), "arm_summary"),
    (re.compile(r"^(invocation|tasks|failure|recovery-failure|container-id|gpu|pull)\.\w+$"), "arm_file"),
    (re.compile(r"^replay/.*$"), "replay"), (re.compile(r"^grade/.*$"), "grade"), (re.compile(r"^smoke-.*\.json$"), "smoke"),
]


def receipt_kind(name):
    for rx, kind in RECEIPT_KINDS:
        if rx.match(name):
            return kind
    return "file"


@contextlib.contextmanager
def tmpdir(prefix="ledger-selftest-"):
    """A scratch directory: the system temp dir, or a lane-local .selftest-<id> when temp is not writable
    (some review sandboxes). Always removed afterwards; never examples/."""
    path = None
    try:
        path = tempfile.mkdtemp(prefix=prefix)
    except (OSError, PermissionError):
        path = os.path.join(HERE, ".selftest-" + uuid.uuid4().hex)
        os.makedirs(path)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def load_jsonl(path):
    out = []
    if path and os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            if ln.strip():
                out.append(json.loads(ln))
    return out
