"""Source-bound captured-text grading; only explicit run starts a sandbox.

prepare/bind execute no supplied code. run invokes one locally present digest-
pinned Docker image, with fixed mounts/limits and bounded stdout/stderr.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

try:
    from . import maintainer
    from .common import ROOT, canonical, closure, load, protocol, read_grading_contract, sha256_file, steps, write, _safe
except ImportError:
    import maintainer
    from common import ROOT, canonical, closure, load, protocol, read_grading_contract, sha256_file, steps, write, _safe

MAX_INPUT = 64 * 1024 * 1024
MAX_OUTPUT = 16 * 1024 * 1024
MAX_LOG = 256 * 1024
VALIDATOR_FILES = ("maintainer.py", "common.py", "streaming.py", "owner_ocl/core.py", "owner_ocl/runner.py",
                   "owner_ocl/tasks.py", "owner_ocl/compare.py", "owner_vllm/audit.py")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _validator_files():
    return {name: sha256_file(ROOT / name) for name in VALIDATOR_FILES}


def _bounded_file(path, limit=MAX_INPUT):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Expected a bounded regular file: " + str(path))
    return path.read_bytes()


def _checked_run(run_path, grading_contract=None):
    path = Path(run_path).resolve()
    preflight = load(path)
    work = load(path.parent / "workload.json")
    proto = protocol(preflight.get("protocol", {}))
    cases, observations = work.get("cases"), preflight.get("observations")
    if not isinstance(cases, list) or not isinstance(observations, list):
        raise ValueError("Workload cases and observations are required")
    count = len(cases) * proto["trials"] * proto["repeats"]
    if not 1 <= count <= 100000 or count != len(observations):
        raise ValueError("External grading observation cardinality mismatch or limit")
    run = maintainer.validate_receipt(path)
    cases = {case["id"]: case for case in work["cases"]}
    external = {key: case for key, case in cases.items() if steps(case)[-1]["expect"]["kind"] == "external"}
    if not external:
        raise ValueError("No externally graded application cases are present")
    graders = [steps(case)[-1]["expect"]["grader"] for case in external.values()]
    if any(g != graders[0] for g in graders):
        raise ValueError("One exact grader identity is required per adapter invocation")
    grader, contract_sha = graders[0], None
    if grading_contract is not None:
        contract, contract_sha = read_grading_contract(grading_contract)
        if contract["workload_sha256"] != run["workload_sha256"]:
            raise ValueError("Selected grading contract belongs to another captured workload")
        grader = contract["grader"]
    if not isinstance(grader.get("criterion"), str) or not grader["criterion"].strip():
        raise ValueError("Generic external grader requires an explicit acceptance criterion")
    return path, run, external, copy.deepcopy(grader), contract_sha


def _transcript(path, run, cases, grader, reference_sha, normalizer_sha):
    rows = []
    for observation in run["observations"]:
        if observation["task_id"] not in cases:
            continue
        case = cases[observation["task_id"]]
        trajectory = {"case": case, "steps": [], "capture_eligible": observation["accepted"] is None}
        for index, attempt in enumerate(observation["attempts"]):
            trajectory["steps"].append({
                "step": index, "request": copy.deepcopy(attempt["request"]),
                "response_text": attempt["response_text"], "response_sha256": attempt["response_sha256"],
                "error": attempt.get("error"), "finish_reason": attempt.get("finish_reason"),
                "raw_sha256": sha256_file(_safe(path.parent, attempt["raw_path"]))})
        last = observation["attempts"][-1]
        rows.append({"task_id": observation["task_id"], "trial": observation["trial"], "repetition": observation["repetition"],
                     "response_sha256": last["response_sha256"], "trajectory_sha256": _sha(canonical(trajectory)),
                     "trajectory": trajectory})
    return {"schema": "cantos.external-transcript/1", "run_sha256": sha256_file(path),
            "workload_sha256": run["workload_sha256"], "grader": grader, "reference_sha256": reference_sha,
            "normalizer_sha256": normalizer_sha, "observations": rows,
            "scope": "Captured text and multi-step text conversations only; no structured tool-call execution or newly generated application work."}


def prepare(run_path, reference_path, out_dir, normalizer_path=None, grading_contract=None):
    path, run, cases, grader, contract_sha = _checked_run(run_path, grading_contract)
    reference = _bounded_file(reference_path)
    if _sha(reference) != grader["reference_sha256"]:
        raise ValueError("Reference bytes differ from the pinned grader identity")
    normalizer = None
    if "normalizer_sha256" in grader:
        if normalizer_path is None:
            raise ValueError("Supply the pinned normalizer as data; it is never executed on the host")
        normalizer = _bounded_file(normalizer_path)
        if _sha(normalizer) != grader["normalizer_sha256"]:
            raise ValueError("Normalizer bytes differ from the pinned grader identity")
    elif normalizer_path is not None:
        raise ValueError("Unpinned normalizer is not permitted")
    transcript = _transcript(path, run, cases, grader, _sha(reference), _sha(normalizer) if normalizer is not None else None)
    root = Path(out_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    inputs = root / "input"
    inputs.mkdir()
    write(inputs / "transcript.json", transcript)
    (inputs / "reference.bin").write_bytes(reference)
    if normalizer is not None:
        (inputs / "normalizer.bin").write_bytes(normalizer)
    if grading_contract is not None:
        (root / "grading-contract.json").write_bytes(_bounded_file(grading_contract))
    total = sum(p.stat().st_size for p in inputs.iterdir())
    if total > MAX_INPUT:
        raise ValueError("Prepared grader input exceeds 64 MiB")
    receipt = {"schema": "cantos.external-prepared/1", "run_sha256": sha256_file(path),
               "workload_sha256": run["workload_sha256"], "grader": grader,
               "transcript_sha256": sha256_file(inputs / "transcript.json"), "observations": len(transcript["observations"]),
               "bridge_sha256": sha256_file(__file__), "validator_files": _validator_files(),
               "artifacts": closure(root, exclude=("prepared.json",))}
    if contract_sha is not None:
        receipt["grading_contract_sha256"] = contract_sha
    write(root / "prepared.json", receipt)
    return receipt


def _prepared(prepared_dir):
    root = Path(prepared_dir).resolve()
    meta = maintainer.validate_closure(root / "prepared.json")
    if meta.get("schema") != "cantos.external-prepared/1":
        raise ValueError("Expected generic external grader preparation")
    if meta.get("bridge_sha256") != sha256_file(__file__) or meta.get("validator_files") != _validator_files():
        raise ValueError("Prepare/bind bridge or native validator implementation changed")
    expected = {"transcript.json", "reference.bin"} | ({"normalizer.bin"} if "normalizer_sha256" in meta["grader"] else set())
    files = list((root / "input").iterdir())
    if {p.name for p in files} != expected or sum(p.stat().st_size for p in files) > MAX_INPUT:
        raise ValueError("Unexpected grader input files or excessive total size")
    for path in files:
        _bounded_file(path)
    if meta["transcript_sha256"] != sha256_file(root / "input/transcript.json"):
        raise ValueError("Prepared transcript hash mismatch")
    return root, meta


def bind(run_path, prepared_dir, results_path, out_dir, grading_contract=None, execution_receipt=None):
    root, meta = _prepared(prepared_dir)
    path, run, cases, grader, contract_sha = _checked_run(run_path, grading_contract)
    if grader != meta["grader"] or meta["run_sha256"] != sha256_file(path) or meta.get("grading_contract_sha256") != contract_sha:
        raise ValueError("Preparation belongs to another run, grader or selected grading contract")
    reference_sha = sha256_file(root / "input/reference.bin")
    normalizer_sha = sha256_file(root / "input/normalizer.bin") if "normalizer_sha256" in grader else None
    if reference_sha != grader["reference_sha256"] or normalizer_sha != grader.get("normalizer_sha256"):
        raise ValueError("Pinned reference or normalizer changed")
    expected = _transcript(path, run, cases, grader, reference_sha, normalizer_sha)
    if load(root / "input/transcript.json") != expected:
        raise ValueError("Prepared transcript differs from exact captured conversation")
    result_bytes = _bounded_file(results_path, MAX_OUTPUT)
    results = load(results_path)
    if not isinstance(results, dict) or set(results) != {"schema", "transcript_sha256", "grader", "results"} or results["schema"] != "cantos.external-results/1":
        raise ValueError("Unsupported generic external grader output")
    if results["grader"] != grader or results["transcript_sha256"] != meta["transcript_sha256"]:
        raise ValueError("Grader identity or transcript hash differs from preparation")
    wanted = {(row["task_id"], row["trial"], row["repetition"]): row for row in expected["observations"]}
    if not isinstance(results["results"], list) or len(results["results"]) != len(wanted):
        raise ValueError("External grader output coverage differs from captured observations")
    seen, joined = set(), []
    for result in results["results"]:
        if not isinstance(result, dict) or set(result) - {"task_id", "trial", "repetition", "response_sha256", "trajectory_sha256", "accepted", "reason"}:
            raise ValueError("Invalid per-observation external result")
        key = (result.get("task_id"), result.get("trial"), result.get("repetition"))
        if type(key[1]) is not int or type(key[2]) is not int or key in seen or key not in wanted:
            raise ValueError("Duplicate or unexpected external result identity")
        seen.add(key)
        source = wanted[key]
        if result.get("response_sha256") != source["response_sha256"] or result.get("trajectory_sha256") != source["trajectory_sha256"]:
            raise ValueError("External result differs from exact response or full trajectory")
        if type(result.get("accepted")) is not bool:
            raise ValueError("External accepted outcome must be boolean")
        if result["accepted"] and not source["trajectory"]["capture_eligible"]:
            raise ValueError("Incomplete, errored or previously failed capture cannot become accepted work")
        joined.append({"task_id": key[0], "trial": key[1], "repetition": key[2],
                       "response_sha256": source["response_sha256"], "trajectory_sha256": source["trajectory_sha256"],
                       "accepted": result["accepted"], "evidence": ["artifacts/results.json", "artifacts/transcript.json", "artifacts/prepared.json"]})
    execution = None
    if execution_receipt is not None:
        execution = maintainer.validate_closure(execution_receipt)
        if execution.get("schema") != "cantos.external-execution/1" or execution.get("exit_code") != 0:
            raise ValueError("External grader execution did not complete successfully")
        if execution.get("image") != "sha256:" + grader["artifact_sha256"] or execution.get("transcript_sha256") != meta["transcript_sha256"] or execution.get("results_sha256") != _sha(result_bytes):
            raise ValueError("Execution receipt does not bind this image, transcript and output")
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    artifacts = out / "artifacts"
    artifacts.mkdir()
    for source, name in ((root / "prepared.json", "prepared.json"), (root / "input/transcript.json", "transcript.json"),
                         (root / "input/reference.bin", "reference.bin"), (Path(results_path), "results.json"),
                         (path, "source-run.json"), (Path(__file__), "external_grader.py")):
        shutil.copyfile(source, artifacts / name)
    if normalizer_sha is not None:
        shutil.copyfile(root / "input/normalizer.bin", artifacts / "normalizer.bin")
    if contract_sha is not None:
        shutil.copyfile(grading_contract, artifacts / "grading-contract.json")
    if execution_receipt is not None:
        source = Path(execution_receipt)
        execution_root = artifacts / "execution"
        execution_root.mkdir()
        shutil.copyfile(source, execution_root / "execution.json")
        for entry in execution["artifacts"]:
            target = artifacts / "execution" / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_safe(source.parent, entry["path"]), target)
    grade = {"schema": "cantos.maintainer.grades/1", "run_sha256": sha256_file(path),
             "workload_sha256": run["workload_sha256"], "grader": grader, "results": joined,
             "transcript_sha256": meta["transcript_sha256"], "artifacts": closure(out, exclude=("grades.json",)),
             "execution_basis": "retained_bounded_docker_receipt" if execution else "operator_supplied_result_no_execution_attested"}
    if contract_sha is not None:
        grade["grading_contract_sha256"] = contract_sha
    write(out / "grades.json", grade)
    basis = read_grading_contract(grading_contract) if grading_contract is not None else None
    maintainer.validate_grades(out / "grades.json", path, basis)
    return grade


def sandbox_arguments(image, input_dir, name, cpus=2, memory_mb=2048, pids=128):
    digest = image.removeprefix("sha256:")
    if image != "sha256:" + digest or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Only an immutable local sha256 image identity is allowed")
    if type(cpus) not in (int, float) or not math.isfinite(cpus) or not .1 <= cpus <= 8:
        raise ValueError("CPU limit must be 0.1..8")
    if type(memory_mb) is not int or not 64 <= memory_mb <= 8192 or type(pids) is not int or not 16 <= pids <= 512:
        raise ValueError("Invalid finite memory or PID limit")
    source = str(Path(input_dir).resolve())
    if "," in source or not name.startswith("cantos-grader-") or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in name):
        raise ValueError("Unsafe sandbox input path or owned container name")
    return ["docker", "run", "--name", name, "--rm", "--pull", "never", "--network", "none", "--ipc", "none",
            "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "65534:65534",
            "--pids-limit", str(pids), "--memory", str(memory_mb) + "m", "--memory-swap", str(memory_mb) + "m", "--cpus", str(cpus),
            "--no-healthcheck", "--workdir", "/tmp",
            "--log-driver", "none", "--ulimit", "nofile=128:128", "--ulimit", "fsize=16777216:16777216",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m", "--mount", "type=bind,source=" + source + ",target=/input,readonly",
            "--entrypoint", "/grader/run", image, "--transcript", "/input/transcript.json", "--reference", "/input/reference.bin"]


def _bounded_process(argv, timeout_s, stdout_limit=MAX_OUTPUT, stderr_limit=MAX_LOG):
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
    exceeded = threading.Event()
    captured = [bytearray(), bytearray()]
    def read(stream, index, limit):
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            if len(captured[index]) + len(chunk) > limit:
                captured[index].extend(chunk[:max(0, limit - len(captured[index]))])
                exceeded.set()
                break
            captured[index].extend(chunk)
    threads = [threading.Thread(target=read, args=(stream, index, limit), daemon=True)
               for index, (stream, limit) in enumerate(((process.stdout, stdout_limit), (process.stderr, stderr_limit)))]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout_s
    try:
        while process.poll() is None and not exceeded.is_set() and time.monotonic() < deadline:
            time.sleep(.02)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=2)
        if any(thread.is_alive() for thread in threads) or exceeded.is_set() or time.monotonic() >= deadline:
            error = ValueError("External grader output exceeded its bounded stream limit" if exceeded.is_set() else "External grader exceeded its wall-clock/stream limit")
            error.stdout, error.stderr = bytes(captured[0]), bytes(captured[1])
            raise error
        return process.returncode, bytes(captured[0]), bytes(captured[1])
    finally:
        if process.poll() is None:
            process.kill()
        for stream in (process.stdout, process.stderr):
            stream.close()


def run(prepared_dir, out_dir, timeout_s=300, cpus=2, memory_mb=2048, pids=128):
    if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 1 <= timeout_s <= 3600:
        raise ValueError("Wall-clock limit must be 1..3600 seconds")
    root, meta = _prepared(prepared_dir)
    image = "sha256:" + meta["grader"]["artifact_sha256"]
    name = "cantos-grader-" + uuid.uuid4().hex
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": "cantos.external-execution/1", "image": image, "container": name,
               "transcript_sha256": meta["transcript_sha256"], "limits": {"timeout_s": timeout_s, "cpus": cpus, "memory_mb": memory_mb, "pids": pids},
               "exit_code": None, "results_sha256": None}
    container_attempted = False
    try:
        docker_host = os.environ.get("DOCKER_HOST")
        if docker_host and not docker_host.startswith(("unix://", "npipe://")):
            raise ValueError("Generic grader execution requires a local Docker endpoint")
        code, stdout, stderr = _bounded_process(["docker", "context", "inspect"], 15, MAX_LOG, MAX_LOG)
        contexts = json.loads(stdout) if code == 0 else []
        endpoint = contexts[0].get("Endpoints", {}).get("docker", {}).get("Host", "") if isinstance(contexts, list) and len(contexts) == 1 else ""
        if not endpoint.startswith(("unix://", "npipe://")):
            raise ValueError("Generic grader execution requires a local Docker context")
        (out / "docker-context.json").write_bytes(stdout)
        code, stdout, stderr = _bounded_process(["docker", "image", "inspect", image], 30, MAX_LOG, MAX_LOG)
        (out / "image-inspect.json").write_bytes(stdout)
        (out / "image-inspect.log").write_bytes(stderr)
        inspected = json.loads(stdout) if code == 0 else []
        if not isinstance(inspected, list) or len(inspected) != 1 or inspected[0].get("Id") != image:
            raise ValueError("Pinned grader image is not already present locally; no pull was attempted")
        if inspected[0].get("Config", {}).get("Volumes"):
            raise ValueError("Grader images declaring writable volumes are not supported")
        with tempfile.TemporaryDirectory(prefix="cantos-grader-input-") as temporary:
            target = Path(temporary)
            for source in (root / "input").iterdir():
                shutil.copyfile(source, target / source.name)
                (target / source.name).chmod(0o444)
            target.chmod(0o555)
            argv = sandbox_arguments(image, target, name, cpus, memory_mb, pids)
            if "normalizer_sha256" in meta["grader"]:
                argv.extend(["--normalizer", "/input/normalizer.bin"])
            receipt["argv"] = argv
            container_attempted = True
            code, stdout, stderr = _bounded_process(argv, timeout_s)
            (out / "results.json").write_bytes(stdout)
            (out / "grader.log").write_bytes(stderr)
            receipt.update(exit_code=code, results_sha256=_sha(stdout))
            if code != 0:
                raise ValueError("External grader failed; retain its execution receipt and logs")
    except Exception as exc:
        receipt["error"] = type(exc).__name__ + ": " + str(exc)
        if hasattr(exc, "stdout"):
            (out / "partial-stdout.bin").write_bytes(exc.stdout)
            (out / "partial-stderr.bin").write_bytes(exc.stderr)
        raise
    finally:
        try:
            if container_attempted:
                cleanup_code, cleanup_out, cleanup_err = _bounded_process(["docker", "rm", "--force", name], 15, MAX_LOG, MAX_LOG)
                receipt["cleanup"] = {"exit_code": cleanup_code, "stdout": cleanup_out.decode("utf-8", "replace"), "stderr": cleanup_err.decode("utf-8", "replace")}
            else:
                receipt["cleanup"] = {"container_not_started": True}
        except Exception as exc:
            receipt["cleanup"] = {"error": type(exc).__name__ + ": " + str(exc)}
        receipt["artifacts"] = closure(out, exclude=("execution.json",))
        write(out / "execution.json", receipt)
    return receipt


def validate_config(config, closure_root):
    """Read-only job contract validation. It never inspects Docker or executes."""
    if not isinstance(config, dict) or set(config) - {"execute", "reference", "normalizer", "grading_contract", "limits"}:
        raise ValueError("Unsupported external_grading configuration")
    if type(config.get("execute", False)) is not bool:
        raise ValueError("external_grading.execute must be boolean")
    root = Path(closure_root).resolve()
    paths = {}
    for field in ("reference", "normalizer", "grading_contract"):
        value = config.get(field)
        if value is None:
            if field == "reference":
                raise ValueError("External grading requires a pinned reference file")
            continue
        if not isinstance(value, str) or Path(value).is_absolute():
            raise ValueError("External grading inputs must be job-relative paths")
        paths[field] = _safe(root, value)
        _bounded_file(paths[field])
    limits = config.get("limits", {})
    if not isinstance(limits, dict) or set(limits) - {"timeout_s", "cpus", "memory_mb", "pids"}:
        raise ValueError("Unsupported external grading limits")
    limits = {"timeout_s": 300, "cpus": 2, "memory_mb": 2048, "pids": 128, **limits}
    if type(limits["timeout_s"]) not in (int, float) or not math.isfinite(limits["timeout_s"]) or not 1 <= limits["timeout_s"] <= 3600:
        raise ValueError("External grading wall-clock limit must be 1..3600 seconds")
    sandbox_arguments("sha256:" + "0" * 64, root, "cantos-grader-validation", limits["cpus"], limits["memory_mb"], limits["pids"])
    return {"execute": config.get("execute", False), "paths": paths, "limits": limits}


def grade_pair(runs, config, closure_root, out_dir):
    """Explicit live-job grading step; never call from import or reanalysis."""
    selected = validate_config(config, closure_root)
    if selected["execute"] is not True:
        raise ValueError("Docker grading requires external_grading.execute=true in an explicit job run")
    if not isinstance(runs, dict) or set(runs) != {"baseline", "candidate"}:
        raise ValueError("External grading requires both captured run paths")
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    paths = selected["paths"]
    result = {"execution": {"inference_requests": 0, "grader_executions": 0}, "grading_contract": paths.get("grading_contract")}
    for side in ("baseline", "candidate"):
        arm = out / side
        arm.mkdir()
        prepare(runs[side], paths["reference"], arm / "prepared", paths.get("normalizer"), paths.get("grading_contract"))
        run(arm / "prepared", arm / "execution", **selected["limits"])
        bind(runs[side], arm / "prepared", arm / "execution/results.json", arm / "grades",
             paths.get("grading_contract"), arm / "execution/execution.json")
        result[side] = arm / "grades/grades.json"
        result["execution"]["grader_executions"] += 1
    result["artifacts"] = closure(out, exclude=())
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    for field in ("run", "reference", "out"):
        prep.add_argument("--" + field, required=True)
    prep.add_argument("--normalizer")
    prep.add_argument("--grading-contract")
    bound = commands.add_parser("bind")
    for field in ("run", "prepared", "results", "out"):
        bound.add_argument("--" + field, required=True)
    bound.add_argument("--grading-contract")
    bound.add_argument("--execution-receipt")
    execute = commands.add_parser("run")
    execute.add_argument("--prepared", required=True)
    execute.add_argument("--out", required=True)
    execute.add_argument("--timeout-s", type=float, default=300)
    execute.add_argument("--cpus", type=float, default=2)
    execute.add_argument("--memory-mb", type=int, default=2048)
    execute.add_argument("--pids", type=int, default=128)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        result = prepare(args.run, args.reference, args.out, args.normalizer, args.grading_contract)
    elif args.command == "bind":
        result = bind(args.run, args.prepared, args.results, args.out, args.grading_contract, args.execution_receipt)
    else:
        result = run(args.prepared, args.out, args.timeout_s, args.cpus, args.memory_mb, args.pids)
    print(json.dumps({key: value for key, value in result.items() if key != "artifacts"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
