"""Prepare bounded changes for existing native record and research owners."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
HELPER = HERE / "change_owner.cjs"
APP = ROOT / "research-desk/app.html"
COMMON_KEYS = {"id", "task_class", "actor", "source", "change"}
CHANGE_KEYS = {
    "price": {"rate", "gpus", "extra"},
    "gates": {"ttft", "e2e", "queue", "quality"},
    "requirements": {"min_accepted_per_s", "max_p95_ttft_ms", "max_p95_e2e_ms", "max_failure_rate"},
    "traffic": {"concurrency", "model", "dataset", "input_len", "output_len", "num_prompts", "request_rate", "backend"},
    "runtime": {"model_revision", "precision", "tokenizer_revision", "runtime_digest", "cache_policy"},
    "evaluator": {"criterion_id"},
}
PATCH_KEYS = {"title", "summary", "tier", "disposition", "deps", "data"}


def only_keys(value, permitted, label):
    if not isinstance(value, dict):
        raise ValueError(label + " must be an object")
    extra = set(value) - permitted
    if extra:
        raise ValueError(label + " has unsupported fields: " + ", ".join(sorted(extra)))


def prepare(task, base):
    only_keys(task, COMMON_KEYS, "task")
    task_class = task.get("task_class")
    if task_class not in ("record-change", "source-correction"):
        raise ValueError("Unsupported change task class: " + str(task_class))
    source = task.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source must name a retained JSON file")
    source = Path(source)
    if not source.is_absolute():
        source = Path(base) / source
    source = source.resolve()
    change = task.get("change")
    if task_class == "record-change":
        only_keys(change, set(CHANGE_KEYS), "change")
        if not change:
            raise ValueError("Nothing changed")
        for key, value in change.items():
            only_keys(value, CHANGE_KEYS[key], "change." + key)
            if not value:
                raise ValueError("change." + key + " must declare at least one changed input")
    else:
        only_keys(change, {"record_id", "patch", "timestamp"}, "change")
        if not isinstance(change.get("record_id"), str) or not change["record_id"].strip():
            raise ValueError("change.record_id is required")
        only_keys(change.get("patch"), PATCH_KEYS, "change.patch")
        if not change["patch"]:
            raise ValueError("change.patch is empty")
        if "timestamp" in change and not isinstance(change["timestamp"], str):
            raise ValueError("change.timestamp must be an explicit timestamp string")
    # Round-trip rejects non-JSON values and separates caller mutations from prepared work.
    change = json.loads(json.dumps(change, allow_nan=False))
    inputs = {"source": source, "change_adapter": Path(__file__), "native_helper": HELPER}
    if task_class == "record-change":
        inputs.update({"native_" + name: ROOT / "hot-aisle/runner/lib" / (name + ".cjs")
                       for name in ("revalidate", "record", "engine")})
        inputs["native_report_engine"] = ROOT / "hot-aisle/index.html"
        app_pin = None
    else:
        inputs["native_research_core"] = APP
        app_pin = hashlib.sha256(APP.read_bytes()).hexdigest()
    parameters = {"task_class": task_class, "change": change}
    if task_class == "source-correction":
        parameters["timestamp_policy"] = "explicit change.timestamp, otherwise inherited last input-event timestamp; not a fresh observation time"

    def execute():
        payload = {"task_class": task_class, "source": str(source), "change": change,
                   "expected_app_sha256": app_pin}
        completed = subprocess.run(["node", str(HELPER)],
            input=json.dumps(payload, ensure_ascii=False, allow_nan=False),
            capture_output=True, text=True, encoding="utf-8")
        if completed.returncode:
            raise ValueError("Native change owner refused: " + completed.stderr.strip())
        return json.loads(completed.stdout)

    return {"parameters": parameters, "inputs": inputs, "execute": execute}
