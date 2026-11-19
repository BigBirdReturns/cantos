# Native qualification of retry and resource accounting

The [portable evidence archive](evidence/retry-qualification-20261118.zip) and [checksum](evidence/RETRY-SHA256SUMS.txt) retain the actual model responses, isolated EvalPlus grades, dispatch journal, complete task timing, raw board samples, exact instrument source, input selection and independent reviews. Extract the archive and run `python -B verify.py` from its retry-qualification directory. Verification needs Python 3.10 or later; it performs no inference, Docker execution or GPU query.

## Observed result

The qualification ran Qwen3-0.6B through vLLM 0.33.0 on one Quadro RTX8000 and executed the existing pinned EvalPlus 0.3.1 image for every completed solution. The instrument completed and validated every task. The model solved one of eight tasks. This is evidence that the collection, grading, retry and resource path works with real inference, including exhausted failures; it is an insufficient model-quality result and establishes no model ranking or Hy4 performance.

| Recorded quantity | Observed value |
| --- | ---: |
| Offered task instances | 8 |
| First-pass accepted tasks | 1 |
| First-pass success rate | 12.5% |
| Eventually accepted tasks | 1 |
| Exhausted tasks | 7 |
| Solution attempts and HTTP requests | 22 |
| Retries across all offered work | 14 |
| Retries per accepted task, charging exhausted work | 14 |
| Retries among eventually successful tasks | 0 |
| Unresolved task outcomes | 0 |
| Transport-failed attempts | 0 |
| Complete campaign elapsed time | 307.520376210 s |
| Selected GPU board energy across that window | 20,659.407266 J |
| Selected GPU board joules per accepted task | 20,659.407266 J |
| Raw board power samples | 978 |
| Actual full operating expenditure | Unknown |

Every exhausted task received three attempts. The sole success passed its first attempt. The 14 retries therefore belong entirely to failed task chains. Reporting retries only for successful chains would hide all of that work. The campaign charges every attempt, elapsed interval and measured board joule to its actual accepted output.

Task receipts retain submit-to-terminal latency, including client queueing, all attempts, 0.1-second backoff and grading. Campaign wall time includes child preparation, endpoint probes and durable journaling. Concurrent task intervals overlap, so their summed duration is a separate quantity. Server startup and prior allocation lie outside the campaign window.

## Fixed inputs and source

The eight cases were selected before this run by positions 0, 4, 8, 12, 16, 20, 24 and 28 in the previously retained 32-case HumanEval+ workload. They are HumanEval/0, /20, /41, /61, /82, /102, /123 and /143. The selection was unchanged after outcomes arrived. One trial, one repetition and client concurrency two define this bounded instrument test.

Each task allowed three attempts with temperature zero, seed 1729, zero seed stride, disabled thinking and 512 maximum output tokens. Retries started the same fixed conversation with no correctness feedback or repair prompt. Repetition under this policy makes no statistical independence or correctness-improvement claim.

The measured source commit is `5fff1cd4e93afcd3a933f6841d2fb34364e8135b`. The archive contains its exact production Python bytes. Weights SHA256 is `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b`; tokenizer SHA256 is `aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4`. The served endpoint used FP16, eager execution, a 4096-token context, two maximum sequences, 0.15 GPU-memory utilization and disabled prefix caching. The existing 200 W power limit remained unchanged. Other host and GPU1 work could coexist; the result describes this observed allocation.

Generated Python executed only in image `sha256:803e956852925ff35f8d7a9f55a97fbcfad09a8dfa77a439f5b2ac537702563d`, with network disabled, a read-only root, dropped capabilities, no-new-privileges, non-root identity, one CPU, 4 GiB memory and a 128-PID bound. The complete-code normalizer, selected reference, exact solution mapping, raw response hashes, commands, image inspection, logs and base-plus outcomes are retained with each attempt. The successful native path used the actual local container, separately from the protocol fixtures. HumanEval/0 passed both base and plus tests. HumanEval/82 and /143 passed base tests but failed plus tests on every attempt, so both remained rejected. An independent read-only review passed 24 grouped checks, matched all 22 actual server POSTs to durable dispatches and isolated grades, reproduced the energy integral exactly, and confirmed endpoint, lease and grader-container cleanup.

## Resource boundary and interruption behavior

Raw NVIDIA board power samples bracket the complete campaign. The original Open Compute Ledger integrator applies piecewise-linear boundary interpolation and the trapezoidal rule under the sampling tolerance declared before collection. The resource receipt binds the exact campaign hash, observation identity, host boot clock, GPU UUID, sampling rule and raw journal hash.

This is gross selected-board energy, including resident-model idle, failed attempts and waiting while the CPU grader runs. It excludes CPU and host memory energy, the other GPU, server startup, facility overhead and financial spending. The board sensor is uncalibrated. The measurement establishes neither exclusive inference energy nor full-system energy. Full-system energy matters particularly for a future Hy4 deployment with host-memory offload.

The independent public-CLI qualification passed 70 checks on unchanged source: 39 arithmetic and command-exit checks, 15 integrity/interruption/timing checks and 16 resource-binding checks. Controlled HTTP fixtures and synthetic power/price inputs are labeled separately from this native test. They cover a task succeeding on its third attempt, permanent failures, transport failure, zero successful tasks, queue and backoff inclusion, tampered raw evidence, altered totals, wrong clocks/campaigns, incomplete telemetry and missing costs.

A process interrupted after POST dispatch leaves a durable request start and an unknown outcome. The journal retains the dispatch and refuses automatic replay or reuse of the output directory. It does not fabricate missing server completion or token billing. The native run ended with complete outcomes, stopped its owned endpoint and released its GPU lease.

## Hy4 terminal condition

The [pinned Hy4 readiness package](experiments/hy4-flash/README.md) identifies the instruction BF16 and FP8 artifacts, exact runtime metadata and native smoke/retry inputs. Its preflight retains an explicit blocked result for the inspected RTX8000 environment, absent Hy4 runtime and unverified local payloads. A compatible allocated machine, verified weights, actual kernel startup and accepted streamed smoke remain necessary before Hy4 measurements can exist. Base is a separate pretrained variant; comparing Base against FP8 would also change training stage.
