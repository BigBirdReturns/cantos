#!/usr/bin/env python3
"""Source-bound diagnosis of retained, externally graded paired coding captures.

Read-only: validates the original grade/capture journal join and reports failure
categories without rerunning inference, leaking solutions or promoting grader
results into claims of representative agentic success.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path


class EvidenceError(ValueError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _key(entry: dict) -> tuple[str, int, int]:
    return (entry["task_id"], entry["trial"], entry["repetition"])


def _exact_sign_p(wins: int, losses: int) -> float:
    """Two-sided conditional sign probability for a declared independent unit."""
    from math import comb
    n = wins + losses
    if not n:
        return 1.0
    smaller = min(wins, losses)
    return min(1.0, (2 * sum(comb(n, k) for k in range(smaller + 1))) / (1 << n))


def paired_acceptance(left: dict, right: dict) -> dict:
    """Reconcile paired grade outcomes, grouping repetitions at task level."""
    if set(left) != set(right):
        raise EvidenceError("unmatched paired grade keys")
    counts = {"both_accepted": 0, "baseline_only": 0,
              "candidate_only": 0, "neither_accepted": 0}
    task_scores = collections.defaultdict(lambda: [0, 0])
    for key in sorted(left):
        a, b = left[key]["accepted"], right[key]["accepted"]
        if type(a) is not bool or type(b) is not bool:
            raise EvidenceError("paired grade acceptance must be boolean")
        counts["both_accepted" if a and b else
               "baseline_only" if a else
               "candidate_only" if b else "neither_accepted"] += 1
        task_scores[key[0]][0] += int(a)
        task_scores[key[0]][1] += int(b)
    wins = sum(b > a for a, b in task_scores.values())
    losses = sum(a > b for a, b in task_scores.values())
    ties = len(task_scores) - wins - losses
    return {
        "attempt_pairs": len(left),
        "attempt_contingency": counts,
        "candidate_minus_baseline_accepted": counts["candidate_only"] - counts["baseline_only"],
        "task_direction": {"candidate_favored": wins, "baseline_favored": losses,
                           "tied": ties, "task_count": len(task_scores)},
        "task_sign_two_sided_p_conditional": _exact_sign_p(wins, losses),
        "interpretation": "Descriptive paired outcomes from verified grades. Task sign probability assumes independent exchangeable tasks; benchmark coverage, trial clustering, nonrandom assignment and pairing metadata limit external inference."
    }


def diagnose(campaign: Path) -> dict:
    campaign = campaign.resolve(strict=True)
    receipt_path = campaign / "VLLM-EMPIRICAL-RECEIPT.json"
    receipt = _read_json(receipt_path)
    if receipt.get("schema") != "cantos.empirical.vllm-application/1":
        raise EvidenceError("unrecognized empirical receipt")
    pinned = receipt["sources"]
    evidence = {"receipt": sha256(receipt_path)}
    arms = {}
    for arm in ("baseline", "candidate"):
        capture_name = f"vllm-capture/{arm}/run.json"
        grade_name = f"grade-{arm}/grades.json"
        raw_path, grade_path = campaign / capture_name, campaign / grade_name
        run_hash, grade_hash = sha256(raw_path), sha256(grade_path)
        if run_hash != pinned[capture_name] or grade_hash != pinned[grade_name]:
            raise EvidenceError(f"{arm}: receipt/source SHA-256 mismatch")
        capture, grades = _read_json(raw_path), _read_json(grade_path)
        if grades.get("run_sha256") != run_hash or capture.get("arm") != arm:
            raise EvidenceError(f"{arm}: grade/run binding mismatch")
        if grades.get("schema") != "cantos.maintainer.grades/1":
            raise EvidenceError(f"{arm}: unknown grade schema")
        eval_path = campaign / f"grade-{arm}/artifacts/humaneval_eval_results.json"
        map_path = campaign / f"grade-{arm}/artifacts/mapping.json"
        mappings, evals = _read_json(map_path), _read_json(eval_path)["eval"]
        artifact_list = {x["path"]: x["sha256"] for x in grades["artifacts"]}
        for name, path in (("artifacts/mapping.json", map_path),
                           ("artifacts/humaneval_eval_results.json", eval_path)):
            if sha256(path) != artifact_list.get(name):
                raise EvidenceError(f"{arm}: grader artifact {name} changed")
        indexed = {}
        for m in mappings:
            k = _key(m)
            if k in indexed:
                raise EvidenceError(f"{arm}: duplicate grader mapping {k}")
            idx = m["observation_index"]
            if not isinstance(idx, int) or idx < 0 or idx >= len(capture["observations"]):
                raise EvidenceError(f"{arm}: invalid raw observation index")
            observation = capture["observations"][idx]
            if _key(observation) != k or observation.get("warmup") or not m.get("capture_eligible"):
                raise EvidenceError(f"{arm}: grader mapping/capture identity mismatch")
            linked_attempts = [
                a for a in observation.get("attempts", [])
                if isinstance(a.get("response_text"), str)
                and hashlib.sha256(a["response_text"].encode("utf-8")).hexdigest() == m["response_sha256"]
                and a.get("response_sha256") == m["response_sha256"]
            ]
            if not linked_attempts:
                raise EvidenceError(f"{arm}: grader response is not bound to raw capture bytes")
            task_evals = evals.get(m["task_id"])
            solution_index = m["task_solution_index"]
            if not isinstance(task_evals, list) or not isinstance(solution_index, int) or not 0 <= solution_index < len(task_evals):
                raise EvidenceError(f"{arm}: missing exact external evaluator sample")
            e = task_evals[solution_index]
            if e["task_id"] != m["task_id"]:
                raise EvidenceError(f"{arm}: evaluator task identity mismatch")
            if hashlib.sha256(e["solution"].encode("utf-8")).hexdigest() != m["solution_sha256"]:
                raise EvidenceError(f"{arm}: evaluator solution bytes changed")
            indexed[k] = (m, e)
        results, records = grades["results"], {}
        for g in results:
            k = _key(g)
            if k in records or k not in indexed:
                raise EvidenceError(f"{arm}: duplicate or missing result {k}")
            mapping, evaluation = indexed[k]
            if g["response_sha256"] != mapping["response_sha256"]:
                raise EvidenceError(f"{arm}: response hash mismatch")
            base = evaluation["base_status"]
            plus = evaluation["plus_status"]
            if base not in ("pass", "fail") or plus not in ("pass", "fail"):
                raise EvidenceError(f"{arm}: unknown grader status")
            if g["accepted"] is not (base == "pass" and plus == "pass"):
                raise EvidenceError(f"{arm}: reported acceptance contradicts grader evidence")
            records[k] = {"accepted": g["accepted"], "base": base, "plus": plus,
                          "response_sha256": g["response_sha256"]}
        if len(records) != len(indexed) or len(records) != len(capture["observations"]):
            raise EvidenceError(f"{arm}: missing or extra raw/graded observations")
        evidence[capture_name], evidence[grade_name] = run_hash, grade_hash
        evidence[f"grade-{arm}/artifacts/mapping.json"] = sha256(map_path)
        evidence[f"grade-{arm}/artifacts/humaneval_eval_results.json"] = sha256(eval_path)
        arms[arm] = {"records": records, "pairing": capture["pairing"],
                     "workload_sha256": grades["workload_sha256"]}

    baseline, candidate = arms["baseline"], arms["candidate"]
    left, right = baseline["records"], candidate["records"]
    if set(left) != set(right) or baseline["workload_sha256"] != candidate["workload_sha256"]:
        raise EvidenceError("arms have mismatched graded task/trial populations")
    if baseline["pairing"] != candidate["pairing"]:
        raise EvidenceError("arms lack a common retained pairing declaration")

    trial_counts = collections.Counter(k[1] for k in left)
    tasks = sorted({k[0] for k in left})
    detail = []
    for task in tasks:
        keys = sorted(k for k in left if k[0] == task)
        detail.append({
            "task_id": task,
            "trials": [k[1] for k in keys],
            "baseline_accepted": sum(left[k]["accepted"] for k in keys),
            "candidate_accepted": sum(right[k]["accepted"] for k in keys),
            "baseline_unique_responses": len({left[k]["response_sha256"] for k in keys}),
            "candidate_unique_responses": len({right[k]["response_sha256"] for k in keys}),
            "cross_arm_identical_responses": sum(left[k]["response_sha256"] == right[k]["response_sha256"] for k in keys),
        })
    def category_counts(records):
        c = collections.Counter((x["base"], x["plus"]) for x in records.values())
        return {"base_pass_plus_pass": c["pass", "pass"],
                "base_pass_plus_fail": c["pass", "fail"],
                "base_fail_plus_pass": c["fail", "pass"],
                "base_fail_plus_fail": c["fail", "fail"]}
    total = len(left)
    return {
        "schema": "cantos.maintainer.coding-diagnosis/1",
        "scope": "Retained externally graded coding responses; no fresh serving or inference",
        "source_sha256": dict(sorted(evidence.items())),
        "workload_sha256": baseline["workload_sha256"],
        "pairing_declaration": baseline["pairing"],
        "identity_note": "Shared pairing metadata observed; broader CI comparability is independently gated.",
        "total_per_arm": total,
        "tasks": len(tasks),
        "trials": dict(sorted(trial_counts.items())),
        "accepted": {a: sum(v["accepted"] for v in arms[a]["records"].values()) for a in arms},
        "grading_categories": {a: category_counts(arms[a]["records"]) for a in arms},
        "cross_arm_identical_responses": sum(left[k]["response_sha256"] == right[k]["response_sha256"] for k in left),
        "cross_arm_different_responses": sum(left[k]["response_sha256"] != right[k]["response_sha256"] for k in left),
        "cross_arm_acceptance_disagreements": sum(left[k]["accepted"] != right[k]["accepted"] for k in left),
        "paired_acceptance": paired_acceptance(left, right),
        "task_diagnosis": detail,
        "limits": ["No raw solutions or prompts are exported", "No provider/cloud SLA inference",
                   "Board-only energy is not whole-system economics", "No model change or application improvement demonstrated"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = diagnose(args.campaign)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"evidence rejection: {error}\n")
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
