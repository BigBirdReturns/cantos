#!/usr/bin/env python3
"""Verify captured GPU-board energy against externally graded useful work.

This audits retained measurement evidence; it never initiates inference.
Only actual board-sensor joules and graded acceptance are observed. Every
economic number is conditional on an explicitly supplied scenario.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from .diagnose_grades import EvidenceError, diagnose, sha256
from .owner_ocl.energy import integrate_power

ARMS = ("baseline", "candidate")
SCENARIO_FIELDS = {
    "electricity_usd_per_kwh", "it_to_facility_multiplier",
    "fixed_usd_per_hour", "verification_usd_per_attempt",
    "intervention_seconds_per_attempt", "intervention_usd_per_hour",
}


def _finite(value, name: str, minimum=0.0) -> float:
    if type(value) not in (float, int) or not math.isfinite(value) or value < minimum:
        raise EvidenceError(f"{name} must be a finite number >= {minimum}")
    return float(value)


def _equal(actual, claimed, name: str) -> None:
    value = _finite(actual, name)
    expected = _finite(claimed, f"claimed {name}")
    if not math.isclose(value, expected, rel_tol=1e-10, abs_tol=1e-8):
        raise EvidenceError(f"{name} disagrees with retained source measurements")


def _source(campaign: Path, relative: str, digest: str) -> Path:
    path = (campaign / relative).resolve(strict=True)
    if not path.is_relative_to(campaign):
        raise EvidenceError("source path escapes retained campaign")
    if sha256(path) != digest:
        raise EvidenceError(f"source SHA-256 changed: {relative}")
    return path


def _scenario(value: dict | None) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != SCENARIO_FIELDS:
        raise EvidenceError("scenario requires exactly six declared economic assumptions")
    return {k: _finite(value[k], k, 1 if k == "it_to_facility_multiplier" else 0)
            for k in sorted(SCENARIO_FIELDS)}


def audit(campaign: Path, scenario: dict | None = None) -> dict:
    campaign = campaign.resolve(strict=True)
    grade_diagnosis = diagnose(campaign)  # Validates original source bytes and external grades.
    receipt_path = campaign / "VLLM-EMPIRICAL-RECEIPT.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    source_name = "vllm-serving/board-samples.jsonl"
    telemetry_path = _source(campaign, source_name, receipt["sources"][source_name])
    samples = [json.loads(s) for s in telemetry_path.read_text(encoding="utf-8").splitlines() if s.strip()]
    if len(samples) < 2:
        raise EvidenceError("insufficient retained board telemetry")
    uuid = None
    prev = -math.inf
    numeric_samples = []
    for sample in samples:
        if not isinstance(sample, dict) or not isinstance(sample.get("uuid"), str):
            raise EvidenceError("invalid sensor identity")
        uuid = uuid or sample["uuid"]
        if uuid != sample["uuid"]:
            raise EvidenceError("mixed GPU board identities in one telemetry journal")
        t = _finite(sample.get("monotonic_s"), "sample timestamp")
        watts = _finite(sample.get("watts"), "board watts")
        if t <= prev:
            raise EvidenceError("nonmonotonic board telemetry")
        prev = t
        numeric_samples.append({"t_s": t, "watts": watts})
    max_gap = _finite(receipt.get("max_telemetry_gap_s"), "recorded maximum sampling gap", 1e-9)
    # Sensor logger may round its stated maximum by a few ns; do not invent new samples.
    max_gap += 1e-6

    arms = {}
    scenario = _scenario(scenario)
    for arm in ARMS:
        run_rel = f"vllm-capture/{arm}/run.json"
        grade_rel = f"grade-{arm}/grades.json"
        run = json.loads(_source(campaign, run_rel, receipt["sources"][run_rel]).read_text())
        grades = json.loads(_source(campaign, grade_rel, receipt["sources"][grade_rel]).read_text())
        if run.get("arm") != arm:
            raise EvidenceError(f"{arm}: wrong capture arm")
        trials, claimed = run["trials"], receipt["arms"][arm]
        if len(trials) != len(claimed["per_trial"]) or not trials:
            raise EvidenceError(f"{arm}: missing or extra trial accounting")
        count_by_trial = {}
        accepted_by_trial = {}
        for g in grades["results"]:
            i = g["trial"]
            if type(i) is not int or i < 0 or i >= len(trials):
                raise EvidenceError(f"{arm}: grading trial outside capture")
            count_by_trial[i] = count_by_trial.get(i, 0) + 1
            accepted_by_trial[i] = accepted_by_trial.get(i, 0) + int(g["accepted"])
        rows, total_joules, total_duration, total_tasks, total_accepted = [], 0.0, 0.0, 0, 0
        for i, (trial, proof) in enumerate(zip(trials, claimed["per_trial"])):
            if trial.get("trial") != i or proof.get("trial") != i:
                raise EvidenceError(f"{arm}: trial order changed")
            start = _finite(trial.get("started_monotonic_s"), "trial start")
            end = _finite(trial.get("ended_monotonic_s"), "trial end")
            if end <= start:
                raise EvidenceError(f"{arm}: invalid trial window")
            _equal(end-start, trial["duration_s"], "trial duration")
            result = integrate_power(numeric_samples, start, end, max_gap)
            if result["joules"] is None:
                raise EvidenceError(f"{arm}: board telemetry does not bracket entire trial with qualified gaps")
            joules = result["joules"]
            tasks, accepted = count_by_trial.get(i, 0), accepted_by_trial.get(i, 0)
            if tasks == 0:
                raise EvidenceError(f"{arm}: trial lacks graded useful-work attempts")
            _equal(joules, proof["board_joules"], "trial board joules")
            _equal(joules / 3600, proof["board_wh"], "trial board Wh")
            _equal(tasks, proof["tasks"], "trial attempts")
            _equal(accepted, proof["accepted"], "trial accepted")
            _equal(end-start, proof["duration_s"], "reported trial duration")
            expected_ratio = joules / accepted if accepted else None
            if expected_ratio is None:
                if proof.get("joules_per_accepted") is not None:
                    raise EvidenceError("zero accepted tasks must have null energy ratio")
            else:
                _equal(expected_ratio, proof["joules_per_accepted"], "trial joules per accepted")
            total_tasks += tasks
            total_accepted += accepted
            total_joules += joules
            total_duration += end - start
            rows.append({"trial": i, "attempts": tasks, "accepted": accepted,
                         "duration_s": end - start, "board_joules": joules,
                         "joules_per_accepted": expected_ratio})
        if total_accepted != grade_diagnosis["accepted"][arm] or total_tasks != grade_diagnosis["total_per_arm"]:
            raise EvidenceError(f"{arm}: grades and trials disagree")
        _equal(total_tasks, claimed["tasks"], "arm attempts")
        _equal(total_accepted, claimed["accepted"], "arm accepted")
        _equal(total_accepted / total_tasks, claimed["acceptance_rate"], "arm acceptance fraction")
        _equal(total_joules, claimed["board_joules"], "arm board joules")
        _equal(total_joules / 3600, claimed["board_wh"], "arm board Wh")
        if total_accepted:
            _equal(total_joules / total_accepted, claimed["joules_per_accepted"], "arm joules per accepted")
        elif claimed.get("joules_per_accepted") is not None:
            raise EvidenceError("zero accepted tasks must have null arm energy ratio")
        record = {"attempts": total_tasks, "accepted": total_accepted,
                  "acceptance_rate": total_accepted / total_tasks,
                  "trial_duration_s": total_duration, "board_joules": total_joules,
                  "board_wh": total_joules / 3600,
                  "board_joules_per_accepted": total_joules / total_accepted if total_accepted else None,
                  "trials": rows}
        if scenario:
            electricity = (total_joules / 3_600_000) * scenario["electricity_usd_per_kwh"] * scenario["it_to_facility_multiplier"]
            fixed = total_duration / 3600 * scenario["fixed_usd_per_hour"]
            verification = total_tasks * scenario["verification_usd_per_attempt"]
            intervention = total_tasks * scenario["intervention_seconds_per_attempt"] / 3600 * scenario["intervention_usd_per_hour"]
            modeled = electricity + fixed + verification + intervention
            record["scenario_usd"] = {"electricity_board_proxy": electricity, "fixed_time": fixed,
                                      "verification": verification, "intervention": intervention,
                                      "total_modeled": modeled,
                                      "per_accepted": modeled / total_accepted if total_accepted else None}
        arms[arm] = record
    return {
        "schema": "cantos.maintainer.empirical-energy-accounting/1",
        "status": "source_bound_observation_and_optional_scenario",
        "source_sha256": {**grade_diagnosis["source_sha256"], source_name: sha256(telemetry_path)},
        "gpu_uuid": uuid, "observed": {"arms": arms,
            "candidate_minus_baseline_board_joules": arms["candidate"]["board_joules"]-arms["baseline"]["board_joules"],
            "candidate_minus_baseline_accepted": arms["candidate"]["accepted"]-arms["baseline"]["accepted"]},
        "scenario": scenario,
        "scope": "Board sensor energy inside captured trial windows, inclusive of failed attempts; accepted task outcomes from source-pinned external grading.",
        "limits": [
            "Board sensor is not whole-host/facility energy or exclusive job attribution.",
            "Start-up, idle between trials, resident other GPU, CPU, verification and operator activity are not metered.",
            "Price and fixed-cost inputs are scenario assumptions, never observed invoices.",
            "Replayed correlated coding trials do not establish representative deployment economics or SLA.",
            "Causal deployment verdict requires qualified comparability and representative acceptance.",
            "Independent custody of the original evidence receipt is required to authenticate rehashed manifests.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--scenario", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    assumptions = json.loads(args.scenario.read_text()) if args.scenario else None
    result = audit(args.campaign, assumptions)
    encoded = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
