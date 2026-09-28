"""Output-contract repair candidates for one retained Run 3 arm.

The retained grade is raw completion, no sanitizer, per PREREG, and stays the
registered result. This adapter proposes a post-hoc candidate for every
completed request by SELECTING A SUBSTRING of the raw output and nothing else:

* ``closing_fence_cut``   the model closed a fence it never opened; everything
                          from that first bare closing fence onward is dropped.
* ``fence_block_extract`` the output opened a fence; only the first fenced
                          block's contents are kept.
* ``length_backoff``      the output finished by length; the longest whole-line
                          prefix whose prompt+prefix parses is kept.

Rules apply only when the raw prompt+output fails to parse, in that order, and
a rule is kept only if it produces a non-empty candidate. No characters are
inserted, no reference answer or test is consulted, already-valid solutions are
never touched, and nothing is executed. ``materialize`` writes the candidates
in the exact ``grade.py:prepare`` layout so the pinned, network-isolated grader
can consume them; a grade obtained that way is post-hoc until prospectively
qualified.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
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
AST_FEATURE_VERSION = (3, 11)  # the pinned grader image is python:3.11
SCHEMA = "second-run/output-contract@1"
MAP_SCHEMA = "second-run/output-contract-map@1"
RULES = ("closing_fence_cut", "fence_block_extract", "length_backoff")
FENCE = "`" * 3
FENCE_LINE = re.compile(r"^[ \t]*" + FENCE)
BARE_CLOSING_FENCE = re.compile(r"^[ \t]*" + FENCE + r"[ \t]*$")
MAX_BACKOFF_LINES = 400


def prepare(task, base):
    """Declare the bytes the candidate reads and return the native call."""
    if not isinstance(task, dict):
        raise ValueError("output-contract task must be an object")
    extra = set(task) - ALLOWED
    if extra:
        raise ValueError("Unknown output-contract arguments: " + ", ".join(sorted(extra)))
    if task.get("task_class") != "output-contract":
        raise ValueError("task_contract only handles output-contract")
    source = task.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("output-contract source must name a retained arm directory")
    directory = (Path(base) / source).resolve()
    if not directory.is_dir():
        raise ValueError("output-contract source is not a retained arm directory")
    inputs = {
        "code:task-contract": Path(__file__).resolve(),
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
        for role, suffix in (("samples", ".jsonl"), ("reference", "-reference.jsonl"),
                             ("evalplus-results", "_eval_results.json")):
            inputs[f"grade:{dataset}:{role}"] = directory / "grade" / (dataset + suffix)

    def execute():
        return contract(directory)

    return {"parameters": {}, "inputs": inputs, "execute": execute}


def _load(name, path, sibling_path=None):
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


def parses(source):
    try:
        ast.parse(source, feature_version=AST_FEATURE_VERSION)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return False
    return True


def _line_starts(text):
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n" and i + 1 < len(text):
            starts.append(i + 1)
    return starts


def _line_at(text, start):
    end = text.find("\n", start)
    return (text[start:], len(text)) if end < 0 else (text[start:end], end + 1)


def closing_fence_cut(output):
    """Span before the first bare closing fence when no fence opened earlier."""
    for start in _line_starts(output):
        line, _ = _line_at(output, start)
        if FENCE_LINE.match(line):
            return (0, start) if BARE_CLOSING_FENCE.match(line) else None
    return None


def fence_block_extract(output):
    """Span of the first fenced block's contents when the output opened a fence."""
    opened = None
    for start in _line_starts(output):
        line, next_start = _line_at(output, start)
        if not FENCE_LINE.match(line):
            continue
        if opened is None:
            if BARE_CLOSING_FENCE.match(line):
                return None  # a closing fence first belongs to closing_fence_cut
            opened = next_start
            continue
        return (opened, start)
    if opened is not None:
        return (opened, len(output))  # opened, never closed (length-limited)
    return None


def length_backoff(prompt, candidate):
    """Longest whole-line prefix of candidate whose prompt+prefix parses."""
    starts = _line_starts(candidate)
    for cut in reversed(starts[-MAX_BACKOFF_LINES:]):
        prefix = candidate[:cut]
        if prefix.strip() and parses(prompt + prefix):
            return (0, cut)
    return None


def propose(prompt, output, finish_reason):
    """Return (rule, start, end) selecting output[start:end], or None to keep raw."""
    if parses(prompt + output):
        return None
    span = closing_fence_cut(output)
    rule = "closing_fence_cut"
    if span is None:
        span = fence_block_extract(output)
        rule = "fence_block_extract"
    if span is not None and not output[span[0]:span[1]].strip():
        span = None  # an empty candidate is refused; the raw output stands
    if span is not None and parses(prompt + output[span[0]:span[1]]):
        return (rule, span[0], span[1])
    if finish_reason == "length":
        base = span if span is not None else (0, len(output))
        inner = length_backoff(prompt, output[base[0]:base[1]])
        if inner is not None:
            return ("length_backoff", base[0], base[0] + inner[1])
    if span is not None:
        return (rule, span[0], span[1])  # substring kept, still invalid; reported as such
    return None


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def comment_only(text):
    """True when a candidate parses but carries no statement: blank and # lines only."""
    return all(not line.strip() or line.lstrip().startswith("#") for line in text.splitlines())


def contract(directory):
    validator = _load("_task_contract_shelf_validator", SHELF_VALIDATOR)
    counts = validator.recompute_retained_run(directory)  # owner consistency first
    grade = _load("_task_contract_run3_grade", RUN3 / "grade.py", RUN3)
    grade.write_json = lambda path, value: None
    replay_dir = directory / "replay"
    joined = grade.join(directory / "tasks.json", replay_dir / "requests.jsonl",
                        directory / "detailed.json", directory / "grade", None)
    passed = joined["passed"]
    plan, rows = grade.recover(replay_dir)
    tasks = grade.read_json(directory / "tasks.json")
    mapping = grade.read_json(directory / "grade" / "mapping.json")
    by_id = {task["task_id"]: task for task in tasks["tasks"]}
    per_dataset, candidates, grading_input = {}, [], {}
    for dataset, meta in mapping["datasets"].items():
        samples = grade.jsonl(directory / "grade" / (dataset + ".jsonl"))
        if len(samples) != len(meta["request_indices"]):
            raise ValueError("Sample mapping length mismatch")
        tally = {"samples": len(samples), "placeholders": 0, "raw_valid": 0, "raw_invalid": 0,
                 "raw_invalid_finish_length": 0, "raw_invalid_retained_correct": 0,
                 "candidate_valid": 0, "candidate_still_invalid": 0, "unresolved_raw_kept": 0,
                 "candidate_valid_comment_only": 0,
                 "by_rule": {rule: {"applied": 0, "valid": 0} for rule in RULES}}
        out_samples = []
        for sample, n in zip(samples, meta["request_indices"]):
            if n is None or rows[n]["error"]:
                tally["placeholders"] += 1
                out_samples.append(sample)
                continue
            row = rows[n]
            prompt = by_id[row["task_id"]]["prompt"]
            output = row["output_text"]
            if sample["solution"] != prompt + output:
                raise ValueError("retained sample is not frozen prompt plus raw output")
            proposal = propose(prompt, output, row.get("finish_reason"))
            if proposal is None:
                if parses(prompt + output):
                    tally["raw_valid"] += 1
                else:
                    tally["raw_invalid"] += 1
                    tally["unresolved_raw_kept"] += 1
                    tally["raw_invalid_finish_length"] += row.get("finish_reason") == "length"
                    tally["raw_invalid_retained_correct"] += bool(passed[n])
                out_samples.append(sample)
                continue
            rule, start, end = proposal
            candidate = output[start:end]
            valid = parses(prompt + candidate)
            tally["raw_invalid"] += 1
            tally["raw_invalid_finish_length"] += row.get("finish_reason") == "length"
            tally["raw_invalid_retained_correct"] += bool(passed[n])
            tally["by_rule"][rule]["applied"] += 1
            tally["by_rule"][rule]["valid"] += valid
            tally["candidate_valid" if valid else "candidate_still_invalid"] += 1
            tally["candidate_valid_comment_only"] += valid and comment_only(candidate)
            candidates.append({"request_index": n, "task_id": row["task_id"], "dataset": dataset,
                               "rule": rule, "span": [start, end], "finish_reason": row.get("finish_reason"),
                               "raw_sha256": _sha(output), "candidate_sha256": _sha(candidate),
                               "raw_chars": len(output), "candidate_chars": len(candidate),
                               "candidate_parses": valid, "comment_only": valid and comment_only(candidate),
                               "retained_passed": bool(passed[n])})
            out_samples.append({"task_id": sample["task_id"], "solution": prompt + candidate})
        if tally["raw_valid"] + tally["raw_invalid"] + tally["placeholders"] != tally["samples"]:
            raise ValueError("candidate tally does not account for every sample")
        if tally["candidate_valid"] + tally["candidate_still_invalid"] + tally["unresolved_raw_kept"] != tally["raw_invalid"]:
            raise ValueError("candidate outcomes do not account for every invalid raw output")
        per_dataset[dataset] = tally
        grading_input[dataset] = {
            "samples_sha256": hashlib.sha256(b"".join(grade.encoded(s) for s in out_samples)).hexdigest(),
            "retained_samples_sha256": meta["samples_sha256"],
            "reference_sha256": meta["reference_sha256"], "reference_md5": meta["reference_md5"],
            "request_indices_unchanged": True,
        }
    keys = [k for k in next(iter(per_dataset.values())) if k != "by_rule"]
    totals = {k: sum(d[k] for d in per_dataset.values()) for k in keys}
    totals["by_rule"] = {rule: {kind: sum(d["by_rule"][rule][kind] for d in per_dataset.values())
                                for kind in ("applied", "valid")} for rule in RULES}
    return {
        "schema": SCHEMA,
        **counts,
        "correct": sum(passed),
        "unit": "requests",
        "basis": "retained-evidence-substring-candidate",
        "rules": {"order": list(RULES), "apply_when": "prompt + raw output fails ast.parse",
                  "never": ["insert characters", "consult references or tests", "alter a parsing solution",
                            "execute generated code", "change retained grading or deadlines"],
                  "parser": {"method": "ast.parse", "feature_version": list(AST_FEATURE_VERSION),
                             "python": platform.python_version()}},
        "per_dataset": per_dataset,
        "totals": totals,
        "candidates": candidates,
        "grading_input": grading_input,
        "materialize": "python -B integration/task_contract.py materialize RESULT.json ARM_DIR OUT_DIR",
        "retained_grade_unchanged": True,
        "acceptance_contract": {
            "criterion_id": joined["criterion_id"],
            "registered_grade_owner": "hot-aisle/campaign/run3/grade.py",
            "consistency_owner": "hot-aisle/campaign/shelf/validator.py:recompute_retained_run",
            "source_sha256": {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in OWNER_CODE.values()},
        },
        "limits": [
            "candidate_parses is a static parse status, not correctness; only the pinned isolated grader can grade.",
            "Any grade of these candidates is post-hoc and unregistered until prospectively qualified.",
            "Substring selection can keep a wrong, partial or comment-only body; nothing here verifies intent.",
            "Refusals or prose-only outputs stay raw (unresolved_raw_kept) and are not classified as refusals.",
        ],
        "graded": False,
        "executed_generated_code": False,
        "fresh_evalplus_execution": False,
        "new_gpu_run": False,
        "authority_promoted": False,
    }


def materialize(result_path, arm, out):
    """Write candidates in the exact grade.py:prepare layout for the isolated grader."""
    import work
    arm = Path(arm).resolve()
    task = {"task_class": "output-contract", "source": str(arm)}
    description = work.snapshot(prepare(task, Path.cwd()), "output-contract")
    entry = work.read_cache(Path(result_path), description)
    value = entry["value"]
    if value.get("schema") != SCHEMA:
        raise ValueError("Not an output-contract result")
    grade = _load("_task_contract_run3_grade_m", RUN3 / "grade.py", RUN3)
    tasks, rows, detailed = grade.bound_inputs(arm / "tasks.json", arm / "replay" / "requests.jsonl",
                                               arm / "detailed.json")
    mapping = grade.read_json(arm / "grade" / "mapping.json")
    by_id = {task["task_id"]: task for task in tasks["tasks"]}
    spans = {c["request_index"]: c for c in value["candidates"]}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    new_map = {"schema": "second-run/grading-map@1", "source_sha256": mapping["source_sha256"],
               "requests_sha256": mapping["requests_sha256"], "tasks_sha256": mapping["tasks_sha256"],
               "datasets": {}}
    lineage = []
    for dataset, meta in mapping["datasets"].items():
        grade.verify(arm / "grade" / (dataset + ".jsonl"), meta["samples_sha256"])
        samples = grade.jsonl(arm / "grade" / (dataset + ".jsonl"))
        out_samples = []
        for sample, n in zip(samples, meta["request_indices"]):
            if n in spans:
                row = rows[n]
                c = spans[n]
                output = row["output_text"]
                if _sha(output) != c["raw_sha256"]:
                    raise ValueError("raw output differs from the candidate's lineage")
                candidate = output[c["span"][0]:c["span"][1]]
                if _sha(candidate) != c["candidate_sha256"]:
                    raise ValueError("candidate bytes differ from the recorded candidate hash")
                out_samples.append({"task_id": sample["task_id"],
                                    "solution": by_id[row["task_id"]]["prompt"] + candidate})
                lineage.append(c)
            else:
                out_samples.append(sample)
        sample_path = out / (dataset + ".jsonl")
        sample_path.write_bytes(b"".join(grade.encoded(s) for s in out_samples))
        if grade.sha(sample_path) != value["grading_input"][dataset]["samples_sha256"]:
            raise ValueError("materialized samples differ from the recorded grading input")
        ref_src = arm / "grade" / (dataset + "-reference.jsonl")
        grade.verify(ref_src, meta["reference_sha256"])
        (out / (dataset + "-reference.jsonl")).write_bytes(ref_src.read_bytes())
        new_map["datasets"][dataset] = {"request_indices": meta["request_indices"],
                                        "samples_sha256": grade.sha(sample_path),
                                        "reference_sha256": meta["reference_sha256"],
                                        "reference_md5": meta["reference_md5"]}
    grade.write_json(out / "mapping.json", new_map)
    grade.write_json(out / "contract-map.json", {
        "schema": MAP_SCHEMA, "origin": "post-hoc output-contract candidate; not the registered grade",
        "result_value_sha256": entry.get("value_sha256"),
        "retained_mapping_sha256": grade.sha(arm / "grade" / "mapping.json"),
        "candidates": lineage, "graded": False, "executed_generated_code": False})
    after = work.snapshot(prepare(task, Path.cwd()), "output-contract")
    if after["identity"] != description["identity"]:
        raise ValueError("Dependencies changed during export; retain the partial export for review")
    return new_map


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    q = sub.add_parser("materialize")
    for arg in ("result", "arm", "out"):
        q.add_argument(arg)
    a = p.parse_args()
    materialize(a.result, a.arm, a.out)
