# Telemetry: measured facts from our own runs that the public pages do not show

Built 2026-09-29 from files on disk under `hot-aisle/campaign/` (Runs 1-3, ledger, availability, market, shop-eval counter). Every number below is recomputed by a script in this folder and has a row in `findings.jsonl` (ids `T01`..`T21`) with file paths and sha256. Producer is **ours** for everything here (imported market data is in EFFICIENCY.md).

**Evidence classes.** MANUAL.md defines `published_claim`, `operator_report`, `measured`, `derived`, `hypothesis`. It has no class named "modeled", but it uses "modeled" for cost windows (`modeled dedicated-equivalent`, `modeled allocation cost`), so the cost rows below carry `modeled` as the class and say so. `measured` = read from a run artefact; `derived` = arithmetic on measured artefacts; `modeled` = a rate times a chosen window; nothing here is an invoice.

**What "the front door" shows.** I checked `campaign/results/receipt-run3.html` and `data/run3/report.html` (the pages built for Run 3). They show: $0.74 and $1.20 per 1,000 accepted, accepted 4,336 and 4,280, TTFT p50 and p99, the selected attention/FP8 kernels, the tie price ($2.72/h), the sanitizer regrade (24.4% to 82.4%), $8.15 and $5.13 spent, and the $0.90 whole-seat figure. Everything else in this file is not on either page.

## 0. Read-first list (not shown on either page)

| # | Fact | Finding |
|---|---|---|
| 1 | 67.2% of A/T0's decode tokens went to requests that failed grading; 12.3% of requests hit the 1,024-token cap, used 41.0% of decode tokens and passed 18.4% | T15 |
| 2 | 99.2% of A/T0's rejected requests were wrong answers; only 35 correct answers (0.41%) missed the gates, all in the first 5 minutes | T07 |
| 3 | The 7 "failed" requests in the forced-backend arm are `client_concurrency_limit` events from our own 256-worker load generator, not server errors | T03 |
| 4 | The server never queued in any Run 3 arm; peak KV use was 3.6%, 3.8%, 13.2%; mean throughput was 9.4% of the 10-second peak | T16 |
| 5 | Run 2's long c32 cell is already at 92% KV; doubling to c64 halves throughput (x0.477) and multiplies median first-token time by 15.7 | T04 |
| 6 | Five cost windows for the same 4,336 accepted requests: $0.6908, $0.7201, $0.7434, $0.8971, $1.0845 | T12 |
| 7 | The July 27 Hot Aisle price rise ($1.99 to $2.99) moves the advantage over a $3.39 H100 from 46.3% to 19.3% | T13 |
| 8 | Time-to-SSH is 83-122 s; time-to-ready is 3.7-4.9 times longer | T10 |
| 9 | The DigitalOcean API said "available, regions empty" and a create then succeeded 57 s later | T11 |
| 10 | Forced ROCM_AITER_FA cut c1 first-token time 12.5% (long) and 7.7% (short) while leaving throughput unchanged | T02 |

## 1. Backend auto-selection vs forced ROCM_AITER_FA

### 1a. Run 2 (Llama-3.3-70B FP8-dynamic, 1x MI300X, vLLM 0.30.0) - measured (T01, T02)

Window: auto arm 2026-09-23 19:11-22:00 UTC; forced arm 22:01-22:26 UTC, same host `enc1-gpuvm002`, same image `vllm/vllm-openai-rocm@sha256:2e7da1ad...`, same flags plus `--attention-backend ROCM_AITER_FA`. Auto had 2 repeats on long cells (r0, r1) and 1 on short cells; forced had 1 repeat (r0). Auto repeat spread: long c8 0.2179 vs 0.2157 req/s, long c32 0.3032 vs 0.3016. Auto selected `ROCM_ATTN` ("incompatible backend TURBOQUANT ... overriding") and `RowWiseTorchFP8ScaledMMLinearKernel` in both arms.

| Cell | req/s auto (r0; r1) | req/s forced | Delta | TTFT p95 ms auto (r0; r1) -> forced | TTFT p99 ms auto (r0; r1) -> forced | Peak KV % auto -> forced |
|---|---|---|---|---|---|---|
| long c1 (8192 in / 512 out, 16 prompts) | 0.0633; 0.0634 | 0.0632 | -0.2%; -0.4% | 1,636; 1,627 -> 1,439 | 1,637; 1,628 -> 1,441 | 2.9 -> 2.9 |
| long c8 (64) | 0.2179; 0.2157 | 0.2796 | +28.3%; +29.6% | 17,786; 20,095 -> 9,560 | 19,234; 20,193 -> 10,863 | 23.1 -> 23.2 |
| long c32 (128) | 0.3032; 0.3016 | 0.4418 | +45.7%; +46.5% | 57,078; 57,348 -> 36,848 | 75,072; 75,750 -> 43,286 | 92.0 -> 92.7 |
| short c1 (2048 / 256, 16) | 0.1371 | 0.1371 | -0.0% | 366 -> 341 | 367 -> 342 | 0.8 -> 0.8 |
| short c8 (64) | 0.7813 | 0.8007 | +2.5% | 2,796 -> 2,473 | 2,801 -> 2,473 | 6.1 -> 5.7 |
| short c32 (128) | 1.5313 | 1.6700 | +9.1% | 11,161 -> 9,758 | 11,164 -> 9,761 | 23.4 -> 23.3 |
| short c64 (256) | 1.8273 | 2.0343 | +11.3% | 19,149 -> 16,830 | 22,281 -> 19,257 | 49.0 -> 48.7 |

Not on the front door: at c1 throughput is unchanged but first-token time falls (long p50 1,629 -> 1,426 ms, -12.5%; short p50 364 -> 336 ms, -7.7%). DISCLOSURES says "c1: unchanged", which is true of req/s only. The forced arm ran about 2.5 hours after the auto arm; time of day is a confound. Post-hoc, unregistered (EXPLORE.md).

### 1b. Run 3 (Qwen3-Coder-30B-A3B FP8, 8,622 requests, one hour of Azure code trace) - measured (T03)

| | A/T0 auto (ROCM_ATTN) | A/T1 forced (ROCM_AITER_FA) | Ratio |
|---|---|---|---|
| TTFT p50 / p95 / p99, ms from send | 52.9 / 155.0 / 568.9 | 60.1 / 202.4 / 1,118.9 | 1.14 / 1.31 / 1.97 |
| TTFT p50 / p95 / p99, ms from scheduled arrival | 56.4 / 171.0 / 572.6 | 63.5 / 216.9 / 1,123.5 | |
| E2E p95 from scheduled arrival, ms | 12,363 | 12,809 | 1.04 |
| Correct / accepted | 4,371 / 4,336 | 4,334 / 4,292 (-1.0%) | |
| Completed / failed | 8,622 / 0 | 8,615 / 7 | |

The 7 failures are request indices 2389-2430, each `error: client_concurrency_limit`, `end_ts == scheduled_ts`: the client's 256-worker cap was hit during a burst. They are load-generator saturation, not server errors, and they cost 0.08% of the run. On this workload the forced tier gave no throughput gain and a doubled p99, in line with RUN3-RESULTS item 4, but the "7 failed" line in the table on the front door reads as a server fault.

## 2. KV-cache overload cells and what they measure - measured (T04)

Run 2, auto arm, long shape (8,192 in + 512 out = 8,704 tokens per request). KV cache: 300,192 tokens (auto), 299,440 (forced). Tokens in flight by construction = concurrency x 8,704.

| Cell | In flight (tokens) | req/s | TTFT p50 | TTFT p95 | E2E p50 | Peak KV | Max waiting / running | Duration |
|---|---|---|---|---|---|---|---|---|
| c1 | 8,704 | 0.0633 | 1.6 s | 1.6 s | 15.8 s | 2.9% | 0 / 1 | 253 s |
| c8 | 69,632 | 0.2179 | 9.9 s | 17.8 s | 36.7 s | 23.1% | 1 / 8 | 294 s |
| c32 | 278,528 (92.8% of cache) | 0.3032 | 16.7 s | 57.1 s | 104.7 s | 92.0% | 27 / 32 | 422 s |
| c64 | 557,056 (1.9x) | 0.1445 | 261.5 s | 262.4 s | 479.7 s | 100% | 57 / 36 | 1,772 s |
| c128 | 1,114,112 (3.7x) | 0.1436 | 712.9 s | 748.0 s | 881.9 s | 99.9% | 117 / 36 | 1,783 s |

What they measure: c64 and c128 measure a saturated KV pool with a queue (running is capped near 36, the number of requests the pool holds), so their throughput is set by the pool, not by compute (c128 / c64 = 0.994). c32 is not a "clean capacity" cell either: it already holds 92% of the pool, and it is the cell behind the "+46%" headline. c64 vs c32: throughput x0.477 at 2x concurrency, TTFT p50 x15.7. r1 repeats agree (c64 0.1430 req/s, c128 0.1426). No failures anywhere (256/256 completed). **Preemption count is not measured**: serve.log has zero "preempt" lines and no metrics were scraped, so "preemption" in DISCLOSURES is an inference from the KV numbers. Cell attribution: arm-log stamps a cell at its start (next stamp minus this stamp = duration + ~15 s).

Short shape peaks: c64 49.0% KV (256 prompts x 2,304 tokens in flight = 147,456 of 300,192).

## 3. Unequal software between arms - measured (T05)

| Run | AMD arm | NVIDIA arm |
|---|---|---|
| 1 (2026-09-23) | vLLM `0.27.1.dev5+gf46a9dfe2.d20260827.rocm100`, image `rocm/vllm@sha256:30761c21...`, ROCm 7.2.4, tuned MI300X MoE config in image | vLLM 0.30.0, `vllm/vllm-openai@sha256:8a69ffad...`, driver 580.173.02, default FP8 MoE config |
| 2 | vLLM 0.30.0, `vllm/vllm-openai-rocm@sha256:2e7da1ad...`, ROCm 7.2.3 | none run |
| 3 (2026-09-24) | same 0.30.0 ROCm image: `ROCM_ATTN` (A/T0) or `ROCM_AITER_FA` (A/T1); `AiterFp8BlockScaledMMKernel`; AITER FP8 MoE backend | 0.30.0 CUDA image: `FLASH_ATTN`; `FlashInferFp8DeepGEMMDynamicBlockScaledKernel`; TRITON FP8 MoE backend; FlashInfer sampling |

Consequences not stated on the front door: (1) the same AMD card ran two different vLLM versions and images between Run 1 and Runs 2-3, so its Run 1 and Run 3 numbers are not the same software; (2) Run 3's "same vLLM" claim holds for version only, not for kernels; (3) Run 1's serve logs were never collected (the tuned-config statement is from live observation); (4) KV pool sizes differ: 1,484,848 tokens (A/T0), 1,484,960 (A/T1), 430,592 (N/T0). The Run 3 comparison is MANUAL.md's "different complete configuration" label.

## 4. The E2E gate hold on ROCm and derived E2E - measured / derived (T06)

The `rocm/vllm` 0.27.1.dev image writes no per-request `latencies`, so the engine holds the E2E gate on the AMD arm and scores both arms on TTFT only (engine files: `e2e_ms: null`). The AMD cell JSONs do carry an aggregate `p95_e2el_ms` field and the `ttfts`/`itls` lists, so E2E per request can be derived as TTFT + sum(ITL):

| Cell | MI300X derived E2E max (s), 3 repeats pooled | H100 derived E2E max (s) | MI300X `p95_e2el_ms` r0/r1/r2 | H100 `p95_e2el_ms` r0/r1/r2 |
|---|---|---|---|---|
| c1 | 2.064 | 1.185 | 2,023 / 2,022 / 2,023 | 1,168 / 1,169 / 1,169 |
| c8 | 2.826 | 2.212 | 2,738 / 2,745 / 2,738 | 2,135 / 2,201 / 2,132 |
| c32 | 3.988 | 4.459 | 3,908 / 3,955 / 3,913 | 4,122 / 4,150 / 4,212 |
| c64 | 5.342 | 7.379 | 5,290 / 5,282 / 5,265 | 7,115 / 7,024 / 7,039 |

The registered gate is p95 E2E <= 15 s. The largest derived value on either arm is 7.38 s, so the hold changed no cell's qualification. The Run 1 ledger's note says the gate was held on both arms "for symmetry" but its H100 cell rows say `e2e_gate: applied`; the engine outputs (`e2e_ms: null` on both) match "held". Run 3 applies E2E <= 60 s on all arms (measured E2E p95 from scheduled arrival: 12,363 / 12,809 / 12,068 ms), so this concern is Run 1 only.

## 5. Accepted vs scheduled and rejected share - measured / derived (T07, T20)

Run 3, 8,622 scheduled per arm. Accepted = EvalPlus base+plus pass AND first token <= 1 s AND done <= 60 s from scheduled arrival. Recomputed from `replay/requests.jsonl` and `grade/evaluation.json`; the counts reproduce the published 4,336 / 4,292 / 4,280.

| | A/T0 | A/T1 | N/T0 |
|---|---|---|---|
| Accepted (share of scheduled) | 4,336 (50.29%) | 4,292 (49.78%) | 4,280 (49.64%) |
| Correct | 4,371 | 4,334 | 4,329 |
| Incorrect (share of scheduled) | 4,251 (49.30%) | 4,288 (49.73%) | 4,293 (49.79%) |
| Correct but TTFT > 1 s | 35 | 42 | 49 |
| Correct but done > 60 s | 0 | 0 | 0 |
| Rejected because incorrect, share of rejected | 99.18% | 99.03% | 98.87% |
| Where the latency-only misses fall | all in the first 5-minute window | all in the first window | all in the first window |
| HumanEval+ correct / 2,624 | 640 (accepted 637) | 635 (627) | 569 (552) |
| MBPP+ correct / 5,998 | 3,731 (3,699) | 3,699 (3,665) | 3,760 (3,728) |

A/T0 acceptance by class: HumanEval+ 24.3% (637/2,624), MBPP+ 61.7% (3,699/5,998). The "50.3% accepted" is a blend of those two, weighted by the task mix (30.4% HumanEval). Across vendor stacks HumanEval+ correct differs by 11.1% (640 vs 569) while A/T0 vs A/T1 differ by 0.8% (single runs at temperature 0.2, so noise and stack effect are not separated; class `measured`, confidence low). In the first 5-minute bucket A/T0 completed 736 requests and accepted 301 of 336 correct.

## 6. TTFT p50 / p95 / p99 per arm - measured (T08, T09)

### Run 3 (ms)

| Arm | Clock | p50 | p95 | p99 | Max |
|---|---|---|---|---|---|
| A/T0 auto | from send (page engine's `ttfts`) | 52.9 | 155.0 | 568.9 | |
| | from scheduled arrival (acceptance clock) | 56.4 | 171.0 | 572.6 | 3,534.9 |
| A/T1 forced | from send | 60.1 | 202.4 | 1,118.9 | |
| | from scheduled arrival | 63.5 | 216.9 | 1,123.5 | 3,965.3 |
| N/T0 H100 | from send | 34.7 | 76.2 | 2,233.6 | |
| | from scheduled arrival | 35.4 | 77.9 | 2,234.2 | 9,767.8 |

Published p99: 571 ms (A/T0) and 2,254 ms (N/T0); both are within 0.9% of either clock. The H100 has the best p50 and p95 and a p99 3.9 times the MI300X's; the front door shows p50 and p99, not p95. Client send lag (scheduled to send) is p50 2.6 / p95 12.1 / p99 41.8 ms on A/T0 and 0.6 / 2.3 / 5.9 ms on N/T0.

### Run 1 (random 2048 in / 256 out, 200 prompts x 3 repeats per cell, ms, min-max over repeats)

| Cell | MI300X p50 | MI300X p95 | MI300X p99 | H100 p50 | H100 p95 | H100 p99 | req/s MI300X | req/s H100 |
|---|---|---|---|---|---|---|---|---|
| c1 | 101-102 | 105-107 | 107-110 | 66-67 | 68-69 | 71-72 | 0.496 | 0.859-0.860 |
| c8 | 85-98 | 145-174 | 157-186 | 223-244 | 284-288 | 293-299 | 3.006-3.027 | 3.947-4.004 |
| c32 | 123-151 | 323-347 | 328-384 | 443-445 | 831-921 | 1,060-1,069 | 7.801-7.889 | 8.179-8.283 |
| c64 | 173-216 | 649-697 | 693-766 | 468-509 | 1,887-1,913 | 2,069-2,119 | 11.476-11.683 | 10.523-10.604 |

The H100 is 1.5x faster at c1 and 2.4-3.2x slower in median first token from c8 up (c8 2.5x, c32 3.2x, c64 2.4x); at c64, 118 of 600 H100 requests exceed 1 s (15 of 600 at c32), against 0 of 600 on the MI300X. Steady-state cost per 1,000 requests at list (engine): MI300X $1.6751 / $0.2751 / $0.1057 / $0.0717 at c1/c8/c32/c64; H100 $1.4253 / $0.3076 / $0.1526 / $0.1443 (c64 accepts 80.3%, c32 97.5%). Cost at the best cell is 23.4x lower than at c1 on the MI300X and 9.3x lower on the H100 (T14).

## 7. Time-to-SSH, time-to-ready and provisioning outcomes per provider - measured (T10, T11)

Sources: `availability/observations.jsonl` (30 rows, sha256 70b94218...), `ledger-times.json`, `closure.json`, ledger examples. Single observations; the counter records mark `measured_3x: false` for both providers.

| Provider / SKU | Event | Observed | Note |
|---|---|---|---|
| DigitalOcean gpu-h100x1-80gb, nyc2 | Run 1 create to SSH | 60 s | console create, clock approximate (few minutes) |
| | Run 3 create to active / SSH | 56 s / 83 s | API `doctl` create 04:08:03Z, active 04:08:59Z, SSH 04:09:26Z |
| | SSH to ready (health + warm-up) | 9.97 min (Run 1), 6.77 min (Run 3) | ready = weights, compile, health, warm-up |
| | Delivered creates | 2 of 2 succeeded | droplet 603084148 and 603208981; deleted via doctl 05:17:52Z |
| DigitalOcean MI300X (nyc2, tor1) | Listing | out_of_capacity, 4 rows (2026-09-23 18:55, 18:56; 2026-09-24 04:08, 05:19) | never provisioned; arm C never ran |
| DigitalOcean H200 | Listing | out_of_capacity in nyc2, ric1, tor1, mkc1, mem1, ams3 (2026-09-23 19:08-19:13) and by API 04:08, 05:19 | 8 rows |
| DigitalOcean H100 x8 | Listing | out_of_capacity, nyc2 (2026-09-23) | 1 row |
| Hot Aisle enc1 vm-mi300x-1x | Run 3 request to SSH | 122 s | requested 00:08:55Z, SSH 00:10:57Z; TUI provision |
| | SSH to ready | 7.62 min (smoke, 00:10:57 to 00:18:34); 34.17 min to A/T0 ready (includes the smoke) | A/T1 restart to ready 3.7 min |
| | Delivered creates | 2 of 2 succeeded | Run 1 2026-09-23 18:17Z (SSH time not recorded), Run 3 2026-09-24 00:08Z |
| RunPod MI300X | Prior-session note | out_of_stock, 2026-09-23 | recorded from memory, time unknown |

Ratio of SSH-to-ready over request-to-SSH: 4.9 (DigitalOcean Run 3: 406 s / 83 s), 3.7 (Hot Aisle smoke: 457 s / 122 s).

**Listing vs delivery.** At 04:08:02Z on 2026-09-24 the DigitalOcean API returned `available=true` with `regions=[]` for the H100 (rows 18-19; the note reads "regions list empty => no capacity"). One second later the create was submitted and succeeded in nyc2. The availability README already says `available`/`regions` flags may not move with capacity; this is the first paired comparison and the flag was wrong in the pessimistic direction. The 2026-09-23 19:14 H100 attempt did not complete because the browser froze (arm skipped, not a stock-out).

## 8. Cost windows, and why they differ - modeled (T12, T17, T21)

All at undiscounted list ($2.99/GPU-hour credit-paid Hot Aisle; $4.41 self-paid DigitalOcean). None is an invoice; invoices are unreconciled (T18).

| Figure | $/1,000 accepted | Numerator (window) | Denominator | Source |
|---|---|---|---|---|
| In-page headline | **0.6908** | 3,606.58 s of replay x $2.99/h = $2.995 (page prints "$3.00") | 4,336 accepted | `data/run3/headline.json`, `report.html` |
| Arm script window only | 0.7201 | 62.65 min = $3.1221 | 4,336 | RUN3-HOTAISLE-SUMMARY prints $0.72 |
| Own-seat equivalent (published $0.74) | **0.7434** | 2.03 min provisioning + 62.65 min = 64.68 min = $3.2235 | 4,336 | receipt, RUN3-RESULTS |
| Whole shared seat (published ~$0.90) | **0.8971** | 163.57 min (00:08:55Z to 02:52:29Z) = $8.1511 | 4,336 + 4,292 + 458 (smoke) = 9,086 | RUN3-HOTAISLE-SUMMARY |
| Ledger `modeled-lower-bound` (**$1.0845**) | **1.0845** | `t_ssh` 00:10:57Z to `t_work_end` 01:45:19Z = 94.37 min = $4.7026 | 4,336 | `ledger/run3-run3-scored-a-t0.ledger.json` |

Why they differ. (1) $0.6908 counts only the hour of replay; the rest add provisioning ($0.7434), then smoke, warm-up, A/T1 and gaps ($0.8971). (2) $1.0845 starts the clock at the seat's first SSH but charges it to A/T0 alone, so it includes the 34.2 minutes of smoke and warm-up before A/T0 began; the same builder gives A/T1 $1.838 (158.3 min from the same `t_ssh`). RUN3-HOTAISLE-SUMMARY records the fix needed (start a shared-seat arm's clock at its own start). (3) $0.72 vs $0.74 differ by exactly the 2.03 min provisioning. The largest to smallest ratio is 1.57. MANUAL.md says not to combine or average them. Other windows on the same arms: A/T1 own window $0.7314 ($0.7550 with provisioning); DigitalOcean N/T0 $1.1990 (69.82 min request to release = $5.1315), $1.1339 for the 66.03 min script window and $1.0322 on the replay-seconds basis (derived, not published; would put Hot Aisle 33.1% cheaper on that basis vs 38.0% on the receipt basis).

**Seat overhead (T17).** Of the 163.57 billed minutes, scored work was 125.65 (A/T0 62.65 + A/T1 63.00 = 76.8%); the smoke was 15.86 min and setup/gaps 22.1 min. Whole-seat cost is 20.7% above the own-window figure.

**Run 1 windows.** Cell-level: MI300X c64 $0.0717 vs H100 c32 $0.1526 per 1,000 = 53.0% cheaper (DISCLOSURES "53%"). Whole-run lower bound including all cells: $0.9248 vs $0.9802 = 5.7% (ledger examples). Both stand under their labels.

## 9. The Hot Aisle price change and the July economics - modeled (T13)

Series (OpenComputePrices `latest-data`, source getdeploying, on-demand): Hot Aisle 1x/2x/4x MI300X at **$1.99** from 2026-03-22 to 2026-07-27 (118 days) and **$2.99** from 2026-07-27 to 2026-07-29 (3 days); 07-27 carries both. The 8x on-demand $1.99 listing ends 2026-05-20 and is replaced by an 8x reserved $3.39. Change: +50.25%. July's monthly median is therefore $1.99 (MARKET.md), not the $2.99 in use since.

| Hot Aisle price | H100 comparator | Hot Aisle $/1k | H100 $/1k | Hot Aisle cheaper by |
|---|---|---|---|---|
| $1.99 (to 2026-07-26) | $3.39 (getdeploying) | 0.4948 | 0.9216 | 46.3% |
| $2.99 (2026-07-27 on) | $3.39 | 0.7434 | 0.9216 | 19.3% |
| $2.99 as run | $4.41 as run | 0.7434 | 1.1990 | 38.0% |
| $2.99 | $6.74 (skypilot value for the same DigitalOcean H100) | 0.7434 | 1.8323 | 59.4% |

(The last row is derived by scaling the H100 cost with price; the by-date file retains 6.74 but does not compute a cost at it.) Break-even H100 price against Hot Aisle $2.99: **$2.7345/h** from unrounded costs; the receipt's $2.72 comes from rounded 0.74 and 1.20. At Hot Aisle $1.99 the tie is $1.82/h. Run 3's economics moved by 27 points of advantage on a list-price change with no GPU rerun. DigitalOcean's MI300X is $1.99 in the aggregator series and $2.59 in the staged table that DISCLOSURES cites.

## 10. Anything else found

- **Where decode tokens went (T15).** A/T0: 2,649,637 output tokens; 1,780,298 (67.2%) on requests that failed grading; 1,062 requests (12.3%) ended at `length` (the 1,024 cap) and took 1,087,488 tokens (41.0%), passing 18.4% vs 55.2% for `stop`-terminated requests. Similar on A/T1 (41.3% of tokens on 12.4% of requests) and N/T0 (39.4% on 11.9%). Post-hoc sanitizer regrade (verified: HumanEval+ 2,161/2,624 = 82.4%): total correct 4,371 to 6,192 (+41.7%), deadline-qualified accepted unmeasured.
- **Utilisation (T16).** Waiting was 0 at all 214/215/217 ticks; peak running 129/141/147 of 256; peak KV 3.6%/3.8%/13.2%; median generation throughput 882/946/915 tok/s vs 10-s peak 7,808/7,566/8,693 tok/s; A/T0 mean 735 tok/s = 9.4% of its peak. The trace has bursts to 531 arrivals a minute and gaps to 217 s. Ticks are ~10 s and only when active, so true peaks are unseen.
- **Spend records disagree (T18).** ~$15 of the $200 credit (DISCLOSURES, 2026-09-23 seat; derived window 18:17-22:35 UTC = 4.30 h = $12.86 at list), $8.15 (Run 3 seat), and a counter record assigning $15.0 modeled cost to the 2026-09-24 evaluation. DigitalOcean: $5.13 (Run 3), $4.05 (counter, Run 1 arm B), $2.22 (Run 1 ledger lower bound). No `billed_usd` is entered anywhere.
- **Counter-record minimums (T19, class `published_claim`/`operator_report`).** Hot Aisle 2x VM 1-hour minimum, 8x bare metal $3.39/GPU-h with a 1-month minimum (about $19,798 for 8 GPUs x 730 h, derived); DigitalOcean minimum disputed between pricing page (5 min) and docs (60 s); new DigitalOcean accounts start at GPU limit 0 (ticket, under a day). Tenant hygiene, firewall posture and support response are `unobserved` for both.
- **In-page report is A/T0-only (T21).** `headline.json` carries the DigitalOcean H100 as `price_only` with `required_rate_to_tie` $1.7732/h, while the receipt states $2.72 and the exact figure is $2.73: three tie prices for one question.
- **Run 1 ledger sustained-window fields (not a finding row).** The 12-cell sweeps cover 1,675 s (MI300X) and 1,107 s (H100), so neither meets the ledger's 60-minute sustained requirement; only Run 3 does.

## Not measured, or could not be verified

- Preemption counts in Run 2 (no metric scraped, 0 log lines).
- Run 1 serve logs (never collected); the tuned-MoE-config statement is unverified from files.
- Any invoice or credit-balance line; the Hot Aisle delete time of 02:52:29Z is operator-reported.
- Repeat-to-repeat variance for Run 3 (one run per arm).
- Energy, network path, tenant hygiene, support, cold start.

## Reproduce

`WORK=<dir> python telemetry_run1.py`, `telemetry_run2.py`, `telemetry_run3.py`, `telemetry_run3_tokens.py`, `telemetry_run3_util.py`, `telemetry_costs.py` (stdlib; they read `hot-aisle/campaign/results/` relative to this folder). `make_findings.py` rebuilds `findings.jsonl`.
