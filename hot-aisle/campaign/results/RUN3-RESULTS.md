# Run 3 results · real graded coding work on real traffic, per run (2026-09-24)

**Workload.**
- Tasks: 542 EvalPlus tasks (HumanEval+ 164, MBPP+ 378), cycled.
- Arrivals: the Azure LLM inference CODE trace, 2023, replayed for one hour at factor 0.95. That is 8,622 requests, very bursty: up to 531 arrivals in a minute, gaps up to 217 s.
- Model: Qwen3-Coder-30B-A3B-Instruct-FP8 on vLLM 0.30.0 on both vendors.
- **Accepted** = EvalPlus base and plus tests pass, first token ≤ 1 s, and done ≤ 60 s from the scheduled arrival.
- Freeze: `run3/freeze-2026-09-24/` (commit 0b032ac). The smoke run came first and is unscored.

| | A/T0 · Hot Aisle 1x MI300X | A/T1 · same, forced ROCM_AITER_FA | N/T0 · DigitalOcean 1x H100 |
|---|---|---|---|
| List price | $2.99/h (Hot Aisle credit) | $2.99/h (credit) | $4.41/h (self-funded) |
| Backends (from serve.log) | ROCM_ATTN · AiterFp8BlockScaledMMKernel | ROCM_AITER_FA · AiterFp8BlockScaledMMKernel | FLASH_ATTN · FlashInferFp8DeepGEMMDynamicBlockScaledKernel (MoE: TRITON) |
| Completed / failed | 8,622 / 0 | 8,615 / 7 | 8,622 / 0 |
| TTFT p50 / p95 / p99 | 53 / 155 / **571** ms | 60 / 202 / 1,119 ms | **35 / 76** / 2,254 ms |
| Correct (raw, registered) | 4,371 | 4,334 | 4,329 |
| **Accepted** | **4,336 (50.3 %)** | 4,292 (49.8 %) | 4,280 (49.6 %) |
| **$ / 1k accepted, whole run** (request → release) | **$0.74** (own-seat equivalent, 64.7 min) | $0.73 (own window) | **$1.20** (69.8 min, fully closed ledger) |

## What it says

1. **Hot Aisle is ~38 % cheaper per accepted closure, per whole run, at list prices.** Both machines did essentially the same work: accepted counts are within 1.3 %. So the gap is price. The H100 is quicker in the typical case (TTFT p50 35 ms against 53 ms). The MI300X holds a far tighter tail through the bursts (p99 571 ms against 2,254 ms).
2. **At H100 prices below ~$2.72/h the ranking flips** (4.41 × 0.74 / 1.20):

   | H100 $/h | $ / 1k accepted |
   |---|---|
   | 2.99 | $0.81 |
   | 2.49 | $0.68 |
   | 1.99 | $0.54 |

   Against Hot Aisle's $0.74 at $2.99/h, the price you rent at decides it, not the silicon.
3. **Output format dominates correctness.** This is labelled post-hoc: A/T0 re-graded after `evalplus.sanitize` goes from HumanEval+ 24.4 % to **82.4 %**, and from 4,371 to 6,192 total correct. That is ~1.4× as many correct outputs from the same retained run. This post-hoc regrade counts correct outputs only; the intersection with the registered TTFT and completion deadlines has not been recomputed, so the change in accepted closures remains unmeasured.
4. **Tuning is workload-specific.** Forcing ROCM_AITER_FA gave up to +46 % on 70B long-context work (Run 2 exploration). On this short-prompt MoE it gives no gain and doubles the p99 TTFT.
5. **Availability is part of the cost.** The DigitalOcean MI300X (arm C) and H200 listed no capacity in any region all night (API `regions=[]`), so arm C did not run. Hot Aisle had one 1x VM. Logged in `availability/observations.jsonl`.

## Money actually spent

- Hot Aisle credit: about $8.15 for the seat (smoke + A/T0 + A/T1, 00:08:55–02:52:29Z).
- Operator cash: DigitalOcean H100 ~$5.13 (04:08:03–05:17:52Z).

## Caveats

- One run per arm, no repeats. HumanEval+ correct counts vary run to run (A 640, N 569) under temperature 0.2.
- The A/T0 whole-run figure uses its own-seat equivalent: provisioning latency plus its arm window. Its actual seat was shared with the smoke and A/T1 (whole seat $0.90/1k across 9,086 accepted).
- Invoices are not reconciled yet. Grader-blind tasks: HumanEval/32, Mbpp/255, Mbpp/392 (kept in the denominators).

**Correction (2026-09-24).** Item 3 originally stated: “A client that strips fences and test scaffolding gets ~1.4× the accepted closures on the same hardware and bill.” The sanitizer regrade established a correctness increase, not the deadline-qualified acceptance increase required by the registered definition. The original measured counts above are unchanged.
