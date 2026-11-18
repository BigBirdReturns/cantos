"""Second Run adapters for explicit maintainer observations and retained analysis.

The native maintainer instrument owns streaming, grading, comparability and
verdicts. This adapter owns dependency declarations and retained artifact custody.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
OWNER = ROOT / "compute/maintainer/maintainer.py"


def _encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _owner():
    if not OWNER.is_file():
        raise ValueError("Maintainer instrument is missing: " + str(OWNER))
    name = "_cantos_maintainer_owner"
    spec = importlib.util.spec_from_file_location(name, OWNER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(OWNER.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def _path(value, base, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be a nonempty local file path")
    path = (Path(base) / value).resolve()
    if not path.is_file():
        raise ValueError(label + " is missing: " + str(path))
    return path


def _procedures():
    return sorted(p.resolve() for p in OWNER.parent.rglob("*.py")
                  if "tests" not in p.relative_to(OWNER.parent).parts
                  and "__pycache__" not in p.parts)


def _inputs(paths, prefix):
    # The role follows a stable native order, while file bytes enter the key.
    return {prefix + ":" + str(i): Path(path).resolve() for i, path in enumerate(paths)}


def _manifest(directory):
    files = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("An observation artifact must be a regular retained file: " + str(path))
        if path.is_file():
            files.append({"path": path.relative_to(directory).as_posix(),
                          "sha256": _sha(path), "bytes": path.stat().st_size})
    if not files:
        raise ValueError("Maintainer owner produced no retained artifacts")
    return files


def verify_artifacts(value):
    if not isinstance(value, dict) or value.get("schema") not in (
            "second-run/maintainer-observation@1", "second-run/maintainer-comparison@1"):
        raise ValueError("Unsupported retained maintainer result")
    root = Path(value["artifact_root"]).resolve()
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("Maintainer result needs its retained artifact closure")
    paths = []
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "bytes"}:
            raise ValueError("Invalid maintainer artifact declaration")
        relative = Path(item["path"])
        path = (root / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(root) or path in paths:
            raise ValueError("Maintainer artifact path is outside its retained result or duplicated")
        if not path.is_file() or path.stat().st_size != item["bytes"] or _sha(path) != item["sha256"]:
            raise ValueError("Maintainer artifact checksum failed; preserve the original before recovery: " + str(path))
        paths.append(path)
    receipt = Path(value["receipt"]).resolve()
    if receipt not in paths:
        raise ValueError("Maintainer terminal receipt is absent from its artifact closure")
    return paths


def _receipt_input(value, base, label, owner):
    source = _path(value, base, label)
    contents = json.loads(source.read_bytes())
    dependencies = [source]
    if isinstance(contents, dict) and contents.get("schema") == "second-run/computation@1":
        native = contents.get("value")
        if hashlib.sha256(_encoded(native)).hexdigest() != contents.get("value_sha256"):
            raise ValueError(label + " retained computation checksum failed")
        if not isinstance(native, dict) or native.get("schema") != "second-run/maintainer-observation@1":
            raise ValueError(label + " must reference a retained maintainer observation")
        dependencies.extend(verify_artifacts(native))
        source = Path(native["receipt"]).resolve()
    receipt = owner.validate_receipt(source)
    if receipt.get("schema") != "cantos.maintainer.run/1":
        raise ValueError(label + " must use cantos.maintainer.run/1")
    dependencies.append(source)
    for artifact in receipt.get("artifacts", []):
        path = (source.parent / artifact["path"]).resolve()
        if not path.is_relative_to(source.parent):
            raise ValueError(label + " artifact escapes its observation directory")
        dependencies.append(path)
    return source, list(dict.fromkeys(dependencies)), receipt


def _output(execution_context):
    if not isinstance(execution_context, dict) or set(execution_context) != {"artifact_dir"}:
        raise ValueError("Maintainer execution requires the result store artifact context")
    path = Path(execution_context["artifact_dir"]).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError("Retained maintainer output already exists; inspect it before an explicit new observation: " + str(path))
    return path


def prepare(task, base, execution_context=None):
    task_class = task.get("task_class")
    common = {"id", "actor", "task_class"}
    owner = _owner()
    if task_class == "maintainer-observe":
        if set(task) - common - {"source", "arm", "observation_id"}:
            raise ValueError("Unsupported maintainer-observe task fields")
        source = _path(task.get("source"), base, "source")
        arm = task.get("arm")
        if arm not in ("baseline", "candidate"):
            raise ValueError("Observation arm must be baseline or candidate")
        epoch = task.get("observation_id")
        if not isinstance(epoch, str) or not epoch.strip() or len(epoch) > 160:
            raise ValueError("A durable nonempty observation_id of at most 160 characters is required; --fresh records a new epoch")
        prepared = owner.prepare(source, arm)
        parameters = {"arm": arm, "observation_id": epoch,
                      "declared_observation": prepared["identity"]}
        dependencies = list(dict.fromkeys([*_procedures(), *prepared["dependencies"]]))
        inputs = {"adapter_code": HERE, **_inputs(dependencies, "observation")}

        def execute():
            directory = _output(execution_context)
            owner.observe(source, arm, directory, epoch)
            receipt_path = directory / "run.json"
            receipt = owner.validate_receipt(receipt_path)
            if receipt.get("observation_id") != epoch:
                raise ValueError("Observed receipt does not match the requested observation epoch")
            calls = receipt.get("inference_requests")
            if type(calls) is not int or calls < 0:
                raise ValueError("Observation receipt needs its actual inference request count")
            value = {"schema": "second-run/maintainer-observation@1",
                     "artifact_root": str(directory), "receipt": str(receipt_path),
                     "artifacts": _manifest(directory), "observation_id": epoch,
                     "observed_at": receipt["started_at"], "ended_at": receipt["ended_at"],
                     "inference_requests": calls, "native_status": receipt.get("status"),
                     "declared_identity": receipt.get("declared_identity"),
                     "observed_identity": receipt.get("observed_identity")}
            verify_artifacts(value)
            return value
        return {"parameters": parameters, "inputs": inputs, "execute": execute}

    if task_class == "maintainer-compare":
        if set(task) - common - {"baseline", "candidate", "policy", "baseline_grades", "candidate_grades"}:
            raise ValueError("Unsupported maintainer-compare task fields")
        baseline, baseline_inputs, baseline_receipt = _receipt_input(task.get("baseline"), base, "baseline", owner)
        candidate, candidate_inputs, candidate_receipt = _receipt_input(task.get("candidate"), base, "candidate", owner)
        policy = _path(task.get("policy"), base, "policy")
        grades = {name: _path(task[name], base, name) for name in ("baseline_grades", "candidate_grades") if name in task}
        grade_inputs = {}
        for name, path in grades.items():
            grade = owner.validate_grades(path, baseline if name == "baseline_grades" else candidate)
            closure = []
            for artifact in grade.get("artifacts", []):
                artifact_path = (path.parent / artifact["path"]).resolve()
                if not artifact_path.is_relative_to(path.parent):
                    raise ValueError(name + " artifact escapes its grading directory")
                closure.append(artifact_path)
            grade_inputs.update(_inputs(closure, name + ":artifact"))
        inputs = {"adapter_code": HERE, "policy": policy,
                  **_inputs(_procedures(), "procedure"),
                  **_inputs(baseline_inputs, "baseline"), **_inputs(candidate_inputs, "candidate"), **grades, **grade_inputs}
        parameters = {"baseline_observation_id": baseline_receipt["observation_id"],
                      "candidate_observation_id": candidate_receipt["observation_id"]}

        def execute():
            directory = _output(execution_context)
            owner.analyze_receipts(baseline, candidate, policy, directory, **grades)
            receipt_path = directory / "verdict.json"
            verdict = json.loads(receipt_path.read_bytes())
            value = {"schema": "second-run/maintainer-comparison@1",
                     "artifact_root": str(directory), "receipt": str(receipt_path),
                     "artifacts": _manifest(directory), "verdict": verdict,
                     "inference_requests": 0}
            verify_artifacts(value)
            return value
        return {"parameters": parameters, "inputs": inputs, "execute": execute}
    raise ValueError("Unsupported maintainer operation: " + str(task_class))
