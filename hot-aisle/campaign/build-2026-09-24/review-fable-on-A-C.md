# Review: lanes A and C (Fable, 2026-09-24)

Read-only. Ran `run3/selftest.py` (17 OK), `availability/test_availability.py` (19 OK), `ledger/test_all.py` (OK), and `ledger_validate.py` on synthesized records.

## Lane A: run3

**1. Blocking**

1a. `arm.py:26-37` with `:135-138`: the backend extractor cannot see the real vLLM 0.30 ROCm selection line. `results/run2-hotaisle-mi300x/serve.log:24` is the only line naming the backend: `Found incompatible backend(s) [TURBOQUANT] ... Overriding with ROCM_ATTN ...`. `backends()` skips lines matching `overrid|incompatible` and requires `Using|Selected`, so A/T0 yields `['UNVERIFIED']` and stops with "Selected backend/kernel not found" after up to 40 minutes of paid pull and download. `fixtures/serve-amd.log` is authored and does not match production; there is no CUDA fixture, and the linear-kernel regex may find nothing for this model's block-FP8 path on either vendor. Fix: parse `Overriding with (X)` as a selection, build fixtures from real logs, and record UNVERIFIED as a hold in env.json instead of a pre-replay hard stop.

1b. `arm.py:155` `child.wait(timeout=3665)`: the child's trace parse, tasks load, executor drain (up to 60 s for an arrival at 3599 s) and journal recovery all sit inside those 3665 s, leaving about 4 s. An overrun marks a complete hour `failed`, which the stop rule reads as a failed replay. Widen into the 115 s bookkeeping slack (3720) or parse before `t_work_start`.

**2. Honesty**

2a. `arm.py:192` stamps `second-run/run-ledger@1` on a flat record. `ledger_validate.py` rejects it: every group missing. Rename it (`second-run/run3-arm-summary@1`) or emit the grouped record.

2b. Factor 0.10 stretches six source minutes into the hour: roughly 0.2-0.5 req/s on the CODE trace (my estimate, UNVERIFIED until the CSV is on disk) against `max-num-seqs 256`. Both GPUs sit mostly idle; sustained throughput collapses to arrival rate and $/accepted to list price times pass rate. PREREG should say that at 0.10 the run measures price and correctness, not capacity.

**3. Fit**

- Watchdog: arithmetic holds (2400+120+3600+65+115 = 6300 alarm; 110 min outer; finally-block worst case about 115 s plus convert inside the 300 s reserve), with caveat 1b.
- Page engine: yes. `convert.py` output passes `engine_check.cjs`, which loads `../../index.html` with the same regex and `vm` sandbox as `engine_table.cjs`; fixture 6/5/2, no holds; sidecar bound to `detailed.json` sha.
- Ledger schema: no. Beyond 2a there is no run3 builder; replay buckets use `offset_s/duration_s` where `sustained.buckets` needs `index/start_s/accepted`; `hourly_list_usd` vs `list_rate_per_gpu_hr`; no `work.unit/evaluator/acceptance_rule`. All hand edits today.
- Fairness: same vLLM 0.30.0, flags, seeds, trace, loopback client and gates; T1 must select ROCM_AITER_FA or stop; primary comparison declared T0 vs T0. Asymmetries: AMD T0 carries `VLLM_ROCM_USE_AITER=1` while NVIDIA T0 carries nothing (as briefed; PREREG:16 should say "auto" is not "default"), and the 1a stop rule was rehearsed against an authored AMD log and no NVIDIA log, so NVIDIA is likeliest to burn its hour on a parsing miss.

**4. Improvements**

1. Fixtures from real logs, both vendors. 2. One short pre-data factor calibration, then refreeze (PREREG permits). 3. `lost_or_unsent_after_interrupt` mixes never-sent with lost; schema `lost` means sent and unanswered. 4. `client_concurrency_limit` counts as failed transport and can breach the 1 % gate; document. 5. PREREG:130 names ledger fields; name the closure builder that maps them.

**5. Verdict: READY-WITH-FIXES** (1a, 1b, 2a).

## Lane C: availability

**1. Blocking**

None for the probe. Cross-lane: `probe.py:211` writes delivered rows with `method: create-attempt`; `ledger_validate.py:156` rejects that as "a listing, not an attempt" and `ledger_build_run1.py` `METHOD_MAP` has no mapping, so a Run 3 acquisition group built from lane C receipts needs a hand edit. Use `api-create`/`console-create`/`tui-provision` as `method` (`layer` already says delivered), or lane B widens the enum.

**2. Honesty**

Listed and delivered stay separate with honest denominators: colour is `yes/valid` API probes, unknowns are excluded and counted, the 14 manual listings are excluded rather than back-filled, `tui-provision-list` with `provisioned: true` is not promoted, and a `console-create` success needs `time_to_ssh_s`. Hot Aisle is held UNVERIFIED (endpoint, `Token` prefix, region scope) and yields unknown until verified. Two soft spots: `heatmap.txt` reports "missed 672" per row for a week before any probe existed, which reads as outages; and DigitalOcean's `available` plus `regions` flags are configuration availability that may never move with capacity (the 09-23 console showed out-of-capacity for SKUs the API may still list). Say so in README; UNVERIFIED until compared with console notes.

**3. Fit**

Rows carry the schema's attempt shape; the builder's `obs_match` needs `provisioned: true`, so listed API rows (`provisioned: false`) cannot be promoted. Only the method enum breaks. Heatmap: inline SVG, `prefers-color-scheme` dark, no dependencies; not visually QA'd (stated).

**4. Improvements**

1. Start "missed" at each row's first API observation; label earlier hours "not sampled". 2. `README.md:5` field list predates `layer`, `attempt_id`, `create-attempt`. 3. Note that a delivered tuple outside `probes.json` still gets a row. 4. Exit 1 on all-unknown fails the unit every 15 min until tokens exist; note the alert noise. 5. Add a fixture with `links.pages.next` to prove pagination.

**5. Verdict: READY-WITH-FIXES** (method enum alignment; missed-slot start).
