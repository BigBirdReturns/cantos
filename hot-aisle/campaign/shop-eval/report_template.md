# <shop name> · shop evaluation report

`diagnose/diagnose.py` writes its output into this shape at `runs/<shop>-<date>/REPORT.md`.
If `diagnose.py` was not available yet, copy this file there and fill it by hand from
`fingerprint/fingerprint.json`, `bench/cell-*.json`, `engine_table.json`, and
`counter/records/<shop>-<yyyy-mm>.json`. Every blank below must be filled or explicitly marked
`unobserved` / `not run` -- never left blank and never guessed. Plain language, no marketing.

## Verdict

> One sentence: is <shop> better, worse, or a wash against Hot Aisle for this workload, at
> this price, on this day -- and why in six words or fewer after the dash.

## The one table

All bench figures from one evaluation window; `x Hot Aisle` compares directly to the reference
in `diagnose/reference/hotaisle-2026-09.json`, so this table lines up against every other
shop's report in `runs/`.

| | <shop> | Hot Aisle (reference) | x Hot Aisle |
|---|---|---|---|
| GPU | <e.g. H100> | MI300X | -- |
| rate ($/GPU-h) | | 2.99 | |
| $/1k accepted (modeled, list rate) | | 0.74 | |
| $/1k accepted (billed, if known) | | -- | |
| TTFT p95 (ms) | | 155 | |
| accepted (%) | | 50.3 | |
| time-to-SSH (s) | | 122 | |
| counter score (/100) | | -- | |

`modeled` = `engine_table.cjs` at list rate. `billed` = the actual invoice line, filled in
once it posts (see `MANUAL.md`'s disclosure rules -- never average the two into one number).

## Wrong

> What <shop> does worse than Hot Aisle, ranked by how much it costs the buyer (money, time,
> or risk) -- not by how surprising it was. Cite the specific field (fingerprint diff, cell
> file, counter dimension) behind each claim; a line with no evidence pointer is a guess, not
> a finding.

1.
2.
3.

## Right

> What <shop> does as well as or better than Hot Aisle. Include this even when the verdict is
> negative overall -- a shop that loses on price but wins on time-to-SSH or support is still
> giving useful information to whoever reads this next.

1.
2.
3.

## Could be better

> Things that are not wrong, but are below what a buyer would expect at this price or from a
> shop this size. Distinguish from "Wrong" by severity, not by feel.

1.
2.
3.

## First three changes

> If <shop>'s team reads exactly one section of this report, it is this one. Concrete,
> specific, ordered by expected impact per unit of effort -- not a wish list.

1.
2.
3.

## Provenance and disclosure

- **Evaluated by:** <name/handle> on <UTC date>.
- **Funding:** <self-funded at list price | $X credit from <shop> | other -- state plainly,
  one line, per `MANUAL.md`>.
- **Relationship:** <none | existing account | prior contact with their team | referral -- say
  which>.
- **Account used:** <new sign-up this session | existing account>.
- **Money spent, this evaluation:** $<compute> compute + $<counter> counter-protocol
  provisioning = $<total>, against a $10 target and a $15 stop-rule ceiling (`MANUAL.md`).
- **Seat:** <SKU/instance type>, region <region or "not disclosed by shop">, requested
  <UTC timestamp>, SSH ready <UTC timestamp>, deleted <UTC timestamp>.
- **Software identity:** model `Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8` @ `<revision>`,
  runtime image `<digest>`, workload id `<workload_id>` -- must match
  `../identity.json` exactly, or the bench numbers above are not comparable to Hot Aisle's and
  this report must say so instead of presenting a table.
- **What was not measured:** <carry forward anything from "What this does not measure" in
  `MANUAL.md` that applies here, plus anything specific to this run -- a skipped cell, a
  watchdog cutoff, a counter dimension left `unobserved`>.
- **Files:** `runs/<shop>-<date>/` -- `fingerprint/`, `bench/`, `engine_table.json`,
  `counter.json`, `MANIFEST.sha256` (verify with `sha256sum -c MANIFEST.sha256` before trusting
  anything above).
