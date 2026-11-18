"""Run supported operations, retaining observations and deterministic results.

The adapters keep their native evidence and acceptance rules. This module owns
only execution bookkeeping and reuse of the same computation, never standing.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
from datetime import datetime, timezone
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import types
import uuid

HERE = Path(__file__).resolve().parent
ADAPTERS = {
    "provider-intake": "task_sources",
    "benchmark-import": "task_sources",
    "run-recompute": "task_results",
    "run-diagnose": "task_diagnose",
    "output-contract": "task_contract",
    "record-change": "task_changes",
    "source-correction": "task_changes",
    "tier-plan": "task_tiers",
    "pool-purchase": "task_pool",
    "maintainer-observe": "task_maintainer",
    "maintainer-compare": "task_maintainer",
}
OBSERVATION_TASKS = frozenset({"maintainer-observe"})

# A cold caller can discover the existing operations without a conversation.
# These descriptions are navigation; adapters and native owners enforce rules.
TASK_HELP = {
    "provider-intake": {"source": "provider JSONL or retained Vast Search Offers JSON", "optional": ["offer_id", "price_scenario", "availability_review", "marketplace_snapshot"],
                        "supports": "Retain offers, calculate conditional price scenarios and review dated availability observations."},
    "benchmark-import": {"source": "native backfill manifest JSON", "optional": [],
                         "supports": "Import retained benchmark artifacts with their provenance."},
    "run-recompute": {"source": "retained Run 3 arm directory", "optional": [],
                      "supports": "Rejoin retained grading and recompute deadline acceptance."},
    "run-diagnose": {"source": "retained Run 3 arm directory", "optional": [],
                     "supports": "Partition correct-but-late requests and classify delivered solutions statically; no generated code runs."},
    "output-contract": {"source": "retained Run 3 arm directory", "optional": [],
                        "supports": "Propose substring repair candidates for syntax-invalid raw outputs and pin the grader input; no grading, no execution."},
    "record-change": {"source": "qualified workload record JSON", "required": ["change"],
                      "supports": "Recalculate, reassess or identify minimal new execution through the native owner."},
    "source-correction": {"source": "Research Desk history JSON", "required": ["change"],
                          "supports": "Apply a correction and preserve affected dependencies and historical reports."},
    "tier-plan": {"source": "second-run/knot-spec@1 JSON", "required": ["evidence"],
                  "optional": ["seats", "availability", "local_models", "supply"],
                  "supports": "Join supplied native Tier-Bench evidence to model and seat plans; planning only."},
    "pool-purchase": {"source": "capital/pool-request@1 JSON", "required": ["offers"],
                      "optional": ["availability_review", "marketplace_snapshot"],
                      "supports": "Pool member GPU demand onto whole offer units at staged list price; arithmetic only, no quote or agreement."},
    "maintainer-observe": {"source": "cantos.maintainer.spec/1 JSON", "required": ["arm", "observation_id"],
                           "supports": "Explicitly collect a streamed workload observation from one configured endpoint, or reuse the same retained observation epoch."},
    "maintainer-compare": {"required": ["baseline", "candidate", "policy"],
                           "optional": ["baseline_grades", "candidate_grades"],
                           "supports": "Compare retained maintainer observations under the supplied policy, including price changes, without inference."},
}


def catalog():
    return {"schema": "second-run/work-catalog@1",
            "operations": [{"task_class": name, "adapter": "integration/" + adapter + ".py",
                            "adapter_available": (HERE / (adapter + ".py")).is_file(),
                            **TASK_HELP[name]} for name, adapter in ADAPTERS.items()],
            "request": {"shape": {"tasks": [{"id": "caller-label", "task_class": "one listed class", "source": "artifact path"}]},
                        "path_basis": "Input paths are relative to the request file; absolute paths also work.",
                        "optional_metadata": ["actor"],
                        "from_record": {"id": "caller-label", "from_record": {
                            "source": "Research Desk packet path", "record_id": "judgment-id", "revision": 1}},
                        "binding": "The claim/conclusion data.work holds a native task without id/actor and its exact computation_key; the current native dependency closure must remain valid. Optional inputs relocate identical source bytes."},
            "run": "python -B integration/work.py --request REQUEST.json --store RESULT_DIRECTORY",
            "examples": ["integration/examples/work.json", "integration/examples/maintainer-work.json", "integration/WORK.md", "integration/WORK.md#retained-judgment-procedure-handoff"],
            "result": "Read tasks[].result for native output; task status executed/reused does not grant standing.",
            "reuse": "The same declared inputs, procedure bytes and runtime reuse one verified computation across callers.",
            "catalog_effects": {"model_calls": 0, "gpu_runs": 0, "resource_acquisition": False},
            "effects": {"model_calls": "Only explicit maintainer-observe tasks issue inference requests.",
                        "gpu_runs": "A remote endpoint does not establish GPU execution; receipt counters preserve unknowns.",
                        "resource_acquisition": False}}


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
    options = {"execution_context": payload.get("execution_context")} if task_class.startswith("maintainer-") else {}
    prepared = adapter.prepare(task, Path(payload["base"]).resolve(), **options)
    before = snapshot(prepared, task_class)
    if payload["action"] == "describe":
        return before
    if payload.get("expected_key") != before["key"]:
        raise ValueError("Inputs changed between preparation and execution; prepare again")
    result = prepared["execute"]()
    after = snapshot(adapter.prepare(task, Path(payload["base"]).resolve(), **options), task_class)
    if before["identity"] != after["identity"]:
        raise ValueError("Inputs or procedure changed during execution; result is not reusable")
    return {**before, "value": result}


def call_worker(task, base, action, expected_key=None, execution_context=None):
    payload = {"task": task, "base": str(base), "action": action, "expected_key": expected_key,
               "execution_context": execution_context}
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


def write_new_atomic(path, value):
    """Publish a complete maintainer envelope without replacing an earlier one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".work-publish-",
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        # A same-directory hard link atomically creates the final name, refuses
        # an existing result, and exposes only the complete fsynced bytes.
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
    if description["identity"]["task_class"].startswith("maintainer-"):
        # A checksum on a path string does not qualify its external evidence.
        # Retained observations retain and verify their entire raw-artifact closure.
        adapter_path = HERE / "task_maintainer.py"
        validator = types.ModuleType("retained_maintainer_validator")
        validator.__file__ = str(adapter_path)
        exec(compile(adapter_path.read_bytes(), str(adapter_path), "exec"), validator.__dict__)
        validator.verify_artifacts(entry["value"])
    return entry


def execute_task(task, base, store, expected_key=None, effect_state=None):
    if effect_state is None:
        effect_state = {"model_calls": 0, "gpu_runs": 0, "new_observations": 0}
    if "from_record" in task:
        import research_handoff
        binding = research_handoff.resolve(task, base, ADAPTERS)
        output = execute_task(binding["task"], binding["base"], store, binding["expected_key"], effect_state)
        research_handoff.verify_unchanged(binding, task, base, ADAPTERS)
        return {**output, "knowledge": binding["knowledge"]}
    started = time.perf_counter()
    description = call_worker(task, base, "describe")
    if expected_key is not None and description["key"] != expected_key:
        raise ValueError("Retained procedure binding differs from current inputs, code or runtime; revise the judgment and binding explicitly")
    path = store / "results" / (description["key"] + ".json")
    if path.exists():
        entry = read_cache(path, description)
        status = "reused"
    else:
        context = None
        if task["task_class"].startswith("maintainer-"):
            context = {"artifact_dir": str(store / "artifacts" / description["key"])}
        if task["task_class"] in OBSERVATION_TASKS:
            # Claim before the first external request. An uncertain observation
            # is retained for recovery, never replayed under the same identity.
            claim = store / "observation-claims" / (description["key"] + ".json")
            try:
                write_new(claim, {"schema": "second-run/observation-claim@1",
                                 "claimed_at": datetime.now(timezone.utc).isoformat(),
                                 "key": description["key"], "observation_id": task["observation_id"],
                                 "identity": description["identity"], **context})
            except FileExistsError as exc:
                raise ValueError("Observation already claimed without a terminal result; inspect retained claim/artifacts before selecting an explicit new observation_id: " + str(claim)) from exc
            effect_state.update(model_calls=None, gpu_runs=None)
        output = call_worker(task, base, "execute", description["key"], context)
        if task["task_class"] in OBSERVATION_TASKS:
            effect_state.update(model_calls=output["value"].get("inference_requests"),
                                gpu_runs=None, new_observations=1)
        entry = {"schema": "second-run/computation@1", "key": output["key"],
                 "identity": output["identity"], "value": output["value"],
                 "value_sha256": digest(encoded(output["value"])),
                 "standing": "computation-only; native result dispositions remain unchanged"}
        try:
            publish = write_new_atomic if task["task_class"].startswith("maintainer-") else write_new
            publish(path, entry)
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
    effects = {"model_calls": 0, "gpu_runs": 0, "new_observations": 0}
    observation = {}
    if task["task_class"] in OBSERVATION_TASKS:
        observation = {"observation": {"id": entry["value"]["observation_id"],
                                       "status": "newly-observed" if status == "executed" else "retained-observation",
                                       "observed_at": entry["value"].get("observed_at"),
                                       "receipt": entry["value"]["receipt"]}}
        if status == "executed":
            effects = {"model_calls": entry["value"].get("inference_requests"),
                       "gpu_runs": None, "new_observations": 1}
    if task["task_class"] == "maintainer-compare":
        observation = {"native_verdict": entry["value"]["verdict"]["verdict"],
                       "native_exit_code": entry["value"]["verdict"]["exit_code"],
                       "verdict_receipt": entry["value"]["receipt"]}
    return {"id": task["id"], "actor": task.get("actor"), "task_class": task["task_class"],
            "status": status, "key": entry["key"], "result": str(path),
            "value_sha256": entry["value_sha256"], "inputs": description["locations"],
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            **effects, **observation}


def resolve_task_references(task, completed):
    """Allow comparison inputs to use earlier terminal results in this request."""
    if task.get("task_class") != "maintainer-compare":
        return task
    resolved = copy.deepcopy(task)
    for name in ("baseline", "candidate"):
        value = resolved.get(name)
        if isinstance(value, dict):
            if set(value) != {"task"} or not isinstance(value["task"], str):
                raise ValueError(name + " reference must contain only a prior task ID")
            prior = next((r for r in completed if r["id"] == value["task"]), None)
            if prior is None or prior["status"] not in ("executed", "reused"):
                raise ValueError(name + " observation dependency has no successful prior result: " + value["task"])
            if prior["task_class"] != "maintainer-observe":
                raise ValueError(name + " reference must select a maintainer-observe task")
            resolved[name] = prior["result"]
    return resolved


def run(request, base, store, fresh=None):
    if not isinstance(request, dict) or set(request) != {"tasks"}:
        raise ValueError("Request must contain only the tasks array")
    tasks = request.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("Request needs a nonempty tasks array")
    ids = [t.get("id") if isinstance(t, dict) else None for t in tasks]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Task IDs must be nonempty and unique within this request")
    store = Path(store).resolve()
    request = copy.deepcopy(request)
    tasks = request["tasks"]
    fresh_epoch = None
    if fresh is not None and fresh is not False:
        if not any(t.get("task_class") in OBSERVATION_TASKS for t in tasks):
            raise ValueError("--fresh requires at least one explicit observation task")
        fresh_epoch = ("fresh-" + uuid.uuid4().hex) if fresh is True or fresh == "" else fresh
        if not isinstance(fresh_epoch, str) or not fresh_epoch.strip():
            raise ValueError("fresh observation identity must be a nonempty string")
        for task in tasks:
            if task.get("task_class") in OBSERVATION_TASKS:
                task["observation_id"] = fresh_epoch
    request_path = store / "requests" / (uuid.uuid4().hex + ".json")
    write_new(request_path, {"schema": "second-run/work-request@1", "base": str(Path(base).resolve()),
                             "request": request, "fresh_observation_id": fresh_epoch,
                             "recorded_at": datetime.now(timezone.utc).isoformat()})
    results = []
    for task in tasks:
        effects = {"model_calls": 0, "gpu_runs": 0, "new_observations": 0}
        try:
            resolved = resolve_task_references(task, results)
            results.append(execute_task(resolved, Path(base).resolve(), store, effect_state=effects))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            results.append({"id": task["id"], "task_class": task.get("task_class"),
                            "status": "held", "reason": str(exc),
                            **effects})
    summary = {kind: sum(r["status"] == kind for r in results) for kind in ("executed", "reused", "held")}
    receipt = {"schema": "second-run/work-run@1", "observed_at": datetime.now(timezone.utc).isoformat(),
               "tasks": results, "summary": summary,
               "model_calls": None if any(r["model_calls"] is None for r in results) else sum(r["model_calls"] for r in results),
               "gpu_runs": None if any(r["gpu_runs"] is None for r in results) else sum(r["gpu_runs"] for r in results),
               "new_observations": sum(r.get("new_observations", 0) for r in results),
               "request_record": str(request_path), "fresh_observation_id": fresh_epoch,
               "scope": "Retained deterministic work plus explicitly selected maintainer observations. Reused observations preserve their original dates; reuse never denotes a fresh measurement or institutional standing."}
    receipt_path = store / "runs" / (uuid.uuid4().hex + ".json")
    write_new(receipt_path, receipt)
    return {**receipt, "receipt": str(receipt_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--store", type=Path)
    parser.add_argument("--catalog", action="store_true", help="Print available task classes and artifact contracts; no execution")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--fresh", nargs="?", const="", metavar="OBSERVATION_ID",
                        help="Collect new explicit observation tasks under a recorded epoch. Supply the same ID to recover/reuse that epoch after reconnecting.")
    parser.add_argument("--require-maintainer-pass", action="store_true",
                        help="Return the native comparison exit code: 0 pass, 1 regression, 2 incomparable, 3 error; held tasks also fail.")
    args = parser.parse_args()
    if args.catalog:
        if args.request or args.store or args.worker or args.fresh is not None or args.require_maintainer_pass:
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
        result = run(json.loads(args.request.read_bytes()), args.request.resolve().parent, args.store, fresh=args.fresh)
        sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
        if args.require_maintainer_pass:
            verdicts = [t["native_exit_code"] for t in result["tasks"] if "native_exit_code" in t]
            if not verdicts or result["summary"]["held"]:
                return 3
            return max(verdicts)
        return 1 if result["summary"]["held"] else 0
    except (OSError, ValueError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
