"""Join the native serving verdict, scoped operational checks and explicit costs.

This is retained analysis only. It never collects, retries requests, executes a
grader or executes source supplied in an evidence attachment.
"""
from __future__ import annotations

import base64
import copy
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import tempfile

try:
    from . import maintainer, deployment_retry
    from .common import ROOT, canonical, load, policy, protocol
    from .owner_ocl.costs import estimate_cost
    from .owner_ocl.energy import integrate_power
    from .owner_ocl import recovery_verifier, storage_verifier, network_health
except ImportError:
    import maintainer, deployment_retry
    from common import ROOT, canonical, load, policy, protocol
    from owner_ocl.costs import estimate_cost
    from owner_ocl.energy import integrate_power
    from owner_ocl import recovery_verifier, storage_verifier, network_health

STATES = ("SELECT-CANDIDATE", "KEEP-BASELINE", "NO-ELIGIBLE", "INCOMPARABLE", "INCOMPLETE", "UNDETERMINED")
BASES = {"observed", "published", "modeled", "unknown"}
ARMS = ("baseline", "candidate")
COST_FIELDS = {"capex_usd", "residual_usd", "life_hours", "utilization", "financing_usd_per_hour",
               "hosting_usd_per_hour", "operations_usd_per_hour", "maintenance_usd_per_hour", "network_usd_per_hour",
               "electricity_usd_per_kwh", "pue", "intervention_seconds", "intervention_usd_per_hour", "average_it_power_w"}
SHA = re.compile(r"^[a-f0-9]{64}$")


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _number(value, label, minimum=0):
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        raise ValueError(label + " must be finite and at least " + str(minimum))
    return value


def _date(value):
    if not isinstance(value, str):
        raise ValueError("Expected a timezone-qualified timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp requires a timezone")
    return parsed


def _window(value):
    if not isinstance(value, dict) or set(value) != {"start", "end"}:
        raise ValueError("Window requires start and end")
    left, right = _date(value["start"]), _date(value["end"])
    if right < left:
        raise ValueError("Window ends before it starts")
    return left, right


def validate_deployment(value):
    if not isinstance(value, dict) or value.get("schema") != "cantos.deployment-job/1":
        raise ValueError("Expected cantos.deployment-job/1")
    result = copy.deepcopy(value)
    if "retry" in result:
        result["retry"] = deployment_retry.controls(result["retry"])
    if not isinstance(result.get("id"), str) or not result["id"].strip():
        raise ValueError("Deployment job requires an id")
    decision = result.setdefault("decision", {})
    if not isinstance(decision, dict) or set(decision) - {"objective", "economics_required", "operational_requirements"}:
        raise ValueError("Unsupported deployment decision fields")
    decision.setdefault("objective", "min_cost_per_accepted")
    decision.setdefault("economics_required", True)
    decision.setdefault("operational_requirements", [])
    if decision["objective"] not in ("min_cost_per_accepted", "min_energy_per_accepted"):
        raise ValueError("Unsupported deployment objective")
    if type(decision["economics_required"]) is not bool:
        raise ValueError("economics_required must be boolean")
    requirements = decision["operational_requirements"]
    if not isinstance(requirements, list) or len(requirements) > 100:
        raise ValueError("At most 100 operational requirements are supported")
    seen = set()
    for req in requirements:
        required_keys = {"id", "check_id", "operator", "threshold", "required", "max_age_s", "allowed_basis"}
        if not isinstance(req, dict) or set(req) - (required_keys | {"network_target", "network_protocol"}) or not required_keys <= set(req):
            raise ValueError("Invalid operational requirement")
        if req["check_id"] in network_health.CHECKS:
            network_health.target(req.get("network_target"))
            network_health.protocol(req.get("network_protocol"))
            if req["operator"] != "lte":
                raise ValueError("Owned network requirements use explicit upper bounds")
        elif set(req) & {"network_target", "network_protocol"}:
            raise ValueError("Network identity/protocol apply only to owned network checks")
        for key in ("id", "check_id"):
            if not isinstance(req[key], str) or not req[key]:
                raise ValueError("Requirement needs " + key)
        if req["id"] in seen:
            raise ValueError("Duplicate operational requirement id")
        seen.add(req["id"])
        if req["operator"] not in ("eq", "lte", "gte") or type(req["required"]) is not bool:
            raise ValueError("Invalid requirement operator or required flag")
        if type(req["threshold"]) is not bool:
            _number(req["threshold"], "operational threshold")
        if req["operator"] != "eq" and type(req["threshold"]) is bool:
            raise ValueError("Boolean requirement uses eq")
        _number(req["max_age_s"], "max_age_s")
        if not isinstance(req["allowed_basis"], list) or not req["allowed_basis"] or set(req["allowed_basis"]) - BASES:
            raise ValueError("Invalid allowed evidence bases")
    arms = result.setdefault("arms", {side: {} for side in ARMS})
    if not isinstance(arms, dict) or set(arms) != set(ARMS):
        raise ValueError("Deployment requires baseline and candidate arms")
    return result


def _checked_native(native, paths):
    if not isinstance(native, dict) or native.get("verdict") not in ("pass", "regression", "incomparable", "error"):
        raise ValueError("Expected a native maintainer verdict")
    # A stopped capture may have no valid run receipt. Preserve the refusal;
    # never synthesize a complete receipt or accepted-work population.
    if not all(key in native for key in ("baseline", "candidate", "policy")):
        if native["verdict"] != "error":
            raise ValueError("Native comparison is missing per-arm facts")
        return copy.deepcopy(native), {}
    inputs = native.get("inputs", {})
    runs = {}
    for side in ARMS:
        path = Path(paths[side]).resolve()
        if inputs.get(side, {}).get("sha256") != sha(path.read_bytes()):
            raise ValueError("Native comparison does not bind " + side + " run bytes")
        preflight = load(path)
        proto = protocol(preflight.get("protocol", {}))
        cases = load(path.parent / "workload.json").get("cases")
        observations = preflight.get("observations")
        if not isinstance(cases, list) or not isinstance(observations, list):
            raise ValueError("Native deployment requires bounded workload/observation arrays")
        count = proto["trials"] * proto["repeats"] * len(cases)
        if not 1 <= count <= 100000 or count != len(observations):
            raise ValueError("Native deployment observation cardinality mismatch or limit")
        runs[side] = maintainer.validate_receipt(path)
    with tempfile.TemporaryDirectory(prefix="cantos-deployment-native-") as temporary:
        temporary = Path(temporary)
        selected = temporary / "policy.json"
        selected.write_bytes(canonical(native["policy"]))
        kwargs = {key: inputs[key]["path"] for key in ("baseline_grades", "candidate_grades", "grading_contract") if key in inputs}
        checked = maintainer.analyze_receipts(paths["baseline"], paths["candidate"], selected, temporary / "analysis", **kwargs)
    for key in ("verdict", "baseline", "candidate", "policy", "errors", "comparability_failures", "regressions", "performance_checks", "changed_factors"):
        if canonical(native.get(key)) != canonical(checked.get(key)):
            raise ValueError("Native deployment input differs from recomputation: " + key)
    return copy.deepcopy(native), runs


def _binding(value, run, run_hash, max_age=None, accounting=False):
    if not isinstance(value, dict):
        raise ValueError("Missing resource/run/time binding")
    if value.get("run_sha256") != run_hash:
        raise ValueError("Evidence is bound to a different run")
    hardware = run["declared_identity"]["hardware"]
    if value.get("resource_identity_sha256") != sha(hardware):
        raise ValueError("Evidence is bound to a different declared resource")
    left, right = _window(value.get("observed_window"))
    start, end = _date(run["started_at"]), _date(run["ended_at"])
    if accounting:
        if left > start or right < end:
            raise ValueError("Resource accounting interval does not cover the run")
    elif right > end or (start - right).total_seconds() > max_age:
        raise ValueError("Operational evidence is future-dated or outside its applicability window")
    return {"run_sha256": run_hash, "resource_identity_sha256": sha(hardware), "observed_window": value["observed_window"],
            "verification": "Exact run/resource hash and declared applicability checked; resource origin is operator-declared, not remote attestation."}


def _blob(value):
    if not isinstance(value, str) or len(value) > 32 * 1024 * 1024:
        raise ValueError("Operational raw evidence must be bounded base64")
    return base64.b64decode(value, validate=True)


def _operation_value(attachment):
    check = attachment["check_id"]
    if check in ("owned_loopback.recovery_verified", "owned_loopback.recovery_max_s"):
        raw_bytes, summary_bytes = _blob(attachment.get("raw_base64")), _blob(attachment.get("summary_base64"))
        raw, summary = json.loads(raw_bytes), json.loads(summary_bytes)
        checked = recovery_verifier.verify(raw, summary, sha(raw_bytes), "recipient-owned-resource")
        packet_bytes = _blob(attachment.get("packet_base64"))
        packet = json.loads(packet_bytes)
        collector = load(ROOT / "SOURCES.json").get("operational_collector", {})
        pin = collector.get("sha256")
        historical = collector.get("historical_recovery_sha256", [])
        if (not isinstance(historical, list) or len(historical) > 10
                or any(not isinstance(value, str) or not SHA.fullmatch(value) for value in historical)):
            raise ValueError("Invalid trusted historical recovery collector pins")
        if not isinstance(pin, str) or not SHA.fullmatch(pin) or packet.get("schema") != "ocl.instrument-packet/1" or packet.get("provenance", {}).get("source_sha256") not in {pin, *historical}:
            raise ValueError("Recovery freshness requires the retained packet from the pinned operational collector")
        entries = packet.get("files")
        if not isinstance(entries, list):
            raise ValueError("Recovery collection packet needs its source file manifest")
        entries_by_path = {}
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("path") in entries_by_path:
                raise ValueError("Invalid or duplicated operational packet file entry")
            entries_by_path[entry.get("path")] = entry
        for relative, payload in (("recovery/raw.json", raw_bytes), ("recovery/summary.json", summary_bytes)):
            entry = entries_by_path.get(relative, {})
            if entry.get("sha256") != sha(payload) or entry.get("bytes") != len(payload):
                raise ValueError("Retained collector packet does not bind recovery raw/summary bytes")
        if packet.get("operations", {}).get("service_recovery") != summary:
            raise ValueError("Recovery summary differs from the retained collector packet")
        provenance = packet["provenance"]
        observed_window = {"start": provenance["captured_at"], "end": provenance["completed_at"]}
        _window(observed_window)
        value = True if check.endswith("_verified") else max(row["stop_to_recovered_s"] for row in checked["injected_recovery_trials"])
        return value, {"verifier": "owner_ocl.recovery_verifier.verify", "raw_sha256": sha(raw_bytes),
                       "summary_sha256": sha(summary_bytes), "collection_packet_sha256": sha(packet_bytes),
                       "observed_window": observed_window, "window_rule": "exact_collector_window", "scope": checked["limits"]}
    if check == "storage.logical_integrity":
        data = attachment.get("storage", {})
        host = data.get("host")
        if not isinstance(host, str) or not re.fullmatch(r"[a-z0-9_-]{1,40}", host):
            raise ValueError("Storage evidence requires its original bounded host label")
        with tempfile.TemporaryDirectory(prefix="cantos-deployment-storage-") as temporary:
            root = Path(temporary)
            (root / "results").mkdir()
            for key, suffix in (("write", "write.json"), ("verify", "verify.json"), ("journal", "journal.jsonl")):
                (root / "results" / ("ocl13-" + host + "-storage-" + suffix)).write_bytes(_blob(data.get(key + "_base64")))
            checked = storage_verifier.load(root, host)
            write_receipt = load(root / "results" / ("ocl13-" + host + "-storage-write.json"))
            verify_receipt = load(root / "results" / ("ocl13-" + host + "-storage-verify.json"))
            observed_window = {"start": write_receipt["utc"], "end": verify_receipt["utc"]}
            _window(observed_window)
        return checked["accepted"], {"verifier": "owner_ocl.storage_verifier.load", "source_sha256": checked["source_sha256"],
                                     "observed_window": observed_window, "window_rule": "native_storage_timestamps",
                                     "scope": "Bounded logical readback; no power-loss durability or cloud SLA established."}
    raise ValueError("Unsupported operational check; no trusted raw verifier is installed")


def _network_operation_value(attachment, requirement, run):
    expected, settings = requirement["network_target"], requirement["network_protocol"]
    hardware = run["declared_identity"]["hardware"]
    if (sha(hardware) != expected["resource_identity_sha256"]
            or hardware.get("audit_host_id_sha256") != expected["responder_host_id_sha256"]):
        raise ValueError("Named responder is not bound to the native declared hardware/audit host")
    sources = load(ROOT / "SOURCES.json")
    pins = {row["path"]: row["sha256"] for row in sources["files"]}
    module_pin = pins.get("owner_ocl/network_health.py")
    collector_pin = sources.get("operational_collector", {}).get("sha256")
    if not isinstance(module_pin, str) or not SHA.fullmatch(module_pin) or not isinstance(collector_pin, str) or not SHA.fullmatch(collector_pin):
        raise ValueError("No trusted network collector/verifier source pin")
    if expected["responder_source_sha256"] != module_pin:
        raise ValueError("Designated responder source is not the installed supported source")
    blobs = {key: _blob(attachment.get(key + "_base64")) for key in ("raw", "summary", "events", "packet")}
    checked = network_health.verify_packet(blobs["raw"], blobs["summary"], blobs["events"], blobs["packet"],
        expected, settings, collector_sha256=collector_pin, producer_sha256=module_pin)
    field = "failure_count" if requirement["check_id"] == "owned_network.failure_count" else "latency_p95_ms"
    value = checked[field]
    if value is None:
        raise ValueError("Owned network latency is unknown because an authorized attempt failed")
    return value, {"verifier": "owner_ocl.network_health.verify_packet", "raw_sha256": sha(blobs["raw"]),
        "collection_packet_sha256": sha(blobs["packet"]), "expected_target": expected,
        "observed_window": checked["observed_window"], "window_rule": "exact_collector_window",
        "attempts": checked["attempts"], "failure_count": checked["failure_count"], "scope": checked["scope"],
        "identity_basis": "Exact TLS certificate pin/key possession during collection; returned host/instance/source labels remain declared identities, not signed receipts or remote execution attestation."}


def _operations(requirements, attachments, run, run_hash):
    if attachments is None:
        attachments = []
    if not isinstance(attachments, list) or len(attachments) > 100:
        raise ValueError("Operations must be a bounded attachment array")
    indexed = {}
    for record in attachments:
        if not isinstance(record, dict) or record.get("schema") != "cantos.operation-binding/1":
            raise ValueError("Unsupported operational binding schema")
        check = record.get("check_id")
        if not isinstance(check, str) or check in indexed:
            raise ValueError("Duplicate or invalid operational attachment check id")
        indexed[check] = record
    gates = []
    for req in requirements:
        gate = {**req, "status": "unknown", "value": None}
        attachment = indexed.get(req["check_id"])
        try:
            if run is None or attachment is None:
                raise ValueError("No bound operational observation is available")
            basis = attachment.get("basis", "unknown")
            if basis != "observed" or basis not in req["allowed_basis"]:
                raise ValueError("A declaration is not a verified observed operational result")
            gate["binding"] = _binding(attachment.get("binding"), run, run_hash, req["max_age_s"])
            value, proof = (_network_operation_value(attachment, req, run) if req["check_id"] in network_health.CHECKS
                            else _operation_value(attachment))
            actual_window = proof.get("observed_window")
            actual_start, actual_end = _window(actual_window)
            declared_start, declared_end = _window(attachment["binding"]["observed_window"])
            if actual_start < declared_start or actual_end > declared_end or (proof.get("window_rule") == "exact_collector_window" and (actual_start, actual_end) != (declared_start, declared_end)):
                raise ValueError("Operational applicability window differs from retained source timestamps")
            source_binding = {**attachment["binding"], "observed_window": actual_window}
            gate["binding"] = _binding(source_binding, run, run_hash, req["max_age_s"])
            gate.update(value=value, basis="observed", proof=proof)
            threshold = req["threshold"]
            if type(value) is not type(threshold) and (type(value) is bool or type(threshold) is bool):
                raise ValueError("Operational metric type differs from requirement")
            passed = value == threshold if req["operator"] == "eq" else value <= threshold if req["operator"] == "lte" else value >= threshold
            gate["status"] = "pass" if passed else "fail"
            gate["reason"] = "Trusted raw check " + ("meets" if passed else "fails") + " the selected threshold"
        except (ValueError, TypeError, KeyError, OSError) as exc:
            gate["reason"] = str(exc)
        gates.append(gate)
    required = [g for g in gates if g["required"]]
    status = "fail" if any(g["status"] == "fail" for g in required) else "unknown" if any(g["status"] == "unknown" for g in required) else "pass"
    return {"status": status, "gates": gates, "coverage": "Only the selected scoped checks; empty requirements establish no operational qualification."}


def _range(record, label):
    if not isinstance(record, dict) or record.get("basis") not in BASES - {"unknown"}:
        raise ValueError(label + " is unknown")
    if not isinstance(record.get("source"), str) or not record["source"].strip() or not isinstance(record.get("source_sha256"), str) or not SHA.fullmatch(record["source_sha256"]):
        raise ValueError(label + " requires source identity and basis")
    if ("value" in record) == ("range" in record):
        raise ValueError(label + " requires exactly value or range")
    bounds = [record["value"]] * 2 if "value" in record else record["range"]
    if not isinstance(bounds, list) or len(bounds) != 2:
        raise ValueError(label + " range requires two bounds")
    low, high = (_number(v, label) for v in bounds)
    if high < low:
        raise ValueError(label + " range is reversed")
    return [low, high]


def _energy_bounds(record, run, mode):
    """Reintegrate actual board samples, or retain explicit non-observed inputs."""
    if record.get("basis") != "observed":
        return _range({**record, **({"value": record["joules"]} if "joules" in record else {})}, "energy"), "source_declared_" + str(record.get("basis"))
    if record.get("scope") != "gpu_board" or mode != "measured_trials":
        raise ValueError("Observed whole-host/facility or reserved-window energy needs a supported raw meter adapter; supplied joules alone are not measurement")
    raw = _blob(record.get("samples_base64"))
    if sha(raw) != record.get("source_sha256"):
        raise ValueError("Energy raw sample source hash mismatch")
    payload = json.loads(raw)
    if payload.get("schema") != "cantos.power-samples/1" or payload.get("time_basis") != "capture_monotonic_s":
        raise ValueError("Energy samples must use the native capture monotonic clock")
    samples = payload.get("samples")
    if not isinstance(samples, list) or not 2 <= len(samples) <= 100000:
        raise ValueError("Energy samples must be a bounded array")
    if not isinstance(record.get("source"), str) or not record["source"].strip():
        raise ValueError("Energy samples require source provenance")
    gap = _number(record.get("max_gap_s", 2.5), "Energy max_gap_s", .000001)
    trials = run.get("trials")
    if not isinstance(trials, list) or not trials:
        raise ValueError("Native measured trial intervals are unavailable for energy alignment")
    total, prior_end = 0, None
    for trial in sorted(trials, key=lambda t: t["started_monotonic_s"]):
        left, right = trial["started_monotonic_s"], trial["ended_monotonic_s"]
        if prior_end is not None and left < prior_end:
            raise ValueError("Overlapping native trial energy intervals")
        integrated = integrate_power(samples, left, right, gap)
        if integrated["joules"] is None:
            raise ValueError("Energy samples do not bracket native trials without excessive gaps")
        total += integrated["joules"]
        prior_end = right
    # Never use a claimed total in place of integration.
    return [total, total], "recomputed_board_samples_aligned_to_native_trial_clock"


def _economics(resource, run, run_hash, accepted):
    result = {"status": "unknown", "cost_per_accepted_range": None, "energy_per_accepted_range": None,
              "known_subtotal_range": None, "unknowns": [], "components": [], "basis": [], "limitations": []}
    if resource is None or run is None:
        result["unknowns"].append("No bound resource accounting record")
        return result
    if not isinstance(resource, dict) or resource.get("schema") != "cantos.resource-binding/1":
        raise ValueError("Unsupported resource binding schema")
    try:
        result["binding"] = _binding(resource.get("binding"), run, run_hash, accounting=True)
        accounting = resource.get("accounting", {})
        left, right = _window(accounting.get("window"))
        bound_left, bound_right = _window(resource["binding"]["observed_window"])
        if (left, right) != (bound_left, bound_right):
            raise ValueError("Accounting and bound resource windows differ")
        mode = accounting.get("mode")
        if mode == "measured_trials":
            if left != _date(run["started_at"]) or right != _date(run["ended_at"]):
                raise ValueError("Measured-trial accounting must bind the exact native observation window")
            duration = run["duration_s"]
        elif mode == "reserved_window":
            duration = (right - left).total_seconds()
        else:
            raise ValueError("Declare measured_trials or reserved_window accounting")
        _number(duration, "Accounting duration", .000001)
        result["duration_s"] = duration
        result["accounting"] = accounting
        result["duration_basis"] = "Summed native measured trial windows; excludes warmup, probes, startup, between-trial pauses and reserved idle" if mode == "measured_trials" else "Explicit UTC reserved interval, including its idle allocation"
        scenario = resource.get("scenario", {})
        if not isinstance(scenario, dict) or set(scenario) - COST_FIELDS:
            raise ValueError("Unsupported cost engine scenario fields")
        ranges = {}
        for key, record in scenario.items():
            try:
                ranges[key] = _range(record, key)
                result["basis"].append({"field": key, "basis": record["basis"], "source": record["source"], "source_sha256": record["source_sha256"]})
            except ValueError as exc:
                result["unknowns"].append(str(exc))
        variable = [key for key, value in ranges.items() if value[0] != value[1]]
        if len(variable) > 7:
            raise ValueError("At most seven varying cost components are supported")
        energy = resource.get("energy")
        energy_range = None
        if energy is not None:
            energy_range, energy_verification = _energy_bounds(energy, run, mode)
            if energy.get("scope") not in ("gpu_board", "it_equipment", "facility"):
                raise ValueError("Declare board, whole-IT or facility energy scope")
            share = _number(energy.get("allocation_fraction"), "Energy allocation_fraction")
            if not 0 < share <= 1:
                raise ValueError("Energy allocation fraction must be >0 and <=1")
            energy_range = [v * share for v in energy_range]
            result["energy_scope"] = energy["scope"]
            result["energy_basis"] = {key: energy[key] for key in ("basis", "source", "source_sha256")}
            result["energy_verification"] = energy_verification
            if accepted > 0:
                result["energy_per_accepted_range"] = [v / accepted for v in energy_range]
            if energy["scope"] == "gpu_board":
                result["limitations"].append("Board energy is partial; whole-host and facility energy remain unknown.")
        extras = resource.get("additional_costs", [])
        if not isinstance(extras, list) or len(extras) > 20:
            raise ValueError("additional_costs must be bounded")
        extra_total = [0, 0]
        categories = set()
        for record in extras:
            category = record.get("category")
            if category not in ("verification", "retry", "operator", "idle", "other") or category in categories:
                raise ValueError("Duplicate or unsupported additional cost category")
            categories.add(category)
            if record.get("unit") != "USD" or record.get("includes_in_scenario") is not False:
                raise ValueError("Additional costs need USD and explicit exclusion from scenario totals")
            bounds = _range(record, "additional " + category)
            extra_total = [a + b for a, b in zip(extra_total, bounds)]
            result["basis"].append({"field": category, "basis": record["basis"], "source": record["source"], "source_sha256": record["source_sha256"]})
        # Missing additional categories are unknown, never silently zero.
        missing_extras = {"verification", "retry", "operator", "idle"} - categories
        result["unknowns"].extend("Unspecified " + key + " allocation/cost" for key in sorted(missing_extras))
        estimates = []
        for bits in itertools.product((0, 1), repeat=len(variable)):
            choices = dict(zip(variable, bits))
            settings = {key: bounds[choices.get(key, 0)] for key, bounds in ranges.items()}
            for e_index in ((0, 1) if energy_range is not None and energy_range[0] != energy_range[1] else (0,)):
                e = {"joules": energy_range[e_index], "scope": energy["scope"]} if energy_range is not None else None
                estimates.append(estimate_cost({"duration_s": duration, "accepted_tasks": accepted}, settings, e))
        unknown_components = sorted({key for estimate in estimates for key in estimate["unknown_components"]})
        result["unknowns"].extend("Unknown cost component: " + key for key in unknown_components)
        result["known_subtotal_range"] = [min(e["known_subtotal_usd"] for e in estimates) + extra_total[0], max(e["known_subtotal_usd"] for e in estimates) + extra_total[1]]
        result["components"] = estimates
        if not result["unknowns"] and accepted > 0 and all(e["complete"] for e in estimates):
            totals = [min(e["total_usd"] for e in estimates) + extra_total[0], max(e["total_usd"] for e in estimates) + extra_total[1]]
            result.update(status="complete", total_cost_range=totals, cost_per_accepted_range=[x / accepted for x in totals])
        elif accepted <= 0:
            result["unknowns"].append("No accepted-task denominator")
    except (ValueError, TypeError, KeyError) as exc:
        result["unknowns"].append(str(exc))
    result["unknowns"] = sorted(set(result["unknowns"]))
    return result


def decide_deployment(contract, native_comparison, runs, operations=None, resources=None, parent=None, *, retry_evidence=None):
    contract = validate_deployment(contract)
    native, verified_runs = _checked_native(native_comparison, runs)
    operations, resources = operations or {}, resources or {}
    if not isinstance(operations, dict) or not isinstance(resources, dict) or set(operations) - set(ARMS) or set(resources) - set(ARMS):
        raise ValueError("Operational/resource evidence must be keyed by baseline and candidate")
    operations = {side: operations.get(side) or [] for side in ARMS}
    resources = {side: resources.get(side) for side in ARMS}
    if parent is not None and (not isinstance(parent, dict) or parent.get("schema") != "cantos.deployment-decision/1"
                               or not isinstance(parent.get("decision_identity"), str) or not SHA.fullmatch(parent["decision_identity"])):
        raise ValueError("A successor requires its immutable parent deployment decision")
    hashes = {side: sha(Path(runs[side]).read_bytes()) for side in ARMS if side in runs and Path(runs[side]).is_file()}
    reqs = contract["decision"]["operational_requirements"]
    retry_layer = deployment_retry.join(verified_runs, retry_evidence, contract.get("retry"), native.get("policy")) if "retry" in contract or retry_evidence else None
    retry_economics = bool(retry_layer and retry_layer["controls"]["economics"])
    layers = {"useful_work": {"verdict": native["verdict"], "reasons": native.get("reasons", []),
                               "comparability_failures": native.get("comparability_failures", []), "regressions": native.get("regressions", [])},
              "operations": {}, "economics": {}}
    unknowns, reversal, eligibility = [], [], {}
    for side in ARMS:
        run, run_hash = verified_runs.get(side), hashes.get(side)
        op = _operations(reqs, operations.get(side), run, run_hash)
        retry_op = None
        if retry_layer and (retry_layer["controls"]["required"] or retry_economics) and run and side in retry_layer["arms"]:
            facts = retry_layer["arms"][side]
            campaign_run = {**run, "started_at": facts["window"]["start"], "ended_at": facts["window"]["end"]}
            retry_op = _operations(reqs, operations.get(side), campaign_run, run_hash)
            facts["operations"] = retry_op
            for gate in retry_op["gates"]:
                if gate["status"] == "unknown":
                    unknowns.append({"layer": "retry_operations", "arm": side, "id": gate["id"], "required": gate["required"], "reason": gate["reason"]})
        accepted = native.get(side, {}).get("accepted_tasks", 0)
        ec = _economics(resources.get(side), run, run_hash, accepted)
        layers["operations"][side], layers["economics"][side] = op, ec
        quality = native.get(side, {}).get("acceptance_rate")
        minimum = native.get("policy", {}).get("min_" + side + "_acceptance")
        failed_quality = quality is not None and minimum is not None and (accepted == 0 or quality < minimum)
        native_candidate_regression = side == "candidate" and native["verdict"] == "regression"
        operation_failed = op["status"] == "fail" or bool(retry_op and retry_op["status"] == "fail")
        operation_unknown = op["status"] == "unknown" or bool(retry_op and retry_op["status"] == "unknown")
        eligibility[side] = "ineligible" if failed_quality or native_candidate_regression or operation_failed else "unknown" if quality is None or operation_unknown else "eligible"
        for gate in op["gates"]:
            if gate["status"] == "unknown":
                unknowns.append({"layer": "operations", "arm": side, "id": gate["id"], "required": gate["required"], "reason": gate["reason"]})
            if gate["status"] != "pass":
                reversal.append(side + ": resolve " + gate["id"] + " (" + gate["reason"] + ")")
        for reason in ec["unknowns"]:
            unknowns.append({"layer": "economics", "arm": side, "id": "accounting", "required": contract["decision"]["economics_required"] and not retry_economics, "reason": reason})
        if failed_quality:
            needed = math.ceil(minimum * native[side]["total_tasks"] - 1e-12)
            reversal.append(side + ": accepted " + str(accepted) + "; requirement needs at least " + str(needed) + " of " + str(native[side]["total_tasks"]) + ". Price changes cannot repair useful-work acceptance.")
    metric = "cost_per_accepted_range" if contract["decision"]["objective"] == "min_cost_per_accepted" else "energy_per_accepted_range"
    a, b = (layers["economics"][side].get(metric) for side in ARMS)
    if retry_layer:
        layers["retry"] = retry_layer
        required = retry_layer["controls"]["required"] or retry_economics
        unknowns.extend({"layer": "retry", "arm": "both", "id": "campaign", "required": required, "reason": reason} for reason in retry_layer["unknowns"])
        if retry_economics:
            # An explicit alternate accounting population, never a synthetic native run.
            values = []
            for side in ARMS:
                facts = retry_layer["arms"].get(side, {})
                bounds = (facts.get("allocations") or {}).get("cost_per_accepted_range") if retry_layer["status"] == "complete" else None
                values.append(bounds)
                metrics = facts.get("metrics", {})
                offered, accepted = metrics.get("offered_tasks", 0), metrics.get("accepted_tasks", 0)
                minimum = native.get("policy", {}).get("min_" + side + "_acceptance")
                if facts.get("status") == "complete" and minimum is not None and (not offered or accepted / offered < minimum):
                    eligibility[side] = "ineligible"
            a, b = values
            if metric != "cost_per_accepted_range":
                a = b = None
                unknowns.append({"layer": "retry", "arm": "both", "id": "whole_system_energy", "required": True,
                                 "reason": "Retry telemetry covers boards only; whole-host/facility retry energy is unknown"})
    if metric == "energy_per_accepted_range":
        # A board-only estimate is never enough for a whole deployment energy objective.
        for side in ARMS:
            if layers["economics"][side].get("energy_scope") not in ("it_equipment", "facility"):
                if side == "baseline": a = None
                else: b = None
                unknowns.append({"layer": "economics", "arm": side, "id": "whole_system_energy", "required": True, "reason": "Whole-host/facility energy is unknown; board energy is descriptive only"})
        if a is not None and b is not None and layers["economics"]["baseline"]["energy_scope"] != layers["economics"]["candidate"]["energy_scope"]:
            a = b = None
            unknowns.append({"layer": "economics", "arm": "both", "id": "energy_boundary_mismatch", "required": True,
                             "reason": "Whole-IT and facility energy have different accounting boundaries and cannot be ranked against each other"})
    if native["verdict"] == "error":
        state = "INCOMPLETE"
    elif native["verdict"] == "incomparable":
        state = "INCOMPARABLE"
    elif all(value == "ineligible" for value in eligibility.values()):
        state = "NO-ELIGIBLE"
    elif "unknown" in eligibility.values():
        state = "UNDETERMINED"
    elif native["verdict"] == "regression":
        state = "KEEP-BASELINE" if eligibility["baseline"] == "eligible" else "NO-ELIGIBLE"
    elif eligibility["candidate"] == "ineligible":
        state = "KEEP-BASELINE"
    elif eligibility["baseline"] == "ineligible":
        state = "SELECT-CANDIDATE" if b is not None else "UNDETERMINED"
    elif a is None or b is None:
        state = "UNDETERMINED"
    elif b[1] < a[0]:
        state = "SELECT-CANDIDATE"
    elif b[0] >= a[1]:
        state = "KEEP-BASELINE"
    else:
        state = "UNDETERMINED"
        reversal.append("Economic ranges overlap; no robust preference. Narrow the source-bound ranges or declare additional evidence.")
    if a is not None:
        reversal.append("Candidate's " + metric.replace("_range", "") + " must be below baseline's lower bound " + str(a[0]) + " to establish robust economic preference.")
    if any(u["required"] for u in unknowns) and state in ("SELECT-CANDIDATE", "KEEP-BASELINE"):
        state = "UNDETERMINED"
    result = {"schema": "cantos.deployment-decision/1", "job_id": contract["id"], "state": state,
              "native_verdict": native["verdict"], "native": native, "layers": layers, "eligibility": eligibility,
              "unknowns": unknowns, "reversal_conditions": list(dict.fromkeys(reversal)),
              "dependencies": {"runs": hashes, "operations": sha(operations), "resources": sha(resources), "contract": sha(contract)},
              "post_hoc": parent is not None, "parent_id": parent.get("decision_identity") if parent else None,
              "original_id": (parent.get("original_id") or parent.get("decision_identity")) if parent else None,
              "execution": {"inference_requests": 0, "grader_executions": 0},
              "limitations": ["Native useful-work verdict is preserved. Operational raw checks have their stated local scope; resource origin is declared, not remote-attested.",
                              "Economic values retain their supplied source basis; source hashes establish custody, not invoice truth or meter calibration.",
                              "This joined job does not complete broader provider, accelerator, agentic-workload or full-system empirical coverage."]}
    if retry_layer:
        result["economic_population"] = "retry_campaign" if retry_economics else "native_measured_trials"
        result["dependencies"]["retry"] = retry_layer["dependencies"]
    # Native analysis timestamps/path projections do not create a new semantic decision.
    semantic = copy.deepcopy(result)
    semantic.pop("native")
    if retry_layer:
        for facts in semantic["layers"]["retry"]["arms"].values():
            if facts.get("resources"):
                facts["resources"].pop("source_code", None)
    semantic["native_core"] = {key: native.get(key) for key in ("verdict", "policy", "baseline", "candidate", "changed_factors", "comparability_failures", "regressions")}
    result["decision_identity"] = sha(semantic)
    return result
