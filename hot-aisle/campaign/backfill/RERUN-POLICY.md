# Historical checkpoint rerun policy

Imported evidence is a prior (`tier: imported`), never a measured campaign result. Preserve its bytes and provenance. Spend on a new measurement only when it can change a seat/workload decision. A listing does not prove acquisition, throughput does not prove correctness, and tokens do not establish accepted closures per weight traversal.

## Triggers (proposed policy, not measured thresholds)

| Change | Action |
|---|---|
| Framework major/minor changes | Select one affected model-class/shape sentinel at low concurrency and one near the latency boundary; freeze a new protocol, old/new images and model revisions before execution. Patch-only changes trigger only with a relevant kernel/scheduler fix or a detected regression. |
| Attention, GEMM, MoE kernel or backend changes, including auto-selection | Re-run affected architecture/precision sentinels even if the framework version string is unchanged. Record selected backend from serve logs, not merely requested flags. Compare declared default and tuned tiers separately. |
| New GPU, firmware, driver or topology | New seat identity and qualification. Match GPU count/interconnect/power policy. Do not divide an eight-GPU result by eight and call it a single-GPU reproduction. |
| Comparable raw gap `abs(ours/theirs - 1) > 0.20` | First audit units, model identity, config, gates and source validity. If unexplained, propose a rerun. Confirm with three independent repeats and a frozen gate before a claim; a single post-hoc comparison is a hypothesis. For latency, a ratio below one is faster; the absolute threshold is symmetric around one, not reciprocal-symmetric. |
| Age at least 90 days for an actively routed class/seat | Check software/config changes and decision relevance; refresh a sentinel if stale evidence could affect routing. Archive-only checkpoints do not automatically consume compute. Unknown measurement dates prompt metadata recovery, not fabricated age from retrieval time. |
| Price changes only | Recompute economics with dated price, billing minimum, credits and setup interval. No GPU rerun unless runtime/workload changed. |
| Missing correctness, sustained window or acquisition evidence | Design the missing boundary measurement. A historical throughput rerun cannot fill these fields by inference. |

## Ranking implemented by delta.py

Each imported observation (checkpoint × metric) remains explicitly unreproduced. Ranking is transparent triage, not spend approval: +20 hardware present, +20 model class present, +20 matching shape/precision/concurrency with a supported metric, +30 a raw gap over 20%, +10 runtime/backend differs or is unknown for a matched pair, +10 measurement age ≥90 days. Ties sort by immutable observation ID. Unknowns produce metadata work; they do not claim a detected runtime change. Deduplicate shared checkpoints across metric rows when assembling a run plan. All actual firmware and major/minor change decisions require the operator's new target configuration; this CLI does not inventory live seats.

Before execution: group checkpoint metrics; exclude invalid outcomes; fill metadata; choose the smallest discriminating cells; freeze model revision, tokenizer, image digest, flags, gates, repeats, budget and stopping rules. Retain every repeat and failures. A close ratio alone is not reproduction: verify the exact workload, precision representation, runtime, topology and evaluation rules. MLPerf reproduction requires its accuracy and compliance evidence, not just the performance summary.

## Carry lessons forward without buying duplicate runs

Store a lesson with source receipt/hash, architectural scope, known exceptions, confidence, invalidation trigger and a preflight check. Example: Run 2 vLLM 0.30.0 with `VLLM_ROCM_USE_AITER=1` selected `ROCM_ATTN`; forcing `ROCM_AITER_FA` changed some dense-70B cells. The transferable lesson is **verify backend selection**, not a universal speedup percentage. Carry that check to compatible dense/GQA workloads. Do not carry the measured uplift to MoE/MLA, another precision, or another version without a targeted confirmation.

Reuse source recipes and lessons to choose the next edge measurement. Do not repeat an entire historical grid just to restate a known failure mode. Retain imported, our registered measurement, and post-hoc exploration as distinct evidence. The buyer's endpoint remains correct, deadline-accepted work per full run cost; streamed seats additionally need measured traversal cost and closures per traversal. This lane produces no estimate of those missing quantities.

Authority: [campaign disclosures](../DISCLOSURES.md), [Run 2 preregistration](../run2/PREREG.md), [exploration](../run2/EXPLORE.md), and the Correction/North star sections of [design synthesis](../research-2026-09/SYNTHESIS.md). This policy authorizes no rental, provisioning, credentials, estate access or publication.
