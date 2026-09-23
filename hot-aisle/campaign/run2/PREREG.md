# Run 2 · pre-registration

Frozen before any Run 2 machine starts serving. This file and `arm2.sh` are committed first; that commit is the registration. Nothing here changes after results exist. Run 1 stays as recorded, unchanged.

**Question.** On a model whose weights stress GPU memory, what does one accepted request cost on Hot Aisle's 1x MI300X, against the single NVIDIA GPU a customer would rent for the same model?

**Why this workload.** Run 1 (a 30B MoE that fits any 80 GB card) was NVIDIA's home turf. A 70B dense model at FP8 (72.7 GB of weights) is the everyday case where memory capacity decides batch size.

## Pinned

- Model `RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic` @ `f50dbad2c84590ca17dc51e207c34321b65ff14b`. Vendor-neutral quantization, ungated, same bytes on every arm.
- vLLM 0.30.0 on both vendors. CUDA `vllm/vllm-openai@sha256:8a69ffad…` (Run 1's image). ROCm `vllm/vllm-openai-rocm:v0.30.0` @ `sha256:2e7da1ad…`.
- Serve flags, identical on every arm: `--max-model-len 16384 --max-num-seqs 256 --gpu-memory-utilization 0.90 --no-enable-prefix-caching`. KV cache dtype left at default on both.
- Vendor tuning, declared: AMD `VLLM_ROCM_USE_AITER=1`, AMD's documented recommendation, which the ROCm image does not set by default. NVIDIA: image defaults, with the attention backend auto-selected and recorded in `serve.log`. No hand-tuned kernel configs on either side.
- Client: `vllm bench serve` inside the serving container. Random dataset, `--ignore-eos`, seed 7 + repeat, request rate inf. One unrecorded warm-up.

## Cells (3 repeats each)

| shape | in / out | concurrency : prompts |
|---|---|---|
| long (primary) | 8192 / 512 | 1:16 · 8:64 · 32:128 · 64:256 · 128:256 |
| short (continuity with Run 1) | 2048 / 256 | 1:16 · 8:64 · 32:128 · 64:256 |

Prompt counts scale with concurrency so each cell runs at least two full waves. They are fixed here and not tuned later.

## Gates

A cell qualifies only if every repeat meets all three limits.

- long: p95 TTFT ≤ 3000 ms, p95 E2E ≤ 40 s, failed ≤ 1 %
- short: p95 TTFT ≤ 1000 ms, p95 E2E ≤ 15 s, failed ≤ 1 %

Also reported, but not used to pick a winner: per-request acceptance from the detailed traces (a request counts as accepted if it completed and its own TTFT and E2E meet the gate), and a gate-sensitivity table with the TTFT gate from 500 ms to 5 s.

## Metric

Cost per 1k requests = hourly list price ÷ measured requests per second, per qualifying cell. Headline: each arm's cheapest qualifying cell per shape. Every cell, including failures, stays in the receipt.

## Arms and prices (list, dated 2026-09-23)

- **A** · Hot Aisle 1x MI300X VM, $2.99/GPU-hr. Compute paid from a $200 credit given by Hot Aisle; this is disclosed.
- **H** · DigitalOcean 1x H200 141 GB, $4.47/GPU-hr, self-funded. The primary comparator.
- **N** · DigitalOcean 1x H100 80 GB, $4.41/GPU-hr, self-funded, optional. 72.7 GB of weights is not expected to load at 0.90 utilization. If attempted, the load failure is recorded as the result.
- Price sensitivity is reported with other providers' dated list prices for H200 and H100. The headline uses the prices above.

## Equivalence

Three fixed prompts, greedy decoding, 64 tokens, saved per arm as `smoke-*.json`. This is a smoke check that both arms serve the same model, not a quality evaluation.

## Stop rules

- No health within 40 min: stop and record the log.
- Watchdog: 150 min per arm.
- Self-funded spend ceiling: $50 across all Run 2 NVIDIA arms.
