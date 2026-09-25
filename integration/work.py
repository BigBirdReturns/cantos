"""Run existing deterministic operations, retaining results by task class and inputs.

The adapters keep their native evidence and acceptance rules. This module owns
only execution bookkeeping and reuse of the same computation, never standing.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
ADAPTERS = {
    "provider-intake": "task_sources",
    "benchmark-import": "task_sources",
    "run-recompute": "task_results",
    "record-change": "task_changes",
    "source-correction": "task_changes",
    "tier-plan": "task_tiers",
}

# A cold caller can discover the existing operations without a conversation.
# These descriptions are navigation; adapters and native owners enforce rules.
TASK_HELP = {
    "provider-intake": {"source": "provider JSONL", "optional": ["offer_id", "price_scenario"],
                        "supports": "Retain offers and calculate conditional price scenarios."},
    "benchmark-import": {"source": "native backfill manifest JSON", "optional": [],
                         "supports": "Import retained benchmark artifacts with their provenance."},
    "run-recompute": {"source": "retained Run 3 arm directory", "optional": [],
                      "supports": "Rejoin retained grading and recompute deadline acceptance."},
    "record-change": {"source": "qualified workload record JSON", "required": ["change"],
                      "supports": "Recalculate, reassess or identify minimal new execution through the native owner."},
    "source-correction": {"source": "Research Desk history JSON", "required": ["change"],
                          "supports": "Apply a correction and preserve affected dependencies and historical reports."},
    "tier-plan": {"source": "second-run/knot-spec@1 JSON", "required": ["evidence"],
                  "optional": ["seats", "availability", "local_models"],
                  "supports": "Join supplied native Tier-Bench evidence to model and seat plans; planning only."},
}


def catalog():
    return {"schema": "second-run/work-catalog@1",
            "operations": [{"task_class": name, "adapter": "integration/" + adapter + ".py",
                            **TASK_HELP[name]} for name, adapter in ADAPTERS.items()],
            "request": {"shape": {"tasks": [{"id": "caller-label", "task_class": "one listed class", "source": "artifact path"}]},
                        "path_basis": "Input paths are relative to the request file; absolute paths also work.",
                        "optional_metadata": ["actor"]},
            "run": "python -B integration/work.py --request REQUEST.json --store RESULT_DIRECTORY",
            "examples": ["integration/examples/work.json", "integration/WORK.md"],
            "result": "Read tasks[].result for native output; task status executed/reused does not grant standing.",
            "reuse": "The same declared inputs, procedure bytes and runtime reuse one verified computation across callers.",
            "effects": {"model_calls": 0, "gpu_runs": 0, "resource_acquisition": False}}


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def snapshot(prepared, task_class):
    dependencies = {}
    locations = {}
    inputs = {**prepared["inputs"], "operation_runner": Path(__file__)}
    for role, path in sorted(inputs.items()):
        if path is None:
            dependencies[role] = None
            locations[role] = None
        else:
            path = Path(path).resolve()
            dependencies[role] = file_digest(path)
            locations[role] = str(path)
    runtime = {"python": platform.python_version(), "implementation": platform.python_implementation()}
    if task_class in ("record-change", "source-correction"):
        runtime["node"] = subprocess.check_output(["node", "--version"], text=True).strip()
    identity = {"task_class": task_class, "parameters": prepared["parameters"],
                "dependencies": dependencies, "runtime": runtime}
    return {"identity": identity, "key": digest(encoded(identity)), "locations": locations}


def worker(payload):
    """Each description/execution uses a fresh process and native owner imports."""
    task = payload["task"]
    task_class = task.get("task_class")
    if task_class not in ADAPTERS:
        raise ValueError("Unsupported task class: " + str(task_class))
    adapter = importlib.import_module(ADAPTERS[task_class])
    prepared = adapter.prepare(task, Path(payload["base"]).resolve())
    before = snapshot(prepared, task_class)
    if payload["action"] == "describe":
        return before
    if payload.get("expected_key") != before["key"]:
        raise ValueError("Inputs changed between preparation and execution; prepare again")
    result = prepared["execute"]()
    after = snapshot(adapter.prepare(task, Path(payload["base"]).resolve()), task_class)
    if before["identity"] != after["identity"]:
        raise ValueError("Inputs or procedure changed during execution; result is not reusable")
    return {**before, "value": result}


def call_worker(task, base, action, expected_key=None):
    payload = {"task": task, "base": str(base), "action": action, "expected_key": expected_key}
    # -B alone still reads old .pyc files. A fresh, unwritten cache prefix makes
    # every worker load the source bytes whose hashes enter the identity.
    cache_prefix = Path(base) / (".work-no-bytecode-" + uuid.uuid4().hex)
    proc = subprocess.run([sys.executable, "-B", "-X", "pycache_prefix=" + str(cache_prefix),
                           str(Path(__file__).resolve()), "--worker"],
                          input=encoded(payload), capture_output=True)
    try:
        response = json.loads(proc.stdout)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Owner process returned no usable response: " + proc.stderr.decode(errors="replace")[-1500:]) from exc
    if proc.returncode or not response.get("ok"):
        raise ValueError(response.get("error", "Owner process failed"))
    return response["result"]


def write_new(path, value):
    """Never overwrite an earlier result or run record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(encoded(value) + b"\n")


def read_cache(path, description):
    entry = json.loads(path.read_bytes())
    if not isinstance(entry, dict):
        raise ValueError("Retained computation must be an object; original retained, recompute into a separate store")
    if entry.get("identity") != description["identity"] or entry.get("key") != description["key"]:
        raise ValueError("Retained computation does not match its requested dependencies")
    if digest(encoded(entry.get("value"))) != entry.get("value_sha256"):
        raise ValueError("Retained computation checksum failed; original retained, recompute into a separate store")
    if entry.get("schema") != "second-run/computation@1":
        raise ValueError("Unsupported retained computation format")
    return entry


def execute_task(task, base, store):
    started = time.perf_counter()
    description = call_worker(task, base, "describe")
    path = store / "results" / (description["key"] + ".json")
    if path.exists():
        entry = read_cache(path, description)
        status = "reused"
    else:
        output = call_worker(task, base, "execute", description["key"])
        entry = {"schema": "second-run/computation@1", "key": output["key"],
                 "identity": output["identity"], "value": output["value"],
                 "value_sha256": digest(encoded(output["value"])),
                 "standing": "computation-only; native result dispositions remain unchanged"}
        try:
            write_new(path, entry)
        except FileExistsError:
            prior = read_cache(path, description)
            if prior["value_sha256"] != entry["value_sha256"]:
                raise ValueError("Same inputs produced different results; retain and investigate before reuse")
        status = "executed"
    # Recheck dependencies even for a cache hit; file freshness is not inferred
    # from retrieval today, mtime or an unchanged filename.
    after = call_worker(task, base, "describe")
    if after["identity"] != description["identity"]:
        raise ValueError("Inputs changed while reading the retained result; prepare again")
    return {"id": task["id"], "actor": task.get("actor"), "task_class": task["task_class"],
            "status": status, "key": entry["key"], "result": str(path),
            "value_sha256": entry["value_sha256"], "inputs": description["locations"],
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "model_calls": 0, "gpu_runs": 0}


def run(request, base, store):
    if not isinstance(request, dict) or set(request) != {"tasks"}:
        raise ValueError("Request must contain only the tasks array")
    tasks = request.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("Request needs a nonempty tasks array")
    ids = [t.get("id") if isinstance(t, dict) else None for t in tasks]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Task IDs must be nonempty and unique within this request")
    store = Path(store).resolve()
    results = []
    for task in tasks:
        try:
            results.append(execute_task(task, Path(base).resolve(), store))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            results.append({"id": task["id"], "task_class": task.get("task_class"),
                            "status": "held", "reason": str(exc),
                            "model_calls": 0, "gpu_runs": 0})
    summary = {kind: sum(r["status"] == kind for r in results) for kind in ("executed", "reused", "held")}
    receipt = {"schema": "second-run/work-run@1", "observed_at": datetime.now(timezone.utc).isoformat(),
               "tasks": results, "summary": summary, "model_calls": 0, "gpu_runs": 0,
               "scope": "Deterministic local procedures only. Reuse means identical declared computation, not source truth, current rental availability or accepted institutional standing."}
    receipt_path = store / "runs" / (uuid.uuid4().hex + ".json")
    write_new(receipt_path, receipt)
    return {**receipt, "receipt": str(receipt_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--store", type=Path)
    parser.add_argument("--catalog", action="store_true", help="Print available task classes and artifact contracts; no execution")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.catalog:
        if args.request or args.store or args.worker:
            parser.error("--catalog is separate from --request, --store and --worker")
        sys.stdout.buffer.write(json.dumps(catalog(), ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
        return 0
    if args.worker:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                result = worker(json.load(sys.stdin.buffer))
            sys.stdout.buffer.write(encoded({"ok": True, "result": result}) + b"\n")
            return 0
        except Exception as exc:
            sys.stdout.buffer.write(encoded({"ok": False, "error": type(exc).__name__ + ": " + str(exc)}) + b"\n")
            return 1
    if args.request is None or args.store is None:
        parser.error("--request and --store are required")
    try:
        result = run(json.loads(args.request.read_bytes()), args.request.resolve().parent, args.store)
        sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
        return 1 if result["summary"]["held"] else 0
    except (OSError, ValueError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
