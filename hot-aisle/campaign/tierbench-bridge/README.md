# tierbench-bridge · Tier-Bench (model-tier axis) x Second Run fabric ledger (seat axis)

Lane E of the 2026-09-24 build. Stdlib Python, offline tests on fixtures, no model calls, no provisioning, no commits.
Design authority: `../research-2026-09/SYNTHESIS.md` (North star: decompose -> fungible seats -> plan -> receipts) and
Tier-Bench's `docs/residue-broker.md` / `docs/burden-discipline.md` (cheapest sufficient rung, K/K decisive receipts).

| File | What |
|---|---|
| `BRIDGE.md` | the two-axis model, exact field mappings (Call rows / route.py receipts / map.json / waterline.json <-> run-ledger@1 + seats.json), SeatIdentity <-> seats.json with an authority proposal, provenance of every input |
| `import_tierbench.py` | reads the pinned Tier-Bench artifacts, emits `second-run/tierbench-call@1` records tagged `tierbench-measured` / `tierbench-shadow-estimated` with provenance (path, git commit, sha256), a per-class summary (min sufficient tier, cost/trial, pass rates, residue) and a priced tier ladder; route.py receipts get a DERIVED cost |
| `tier_waterline.py` | planner extension: Knot task class -> cheapest sufficient model tier (Tier-Bench evidence) -> seat plans (API tiers = zero-seat; open-weight tiers through `../ledger/waterline.py`, imported, never edited) |
| `local_models.json` | registry: open-weight Tier-Bench tiers -> Knot model specs the fabric planner needs (bytes UNVERIFIED where so) |
| `RUN3-GRID.md` | how Run 3's EvalPlus workload becomes a Tier-Bench task class run across tiers and seats; budget at Tier-Bench / Race 6 prices; what the grid answers |
| `fixtures/` | verbatim excerpts of the pinned files (`REGENERATE.py`), SYNTHETIC route.py receipts and the Run 3 Knot (`make_synthetic.py`), `PROVENANCE.json` |
| `test_all.py` | every self-test, a fixture import and two plans into temp storage, plus lane B's untouched `waterline.py --selftest` |
| `BUILD-REPORT.md` | files, how to run, test output, open questions, what the operator must supply |

## Run

From this directory (`hot-aisle/campaign/tierbench-bridge/`):

```sh
python test_all.py                                          # all offline self-tests; exit 0 = all pass

python import_tierbench.py --selftest
python import_tierbench.py --fixtures --out /tmp/ev         # fixture excerpts -> tierbench-calls.jsonl, tierbench-summary.json, tier-ladder.json
python import_tierbench.py --tierbench-root "D:\Projects\Measurement\Tier-Bench\worktrees\task-computer-no-console-current-main-20260730" \
                           --router-root "D:\Projects\Measurement\Tier-Bench\integrations\our-auto-router" \
                           --receipts <dir-or-files of route.py receipt.json> --out /tmp/ev     # the real pinned inputs (read-only)

python tier_waterline.py --selftest
python tier_waterline.py plan fixtures/knots/knot-run3-evalplus-tierbench.json --evidence /tmp/ev            # exit 0 chosen, 2 no sufficient tier
python tier_waterline.py plan <knot.json> --evidence /tmp/ev --start-at 2026-09-29T10:00:00Z --json plan.json \
                              [--seats ../ledger/seats.json] [--availability ../availability/observations.jsonl] [--local-models local_models.json]

python fixtures/REGENERATE.py        # only when the pinned inputs change; reads the two entry-locked paths only
python fixtures/make_synthetic.py    # rewrites the synthetic receipts and the Knot fixture
```

`tier_waterline.py plan` reads `../ledger/seats.json` and `../availability/observations.jsonl` by default, exactly as lane B's planner does.
A Knot names its Tier-Bench classes in `tierbench.task_classes` (default map: `graded-coding -> tierbench-T1`, an analogy the plan prints)
and its own open-weight tier in `tierbench.open_weight_tier`, which is always planned on the fabric so the grid row exists.

## Conventions kept

- Nothing here asserts a result. The importer carries Tier-Bench's own bases (`real-billed`, `shadow-estimated`, `unbilled-zero`) and never
  promotes an estimate to measured; a route.py cost is `DERIVED` from list prices and says so.
- Every missing input is a written reason: no class evidence, no sufficient tier, no registry entry, no price, no latency.
- Inputs are read from the two entry-locked paths only; the fixtures record each source's git commit and sha256.
- `../ledger/waterline.py` and `../ledger/seats.json` are imported and read, never edited. BRIDGE.md proposes changes; it does not make them.
