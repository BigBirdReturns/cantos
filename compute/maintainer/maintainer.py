#!/usr/bin/env python3
"""Cantos maintainer instrument: live observations and separate retained analysis."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import random
import socket
import statistics
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from .common import (ROOT, EXITS, _equal, _safe, _strict_loads, canonical, closure,
                         digest, file_record, load, now, policy, prepare, producer_records,
                         sha256_file, steps, validate_closure, validate_workload, write)
    from .streaming import capture, parse_capture, probe
    from .owner_ocl.compare import compare as ocl_compare
    from .owner_ocl.core import _pct, summarize
    from .owner_ocl.runner import FORMATS
    from .owner_ocl.tasks import make_tasks
    from .owner_vllm.audit import exact_peak
except ImportError:
    from common import (ROOT, EXITS, _equal, _safe, _strict_loads, canonical, closure,
                        digest, file_record, load, now, policy, prepare, producer_records,
                        sha256_file, steps, validate_closure, validate_workload, write)
    from streaming import capture, parse_capture, probe
    from owner_ocl.compare import compare as ocl_compare
    from owner_ocl.core import _pct, summarize
    from owner_ocl.runner import FORMATS
    from owner_ocl.tasks import make_tasks
    from owner_vllm.audit import exact_peak


LIMITS = [
    "This verdict covers the supplied workload, serving endpoints and policy only.",
    "Declared weights, hardware, tokenizer and server flags are operator declarations; HTTP probes do not attest them.",
    "Repeated cases are correlated. Trial ranges describe variation and are not a population confidence guarantee.",
    "TTFT measures first visible content at the client, including network and queueing; content chunks are not tokens.",
    "Token counts come from server usage. The instrument does not manufacture per-token timings, power or GPU run counts.",
    "No request retries. Transport and incomplete stream failures are retained and force an error verdict.",
    "Server cache state, co-tenancy, thermals and load require operator controls and declared identity settings.",
]


def grade_text(expect, attempt):
    if attempt["error"]:
        return False, None, attempt["error"]
    kind = expect["kind"]
    if kind == "external":
        return None, None, "external grading required"
    try:
        actual = (_strict_loads(attempt["response_text"]) if kind == "json_exact"
                  else attempt["response_text"])
        ok = _equal(actual, expect["value"])
        return ok, actual, None if ok else "answer mismatch"
    except (ValueError, TypeError, KeyError) as exc:
        return False, None, type(exc).__name__ + ": exact output parse failed"


class Observer:
    def __init__(self, prepared, out_dir, observation_id, pairing=None):
        self.p = prepared
        self.root = Path(out_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=False)
        self.id = observation_id
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("observation_id must be nonempty")
        self.started_at = now()
        self.observations = []
        self.warmups = []
        self.trials = []
        self.pairing = pairing
        self.request_count = 0
        self.client = {"hostname": socket.gethostname(), "platform": platform.platform(),
                       "python": platform.python_version()}
        self.workbytes = Path(prepared["workload_path"]).read_bytes()
        (self.root / "workload.json").write_bytes(self.workbytes)
        write(self.root / "plan.json", {
            "schema": "cantos.maintainer.plan/1", "observation_id": self.id,
            "started_at": self.started_at, "arm": prepared["arm"],
            "observation_key": prepared["observation_key"], "identity": prepared["identity"],
            "client": self.client, "pairing": pairing,
            "expected_observations": len(prepared["workload"]["cases"]) * prepared["protocol"]["trials"] * prepared["protocol"]["repeats"],
            "execution": "real streamed HTTP; zero retries; no server process management"})
        self.before = probe(prepared["configuration"], prepared["protocol"]["timeout_s"])
        write(self.root / "identity-before.json", self.before)
        self.journal = (self.root / "observations.jsonl").open("x", encoding="utf-8")

    def one(self, case_index, trial, repetition, warmup=False):
        case = self.p["workload"]["cases"][case_index]
        start = time.monotonic()
        attempts = []
        answers = []
        checks = []
        messages = []
        all_steps = steps(case)
        final_error = None
        for i, step in enumerate(all_steps):
            messages.extend(copy.deepcopy(step["messages"]))
            raw, attempt = capture(self.p["configuration"], self.p["protocol"], copy.deepcopy(messages), "step_" + str(i))
            rel = f"raw/{'warmup' if warmup else 'trial'}/{trial:03d}-{repetition:03d}-{case_index:06d}-{i:02d}.json"
            write(self.root / rel, raw)
            attempt["raw_path"] = rel
            attempts.append(attempt)
            ok, actual, err = grade_text(step["expect"], attempt)
            checks.append(ok)
            answers.append(actual)
            final_error = err
            if ok is False:
                break
            messages.append({"role": "assistant", "content": attempt["response_text"]})
        end = time.monotonic()
        accepted = False if False in checks else (None if None in checks else True)
        return {"task_id": case["id"], "case_index": case_index, "trial": trial,
                "repetition": repetition, "warmup": warmup, "accepted": accepted,
                "error": final_error, "duration_s": end - start,
                "started_monotonic_s": start, "ended_monotonic_s": end,
                "step_checks": checks, "actual": answers, "attempts": attempts,
                "evaluator_version": "ocl.exact-json/1+cantos.stream/1"}

    def record(self, record):
        self.request_count += len(record["attempts"])
        self.journal.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        self.journal.flush()
        os.fsync(self.journal.fileno())
        (self.warmups if record["warmup"] else self.observations).append(record)

    def warmup(self):
        count = self.p["protocol"]["warmup"]
        for i in range(count):
            self.record(self.one(i % len(self.p["workload"]["cases"]), 0, i, True))

    def trial(self, trial, position=None):
        proto = self.p["protocol"]
        work = [(i, r) for r in range(proto["repeats"])
                for i in range(len(self.p["workload"]["cases"]))]
        random.Random(proto["seed"] + trial).shuffle(work)
        begin = time.monotonic()
        with ThreadPoolExecutor(max_workers=proto["concurrency"]) as pool:
            futures = [pool.submit(self.one, i, trial, r) for i, r in work]
            for future in as_completed(futures):
                self.record(future.result())
        end = time.monotonic()
        self.trials.append({"trial": trial, "paired_position": position,
                            "order": [[self.p["workload"]["cases"][i]["id"], r] for i, r in work],
                            "started_monotonic_s": begin, "ended_monotonic_s": end,
                            "duration_s": end - begin})

    def finish(self):
        self.journal.close()
        after = probe(self.p["configuration"], self.p["protocol"]["timeout_s"])
        write(self.root / "identity-after.json", after)
        self.observations.sort(key=lambda x: (x["trial"], x["repetition"], x["task_id"]))
        all_attempts = [a for o in self.observations + self.warmups for a in o["attempts"]]
        receipt = {
            "schema": "cantos.maintainer.run/1", "run_id": self.id,
            "observation_id": self.id, "arm": self.p["arm"],
            "observation_key": self.p["observation_key"], "observation_identity": self.p["identity"],
            "status": "error" if any(a["error"] for a in all_attempts) else "complete",
            "started_at": self.started_at, "ended_at": now(),
            "workload_sha256": hashlib.sha256(self.workbytes).hexdigest(),
            "protocol": self.p["protocol"], "declared_identity": self.p["configuration"]["identity"],
            "configuration": self.p["configuration"], "producer_files": self.p["identity"]["producer_files"],
            "client": self.client, "pairing": self.pairing,
            "observed_identity": {"before": self.before, "after": after,
                                  "stream_models": sorted({m for a in all_attempts for m in a["response_models"]}),
                                  "authority": "endpoint self-report and response fields; not hardware or weights attestation"},
            "inference_requests": self.request_count,
            "duration_s": sum(t["duration_s"] for t in self.trials),
            "trials": self.trials, "observations": self.observations, "warmups": self.warmups,
            "limitations": LIMITS, "artifacts": closure(self.root)}
        write(self.root / "run.json", receipt)
        return receipt


def observe(spec_path, arm, out_dir, observation_id):
    p = prepare(spec_path, arm)
    o = Observer(p, out_dir, observation_id)
    o.warmup()
    for trial in range(p["protocol"]["trials"]):
        o.trial(trial)
    return o.finish()


def _request_expected(config, proto, messages):
    return {"model": config["model"], "messages": messages, "temperature": 0,
            "seed": proto["seed"], "max_tokens": proto["max_tokens"], "stream": True,
            "stream_options": {"include_usage": True}, **proto["extra_body"]}


def validate_receipt(run_path):
    path = Path(run_path).resolve()
    receipt = validate_closure(path)
    if receipt.get("schema") != "cantos.maintainer.run/1":
        raise ValueError("unsupported run schema")
    if receipt.get("status") not in ("complete", "error"):
        raise ValueError("run did not reach a terminal capture state")
    if digest(receipt["observation_identity"]) != receipt["observation_key"]:
        raise ValueError("observation identity hash mismatch")
    projection = receipt["observation_identity"]
    for a, b in ((receipt["protocol"], projection["protocol"]),
                 (receipt["configuration"], projection["configuration"]),
                 (receipt["declared_identity"], receipt["configuration"]["identity"]),
                 (receipt["producer_files"], projection["producer_files"]),
                 (receipt["workload_sha256"], projection["workload_sha256"])):
        if not _equal(a, b):
            raise ValueError("receipt identity projection mismatch")
    if sha256_file(path.parent / "workload.json") != receipt["workload_sha256"]:
        raise ValueError("workload hash mismatch")
    workload = validate_workload(load(path.parent / "workload.json"))
    available = {x["path"] for x in receipt["artifacts"]}
    mandatory = {"workload.json", "plan.json", "identity-before.json", "identity-after.json", "observations.jsonl"}
    if not mandatory <= available:
        raise ValueError("receipt closure omits required evidence")
    plan = load(path.parent / "plan.json")
    if plan["observation_key"] != receipt["observation_key"] or plan["identity"] != projection or plan["observation_id"] != receipt["observation_id"]:
        raise ValueError("plan and completed receipt disagree")
    if plan["pairing"] != receipt["pairing"] or plan["client"] != receipt["client"]:
        raise ValueError("client or pairing metadata differs from plan")
    if receipt["observed_identity"]["before"] != load(path.parent / "identity-before.json") or receipt["observed_identity"]["after"] != load(path.parent / "identity-after.json"):
        raise ValueError("observed identity differs from raw probe evidence")
    proto = receipt["protocol"]
    expected = {(c["id"], t, r) for t in range(proto["trials"])
                for r in range(proto["repeats"]) for c in workload["cases"]}
    actual = [(o["task_id"], o["trial"], o["repetition"]) for o in receipt["observations"]]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("missing, extra or duplicate task observations")
    if len(receipt["warmups"]) != proto["warmup"]:
        raise ValueError("warmup accounting mismatch")
    if len(receipt["trials"]) != proto["trials"] or {t["trial"] for t in receipt["trials"]} != set(range(proto["trials"])):
        raise ValueError("trial accounting mismatch")
    for trial in receipt["trials"]:
        if trial["duration_s"] <= 0 or abs(trial["ended_monotonic_s"] - trial["started_monotonic_s"] - trial["duration_s"]) > 1e-6:
            raise ValueError("invalid trial interval")
        wanted = [(i, r) for r in range(proto["repeats"]) for i in range(len(workload["cases"]))]
        random.Random(proto["seed"] + trial["trial"]).shuffle(wanted)
        if trial["order"] != [[workload["cases"][i]["id"], r] for i, r in wanted]:
            raise ValueError("trial order differs from fixed protocol")
    count = 0
    had_error = False
    models = set()
    seen_raw = set()
    journal = [_strict_loads(line) for line in (path.parent / "observations.jsonl").read_text(encoding="utf-8").splitlines()]
    retained = receipt["observations"] + receipt["warmups"]
    if sorted(canonical(x) for x in journal) != sorted(canonical(x) for x in retained):
        raise ValueError("journal and receipt observations disagree")
    for obs in retained:
        case = workload["cases"][obs["case_index"]]
        if case["id"] != obs["task_id"] or not obs["attempts"]:
            raise ValueError("invalid case mapping or missing attempt")
        messages = []
        checks, answers = [], []
        if len(obs["attempts"]) > len(steps(case)):
            raise ValueError("too many task attempts")
        for i, attempt in enumerate(obs["attempts"]):
            step = steps(case)[i]
            messages.extend(copy.deepcopy(step["messages"]))
            rel = attempt["raw_path"]
            if rel not in available or rel in seen_raw:
                raise ValueError("raw stream omitted from closure or reused by another request")
            seen_raw.add(rel)
            raw = load(_safe(path.parent, rel))
            parsed = parse_capture(raw)
            for key, value in parsed.items():
                if not _equal(attempt.get(key), value):
                    raise ValueError("stored stream summary differs from raw evidence: " + key)
            if not _equal(raw["request"], _request_expected(receipt["configuration"], proto, messages)):
                raise ValueError("actual request differs from workload/protocol")
            if attempt["started_monotonic_s"] < obs["started_monotonic_s"] or attempt["ended_monotonic_s"] > obs["ended_monotonic_s"]:
                raise ValueError("attempt outside observation interval")
            ok, answer, _ = grade_text(step["expect"], parsed)
            checks.append(ok)
            answers.append(answer)
            if ok is False and i != len(obs["attempts"]) - 1:
                raise ValueError("attempt continued after failed stage")
            messages.append({"role": "assistant", "content": parsed["response_text"]})
            count += 1
            had_error |= bool(parsed["error"])
            models.update(parsed["response_models"])
        if len(obs["attempts"]) < len(steps(case)) and checks[-1] is not False:
            raise ValueError("missing later task stage")
        accepted = False if False in checks else (None if None in checks else True)
        if not _equal(obs["accepted"], accepted) or not _equal(obs["step_checks"], checks) or not _equal(obs["actual"], answers):
            raise ValueError("stored grade differs from exact raw response")
        if obs["duration_s"] <= 0 or abs(obs["ended_monotonic_s"] - obs["started_monotonic_s"] - obs["duration_s"]) > 1e-6:
            raise ValueError("invalid observation interval")
        if not obs["warmup"]:
            trial = next(t for t in receipt["trials"] if t["trial"] == obs["trial"])
            if obs["started_monotonic_s"] < trial["started_monotonic_s"] or obs["ended_monotonic_s"] > trial["ended_monotonic_s"]:
                raise ValueError("observation outside measured trial")
    if count != receipt["inference_requests"] or receipt["status"] != ("error" if had_error else "complete"):
        raise ValueError("request count or terminal status inconsistent with raw evidence")
    if sorted(models) != receipt["observed_identity"]["stream_models"]:
        raise ValueError("response model receipt mismatch")
    if abs(receipt["duration_s"] - sum(t["duration_s"] for t in receipt["trials"])) > 1e-6:
        raise ValueError("measured trial duration mismatch")
    return receipt


def validate_grades(grades_path, run_path):
    run = validate_receipt(run_path)
    grade = validate_closure(grades_path)
    if grade.get("schema") != "cantos.maintainer.grades/1":
        raise ValueError("unsupported external grade schema")
    if grade.get("run_sha256") != sha256_file(run_path) or grade.get("workload_sha256") != run["workload_sha256"]:
        raise ValueError("external grades belong to another run or workload")
    work = load(Path(run_path).resolve().parent / "workload.json")
    external = {c["id"]: steps(c)[-1]["expect"] for c in work["cases"] if steps(c)[-1]["expect"]["kind"] == "external"}
    records = {(o["task_id"], o["trial"], o["repetition"]): o for o in run["observations"]}
    artifacts = {x["path"] for x in grade["artifacts"]}
    seen = set()
    if not isinstance(grade.get("results"), list):
        raise ValueError("external grade results required")
    for result in grade["results"]:
        key = (result["task_id"], result["trial"], result["repetition"])
        if key in seen or key not in records or key[0] not in external:
            raise ValueError("duplicate or unexpected external grade")
        seen.add(key)
        if not _equal(grade.get("grader"), external[key[0]]["grader"]):
            raise ValueError("external grader identity differs from workload contract")
        if result.get("response_sha256") != records[key]["attempts"][-1]["response_sha256"]:
            raise ValueError("external grade response hash mismatch")
        if type(result.get("accepted")) is not bool:
            raise ValueError("external accepted outcome must be boolean")
        evidence = result.get("evidence")
        if not isinstance(evidence, list) or not evidence or not set(evidence) <= artifacts:
            raise ValueError("external grade requires retained result evidence")
    expected = {key for key, obs in records.items() if key[0] in external and obs["accepted"] is None}
    if not expected <= seen:
        raise ValueError("external grades omit completed ungraded responses")
    return grade


def _flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict) and obj:
        for key, value in sorted(obj.items()):
            out.update(_flatten(value, (prefix + "." if prefix else "") + key))
    else:
        out[prefix] = obj
    return out


def _factor_view(run):
    identity = run["observation_identity"]
    return {"identity": run["declared_identity"], "model": run["configuration"]["model"],
            "implementation_inputs": identity["implementation_inputs"],
            "protocol": run["protocol"], "client": run["client"],
            "producer_files": run["producer_files"], "workload_sha256": run["workload_sha256"]}


def _identity_problems(run, pol, side):
    flat = _flatten(run["declared_identity"])
    required = ("implementation.name", "implementation.revision", "model.revision", "model.sha256",
                "tokenizer.revision", "hardware.id", "hardware.description", "precision", "context_limit")
    issues = []
    for key in required:
        value = flat.get(key)
        if value is None or value == "" or (isinstance(value, str) and (value.lower() in ("unknown", "unverified", "tbd") or value.upper().startswith("REPLACE_"))):
            issues.append(side + ": missing declared identity." + key)
    weights = flat.get("model.sha256", "")
    if not isinstance(weights, str) or len(weights) != 64 or any(c not in "0123456789abcdef" for c in weights):
        issues.append(side + ": model.sha256 is not a pinned SHA256")
    context = flat.get("context_limit")
    if type(context) is not int or context <= 0:
        issues.append(side + ": context_limit must be a positive integer")
    expected_model = run["configuration"]["model"]
    observed = run["observed_identity"]
    if pol["require_observed_model"] and observed["stream_models"] != [expected_model]:
        issues.append(side + ": response model differs from requested identity or is absent")
    versions = []
    for phase in ("before", "after"):
        probes = observed[phase]
        version = (probes.get("version", {}).get("body") or {}).get("version")
        versions.append(version)
        data = (probes.get("models", {}).get("body") or {}).get("data", [])
        ids = [x.get("id") for x in data if isinstance(x, dict)]
        if pol["require_observed_model"] and expected_model not in ids:
            issues.append(side + ": /v1/models does not confirm requested model at " + phase)
        if pol["require_observed_version"] and not version:
            issues.append(side + ": /version missing at " + phase)
    if versions[0] != versions[1]:
        issues.append(side + ": observed server version changed during capture")
    return issues


def _graded(run, workload, pol, grades=None):
    external = {} if grades is None else {(g["task_id"], g["trial"], g["repetition"]): g for g in grades["results"]}
    observations = []
    ungraded = []
    for original in run["observations"]:
        obs = copy.deepcopy(original)
        case = workload["cases"][obs["case_index"]]
        check = [x is True for x in obs["step_checks"]]
        actual = obs["actual"]
        expected = [s["expect"].get("value", True) for s in steps(case)]
        if steps(case)[-1]["expect"]["kind"] == "external" and obs["accepted"] is None:
            key = (obs["task_id"], obs["trial"], obs["repetition"])
            result = external.get(key)
            if result is None:
                ungraded.append(key)
            check[-1] = result is not None and result["accepted"]
            actual[-1] = result["accepted"] if result else None
        reasons = []
        if not all(check):
            reasons.append("exact task acceptance failed" if obs["accepted"] is not None else "external grade absent or failed")
        if any(a["finish_reason"] not in pol["acceptance"]["finish_reasons"] for a in obs["attempts"]):
            reasons.append("finish reason outside acceptance policy")
        max_latency = pol["acceptance"]["max_latency_s"]
        if max_latency is not None and obs["duration_s"] > max_latency:
            reasons.append("task latency requirement exceeded")
        max_ttft = pol["acceptance"]["max_ttft_s"]
        if max_ttft is not None and any(a["ttft_s"] is None or a["ttft_s"] > max_ttft for a in obs["attempts"]):
            reasons.append("TTFT requirement exceeded or unmeasured")
        accepted = not reasons
        obs.update({"accepted": accepted, "actual": actual, "expected": expected,
                    "error": "; ".join(reasons) if reasons else None,
                    "checks": {"exact_expected": all(check), "acceptance_policy": not reasons},
                    "repetition": obs["trial"] * run["protocol"]["repeats"] + obs["repetition"]})
        observations.append(obs)
    proto = run["protocol"]
    identity = run["declared_identity"]
    projected = {"schema": "ocl.run/1", "run_id": run["run_id"], "started_at": run["started_at"],
                 "duration_s": run["duration_s"], "observations": observations,
                 "workload": {"name": workload["name"], "version": workload["version"], "seed": proto["seed"],
                              "repeats": proto["trials"] * proto["repeats"], "fixture_sha256": run["workload_sha256"],
                              "expected_tasks": len(observations), "concurrency": proto["concurrency"], "max_tokens": proto["max_tokens"]},
                 "provenance": {"model": run["configuration"]["model"], "model_sha256": identity.get("model", {}).get("sha256"),
                                "runtime": identity.get("implementation"), "precision": identity.get("precision"),
                                "context_limit": identity.get("context_limit"), "hardware": identity.get("hardware")},
                 "energy": None, "cost": None, "limitations": LIMITS}
    return projected, ungraded


def _metrics(run, projected, rate, matched_keys):
    result = summarize(projected)
    accepted = [o for o in projected["observations"] if o["accepted"]]
    matched = [o for o in accepted if (o["task_id"], o["repetition"]) in matched_keys]
    result["p95_latency_s"] = _pct([o["duration_s"] for o in matched], .95)
    result["p95_ttft_s"] = _pct([a["ttft_s"] for o in matched for a in o["attempts"] if a["ttft_s"] is not None], .95)
    result["performance_population"] = "latency/TTFT: exact matched both-accepted task/trial/repetition pairs; accepted throughput: all measured tasks and full trial windows"
    result["matched_accepted_tasks"] = len(matched)
    result["cost_assumption_per_hour"] = rate
    result["estimated_cost"] = rate * run["duration_s"] / 3600 if rate is not None else None
    result["cost_duration_scope"] = "summed measured trial windows only, including request failures; excludes warmup, probes, server startup, between-trial idle and other reserved time"
    result["cost_per_accepted"] = result["estimated_cost"] / len(accepted) if accepted and result["estimated_cost"] is not None else None
    attempts = [a for o in projected["observations"] for a in o["attempts"]]
    result["peak_request_concurrency"] = exact_peak([a["started_monotonic_s"] for a in attempts],
                                                    [a["duration_s"] for a in attempts], [None] * len(attempts))
    result["trial_metrics"] = []
    for trial in run["trials"]:
        obs = [o for o in projected["observations"] if o["trial"] == trial["trial"]]
        ok = [o for o in obs if o["accepted"]]
        both = [o for o in ok if (o["task_id"], o["repetition"]) in matched_keys]
        result["trial_metrics"].append({"trial": trial["trial"], "duration_s": trial["duration_s"],
                                        "accepted": len(ok), "tasks": len(obs),
                                        "matched_accepted": len(both),
                                        "acceptance_rate": len(ok) / len(obs),
                                        "accepted_per_s": len(ok) / trial["duration_s"],
                                        "p95_latency_s": _pct([o["duration_s"] for o in both], .95),
                                        "p95_ttft_s": _pct([a["ttft_s"] for o in both for a in o["attempts"] if a["ttft_s"] is not None], .95)})
    return result


def _compare_runs(a, b, wa, wb, pol, ga=None, gb=None):
    reasons, regressions, errors = [], [], []
    for side, run in (("baseline", a), ("candidate", b)):
        reasons.extend(_identity_problems(run, pol, side))
        if run["protocol"]["trials"] < pol["min_trials"]:
            reasons.append(side + ": insufficient repeated trials")
        if run["status"] == "error":
            errors.append(side + ": captured transport or stream errors")
    fa, fb = _flatten(_factor_view(a)), _flatten(_factor_view(b))
    changed = [{"factor": k, "baseline": fa.get(k), "candidate": fb.get(k)}
               for k in sorted(set(fa) | set(fb)) if not _equal(fa.get(k), fb.get(k))]
    mandatory = ("workload_sha256", "producer_files", "protocol.trials", "protocol.repeats", "protocol.seed")
    for item in changed:
        factor = item["factor"]
        item["allowed"] = any(factor == x or factor.startswith(x + ".") for x in pol["allowed_changes"])
        if any(factor == x or factor.startswith(x + ".") for x in mandatory):
            reasons.append("fixed pairing condition changed: " + factor)
        elif not item["allowed"]:
            reasons.append("undeclared changed condition: " + factor)
    # Runtime version is observed separately from the declared implementation revision.
    va = a["observed_identity"]["before"].get("version", {}).get("body", {}).get("version")
    vb = b["observed_identity"]["before"].get("version", {}).get("body", {}).get("version")
    if va != vb:
        allowed = any(x in ("identity.implementation", "identity.implementation.revision", "observed.version") for x in pol["allowed_changes"])
        changed.append({"factor": "observed.version", "baseline": va, "candidate": vb, "allowed": allowed})
        if not allowed:
            reasons.append("undeclared changed condition: observed.version")
    pa, ua = _graded(a, wa, pol, ga)
    pb, ub = _graded(b, wb, pol, gb)
    if ua or ub:
        reasons.append("external application outcomes remain ungraded")
    native = ocl_compare(pa, pb)
    matched_keys = {(x["task_id"], x["repetition"]) for x in native["task_transitions"] if x["outcome"] == "both_accepted"}
    ma = _metrics(a, pa, pol["prices"]["baseline_per_hour"], matched_keys)
    mb = _metrics(b, pb, pol["prices"]["candidate_per_hour"], matched_keys)
    if not native["paired_task_accounting"]:
        reasons.append("native OCL paired task accounting failed")
    if ma["accepted_tasks"] == 0 or ma["acceptance_rate"] < pol["min_baseline_acceptance"]:
        reasons.append("baseline acceptance is insufficient to establish a usable reference")
    if mb["accepted_tasks"] == 0 or mb["acceptance_rate"] < pol["min_candidate_acceptance"]:
        regressions.append("candidate acceptance falls below requirement")
    if ma["acceptance_rate"] - mb["acceptance_rate"] > pol["max_acceptance_drop"] + 1e-12:
        regressions.append("candidate acceptance drop exceeds policy")
    if native["paired_counts"]["a_only"] > pol["max_new_failures"]:
        regressions.append("newly failing baseline-accepted task instances exceed max_new_failures")
    checks = []
    for metric, threshold, lower_better in (("p95_latency_s", "max_p95_latency_increase", True),
                                            ("p95_ttft_s", "max_p95_ttft_increase", True),
                                            ("accepted_per_s", "max_accepted_throughput_drop", False)):
        limit = pol[threshold]
        if limit is None:
            continue
        ratios = []
        for left, right in zip(ma["trial_metrics"], mb["trial_metrics"]):
            x, y = left[metric], right[metric]
            if x is not None and y is not None and x > 0:
                ratios.append(y / x)
        if len(ratios) != len(ma["trial_metrics"]) or len(ratios) != len(mb["trial_metrics"]):
            if regressions and not (ua or ub):
                checks.append({"metric": metric, "status": "unavailable after quality regression"})
            else:
                reasons.append("unmeasured paired trial metric: " + metric)
                checks.append({"metric": metric, "status": "unmeasured"})
            continue
        center = statistics.median(ratios)
        bad = center > 1 + limit if lower_better else center < 1 - limit
        checks.append({"metric": metric, "trial_candidate_over_baseline": ratios,
                       "median_ratio": center, "range": [min(ratios), max(ratios)],
                       "threshold_fraction": limit, "status": "regression" if bad else "pass"})
        if bad:
            regressions.append(metric + " median paired-trial ratio exceeds policy")
    cost_limit = pol["max_cost_per_accepted_increase"]
    if cost_limit is not None:
        x, y = ma["cost_per_accepted"], mb["cost_per_accepted"]
        if x is None or y is None or x <= 0:
            reasons.append("cost gate requires positive baseline and measured accepted work")
        elif y / x > 1 + cost_limit:
            regressions.append("estimated cost per accepted task exceeds policy")
    verdict = "error" if errors else "incomparable" if reasons else "regression" if regressions else "pass"
    paired = bool(a.get("pairing") and a["pairing"] == b.get("pairing"))
    return {"schema": "cantos.maintainer.verdict/1", "created_at": now(), "verdict": verdict,
            "exit_code": EXITS[verdict], "reasons": errors + reasons + regressions,
            "errors": errors, "comparability_failures": reasons, "regressions": regressions,
            "changed_factors": changed, "baseline": ma, "candidate": mb,
            "paired_trials": paired, "trial_schedule": "alternating AB/BA" if paired else "separate retained observations",
            "policy": pol, "performance_checks": checks, "native_ocl_comparison": native,
            "scope": "paired accepted outcomes under explicitly declared changes" if changed else "matched declared conditions",
            "limitations": LIMITS, "new_inference_requests": 0}


def _report(result):
    lines = ["# Cantos maintainer verdict", "", "**" + result["verdict"].upper() + "**", ""]
    for reason in result.get("reasons", []):
        lines.append("- " + reason)
    if "baseline" in result:
        lines.extend(["", "| Metric | Baseline | Candidate |", "| --- | ---: | ---: |"])
        for key in ("total_tasks", "accepted_tasks", "acceptance_rate", "p95_latency_s", "p95_ttft_s", "accepted_per_s", "peak_request_concurrency", "cost_per_accepted"):
            values = [result[side].get(key) for side in ("baseline", "candidate")]
            values = [("unpriced" if key == "cost_per_accepted" else "unmeasured") if value is None else str(value) for value in values]
            lines.append(f"| {key} | {values[0]} | {values[1]} |")
    lines.extend(["", "## Evidence scope", ""] + ["- " + x for x in result.get("limitations", LIMITS)])
    return "\n".join(lines) + "\n"


def analyze_receipts(baseline_path, candidate_path, policy_path, out_dir,
                     baseline_grades=None, candidate_grades=None):
    root = Path(out_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    inputs = {}
    try:
        pol = policy(load(policy_path) if policy_path else {})
        a, b = validate_receipt(baseline_path), validate_receipt(candidate_path)
        wa = load(Path(baseline_path).resolve().parent / "workload.json")
        wb = load(Path(candidate_path).resolve().parent / "workload.json")
        ga = validate_grades(baseline_grades, baseline_path) if baseline_grades else None
        gb = validate_grades(candidate_grades, candidate_path) if candidate_grades else None
        for key, path in (("baseline", baseline_path), ("candidate", candidate_path), ("policy", policy_path),
                          ("baseline_grades", baseline_grades), ("candidate_grades", candidate_grades)):
            if path:
                inputs[key] = {"path": str(Path(path).resolve()), "sha256": sha256_file(path)}
        result = _compare_runs(a, b, wa, wb, pol, ga, gb)
    except Exception as exc:
        result = {"schema": "cantos.maintainer.verdict/1", "created_at": now(), "verdict": "error",
                  "exit_code": EXITS["error"], "reasons": [type(exc).__name__ + ": " + str(exc)[:1000]],
                  "limitations": LIMITS, "new_inference_requests": 0}
    result["inputs"] = inputs
    result["analysis_producer_files"] = producer_records()
    write(root / "verdict.json", result)
    with (root / "report.md").open("x", encoding="utf-8") as f:
        f.write(_report(result))
    return result


def run(spec_path, out_dir):
    prepared = prepare(spec_path)
    # Reject an invalid/missing analysis policy before issuing any live inference.
    policy_path = prepared["baseline"]["policy_path"]
    policy(load(policy_path) if policy_path else {})
    root = Path(out_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    pairing = {"id": str(uuid.uuid4()), "schedule": "alternating AB/BA", "seed": prepared["baseline"]["protocol"]["seed"]}
    observers = {arm: Observer(p, root / arm, pairing["id"] + ":" + arm, pairing)
                 for arm, p in prepared.items()}
    for arm in ("baseline", "candidate"):
        observers[arm].warmup()
    for trial in range(prepared["baseline"]["protocol"]["trials"]):
        order = ("baseline", "candidate") if trial % 2 == 0 else ("candidate", "baseline")
        for position, arm in enumerate(order):
            observers[arm].trial(trial, position)
    for obs in observers.values():
        obs.finish()
    result = analyze_receipts(root / "baseline/run.json", root / "candidate/run.json",
                              prepared["baseline"]["policy_path"], root / "analysis")
    # Convenient top-level verdict, identical bytes, with relative evidence pointers.
    (root / "verdict.json").write_bytes((root / "analysis/verdict.json").read_bytes())
    (root / "report.md").write_bytes((root / "analysis/report.md").read_bytes())
    return result


def export_ocl(path, seed):
    cases = []
    for task in make_tasks(seed):
        lookup = {"tool": "lookup", "arguments": {"key": task.key}}
        cases.append({"id": task.task_id, "description": task.description,
                      "steps": [{"messages": [{"role": "system", "content": "Perform the bounded lookup and data-analysis task. Reply only with requested JSON. /no_think"},
                                                {"role": "user", "content": json.dumps(lookup, separators=(",", ":"))}],
                                 "expect": {"kind": "json_exact", "value": lookup}},
                                {"messages": [{"role": "user", "content": json.dumps(task.fixture, separators=(",", ":"))},
                                                {"role": "user", "content": task.description + " " + FORMATS[task.family] + " /no_think"}],
                                 "expect": {"kind": "json_exact", "value": task.expected}}]})
    work = {"schema": "cantos.maintainer.workload/1", "name": "OCL lookup-analysis micro-suite", "version": "1",
            "source": "Pinned owner_ocl.tasks.make_tasks; synthetic qualification cases, not a representative application claim",
            "cases": cases}
    write(path, work)
    return work


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    live = sub.add_parser("run", help="execute paired alternating live trials, then analyze retained evidence")
    live.add_argument("--spec", required=True)
    live.add_argument("--out", required=True)
    obs = sub.add_parser("observe", help="capture one arm; never claim cached evidence is fresh")
    obs.add_argument("--spec", required=True)
    obs.add_argument("--arm", choices=("baseline", "candidate"), required=True)
    obs.add_argument("--out", required=True)
    obs.add_argument("--observation-id", required=True)
    analysis = sub.add_parser("analyze", help="grade and compare retained evidence without network requests")
    for flag in ("baseline", "candidate", "policy", "out"):
        analysis.add_argument("--" + flag, required=True)
    analysis.add_argument("--baseline-grades")
    analysis.add_argument("--candidate-grades")
    prep = sub.add_parser("prepare", help="print selected-arm observation dependency contract, without network")
    prep.add_argument("--spec", required=True)
    prep.add_argument("--arm", choices=("baseline", "candidate"), required=True)
    export = sub.add_parser("export-ocl", help="export the existing synthetic OCL two-turn workload")
    export.add_argument("--out", required=True)
    export.add_argument("--seed", type=int, default=1729)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            result = run(args.spec, args.out)
        elif args.command == "analyze":
            result = analyze_receipts(args.baseline, args.candidate, args.policy, args.out,
                                      args.baseline_grades, args.candidate_grades)
        elif args.command == "observe":
            result = observe(args.spec, args.arm, args.out, args.observation_id)
            print(json.dumps({"status": result["status"], "run": str(Path(args.out) / "run.json"),
                              "inference_requests": result["inference_requests"], "observation_id": result["observation_id"]}))
            return 3 if result["status"] == "error" else 0
        elif args.command == "prepare":
            result = prepare(args.spec, args.arm)
            print(json.dumps({key: result[key] for key in ("identity", "observation_key", "dependencies", "protocol")}, indent=2))
            return 0
        else:
            export_ocl(args.out, args.seed)
            print(json.dumps({"workload": args.out, "source": "native OCL synthetic qualification fixture"}))
            return 0
        print(json.dumps({"verdict": result["verdict"], "exit_code": result["exit_code"], "reasons": result["reasons"]}))
        return result["exit_code"]
    except Exception as exc:
        print(json.dumps({"verdict": "error", "exit_code": 3, "reasons": [type(exc).__name__ + ": " + str(exc)[:1000]]}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
