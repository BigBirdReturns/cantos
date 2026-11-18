"""Read-only joins of complete retry campaigns; never manufacture native runs."""
from pathlib import Path
import copy
import math
import re

try:
    from . import retry, retry_resources
    from .common import load, protocol, sha256_file, canonical
except ImportError:
    import retry, retry_resources
    from common import load, protocol, sha256_file, canonical

ARMS = ("baseline", "candidate")


def _allocations(path, campaign_path, summary):
    if path is None:
        return {"status": "unknown", "unknowns": ["Missing explicit verification/retry/operator/idle allocations"], "cost_per_accepted_range": None}
    value = load(path)
    if value.get("schema") != "cantos.retry.allocations/1" or value.get("campaign_sha256") != sha256_file(campaign_path):
        raise ValueError("Retry allocation receipt belongs to a different campaign")
    records = value.get("additional_costs")
    if not isinstance(records, list) or len(records) > 20:
        raise ValueError("Retry additional allocations must be bounded")
    seen, extra = set(), [0, 0]
    scenario = (summary.get("economics") or {}).get("scenario", {})
    for record in records:
        category = record.get("category")
        if category not in ("verification", "retry", "operator", "idle", "other") or category in seen:
            raise ValueError("Duplicate or unsupported retry allocation category")
        seen.add(category)
        if record.get("unit") != "USD" or type(record.get("includes_in_scenario")) is not bool or not isinstance(record.get("rationale"), str) or not record["rationale"].strip():
            raise ValueError("Retry allocation needs USD, explicit inclusion and a rationale")
        if record.get("basis") not in ("observed", "published", "modeled") or not isinstance(record.get("source"), str) or not record["source"].strip() or not isinstance(record.get("source_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", record["source_sha256"]):
            raise ValueError("Retry allocation requires explicit source identity and basis")
        if ("value" in record) == ("range" in record):
            raise ValueError("Retry allocation needs exactly value or range")
        bounds = [record["value"]] * 2 if "value" in record else record["range"]
        if not isinstance(bounds, list) or len(bounds) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in bounds) or bounds[1] < bounds[0]:
            raise ValueError("Invalid retry allocation range")
        if record["includes_in_scenario"]:
            fields = record.get("scenario_fields")
            if not isinstance(fields, list) or not fields or any(key not in scenario or scenario[key] is None for key in fields):
                raise ValueError("Included retry allocations must name explicit known scenario fields")
            # Informational allocation only; its amount is already in the scenario.
        else:
            extra = [a + b for a, b in zip(extra, bounds)]
    unknowns = ["Unspecified " + key + " retry allocation/cost" for key in sorted({"verification", "retry", "operator", "idle"} - seen)]
    economics = summary.get("economics") or {}
    total, accepted = economics.get("total_usd"), summary.get("accepted_tasks", 0)
    if total is None:
        unknowns.append("Incomplete complete-campaign cost scenario")
    if not accepted:
        unknowns.append("No retry accepted-task denominator")
    bounds = [(total + value) / accepted for value in extra] if not unknowns else None
    return {"status": "complete" if not unknowns else "unknown", "unknowns": unknowns,
            "additional_costs": copy.deepcopy(records), "cost_per_accepted_range": bounds,
            "basis": "Source-declared full-campaign scenario plus explicitly excluded additional costs; included allocations are not added again. Source hashes establish custody, not expenditure truth."}


def controls(value):
    if value is None:
        return {"required": False, "economics": False}
    if not isinstance(value, dict) or set(value) - {"required", "economics"}:
        raise ValueError("retry requires only required/economics boolean controls")
    result = {"required": False, "economics": False, **value}
    if any(type(v) is not bool for v in result.values()):
        raise ValueError("retry controls must be boolean")
    return result


def _campaign(path, side, native_run):
    path = Path(path).resolve()
    if path.is_dir():
        path /= "retry-campaign.json"
    # Bound the trusted validator's Cartesian population before materialization.
    plan = load(path.parent / "plan.json")
    identity = plan.get("identity", {})
    observed = identity.get("owner_observation_identity", {})
    proto = protocol(observed.get("protocol", {}))
    work = load(path.parent / "workload.json")
    cases = work.get("cases")
    value = load(path)
    tasks = value.get("tasks")
    if not isinstance(cases, list) or not isinstance(tasks, list):
        raise ValueError("Retry campaign needs bounded cases and tasks")
    count = proto["trials"] * proto["repeats"] * len(cases)
    if not 1 <= count <= 100000 or count != len(tasks):
        raise ValueError("Retry campaign task cardinality mismatch or limit")
    checked = retry.validate_campaign(path)
    if checked.get("arm") != side:
        raise ValueError("Retry campaign belongs to a different arm")
    expected = native_run.get("observation_identity", {})
    for field in ("configuration", "implementation_inputs", "workload_sha256", "protocol", "producer_files"):
        if canonical(observed.get(field)) != canonical(expected.get(field)):
            raise ValueError("Retry campaign differs from native experiment: " + field)
    return path, checked, identity


def join(native_runs, evidence=None, policy=None, native_policy=None):
    """Return explicit per-arm campaign facts and separately scoped economics.

    Evidence is baseline/candidate {campaign:Path, telemetry?:Path, scenario?:Path, allocations?:Path}.
    A malformed or changed artifact is rejected, rather than becoming a pass.
    Incomplete/unresolved or unmatched campaigns retain facts but cannot rank.
    """
    selected = controls(policy)
    if evidence is None:
        evidence = {}
    if not isinstance(evidence, dict) or set(evidence) - set(ARMS):
        raise ValueError("Retry evidence must be keyed by baseline and candidate")
    result = {"status": "absent" if not evidence else "unknown", "controls": selected,
              "arms": {}, "unknowns": [], "dependencies": {},
              "accounting": "Retry economics uses the complete campaign window and its accepted_tasks denominator only; native run costs are not added. Campaign time includes failed attempts, queue, backoff and grading, excludes server startup/prior reservation. Board telemetry is gross scoped sensor energy, not whole-host/facility or exclusive inference energy.",
              "execution": {"inference_requests": 0, "grader_executions": 0}}
    identities = {}
    for side in ARMS:
        item = evidence.get(side)
        if item is None:
            if evidence or selected["required"] or selected["economics"]:
                result["unknowns"].append(side + ": no retry campaign supplied")
            continue
        if not isinstance(item, dict) or set(item) - {"campaign", "telemetry", "scenario", "allocations"} or not item.get("campaign"):
            raise ValueError("Retry evidence requires campaign and optional telemetry/scenario paths")
        if side not in native_runs:
            result["unknowns"].append(side + ": native run unavailable for identity binding")
            continue
        path, campaign, identity = _campaign(item["campaign"], side, native_runs[side])
        if native_policy is not None:
            expected_controls = {key: native_policy.get(key) for key in ("acceptance", "require_observed_model", "require_observed_version")}
            if canonical(identity.get("acceptance_controls")) != canonical(expected_controls):
                raise ValueError("Retry acceptance controls differ from native policy")
        identities[side] = identity
        result["dependencies"][side] = {"campaign": sha256_file(path)}
        facts = {"campaign_sha256": sha256_file(path), "observation_id": campaign["observation_id"],
                 "status": campaign["status"], "metrics": copy.deepcopy(campaign["metrics"]),
                 "window": {"start": campaign["started_at"], "end": campaign["ended_at"]},
                 "clock_identity": campaign["clock_identity"], "retry_policy": identity["retry_policy"],
                 "resources": None, "denominator": "retry_campaign_accepted_tasks"}
        result["arms"][side] = facts
        if campaign["status"] != "complete" or campaign["metrics"].get("unresolved_tasks") or campaign.get("unknown_request_ids"):
            result["unknowns"].append(side + ": retry campaign incomplete or unresolved; no accepted-work ratio authorized")
            continue
        if item.get("telemetry") or item.get("scenario") or item.get("allocations"):
            summary = retry_resources.summarize(path, item.get("telemetry"), item.get("scenario"))
            summary.pop("analyzed_at", None)  # Analysis time is not observation identity.
            facts["resources"] = summary
            facts["allocations"] = _allocations(item.get("allocations"), path, summary)
            for key in ("telemetry", "scenario", "allocations"):
                if item.get(key):
                    result["dependencies"][side][key] = sha256_file(item[key])
        if selected["economics"] and (not facts.get("allocations") or facts["allocations"]["status"] != "complete"):
            result["unknowns"].extend(side + ": " + reason for reason in facts.get("allocations", {}).get("unknowns", ["complete source-labeled retry campaign economics unavailable"]))
    if len(identities) == 2:
        for field in ("retry_policy", "acceptance_controls", "grader_adapter"):
            if canonical(identities["baseline"].get(field)) != canonical(identities["candidate"].get(field)):
                result["unknowns"].append("Paired retry " + field + " differs; campaigns cannot establish a common-policy preference")
    if len(result["arms"]) == 2 and not result["unknowns"]:
        result["status"] = "complete"
    elif result["unknowns"]:
        result["status"] = "unknown"
    return result
