"""Diagnose one retained Run 3 arm for the common task runner.

The campaign owns recovery, grading joins and deadline arithmetic; the shelf
validator owns the consistency checks that make a retained arm trustworthy.
This adapter reuses those owners and adds two static, offline observations:

* a partition of correct-but-late requests into dispatch, send-to-first, both
  and combined intervals against the native one-second first-token rule; and
* a classification of every delivered solution as syntax-invalid, syntax-valid
  but grade-failing, correct, or a never-sent placeholder, by dataset.

No generated code is executed, repaired or sanitized. The categories are
observations about retained bytes; they are not proof of repairability or of a
provider, GPU or client cause. Any such attribution needs its own experiment.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import re
import sys


ROOT = Path(__file__).resolve().parent.parent
CAMPAIGN = ROOT / "hot-aisle" / "campaign"
RUN3 = CAMPAIGN / "run3"
SHELF_VALIDATOR = CAMPAIGN / "shelf" / "validator.py"
OWNER_CODE = {
    "shelf-validator": SHELF_VALIDATOR,
    "run3-grade": RUN3 / "grade.py",
    "run3-replay": RUN3 / "replay.py",
    "run3-common": RUN3 / "common.py",
}
ALLOWED = {"id", "task_class", "actor", "source"}
FIRST_TOKEN_LIMIT_S = 1      # replay.buckets: first_token_ts - scheduled_ts <= 1
COMPLETION_LIMIT_S = 60      # replay.buckets: end_ts - scheduled_ts <= 60
BIN_S = 300                  # replay.buckets: five-minute offsets
AST_FEATURE_VERSION = (3, 11)  # the pinned grader image is python:3.11
SCHEMA = "second-run/run-diagnosis@1"


def prepare(task, base):
    """Declare the bytes the diagnosis reads and return the native call."""
    if not isinstance(task, dict):
        raise ValueError("run-diagnose task must be an object")
    extra = set(task) - ALLOWED
    if extra:
        raise ValueError("Unknown run-diagnose arguments: " + ", ".join(sorted(extra)))
    if task.get("task_class") != "run-diagnose":
        raise ValueError("task_diagnose only handles run-diagnose")
    source = task.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("run-diagnose source must name a retained arm directory")
    directory = (Path(base) / source).resolve()
    if not directory.is_dir():
        raise ValueError("run-diagnose source is not a retained arm directory")

    inputs = {
        "code:task-diagnose": Path(__file__).resolve(),
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
        return diagnose(directory)

    return {"parameters": {}, "inputs": inputs, "execute": execute}


def _load(name, path, sibling_path=None):
    """Load a native module privately; grade.py imports its run3 siblings by name."""
    if sibling_path is not None:
        sys.path.insert(0, str(sibling_path))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if sibling_path is not None:
            sys.path.remove(str(sibling_path))
    return module


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _interval(row, start, end):
    if not _number(row.get(start)) or not _number(row.get(end)):
        return None
    return row[end] - row[start]


def _quantiles(values):
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return {"min": ordered[0], "median": median, "max": ordered[-1], "count": len(ordered)}


def late_partition(plan, rows, passed):
    """Partition correct responses that missed the native first-token rule.

    dispatch = send_ts - scheduled_ts (client wait before the request left),
    send_to_first = first_token_ts - send_ts (from send until first token).
    Both are compared against the same one-second limit the acceptance rule uses.
    """
    categories = {"dispatch_only": 0, "send_to_first_only": 0, "both": 0, "combined": 0}
    completion_only = 0
    dispatch_values, send_to_first_values = [], []
    duration = plan["duration_s"]
    bins = {offset: 0 for offset in range(0, math.ceil(duration), BIN_S)}
    unmeasurable = 0
    for row in rows:
        n = row["request_index"]
        if row["error"] or not passed[n]:
            continue
        first = _interval(row, "scheduled_ts", "first_token_ts")
        end = _interval(row, "scheduled_ts", "end_ts")
        if first is None or end is None:
            raise ValueError("successful request timestamps must be finite numbers")
        if first <= FIRST_TOKEN_LIMIT_S:
            if end > COMPLETION_LIMIT_S:
                completion_only += 1
            continue
        dispatch = _interval(row, "scheduled_ts", "send_ts")
        send_to_first = _interval(row, "send_ts", "first_token_ts")
        if dispatch is None or send_to_first is None:
            unmeasurable += 1
            continue
        dispatch_values.append(dispatch)
        send_to_first_values.append(send_to_first)
        late_dispatch = dispatch > FIRST_TOKEN_LIMIT_S
        late_send = send_to_first > FIRST_TOKEN_LIMIT_S
        if late_dispatch and late_send:
            categories["both"] += 1
        elif late_dispatch:
            categories["dispatch_only"] += 1
        elif late_send:
            categories["send_to_first_only"] += 1
        else:
            categories["combined"] += 1
        offset = row["scheduled_ts"] - plan["start_ts"]
        if 0 <= offset < duration:
            bins[int(offset // BIN_S) * BIN_S] += 1
    return {
        "rule": {"first_token_limit_s": FIRST_TOKEN_LIMIT_S, "completion_limit_s": COMPLETION_LIMIT_S,
                 "owner": "hot-aisle/campaign/run3/replay.py:buckets"},
        "segments": {"dispatch": "send_ts - scheduled_ts", "send_to_first": "first_token_ts - send_ts"},
        "correct_first_token_late": sum(categories.values()) + unmeasurable,
        "categories": categories,
        "unmeasurable_send_ts": unmeasurable,
        "correct_completion_late_only": completion_only,
        "bins": [{"offset_s": offset, "duration_s": min(BIN_S, duration - offset), "late": count}
                 for offset, count in sorted(bins.items())],
        "intervals_s": {"dispatch": _quantiles(dispatch_values),
                        "send_to_first": _quantiles(send_to_first_values)},
    }


LINE_SUFFIX = re.compile(r"( on line \d+| \(detected at line \d+\))$")


def _parse_status(solution):
    try:
        ast.parse(solution, feature_version=AST_FEATURE_VERSION)
    except SyntaxError as exc:  # includes IndentationError and TabError
        # Families group by message; the per-sample line number is not a family.
        return "syntax_invalid", f"{type(exc).__name__}: {LINE_SUFFIX.sub('', exc.msg or '')}"
    except (ValueError, RecursionError, MemoryError) as exc:
        return "syntax_invalid", f"{type(exc).__name__}: unparseable"
    return "syntax_valid", None


CLASSES = ("correct", "syntax_valid_grade_failed", "syntax_invalid",
           "never_sent_placeholder", "not_requested_placeholder")
EXTRA_COUNTS = ("samples", "syntax_invalid_with_markdown_fence", "syntax_invalid_finish_length")


def classify_solutions(grade, directory, tasks, rows, passed, mapping):
    """Classify each graded sample by static parse status and retained verdict."""
    by_id = {task["task_id"]: task for task in tasks["tasks"]}
    per_dataset, families, anomalies = {}, {}, []
    solution_matches = True
    for dataset, meta in mapping["datasets"].items():
        samples = grade.jsonl(directory / "grade" / (dataset + ".jsonl"))
        if len(samples) != len(meta["request_indices"]):
            raise ValueError("Sample mapping length mismatch")
        counts = {name: 0 for name in CLASSES}
        fenced_invalid = 0
        length_invalid = 0
        for sample, n in zip(samples, meta["request_indices"]):
            if n is None:
                counts["not_requested_placeholder"] += 1
                continue
            row = rows[n]
            if row["error"]:
                counts["never_sent_placeholder"] += 1
                continue
            if sample["solution"] != by_id[row["task_id"]]["prompt"] + row["output_text"]:
                solution_matches = False
            status, family = _parse_status(sample["solution"])
            if passed[n]:
                counts["correct"] += 1
                if status == "syntax_invalid":
                    anomalies.append({"dataset": dataset, "request_index": n, "family": family,
                                      "note": "graded correct but static parse failed"})
                continue
            if status == "syntax_valid":
                counts["syntax_valid_grade_failed"] += 1
                continue
            counts["syntax_invalid"] += 1
            families[family] = families.get(family, 0) + 1
            if "```" in row["output_text"]:
                fenced_invalid += 1
            if row.get("finish_reason") == "length":
                length_invalid += 1
        counts["samples"] = len(samples)
        counts["syntax_invalid_with_markdown_fence"] = fenced_invalid
        counts["syntax_invalid_finish_length"] = length_invalid
        per_dataset[dataset] = counts
    totals = {name: sum(d[name] for d in per_dataset.values()) for name in (*CLASSES, *EXTRA_COUNTS)}
    return {
        "parser": {"method": "ast.parse", "feature_version": list(AST_FEATURE_VERSION),
                   "python": platform.python_version()},
        "per_dataset": per_dataset,
        "totals": totals,
        "syntax_error_families": dict(sorted(families.items(), key=lambda item: (-item[1], item[0]))),
        "all_solutions_equal_frozen_prompt_plus_raw_output": solution_matches,
        "anomalies": anomalies,
    }


def diagnose(directory):
    validator = _load("_task_diagnose_shelf_validator", SHELF_VALIDATOR)
    # The owner's consistency checks run first; an inconsistent arm raises here.
    counts = validator.recompute_retained_run(directory)
    grade = _load("_task_diagnose_run3_grade", RUN3 / "grade.py", RUN3)
    grade.write_json = lambda path, value: None  # private module; no retained file changes
    replay_dir = directory / "replay"
    plan, rows = grade.recover(replay_dir)
    joined = grade.join(directory / "tasks.json", replay_dir / "requests.jsonl",
                        directory / "detailed.json", directory / "grade", None)
    passed = joined["passed"]
    accepted = sum(bucket["accepted"] for bucket in grade.buckets(plan, rows, passed))
    if accepted != counts["accepted"]:
        raise ValueError("diagnosis acceptance differs from the validator's recomputation")
    tasks = grade.read_json(directory / "tasks.json")
    mapping = grade.read_json(directory / "grade" / "mapping.json")
    detailed = grade.read_json(directory / "detailed.json")
    late = late_partition(plan, rows, passed)
    correct = sum(passed)
    if correct - accepted != late["correct_first_token_late"] + late["correct_completion_late_only"]:
        raise ValueError("late partition does not account for every correct-but-unaccepted request")
    solutions = classify_solutions(grade, directory, tasks, rows, passed, mapping)
    if solutions["totals"]["correct"] != correct:
        raise ValueError("solution classes do not account for every correct request")
    return {
        "schema": SCHEMA,
        **counts,
        "correct": correct,
        "unit": "requests",
        "basis": "retained-evidence-static-diagnosis",
        "synthetic": detailed.get("synthetic"),
        "late_partition": late,
        "solutions": solutions,
        "acceptance_contract": {
            "criterion_id": joined["criterion_id"],
            "correctness_owner": "hot-aisle/campaign/run3/grade.py:join",
            "deadline_owner": "hot-aisle/campaign/run3/replay.py:buckets",
            "consistency_owner": "hot-aisle/campaign/shelf/validator.py:recompute_retained_run",
            "source_sha256": {
                path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in OWNER_CODE.values()
            },
        },
        "limits": [
            "Categories are observations of retained bytes, not proof of repairability.",
            "Interval segments do not identify a provider, GPU, serving-stack or client cause.",
            "Static parsing on the current interpreter approximates the pinned grader's parser.",
            "The original grader-blind task limitations remain in effect.",
        ],
        "executed_generated_code": False,
        "sanitized_or_repaired": False,
        "fresh_evalplus_execution": False,
        "new_gpu_run": False,
        "authority_promoted": False,
    }
