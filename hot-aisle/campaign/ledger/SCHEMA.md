# Run ledger schema · `second-run/run-ledger@1`

One JSON record per **run**: one seat lease executing one Knot (or, for Runs 1–2, one campaign arm). It extends the qualified record the page already publishes with the buyer's side of the story: when the capacity was asked for, how many tries it took, what finished correctly, what it cost including the failed attempts, and how many weight traversals the work took. The machine-readable form is `ledger.schema.json`; `ledger_validate.py` enforces it with the stdlib only.

Design authority: `../research-2026-09/SYNTHESIS.md` ("The unit: one run, not one token", the Correction, the North star). Nothing in a ledger line asserts a result; it records one.

## Conventions

- **Nulls carry reasons.** Every group may hold `"null_reasons": {field: reason}`. A null field without a reason fails validation. This is how Run 1's gaps stay visible instead of silently zero.
- **Clocks are UTC ISO-8601** (`2026-09-23T17:49:00Z`). `clocks.sources` names where each timestamp came from and its precision.
- **Basis strings.** Numbers that could be measured or estimated carry a sibling `<field>_basis` (traversal group) or a `*_basis` field (money) stating which.
- **Derived values are recomputed** by the validator from the groups above. If they disagree beyond tolerance the record fails.

## Groups

### identity
`run_id`, `campaign`, `run`, `arm`, `knot_id` (null before Knots existed), `seat_id` (a key in `seats.json`), `provider`, `region`, `sku`, `gpus`, `host`, `model{id, revision, precision, bytes}`, `runtime{image, digest, engine, engine_version}`, `workload_id`, `prereg{path, commit}`.

### clocks
`t_request → t_ssh → t_ready → t_work_start → t_work_end → t_released`. Non-null values must be non-decreasing in that order. The buyer's clock is `t_request` to `t_released`; `t_ready` is when the engine answered health with the model loaded.

### acquisition
`attempts[]` (same line shape as `../availability/observations.jsonl`, restricted to real create/provision actions), `n_attempts`, `n_allocations`, `yield = n_allocations / n_attempts`. **A listing is not an attempt.** Counts must agree with the array.

### work
`unit` (`request` | `task`), `evaluator{name, frozen, ref}` or null, `acceptance_rule{basis, ttft_ms, e2e_ms, correctness}`, then `attempted`, `completed`, `correct`, `accepted`, `lost`, `restarts`. Ordering rules: `accepted ≤ correct ≤ completed ≤ attempted` where non-null. `correct` is null when no frozen evaluator ran (Run 1). Optional `cells[]` keeps the per-cell breakdown for benchmark runs.

### sustained
`required_window_s` (3600 Fable / 7200 Astra), `bucket_s` (300), `window_s`, `meets_required_window`, `buckets[{index, start_s, accepted}]`, `min_accepted_per_bucket`, `median_accepted_per_bucket`, `last_q_over_first_q`. Run 1 windows are 15–21 minutes, so `meets_required_window` is false there and the bucket statistics are shown for what they are.

### traversal
`path` (`resident-hbm` | `resident-gddr` | `split-vram-ram` | `streamed-pcie` | `streamed-thunderbolt` | `streamed-lan` | `streamed-disk`), `bytes_per_traversal`, `traversals`, `seconds_per_traversal`, `accepted_closures_per_traversal`, each with `_basis`. Optional `by_depth[]` gives the curve against batch depth, which is what WATERLINE reads.

### money
`list_rate_per_gpu_hr`, `billing`, `payer` (`self` | `credit:hotaisle` | ...), `modeled_minutes` + `modeled_minutes_basis`, `modeled_usd` (= rate × gpus × minutes / 60), `billed_usd` + `billed_ref` (null until the invoice posts), `credits_usd` (separate, never netted), `energy{watts_mean, kwh, tariff_usd_per_kwh, usd, meter}`.

### derived
`usd_per_accepted`, `usd_per_1k_accepted`, `wall_s_per_accepted` (work window ÷ accepted), `accepted_per_s`, `cost_basis` (`modeled` | `billed` | `energy`).

### receipts
`items[{kind, path, sha256?}]`. Kinds: `cell`, `env`, `env_normalized`, `image`, `manifest`, `log`, `serve_log`, `engine_output`, `availability`, `invoice`, `prereg`, `event_log`, `meter`.

### notes
Free-form array of strings. Anything the numbers cannot say (unequal software, post-hoc scoring, missing serve log) goes here, mirroring `../DISCLOSURES.md`.

## Worked example

`ledger_build_run1.py` assembles `examples/run1-do-h100.ledger.json` and `examples/run1-hotaisle-mi300x.ledger.json` from `../results/`, `../identity.json` and `../availability/observations.jsonl`, plus a reconstructed Knot event log per arm. Fields Run 1 cannot supply (`t_ssh` for Hot Aisle, `t_released`, `correct`, `restarts`, billed and credit amounts, energy) are null with reasons.
