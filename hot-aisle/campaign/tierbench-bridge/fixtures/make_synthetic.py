#!/usr/bin/env python3
"""Write the SYNTHETIC fixtures: four route.py receipts in the our-auto/run@1 shape and the Run 3 Knot.
Stdlib only. No real run directory was read (route.py's scratch/durable roots are outside the entry lock);
token counts are invented to exercise the pricing path. Nothing here is evidence.

    python fixtures/make_synthetic.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
H = lambda c: c * 64  # a fake sha256


def receipt(tag, **kw):
    base = {"schema": "our-auto/run@1", "synthetic": True,
            "_note": "SYNTHETIC receipt in route.py's our-auto/run@1 shape (integrations/our-auto-router/scripts/route.py). "
                     "No real run directory was read. Token counts are invented to exercise the pricing path; nothing here is evidence.",
            "prefer_latency": False, "workspace": None, "allow_read_tools": False,
            "run_dir": f"S:/x/runs/synth{tag}", "receipt_paths": [f"S:/x/runs/synth{tag}/receipt.json"]}
    base.update(kw)
    return base


def main():
    A = receipt("A", started_at_utc="2026-07-18T21:40:00+00:00", kind="structured", allow_cloud=False,
                prompt_file="S:/x/prompt.txt", prompt_sha256=H("0"), validator="S:/x/validate_json.py", validator_sha256=H("1"),
                attempts=[{"index": 1, "provider": "ollama", "model": "qwen3.5:9b-q4_K_M", "effort": "none", "attempt_dir": "attempt-01-qwen3.5_9b-q4_K_M",
                           "gpu_probe": "gpu_memory_fraction=0.120;limit=0.650", "call_status": "completed", "elapsed_seconds": 1.098, "done": True, "done_reason": "stop",
                           "prompt_eval_count": 46, "eval_count": 13, "total_duration_ns": 1027249700, "raw_sha256": H("2"), "candidate_sha256": H("3"),
                           "validator": {"passed": True, "exit_code": 0, "elapsed_seconds": 0.05, "command": ["python", "validate_json.py", "<CANDIDATE>"], "stdout_sha256": H("4"), "stderr_sha256": H("5")}},
                          {"index": 2, "provider": "codex", "model": "gpt-5.6-luna", "effort": "low", "attempt_dir": "attempt-02-gpt-5.6-luna", "call_status": "skipped", "reason": "cloud_not_allowed"}],
                completed_at_utc="2026-07-18T21:40:02+00:00", status="pass", selected_candidate="attempt-01-qwen3.5_9b-q4_K_M/candidate.txt", selected_candidate_sha256=H("3"))
    B = receipt("B", started_at_utc="2026-07-19T00:38:00+00:00", kind="code", allow_cloud=True,
                prompt_file="S:/x/prompt.txt", prompt_sha256=H("6"), validator="S:/x/validate_code.py", validator_sha256=H("7"),
                attempts=[{"index": 1, "provider": "codex", "model": "gpt-5.6-luna", "effort": "low", "attempt_dir": "attempt-01-gpt-5.6-luna", "call_status": "completed", "exit_code": 0,
                           "elapsed_seconds": 6.957, "command": ["codex", "exec", "..."], "stdout_sha256": H("8"), "stderr_sha256": H("9"),
                           "usage": {"input_tokens": 1800, "cached_input_tokens": 600, "output_tokens": 420}, "candidate_sha256": H("a"),
                           "validator": {"passed": True, "exit_code": 0, "elapsed_seconds": 0.4, "command": ["python", "validate_code.py", "<CANDIDATE>"], "stdout_sha256": H("b"), "stderr_sha256": H("c")}}],
                completed_at_utc="2026-07-19T00:38:08+00:00", status="pass", selected_candidate="attempt-01-gpt-5.6-luna/candidate.txt", selected_candidate_sha256=H("a"))
    C = receipt("C", started_at_utc="2026-07-19T01:00:00+00:00", kind="code", allow_cloud=True,
                prompt_file="S:/x/prompt2.txt", prompt_sha256=H("d"), validator="S:/x/validate_code.py", validator_sha256=H("7"), workspace="S:/x/ws", allow_read_tools=True,
                attempts=[{"index": 1, "provider": "codex", "model": "gpt-5.6-luna", "effort": "low", "attempt_dir": "attempt-01-gpt-5.6-luna", "call_status": "completed", "exit_code": 0,
                           "elapsed_seconds": 9.2, "usage": {"input_tokens": 5200, "cached_input_tokens": 0, "output_tokens": 900}, "candidate_sha256": H("e"),
                           "validator": {"passed": False, "exit_code": 1, "elapsed_seconds": 0.4}},
                          {"index": 2, "provider": "codex", "model": "gpt-5.6-terra", "effort": "medium", "attempt_dir": "attempt-02-gpt-5.6-terra", "call_status": "completed", "exit_code": 0,
                           "elapsed_seconds": 41.0, "usage": {"input_tokens": 5300, "cached_input_tokens": 0, "output_tokens": 1500}, "candidate_sha256": H("f"),
                           "validator": {"passed": True, "exit_code": 0, "elapsed_seconds": 0.4}},
                          {"index": 3, "provider": "codex", "model": "gpt-5.6-sol", "effort": "high", "attempt_dir": "attempt-03-gpt-5.6-sol", "call_status": "skipped", "reason": "cloud_attempt_ceiling"}],
                completed_at_utc="2026-07-19T01:01:00+00:00", status="pass", selected_candidate="attempt-02-gpt-5.6-terra/candidate.txt", selected_candidate_sha256=H("f"))
    D = receipt("D", started_at_utc="2026-07-19T02:00:00+00:00", kind="code", allow_cloud=True,
                prompt_file="S:/x/prompt3.txt", prompt_sha256="1a" * 32, validator="S:/x/validate_code.py", validator_sha256=H("7"),
                attempts=[{"index": 1, "provider": "codex", "model": "gpt-5.6-luna", "effort": "low", "attempt_dir": "attempt-01-gpt-5.6-luna", "call_status": "failed",
                           "elapsed_seconds": 300.0, "error_type": "TimeoutExpired", "error": "codex timed out"}],
                completed_at_utc="2026-07-19T02:05:00+00:00", status="no_passing_candidate", selected_candidate=None)
    for n, r in (("A", A), ("B", B), ("C", C), ("D", D)):
        with open(os.path.join(HERE, "router", f"receipt-synth{n}.json"), "w", encoding="utf-8") as f:
            json.dump(r, f, indent=2)
    knot = {
        "schema": "second-run/knot-spec@1",
        "knot_id": "knot-run3-evalplus-tierbench",
        "task_class": "graded-coding",
        "tierbench": {
            "task_classes": ["tierbench-T1"],
            "basis": "EvalPlus HumanEval+/MBPP+ is implement-from-docstring, the shape of Tier-Bench's t1_impl_from_docstring_001. This is an ANALOGY declared by the Knot, not a measured equivalence (RUN3-GRID.md).",
            "k": 3,
            "open_weight_tier": "qwen3-coder-30b-a3b-fp8@vllm",
            "open_weight_tier_note": "the tier this Knot's model field describes when run on a fabric seat; no Tier-Bench Call rows exist for it yet",
        },
        "count": 542,
        "evaluator": {"name": "evalplus-base-plus", "frozen": True, "needs_seat_role": "grader", "hidden": False,
                      "hidden_note": "EvalPlus plus-tests are public; Tier-Bench would not call this hidden-graded"},
        "deadline_s": 5400,
        "start_at": "2026-09-24T18:00:00Z",
        "tokens_in_per_closure": 400,
        "tokens_out_per_closure": 300,
        "model": {
            "id": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
            "class": "moe-30b-a3b",
            "formats": [
                {"format": "fp8", "bytes": 31187041238, "bytes_basis": "identity.json (pinned)", "recipes": ["vllm-cuda", "vllm-rocm"]},
                {"format": "awq-int4", "bytes": 16500000000, "bytes_basis": "UNVERIFIED ~16 GB (SYNTHESIS)", "recipes": ["vllm-cuda", "vllm-rocm"]},
                {"format": "gguf-q4", "bytes": 18600000000, "bytes_basis": "UNVERIFIED ~18.6 GB Q4_K_M estimate; pin before use", "recipes": ["llama.cpp-cuda", "ollama"]},
            ],
        },
        "traversal_profile": {"batch_depths": [1, 8, 32, 64], "closures_per_traversal_curve": None},
        "policy": {"max_usd": 25.0, "kwh_usd": 0.30, "kwh_usd_basis": "assumed; operator to supply the tariff"},
    }
    with open(os.path.join(HERE, "knots", "knot-run3-evalplus-tierbench.json"), "w", encoding="utf-8") as f:
        json.dump(knot, f, indent=2)
    print("synthetic fixtures written: 4 receipts, 1 knot")


if __name__ == "__main__":
    main()
