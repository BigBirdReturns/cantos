#!/usr/bin/env python3
"""Read-only Hy4 source/schema/hardware preflight. Never downloads or starts inference."""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE.parents[1]))
import common as native

EXPECTED = {
    "instruct-bf16": ("tencent/Hy4-flash", "d88c9dfd96ba4f2e6b92adba0b8e8f1c8696f959", "instruction_tuned"),
    "instruct-fp8": ("tencent/Hy4-flash-FP8", "003107fa248f5892064ab1c43af0a7003dd68c9b", "instruction_tuned"),
    "base-bf16": ("tencent/Hy4-flash-base", "95b9f8239e2f63cb837c91704f070ae47332ebdf", "pretrained_base"),
}
GPU_FAMILY = re.compile(r"(?:^|\s)(H100|H200|B200|GB200|B300|GB300)(?:\s|$)")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def record_check(checks, name, status, detail, **evidence):
    checks.append({"id": name, "status": status, "detail": detail, **evidence})


def verify_artifact(root, record):
    path = (root / record["path"]).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("missing or escaping source artifact: " + record["path"])
    data = path.read_bytes()
    if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise ValueError("changed source artifact: " + record["path"])
    return path


def verify_package(root=PACKAGE):
    root = Path(root)
    sources = native.load(root / "sources.json")
    records = [s["artifact"] for s in sources["sources"] if "artifact" in s]
    for rec in records:
        verify_artifact(root, rec)
    variants = native.load(root / "variants.json")
    if {v["id"] for v in variants["variants"]} != set(EXPECTED) or len(variants["variants"]) != 3:
        raise ValueError("expected precisely the three pinned published variants")
    weights = {}
    for v in variants["variants"]:
        if (v["repository"], v["revision"], v["training_stage"]) != EXPECTED[v["id"]]:
            raise ValueError("variant identity or training-stage mismatch")
        path = verify_artifact(root, v["publisher_weight_manifest"])
        wm = native.load(path)
        metadata = native.load(verify_artifact(root, v["metadata"]))
        verify_artifact(root, v["config"])
        if wm["model_id"] != v["repository"] or wm["revision"] != v["revision"] or metadata["sha"] != v["revision"]:
            raise ValueError("weight manifest revision mismatch")
        publisher = {
            x["rfilename"]: (x["size"], x["lfs"]["sha256"])
            for x in metadata["siblings"] if x["rfilename"].endswith(".safetensors")
        }
        retained = {}
        for f in wm["files"]:
            if f["path"] in retained or not HEX64.fullmatch(f["sha256"]):
                raise ValueError("invalid weight digest or duplicate shard")
            retained[f["path"]] = (f["bytes"], f["sha256"])
        if retained != publisher or len(retained) != v["weight_file_count"]:
            raise ValueError("publisher weight closure mismatch")
        if sum(x[0] for x in retained.values()) != v["weight_bytes"]:
            raise ValueError("weight byte total mismatch")
        weights[v["id"]] = {"files": len(retained), "bytes": v["weight_bytes"],
                              "local_payload_verified": False}
    runtime = native.load(root / "runtime.json")
    index = root / "snapshots/container-index.json"
    if "sha256:" + hashlib.sha256(index.read_bytes()).hexdigest() != runtime["image_digest"]:
        raise ValueError("container digest mismatch")
    for name, model in (("bf16", "tencent/Hy4-flash"), ("fp8", "tencent/Hy4-flash-FP8")):
        recipe = native.load(root / runtime["recipes"][name]["artifact"])
        argv = runtime["recipes"][name]["argv"]
        if argv != recipe["argv"] or argv[:3] != ["vllm", "serve", model]:
            raise ValueError("recipe/model mapping mismatch")
        if "--speculative-config" in argv or argv[argv.index("--tensor-parallel-size") + 1] != "8":
            raise ValueError("primary experiment must retain TP8 and disable speculation")
    spec_path = root / "spec.precision.template.json"
    spec = native.load(spec_path)
    native.keys(spec, {"schema", "workload", "policy", "protocol", "baseline", "candidate"}, "spec")
    if spec["schema"] != "cantos.maintainer.spec/1":
        raise ValueError("incorrect native spec schema")
    workload = native.validate_workload(native.load(root / spec["workload"]))
    native.protocol(spec["protocol"])
    native.policy(native.load(root / spec["policy"]))
    refusal = {}
    for arm in ("baseline", "candidate"):
        try:
            native.prepare(spec_path, arm)
        except ValueError as exc:
            if "configure " + arm not in str(exc):
                raise
            refusal[arm] = str(exc)
        else:
            raise ValueError("unbound template unexpectedly prepared: " + arm)
    return {"source_artifacts_verified": len(records), "publisher_weights": weights,
            "workload_cases": len(workload["cases"]),
            "native_schema": spec["schema"], "native_template_refusal": refusal}


def probe(argv):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=20)
        return {"argv": argv, "exit_code": r.returncode, "stdout": r.stdout, "stderr": r.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"argv": argv, "error": str(exc)}


def live_inventory(runtime):
    memory = {}
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        for line in meminfo.read_text().splitlines():
            key, value = line.split(":", 1)
            if key in ("MemTotal", "MemAvailable"):
                memory[key + "_bytes"] = int(value.split()[0]) * 1024
    disk = shutil.disk_usage(PACKAGE)
    return {
        "schema": "cantos.hy4.hardware-observation/1",
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "host": platform.node(),
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "memory": memory,
        "filesystem": {"path": str(PACKAGE), "free_bytes": disk.free, "total_bytes": disk.total},
        "gpu_probe": probe(["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,memory.used,driver_version,compute_cap,power.draw,power.limit,temperature.gpu",
                            "--format=csv,noheader,nounits"]),
        "container_probe": probe(["docker", "image", "inspect",
                                  runtime["image_repository"] + "@" + runtime["image_digest"],
                                  "--format", "{{json .RepoDigests}}"]),
        "scope": "Read-only OS/GPU inventory and local image inspect; no pull or inference."
    }


def parse_gpus(observation):
    p = observation.get("gpu_probe", {})
    if p.get("exit_code") != 0:
        return []
    out = []
    for row in csv.reader(io.StringIO(p.get("stdout", "")), skipinitialspace=True):
        if len(row) != 10:
            raise ValueError("unexpected GPU inventory column count")
        out.append({"index": int(row[0]), "name": row[1].strip(), "uuid": row[2].strip(),
                    "memory_total_mib": int(float(row[3])), "memory_used_mib": int(float(row[4])),
                    "driver_version": row[5].strip(), "compute_capability": row[6].strip(),
                    "power_draw_w": row[7].strip(), "power_limit_w": row[8].strip(),
                    "temperature_c": row[9].strip()})
    return out


def assess_inventory(observation, runtime):
    checks = []
    gpus = parse_gpus(observation)
    unsupported = [g["name"] for g in gpus if not GPU_FAMILY.search(g["name"])]
    record_check(checks, "documented_gpu_family", "pass" if gpus and not unsupported else "blocked",
                 "The published container path targets Hopper/Blackwell data-center families.",
                 devices=gpus, unsupported=unsupported, source_id="vllm-recipe-documentation")
    exact = len(gpus) == 8 and all(re.search(r"(?:^|\s)H200(?:\s|$)", g["name"]) for g in gpus)
    record_check(checks, "selected_recipe_topology", "pass" if exact else "blocked",
                 "This retained recipe selects eight H200 GPUs; other supported families require their own retained recipe and qualification.",
                 observed_count=len(gpus), selected_count=8, selected_model="H200")
    cp = observation.get("container_probe", {})
    expected = runtime["image_repository"] + "@" + runtime["image_digest"]
    present = cp.get("exit_code") == 0 and expected in cp.get("stdout", "")
    record_check(checks, "local_pinned_image", "pass" if present else "blocked",
                 "Local image inspection does not pull an image.", expected=expected, probe=cp)
    record_check(checks, "host_and_gpu_capacity", "unverified",
                 "Published download-size multipliers are estimates, not measured allocation minima. Host Engram offload requires independent RAM and GPU-memory qualification.",
                 memory=observation.get("memory"), filesystem=observation.get("filesystem"))
    busy = [g["uuid"] for g in gpus if g["memory_used_mib"] > 256]
    record_check(checks, "device_allocation_and_other_load", "unverified",
                 "An inventory does not reserve devices or establish sole job ownership.",
                 devices_with_more_than_256_mib_used=busy)
    record_check(checks, "local_weight_payloads", "blocked",
                 "This package binds publisher shard hashes. No local Hy4 weight payload has been verified by this package.")
    record_check(checks, "kernel_and_endpoint_smoke", "unverified",
                 "A real pinned-server startup and streamed accepted request have not been executed.")
    record_check(checks, "bound_native_spec", "blocked",
                 "The shipped native spec retains required hardware, weight-verification and runtime-control placeholders.")
    return checks


def make_report(observation, mode, root=PACKAGE):
    verified = verify_package(root)
    runtime = native.load(Path(root) / "runtime.json")
    checks = assess_inventory(observation, runtime)
    return {
        "schema": "cantos.hy4.preflight/1",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "inventory_mode": mode, "inventory_observed_at": observation["observed_at"],
        "host": observation["host"], "status": "blocked" if any(c["status"] == "blocked" for c in checks) else "unqualified",
        "ready_to_launch": False, "hy4_inference_observed": False,
        "read_only": True, "model_requests_sent": 0, "gpu_workloads_started": 0,
        "weight_payloads_downloaded": False, "container_layers_downloaded": False,
        "package_validation": verified, "checks": checks,
        "energy_boundary": "GPU-board telemetry excludes CPU, host RAM, networking and wall-power losses; host Engram offload makes those exclusions material.",
        "terminal_condition": "This preflight reports prerequisites and retained evidence; successful Hy4 deployment and benchmark acceptance require new source-bound observations."
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--live", action="store_true", help="Read current local OS/GPU/image metadata only.")
    group.add_argument("--inventory", type=Path, help="Replay a retained hardware observation.")
    args = p.parse_args()
    try:
        runtime = native.load(PACKAGE / "runtime.json")
        observation = live_inventory(runtime) if args.live else native.load(args.inventory or PACKAGE / "hardware-observed.json")
        report = make_report(observation, "live_metadata" if args.live else "retained_metadata")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({"schema": "cantos.hy4.preflight/1", "status": "error",
                          "ready_to_launch": False, "error": str(exc)}, indent=2))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
