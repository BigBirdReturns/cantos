"""Run, retain, decide, export and re-import one recipient-owned deployment job.

The manifest is data. Only the shipped maintainer engine and decision logic run;
uploaded grader or helper code is never executed.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import socket
import sys
import uuid
import zipfile

try:
    from . import deployment, deployment_bundle, deployment_retry, external_grader, maintainer, packets
    from .common import canonical, load, sha256_file, write
except ImportError:
    import deployment, deployment_bundle, deployment_retry, external_grader, maintainer, packets
    from common import canonical, load, sha256_file, write

SCHEMA = "cantos.deployment-job/1"
MAX_OBSERVATIONS = 100_000


def _inside(root: Path, value: str, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(label + " must be a relative POSIX path")
    rel = PurePosixPath(value)
    if rel.is_absolute() or any(part in ("", ".", "..") for part in rel.parts):
        raise ValueError(label + " must stay inside the job")
    path = (root / Path(*rel.parts)).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(label + " escapes the job") from exc
    if not path.is_file():
        raise ValueError(label + " is missing")
    return path


def _load_job(path: Path):
    path = path.resolve()
    job = deployment.validate_deployment(load(path))
    base = path.parent
    comparison = job.get("comparison")
    if not isinstance(comparison, dict) or set(comparison) - {"spec", "baseline_grades", "candidate_grades", "grading_contract"}:
        raise ValueError("comparison needs spec and optional receipt paths")
    spec_path = _inside(base, comparison.get("spec"), "comparison.spec")
    spec = load(spec_path)
    if spec.get("schema") != "cantos.maintainer.spec/1":
        raise ValueError("Expected cantos.maintainer.spec/1")
    workload_path = _inside(spec_path.parent, spec.get("workload"), "spec.workload")
    policy_path = _inside(spec_path.parent, spec.get("policy"), "spec.policy") if spec.get("policy") else None
    workload = load(workload_path)
    protocol = maintainer.prepare(spec_path)["baseline"]["protocol"]
    count = protocol["trials"] * protocol["repeats"] * len(workload.get("cases", []))
    if count > MAX_OBSERVATIONS:
        raise ValueError("Expected observations exceed the 100000 job limit")
    for side in ("baseline", "candidate"):
        config = spec[side]
        for name in config.get("implementation_files", []):
            _inside(spec_path.parent, name, side + ".implementation_files")
    grades = {}
    for side in ("baseline", "candidate"):
        key = side + "_grades"
        if key in comparison:
            grades[side] = _inside(base, comparison[key], "comparison." + key)
            grade_record = load(grades[side])
            artifacts = grade_record.get("artifacts", [])
            if not isinstance(artifacts, list) or len(artifacts) > 10000:
                raise ValueError("Grade artifact closure is invalid or too large")
            for entry in artifacts:
                if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                    raise ValueError("Grade artifact closure entry is invalid")
                _inside(grades[side].parent, entry["path"], "grade artifact")
    grading_contract = _inside(base, comparison["grading_contract"], "comparison.grading_contract") if comparison.get("grading_contract") else None
    external = job.get("external_grading")
    if external is not None:
        external_grader.validate_config(external, base)
        if external.get("execute") is True and (grades or grading_contract):
            raise ValueError("Choose explicit external_grading execution or preattached grade receipts, not both")
    operations, resources, collections = {}, {}, {}
    arms = job.get("arms", {})
    for side in ("baseline", "candidate"):
        arm = arms[side]
        if not isinstance(arm, dict) or set(arm) - {"operations", "resources", "resource_template", "collection", "retry"}:
            raise ValueError("Arm permits only operations, resources, resource_template, collection and retry")
        ops = arm.get("operations", [])
        if not isinstance(ops, list) or len(ops) > 100:
            raise ValueError("operations must be a bounded list of paths")
        operations[side] = [_inside(base, item, side + ".operations") for item in ops]
        resources[side] = _inside(base, arm["resources"], side + ".resources") if arm.get("resources") else None
        if arm.get("resource_template"):
            _inside(base, arm["resource_template"], side + ".resource_template")
        retry_item = arm.get("retry")
        if retry_item is not None:
            if not isinstance(retry_item, dict) or set(retry_item) - {"campaign", "telemetry", "scenario", "allocations"} or not retry_item.get("campaign"):
                raise ValueError(side + ".retry requires a campaign and optional telemetry/scenario/allocations files")
            for key, value in retry_item.items():
                _inside(base, value, side + ".retry." + key)
        collections[side] = _inside(base, arm["collection"], side + ".collection") if arm.get("collection") else None
    return job, base, spec_path, spec, workload_path, policy_path, grades, grading_contract, operations, resources, collections, count


def _retry_paths(job, root):
    result = {}
    for side in ("baseline", "candidate"):
        item = job.get("arms", {}).get(side, {}).get("retry")
        if item:
            result[side] = {key: _inside(root, value, side + ".retry." + key) for key, value in item.items()}
    return result


def _retry_closure(campaign_path):
    campaign_path = Path(campaign_path).resolve()
    root = campaign_path.parent
    limits = {campaign_path: 64 * 1024 * 1024, root / "plan.json": 16 * 1024 * 1024,
              root / "workload.json": 64 * 1024 * 1024, root / "events.jsonl": 256 * 1024 * 1024}
    for path, limit in limits.items():
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            raise ValueError("Retry campaign contains a missing or oversized core input")
    raw_campaign, plan, workload = load(campaign_path), load(root / "plan.json"), load(root / "workload.json")
    identity = plan.get("identity", {})
    observed = identity.get("owner_observation_identity", {})
    proto_value = observed.get("protocol", {})
    trials, repeats = proto_value.get("trials"), proto_value.get("repeats")
    cases, tasks = workload.get("cases"), raw_campaign.get("tasks")
    if type(trials) is not int or type(repeats) is not int or not (1 <= trials <= 100 and 1 <= repeats <= 100):
        raise ValueError("Retry protocol counts must be bounded exact integers")
    if not isinstance(cases, list) or not isinstance(tasks, list):
        raise ValueError("Retry campaign needs bounded workload cases and tasks")
    expected = trials * repeats * len(cases)
    if not 1 <= expected <= 100_000 or expected != len(tasks):
        raise ValueError("Retry campaign task cardinality mismatch or limit")
    checked = deployment_retry.retry.validate_campaign(campaign_path)
    if checked.get("tasks") != raw_campaign.get("tasks"):
        raise ValueError("Retry campaign changed during bounded preflight")
    files = {campaign_path, root / "plan.json", root / "workload.json", root / "events.jsonl"}
    for item in checked.get("artifacts", []):
        path = (root / item["path"]).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("Retry campaign artifact escapes its root") from exc
        if not path.is_file() or path.is_symlink():
            raise ValueError("Retry campaign artifact is missing or unsafe")
        files.add(path)
    if any(not path.is_file() or path.is_symlink() for path in files):
        raise ValueError("Retry campaign closure contains a missing or unsafe file")
    if len(files) > 100_000 or sum(path.stat().st_size for path in files) > 1024 * 1024 * 1024:
        raise ValueError("Retry campaign closure exceeds retained job limits")
    return files


def _retry_telemetry_closure(telemetry_path):
    telemetry_path = Path(telemetry_path).resolve()
    if telemetry_path.is_symlink() or not telemetry_path.is_file():
        raise ValueError("Retry telemetry receipt is missing or unsafe")
    receipt = load(telemetry_path)
    record = receipt.get("samples")
    if not isinstance(record, dict):
        raise ValueError("Retry telemetry must bind its raw samples journal")
    journal = deployment_retry.retry_resources._safe_source(telemetry_path.parent, record)
    return {telemetry_path, journal}


def _stage_retry_inputs(retry_paths, base, out):
    staged = {}
    for side, item in retry_paths.items():
        campaign = item["campaign"]
        source_root = campaign.parent
        try:
            source_root.relative_to(base.resolve())
        except ValueError as exc:
            raise ValueError("Retry campaign root must be inside its manifest directory") from exc
        closure = _retry_closure(campaign)
        target_root = out / "inputs" / "retry" / side
        target_root.mkdir(parents=True, exist_ok=True)
        for source in closure:
            relative = source.relative_to(source_root)
            target = target_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        staged_item = {"campaign": (target_root / campaign.relative_to(source_root)).relative_to(out).as_posix()}
        for key in ("telemetry", "scenario", "allocations"):
            if key in item:
                staged_item[key] = _copy_file_to_inputs(item[key], base, out).relative_to(out).as_posix()
                if key == "telemetry":
                    receipt = load(item[key])
                    sample_record = receipt["samples"]
                    sample_source = deployment_retry.retry_resources._safe_source(item[key].parent, sample_record)
                    staged_telemetry = out / staged_item[key]
                    sample_target = staged_telemetry.parent / sample_record["path"]
                    sample_target.parent.mkdir(parents=True, exist_ok=True)
                    if not sample_target.exists():
                        shutil.copyfile(sample_source, sample_target)
        staged[side] = staged_item
    return staged


def _preflight_run(path: Path, workload_cases: int):
    """Bound protocol expansion before validate_receipt constructs its Cartesian set."""
    raw = load(path)
    proto = raw.get("protocol") if isinstance(raw, dict) else None
    if not isinstance(proto, dict):
        raise ValueError("Run receipt has no protocol")
    trials, repeats = proto.get("trials"), proto.get("repeats")
    if type(trials) is not int or type(repeats) is not int or not (1 <= trials <= 100 and 1 <= repeats <= 100):
        raise ValueError("Run protocol trial and repeat counts must be bounded exact integers")
    expected = trials * repeats * workload_cases
    if expected > MAX_OBSERVATIONS:
        raise ValueError("Run protocol expands beyond the 100000 observation limit")
    observations = raw.get("observations")
    if not isinstance(observations, list) or len(observations) != expected:
        raise ValueError("Run observation count differs from bounded protocol/workload expectation")
    return raw, expected


def _validate_runs_against_spec(spec_path: Path, workload_cases: int, runs: dict):
    checked = {}
    for side, path in runs.items():
        raw, expected = _preflight_run(path, workload_cases)
        prepared = maintainer.prepare(spec_path, side)
        recorded = raw.get("observation_identity", {})
        requested = prepared["identity"]
        capture_fields = ("configuration", "implementation_inputs", "workload_sha256", "protocol")
        if any(recorded.get(key) != requested.get(key) for key in capture_fields):
            raise ValueError("capture_required: " + side + " serving/workload/protocol identity changed")
        validated = maintainer.validate_receipt(path)
        if len(validated["observations"]) != expected:
            raise ValueError("Run validator count differs from preflight")
        checked[side] = validated
    return checked


def _copy_source_inputs(out: Path, base: Path, spec_path: Path, spec: dict,
                        policy_path: Path | None, grades: dict, grading_contract: Path | None,
                        operations: dict, resources: dict):
    """Copy only declared data inputs, retaining spec-relative closure paths."""
    inputs = out / "inputs"
    inputs.mkdir()
    copied = {}

    def copy_file(src: Path, ref_root: Path):
        src = src.resolve()
        try:
            rel = src.relative_to(ref_root.resolve())
        except ValueError as exc:
            raise ValueError("Declared input is outside its reference root") from exc
        target = inputs / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(src, target)
        copied[src] = target
        return target

    # Spec-relative paths are retained under inputs/ so prepare() sees the same closure.
    for name in (spec["workload"], spec.get("policy")):
        if name:
            copy_file((spec_path.parent / name).resolve(), base)
    for side in ("baseline", "candidate"):
        for name in spec[side].get("implementation_files", []):
            copy_file((spec_path.parent / name).resolve(), base)
    staged_spec = copy_file(spec_path, base)
    if policy_path:
        copy_file(policy_path, base)
    staged_grades = {side: copy_file(path, base) for side, path in grades.items()}
    for grade_path in grades.values():
        for entry in load(grade_path).get("artifacts", []):
            copy_file(_inside(grade_path.parent, entry["path"], "grade artifact"), base)
    staged_contract = copy_file(grading_contract, base) if grading_contract else None
    staged_ops = {side: [copy_file(path, base) for path in paths] for side, paths in operations.items()}
    staged_resources = {side: copy_file(path, base) if path else None for side, path in resources.items()}
    return staged_spec, staged_grades, staged_contract, staged_ops, staged_resources, copied


def _copy_file_to_inputs(source: Path, base: Path, out: Path):
    source = source.resolve()
    try:
        relative = source.relative_to(base.resolve())
    except ValueError as exc:
        raise ValueError("Declared collection input is outside manifest directory") from exc
    target = out / "inputs" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copyfile(source, target)
    return target


def _bind_job_evidence(job: dict, runs: dict, collections: dict, operation_paths: dict,
                       resource_paths: dict, out: Path, *, evidence_root: Path | None = None):
    derived_ops, derived_resources = {}, {}
    requirements = job.get("decision", {}).get("operational_requirements", [])
    evidence_root = evidence_root or (out / "derived-evidence" / uuid.uuid4().hex)
    ops_root = evidence_root / "operations"
    resources_root = evidence_root / "resources"
    for directory in (ops_root, resources_root):
        directory.mkdir(parents=True, exist_ok=True)
    for side in ("baseline", "candidate"):
        run_path = Path(runs[side])
        run = maintainer.load(run_path)
        hardware = run["declared_identity"]["hardware"]
        run_hash = hashlib.sha256(run_path.read_bytes()).hexdigest()
        generated = []
        existing_checks = set()
        network_templates, bound_network = {}, {}
        for path in operation_paths.get(side, []):
            retained = load(path)
            for item in retained if isinstance(retained, list) else [retained]:
                if isinstance(item, dict):
                    check = item.get("check_id")
                    if item.get("schema") == "cantos.operation-template/1":
                        if check not in deployment.network_health.CHECKS or check in network_templates:
                            raise ValueError("Duplicate or unsupported network operation template")
                        network_templates[check] = item
                    else:
                        existing_checks.add(check)
                        if check in deployment.network_health.CHECKS:
                            bound_network[check] = item
        for check, template in network_templates.items():
            template_hash = hashlib.sha256(canonical(template)).hexdigest()
            if check in bound_network:
                if bound_network[check].get("template_sha256") != template_hash:
                    raise ValueError("Changed network acquisition requires removing its stale bound attachment from the child manifest")
                continue
            raw = deployment.network_health.strict(deployment._blob(template.get("raw_base64")))
            attachment = {**template, "schema": "cantos.operation-binding/1", "template_sha256": template_hash,
                "binding": {"run_sha256": run_hash, "resource_identity_sha256": deployment.sha(hardware),
                            "observed_window": {"start": raw["started_at"], "end": raw["ended_at"]}}}
            generated.append(attachment)
        collection_path = collections.get(side)
        if collection_path:
            acquisition = load(collection_path)
            if acquisition.get("schema") != "cantos.local-operation-acquisition/1":
                raise ValueError("Unsupported local operation acquisition schema")
            supported_required = {req["check_id"] for req in requirements
                                  if req.get("required") and req["check_id"] in
                                  ("owned_loopback.recovery_verified", "owned_loopback.recovery_max_s")}
            if supported_required.issubset(existing_checks):
                # Reanalysis reuses retained bindings and never recollects or
                # changes custody/freshness based on the importing machine.
                acquisition = None
        else:
            acquisition = None
        if collection_path and acquisition is not None:
            expected_host = hardware.get("audit_host_label")
            expected_host_hash = hardware.get("audit_host_id_sha256")
            if not expected_host or not expected_host_hash or acquisition.get("host_label") != expected_host or acquisition.get("host_id_sha256") != expected_host_hash:
                # Preserve the input but do not attach it to this serving identity.
                derived_ops[side] = []
            else:
                if acquisition.get("host_id_sha256") != hashlib.sha256(socket.gethostname().encode("utf-8")).hexdigest():
                    raise ValueError("Collection host differs from the local paired-run host")
                if acquisition.get("hardware_identity_sha256") != deployment.sha(hardware):
                    raise ValueError("Collection hardware identity differs from native run declaration")
                binding = {"run_sha256": run_hash, "resource_identity_sha256": deployment.sha(hardware),
                           "observed_window": acquisition["observed_window"]}
                for req in requirements:
                    check = req["check_id"]
                    if check not in ("owned_loopback.recovery_verified", "owned_loopback.recovery_max_s"):
                        continue
                    if check in existing_checks:
                        continue
                    attachment = {"schema": "cantos.operation-binding/1", "check_id": check,
                                  "binding": binding, "basis": "observed",
                                  "raw_base64": acquisition["raw_base64"],
                                  "summary_base64": acquisition["summary_base64"],
                                  "packet_base64": acquisition["packet_base64"],
                                  "collection_sha256": hashlib.sha256(base64.b64decode(acquisition["packet_base64"], validate=True)).hexdigest()}
                    generated.append(attachment)
                derived_ops[side] = []
        else:
            derived_ops[side] = []
        if generated:
            destination = ops_root / (side + ".json")
            write(destination, generated)
            derived_ops[side] = [destination]
        resource_path = resource_paths.get(side)
        if resource_path:
            resource = load(resource_path)
            if resource.get("schema") == "cantos.resource-template/1":
                if resource.get("resource_identity_sha256") != deployment.sha(hardware):
                    raise ValueError("Resource template hardware identity differs from native run declaration")
                if resource.get("accounting_mode") != "measured_trials":
                    raise ValueError("New run resource templates currently require measured_trials accounting")
                bound = {"schema": "cantos.resource-binding/1",
                         "binding": {"run_sha256": run_hash, "resource_identity_sha256": deployment.sha(hardware),
                                     "observed_window": {"start": run["started_at"], "end": run["ended_at"]}},
                         "accounting": {"mode": "measured_trials", "window": {"start": run["started_at"], "end": run["ended_at"]}},
                         "scenario": resource.get("scenario", {}), "additional_costs": resource.get("additional_costs", [])}
                if "energy" in resource:
                    bound["energy"] = resource["energy"]
                destination = resources_root / (side + ".json")
                write(destination, bound)
                derived_resources[side] = destination
            else:
                derived_resources[side] = resource_path
        else:
            derived_resources[side] = None
    ops, resources = _read_evidence({side: operation_paths[side] + derived_ops[side] for side in ("baseline", "candidate")},
                                    {side: derived_resources[side] or resource_paths.get(side) for side in ("baseline", "candidate")})
    return ops, resources, derived_ops, derived_resources


def _native_for_run(run_root: Path, spec_path: Path, grades: dict, grading_contract: Path | None):
    run_root.mkdir(parents=True, exist_ok=False)
    native = maintainer.run(spec_path, run_root / "capture")
    # Native run has already analyzed. If grades are attached, recompute with those
    # exact receipts; otherwise retain the native result without a redundant analysis.
    if not grades and not grading_contract:
        return native
    policy_name = load(spec_path).get("policy")
    policy_path = (spec_path.parent / policy_name).resolve() if policy_name else None
    native = maintainer.analyze_receipts(run_root / "capture" / "baseline" / "run.json",
                                         run_root / "capture" / "candidate" / "run.json",
                                         policy_path, run_root / "analysis",
                                         baseline_grades=grades.get("baseline"),
                                         candidate_grades=grades.get("candidate"),
                                         grading_contract=grading_contract)
    return native


def _read_evidence(operations, resources):
    ops = {}
    for side, paths in operations.items():
        ops[side] = []
        for path in paths:
            value = load(path)
            ops[side].extend(item for item in (value if isinstance(value, list) else [value])
                             if not isinstance(item, dict) or item.get("schema") != "cantos.operation-template/1")
    res = {side: load(path) if path else None for side, path in resources.items()}
    return ops, res


def _portable_native(native: dict, root: Path):
    value = copy.deepcopy(native)
    for record in value.get("inputs", {}).values():
        source = record.get("path")
        if not source:
            continue
        try:
            record["path"] = Path(source).resolve().relative_to(root.resolve()).as_posix()
        except (ValueError, OSError):
            record.pop("path", None)
            record["path_status"] = "source path omitted; retained inputs are in this job bundle"
    return value


def _input_hashes(root: Path):
    """Hash only declared data closure files, including bound/generated attachments."""
    job, base, spec_path, spec, workload_path, policy_path, grades, grading_contract, operations, resources, collections, _ = _load_job(root / "job.json")
    files = {spec_path, workload_path, *grades.values(), *operations["baseline"], *operations["candidate"]}
    if policy_path:
        files.add(policy_path)
    if grading_contract:
        files.add(grading_contract)
    files.update(p for p in resources.values() if p)
    files.update(p for p in collections.values() if p)
    retries = _retry_paths(job, base)
    for item in retries.values():
        files.update(_retry_closure(item["campaign"]))
        files.update(item[key] for key in ("telemetry", "scenario", "allocations") if key in item)
        if "telemetry" in item:
            files.update(_retry_telemetry_closure(item["telemetry"]))
    for side in ("baseline", "candidate"):
        ref = job["arms"][side].get("resource_template")
        if ref:
            files.add(_inside(base, ref, side + " resource template"))
    if job.get("external_grading"):
        files.update(external_grader.validate_config(job["external_grading"], base)["paths"].values())
    if job.get("execution_plan"):
        files.add(_inside(base, job["execution_plan"], "execution plan"))
    for side in ("baseline", "candidate"):
        for name in spec[side].get("implementation_files", []):
            files.add(_inside(spec_path.parent, name, side + " implementation file"))
    for grade_path in grades.values():
        for entry in load(grade_path).get("artifacts", []):
            files.add(_inside(grade_path.parent, entry["path"], "grade artifact"))
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in sorted(files)}


def _replace_json(path: Path, value: dict):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _write_status(root: Path, status: str, decision_identity: str | None = None):
    value = {"schema": "cantos.deployment-job-status/1", "status": status}
    if decision_identity:
        value["decision_identity"] = decision_identity
    _replace_json(root / "decision-status.json", value)


def _require_complete(root: Path):
    status = load(_inside(root, "decision-status.json", "decision status"))
    decision = load(_inside(root, "decision.json", "decision.json"))
    result = load(_inside(root, "job-result.json", "job-result.json"))
    if (status.get("schema") != "cantos.deployment-job-status/1" or status.get("status") != "complete"
            or status.get("decision_identity") != decision.get("decision_identity")
            or result.get("decision_identity") != decision.get("decision_identity")):
        raise ValueError("Retained job is incomplete or its decision/status records differ")
    return decision


def run_job(manifest_path, out_dir):
    """Stage a manifest closure, perform one paired run, then make a deployment decision."""
    (job, base, spec_path, spec, workload_path, policy_path, grades, grading_contract,
     operations, resources, collections, expected) = _load_job(Path(manifest_path))
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    _write_status(out, "in_progress")
    staged_spec, staged_grades, staged_contract, staged_ops, staged_resources, copied = _copy_source_inputs(
        out, base, spec_path, spec, policy_path, grades, grading_contract, operations, resources)
    staged_collections = {side: _copy_file_to_inputs(path, base, out) if path else None
                          for side, path in collections.items()}
    staged_retry = _stage_retry_inputs(_retry_paths(job, base), base, out)
    external = copy.deepcopy(job.get("external_grading"))
    execution_plan = None
    if external is not None:
        execution_plan = copy.deepcopy(external)
        selected_external = external_grader.validate_config(external, base)
        for field, source in selected_external["paths"].items():
            external[field] = _copy_file_to_inputs(source, base, out).relative_to(out).as_posix()
    # Preserve a portable manifest with only paths inside this output directory.
    staged = copy.deepcopy(job)
    staged["comparison"]["spec"] = staged_spec.relative_to(out).as_posix()
    staged["comparison"].pop("baseline_grades", None)
    staged["comparison"].pop("candidate_grades", None)
    staged["comparison"].pop("grading_contract", None)
    for side, path in staged_grades.items():
        staged["comparison"][side + "_grades"] = path.relative_to(out).as_posix()
    if staged_contract:
        staged["comparison"]["grading_contract"] = staged_contract.relative_to(out).as_posix()
    for side in ("baseline", "candidate"):
        staged["arms"][side]["operations"] = [p.relative_to(out).as_posix() for p in staged_ops[side]]
        staged["arms"][side]["resources"] = staged_resources[side].relative_to(out).as_posix() if staged_resources[side] else None
        staged["arms"][side]["collection"] = staged_collections[side].relative_to(out).as_posix() if staged_collections[side] else None
        if side in staged_retry:
            staged["arms"][side]["retry"] = staged_retry[side]
    if external is not None:
        staged["external_grading"] = external
    for side in ("baseline", "candidate"):
        template_path = staged_resources[side]
        if template_path and load(template_path).get("schema") == "cantos.resource-template/1":
            staged["arms"][side]["resource_template"] = template_path.relative_to(out).as_posix()
    write(out / "job.json", staged)
    write(out / "input-hashes.json", {p.relative_to(out).as_posix(): sha256_file(p) for p in copied.values()})
    native = _native_for_run(out / "native", staged_spec, staged_grades, staged_contract)
    run_paths = {side: out / "native" / "capture" / side / "run.json" for side in ("baseline", "candidate")}
    if external is not None and external.get("execute") is True:
        grade_out = external_grader.grade_pair(run_paths, external, out, out / "external-grading")
        staged_grades = {side: grade_out[side] for side in ("baseline", "candidate")}
        staged_contract = grade_out.get("grading_contract")
        staged["comparison"]["baseline_grades"] = staged_grades["baseline"].relative_to(out).as_posix()
        staged["comparison"]["candidate_grades"] = staged_grades["candidate"].relative_to(out).as_posix()
        if staged_contract:
            staged["comparison"]["grading_contract"] = staged_contract.relative_to(out).as_posix()
        # Retain what was explicitly authorized, but completed jobs are data-only
        # and can never trigger a second grader execution during replay.
        staged["execution_plan"] = "execution-plan.json"
        write(out / "execution-plan.json", {"schema": "cantos.deployment-execution-plan/1",
                                             "external_grading": execution_plan,
                                             "executed": True, "inference_requests": 0})
        staged["external_grading"] = dict(external, execute=False)
        policy_name = load(staged_spec).get("policy")
        selected_policy = (staged_spec.parent / policy_name).resolve() if policy_name else None
        native = maintainer.analyze_receipts(run_paths["baseline"], run_paths["candidate"],
                                             selected_policy,
                                             out / "native" / "final-analysis",
                                             baseline_grades=staged_grades["baseline"],
                                             candidate_grades=staged_grades["candidate"],
                                             grading_contract=staged_contract)
    ops, res, derived_ops, derived_resources = _bind_job_evidence(
        staged, run_paths, staged_collections, staged_ops, staged_resources, out,
        evidence_root=out / "derived-evidence" / ("initial-" + uuid.uuid4().hex))
    for side in ("baseline", "candidate"):
        staged["arms"][side]["operations"] = [p.relative_to(out).as_posix() for p in staged_ops[side] + derived_ops[side]]
        # Keep the collection source as provenance, but do not regenerate a check
        # already represented by a retained bound attachment on reanalysis.
        staged["arms"][side]["resources"] = derived_resources[side].relative_to(out).as_posix() if derived_resources[side] else (
            staged_resources[side].relative_to(out).as_posix() if staged_resources[side] else None)
    _replace_json(out / "job.json", staged)
    _replace_json(out / "input-hashes.json", _input_hashes(out))
    decision = deployment.decide_deployment(staged, native, run_paths, ops, res,
                                              retry_evidence=_retry_paths(staged, out) or None)
    # Store portable references; all receipts and inputs are in the job root.
    for item in decision.get("native", {}).get("inputs", {}).values():
        if item.get("path"):
            try:
                item["path"] = Path(item["path"]).resolve().relative_to(out).as_posix()
            except ValueError:
                item["path"] = "retained source path omitted; use native run receipts in this bundle"
    write(out / "native-verdict.json", _portable_native(native, out))
    write(out / "decision.json", decision)
    write(out / "job-result.json", {"schema": "cantos.deployment-job-result/1", "expected_observations": expected,
                                      "actual_observations": sum(len(maintainer.load(run_paths[s])["observations"]) for s in ("baseline", "candidate")),
                                      "inference_requests": sum(maintainer.load(run_paths[s]).get("inference_requests", 0) for s in ("baseline", "candidate")),
                                      "decision_identity": decision["decision_identity"]})
    _write_status(out, "complete", decision["decision_identity"])
    return decision


def decide_job(root_dir, out_dir, *, manifest_path=None):
    """Reanalyze retained observations under an optional changed manifest, without inference."""
    root, out = Path(root_dir).resolve(), Path(out_dir).resolve()
    manifest = Path(manifest_path).resolve() if manifest_path else root / "job.json"
    try:
        manifest.relative_to(root)
    except ValueError as exc:
        raise ValueError("Updated manifest must be staged inside the retained job directory") from exc
    job, base, spec_path, spec, workload_path, policy_path, grades, grading_contract, operations, resources, collections, expected = _load_job(manifest)
    runs = {side: _inside(root, "native/capture/" + side + "/run.json", side + " run") for side in ("baseline", "candidate")}
    _validate_runs_against_spec(spec_path, len(load(workload_path)["cases"]), runs)
    out.mkdir(parents=True, exist_ok=False)
    _write_status(out, "in_progress")
    shutil.copytree(root, out, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.pyc", "__pycache__", "decision-status.json"))
    parent_record = load(root / "decision.json")
    if not parent_record.get("decision_identity"):
        raise ValueError("Retained parent decision has no decision_identity")
    parent_ref = "parents/" + parent_record["decision_identity"] + ".json"
    parent_path = out / parent_ref
    parent_path.parent.mkdir(parents=True, exist_ok=True)
    write(parent_path, parent_record)
    # Canonical root manifest makes the child immediately exportable/importable.
    prefix = manifest.parent.relative_to(root).as_posix()
    if prefix == ".":
        prefix = ""
    def root_ref(value):
        return (prefix + "/" + value).lstrip("/") if prefix else value
    child_job = copy.deepcopy(job)
    child_job["parent_record"] = parent_ref
    child_job["comparison"]["spec"] = root_ref(child_job["comparison"]["spec"])
    for key in ("baseline_grades", "candidate_grades", "grading_contract"):
        if child_job["comparison"].get(key):
            child_job["comparison"][key] = root_ref(child_job["comparison"][key])
    for side in ("baseline", "candidate"):
        child_job["arms"][side]["operations"] = [root_ref(p) for p in child_job["arms"][side].get("operations", [])]
        if child_job["arms"][side].get("resources"):
            child_job["arms"][side]["resources"] = root_ref(child_job["arms"][side]["resources"])
        if child_job["arms"][side].get("resource_template"):
            child_job["arms"][side]["resource_template"] = root_ref(child_job["arms"][side]["resource_template"])
        if child_job["arms"][side].get("collection"):
            child_job["arms"][side]["collection"] = root_ref(child_job["arms"][side]["collection"])
    if child_job.get("external_grading"):
        for field in ("reference", "normalizer", "grading_contract"):
            if child_job["external_grading"].get(field):
                child_job["external_grading"][field] = root_ref(child_job["external_grading"][field])
    for side in ("baseline", "candidate"):
        retry_item = child_job["arms"][side].get("retry")
        if retry_item:
            for field, value in retry_item.items():
                retry_item[field] = root_ref(value)
    if child_job.get("execution_plan"):
        child_job["execution_plan"] = root_ref(child_job["execution_plan"])
    _replace_json(out / "job.json", child_job)
    _replace_json(out / "input-hashes.json", _input_hashes(out))
    run_copies = {side: out / "native" / "capture" / side / "run.json" for side in ("baseline", "candidate")}
    staged_policy = (out / policy_path.relative_to(root)) if policy_path is not None and policy_path.is_relative_to(root) else policy_path
    staged_grades = {side: out / p.relative_to(root) for side, p in grades.items()}
    staged_contract = out / grading_contract.relative_to(root) if grading_contract else None
    analysis_dir = out / "analyses" / uuid.uuid4().hex
    native = maintainer.analyze_receipts(run_copies["baseline"], run_copies["candidate"], staged_policy, analysis_dir,
                                         baseline_grades=staged_grades.get("baseline"), candidate_grades=staged_grades.get("candidate"),
                                         grading_contract=staged_contract)
    staged_collections = {side: out / p.relative_to(root) if p else None for side, p in collections.items()}
    staged_ops = {side: [out / p.relative_to(root) for p in paths] for side, paths in operations.items()}
    staged_resources = {side: out / p.relative_to(root) if p else None for side, p in resources.items()}
    ops, res, derived_ops, derived_resources = _bind_job_evidence(
        child_job, run_copies, staged_collections, staged_ops, staged_resources, out,
        evidence_root=out / "derived-evidence" / ("analysis-" + uuid.uuid4().hex))
    for side in ("baseline", "candidate"):
        child_job["arms"][side]["operations"] = [p.relative_to(out).as_posix() for p in staged_ops[side] + derived_ops[side]]
        template = staged_resources[side]
        if template and load(template).get("schema") == "cantos.resource-template/1":
            child_job["arms"][side]["resource_template"] = template.relative_to(out).as_posix()
        resource = derived_resources[side] or staged_resources[side]
        child_job["arms"][side]["resources"] = resource.relative_to(out).as_posix() if resource else None
    _replace_json(out / "job.json", child_job)
    _replace_json(out / "input-hashes.json", _input_hashes(out))
    decision = deployment.decide_deployment(child_job, native, run_copies, ops, res, parent=parent_record,
                                              retry_evidence=_retry_paths(child_job, out) or None)
    _replace_json(out / "native-verdict.json", _portable_native(native, out))
    _replace_json(out / "decision.json", decision)
    _replace_json(out / "job-result.json", {"schema": "cantos.deployment-job-result/1", "expected_observations": expected,
                                      "actual_observations": 2 * expected, "inference_requests": 0,
                                      "decision_identity": decision["decision_identity"]})
    _write_status(out, "complete", decision["decision_identity"])
    return decision


def export_job(root_dir, destination):
    root = Path(root_dir).resolve()
    _require_complete(root)
    return deployment_bundle.export_bundle(root, destination, record="decision.json")


def collect_local(manifest_path, arm, authorize_local_host, out_dir):
    """Run the pinned owned-loopback operational collector on the declared local host."""
    job, base, spec_path, spec, _, _, _, _, _, _, _, _ = _load_job(Path(manifest_path))
    if arm not in ("baseline", "candidate"):
        raise ValueError("arm must be baseline or candidate")
    hardware = spec[arm]["identity"]["hardware"]
    actual_host_hash = hashlib.sha256(socket.gethostname().encode("utf-8")).hexdigest()
    if not isinstance(authorize_local_host, str) or not authorize_local_host:
        raise ValueError("Explicit --authorize-local-host is required")
    if hardware.get("audit_host_label") != authorize_local_host:
        raise ValueError("Authorized local host label differs from the declared arm hardware")
    if hardware.get("audit_host_id_sha256") != actual_host_hash:
        raise ValueError("Declared local host identity hash differs from this host")
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    bundle = Path(__file__).resolve().parents[2] / "public" / "open-compute" / "open-compute-workbench.zip"
    owner = packets.unpack_owner(bundle, out / "pinned-workbench")
    collector = packets._module(owner / "instruments" / "collect.py", "cantos_pinned_local_operations")
    packet_dir = out / "packet"
    run_id = "job_" + uuid.uuid4().hex
    # No endpoint/model arguments: this executes only the pinned local inventory
    # and owned-loopback/storage probes; it cannot issue inference requests.
    status = collector.main(["collect", "--out", str(packet_dir), "--label", "cantos-local",
                             "--run-id", run_id, "--operations", "full"])
    packet = load(packet_dir / "packet.json")
    if status != 0 or packet.get("status") != "collected":
        raise ValueError("Pinned local operations collector did not complete successfully")
    raw_path = packet_dir / "recovery" / "raw.json"
    summary_path = packet_dir / "recovery" / "summary.json"
    raw_bytes, summary_bytes = raw_path.read_bytes(), summary_path.read_bytes()
    packet_bytes = (packet_dir / "packet.json").read_bytes()
    raw, summary = json.loads(raw_bytes), json.loads(summary_bytes)
    source_member = "cantos/open-compute-ledger/instruments/collect.py"
    with zipfile.ZipFile(bundle) as archive:
        trusted_collector_sha = hashlib.sha256(archive.read(source_member)).hexdigest()
    if packet.get("provenance", {}).get("source_sha256") != trusted_collector_sha:
        raise ValueError("Collector receipt source identity differs from the pinned public archive")
    file_records = {entry["path"]: entry for entry in packet.get("files", [])}
    sources = load(Path(__file__).resolve().parent / "SOURCES.json")
    pinned_source_sha = sources.get("operational_collector", {}).get("sha256")
    if trusted_collector_sha != pinned_source_sha:
        raise ValueError("Pinned collector archive source differs from the trusted SOURCES.json entry")
    for relative, content in (("recovery/raw.json", raw_bytes), ("recovery/summary.json", summary_bytes)):
        entry = file_records.get(relative)
        if not entry or entry.get("sha256") != hashlib.sha256(content).hexdigest() or entry.get("bytes") != len(content):
            raise ValueError("Pinned packet file manifest does not bind recovery evidence")
    if packet.get("operations", {}).get("service_recovery") != summary:
        raise ValueError("Pinned packet summary differs from exact recovery summary bytes")
    _verify_recovery_collection(raw_bytes, summary_bytes, packet_bytes)
    if raw.get("host_unverified_label") != "cantos-local":
        raise ValueError("Pinned local recovery raw evidence label mismatch")
    acquisition = {"schema": "cantos.local-operation-acquisition/1", "arm": arm,
                   "host_label": authorize_local_host, "host_id_sha256": actual_host_hash,
                   "hardware_identity_sha256": deployment.sha(hardware),
                   "observed_window": {"start": packet["provenance"]["captured_at"],
                                       "end": packet["provenance"]["completed_at"]},
                   "check_id": "owned_loopback.recovery", "run_id": raw["run_id"],
                   "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                   "summary_sha256": hashlib.sha256(summary_bytes).hexdigest(),
                   "raw_base64": base64.b64encode(raw_bytes).decode("ascii"),
                   "summary_base64": base64.b64encode(summary_bytes).decode("ascii"),
                   "packet_base64": base64.b64encode(packet_bytes).decode("ascii"),
                   "collector_source_sha256": trusted_collector_sha,
                   "pinned_workbench_sha256": sha256_file(bundle),
                   "scope": "Pinned owned-loopback child-process recovery audit on the explicitly declared local host; no remote attestation.",
                   "collector_packet": "packet/packet.json"}
    write(out / "acquisition.json", acquisition)
    return acquisition


def collect_network(manifest_path, arm, requirement_id, authorize_target, out_dir):
    """Explicit health-only probe through the pinned collector; never runs on import."""
    job, _, _, spec, *_ = _load_job(Path(manifest_path))
    if arm not in ("baseline", "candidate"):
        raise ValueError("Expected baseline or candidate arm")
    selected = [req for req in job["decision"]["operational_requirements"] if req["id"] == requirement_id]
    if len(selected) != 1 or selected[0]["check_id"] not in deployment.network_health.CHECKS:
        raise ValueError("Select one declared owned network requirement")
    req = selected[0]
    expected, settings = req["network_target"], req["network_protocol"]
    hardware = spec[arm]["identity"]["hardware"]
    if (expected["resource_identity_sha256"] != deployment.sha(hardware)
            or hardware.get("audit_host_id_sha256") != expected["responder_host_id_sha256"]):
        raise ValueError("Network target differs from the declared arm hardware/audit host")
    if authorize_target != deployment.network_health.sha(canonical(expected)):
        raise ValueError("Explicit authorization must match declared exact network target hash")
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    bundle = Path(__file__).resolve().parents[2] / "public/open-compute/open-compute-workbench.zip"
    owner = packets.unpack_owner(bundle, out / "pinned-workbench")
    sources = load(Path(__file__).resolve().parent / "SOURCES.json")
    collector_pin = sources["operational_collector"]["sha256"]
    network_pin = next(row["sha256"] for row in sources["files"] if row["path"] == "owner_ocl/network_health.py")
    # Check both source pins BEFORE the collector can contact the target.
    if (sha256_file(owner / "instruments/collect.py") != collector_pin
            or sha256_file(owner / "instruments/controller/ocl/network_health.py") != network_pin):
        raise ValueError("Network acquisition requires a reviewed workbench archive with the exact pinned collector/source")
    config = out / "network-config.json"
    write(config, {"network_target": expected, "network_protocol": settings})
    collector = packets._module(owner / "instruments/collect.py", "cantos_pinned_network_operations")
    packet_dir = out / "packet"
    collector.main(["network-health", "--config", str(config), "--authorize-target", authorize_target, "--out", str(packet_dir)])
    contents = {key: (packet_dir / path).read_bytes() for key, path in
                (("raw", "network/raw.json"), ("summary", "network/summary.json"),
                 ("events", "network/attempt-events.jsonl"), ("packet", "packet.json"))}
    checked = deployment.network_health.verify_packet(contents["raw"], contents["summary"], contents["events"],
        contents["packet"], expected, settings, collector_sha256=collector_pin, producer_sha256=network_pin)
    templates = [{"schema": "cantos.operation-template/1", "check_id": item["check_id"], "basis": "observed",
                  **{key + "_base64": base64.b64encode(value).decode("ascii") for key, value in contents.items()}}
                 for item in job["decision"]["operational_requirements"] if item["check_id"] in deployment.network_health.CHECKS
                 and item["network_target"] == expected and item["network_protocol"] == settings]
    write(out / "operation-template.json", templates)
    return {"schema": "cantos.network-operation-acquisition/1", "arm": arm, "summary": checked,
            "operation_template": str(out / "operation-template.json"), "pinned_workbench_sha256": sha256_file(bundle),
            "scope": "Named owned health route only. Attach operation-template.json to this arm's operations; normal run binds exact run/time/hardware. No inference or server launch occurred."}


def _verify_recovery_collection(raw_bytes, summary_bytes, packet_bytes):
    """Preflight the exact raw, summary and original packet before retaining them."""
    return deployment._operation_value({"check_id": "owned_loopback.recovery_verified",
                                        "raw_base64": base64.b64encode(raw_bytes).decode("ascii"),
                                        "summary_base64": base64.b64encode(summary_bytes).decode("ascii"),
                                        "packet_base64": base64.b64encode(packet_bytes).decode("ascii")})


def validate_job(manifest_path):
    """Validate shape/closures and print required-unknown blockers before capture."""
    job, base, spec_path, spec, workload_path, policy_path, grades, grading_contract, operations, resources, collections, expected = _load_job(Path(manifest_path))
    blockers = []
    requirements = job["decision"]["operational_requirements"]
    supported_checks = {"owned_loopback.recovery_verified", "owned_loopback.recovery_max_s", *deployment.network_health.CHECKS}
    for side in ("baseline", "candidate"):
        if not resources.get(side):
            if job["decision"]["economics_required"]:
                blockers.append({"layer": "economics", "arm": side, "status": "required_unknown",
                                 "reason": "No source-bound resource template or accounting record is attached."})
        else:
            resource = load(resources[side])
            if resource.get("schema") not in ("cantos.resource-binding/1", "cantos.resource-template/1"):
                blockers.append({"layer": "economics", "arm": side, "status": "invalid",
                                 "reason": "Resource input must be a resource binding or template."})
            elif resource.get("schema") == "cantos.resource-template/1":
                if resource.get("resource_identity_sha256") != deployment.sha(spec[side]["identity"]["hardware"]):
                    blockers.append({"layer": "economics", "arm": side, "status": "invalid",
                                     "reason": "Resource template identity does not match the declared arm hardware."})
                scenario = resource.get("scenario", {})
                missing_fields = sorted(deployment.COST_FIELDS - set(scenario)) if isinstance(scenario, dict) else sorted(deployment.COST_FIELDS)
                unknown_fields = sorted(key for key, value in scenario.items() if isinstance(value, dict) and value.get("basis") == "unknown") if isinstance(scenario, dict) else []
                extra_categories = {item.get("category") for item in resource.get("additional_costs", []) if isinstance(item, dict)}
                missing_extras = sorted({"verification", "retry", "operator", "idle"} - extra_categories)
                if missing_fields or unknown_fields or missing_extras:
                    blockers.append({"layer": "economics", "arm": side, "status": "required_unknown",
                                     "reason": "Preflight economics gaps (hypothetical only; not a result): missing scenario fields=" + repr(missing_fields) +
                                     "; explicitly unknown fields=" + repr(unknown_fields) + "; missing additional-cost categories=" + repr(missing_extras) +
                                     ". Empty values are not zero."})
        checks = set()
        for path in operations.get(side, []):
            value = load(path)
            checks.update(item.get("check_id") for item in (value if isinstance(value, list) else [value]) if isinstance(item, dict))
        for req in requirements:
            acquired_check = None
            if collections.get(side):
                acquired_check = load(collections[side]).get("check_id")
            if req["required"] and req["check_id"] not in supported_checks:
                blockers.append({"layer": "operations", "arm": side, "id": req["id"], "status": "unsupported",
                                 "reason": "This job driver cannot acquire this check from its pinned local collector."})
            elif req["required"] and req["check_id"] not in checks and acquired_check != req["check_id"]:
                blockers.append({"layer": "operations", "arm": side, "id": req["id"], "status": "required_unknown",
                                 "reason": "No matching bound receipt or local acquisition is attached."})
    workload = load(workload_path)
    external_tasks = sum(1 for case in workload.get("cases", []) for step in maintainer.steps(case)
                         if step["expect"].get("kind") == "external")
    external = job.get("external_grading")
    if external_tasks and (not external or external.get("execute") is not True) and not all(side in grades for side in ("baseline", "candidate")):
        blockers.append({"layer": "useful_work", "status": "required_unknown",
                         "reason": "Workload contains external-grader tasks; attach both native grade receipts or configure an explicit external_grading execution."})
    if external is not None and external.get("execute") is True and not external_tasks:
        blockers.append({"layer": "useful_work", "status": "invalid", "reason": "external_grading execution is configured but the workload has no external-grader tasks."})
    retry_controls = deployment_retry.controls(job.get("retry"))
    for side in ("baseline", "candidate"):
        selected = job.get("arms", {}).get(side, {}).get("retry")
        if retry_controls["required"] or retry_controls["economics"]:
            if not selected:
                blockers.append({"layer": "retry", "arm": side, "status": "required_unknown",
                                 "reason": "No retry campaign is attached; validation does not run or replay campaigns."})
            else:
                _retry_closure(_inside(base, selected["campaign"], side + ".retry.campaign"))
    invalid = any(item["status"] == "invalid" for item in blockers)
    return {"schema": "cantos.deployment-job-validation/1", "status": "valid_manifest", "ready_for_capture": not invalid,
            "decision_blockers": blockers, "no_known_preflight_blockers": not blockers,
            "arms": {side: {"endpoint": spec[side]["base_url"], "model": spec[side]["model"],
                            "declared_identity": spec[side]["identity"], "expected_observations": expected}
                     for side in ("baseline", "candidate")},
            "external_grade_tasks": external_tasks, "inference_requests": 0,
            "limitations": ["Validation reads manifest and declared files only. It does not probe endpoints, collect host evidence or run a grader."]}


def import_job(source, out_dir):
    """Import data only and recompute the decision using installed trusted code."""
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    _write_status(out, "in_progress")
    unpacked = deployment_bundle.import_bundle(source, out / "bundle")
    root = Path(unpacked["root"]).resolve()
    record = Path(unpacked["record"]).resolve()
    if record.name != "decision.json" or record.parent != root:
        raise ValueError("Bundle record must be its root decision.json")
    claimed = load(record)
    original_job = load(_inside(root, "job.json", "job.json"))
    # Check every manifest-declared data input is contained and unchanged before use.
    _load_job(root / "job.json")
    hash_manifest = load(_inside(root, "input-hashes.json", "input-hashes.json"))
    if not isinstance(hash_manifest, dict) or len(hash_manifest) > 10000:
        raise ValueError("Invalid retained input hash manifest")
    for name, digest in hash_manifest.items():
        path = _inside(root, name, "input hash path")
        if not isinstance(digest, str) or sha256_file(path) != digest:
            raise ValueError("Retained input hash mismatch: " + name)
    run_paths = {side: _inside(root, "native/capture/" + side + "/run.json", side + " run") for side in ("baseline", "candidate")}
    _, _, spec_path, spec, workload_path, policy_path, grades, grading_contract, operations, resources, collections, expected = _load_job(root / "job.json")
    _validate_runs_against_spec(spec_path, len(load(workload_path)["cases"]), run_paths)
    native = maintainer.analyze_receipts(run_paths["baseline"], run_paths["candidate"], policy_path, out / "reanalysis",
                                         baseline_grades=grades.get("baseline"), candidate_grades=grades.get("candidate"),
                                         grading_contract=grading_contract)
    ops, res = _read_evidence(operations, resources)
    parent = None
    if claimed.get("post_hoc"):
        parent_ref = original_job.get("parent_record", "parent-decision.json")
        parent_record = load(_inside(root, parent_ref, "parent decision"))
        if parent_record.get("decision_identity") != claimed.get("parent_id"):
            raise ValueError("Imported post-hoc parent record differs from claimed lineage")
        parent = parent_record
    decision = deployment.decide_deployment(original_job, native, run_paths, ops, res, parent=parent,
                                              retry_evidence=_retry_paths(original_job, root) or None)
    if decision.get("decision_identity") != claimed.get("decision_identity"):
        raise ValueError("Imported decision differs from trusted recomputation")
    write(out / "native-verdict.json", _portable_native(native, out))
    write(out / "decision.json", decision)
    result_path = out / "job-result.json"
    write(result_path, {"schema": "cantos.deployment-job-result/1", "decision_identity": decision["decision_identity"],
                        "inference_requests": 0, "grader_executions": 0})
    _write_status(out, "complete", decision["decision_identity"])
    return decision


def decision_exit_code(decision):
    state = decision.get("state") if isinstance(decision, dict) else None
    return {"SELECT-CANDIDATE": 0, "KEEP-BASELINE": 1,
            "NO-ELIGIBLE": 2, "INCOMPARABLE": 2, "UNDETERMINED": 2,
            "INCOMPLETE": 3}.get(state, 3)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="perform one paired recipient-owned endpoint run and retain decision")
    run.add_argument("--manifest", required=True)
    run.add_argument("--out", required=True)
    decide = sub.add_parser("decide", help="reanalyze retained runs with changed prices or requirements; no inference")
    decide.add_argument("--job", required=True)
    decide.add_argument("--manifest", help="optional changed data-only manifest already staged inside --job")
    decide.add_argument("--out", required=True)
    export = sub.add_parser("export", help="stream a retained data-only deployment bundle")
    export.add_argument("--job", required=True)
    export.add_argument("--out", required=True)
    imp = sub.add_parser("import", help="verify and recompute a data-only deployment bundle")
    imp.add_argument("--bundle", required=True)
    imp.add_argument("--out", required=True)
    collect = sub.add_parser("collect", help="run the pinned operational audit on an explicitly declared local host")
    collect.add_argument("--manifest", required=True)
    collect.add_argument("--arm", choices=("baseline", "candidate"), required=True)
    collect.add_argument("--authorize-local-host", required=True)
    collect.add_argument("--out", required=True)
    network = sub.add_parser("collect-network", help="explicit authorized TLS health-only acquisition through pinned collector")
    network.add_argument("--manifest", required=True)
    network.add_argument("--arm", choices=("baseline", "candidate"), required=True)
    network.add_argument("--requirement", required=True)
    network.add_argument("--authorize-target", required=True)
    network.add_argument("--out", required=True)
    validate = sub.add_parser("validate", help="validate a manifest and display required-unknown blockers without inference")
    validate.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            result = run_job(args.manifest, args.out)
        elif args.command == "decide":
            result = decide_job(args.job, args.out, manifest_path=args.manifest)
        elif args.command == "export":
            result = export_job(args.job, args.out)
        elif args.command == "collect":
            result = collect_local(args.manifest, args.arm, args.authorize_local_host, args.out)
        elif args.command == "collect-network":
            result = collect_network(args.manifest, args.arm, args.requirement, args.authorize_target, args.out)
        elif args.command == "validate":
            result = validate_job(args.manifest)
        else:
            result = import_job(args.bundle, args.out)
        if args.command == "collect":
            result = {key: result[key] for key in ("schema", "arm", "host_label", "host_id_sha256",
                                                   "hardware_identity_sha256", "observed_window", "raw_sha256",
                                                   "summary_sha256", "pinned_workbench_sha256", "scope")}
            result["acquisition_file"] = str(Path(args.out).resolve() / "acquisition.json")
            result["acquisition_file_sha256"] = sha256_file(Path(args.out).resolve() / "acquisition.json")
        print(json.dumps(result, sort_keys=True, default=str))
        return decision_exit_code(result) if args.command in ("run", "decide", "import") else 0
    except Exception as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
