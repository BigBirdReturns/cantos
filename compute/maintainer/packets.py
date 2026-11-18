"""Bridge validated maintainer evidence through the pinned existing packet owner.

Collection, finance normalization, packet accounting, import and decision retention
remain in the published Open Compute Workbench. This adapter maps workload and
timing metadata whose old collector defaults describe only its synthetic suite.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile

try:
    from .common import ROOT, _safe, canonical, closure, digest, load, policy, producer_records, read_grading_contract, sha256_file, steps, write
    from .maintainer import _compare_runs, export_ocl_receipt, validate_grades, validate_receipt
except ImportError:
    from common import ROOT, _safe, canonical, closure, digest, load, policy, producer_records, read_grading_contract, sha256_file, steps, write
    from maintainer import _compare_runs, export_ocl_receipt, validate_grades, validate_receipt

BUNDLE_SHA256 = "16ea5f01a458971d07f87a12bf61b95e9643379c9a6a44655c3c387be8e3ab82"
BUNDLE_SOURCE = "Cantos public workbench 2026-11-18; public/open-compute/WORKBENCH-RELEASE.json and exact archive MANIFEST.json"


def unpack_owner(bundle, out):
    bundle, out = Path(bundle).resolve(), Path(out).resolve()
    if sha256_file(bundle) != BUNDLE_SHA256:
        raise ValueError("workbench bundle SHA256 differs from the pinned public collector/engine source")
    out.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(bundle) as archive:
        infos = archive.infolist()
        if len(infos) > 10000 or sum(i.file_size for i in infos) > 64 * 1024 * 1024:
            raise ValueError("workbench archive exceeds extraction bounds")
        seen = set()
        for info in infos:
            name = info.filename.rstrip("/")
            path = _safe(out, name)
            if name in seen or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("duplicate or symlink archive member")
            seen.add(name)
            if info.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as target:
                    target.write(archive.read(info))
    package = out / "cantos/open-compute-ledger"
    for relative in ("instruments/collect.py", "engine/engine.py", "instruments/controller/SNAPSHOT.json"):
        if not (package / relative).is_file():
            raise ValueError("pinned workbench is missing its existing owner: " + relative)
    return package


def _module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy_closure(receipt_path, value, destination):
    receipt_path, destination = Path(receipt_path).resolve(), Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(receipt_path, destination / receipt_path.name)
    for entry in value["artifacts"]:
        source = _safe(receipt_path.parent, entry["path"])
        target = _safe(destination, entry["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _checked_analysis(path):
    path = Path(path).resolve()
    if path.is_dir():
        path = path / "verdict.json"
    result = load(path)
    exports = result.get("ocl_exports", {})
    if exports.get("status") != "exported":
        raise ValueError("analyze complete graded evidence first; this verdict has no native OCL exports")
    for key in ("policy", "baseline", "candidate"):
        entry = exports[key]
        source = _safe(path.parent, entry["path"])
        if source.stat().st_size != entry["bytes"] or sha256_file(source) != entry["sha256"]:
            raise ValueError("analysis export changed: " + key)
    for name, entry in result["inputs"].items():
        if sha256_file(entry["path"]) != entry["sha256"]:
            raise ValueError("retained analysis input changed: " + name)
    pol = policy(load(_safe(path.parent, exports["policy"]["path"])))
    grading = result["inputs"].get("grading_contract")
    basis = read_grading_contract(grading["path"]) if grading else None
    if basis is not None:
        if grading["sha256"] != basis[1] or result.get("grading_contract") != {"sha256": basis[1], **basis[0]}:
            raise ValueError("analysis grading contract differs from its exact input")
        if not all(arm + "_grades" in result["inputs"] for arm in ("baseline", "candidate")):
            raise ValueError("analysis grading contract requires grade receipts for both arms")
    elif "grading_contract" in result:
        raise ValueError("analysis grading contract input is missing")
    runs, workloads, grades = {}, {}, {}
    for arm in ("baseline", "candidate"):
        run_path = result["inputs"][arm]["path"]
        runs[arm] = validate_receipt(run_path)
        workloads[arm] = load(Path(run_path).parent / "workload.json")
        grade_path = result["inputs"].get(arm + "_grades", {}).get("path")
        grades[arm] = validate_grades(grade_path, run_path, basis) if grade_path else None
        projection = export_ocl_receipt(run_path, runs[arm], workloads[arm], pol, grades[arm], grade_path)
        exported = load(_safe(path.parent, exports[arm]["path"]))
        if canonical(projection) != canonical(exported):
            raise ValueError("OCL export differs from the validated raw/grade/policy projection")
    checked = _compare_runs(runs["baseline"], runs["candidate"], workloads["baseline"], workloads["candidate"],
                            pol, grades["baseline"], grades["candidate"])
    for field in ("verdict", "baseline", "candidate", "changed_factors", "regressions", "comparability_failures"):
        if canonical(result[field]) != canonical(checked[field]):
            raise ValueError("analysis changed or requires recomputation under this producer: " + field)
    return path, result, pol, runs, workloads, grades


def _acceptance_definition(workload, pol, grading_contract=None):
    expected = [{"id": c["id"], "expectations": [s["expect"] for s in steps(c)]} for c in workload["cases"]]
    contract_identity = ""
    if grading_contract is not None:
        expected = copy.deepcopy(expected)
        for case in expected:
            for expectation in case["expectations"]:
                if expectation["kind"] == "external":
                    expectation["grader"] = grading_contract["grader"]
        contract_identity = "; external grading contract SHA256 " + grading_contract["sha256"]
    return ("All declared task stages must pass their exact text/JSON oracle or pinned independent application grader, "
            "with complete streamed final output and this acceptance policy: " +
            json.dumps(pol["acceptance"], sort_keys=True) +
            "; expectation identity SHA256 " + digest(expected) + contract_identity +
            ". The acceptance threshold for choosing a configuration is separate from task acceptance.")


def export_packets(analysis, bundle, out_dir, baseline_financials=None, candidate_financials=None, policy_prices_usd=False):
    analysis_path, result, pol, runs, workloads, grades = _checked_analysis(analysis)
    grading_contract = result.get("grading_contract")
    bundle = Path(bundle).resolve()
    if sha256_file(bundle) != BUNDLE_SHA256:
        raise ValueError("expected the pinned public workbench ZIP SHA256 " + BUNDLE_SHA256)
    root = Path(out_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    package = unpack_owner(bundle, root / "workbench-owner")
    collector_path = package / "instruments/collect.py"
    collector = _module(collector_path, "cantos_existing_packet_owner")
    engine_path = package / "engine/engine.py"
    engine = _module(engine_path, "cantos_existing_decision_owner")
    finances = {"baseline": baseline_financials, "candidate": candidate_financials}
    pricing_mode = {arm: "independent_financial_inputs" if value else "unknown" for arm, value in finances.items()}
    if policy_prices_usd:
        for arm in ("baseline", "candidate"):
            if pol["prices"][arm + "_per_hour"] is not None:
                if finances[arm]:
                    raise ValueError("choose explicit financials or --policy-prices-usd for " + arm)
                target = root / (arm + "-policy-financials.json")
                write(target, {"schema": "ocl.financial-inputs/1", "costs": [{
                    "value": result[arm]["estimated_cost"], "unit": "USD", "scope": "complete_run", "basis": "modeled",
                    "source": "Explicit --policy-prices-usd declaration; maintainer analysis SHA256 " + sha256_file(analysis_path) +
                              "; rate " + str(pol["prices"][arm + "_per_hour"]) + " USD/hour; " + result[arm]["cost_duration_scope"]}],
                    "energy": [], "notes": "No invoice or energy measurement inferred. The named run covers its summed measured trial windows."})
                finances[arm] = target
                pricing_mode[arm] = "explicit_policy_hourly_usd_measured_windows"
    for value in finances.values():
        collector.finances(value)  # The existing owner validates units, scope and basis.
    packet_paths = {}
    for arm in ("baseline", "candidate"):
        run, workload = runs[arm], workloads[arm]
        identity = run["declared_identity"]
        runtime = identity.get("implementation", {})
        config = {"id": "maintainer-" + arm + "-" + result["ocl_exports"][arm]["sha256"][:20],
                  "label": workload["name"][:150] + " / " + arm,
                  "provider": "operator-owned-endpoint", "model": run["configuration"]["model"],
                  "runtime": str(runtime.get("name")) + " " + str(runtime.get("revision")),
                  "precision": identity.get("precision"),
                  "accelerator": identity.get("hardware", {}).get("description"),
                  "declared_identity": identity}
        config_path = root / (arm + "-configuration.json")
        write(config_path, config)
        destination = root / arm
        projected_path = _safe(analysis_path.parent, result["ocl_exports"][arm]["path"])
        argv = [sys.executable, "-B", str(collector_path), "ingest", "--out", str(destination),
                "--label", "maintainer-" + arm, "--run-id", "maintainer_" + arm + "_" + sha256_file(projected_path)[:32],
                "--configuration", str(config_path), "--receipt", str(projected_path), "--useful-work-basis", "observed"]
        if finances[arm]:
            argv.extend(["--financials", str(Path(finances[arm]).resolve())])
        completed = subprocess.run(argv, capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
        (root / (arm + "-collector.stdout")).write_bytes(completed.stdout)
        (root / (arm + "-collector.stderr")).write_bytes(completed.stderr)
        if completed.returncode != 0:
            raise ValueError("existing collector ingest failed for " + arm + "; retained logs identify the failure")
        packet_path = destination / "packet.json"
        packet = load(packet_path)
        # Retain the owner's original output before adapting its old synthetic-only
        # metadata. Acceptance and financial arithmetic stay with that owner.
        shutil.copyfile(packet_path, destination / "collector-original.json")
        _copy_closure(result["inputs"][arm]["path"], run, destination / "evidence/source-run")
        if grades[arm]:
            _copy_closure(result["inputs"][arm + "_grades"]["path"], grades[arm], destination / "evidence/application-grades")
        shutil.copyfile(analysis_path, destination / "evidence/maintainer-verdict.json")
        shutil.copyfile(_safe(analysis_path.parent, result["ocl_exports"]["policy"]["path"]), destination / "evidence/resolved-policy.json")
        if "policy" in result["inputs"]:
            shutil.copyfile(result["inputs"]["policy"]["path"], destination / "evidence/original-policy.json")
        if grading_contract is not None:
            target = destination / "evidence/grading-contract.json"
            shutil.copyfile(result["inputs"]["grading_contract"]["path"], target)
            if sha256_file(target) != grading_contract["sha256"]:
                raise ValueError("grading contract changed while exporting packet")
        shutil.copyfile(bundle, destination / "evidence/workbench-source.zip")
        producer = destination / "evidence/packet-adapter-source"
        producer.mkdir()
        for entry in producer_records():
            target = _safe(producer, entry["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / entry["path"], target)
        workload_identity = run["workload_sha256"]
        if grading_contract is not None:
            workload_identity = digest({"captured_workload_sha256": workload_identity,
                                        "grading_contract_sha256": grading_contract["sha256"]})
        packet["workload"] = {
            "id": "maintainer/" + workload_identity, "label": workload["name"],
            "kind": "application" if grades[arm] else "declared_exact_workload",
            "identity": workload_identity, "seed": run["protocol"]["seed"],
            "acceptance_definition": _acceptance_definition(workload, pol, grading_contract),
            "source": workload.get("source"), "limits": result["limitations"] + [
                "Imported latency and TTFT use matched both-accepted task/trial/repetition pairs from the paired maintainer comparison.",
                result[arm]["cost_duration_scope"],
                "This import carries its maintainer verdict; importing evidence does not qualify a failed acceptance requirement."]}
        packet["metrics"]["ttft_p95_s"] = result[arm]["p95_ttft_s"]
        packet["metrics"]["e2e_p95_s"] = result[arm]["p95_latency_s"]
        packet["metrics"]["scope"] = result[arm]["performance_population"]
        packet["metrics"]["matched_accepted_tasks"] = result[arm]["matched_accepted_tasks"]
        packet["provenance"]["imported_at"] = packet["provenance"]["captured_at"]
        packet["provenance"]["captured_at"] = run["started_at"]
        packet["provenance"]["observation_ended_at"] = run["ended_at"]
        packet["provenance"]["maintainer"] = {
            "verdict": result["verdict"], "verdict_sha256": sha256_file(analysis_path),
            "source_run_sha256": result["inputs"][arm]["sha256"],
            "grade_sha256": result["inputs"].get(arm + "_grades", {}).get("sha256"),
            "normalized_policy_sha256": result["ocl_exports"]["policy"]["sha256"],
            "observation_key": run["observation_key"], "capture_producer_files": run["producer_files"],
            "adapter_sha256": sha256_file(__file__), "collector_sha256": sha256_file(collector_path),
            "bundle_sha256": BUNDLE_SHA256, "bundle_source": BUNDLE_SOURCE,
            "pricing_mode": pricing_mode[arm],
            "projection": "Existing collector ingest accounting; explicit workload, timing, original date and evidence-closure mapping",
            "new_inference_requests": 0}
        if grading_contract is not None:
            packet["provenance"]["maintainer"].update(
                captured_workload_sha256=run["workload_sha256"],
                grading_contract_sha256=grading_contract["sha256"])
        packet["coverage"]["useful_work"] = "independent_application_grading" if grades[arm] else "declared_exact_output_grading"
        if run["status"] == "error":
            packet["status"] = "partial_failure"
            packet["failures"].append({"stage": "retained_stream_capture", "error": "Original capture contains transport or stream failures"})
        if packet["acceptance"]["accepted"] != result[arm]["accepted_tasks"]:
            raise ValueError("existing collector changed accepted-work accounting")
        packet["files"] = collector.file_manifest(destination)
        # This file is an explicitly derived packet; the original collector output
        # and all input receipts remain byte-exact artifacts beside it.
        packet_path.write_text(json.dumps(packet, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        if len(engine.encoded(packet)) > engine.MAX_BODY:
            raise ValueError("packet exceeds the existing workbench HTTP import size limit")
        packet_paths[arm] = packet_path
    ledger = engine.Ledger(package, root / "workbench-verification-store")
    imported = {}
    for arm, path in packet_paths.items():
        packet = load(path)
        first = ledger.import_packet(packet)
        second = ledger.import_packet(packet)
        if first["id"] != second["id"] or second["status"] != "already_imported":
            raise ValueError("existing workbench did not preserve idempotent import")
        imported[arm] = first
    rows = [r for r in ledger.serving_rows() if any(r["id"] == "import-" + item["id"][:24] for item in imported.values())]
    if len(rows) != 2 or len({r["workload_id"] for r in rows}) != 1:
        raise ValueError("workbench did not join both configurations under the same workload")
    for arm, receipt in imported.items():
        row = next(r for r in rows if r["id"] == "import-" + receipt["id"][:24])
        if row["accepted"] != result[arm]["accepted_tasks"] or row["offered"] != result[arm]["total_tasks"]:
            raise ValueError("workbench import changed task accounting")
        if row["observed_at"] != runs[arm]["started_at"]:
            raise ValueError("workbench import renewed the original observation time")
        if not finances[arm] and row["cost_usd"] is not None:
            raise ValueError("unpriced work acquired a fabricated cost")
    constraints = {"min_accepted_fraction": max(pol["min_baseline_acceptance"], pol["min_candidate_acceptance"])}
    for source, target in (("max_latency_s", "max_latency_p95_s"), ("max_ttft_s", "max_ttft_p95_s")):
        if pol["acceptance"][source] is not None:
            constraints[target] = pol["acceptance"][source]
    decision = ledger.decide({"kind": "serving", "objective": "max_acceptance", "workload_id": rows[0]["workload_id"],
                              "title": "Retained maintainer application evidence", "constraints": constraints})
    verification = {"schema": "cantos.maintainer.workbench-import/1", "engine_sha256": sha256_file(engine_path),
                    "imports": imported, "rows": rows, "decision": {"id": decision["id"], "status": decision["status"],
                    "workload_id": decision["workload_id"]}, "history": ledger.history(), "inference_requests": 0}
    write(root / "workbench-import.json", verification)
    output = {"schema": "cantos.maintainer.packet-export/1", "status": "exported-and-import-verified",
              "analysis_sha256": sha256_file(analysis_path), "bundle_sha256": BUNDLE_SHA256,
              "packets": {arm: str(path.relative_to(root)) for arm, path in packet_paths.items()},
              "workbench_import": verification, "new_inference_requests": 0, "artifacts": closure(root, exclude=("export.json",))}
    write(root / "export.json", output)
    return output
