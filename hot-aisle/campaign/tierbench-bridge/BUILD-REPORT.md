# BUILD-REPORT · lane E, tierbench-bridge (2026-09-23 night, for the 2026-09-24 build)

Status: **BUILT, tests passing, nothing run against a model or a provider; nothing committed.**
Written only inside `hot-aisle/campaign/tierbench-bridge/`. `../ledger/waterline.py` and `../ledger/seats.json` are imported/read, not edited.
Under Tier-Bench only the two entry-locked paths were read (W worktree at HEAD 27fbc0c, clean; R, not a git repo); no other branch,
worktree, shelf, `S:\Scratch` run or `Tier-Bench\main`. No route.py run directory was read (they are outside the lock).

## Files built

| File | Purpose |
|---|---|
| `BRIDGE.md` | the two-axis model; sufficiency rule; evidence tags; field mappings Call row / route.py receipt / map.json / waterline.json -> `tierbench-call@1` -> `run-ledger@1` + `seats.json`; proposed per-run sidecar; SeatIdentity <-> seats.json table with the authority proposal; provenance table |
| `import_tierbench.py` | importer: `tierbench-calls.jsonl` (records tagged `tierbench-measured` / `tierbench-shadow-estimated`, provenance path + git commit + sha256 + line), `tierbench-summary.json` (per class: per task, per tier: trials/pass/fail/error/partial, decisive, pass rate, cost/trial with basis, status; min sufficient tier; covering tier; residue list; map.json cross-check; waterline.json seals honoured), `tier-ladder.json` (priced tiers with seat kind api / subscription / local). route.py receipts priced as DERIVED from list x provider-reported tokens |
| `tier_waterline.py` | planner extension: Knot -> Tier-Bench classes -> tier verdicts (sufficient / partly-sufficient / unstable / wall / insufficient-evidence / unmeasured, with coverage) -> cheapest sufficient tier -> zero-seat plan (API/subscription) or fabric plan via `../ledger/waterline.py` (open weights); a grid row per tier; written reasons for every gap |
| `local_models.json` | open-weight tier -> Knot model spec registry (qwen3.5:9b, qwen2.5-coder, the Run 3 30B as `self`); bytes UNVERIFIED where so; proposed `resource_key` |
| `RUN3-GRID.md` | Run 3 EvalPlus as a Tier-Bench task class; the tier x seat grid; budget at Tier-Bench / Race 6 / seats.json list prices; what it answers (frontier residue x hardware cost) and what it does not |
| `fixtures/REGENERATE.py`, `fixtures/PROVENANCE.json` | verbatim excerpts from the pinned files (52 ledger rows across 11 tasks, 5 map tasks, whole waterline.json, 9 models, policy.json and race6 byte copies) with each source's path, last commit, pin membership, sha256 |
| `fixtures/make_synthetic.py`, `fixtures/router/receipt-synth{A..D}.json`, `fixtures/knots/knot-run3-evalplus-tierbench.json` | SYNTHETIC route.py receipts (flagged `synthetic: true` in file and in every record) and the Run 3 Knot |
| `test_all.py`, `README.md` | test runner; how to run |

## How to run

```sh
cd hot-aisle/campaign/tierbench-bridge
python test_all.py
python import_tierbench.py --fixtures --out /tmp/ev
python tier_waterline.py plan fixtures/knots/knot-run3-evalplus-tierbench.json --evidence /tmp/ev --start-at 2026-09-29T10:00:00Z
python import_tierbench.py --tierbench-root <W> --router-root <R> [--receipts <route.py receipt dir>] --out /tmp/ev   # real pinned inputs, read-only
```

## Test output summary (`python -B test_all.py`, exit 0)

```
=== import_tierbench.py --selftest      32 PASS, 0 FAIL   "all passed"
=== tier_waterline.py --selftest        19 PASS, 0 FAIL   "all passed"
=== import_tierbench.py --fixtures      68 records, 11 task classes, 15 ladder tiers (into temp)
=== tier_waterline.py plan (09-24)      exit 0: haiku@harness chosen (T1 evidence); 30B row planned on the fabric, sufficiency UNMEASURED
=== tier_waterline.py plan (09-29)      exit 0: same; estate 3090 appears among unmeasured fabric candidates
=== ../ledger/waterline.py --selftest   39 PASS (lane B's planner, imported unmodified, still passes)
ALL PASSED
```

What the importer self-test pins: provenance commit/sha on every record; T0/T1/T3/T4 tasks sufficient at haiku@harness and agreeing
with map.json; task02 floor unstable and sealed at sonnet@low by waterline.json (real-billed -> `tierbench-measured`); the seal wins over
a derivation when five `cheap` passes are added; replay02 wall / replay04 unstable / almanac escalation from an unstable floor flagged;
errors excluded from decisive; shadow rows never promoted; unbilled-zero on blank rows; route receipts: ollama $0 local with the host
unmapped, luna cost derived with the race6 cache discount, skipped and failed attempts null with reasons, wrong schema refused;
ladder ordering haiku < sonnet < fable@low < fable@high; race6 kept as aggregates.

What the planner self-test pins: graded-coding -> T1 -> haiku@harness zero-seat plan ($20.47 carried as shadow-estimated; serial wall
5.99 h exceeds the 90 min deadline, concurrency 4 written); grader seats named; open-weight 30B UNMEASURED with reason and a fabric
plan (cheapest Hot Aisle $0.85 modeled); unknown class refused with reason; task02 class -> sonnet@low with partial coverage stated;
pooled T0+T1; missing class named; qwen 9B through the fabric on the estate 3090 with the routing-evidence caveat and unmeasured
curves; a local tier without a registry entry -> no plan, reason; render.

**Live read-only run on the real pinned inputs** (into temp, not kept): 160 records (140 shadow-estimated, 20 measured), 10 classes,
15 ladder tiers; every class's covering tier is haiku@harness except arc-c-almanac (fable@low after an unstable floor), arc-d-b2-grade
(no sufficient tier: fable@high 2/2 real-billed but < K, plus partial/error rows) and breadth-task02-wildcard (sonnet@low, sealed);
zero disagreements with map.json; one recorded disagreement with the whole-window derivation (task02 `cheap` 5/5 vs the seal), resolved
in favour of the seal and written.

## Findings worth carrying

- Tier-Bench's Claude ledger has **no open-weight rows at all**: every "local model costs 0" in models.json is a declaration. The 30B
  and qwen 9B rows of the grid exist only after Run 3 / the estate arm. `tier_waterline` says UNMEASURED for them and still plans the seat.
- Tier-Bench trial latencies (median ~40 s for a haiku harness trial) make a serial API plan miss the Knot deadline; concurrency is a
  plan parameter the fabric ledger never needed. Written into the zero-seat plan.
- The two "attempts" tables are different denominators (fabric job attempts on a present seat vs ledger provisioning attempts); BRIDGE.md
  refuses to merge them.
- `tier_runner/fabric/*` is post-pin (98e12ac / 86d05f2, Aug 18-20); everything else read is inside the 9693cb9 pin. Recorded per file.

## Open questions

1. **Sidecar reader.** BRIDGE.md 2e proposes `tierbench-calls.jsonl` beside each Run 3 run ledger. The importer classifies `evalplus:` ids
   but does not yet read `detailed.json + grade/evaluation.json` directly; that reader belongs with lane B's builder or as a `--run3-arm`
   input here. Which lane owns it?
2. **Default class map.** `graded-coding -> tierbench-T1` is an analogy. Should the Knot be required to name classes explicitly (no default)?
3. **Sealed vs derived.** The bridge honours waterline.json seals. Should it also apply Tier-Bench's rolling latest-K window instead of
   the whole-window rule? Today it recomputes conservatively and records the disagreement.
4. **Subscription pricing.** Codex tiers are list-priced from the race6 diagnostic for comparison; the true marginal cost is the weekly
   window. The zero-seat plan says so; is a "window-fraction" cost model wanted?
5. **seats.json additions** (`hardware_identity`, `contention_domain`, `tierbench_seat_id`, `priors["graded-coding"]`) are proposals in
   BRIDGE.md 3; lane B decides.
6. **Contamination.** EvalPlus is public-graded; Tier-Bench's hidden-grading standard is not met by Run 3. RUN3-GRID.md states it; a hidden
   variant (held-out plus tests) would be a later class.

## What the operator must supply

- Nothing for this lane to run its tests (offline). To import real route.py receipts: the path to the durable receipt root
  (`D:\Projects\Measurement\Tier-Bench\exports\our-auto-router`, outside this lane's entry lock; the operator must lift the lock).
- For the grid itself: Run 3 approval (~$25 cloud, already in SYNTHESIS), an API key / Codex window for the haiku and luna rows
  (~$4 list + subscription window), the plug meter and tariff for the estate row, and the 3090 after ~09-28.
- A decision on open questions 1, 2 and 5.
