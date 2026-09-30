# Source register for the Run 3 case

The page's `data/seed.json` is a public-safe projection. It contains dated observations, source digests and eight ResearchCore records. It does not carry the raw prompt/completion corpus, local absolute paths, account details or the private campaign strategy. All values below are scoped to the 2026-09-24 experiment.

| Source coordinate in this repository | SHA-256 | Use and limit |
|---|---|---|
| `hot-aisle/campaign/results/RUN3-RESULTS.md` | `2f29c31a56c72100395af280efc04a682188e74bd760be554f5c0916868b5de2` | Reported workload, model, arms, rounded cost and timing, funding summary, one-run caveat, and 2026-09-24 correction. Source-reported price and cost are dated, not live. |
| `hot-aisle/campaign/results/RUN3-HOTAISLE-SUMMARY.md` | `0796d8e840a59cea8096f4a0e2e583db7a1ba1d3647f6a3888c59d7a6c5f1d77` | Distinguishes A/T0 own-script $0.72, modeled own-seat $0.74 in the later report, and mixed shared-seat $0.90 scopes. Its older comparator-pending sentence was superseded by the later `RUN3-RESULTS.md`. |
| `hot-aisle/campaign/results/run3-scored-a-t0/grade/evaluation.json` | `f5e2fe316996ac26d953fb5ebe6d0415b2debd9664c1bc74a309776748ff08ca` | Retained A/T0 grading input. Native recomputation also reads its replay, tasks, mapping and reference files. |
| `hot-aisle/campaign/results/run3-scored-n-t0/grade/evaluation.json` | `7ff6854844b405ea067ec347750e80d8633087d65578c949f5d9144e58532349` | Retained N/T0 comparator grading input. Native recomputation reads the same classes of retained files. |
| `hot-aisle/campaign/DISCLOSURES.md` | `327114957bbeda4b24eb79af60fcd0a32f8fdf21a64fc5bd9d30af717866714f` | Funding and method disclosure dated 2026-09-23. Hot Aisle work used provider credit at undiscounted list-price valuation; N/T0 was self-funded. This is a relationship disclosure, not a defect finding. |

## Work measured and recomputed

`RUN3-RESULTS.md` reports 542 distinct EvalPlus HumanEval+/MBPP+ coding tasks cycled across 8,622 arrivals from the Azure LLM CODE trace (2023), replayed for one hour at factor 0.95. Both arms used Qwen3-Coder-30B-A3B-Instruct-FP8, revision `dcaee4d4dfc5ee71ad501f01f530e5652438fde0`, with vLLM 0.30.0. Acceptance was raw base-and-plus correctness **and** first token by 1 second **and** completion by 60 seconds, both deadlines from scheduled arrival. The local private freeze was commit `0b032ac`; Git alone is not an independent registration timestamp.

| Arm | Scheduled/completed | Raw correct | Accepted | TTFT p50/p95/p99 | Dated list rate | Reported cost per 1,000 accepted |
|---|---:|---:|---:|---:|---:|---:|
| A/T0: Hot Aisle 1× MI300X, `ROCM_ATTN` | 8,622 / 8,622 | 4,371 | 4,336 (50.3%) | 53 / 155 / 571 ms | $2.99/GPU-hour | $0.74, modeled 64.7-minute own-seat equivalent |
| N/T0: DigitalOcean 1× H100, `FLASH_ATTN` | 8,622 / 8,622 | 4,329 | 4,280 (49.6%) | 35 / 76 / 2,254 ms | $4.41/GPU-hour | $1.20, closed 69.8-minute request-to-release ledger |

On 2026-09-28, `python -B integration/work.py` ran `run-recompute` locally against both retained arms. It returned 8,622 scheduled/completed and 4,336 accepted for A/T0, and 8,622 scheduled/completed and 4,280 accepted for N/T0. The native result explicitly says `fresh_evalplus_execution: false`, `new_gpu_run: false`, and `authority_promoted: false`. This is recomputation of the retained grader join and deadline buckets, not an independent rerun of generated solutions.

The reported dollar figures use different accounting evidence classes. A/T0's 64.7-minute standalone equivalent is modeled from provisioning latency plus its own arm, yielding $0.74 per 1,000. `RUN3-HOTAISLE-SUMMARY.md` also gives **$0.72 for the shorter own-script window** from `t_script_start` to `t_script_end`; that window excludes the modeled provisioning time, so it is not the input to this case. The actual Hot Aisle seat was shared across smoke, setup, A/T0, A/T1 and idle time. That full mixed seat was approximately $8.15 at list price for 9,086 accepted, or $0.90 per 1,000. Do not compare that mixed-workload aggregate to N/T0 as a matched arm. N/T0's reported $1.20 uses its closed allocation window. Invoices are unreconciled; neither amount is a verified cash charge for accepted work.

For the workbench's scenario arithmetic, `rate × minutes / 60 × 1000 / accepted` yields A/T0 $0.7436 and N/T0 $1.1987 at the reported rates; the source rounds these to $0.74 and $1.20. An **illustrative**, unquoted A/T0 rate of $5.00 yields $1.2435 on the same retained accepted count and 64.7-minute own-seat equivalent. This crosses N/T0's historical $1.20 closed-ledger reference. It changes the conditional arithmetic ordering; it does not refresh correctness, capacity, billing terms or source dates. The workbench should visibly keep the old issued report and require a new review of the revised recommendation.

## Correction and unresolved limits

The source's post-hoc `evalplus.sanitize` regrade raised A/T0 correct outputs from 4,371 to 6,192. It did **not** recompute the intersection with the registered first-token and completion deadlines. The corrected report withdrew its earlier implication that accepted closures grew by the same ratio. This case retains 4,336 as the only registered accepted figure for A/T0. The three grader-blind tasks listed in the report remain in the denominator. There was one run per arm, no repeats, and the sampled task cycle is not a population reliability estimate. A price scenario supplies no current provider quote or availability.

## Adjacent source status

- `research-desk/CONTRACTS.md` defines the native record, review, freeze and packet rules. Journal hashes are consistency checks, not publisher authentication.
- `integration/WORK.md` and `integration/work.py --catalog` define deterministic reuse and the exact `from_record` procedure handoff. This page does not run that handoff in the browser.
- `hot-aisle/campaign/shelf/join/run3-v3/` records a Genesis-bound local candidate and Canon native evidence-format validation. `standing` remains `filed/candidate`; `authorized_reuse` is false. The page does not import its private absolute paths or imply admission.
- `hot-aisle/campaign/ledger/KNOT-LIFECYCLE.md` implements a bounded campaign state machine derived from CAIRN's Knot vocabulary. The broader CAIRN composition is documented design/held work, not a deployed service here.
- `axm-genesis` and `axm-core` are separate existing authorities for signed shard construction/verification and read-side extraction/query. This page invokes neither. A generalized Decision Continuity Fabric runtime was not qualified by this source inspection.
