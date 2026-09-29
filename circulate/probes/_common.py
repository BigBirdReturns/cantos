"""Shared plumbing for circulate probes (stdlib only).

Every probe module exposes run(ctx) -> ProbeResult. A probe body is a function
body(ctx, work) -> dict(observed=..., expected=..., notes=..., status=optional) and is wrapped by
execute(), which times it, hashes the frozen files before and after, converts exceptions
into FAIL, and never lets a probe leave its temp directory behind.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
CIRCULATE = HERE.parent
ROOT = CIRCULATE.parent          # the axm-tools checkout (main/)
SESSIONS = ROOT.parent / "sessions" / "public-tail-20260929"

# Files no probe may move. Paths are relative to ROOT.
FROZEN = [
    "clustermax-challenge/retrospective/plan.json",
    "clustermax-challenge/retrospective/PLAN.md",
    "clustermax-challenge/retrospective/results/R1-result.json",
    "clustermax-challenge/retrospective/results/R1-result.md",
    "clustermax-challenge/retrospective/plan-R2.json",
    "clustermax-challenge/retrospective/PLAN-R2.md",
    "clustermax-challenge/retrospective/results/R2-result.json",
    "clustermax-challenge/retrospective/results/R2-result.md",
    "research-desk/app.html",
    "hot-aisle/data/run3/record.json",
    "hot-aisle/data/run3/evidence.json",
]


class Assertion(Exception):
    """A probe observation contradicted the contract's 'must observe' column."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def frozen_hashes(root: Path = ROOT) -> dict:
    out = {}
    for rel in FROZEN:
        p = root / rel
        out[rel] = sha256_file(p) if p.is_file() else None
    return out


def ctx_root(ctx) -> Path:
    return Path((ctx or {}).get("root") or ROOT)


def need(cond, message):
    if not cond:
        raise Assertion(message)


def run_cmd(args, cwd=None, env=None, timeout=300, input_bytes=None):
    """subprocess.run with captured text output; never raises on nonzero exit."""
    e = dict(os.environ)
    e.update(env or {})
    e.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    p = subprocess.run([str(a) for a in args], cwd=str(cwd) if cwd else None, env=e, capture_output=True,
                       timeout=timeout, input=input_bytes)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def flip_byte_in_json_value(raw: bytes, needle: bytes) -> bytes:
    """Flip one byte (a digit or hex digit) shortly after the first occurrence of needle, keeping
    the file well-formed JSON, so the failure has to come from the integrity check and not the parser."""
    i = raw.find(needle)
    need(i >= 0, "tamper anchor not found: %r" % needle)
    j = i + len(needle)
    while j < len(raw) and raw[j:j + 1] not in b"0123456789abcdef":
        j += 1
    need(j < len(raw), "no flippable digit after anchor")
    b = bytearray(raw)
    b[j] = ord("0") if b[j] != ord("0") else ord("1")
    return bytes(b)


def execute(name, body, ctx=None):
    ctx = ctx or {}
    started = time.time()
    res = {"name": name, "status": "PASS", "started_utc": utc_now(), "finished_utc": None, "seconds": None,
           "observed": {}, "expected": None, "notes": "", "error": None}
    root = ctx_root(ctx)
    before = frozen_hashes(root)
    work = Path(tempfile.mkdtemp(prefix="circ-" + name.split("_")[0] + "-"))
    try:
        out = body(ctx, work) or {}
        for k in ("observed", "expected", "notes"):
            if k in out:
                res[k] = out[k]
        if out.get("status"):
            res["status"] = out["status"]
        if out.get("error"):
            res["error"] = out["error"]
    except Assertion as e:
        res["status"] = "FAIL"
        res["error"] = str(e)
    except Exception as e:  # a broken probe is a FAIL, never a silent pass
        res["status"] = "FAIL"
        res["error"] = "%s: %s" % (type(e).__name__, e)
        res["notes"] = (res["notes"] + "\n" if res["notes"] else "") + traceback.format_exc(limit=6)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    after = frozen_hashes(root)
    moved = sorted(k for k in before if before[k] != after[k])
    if isinstance(res["observed"], dict):
        res["observed"]["frozen_files_checked"] = len(before)
        res["observed"]["frozen_files_moved"] = moved
    if moved:
        res["status"] = "FAIL"
        res["error"] = ((res["error"] + " | ") if res["error"] else "") + "frozen files moved during probe: " + ", ".join(moved)
    res["finished_utc"] = utc_now()
    res["seconds"] = round(time.time() - started, 3)
    return res


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
