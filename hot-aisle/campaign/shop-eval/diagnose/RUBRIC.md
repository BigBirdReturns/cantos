# Diagnosis rules and interpretation

The report separates observed outcomes from hypotheses. `WRONG` means an explicit, scoped buyer-relevant requirement or accounting fact is missed. `SIGNAL` means an observation merits a discriminating test but does not establish a defect. `RIGHT` means the stated field was observed for this specific sample. `UNKNOWN` means the needed evidence was absent or partial. `NOT_COMPARABLE` is used where vendor-specific fields or incomplete scope prevent a like-for-like claim. None of these statuses proves hidden host cooling, PSU, tenant, topology, or operator causes.

## Economic comparison gate

`PRICE-02` and the headline ratio require a scope JSON bound to the exact scored table by SHA-256. Candidate and reference must match workload ID, model and tokenizer revisions, precision, cache policy, load profile, acceptance rule and latency gates, cost scope, and rate. Both configurations must identify GPU model/count, runtime digest/version, backend/kernel, and tensor-parallel size. Candidate input must include evidence paths and observation date. Any missing/unobserved value, table hash mismatch, or gate/rate mismatch refuses the ratio.

Reference scope IDs preserve separate windows:

- `run1-cell-c64`: Run 1 C64, warm random seed-7 2048/256 workload, latency-only gate and no correctness sidecar; cost is per-cell.
- `run3-own-window`: Run 3 Azure CODE trace with EvalPlus correctness and scheduled-arrival deadlines; cost is the arm own-window estimate.
- `run3-whole-seat`: same Run 3 accepted workload, with whole-seat request-to-release allocation cost.

These are not interchangeable. Run 1 and Run 3 are not comparable because workload and acceptance differ. Run 1 serving-backend evidence is unobserved. Run 3 disables prefix caching, while broader cache warm/cold state is unobserved; those fields block a fail-closed ratio until completed from evidence. Historical labels identify dated evidence, not current provider behavior. Different configurations can compare economics for exactly matched customer work, but a different GPU/runtime/backend/kernel does not establish operator causality. Billed invoices remain separate from modeled list-rate cost.

## Rules

| ID | Evidence and status logic | Limits and first discriminating check |
|---|---|---|
| CNT-01 | Composite counter score is always a `SIGNAL`, never a quality verdict. | Inspect component dimensions against their source evidence. |
| CNT-02 | Dimension score spread is a prioritization `SIGNAL`. | Validate each dimension's observations; the spread alone does not establish a compute fault. |
| PWR-01 | Requires sustained sample, throttle state, and start/end clocks for every GPU. Throttle or >15% clock slope is a `SIGNAL`. | Compare vendor-specific telemetry under a bounded, supported load; ask operator to inspect cooling, power, limit, workload, and sharing evidence before proposing changes. No generic power-limit advice. |
| HW-01 | Requires current and supported maximum PCIe generation/width for every GPU. A shortfall is a `SIGNAL`. | Check exact part/platform documentation and loaded transfer behavior; inspect host slot/riser/topology with operator. No universal link threshold is encoded as proof. |
| HW-02 | Requires vendor-sourced firmware age for every GPU. Age >270 days is a `SIGNAL`; absent age is `UNKNOWN`. | Check exact board release notes, qualified driver branch, and firmware recovery method. Host-authorized maintenance only. |
| HW-03 | Requires both correctable and uncorrectable RAS counters on every GPU. Any uncorrectable or >100 correctable counter is a `SIGNAL`. | Confirm counter semantics and baseline/delta in vendor docs, then correlate with a scoped workload and retained logs. A single snapshot does not justify reseat/RMA. |
| STK-01 | Requires same-vendor version evidence. NVIDIA driver and AMD ROCm versions are never directly compared. A same-vendor version difference is a `SIGNAL`, not an automatic failure. | Inspect vendor support matrix, image digest, backend/kernel, then test a matched workload before attributing performance. |
| STK-02 | Missing/unknown backend is `UNKNOWN`; a reported backend is `RIGHT` only for observability. | Capture the per-session serving backend/kernel. A reported value does not mean the backend is optimal. |
| FLEET-01 | Request-to-SSH time >300 seconds is a `WRONG` against this kit's buyer-selected 5-minute service target; this is not a Hot Aisle performance standard. | Repeat authorized fresh allocations; separate provider queue, image, network, and client clock causes with timestamps. Canary one provisioning setting and retain rollback. |
| HEALTH-01 | Requires complete attempted/completed/failed counts for every cell. Any failures are `WRONG` for a zero-failure acceptance target only when that target is declared for the workload; absent counts are `UNKNOWN`. | Join request IDs to client results and server logs. Replay only scoped failing cases; do not assume hardware cause. |
| HEALTH-02 | Idle/load power ratio above 1.5 is only a `SIGNAL`. Partial readings are `UNKNOWN`. | Repeat authorized idle/load samples and correlate utilization with scheduler/job records. Customer-side power readings cannot prove tenant sharing. |
| PRICE-03 | A listed SKU with a recorded unsuccessful attempt is `WRONG` for that attempt. No listing or no attempt denominator is `UNKNOWN`; successful provisioning is `RIGHT` for that one observation. | Record SKU, region, listing snapshot, attempts, outcomes, and timestamps; ask operator for inventory/quota logs. |
| TEN-01 | For a VM, ACS/hugepage state is a `SIGNAL` only; incomplete state is `UNKNOWN`. Bare metal is not evidence of universal superiority. | Compare a scoped job-local memory/collective test and obtain topology/virtualization evidence. Do not recommend ACS override. |
| TEN-02 | On multi-NUMA systems, missing pinning state is `UNKNOWN`; unpinned state is a `SIGNAL`. | Compare GPU locality and a bounded pinned/unpinned run. Do not change shared scheduler defaults based on a probe alone. |
| PRICE-01 | Explicit hourly-or-coarser billing is `WRONG` against the buyer's sub-hour requirement. Unknown/unrecognized terms are `UNKNOWN`; recognized minute/second terms are `RIGHT` for granularity only. | Confirm dated plan terms and invoice, including minimums and fees. |
| PRICE-02 | Candidate best cell cost is `WRONG` only when validated same-scope cost exceeds the reference by >5%; otherwise `RIGHT` for that scoped economic observation. | Verify table digest and recompute a cell from accepted count, duration, rate, and declared window. It does not attribute cause. |
| PROOF-01 | Explicitly false manifest/disclosure/pinned-revision flags are `WRONG`; missing fields are `UNKNOWN`. | Verify each referenced artifact hash, disclosure, and revision. |
| PROOF-02 | Explicit absence of whole-seat cost disclosure is `WRONG`; missing proof is `UNKNOWN`. | Reconcile request-to-release timestamps and cost; publish cell, arm-window, whole-seat, and billed figures separately. |

Every `WRONG` result carries plausible competing causes, a minimum discriminating test, bounded intervention, acceptance measure, rollback, and access needed. These are evaluation prompts, not automatic commands. Failure drills or live changes require an isolated scoped job and operator/customer authorization.
