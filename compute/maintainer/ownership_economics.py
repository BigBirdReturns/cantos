#!/usr/bin/env python3
"""Source-bound useful-work ownership economics, including idle and failure burden.

This consumes retained, SHA-256-qualified board telemetry and external grades.
Every host, idle, ownership, price, availability and recovery input is an
explicit counterfactual assumption. No inference, billing or facility metering.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path

from .diagnose_grades import EvidenceError
from .empirical_economics import audit as empirical_audit

ARMS = ("baseline", "candidate")
COMMON = frozenset({
    "electricity_usd_per_kwh", "it_to_facility_multiplier", "acceptance_floor",
    "verification_usd_per_attempt", "recovery_usd_per_failed_attempt",
    "operator_seconds_per_failed_attempt", "operator_usd_per_hour", "arms",
})
PER_ARM = frozenset({
    "hardware_usd", "service_life_calendar_hours", "utilization_fraction",
    "availability_fraction", "operations_usd_per_calendar_hour",
    "network_storage_usd_per_active_hour", "unmetered_active_watts_assumed",
    "whole_host_idle_watts_assumed",
})
FRACTIONS = {"utilization_fraction", "availability_fraction"}


def finite(value, field, strictly_positive=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise EvidenceError(f"{field}: expected finite numeric assumption")
    if (value <= 0 if strictly_positive else value < 0):
        raise EvidenceError(f"{field}: out of nonnegative/positive domain")
    return float(value)


def checked_scenario(scenario):
    if not isinstance(scenario, dict) or set(scenario) != COMMON:
        raise EvidenceError("ownership scenario requires exact declared fields")
    if not isinstance(scenario["arms"], dict) or set(scenario["arms"]) != set(ARMS):
        raise EvidenceError("scenario requires baseline and candidate assumptions")
    parsed = {}
    for key in COMMON - {"arms"}:
        parsed[key] = finite(scenario[key], key,
                             key in {"it_to_facility_multiplier", "acceptance_floor"})
    if parsed["it_to_facility_multiplier"] < 1:
        raise EvidenceError("facility multiplier must be at least 1")
    if parsed["acceptance_floor"] > 1:
        raise EvidenceError("acceptance floor must not exceed 1")
    parsed["arms"] = {}
    for name in ARMS:
        value = scenario["arms"][name]
        if not isinstance(value, dict) or set(value) != PER_ARM:
            raise EvidenceError(f"{name}: missing or unknown ownership fields")
        a = {}
        for key in PER_ARM:
            a[key] = finite(value[key], f"{name}.{key}",
                            key in FRACTIONS or key == "service_life_calendar_hours")
            if key in FRACTIONS and a[key] > 1:
                raise EvidenceError(f"{name}.{key}: fraction exceeds 1")
        parsed["arms"][name] = a
    return parsed


def audit(campaign: Path, scenario: dict) -> dict:
    s = checked_scenario(scenario)
    original = empirical_audit(campaign)  # Enforces pinned raw telemetry and grades.
    records = original["observed"]["arms"]
    outputs = {}
    for name in ARMS:
        src = records[name]
        assumptions = s["arms"][name]
        attempts = src["attempts"]
        accepted = src["accepted"]
        failed = attempts - accepted
        if type(attempts) is not int or type(accepted) is not int or failed < 0:
            raise EvidenceError("invalid externally graded acceptance counts")
        active_h = finite(src["trial_duration_s"], "measured active duration") / 3600
        reserved_h = active_h / (assumptions["utilization_fraction"] *
                                  assumptions["availability_fraction"])
        idle_h = reserved_h - active_h
        if idle_h < -1e-10:
            raise EvidenceError("negative modeled idle hours")
        idle_h = max(0., idle_h)
        observed_board_j = finite(src["board_joules"], "observed board joules")
        assumed_active_j = assumptions["unmetered_active_watts_assumed"] * active_h * 3600
        assumed_idle_j = assumptions["whole_host_idle_watts_assumed"] * idle_h * 3600
        components = {
            "board_proxy_electricity": observed_board_j / 3600000 *
                s["electricity_usd_per_kwh"] * s["it_to_facility_multiplier"],
            "assumed_unmetered_active_electricity": assumed_active_j / 3600000 *
                s["electricity_usd_per_kwh"] * s["it_to_facility_multiplier"],
            "assumed_whole_host_idle_electricity": assumed_idle_j / 3600000 *
                s["electricity_usd_per_kwh"] * s["it_to_facility_multiplier"],
            "amortized_hardware": (assumptions["hardware_usd"] /
                                   assumptions["service_life_calendar_hours"]) * reserved_h,
            "calendar_operations": assumptions["operations_usd_per_calendar_hour"] * reserved_h,
            "network_storage": assumptions["network_storage_usd_per_active_hour"] * active_h,
            "verification": s["verification_usd_per_attempt"] * attempts,
            "post_failure_recovery": s["recovery_usd_per_failed_attempt"] * failed,
            "post_failure_operator": (s["operator_seconds_per_failed_attempt"] *
                                       s["operator_usd_per_hour"] / 3600) * failed,
        }
        total = math.fsum(components.values())
        if not math.isfinite(total):
            raise EvidenceError("modeled cost overflow")
        outputs[name] = {
            "observed": {"attempts": attempts, "accepted": accepted, "failed": failed,
                         "acceptance_rate": src["acceptance_rate"],
                         "active_trial_hours": active_h, "board_joules": observed_board_j},
            "modeled": {"reserved_calendar_hours": reserved_h, "idle_calendar_hours": idle_h,
                        "assumed_nonboard_active_joules": assumed_active_j,
                        "assumed_whole_host_idle_joules": assumed_idle_j,
                        "components_usd": components, "total_usd": total,
                        "usd_per_accepted": total / accepted if accepted else None},
            "sample_quality_gate": ("sample_pass" if src["acceptance_rate"] >=
                                    s["acceptance_floor"] else "sample_fail"),
        }
    b, c = outputs["baseline"], outputs["candidate"]
    cb, cc = b["modeled"]["usd_per_accepted"], c["modeled"]["usd_per_accepted"]
    if b["sample_quality_gate"] == c["sample_quality_gate"] == "sample_fail":
        decision = "hold_both_below_observed_acceptance_floor"
    elif b["sample_quality_gate"] == "sample_fail":
        decision = "conditional_candidate_only_sample_eligible"
    elif c["sample_quality_gate"] == "sample_fail":
        decision = "conditional_baseline_only_sample_eligible"
    elif cb is None or cc is None:
        decision = "hold_undefined_per_accepted_cost"
    else:
        decision = "conditional_sample_price_tie" if math.isclose(cb, cc, abs_tol=1e-12) else (
            "conditional_sample_price_candidate" if cc < cb else "conditional_sample_price_baseline"
        )
    capex_parity = None
    delta = cc - cb if cb is not None and cc is not None else None
    if delta is not None:
        cand = s["arms"]["candidate"]
        capex_slope = (c["modeled"]["reserved_calendar_hours"] /
                       cand["service_life_calendar_hours"] / c["observed"]["accepted"])
        if capex_slope > 0:
            root = cand["hardware_usd"] - delta / capex_slope
            if math.isfinite(root) and root >= 0:
                capex_parity = root
    return {
        "schema": "cantos.maintainer.ownership-economics/1",
        "evidence_class": "retained_board_sensor_and_external_grades_plus_explicit_scenarios",
        "original_source_sha256": original["source_sha256"],
        "scenario_sha256": sha256(json.dumps(s, sort_keys=True, separators=(",", ":"),
                                          allow_nan=False).encode()).hexdigest(),
        "scenario": s,
        "arms": outputs,
        "comparison": {"candidate_minus_baseline_usd_per_accepted": delta,
                       "candidate_hardware_usd_at_conditional_cost_parity": capex_parity,
                       "decision": decision},
        "terminal_condition": "Procurement remains unqualified absent representative acceptance, attributable wall energy, and validated operational assumptions.",
        "limitations": [
            "Only original GPU-board sensor joules and externally graded outcomes are observed.",
            "Unmetered active power, entire-host idle power, occupancy, availability, prices, hardware life and recovery are scenario inputs.",
            "Calendar capacity is active time / (availability times utilization); reported idle includes unoccupied and unavailable calendar capacity.",
            "Original failed attempts are charged once inside trial board/time cost; only assumed post-failure work adds a separate charge.",
            "This reanalysis does not create inference observations, provider SLAs, invoices or a representative procurement winner.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path, help="retained empirical campaign")
    parser.add_argument("--scenario", required=True, type=Path, help="explicit ownership scenario JSON")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = audit(args.campaign, json.loads(args.scenario.read_text(encoding="utf-8")))
    content = json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
