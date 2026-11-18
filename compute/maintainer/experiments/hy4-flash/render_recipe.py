#!/usr/bin/env python3
"""Print a pinned, offline Docker command. This command renderer never executes it."""
from __future__ import annotations
import argparse
import json
import re
import shlex
from pathlib import Path
from preflight import PACKAGE, native, verify_package

UUID = re.compile(r"GPU-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")


def render(variant, snapshot, gpu_uuids, port=8000):
    verify_package()
    snapshot = Path(snapshot)
    if not snapshot.is_absolute() or ":" in str(snapshot) or "\n" in str(snapshot):
        raise ValueError("snapshot must be an absolute, Docker-mount-safe path")
    if len(gpu_uuids) != 8 or len(set(gpu_uuids)) != 8 or any(not UUID.fullmatch(x) for x in gpu_uuids):
        raise ValueError("supply exactly eight distinct NVIDIA GPU UUIDs for the retained TP8 recipe")
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("port must be 1024..65535")
    if variant not in ("instruct-bf16", "instruct-fp8"):
        raise ValueError("Base needs a separately qualified task-fit protocol")
    runtime = native.load(PACKAGE / "runtime.json")
    key = "bf16" if variant == "instruct-bf16" else "fp8"
    source = runtime["recipes"][key]
    serving_args = source["argv"][3:]
    command = [
        "docker", "run", "--rm", "--pull=never", "--gpus", '"device=' + ",".join(gpu_uuids) + '"',
        "--ipc=host", "-p", f"127.0.0.1:{port}:8000", "-v", str(snapshot) + ":/model:ro",
        "-e", "HF_HUB_OFFLINE=1", "-e", "TRANSFORMERS_OFFLINE=1",
        "-e", "VLLM_USE_RUST_FRONTEND=1",
        runtime["image_repository"] + "@" + runtime["image_digest"], "/model",
        *serving_args, "--served-model-name", "hy4-flash", "--host", "0.0.0.0", "--port", "8000"
    ]
    return {
        "schema": "cantos.hy4.command-proposal/1", "variant": variant, "status": "unexecuted",
        "source_recipe": source["artifact"], "argv": command, "shell": shlex.join(command),
        "adaptations": [
            "Pin the container by immutable index digest and require it already present.",
            "Mount an operator-verified local model snapshot read-only; request offline HF/Transformers access.",
            "Bind explicit GPU UUIDs and expose the API only on host loopback.",
            "Omit the vendor example's privileged container flag; actual startup remains unqualified."
        ],
        "requires": [
            "Matching qualified eight-H200 allocation, sufficient host RAM/VRAM and verified local weights.",
            "Actual startup/kernel/endpoint acceptance before any benchmark-readiness claim.",
            "Measured effective runtime controls and a separately bound native spec."
        ]
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--variant", choices=["instruct-bf16", "instruct-fp8"], required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--gpu-uuids", required=True, help="Comma-separated eight actual GPU UUIDs.")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    try:
        print(json.dumps(render(args.variant, args.snapshot, args.gpu_uuids.split(","), args.port), indent=2))
    except (ValueError, OSError, KeyError) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
