# Run 3 pre-data freeze, 2026-09-24 ~00:45 UTC

Made after one labelled smoke (`results/run3-smoke-a-t0`, not scored) and before any scored data.

- **Code:** this commit (`run3/` with the smoke fixes from c2dbc81). Inputs and hashes are in `FREEZE-INPUTS.md`.
- **Tasks:** sha256 `6c508237082261ac927b96825e2f097782389b1cebc3f78360f0665a8db3501f`. Trace: sha256 `54e9a6d2…77fb6`.
- **Trace start:** `2023-11-16T18:17:04Z`. **Rate factor:** `0.95`, the maximum the 57-min source supports over a 3,600 s hour.
  - Calibration outcome, from the smoke on A/T0: the offered load, including a 531-arrival burst, was served with zero client-limit rejections and 0 transport failures. Capacity is therefore above the maximum offered rate, and 0.95 is both the trace ceiling and below capacity.
  - Label: the load is bounded by the trace, not calibrated to 70 % of capacity.
- **Grader-uninformative tasks** (canonical solution fails in the pinned grader): HumanEval/32, Mbpp/255, Mbpp/392. They stay in every denominator and are also reported separately.
- **Grader image:** `sha256:c7c75a7fbc8aa215ddd39930ca0adb2cd4df87de19d4792db8c9f2a7853d7b93` (EvalPlus 0.3.1).
- **Order:**
  1. A/T0: Hot Aisle MI300X, same VM as the smoke, funded by Hot Aisle credit. Disclosed deviation from "self-funded".
  2. A/T1: `ROCM_AITER_FA` forced.
  3. N/T0: DigitalOcean H100, self-funded.
  4. C: DigitalOcean MI300X if it is listed; operator approved arm C on 2026-09-24.
- **Uninterrupted scored hours.** No interrupts.

Smoke result, for reference only: 984 completed, 491 correct, 458 accepted in ~9 min, and ledger `results/run3-smoke-a-t0/ledger/` validates. Two interface gaps were found and handled:
- grade.sh writes `quality-buckets.json`, but the ledger builder expects `grade/buckets.json`
- the linear-kernel parser missed the `Selected X for Y` form (fixed)
