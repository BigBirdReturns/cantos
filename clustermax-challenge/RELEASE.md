# Launch-ready presentation 1.4.0

Upgrades the scorer's primary test to a medal-permutation significance check
(v1.4.0) without changing the five-tier transform, historical inputs or R1
output; the v1.3 baseline and fixed-0.50-reference comparisons are retained but
now reported as descriptive only. Adds a scoped 3.0 observation ledger,
separates collected histories from publication claims, fixes pre-medal/pre-outcome
instructions and the issue-submission link, and keeps the disclosure visible.

This is a published test instrument, not a registered customer experiment or a finding against ClusterMAX. The six-tier observation ledger does not silently change the five-tier predictor. No cloud resources are allocated by this release.

## Verification

The reconciled release passed 207 Python unit tests and 166 Node checks against the embedded browser engine, including hash vectors and numerical agreement. Disclosure validation and diff whitespace checks passed. No new real GPU job or prospective outcome was produced. Fresh native browser navigation was not requalified in this session; the earlier v1.3 browser results are historical, not a new claim. Exact deployed bytes are checked separately after publication.

The concurrent 77-provider transcription, transition dataset and latest one-line disclosure were preserved. Four truncated source-hash fields were restored from the retained capture manifest, checked against Git source bytes where published; the correction log preserves the prior fields. Original R1 inputs/results and the five-tier probability transform were not changed.

## CHANGELOG

### v1.4.0 (2026-09-23)

- **Primary test changed to a medal permutation test.** `T` is the
  provider-weighted mean Brier improvement of the medal-blend predictor over a
  level-matched blend built from the cohort's mean bound anchor, so both
  predictors receive the same average shift and `T` carries only ranking
  information. `p_help`/`p_hurt` come from exact enumeration of every distinct
  medal-to-provider assignment (up to 20,000 of them) or 20,000 seeded
  Fisher-Yates shuffles otherwise. `signal` is `positive`, `negative`,
  `inconclusive` or `not_testable`, with symmetric thresholds on both sides.
- **Why it changed:** an independent adversarial review found that v1.3's
  `positive`/`negative` calls, driven by the fixed 0.50 reference, rewarded any
  uniform upward shift in pass rate rather than medal-specific information --
  shuffled, rank-irrelevant medals could still score positive, since every
  anchor from Bronze up sits above 0.50. No real submission had ever been
  scored under v1.3; the flaw was caught before it judged a real packet.
- The v1.3 comparisons (vs. plain baseline, vs. fixed 0.50 reference) are kept
  for continuity but reported under `descriptive` only, since both include a
  level shift and do not isolate medal-specific information.
- **New locks:** a plan's `transform` must canonically hash to a transform
  registered in `design/registry.json`; transform anchors must be strictly
  decreasing (Platinum > Gold > Silver > Bronze > Underperforming); every
  trial sharing a `workload_sha256` must carry identical `gates`; both
  predictors' `training_providers` must be nonempty; a binding for a
  registered rating version (currently ClusterMAX 3.0) must cite a registered
  medal-table source digest, and every bound medal must exactly match the
  registered transcription's tier for that exact provider name (unregistered
  ratings are still scored, flagged `source_unverified`).
- Removed the republished ClusterMAX 1.0/2.0 newsletter article pages and the
  newsletter-archive listing from the published tree (commit `64be88b`);
  their hashes remain recorded, and a test now fails if any paid-article
  marker text reappears anywhere under the challenge.
- Added the R1 post-hoc sensitivity addendum to `retrospective/READOUT.md`
  (bootstrap-lower-bound seed sensitivity, exact vs. capped-random permutation
  p, one mislabeled-incident sensitivity check, and the leave-one-provider-out
  rho range) -- computed after the frozen R1 run, without changing R1's own
  pre-registered result or code.
- `scripts/csv_to_packet.py` now imports its canonical-hashing function from
  `scripts/challenge.py` instead of keeping a private duplicate.

### v1.3.1 and earlier

See git history; this file did not carry a structured changelog before v1.4.0.
