# Disclosures · first qualified workload campaign (2026-09-23)

Read this before any number from `results/`. Written after two independent reviews (Fable, Astra) of the campaign.

## Funding and relationship
- The Hot Aisle arms ran on a **$200 credit given by Hot Aisle** to the Second Run team. Second Run is pitching Hot Aisle a paid engagement. Costs are computed at **undiscounted list price** ($2.99/GPU-hr), not at the credit.
- The DigitalOcean arm was self-funded at list price ($4.41/GPU-hr).

## Run 1 (Qwen3-Coder-30B-A3B FP8, random 2048/256, c1/8/32/64 × 3)
**Registered scoring first.** `identity.json` registered cell-level gates: p95 TTFT ≤ 1000 ms, p95 E2E ≤ 15 s, failed ≤ 1 %.
- Under that rule the H100's cheapest qualifying cell is c32 ($0.153 per 1k requests); its c64 cell fails (p95 TTFT 1.9 s). The MI300X qualifies at c64 ($0.072 per 1k). **Hot Aisle is 53 % cheaper at DigitalOcean list price.**
- **Post-hoc scoring (declared).** After seeing the data, both arms were also scored per request by the page's engine (`run1-engine/`, commit 60133ff): a request counts if its own TTFT ≤ 1000 ms. The results are H100 $0.144 per 1k (c64, 80 % of requests accepted) and MI300X $0.072 (c64, 100 %), a 50 % gap. These are two different claims and are shown as such.
- **E2E gate.** The ROCm image (vLLM 0.27.1-dev) does not write per-request latencies, so the engine holds the E2E gate on the AMD arm. Both arms are therefore scored on TTFT only. Derived AMD per-request E2E (ttft + Σ itl) peaks at 5.34 s. This is supporting evidence, not a restored gate.
- **Unequal software.** The CUDA arm ran vLLM 0.30.0 with the *default* FP8 MoE kernel config (no tuned file ships for H100). The ROCm arm ran vLLM 0.27.1-dev (build of Aug 27), whose image includes a *tuned* MI300X MoE config. The serve logs noting this were observed live but were not collected into the receipt.
- **Where Hot Aisle loses.** At c1 the MI300X costs 17.5 % more per request (the H100 is ~1.7× faster single-stream), and the H100 is also faster at c8. Raw throughput at c64 is near parity (10.6 against 11.6 req/s). **Most of the gap is price.** Price sensitivity, with the H100 at c32 against the MI300X at c64:

  | H100 $/GPU-hr | Hot Aisle cheaper by |
  |---|---|
  | 4.41 (DigitalOcean list) | 53 % |
  | 2.99 | 31 % |
  | 2.49 | 17 % |

- **Coarse grid.** The H100 may qualify somewhere between c32 and c64 (untested).
- **Not measured.** Output quality or correctness; startup and idle time; billed invoices; network or remote-client effects (the client ran on the serving host); cold cache.
- **Allocation.** Both arms ran on 1 GPU with tensor parallel 1. `env.normalized.json` in each arm states this and fixes two receipt defects without touching the raw files: the AMD `env.json` has tab characters that break strict JSON parsing, and `image` is empty in both. Each raw `env.json` stays byte-identical so `MANIFEST.sha256` still verifies.
- **Arm C not run.** The planned control, a DigitalOcean MI300X at $2.59 (same silicon, second price), was dropped by the operator on 2026-09-23, and was also out of capacity in every region checked that evening. It would likely have shown the same silicon cheaper than Hot Aisle at list. No claim here says Hot Aisle is the cheapest MI300X provider.

## Run 2 (Llama-3.3-70B FP8)
- **No NVIDIA comparator.** DigitalOcean H200 was out of capacity in all six regions. The H100 arm was skipped, since 72.7 GB of weights exceeds ~72 GB usable. Run 2 therefore makes no comparative claim.
- **As registered, it could not be completed.** About 80 min per repeat cannot fit three repeats in the registered 150-min watchdog. Long c64/c128 exceed the 300k-token KV cache by construction, so those cells measure preemption and overload. A sample of 16 prompts at c1 makes p95 close to the maximum.
- **The AMD "default" path is AITER-enabled and auto-selected.** vLLM picked `ROCM_ATTN` and a torch FP8 GEMM fallback. `EXPLORE.md` (commit 59ca344) is a labelled post-hoc pass that forces `ROCM_AITER_FA`. It is shown only side by side with the default result, never as a headline, and any claim drawn from it needs a newly frozen confirmation protocol.

## Timestamps
All commits are **local and unpushed**. They order the work inside this repository but are not an independent registration, since git dates can be edited. Anything called "pre-registered" here means *privately recorded before the data*, not publicly timestamped.

## Added 2026-09-23 late
- **Whole-run view of Run 1** (per-run ledger, `ledger/examples/`): modeled from request to work end, all cells included, H100 $0.980 against MI300X $0.925 per 1k latency-accepted requests, **~5.7 % lower**. This is a different aggregation from the 53 % cell-level figure (selected qualifying cells, no setup). Both stand, labelled. Neither is an invoice or a correctness result.
- **Run 2 post-hoc exploration** (`results/run2-explore-hotaisle-mi300x`, `run2/EXPLORE.md`). One repeat, same seeds as registered repeat 0. Forcing `--attention-backend ROCM_AITER_FA` (vLLM had auto-selected `ROCM_ATTN`):
  - long c8: +28 % req/s
  - long c32: +46 % (p95 TTFT 57 s → 37 s)
  - short c32/c64: +9 % / +11 %
  - c1: unchanged

  The FP8 linear kernel stayed on the torch fallback. This is a hypothesis for a frozen confirmation run, not a claim.
- The Hot Aisle VM was deleted 2026-09-23 ~22:35 UTC after all results were collected and manifests verified. About $15 of the $200 credit was used.
