#!/usr/bin/env python3
"""Regenerate this fixture from run3's own modules (workload, convert, grade, replay). Run only when run3
changes its shapes; the committed fixture is what ledger_build_run3.py's self-test reads. Stdlib only.

    python fixtures/run3-mini/REGENERATE.py

Everything produced is synthetic (tasks synthetic=true, six scheduled requests over a 3600 s plan,
authored grades) and mirrors run3/selftest.py's evidence()/grading() so the shapes are lane A's, not ours.
"""
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAMPAIGN = HERE.parents[2]
RUN3 = CAMPAIGN / "run3"
sys.path.insert(0, str(RUN3))
sys.dont_write_bytecode = True
import convert  # noqa: E402
import grade  # noqa: E402
import workload  # noqa: E402
from common import MODEL, REVISION, encoded, jsonl, read_json, sha, write_json  # noqa: E402

FIX = RUN3 / "fixtures"
ARM = HERE / "arm-amd-t0"


def main():
    if ARM.exists():
        shutil.rmtree(ARM)
    ARM.mkdir(parents=True)
    tasks = ARM / "tasks.json"
    frozen = workload.build(FIX / "humaneval.jsonl", FIX / "mbpp.jsonl",
                            {d: sha(FIX / (d + ".jsonl")) for d in ("humaneval", "mbpp")}, tasks, fixture=True)
    replay_dir = ARM / "replay"; replay_dir.mkdir()
    specs, rows = [], []
    for i in range(6):
        spec = dict(request_index=i, task_id=frozen["tasks"][i % 5]["task_id"], seed=700000 + i, scheduled_ts=1000 + i * 300)
        specs.append(spec)
        row = dict(spec, send_ts=spec["scheduled_ts"] + (2 if i == 2 else 0.01),
                   first_token_ts=spec["scheduled_ts"] + (2.1 if i == 2 else 0.1),
                   end_ts=spec["scheduled_ts"] + 3, output_text=f"    return x + {i}\n",
                   input_tokens=20, output_tokens=4, finish_reason="stop", error="")
        if i == 4:
            row.update(error="HTTP 500", first_token_ts=None, output_tokens=None, input_tokens=None)
        rows.append(row)
    plan = dict(schema="second-run/replay-plan@1", synthetic=True, start_ts=1000, duration_s=3600, rate_factor=0.1,
                trace_sha256=sha(FIX / "code-slice.csv"), trace_start="2023-11-16T00:00:00Z", tasks_sha256=sha(tasks),
                model=MODEL, revision=REVISION, temperature=0.2, max_tokens=1024, request_timeout_s=60,
                workers=256, requests=specs)   # same keys replay.replay() writes
    write_json(replay_dir / "plan.json", plan)
    (replay_dir / "journal.jsonl").write_bytes(b"".join(encoded(r) for r in rows))
    write_json(replay_dir / "replay-status.json", {"interrupted": False, "end_ts": 4600})
    detail = ARM / "detailed.json"
    image = "vllm/vllm-openai-rocm:v0.30.0@sha256:2e7da1ad1c66836802072588adea75f9f4991da5f9545b4318e91d422c22ce6a"
    convert.convert(replay_dir, detail, image)
    gdir = ARM / "grade"
    mapping = grade.prepare(tasks, replay_dir / "requests.jsonl", detail, gdir)
    for dataset, meta in mapping["datasets"].items():
        result = {"hash": meta["reference_md5"], "eval": {}}
        for sample, n in zip(jsonl(gdir / (dataset + ".jsonl")), meta["request_indices"]):
            result["eval"].setdefault(sample["task_id"], []).append(dict(sample, base_status="pass", plus_status="pass" if n in (0, 2, 4, 5) else "fail"))
        write_json(gdir / (dataset + "_eval_results.json"), result)
    sidecar = gdir / "evaluation.json"
    grade.join(tasks, replay_dir / "requests.jsonl", detail, gdir, sidecar)
    grade.summary(replay_dir, sidecar, detail, gdir / "buckets.json")
    # arm.py outputs, as arm.py writes them (env.json, invocation.json, ledger-times.json, ledger.json)
    write_json(ARM / "invocation.json", {"kind": "amd", "tier": "T0", "argv": ["docker", "run", "fixture"], "tasks_sha256": sha(tasks),
                                          "trace_sha256": plan["trace_sha256"], "trace_start": plan["trace_start"], "rate_factor": 0.1, "watchdog_s": 6600})
    write_json(ARM / "env.json", {"schema": "second-run/arm-environment@1", "run": "run3", "kind": "amd", "tier": "T0", "image": image,
                                   "model": plan["model"], "revision": plan["revision"], "gpu_count": 1, "tensor_parallel": 1,
                                   "serve_argv": ["fixture"], "attention_backend": ["ROCM_ATTN"], "linear_kernel": ["RowWiseTorchFP8ScaledMMLinearKernel"],
                                   "vllm_version": "0.30.0"})
    times = {"t_request": None, "t_ssh": "2026-09-24T18:00:00+00:00", "t_script_start": "2026-09-24T18:01:00+00:00",
             "t_ready": "2026-09-24T18:20:00+00:00", "t_work_start": "2026-09-24T18:22:00+00:00",
             "t_work_end": "2026-09-24T19:22:05+00:00", "t_released": None, "t_script_end": "2026-09-24T19:24:00+00:00"}
    write_json(ARM / "ledger-times.json", times)
    write_json(ARM / "ledger.json", {"schema": "second-run/run3-arm-summary@1", "status": "completed_ungraded", "arm": "A", "tier": "T0",
                                      "timestamps": times, "hourly_list_usd": 2.99, "funding": "self-funded; operator must verify invoice",
                                      "modeled_full_cost_usd": None, "billed_usd": None, "credits_usd": None, "acquisition_attempts": None,
                                      "restarts": 0, "attempted": 6, "completed": 5, "failed": 1, "lost": 0, "correct": None, "accepted": None,
                                      "cost_per_accepted_usd": None, "wall_seconds_per_accepted": None, "traversals_per_run": None,
                                      "seconds_per_traversal": None, "bytes_per_traversal": None, "accepted_closures_per_traversal": None,
                                      "energy_wh": None, "note": "Null means unmeasured; provider release is not container stop."})
    (ARM / "serve.log").write_text("INFO Using ROCM_ATTN attention backend.\n", encoding="utf-8")
    files = sorted(p for p in ARM.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    (ARM / "MANIFEST.sha256").write_text("".join(f"{sha(p)}  {p.relative_to(ARM).as_posix()}\n" for p in files), encoding="utf-8")
    # operator closure: what arm.py cannot know (lane C delivered row shape for the attempt)
    write_json(HERE / "closure.json", {
        "schema": "second-run/run-closure@1", "run_id": "run3/A-T0", "campaign": "run3-2026-09", "synthetic": True,
        "seat_id": "hotaisle-mi300x-1x-enc1", "provider": "hotaisle", "region": "enc1", "sku": "vm-mi300x-1x", "host": "fixture-host",
        "t_request": "2026-09-24T17:50:00Z", "t_released": "2026-09-24T19:30:00Z",
        "t_released_source": "fixture: provider console delete confirmation",
        "attempts": [
            {"ts": "2026-09-24T17:40:00Z", "provider": "hotaisle", "sku": "vm-mi300x-1x", "region": "enc1", "gpus": 1, "method": "tui-provision", "layer": "delivered",
             "outcome": "create_failed", "ssh_reached": False, "provisioned": False, "attempt_id": "fixture-1", "evidence": "fixture: first provision refused"},
            {"ts": "2026-09-24T17:50:00Z", "provider": "hotaisle", "sku": "vm-mi300x-1x", "region": "enc1", "gpus": 1, "method": "tui-provision", "layer": "delivered",
             "outcome": "available", "ssh_reached": True, "provisioned": True, "time_to_ssh_s": 600, "attempt_id": "fixture-2", "evidence": "fixture: second provision reached ssh"}],
        "billed_usd": None, "billed_ref": None, "credits_usd": None, "payer": "self",
        "prereg_commit": None,
    })
    print("regenerated", ARM, "and closure.json")


if __name__ == "__main__":
    main()
