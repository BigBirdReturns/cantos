"""Stable, explicit inputs and evidence integrity for the maintainer instrument."""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

try:
    from .owner_ocl.runner import _strict_loads, _equal, endpoint
    from .owner_ocl.core import _safe, sha256_file
except ImportError:
    from owner_ocl.runner import _strict_loads, _equal, endpoint
    from owner_ocl.core import _safe, sha256_file

ROOT = Path(__file__).resolve().parent
EXITS = {"pass": 0, "regression": 1, "incomparable": 2, "error": 3}


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def load(path):
    # Reuse the owning evaluator's duplicate-key and non-finite rejection.
    return _strict_loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())


def keys(value, allowed, label):
    if not isinstance(value, dict):
        raise ValueError(label + " must be an object")
    extra = set(value) - set(allowed)
    if extra:
        raise ValueError(label + " has unknown fields: " + ", ".join(sorted(extra)))


def number(value, label, lo, hi, integer=False):
    types = (int,) if integer else (int, float)
    if type(value) not in types or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"invalid {label}: expected {lo}..{hi}")
    return value


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be a nonempty string")
    return value


def file_record(path, root):
    path = Path(path)
    return {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path),
            "bytes": path.stat().st_size}


def closure(root, exclude=("run.json",)):
    root = Path(root)
    return [file_record(p, root) for p in sorted(root.rglob("*"))
            if p.is_file() and p.relative_to(root).as_posix() not in exclude]


def validate_closure(receipt_path, receipt=None):
    path = Path(receipt_path).resolve()
    value = receipt if receipt is not None else load(path)
    entries = value.get("artifacts")
    if not isinstance(entries, list) or not entries:
        raise ValueError("evidence artifact closure is missing")
    seen = set()
    for entry in entries:
        keys(entry, {"path", "sha256", "bytes"}, "artifact")
        rel = entry.get("path")
        p = _safe(path.parent, rel)
        if rel in seen or p == path:
            raise ValueError("duplicate or self-referencing artifact")
        seen.add(rel)
        if not p.is_file() or p.stat().st_size != entry.get("bytes") or sha256_file(p) != entry.get("sha256"):
            raise ValueError("missing or changed evidence: " + str(rel))
    return value


PROTOCOL_DEFAULTS = {"trials": 3, "repeats": 1, "concurrency": 1, "seed": 1729,
                     "timeout_s": 60, "max_tokens": 512, "warmup": 0, "extra_body": {}}


def protocol(value):
    keys(value, PROTOCOL_DEFAULTS, "protocol")
    out = {**PROTOCOL_DEFAULTS, **value}
    for key, lo, hi in (("trials", 1, 100), ("repeats", 1, 100), ("concurrency", 1, 128),
                        ("seed", 0, 2147483647), ("max_tokens", 1, 131072), ("warmup", 0, 1000)):
        number(out[key], "protocol." + key, lo, hi, True)
    number(out["timeout_s"], "timeout_s", 0.001, 600)
    extra = out["extra_body"]
    if not isinstance(extra, dict):
        raise ValueError("extra_body must be an object")
    protected = {"model", "messages", "temperature", "max_tokens", "stream", "stream_options",
                 "api_key", "authorization", "api_base", "n", "seed"}
    if protected & set(extra):
        raise ValueError("protected request control in extra_body")
    canonical(out)
    return out


def expectation(value):
    keys(value, {"kind", "value", "grader"}, "expect")
    kind = value.get("kind")
    if kind in ("json_exact", "text_exact"):
        if "value" not in value or (kind == "text_exact" and not isinstance(value["value"], str)):
            raise ValueError("exact expectation value required")
        if "grader" in value:
            raise ValueError("grader is only valid for external expectations")
    elif kind == "external":
        if "value" in value:
            raise ValueError("external expectation must not contain a placeholder value")
        grader = value.get("grader")
        keys(grader, {"name", "revision", "artifact_sha256", "reference_sha256", "criterion", "normalizer_sha256"}, "grader")
        for field in ("name", "revision", "artifact_sha256", "reference_sha256"):
            nonempty(grader.get(field), "grader." + field)
        for field in ("artifact_sha256", "reference_sha256"):
            if len(grader[field]) != 64 or any(c not in "0123456789abcdef" for c in grader[field]):
                raise ValueError("grader digest must be lowercase SHA256")
        if "normalizer_sha256" in grader and (not isinstance(grader["normalizer_sha256"], str) or len(grader["normalizer_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in grader["normalizer_sha256"])):
            raise ValueError("normalizer digest must be lowercase SHA256")
        if "criterion" in grader:
            nonempty(grader["criterion"], "grader.criterion")
    else:
        raise ValueError("expect.kind must be json_exact, text_exact, or external")


def steps(case):
    return case["steps"] if "steps" in case else [{"messages": case["messages"], "expect": case["expect"]}]


def validate_workload(value):
    keys(value, {"schema", "name", "version", "source", "description", "cases"}, "workload")
    if value.get("schema") != "cantos.maintainer.workload/1":
        raise ValueError("unsupported workload schema")
    for field in ("name", "version"):
        nonempty(value.get(field), "workload." + field)
    cases = value.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100000:
        raise ValueError("workload requires 1..100000 cases")
    seen = set()
    for case in cases:
        keys(case, {"id", "messages", "expect", "steps", "description", "source"}, "case")
        tid = nonempty(case.get("id"), "case.id")
        if tid in seen:
            raise ValueError("duplicate case id")
        seen.add(tid)
        if "steps" in case and ("messages" in case or "expect" in case):
            raise ValueError("use steps or messages/expect")
        items = steps(case)
        if not isinstance(items, list) or not 1 <= len(items) <= 32:
            raise ValueError("case requires 1..32 steps")
        for index, step in enumerate(items):
            keys(step, {"messages", "expect"}, "step")
            messages = step.get("messages")
            if not isinstance(messages, list) or not messages:
                raise ValueError("step messages required")
            for message in messages:
                keys(message, {"role", "content"}, "message")
                if message.get("role") not in ("system", "user", "assistant") or not isinstance(message.get("content"), str):
                    raise ValueError("only text system/user/assistant messages are supported")
            expectation(step.get("expect"))
            if step["expect"]["kind"] == "external" and index != len(items) - 1:
                raise ValueError("external grading is allowed at the final step only")
    canonical(value)
    return value


POLICY_DEFAULTS = {
    "schema": "cantos.maintainer.policy/1", "allowed_changes": [], "min_trials": 3,
    "min_baseline_acceptance": 1.0, "min_candidate_acceptance": 1.0, "max_acceptance_drop": 0.0,
    "max_new_failures": 0,
    "max_p95_latency_increase": 0.15, "max_p95_ttft_increase": 0.15,
    "max_accepted_throughput_drop": 0.15, "max_cost_per_accepted_increase": None,
    "acceptance": {"max_latency_s": None, "max_ttft_s": None, "finish_reasons": ["stop"]},
    "prices": {"baseline_per_hour": 0.0, "candidate_per_hour": 0.0},
    "require_observed_model": True, "require_observed_version": False,
}


def policy(value):
    keys(value, POLICY_DEFAULTS, "policy")
    out = {**POLICY_DEFAULTS, **value}
    if out["schema"] != "cantos.maintainer.policy/1":
        raise ValueError("unsupported policy schema")
    number(out["min_trials"], "min_trials", 1, 100, True)
    number(out["max_new_failures"], "max_new_failures", 0, 1000000000, True)
    for key in ("min_baseline_acceptance", "min_candidate_acceptance", "max_acceptance_drop",
                "max_accepted_throughput_drop"):
        number(out[key], key, 0, 1)
    for key in ("max_p95_latency_increase", "max_p95_ttft_increase", "max_cost_per_accepted_increase"):
        if out[key] is not None:
            number(out[key], key, 0, 1000000)
    for key in ("require_observed_model", "require_observed_version"):
        if type(out[key]) is not bool:
            raise ValueError(key + " must be boolean")
    allowed = out["allowed_changes"]
    if not isinstance(allowed, list) or any(not isinstance(x, str) or not x or x.startswith(".") for x in allowed):
        raise ValueError("allowed_changes must contain explicit dotted factor paths")
    if len(set(allowed)) != len(allowed):
        raise ValueError("duplicate allowed change")
    for key in ("acceptance", "prices"):
        keys(out[key], POLICY_DEFAULTS[key], key)
        out[key] = {**POLICY_DEFAULTS[key], **out[key]}
    for key in ("max_latency_s", "max_ttft_s"):
        if out["acceptance"][key] is not None:
            number(out["acceptance"][key], key, 0, 100000000)
    reasons = out["acceptance"]["finish_reasons"]
    if not isinstance(reasons, list) or not reasons or any(not isinstance(x, str) or not x for x in reasons):
        raise ValueError("finish_reasons must be nonempty")
    for key, value in out["prices"].items():
        number(value, key, 0, 1000000000)
    return out


def producer_records():
    # Hash actual code, including the pinned owner modules, not a version label.
    return [file_record(p, ROOT) for p in sorted(ROOT.rglob("*.py"))
            if "tests" not in p.relative_to(ROOT).parts and not p.name.startswith("test_")]


def prepare(spec_path, arm=None):
    path = Path(spec_path).resolve()
    spec = load(path)
    keys(spec, {"schema", "workload", "policy", "protocol", "baseline", "candidate"}, "spec")
    if spec.get("schema") != "cantos.maintainer.spec/1":
        raise ValueError("unsupported spec schema")
    if arm is None:
        return {name: prepare(path, name) for name in ("baseline", "candidate")}
    if arm not in ("baseline", "candidate"):
        raise ValueError("arm must be baseline or candidate")
    config = spec.get(arm)
    keys(config, {"base_url", "model", "identity", "implementation_files", "allow_remote", "auth_env"}, arm)
    config = json.loads(json.dumps(config))
    nonempty(config.get("model"), arm + ".model")
    if config["model"] == "your-served-model-id" or "REPLACE_WITH" in canonical(config).decode("utf-8"):
        raise ValueError("configure " + arm + " endpoint, served model and pinned identities in your copy of examples/spec.json before live observation")
    if type(config.get("allow_remote", False)) is not bool:
        raise ValueError("allow_remote must be boolean")
    endpoint(config.get("base_url"), config.get("allow_remote", False))
    if not isinstance(config.get("identity"), dict):
        raise ValueError("arm identity must be an object")
    auth = config.get("auth_env", "OCL_API_KEY")
    if not isinstance(auth, str) or not auth or any(not (c.isalnum() or c == "_") for c in auth):
        raise ValueError("auth_env must name an environment variable")
    config["auth_env"] = auth
    workpath = (path.parent / nonempty(spec.get("workload"), "workload path")).resolve()
    work = validate_workload(load(workpath))
    proto = protocol(spec.get("protocol", {}))
    declared_files = config.get("implementation_files", [])
    if not isinstance(declared_files, list) or any(not isinstance(x, str) or not x for x in declared_files):
        raise ValueError("implementation_files must be a list of paths")
    impl = []
    dependencies = [str(workpath)]
    for name in declared_files:
        p = (path.parent / name).resolve()
        if not p.is_file():
            raise ValueError("missing implementation input: " + name)
        impl.append({"path": name, "sha256": sha256_file(p), "bytes": p.stat().st_size})
        dependencies.append(str(p))
    producers = producer_records()
    dependencies.extend(str(ROOT / x["path"]) for x in producers)
    projection = {"configuration": config, "implementation_inputs": impl,
                  "workload_sha256": sha256_file(workpath), "protocol": proto,
                  "producer_files": producers}
    # Neither the whole spec file nor the policy file participates here. A price
    # change or another arm's edit cannot authorize or invalidate live observation.
    return {"spec": spec, "arm": arm, "configuration": config, "workload": work,
            "workload_path": str(workpath), "protocol": proto, "identity": projection,
            "observation_key": digest(projection), "dependencies": sorted(set(dependencies)),
            "policy_path": str((path.parent / spec["policy"]).resolve()) if spec.get("policy") else None,
            "spec_path": str(path)}
