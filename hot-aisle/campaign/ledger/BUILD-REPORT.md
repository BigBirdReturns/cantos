# Lane B build report · ledger, Knot lifecycle, seats, WATERLINE, estate arm prereg

Built 2026-09-23 (night) into `hot-aisle/campaign/ledger/` only. Nothing committed, pushed, provisioned or bought. Python stdlib only. No result is asserted anywhere in this lane; the worked example records Run 1, it does not re-score it.

## Files built

| File | Deliverable |
|---|---|
| `ledger.schema.json`, `SCHEMA.md` | 1 · run-ledger schema `second-run/run-ledger@1` with the nine field groups (identity, clocks, acquisition, work, sustained, traversal, money, derived, receipts) and the null-reasons rule |
| `ledger_validate.py` | 1 · stdlib validator: types/enums/required, every null needs a reason, clock order, acquisition counts (a listing is not an attempt), work ordering, money arithmetic, derived recomputation, sha256 shape |
| `ledger_build_run1.py` → `examples/run1-do-h100.ledger.json`, `examples/run1-hotaisle-mi300x.ledger.json`, `examples/run1-*.events.jsonl` | 1 · builder from `../results`, `../identity.json`, `../availability/observations.jsonl`; 5-minute sustained buckets from the bench's monotonic clock; traversal-by-depth estimates from median ITL; reconstructed Knot event log per arm |
| `knot_lifecycle.py`, `KNOT-LIFECYCLE.md` | 2 · 16 states (ISSUED, QUOTED, RESERVED, PROVISIONED, RUNNING, DELIVERED, KNOT_VERIFIED, SETTLED, RELEASED, PROVISIONING_FAILED, INTERRUPTED, REASSIGNED, DELIVERY_REJECTED, VERIFICATION_FAILED, EXPIRED, CANCELLED), transition table with required event data, JSONL append-only hash-chained log with replay verification |
| `seats.json` | 3 · 13 seats: Hot Aisle 1×MI300X, DO H100, DO H200 (unavailable), DO MI300X (never ran), estate 3090 W01, 3090 N01 eGPU, 4060 W01, three CPUs, two iGPUs and the NPU as validator-only. Measured fields cite receipt paths; nulls carry reasons; UNVERIFIED written where applicable |
| `waterline.py` | 4 · planner: feasibility (role, availability/busy, recipe+format, memory: resident / measured split curve / measured streamed link, deadline, budget, grader role), then fastest / cheapest / most-efficient plans with wall clock, modeled cost or nameplate-energy cost, success probability from observations with "TOO THIN" flags; refusals are written reasons; exit 2 on refusal |
| `ESTATE-ARM-PREREG.md` | 5 · draft pre-registration for the estate arm: gpt-oss-120B Q2_0 (33.7 GB, does not fit a 3090) on `estate-w01-3090` at depths 1/4/16 over HumanEval+ (164 tasks), sized from the 2026-09-09 llama-bench receipt (12.44 tok/s at `-ngl 22`), explicitly **llama.cpp partial offload (split-vram-ram), not true streaming**; a slice-scale link-streaming cell as Path B |
| `fixtures/` | `ledger/` 2 valid + 13 invalid records; `run1-mini/` two real cells per arm with generated texts stripped + `expected.json` hand values; `knots/` 30B coding, 70B dense, estate-arm 120B; `availability-2026-09-23.jsonl` |
| `test_all.py`, `README.md` | 6 · test runner and run instructions |

## How to run

From `hot-aisle/campaign/ledger/`: `python test_all.py` runs everything offline. Individual commands are in `README.md` (validate a record, rebuild the worked example, drive a Knot through the event log, `waterline.py plan <knot.json> [--start-at …] [--json out]`).

## Test output (2026-09-23, Python 3.13)

```
=== ledger_validate.py --selftest      17 passed, 0 failed  (2 valid fixtures + 2 examples pass; 13 invalid fixtures fail with the named error)
=== knot_lifecycle.py --selftest       all passed  (11 checks: legal chain, reassignment, terminal refusals, required data, settlement-none rule, retry path, tamper detection, table coverage)
=== ledger_build_run1.py --selftest    all passed  (20 checks against hand-computed expected.json for both arms)
=== waterline.py check-seats           seats.json: clean
=== waterline.py --selftest            all passed  (33 checks)
=== ledger_build_run1.py (full build)  do-h100: accepted 2267/2400, modeled $2.22 over 30.2 min, window 1106 s (60-min requirement: not met), validate ok, events ok
                                       hotaisle-mi300x: accepted 2400/2400, modeled $2.22 over 44.5 min, window 1675 s (not met), validate ok, events ok
ALL PASSED
```

Planner spot checks from the self-test (all flagged "TOO THIN" on availability, n ≤ 2 probes per SKU):
- 70B FP8 Knot: W01 3090 refused ("42.5 GB exceeds 20.0 GB usable … no measured streamed link; host RAM 34.1 GB also too small for a split"), H100 refused ("72.7 GB > 72.0 GB usable"), H200 "unavailable (0/6 regions)", NPU/iGPUs "validator-only"; only Hot Aisle MI300X plans (fastest 17.5 min at depth 32, $0.90 modeled, on the Run 2 median-ITL curve now under `../results/run2-hotaisle-mi300x/`, 27.7 ms at c1; that directory appeared during this build from another lane and is cited, not verified against its manifest here).
- 30B coding Knot on 09-24: both cloud seats plan (H100 fastest 11.3 min / $0.83; Hot Aisle cheapest $0.80 at depth 64); 3090s "declared busy until 2026-09-28"; 4060 "traversal time exceeds the deadline — 12.9 GB non-resident per traversal over 817 MB/s".
- Same Knot on 09-29: W01 3090 becomes cheapest on assumed energy ($0.001, "NOT metered"); its timing is marked ASSUMED (no 30B curve on that seat).
- Estate-arm Knot on 09-29: plans on the measured B1 curve, depth 1 = 164 × 301 traversals × 0.0804 s ≈ 66 min; depths 4/16 flagged extrapolated; path named `split-vram-ram`.

Two defects found and fixed by the tests during the build: the event-log chain originally compared against each line's *recorded* hash (a tampered line slipped through; now chains on recomputed hashes), and the builder derived the work window from sub-second clocks while writing whole-second clocks (validator caught the mismatch).

## Open questions

1. **Extrapolation policy.** WATERLINE scales traversal time beyond the measured depth by √depth and labels it; for the estate arm that makes an extrapolated depth-16 plan the "fastest". Should plans with any ASSUMED/extrapolated term be ranked behind fully-measured ones, or shown only as "needs a pilot cell"?
2. **Estate arm model.** The prereg registers gpt-oss-120B Q2_0 because it is the only over-VRAM model with a token receipt on the seat. The Qwen3-Coder-30B Q8_0 continuity variant would compare directly with Run 3 but has no receipt and is not on disk. Which is primary is the operator's call before freezing.
3. **Traversal counter.** `llamacpp:n_decode_total` on llama-server `/metrics` is assumed for build b10665; if absent the fallback (per-request `predicted_n` and slot counts) must be declared before freezing.
4. **`usable_for_weights_bytes` for the 3090s** is the SYNTHESIS "about 20 GB" rule, not a measurement; the estate arm's load log will replace it.
5. **Run 1 sustained buckets** follow the c1→c64 cell schedule with ~30 s gaps; they satisfy the schema, not the 60-minute requirement, and say so. Run 3's 90-minute window is the first real one.
6. **Seat identity drift.** The 2026-08-25 reconciliation and the 2026-09-09 binding disagree on which 3090 UUID sits in W01 vs the laptop; `seats.json` follows the later receipt and notes the earlier one. OCTO-L01 GPUs are deliberately not registered.
7. **Fixture weight.** `fixtures/run1-mini/` is ~4.6 MB (four real cell files with per-request arrays, texts stripped). `main` is published by Pages; if that is too heavy, the builder self-test can be pointed at `../results` instead and the fixture dropped.
8. **Whether `ledger/` belongs on `main` at all** before the campaign push decision in SYNTHESIS "Decisions for the operator" item 3; it references estate receipt paths on `D:` and `S:` (paths only, no content).

## What the operator must supply

- **Tokens** (not for this lane's code, but for the probabilities it reads): DigitalOcean read-scope API token and a Hot Aisle API token so `availability/observations.jsonl` grows past n = 2 per SKU; until then every WATERLINE success probability is flagged too thin.
- **A wall-socket plug meter** with a machine-readable ≥ 1 Hz log on OCTO-W01, and the **electricity tariff** ($/kWh); without them `money.energy` stays null and estate cost stays "nameplate, NOT metered".
- **Approval of `ESTATE-ARM-PREREG.md`** after resolving its UNVERIFIED items (model file sha256, llama-server metrics name, evalplus version and dataset hash, reasoning-effort flag), then a commit to freeze it before ~2026-09-28.
- **Hot Aisle credit consumption and both invoices** when they post, to fill `money.billed_usd` / `credits_usd` in the Run 1 examples (currently null with reasons).
- **Confirmation of the 3090 busy-until date** (SeedVR2 finish); `seats.json` declares 2026-09-28.
