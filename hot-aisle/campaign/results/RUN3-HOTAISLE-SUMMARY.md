# Run 3 · Hot Aisle MI300X arms: summary and cost correction (2026-09-24)

Seat: Hot Aisle `enc1-gpuvm004` (1x MI300X VM). Requested 00:08:55Z, SSH ready 00:10:57Z, deleted 02:52:29Z.
It was paid from Hot Aisle's credit, costed at list price ($2.99/h).

| Arm | Completed / scheduled | Correct (raw, registered) | Accepted | TTFT p50/p95/p99 | $/1k accepted, own window |
|---|---|---|---|---|---|
| Smoke (unscored, ~9 min) | 984 / 984 sent | 491 | 458 | 38 ms median | — |
| A/T0 · auto backend (ROCM_ATTN) | 8,622 / 8,622 | 4,371 | **4,336 (50.3 %)** | 53 / 155 / 571 ms | **$0.72** |
| A/T1 · forced ROCM_AITER_FA | 8,615 / 8,622 | 4,334 | 4,292 (49.8 %) | 60 / 202 / 1,119 ms | $0.73 |

**Whole seat, request to release, including smoke, setup and the idle gap:** 2.73 h, $8.15, 9,086 accepted → **$0.90 per 1k accepted**.

**Cost correction.** Each ledger's `modeled-lower-bound` ($1.08 for A/T0, $1.84 for A/T1) started its clock at the shared seat's `t_ssh`, so the later arm was charged for the earlier arms' time. The per-arm figures above use each arm's own `t_script_start` → `t_script_end`. Builder fix to make: on a shared seat, start an arm's clock at its own start and attribute seat overhead separately.

**Format, not capability.** A post-hoc re-grade of A/T0's completions after `evalplus.sanitize` (`run3-scored-a-t0/posthoc-sanitized/`) gives:
- HumanEval+: 24.4 % → 82.4 %
- MBPP+: 62.2 % → 67.2 %
- all requests: 4,371 → 6,192 correct

Roughly three quarters of HumanEval's losses come from the raw-completion output contract: stray fences, re-declared functions and test prints.

**Tuning depends on the workload.** Forcing ROCM_AITER_FA gave up to +46 % on 70B long-context work (Run 2 exploration). Here, on a short-prompt 30B MoE, it gives no gain and a worse tail.

**Still to run:** N/T0 (DigitalOcean H100) and arm C (DigitalOcean MI300X) under the same freeze. Pending the operator's doctl token.
