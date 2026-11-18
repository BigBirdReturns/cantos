#!/usr/bin/env python3
"""Independent audit of vLLM bench serve's published per-request traces.

This script uses only Python's standard library. It recomputes *true* request
overlap with an event sweep, validates token accounting, and preserves the
original result JSON without mutating it.
"""
import hashlib
import json
import math
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
RESULTS = ROOT / "results"
CASES = ["fresh32", "reuse32", "fresh_warm32", "reuse_warm32"]

def exact_peak(starts, latencies, errors):
    events = []
    for start, dur, err in zip(starts, latencies, errors):
        if err:
            continue
        a = float(start)
        b = a + float(dur)
        if b <= a:
            raise ValueError(f"invalid interval {a}, {b}")
        events.extend(((a, 1), (b, -1)))
    # End before start at equal timestamp: half-open request intervals.
    active = peak = 0
    for _t, delta in sorted(events, key=lambda e: (e[0], e[1])):
        active += delta
        if active < 0:
            raise AssertionError("negative active requests")
        peak = max(peak, active)
    if active:
        raise AssertionError("unfinished requests")
    return peak

def bucket_peak(starts, latencies, errors):
    intervals = [(float(a), float(a)+float(b))
                 for a,b,e in zip(starts,latencies,errors) if not e]
    if not intervals:
        return 0
    first = min(a for a,b in intervals)
    duration = int(math.ceil(max(b for a,b in intervals)-first))+1
    count = [0]*duration
    for a,b in intervals:
        for second in range(int(a-first),int(b-first)+1):
            count[second] += 1
    return max(count)

def value_from_metrics(path, name):
    txt = path.read_text()
    m = re.search(rf"^{re.escape(name)}\{{[^\n]*\}}\s+(\d+(?:\.\d+)?)$",txt,re.M)
    return float(m.group(1)) if m else None

def audit():
    assert exact_peak([0.1,0.6],[0.4,0.2],[None,None]) == 1
    assert bucket_peak([0.1,0.6],[0.4,0.2],[None,None]) == 2
    cases = {}
    for case in CASES:
        src = RESULTS / (case+".json")
        d = json.loads(src.read_text())
        peak = exact_peak(d["start_times"], d["latencies"],d["errors"])
        coarse = bucket_peak(d["start_times"],d["latencies"],d["errors"])
        assert peak <= d["max_concurrency"], (case,peak,d["max_concurrency"])
        assert coarse == d["max_concurrent_requests"], (case,coarse,d["max_concurrent_requests"])
        assert d["completed"] == 32 and d["failed"] == 0
        out = {
            "requests_completed": d["completed"],
            "configured_max_concurrency": d["max_concurrency"],
            "observed_true_peak_concurrency": peak,
            "reported_binned_peak_concurrency": d["max_concurrent_requests"],
            "duration_s": d["duration"],
            "input_tokens": d["total_input_tokens"],
            "output_tokens": d["total_output_tokens"],
            "output_tokens_s": d["output_throughput"],
            "total_tokens_s": d["total_token_throughput"],
            "mean_ttft_ms": d["mean_ttft_ms"],
            "median_ttft_ms": d["median_ttft_ms"],
            "p99_ttft_ms": d["p99_ttft_ms"],
            "mean_tpot_ms": d["mean_tpot_ms"],
            "p99_tpot_ms": d["p99_tpot_ms"],
            "raw_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        }
        cases[case] = out

    before, after = RESULTS/"prom_before.txt", RESULTS/"prom_after.txt"
    counters = {}
    for name in ("vllm:prefix_cache_queries_total","vllm:prefix_cache_hits_total"):
        left, right = value_from_metrics(before,name),value_from_metrics(after,name)
        counters[name] = {"before":left,"after":right,"delta":right-left if None not in (right,left) else None}

    fresh = cases["fresh_warm32"]
    reuse = cases["reuse_warm32"]
    result = {
        "experiment": "vllm independent prefix reuse audit 2026-11-16",
        "host":"OCTO-W03","gpu":"Quadro RTX 8000 GPU0 48GB",
        "model":"Qwen/Qwen3-0.6B, local weights","vllm_version":"0.33.0",
        "precision":"FP16","eager":True,"prefix_cache_enabled":True,
        "model_max_len":2048,"gpu_memory_utilization_limit":0.30,
        "workload":"Closed-loop maximum 4 client requests, 32 x ~832 input + 64 output tokens; seed 164; two repeated 768-token prefixes in reuse case.",
        "cases": cases,
        "controlled_reuse_vs_fresh": {
            "output_tokens_per_second_ratio":reuse["output_tokens_s"]/fresh["output_tokens_s"],
            "output_tokens_per_second_percent_gain":100*(reuse["output_tokens_s"]/fresh["output_tokens_s"]-1),
            "mean_ttft_ms_reduction":fresh["mean_ttft_ms"]-reuse["mean_ttft_ms"],
            "same_output_tokens":reuse["output_tokens"]==fresh["output_tokens"],
            "input_token_difference":reuse["input_tokens"]-fresh["input_tokens"],
        },
        "prometheus_prefix_counters_controlled_pair": counters,
        "methodology_limits": [
            "Small 0.6B model and legacy RTX 8000; not comparable to 552B Rubin NVL72",
            "Single trials per condition; random/fresh followed by repeated-prefix",
            "Server used eager execution; output token count from vLLM bench detailed traces",
            "Synthetic token distributions; client emitted tokenizer-alignment 404 warning",
            "Benchmark left temperature unspecified; server model generation defaults apply",
            "P99 estimates from 32 requests are fragile",
            "The reported peak_concurrent_requests metric uses coarse second bins and can exceed the configured concurrency."
        ]
    }
    (RESULTS/"audit.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"controlled":result["controlled_reuse_vs_fresh"],"prefix":counters,"true_peak":[(k,v["observed_true_peak_concurrency"],v["reported_binned_peak_concurrency"]) for k,v in cases.items()]},indent=2))

if __name__=="__main__":
    audit()
