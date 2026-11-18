#!/usr/bin/env python3
"""Source-bound task retries over the existing streamed observation/grading owners.

A task attempt is one complete conversation. Each HTTP step is separately
journaled before network dispatch. Interrupted starts are unknown and never replayed.
"""
from __future__ import annotations

import argparse
import copy
import functools
import json
import math
import os
import platform
import random
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from . import maintainer as owner
    from .common import (ROOT, _safe, _strict_loads, canonical, closure, digest, file_record, keys, load,
                         nonempty, now, number, policy as owner_policy,
                         prepare as owner_prepare, sha256_file, steps,
                         validate_closure, write)
    from .streaming import capture
except ImportError:
    import maintainer as owner
    from common import (ROOT, _safe, _strict_loads, canonical, closure, digest, file_record, keys, load,
                        nonempty, now, number, policy as owner_policy,
                        prepare as owner_prepare, sha256_file, steps,
                        validate_closure, write)
    from streaming import capture

SCHEMA = "cantos.maintainer.retry-campaign/1"
DEFAULTS = {"schema": "cantos.maintainer.retry-policy/1", "max_attempts": 1,
            "backoff_s": 0, "retry_on": ["rejected"], "attempt_seed_stride": 0}
LIMITATIONS = [
    "Task attempts restart the exact fixed conversation; no oracle feedback is added.",
    "Temperature remains zero. The predeclared seed schedule does not establish independent samples.",
    "Attempted HTTP dispatch is not proof of server-side inference or billed tokens after transport failure.",
    "Task elapsed time includes client queue, all attempts, backoff and application grading.",
    "Campaign time includes task execution/preparation/probes/grading; preflight, server startup and prior reservations are outside it.",
    "Power, energy and actual spending remain unknown unless joined to independently sourced resource evidence.",
    "A durable request start without a terminal receipt is unknown, never a zero-cost failure or an automatic replay."
]


def retry_policy(value):
    keys(value, DEFAULTS, "retry policy")
    p = {**DEFAULTS, **value}
    if p["schema"] != DEFAULTS["schema"]:
        raise ValueError("unsupported retry policy")
    number(p["max_attempts"], "max_attempts", 1, 100, True)
    number(p["backoff_s"], "backoff_s", 0, 600)
    number(p["attempt_seed_stride"], "attempt_seed_stride", 0, 1000000, True)
    if not isinstance(p["retry_on"], list) or len(set(p["retry_on"])) != len(p["retry_on"]):
        raise ValueError("retry_on must be a unique list")
    if any(x not in ("rejected", "transport_error") for x in p["retry_on"]):
        raise ValueError("retry_on permits rejected and transport_error only")
    return p


@functools.lru_cache(maxsize=1)
def _clock_identity():
    value = {"hostname": socket.gethostname(), "platform": platform.platform(),
             "clock": "time.monotonic_ns", "boot_id": None, "source": None}
    boot = Path("/proc/sys/kernel/random/boot_id")
    if boot.is_file():
        value.update(boot_id=boot.read_text().strip(), source="/proc/sys/kernel/random/boot_id")
    else:
        value.update(source="process-scoped clock identity; OS boot identity unavailable",
                     process_clock_id=str(uuid.uuid4()))
    return value


def clock_identity():
    return copy.deepcopy(_clock_identity())


timebase = clock_identity


def prepare(spec_path, arm, retry_policy_path, grader=None):
    p = owner_prepare(spec_path, arm)
    rp = retry_policy(load(retry_policy_path))
    if p["protocol"]["warmup"]:
        raise ValueError("retry campaigns require protocol.warmup=0; retain warmup as a separate run")
    if p["protocol"]["seed"] + (rp["max_attempts"]-1)*rp["attempt_seed_stride"] > 2147483647:
        raise ValueError("attempt seed schedule exceeds protocol seed bound")
    pol = owner_policy(load(p["policy_path"]) if p["policy_path"] else {})
    controls = {"acceptance": pol["acceptance"], "require_observed_model": pol["require_observed_model"],
                "require_observed_version": pol["require_observed_version"]}
    external = [c for c in p["workload"]["cases"] if steps(c)[-1]["expect"]["kind"] == "external"]
    grading = None
    if external:
        if not isinstance(grader, dict):
            raise ValueError("external cases require the source-bound EvalPlus adapter")
        keys(grader, {"kind", "reference", "normalizer", "docker", "timeout_s"}, "grader adapter")
        if grader.get("kind") != "evalplus":
            raise ValueError("only the existing isolated EvalPlus adapter is supported")
        if len(external) != len(p["workload"]["cases"]) or any("steps" in c for c in external):
            raise ValueError("EvalPlus retry campaigns require single-step external cases")
        identities = [c["expect"]["grader"] for c in external]
        g = identities[0]
        if any(x != g for x in identities):
            raise ValueError("external cases must share one pinned grader")
        if (g["name"], g["revision"], g.get("criterion")) != (
                "EvalPlus", "0.3.1", "humanevalplus-v0.1.10-base-and-plus-chat-complete-code-v1"):
            raise ValueError("unsupported EvalPlus grading contract")
        ref = Path(grader["reference"]).resolve()
        norm = Path(grader["normalizer"]).resolve()
        if sha256_file(ref) != g["reference_sha256"] or sha256_file(norm) != g.get("normalizer_sha256"):
            raise ValueError("external reference or normalizer differs from workload pin")
        rows = [json.loads(s) for s in ref.read_text().splitlines() if s.strip()]
        ids = [x["task_id"] for x in rows]
        if len(set(ids)) != len(ids) or set(ids) != {c["id"] for c in external}:
            raise ValueError("parent reference cases must equal parent workload cases")
        timeout = number(grader.get("timeout_s", 600), "grader timeout", 1, 7200)
        grading = {"kind": "evalplus", "reference_sha256": sha256_file(ref),
                   "normalizer_sha256": sha256_file(norm), "grader": g,
                   "docker": grader.get("docker", "docker"), "timeout_s": timeout,
                   "reference": str(ref), "normalizer": str(norm)}
        nonempty(grading["docker"], "docker executable")
        p["dependencies"] += [str(ref), str(norm)]
    elif grader is not None:
        raise ValueError("a grader adapter is only valid for external workloads")
    public_grading = None if grading is None else {k:v for k,v in grading.items() if k not in ("reference", "normalizer")}
    identity = {"owner_observation_identity": p["identity"], "retry_policy": rp,
                "acceptance_controls": controls, "grader_adapter": public_grading}
    return {"schema": "cantos.maintainer.retry-plan/1", "arm": arm,
            "observation_key": digest(identity), "identity": identity,
            "prepared": p, "retry_policy": rp, "acceptance_controls": controls,
            "grading": grading, "dependencies": sorted(set(p["dependencies"]+[str(Path(retry_policy_path).resolve())]))}


class Journal:
    def __init__(self, path):
        self.f = Path(path).open("x", encoding="utf-8")
        self.lock = threading.Lock()
        self.seq = 0

    def event(self, kind, **fields):
        with self.lock:
            self.seq += 1
            item = {"seq": self.seq, "event": kind, "monotonic_ns": time.monotonic_ns(),
                    "observed_at": now(), **fields}
            self.f.write(canonical(item).decode()+"\n")
            self.f.flush()
            os.fsync(self.f.fileno())
            return item

    def close(self):
        self.f.close()


class JournalObserver(owner.Observer):
    """The existing one-attempt receipt, with durable HTTP dispatch events."""
    def __init__(self, prepared, out_dir, observation_id, journal, task_instance, attempt_number):
        self.campaign_journal = journal
        self.task_instance = task_instance
        self.attempt_number = attempt_number
        super().__init__(prepared, out_dir, observation_id)

    def one(self, case_index, trial, repetition, warmup=False):
        case = self.p["workload"]["cases"][case_index]
        start = time.monotonic()
        attempts, answers, checks, messages = [], [], [], []
        final_error = None
        for i, step in enumerate(steps(case)):
            messages.extend(copy.deepcopy(step["messages"]))
            request_id = self.task_instance + "/attempt-" + str(self.attempt_number) + "/step-" + str(i)
            self.campaign_journal.event("request_start", request_id=request_id,
                task_instance=self.task_instance, attempt=self.attempt_number, step=i)
            raw, attempt = capture(self.p["configuration"], self.p["protocol"], copy.deepcopy(messages), "step_"+str(i))
            rel = f"raw/trial/{trial:03d}-{repetition:03d}-{case_index:06d}-{i:02d}.json"
            write(self.root/rel, raw)
            attempt["raw_path"] = rel
            self.campaign_journal.event("request_terminal", request_id=request_id,
                task_instance=self.task_instance, attempt=self.attempt_number, step=i,
                transport_error=attempt["transport_error"], stream_error=attempt["stream_error"],
                raw_sha256=sha256_file(self.root/rel))
            attempts.append(attempt)
            ok, actual, err = owner.grade_text(step["expect"], attempt)
            checks.append(ok); answers.append(actual); final_error = err
            if ok is False:
                break
            messages.append({"role": "assistant", "content": attempt["response_text"]})
        end = time.monotonic()
        accepted = False if False in checks else (None if None in checks else True)
        return {"task_id": case["id"], "case_index": case_index, "trial": trial,
                "repetition": repetition, "warmup": warmup, "accepted": accepted,
                "error": final_error, "duration_s": end-start, "started_monotonic_s": start,
                "ended_monotonic_s": end, "step_checks": checks, "actual": answers,
                "attempts": attempts, "evaluator_version": "ocl.exact-json/1+cantos.stream/1"}


def _child_inputs(root, parent, case_index, attempt_number):
    p, rp = parent["prepared"], parent["retry_policy"]
    case = copy.deepcopy(p["workload"]["cases"][case_index])
    work = {**copy.deepcopy(p["workload"]), "cases": [case]}
    inputs = root/"inputs"
    inputs.mkdir(parents=True, exist_ok=False)
    if parent["grading"]:
        rows = [json.loads(s) for s in (root.parents[2]/"reference.jsonl").read_text().splitlines() if s.strip()]
        row = next(r for r in rows if r["task_id"] == case["id"])
        (inputs/"reference.jsonl").write_bytes(canonical(row)+b"\n")
        case["expect"]["grader"]["reference_sha256"] = sha256_file(inputs/"reference.jsonl")
    write(inputs/"workload.json", work)
    proto = {**p["protocol"], "trials": 1, "repeats": 1, "concurrency": 1, "warmup": 0,
             "seed": p["protocol"]["seed"]+(attempt_number-1)*rp["attempt_seed_stride"]}
    config = copy.deepcopy(p["configuration"])
    # Implementation input bytes remain bound by the parent plan. Avoid resolving
    # their original relative paths against this derived immutable input folder.
    config.pop("implementation_files", None)
    spec = {"schema": "cantos.maintainer.spec/1", "workload": "workload.json",
            "protocol": proto, "baseline": config, "candidate": config}
    write(inputs/"spec.json", spec)
    child = owner_prepare(inputs/"spec.json", p["arm"])
    if child["identity"]["producer_files"] != p["identity"]["producer_files"]:
        raise ValueError("measurement source changed during campaign")
    return child


def _preflight_grader(grading):
    if grading is None:
        return None
    if os.name != "posix":
        raise ValueError("the existing isolated EvalPlus container owner requires POSIX")
    image = "sha256:"+grading["grader"]["artifact_sha256"]
    r = subprocess.run([grading["docker"], "image", "inspect", image], capture_output=True, text=True,
                       timeout=min(grading["timeout_s"], 30), check=True)
    images = json.loads(r.stdout)
    if len(images) != 1 or images[0].get("Id") != image:
        raise ValueError("actual local grader image differs from workload pin")
    return images


def _grade_evalplus(root, run_path, parent, images):
    """Reuse prepare/container/bind; generated solutions execute only in Docker."""
    grading = parent["grading"]
    prepared = root/"evalplus-prepared"
    common = [sys.executable, "-B", str(ROOT/"evalplus_bridge.py")]
    prep = common+["prepare", "--run", str(run_path), "--instrument", str(ROOT),
                   "--reference", str(root/"inputs/reference.jsonl"),
                   "--normalizer", str(root.parents[2]/"normalize.py"), "--out", str(prepared)]
    r = subprocess.run(prep, capture_output=True, text=True, timeout=grading["timeout_s"])
    write(root/"evalplus-prepare-invocation.json", {"argv": prep, "exit_code": r.returncode,
          "stdout": r.stdout, "stderr": r.stderr})
    if r.returncode:
        raise RuntimeError("source-bound EvalPlus preparation failed")
    write(prepared/"grader-image.json", images)
    container = "cantos-retry-"+uuid.uuid4().hex
    image = "sha256:"+grading["grader"]["artifact_sha256"]
    command = ('python -c \'import importlib.metadata as m; assert m.version("evalplus")=="0.3.1"\'; '
               'evalplus.evaluate --dataset humaneval --samples humaneval.jsonl '
               '--parallel 1 --min-time-limit 1 --gt-time-limit-factor 4')
    argv = [grading["docker"], "run", "--pull", "never", "--rm", "--name", container, "--network", "none",
            "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "128", "--memory", "4g", "--cpus", "1",
            "--user", str(os.getuid())+":"+str(os.getgid()),
            "--tmpfs", "/tmp:rw,exec,size=1g", "-e", "HOME=/tmp", "-e", "XDG_CACHE_HOME=/tmp/cache",
            "-e", "HUMANEVAL_OVERRIDE_PATH=/work/humaneval-reference.jsonl",
            "-v", str(prepared)+":/work", "-w", "/work", "--entrypoint", "/bin/sh", image, "-ec", command]
    started = time.monotonic_ns()
    status, code = "started", None
    try:
        with (prepared/"evalplus.log").open("xb") as log:
            result = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=grading["timeout_s"])
        code, status = result.returncode, "completed"
    except subprocess.TimeoutExpired:
        status = "timeout"
    finally:
        cleanup = subprocess.run([grading["docker"], "stop", "-t", "5", container],
                                 capture_output=True, text=True, timeout=15)
        write(prepared/"invocation.json", {"argv": argv, "status": status, "exit_code": code,
              "started_monotonic_ns": started, "ended_monotonic_ns": time.monotonic_ns(),
              "cleanup_exit": cleanup.returncode, "image": image,
              "authority": "owned digest-pinned local network-isolated EvalPlus execution"})
    if status != "completed" or code != 0:
        raise RuntimeError("independent EvalPlus invocation failed")
    output = root/"grades"
    argv = common+["bind", "--run", str(run_path), "--instrument", str(ROOT),
                   "--prepared", str(prepared), "--results", str(prepared/"humaneval_eval_results.json"),
                   "--log", str(prepared/"evalplus.log"), "--out", str(output)]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=grading["timeout_s"])
    write(root/"evalplus-bind-invocation.json", {"argv": argv, "exit_code": r.returncode,
          "stdout": r.stdout, "stderr": r.stderr})
    if r.returncode:
        raise RuntimeError("source-bound EvalPlus binding failed")
    owner.validate_grades(output/"grades.json", run_path)
    return output/"grades.json"


def _verdict(run, work, controls, grades, elapsed):
    pol = owner_policy({**controls})
    projected, pending = owner._graded(run, work, pol, grades)
    issues = owner._identity_problems(run, pol, run["arm"])
    obs = projected["observations"][0]
    transport = any(a["error"] for a in run["observations"][0]["attempts"])
    if transport:
        return "transport_error", False, [a["error"] for a in run["observations"][0]["attempts"] if a["error"]]
    if issues or pending:
        return "unresolved", None, issues+["external grade missing"]*bool(pending)
    limit = controls["acceptance"]["max_latency_s"]
    if limit is not None and elapsed > limit:
        return "rejected", False, ["total task latency requirement exceeded"]
    return ("accepted", True, []) if obs["accepted"] else ("rejected", False, [obs["error"]])


def metrics(tasks, campaign_duration_s, request_starts):
    successes = [t for t in tasks if t["accepted"] is True]
    first = sum(t["accepted"] is True and len(t["attempts"]) == 1 for t in tasks)
    attempts = sum(len(t["attempts"]) for t in tasks)
    retries = sum(max(0, len(t["attempts"])-1) for t in tasks)
    success_retries = sum(len(t["attempts"])-1 for t in successes)
    accepted = len(successes)
    return {"offered_tasks": len(tasks), "accepted_tasks": accepted,
            "first_pass_successes": first, "first_pass_success_rate": first/len(tasks) if tasks else None,
            "total_task_attempts": attempts, "retries_total": retries,
            "retries_per_accepted_task": retries/accepted if accepted else None,
            "retries_among_successes": success_retries,
            "mean_retries_among_successes": success_retries/accepted if accepted else None,
            "total_http_requests": request_starts,
            "transport_failed_task_attempts": sum(a["verdict"] == "transport_error" for t in tasks for a in t["attempts"]),
            "unresolved_tasks": sum(t["accepted"] is None for t in tasks),
            "exhausted_tasks": sum(t["accepted"] is False for t in tasks),
            "campaign_duration_s": campaign_duration_s,
            "accepted_tasks_per_s": accepted/campaign_duration_s if campaign_duration_s > 0 else None,
            "sum_task_elapsed_s": sum(t["duration_s"] for t in tasks),
            "energy_joules": None, "joules_per_accepted_task": None, "actual_cost": None}


def run(spec_path, arm, retry_policy_path, out_dir, observation_id, grader=None):
    p = prepare(spec_path, arm, retry_policy_path, grader)
    images = _preflight_grader(p["grading"])
    nonempty(observation_id, "observation_id")
    root = Path(out_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    start_ns, started_at = time.monotonic_ns(), now()
    clock = timebase()
    write(root/"plan.json", {"schema": p["schema"], "observation_id": observation_id,
          "observation_key": p["observation_key"], "identity": p["identity"],
          "arm": arm, "started_monotonic_ns": start_ns, "started_at": started_at, "timebase": clock})
    shutil.copyfile(p["prepared"]["workload_path"], root/"workload.json")
    if p["grading"]:
        shutil.copyfile(p["grading"]["reference"], root/"reference.jsonl")
        shutil.copyfile(p["grading"]["normalizer"], root/"normalize.py")
        write(root/"grader-image.json", images)
        if sha256_file(root/"reference.jsonl") != p["grading"]["reference_sha256"] or sha256_file(root/"normalize.py") != p["grading"]["normalizer_sha256"]:
            raise ValueError("external inputs changed during preflight/copy")
    journal = Journal(root/"events.jsonl")
    journal.event("campaign_start", observation_id=observation_id)
    tasks = []

    def one(case_index, trial, repetition, submitted):
        case = p["prepared"]["workload"]["cases"][case_index]
        instance = f"t{trial:03d}-r{repetition:03d}-c{case_index:06d}"
        task_start = journal.event("task_start", task_instance=instance)
        record = {"task_instance": instance, "task_id": case["id"], "case_index": case_index,
                  "trial": trial, "repetition": repetition, "submitted_monotonic_ns": submitted,
                  "started_monotonic_ns": task_start["monotonic_ns"], "attempts": [], "accepted": False}
        for n in range(1, p["retry_policy"]["max_attempts"]+1):
            if n > 1 and p["retry_policy"]["backoff_s"]:
                backoff_s = p["retry_policy"]["backoff_s"]
                begun = journal.event("backoff_start", task_instance=instance, attempt=n, seconds=backoff_s)
                deadline_ns = begun["monotonic_ns"] + math.ceil(backoff_s * 1_000_000_000)
                # The recorded interval, not the requested sleep, must satisfy
                # the policy: Windows timers can return before the deadline.
                while (remaining_ns := deadline_ns - time.monotonic_ns()) > 0:
                    time.sleep(remaining_ns / 1_000_000_000)
                journal.event("backoff_end", task_instance=instance, attempt=n)
            event = journal.event("task_attempt_start", task_instance=instance, attempt=n)
            attempt_root = root/"attempts"/instance/f"attempt-{n:03d}"
            attempt_root.mkdir(parents=True, exist_ok=False)
            a = {"attempt": n, "started_monotonic_ns": event["monotonic_ns"], "run": None, "grades": None}
            try:
                child = _child_inputs(attempt_root, p, case_index, n)
                observer = JournalObserver(child, attempt_root/"capture", observation_id+"/"+instance+"/"+str(n), journal, instance, n)
                observer.trial(0)
                observer.finish()
                run_path = attempt_root/"capture/run.json"
                captured = owner.validate_receipt(run_path)
                a["run"] = file_record(run_path, root)
                grade_path = None
                if p["grading"] and captured["observations"][0]["accepted"] is None:
                    journal.event("grading_start", task_instance=instance, attempt=n)
                    grade_path = _grade_evalplus(attempt_root, run_path, p, images)
                    journal.event("grading_end", task_instance=instance, attempt=n, grades_sha256=sha256_file(grade_path))
                    a["grades"] = file_record(grade_path, root)
                grades = owner.validate_grades(grade_path, run_path) if grade_path else None
                a["evaluated_monotonic_ns"] = time.monotonic_ns()
                elapsed = (a["evaluated_monotonic_ns"]-submitted)/1e9
                state, accepted, reasons = _verdict(captured, load(run_path.parent/"workload.json"),
                                                  p["acceptance_controls"], grades, elapsed)
                a.update(verdict=state, accepted=accepted, reasons=reasons)
            except Exception as exc:
                a.update(verdict="unresolved", accepted=None, reasons=[type(exc).__name__+": "+str(exc)[:300]])
            terminal = journal.event("task_attempt_terminal", task_instance=instance, attempt=n,
                                     verdict=a["verdict"], accepted=a["accepted"])
            a["ended_monotonic_ns"] = terminal["monotonic_ns"]
            a["duration_s"] = (a["ended_monotonic_ns"]-a["started_monotonic_ns"])/1e9
            record["attempts"].append(a)
            record["accepted"] = a["accepted"]
            if a["accepted"] is True or a["verdict"] not in p["retry_policy"]["retry_on"]:
                break
        terminal = journal.event("task_terminal", task_instance=instance, accepted=record["accepted"])
        record["ended_monotonic_ns"] = terminal["monotonic_ns"]
        record["duration_s"] = (record["ended_monotonic_ns"]-submitted)/1e9
        record["queue_duration_s"] = (record["started_monotonic_ns"]-submitted)/1e9
        return record

    try:
        proto = p["prepared"]["protocol"]
        for trial in range(proto["trials"]):
            work = [(i,r) for r in range(proto["repeats"]) for i in range(len(p["prepared"]["workload"]["cases"]))]
            random.Random(proto["seed"]+trial).shuffle(work)
            with ThreadPoolExecutor(max_workers=proto["concurrency"]) as pool:
                futures = []
                for i,r in work:
                    instance = f"t{trial:03d}-r{r:03d}-c{i:06d}"
                    e = journal.event("task_submit", task_instance=instance)
                    futures.append(pool.submit(one, i, trial, r, e["monotonic_ns"]))
                for future in as_completed(futures):
                    tasks.append(future.result())
        terminal = journal.event("campaign_terminal", observation_id=observation_id)
    finally:
        journal.close()
    end_ns, ended_at = terminal["monotonic_ns"], terminal["observed_at"]
    tasks.sort(key=lambda t:(t["trial"],t["repetition"],t["case_index"]))
    events = [load_json_line(s) for s in (root/"events.jsonl").read_text().splitlines()]
    pending = inspect_journal(root)["unknown_request_ids"]
    status = "incomplete" if pending else ("unresolved" if any(t["accepted"] is None for t in tasks) else "complete")
    value = {"schema": SCHEMA, "status": status, "observation_id": observation_id,
             "observation_key": p["observation_key"], "arm": arm, "timebase": clock, "clock_identity": clock,
             "started_monotonic_s": start_ns/1e9, "ended_monotonic_s": end_ns/1e9,
             "started_at": started_at, "ended_at": ended_at, "started_monotonic_ns": start_ns,
             "ended_monotonic_ns": end_ns, "campaign_duration_s": (end_ns-start_ns)/1e9,
             "tasks": tasks, "metrics": metrics(tasks, (end_ns-start_ns)/1e9, sum(e["event"]=="request_start" for e in events)),
             "unknown_request_ids": pending, "limitations": LIMITATIONS,
             "artifacts": closure(root, exclude=("retry-campaign.json",))}
    write(root/"retry-campaign.json", value)
    validate_campaign(root/"retry-campaign.json")
    return value


def load_json_line(line):
    return _strict_loads(line)


def inspect_journal(path):
    root = Path(path)
    if root.is_file():
        root = root.parent
    events = []
    partial_tail = False
    raw = (root/"events.jsonl").read_bytes()
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            partial_tail = True
            break
        events.append(load_json_line(line.decode()))
    starts, ends = {}, {}
    last = -1
    for i, e in enumerate(events,1):
        if e["seq"] != i or e["monotonic_ns"] < last:
            raise ValueError("journal sequence/time mismatch")
        last = e["monotonic_ns"]
        if e["event"] in ("request_start", "request_terminal"):
            target = starts if e["event"] == "request_start" else ends
            if e["request_id"] in target:
                raise ValueError("duplicate request event")
            target[e["request_id"]] = e
    if not set(ends) <= set(starts):
        raise ValueError("request terminal lacks durable start")
    for rid in ends:
        if ends[rid]["seq"] < starts[rid]["seq"]:
            raise ValueError("request ended before it started")
    pending = sorted(set(starts)-set(ends))
    return {"status": "incomplete" if pending or partial_tail or not events or events[-1]["event"]!="campaign_terminal" else "journal_complete",
            "attempted_http_requests": len(starts), "terminal_http_requests": len(ends),
            "unknown_request_ids": pending, "partial_journal_tail": partial_tail,
            "automatic_replay_authorized": False}


def validate_campaign(path):
    path = Path(path).resolve()
    if path.is_dir():
        path = path/"retry-campaign.json"
    value = validate_closure(path)
    if value.get("schema") != SCHEMA:
        raise ValueError("unsupported retry campaign")
    root = path.parent
    artifact_map = {a["path"]: a for a in value["artifacts"]}
    plan = load(root/"plan.json")
    identity = plan["identity"]
    if plan["observation_key"] != digest(identity) or value["observation_key"] != plan["observation_key"]:
        raise ValueError("campaign observation identity mismatch")
    if any(value[k] != plan[k] for k in ("observation_id","arm","timebase","started_at","started_monotonic_ns")):
        raise ValueError("campaign differs from its durable start")
    check = inspect_journal(root)
    if check["status"] != "journal_complete" or value["unknown_request_ids"]:
        raise ValueError("unknown/incomplete request dispatch remains; no automatic replay")
    events = [load_json_line(s) for s in (root/"events.jsonl").read_text().splitlines()]
    if value["ended_monotonic_ns"] != events[-1]["monotonic_ns"] or value["ended_at"] != events[-1]["observed_at"]:
        raise ValueError("campaign end differs from journal")
    if value["clock_identity"] != value["timebase"] or value["started_monotonic_s"] != value["started_monotonic_ns"]/1e9 or value["ended_monotonic_s"] != value["ended_monotonic_ns"]/1e9:
        raise ValueError("clock identity or second/ns timestamp alias mismatch")
    duration = (value["ended_monotonic_ns"]-value["started_monotonic_ns"])/1e9
    if duration <= 0 or value["campaign_duration_s"] != duration:
        raise ValueError("campaign timing mismatch")
    workload = load(root/"workload.json")
    if sha256_file(root/"workload.json") != identity["owner_observation_identity"]["workload_sha256"]:
        raise ValueError("parent workload changed")
    if identity["grader_adapter"]:
        if sha256_file(root/"reference.jsonl") != identity["grader_adapter"]["reference_sha256"] or sha256_file(root/"normalize.py") != identity["grader_adapter"]["normalizer_sha256"]:
            raise ValueError("parent grading source differs from original pin")
    rp = retry_policy(identity["retry_policy"])
    proto = identity["owner_observation_identity"]["protocol"]
    expected = {(i,t,r) for i in range(len(workload["cases"])) for t in range(proto["trials"]) for r in range(proto["repeats"])}
    seen, raw_hashes = set(), []
    event_map = {}
    for e in events:
        key = (e["event"],e.get("task_instance"),e.get("attempt"))
        event_map.setdefault(key,[]).append(e)
    def event(kind, tid, attempt=None):
        rows = event_map.get((kind,tid,attempt),[])
        if len(rows)!=1:
            raise ValueError("missing/duplicate "+kind)
        return rows[0]
    for task in value["tasks"]:
        key = (task["case_index"],task["trial"],task["repetition"])
        if key in seen or key not in expected:
            raise ValueError("duplicate or unexpected task instance")
        seen.add(key)
        case = workload["cases"][key[0]]
        tid = f"t{key[1]:03d}-r{key[2]:03d}-c{key[0]:06d}"
        if task["task_instance"] != tid or task["task_id"] != case["id"]:
            raise ValueError("task identity mismatch")
        for field, kind in (("submitted_monotonic_ns","task_submit"),("started_monotonic_ns","task_start"),("ended_monotonic_ns","task_terminal")):
            if task[field] != event(kind,tid)["monotonic_ns"]:
                raise ValueError("task timestamp differs from journal")
        if not value["started_monotonic_ns"] <= task["submitted_monotonic_ns"] <= task["started_monotonic_ns"] <= task["ended_monotonic_ns"] <= value["ended_monotonic_ns"]:
            raise ValueError("task interval outside campaign")
        if task["duration_s"] != (task["ended_monotonic_ns"]-task["submitted_monotonic_ns"])/1e9 or task["queue_duration_s"] != (task["started_monotonic_ns"]-task["submitted_monotonic_ns"])/1e9:
            raise ValueError("task elapsed/queue duration mismatch")
        if not 1 <= len(task["attempts"]) <= rp["max_attempts"]:
            raise ValueError("attempt bound violated")
        for n, attempt in enumerate(task["attempts"],1):
            if attempt["attempt"] != n:
                raise ValueError("attempt sequence mismatch")
            if n>1 and task["attempts"][n-2]["verdict"] not in rp["retry_on"]:
                raise ValueError("attempt continued after success or non-retryable result")
            started = event("task_attempt_start",tid,n)
            terminal = event("task_attempt_terminal",tid,n)
            if attempt["started_monotonic_ns"] != started["monotonic_ns"] or attempt["ended_monotonic_ns"] != terminal["monotonic_ns"]:
                raise ValueError("attempt timestamps differ from journal")
            if n > 1:
                previous_end = task["attempts"][n-2]["ended_monotonic_ns"]
                if started["monotonic_ns"] < previous_end:
                    raise ValueError("retry overlaps previous attempt")
                if rp["backoff_s"]:
                    bs, be = event("backoff_start",tid,n), event("backoff_end",tid,n)
                    if not previous_end <= bs["monotonic_ns"] <= be["monotonic_ns"] <= started["monotonic_ns"] or (be["monotonic_ns"]-bs["monotonic_ns"])/1e9 < rp["backoff_s"]:
                        raise ValueError("retry backoff differs from pinned policy")
            if attempt["duration_s"] != (terminal["monotonic_ns"]-started["monotonic_ns"])/1e9:
                raise ValueError("attempt elapsed mismatch")
            if attempt["accepted"] != terminal["accepted"] or attempt["verdict"] != terminal["verdict"]:
                raise ValueError("attempt outcome differs from journal")
            if not task["started_monotonic_ns"] <= started["monotonic_ns"] <= terminal["monotonic_ns"] <= task["ended_monotonic_ns"]:
                raise ValueError("attempt outside task")
            if attempt["run"] is None:
                if attempt["accepted"] is not None or attempt["verdict"]!="unresolved":
                    raise ValueError("missing capture cannot establish task outcome")
                continue
            record = attempt["run"]
            run_path = _safe(root,record["path"])
            if artifact_map.get(record["path"]) != record or file_record(run_path,root)!=record:
                raise ValueError("child run binding mismatch")
            run_value = owner.validate_receipt(run_path)
            child_work = load(run_path.parent/"workload.json")
            want_case = copy.deepcopy(case)
            if identity["grader_adapter"]:
                reference = run_path.parent.parent/"inputs/reference.jsonl"
                full_rows = [json.loads(s) for s in (root/"reference.jsonl").read_text().splitlines() if s.strip()]
                want_row = next(x for x in full_rows if x["task_id"]==case["id"])
                if reference.read_bytes()!=canonical(want_row)+b"\n":
                    raise ValueError("child reference differs from exact parent subset")
                want_case["expect"]["grader"]["reference_sha256"]=sha256_file(reference)
            if child_work != {**workload,"cases":[want_case]}:
                raise ValueError("child workload differs from parent case")
            want_protocol = {**proto,"trials":1,"repeats":1,"concurrency":1,"warmup":0,
                             "seed":proto["seed"]+(n-1)*rp["attempt_seed_stride"]}
            if run_value["protocol"] != want_protocol:
                raise ValueError("child request protocol/seed differs")
            want_config = copy.deepcopy(identity["owner_observation_identity"]["configuration"])
            want_config.pop("implementation_files",None)
            if run_value["producer_files"] != identity["owner_observation_identity"]["producer_files"]:
                raise ValueError("child producer source differs from campaign")
            if run_value["configuration"] != want_config:
                raise ValueError("child serving identity differs")
            grades = None
            if attempt["grades"]:
                gp = _safe(root,attempt["grades"]["path"])
                if artifact_map.get(attempt["grades"]["path"]) != attempt["grades"] or file_record(gp,root)!=attempt["grades"]:
                    raise ValueError("grade binding mismatch")
                grades = owner.validate_grades(gp,run_path)
            evaluation = attempt.get("evaluated_monotonic_ns", attempt["ended_monotonic_ns"])
            if not attempt["started_monotonic_ns"] <= evaluation <= attempt["ended_monotonic_ns"]:
                raise ValueError("evaluation outside attempt interval")
            elapsed=(evaluation-task["submitted_monotonic_ns"])/1e9
            state, accepted, reasons = _verdict(run_value,child_work,identity["acceptance_controls"],grades,elapsed)
            # Infrastructure grading failure remains unresolved with no invented grade.
            if attempt["verdict"]=="unresolved" and attempt["grades"] is None and run_value["observations"][0]["accepted"] is None:
                accepted, state = None,"unresolved"
            if (state,accepted)!=(attempt["verdict"],attempt["accepted"]):
                raise ValueError("stored retry outcome differs from source-bound grading")
            for i,a in enumerate(run_value["observations"][0]["attempts"]):
                rid=tid+"/attempt-"+str(n)+"/step-"+str(i)
                starts=[e for e in events if e["event"]=="request_start" and e["request_id"]==rid]
                ends=[e for e in events if e["event"]=="request_terminal" and e["request_id"]==rid]
                raw=run_path.parent/a["raw_path"]
                if len(starts)!=1 or len(ends)!=1 or ends[0]["raw_sha256"]!=sha256_file(raw):
                    raise ValueError("request dispatch does not bind exact raw evidence")
                if starts[0]["monotonic_ns"]/1e9>a["started_monotonic_s"] or ends[0]["monotonic_ns"]/1e9<a["ended_monotonic_s"]:
                    raise ValueError("request raw interval outside journaled dispatch")
                raw_hashes.append(rid)
        if task["accepted"]!=task["attempts"][-1]["accepted"] or task["accepted"]!=event("task_terminal",tid)["accepted"]:
            raise ValueError("task terminal differs from final attempt")
    if seen!=expected:
        raise ValueError("offered tasks missing from complete campaign")
    if len(raw_hashes)!=check["attempted_http_requests"]:
        raise ValueError("journaled HTTP attempt lacks bound raw receipt")
    calculated=metrics(value["tasks"],duration,check["attempted_http_requests"])
    if calculated!=value["metrics"]:
        raise ValueError("campaign summary differs from all-attempt accounting")
    expected_status = "unresolved" if any(t["accepted"] is None for t in value["tasks"]) else "complete"
    if value["status"] != expected_status:
        raise ValueError("campaign terminal status differs from task outcomes")
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    for name in ("prepare","run"):
        q=sub.add_parser(name)
        for field in ("spec","arm","retry-policy"): q.add_argument("--"+field,required=True)
        q.add_argument("--evalplus-reference"); q.add_argument("--evalplus-normalizer")
        q.add_argument("--docker",default="docker"); q.add_argument("--grader-timeout-s",type=float,default=600)
        if name=="run":
            q.add_argument("--out",required=True); q.add_argument("--observation-id",required=True)
    sub.add_parser("validate").add_argument("--path",required=True)
    sub.add_parser("inspect").add_argument("--path",required=True)
    a=p.parse_args()
    try:
        if a.command=="inspect":
            result=inspect_journal(a.path); code=0 if result["status"]=="journal_complete" else 2
        elif a.command=="validate":
            result=validate_campaign(a.path); code=0 if result["status"]=="complete" else 2
        else:
            grader=None
            if a.evalplus_reference or a.evalplus_normalizer:
                if not a.evalplus_reference or not a.evalplus_normalizer:
                    raise ValueError("both EvalPlus reference and normalizer paths are required")
                grader={"kind":"evalplus","reference":a.evalplus_reference,"normalizer":a.evalplus_normalizer,
                        "docker":a.docker,"timeout_s":a.grader_timeout_s}
            if a.command=="prepare":
                result=prepare(a.spec,a.arm,a.retry_policy,grader); result.pop("prepared"); code=0
            else:
                result=run(a.spec,a.arm,a.retry_policy,a.out,a.observation_id,grader)
                code=0 if result["status"]=="complete" else 2
        print(json.dumps(result,sort_keys=True,allow_nan=False))
        return code
    except Exception as exc:
        print(json.dumps({"status":"error","error":type(exc).__name__+": "+str(exc)[:1000]}))
        return 3

if __name__=="__main__":
    raise SystemExit(main())
