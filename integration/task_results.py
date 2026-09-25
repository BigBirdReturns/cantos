"""Prepare one retained Run 3 recomputation for the common task runner.

The campaign owns recovery, grading joins and deadline arithmetic. This adapter
only declares the bytes those functions read and calls the existing shelf entry.
The caller executes each operation in a fresh Python worker.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent
CAMPAIGN = ROOT / "hot-aisle" / "campaign"
SHELF_VALIDATOR = CAMPAIGN / "shelf" / "validator.py"
OWNER_CODE = {
    "shelf-validator": SHELF_VALIDATOR,
    "run3-grade": CAMPAIGN / "run3" / "grade.py",
    "run3-replay": CAMPAIGN / "run3" / "replay.py",
    "run3-common": CAMPAIGN / "run3" / "common.py",
}
ALLOWED = {"id", "task_class", "actor", "source"}


def prepare(task, base):
    """Return semantic parameters, stable dependency roles and a native call.

    Source locations and request metadata are deliberately absent from semantic
    parameters. Identical copied evidence has identical logical dependency roles.
    Missing or malformed grading maps cannot provide a complete dependency set.
    """
    if not isinstance(task, dict):
        raise ValueError("run-recompute task must be an object")
    extra = set(task) - ALLOWED
    if extra:
        raise ValueError("Unknown run-recompute arguments: " + ", ".join(sorted(extra)))
    if task.get("task_class") != "run-recompute":
        raise ValueError("task_results only handles run-recompute")
    source = task.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("run-recompute source must name a retained arm directory")
    directory = (Path(base) / source).resolve()
    if not directory.is_dir():
        raise ValueError("run-recompute source is not a retained arm directory")

    inputs = {
        "code:task-results": Path(__file__).resolve(),
        **{"code:" + role: path for role, path in OWNER_CODE.items()},
        "replay:plan": directory / "replay" / "plan.json",
        "replay:journal": directory / "replay" / "journal.jsonl",
        "replay:requests": directory / "replay" / "requests.jsonl",
        "tasks": directory / "tasks.json",
        "detailed": directory / "detailed.json",
        "grade:mapping": directory / "grade" / "mapping.json",
        "grade:evaluation": directory / "grade" / "evaluation.json",
    }
    mapping = json.loads(inputs["grade:mapping"].read_bytes())
    datasets = mapping.get("datasets")
    if not isinstance(datasets, dict) or not datasets:
        raise ValueError("retained grading map must contain datasets")
    for dataset in sorted(datasets):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", dataset):
            raise ValueError("grading dataset must be one file-name component")
        for role, suffix in (
            ("samples", ".jsonl"),
            ("reference", "-reference.jsonl"),
            ("evalplus-results", "_eval_results.json"),
        ):
            inputs[f"grade:{dataset}:{role}"] = directory / "grade" / (dataset + suffix)

    def execute():
        # Never substitute aggregate summaries, sidecar masks alone, or a new
        # implementation of the native recover/join/buckets path.
        spec = importlib.util.spec_from_file_location(
            "_task_results_shelf_validator", SHELF_VALIDATOR
        )
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        counts = validator.recompute_retained_run(directory)
        evaluation = json.loads(inputs["grade:evaluation"].read_bytes())
        detailed = json.loads(inputs["detailed"].read_bytes())
        return {
            **counts,
            "unit": "requests",
            "basis": "retained-evidence-recomputation",
            "synthetic": detailed.get("synthetic"),
            "acceptance_contract": {
                "criterion_id": evaluation["criterion_id"],
                "correctness_owner": "hot-aisle/campaign/run3/grade.py:join",
                "deadline_owner": "hot-aisle/campaign/run3/replay.py:buckets",
                "source_sha256": {
                    path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in OWNER_CODE.values()
                },
            },
            "fresh_evalplus_execution": False,
            "new_gpu_run": False,
            "authority_promoted": False,
        }

    return {"parameters": {}, "inputs": inputs, "execute": execute}
