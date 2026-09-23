# SecondRun · ClusterMAX Challenge

**Does the rating predict the job?**

ClusterMAX 3.0 is out. This standing test asks whether adding its medal improves predictions of ordinary customer outcomes beyond public specifications and price. The instrument accepts source-bound submissions; no prospective customer-outcome result has been supplied. The separate R1 retrospective result is inconclusive. See the [3.0 evidence ledger](launch/index.html).

This is a test of incremental predictive value, not a competing provider rating.
Freeze a public-specs-and-price baseline, a version of that same predictor with the
rating added, a frozen medal-to-probability transform and the customer test cohort.
Then score held-out outcomes. Ordinary customer authority and ordinary support are
required; a curated reviewer allocation belongs in a separate study.

## Run

Python 3.10+; standard library only. No installation, account, telemetry, network
requests, GPU allocation, or shell audit is required.

```sh
python scripts/make_demo.py
python scripts/challenge.py --plan data/demo-plan.json --binding data/demo-binding.json --outcomes data/demo-outcomes.json
python -m unittest discover -s tests -v
node tests/test_engine.cjs
```

The demo is synthetic. It exercises the test, not ClusterMAX or any cloud. All
submitted results remain conditional on the truth and completeness of the supplied
records. No actual ClusterMAX provider outcome packet has been tested here.

## The three records

Scoring a submission takes three separate JSON records, in this order:

1. **`plan.json`** (schema `secondrun.rating-plan.v4`) — the design, frozen
   before the jobs ran. Predictors, cohort, transform, primary metric and
   minimum effect are all locked here. Critically, **it carries no `medal`
   field**: a design can (and should) be frozen before a rating even exists
   for the providers under test, so medal observation stays separate from design. A post-medal design is permitted when explicitly identified and frozen before future outcomes. It also carries no rubric hash: a design frozen before
   ClusterMAX 3.0 exists cannot know 3.0's rubric. Instead it commits to
   `rating_name`, `rating_version` (expected), and a `binding_rules` object
   (`medal_source`, `rubric_source` — which official sources the binding must
   later cite — and `tiers`, which must equal the transform's frozen anchor
   tiers exactly). The rubric hash itself moves to `binding.json`, below,
   where it belongs: it can only be known once the rating actually publishes.
2. **`binding.json`** (schema `secondrun.rating-binding.v2`) — filled in
   later, once the rating actually publishes: which rating and version, where
   the medal table came from (`source.url`, and its `sha256`), where the
   rubric came from (`rubric.url`, and its `sha256`), when both were read
   (`source.retrieved_utc`, `rubric.retrieved_utc`), when the binding itself
   was made (`bound_at`), and the medal per test provider (`medals`). It
   references the exact `plan.json` bytes by hash (`plan_sha256`), so it
   can't be quietly rewritten to match a different plan.
3. **`outcomes.json`** (schema `secondrun.rating-outcomes.v4`) — the terminal
   job records, referencing both the plan and the binding by hash
   (`plan_sha256`, `binding_sha256`).

The scorer holds the packet if the binding doesn't hash-match the plan it
claims to bind, if the outcomes don't hash-match the exact binding bytes
(tamper), if the binding's rating name/version don't match the plan's (wrong
vintage), if `binding.medals` doesn't cover exactly the plan's test providers
(one missing or one extra), if a bound tier isn't one of the five frozen
anchor tiers (an unrated or unavailable provider is never silently scored as
"Underperforming"), if `bound_at` precedes the plan's freeze or lands at or
after any trial's `started_at` (a medal chosen, in effect, after the attempt),
or if `binding.rubric` is missing, incomplete or its `sha256` isn't lowercase
hex, or if either `source.retrieved_utc` or `rubric.retrieved_utc` lands
after `bound_at` (a source read, in effect, after the binding claims to have
been made). `p_with_rating` is always recomputed from the bound medal — never
supplied by the plan, since the plan doesn't know it yet.

`plan.json` also carries a structured `disclosure` object (`relationship`,
`compensation`, `credits`, `special_support`, `editorial_influence`), each a
required, nonempty, non-placeholder field — the scorer holds a packet whose
disclosure is missing or still says `CONFIRM`, `TBD`, `TODO`, `???`, "none /
describe" or similar. `scripts/release_check.py` separately checks this
repo's own `index.html`/`README.md` for the same kind of unanswered
placeholder (see "Files and maintenance" below) — that is a human-facing
release gate, not part of `evaluate()`.

## Other work on this challenge

* **[Retrospective study R1](retrospective/PLAN.md)** — a frozen, look-back question
  about whether ClusterMAX medals track providers' own public incident records. Plan
  committed before collection (commit 73da1cf; git time is self-reported, not an
  independent timestamp), run 2026-09-23: our collection obtained 9 eligible histories from 59 providers rated in 2.0; reading **inconclusive** (Spearman rho +0.64
  between medal and self-reported major/critical incidents, 95% bootstrap interval
  0.00 to 0.94, permutation p = 0.075). The direction (higher medal, more reported
  incidents) fits the plan's stated limit that detailed self-reporting looks worse.
  See [the result](retrospective/results/R1-result.md) and
  [exclusion reasons](retrospective/incidents/INELIGIBLE.md).
* **[Submit your own job records](SUBMITTING.md)** — bring a real, frozen design, the
  medal binding filled in once the rating published, and terminal outcomes. The scorer
  runs the same way on real or synthetic input.

## The medal-to-probability transform

`design/transform.json` (schema `secondrun.rating-transform.v1`) fixes, before any
outcome packet is scored, how an ordinal medal becomes a probability contribution:
an anchor probability per tier (Platinum 0.90 down to Underperforming 0.30), a
blend weight (0.25) against the supplied baseline probability, a medal-blind
**reference anchor** (0.50, used only in the v1.3 descriptive comparisons — see
"The medal permutation test" below for the primary result), and two prespecified
alternative weights (0.10, 0.40) for sensitivity. These are SecondRun's
uncalibrated research assumptions, adopted to make the mapping concrete enough to
test — **not probabilities asserted by SemiAnalysis**, and not fitted to any real
outcome data.

A plan carries the transform object inline plus `transform_sha256`, the SHA-256 of
its canonical JSON bytes (`sort_keys=True, separators=(',', ':')`, identical
Python/JS). The scorer recomputes, per trial, from the medal in the bound
binding record (see "The three records" above — the plan itself carries no
medal):

```
p_with_rating = (1 - weight) * p_baseline + weight * anchor[bound_medal]
p_reference    = (1 - weight) * p_baseline + weight * reference_anchor
```

Results also report the two v1.3 paired comparisons — baseline vs. with-rating, and
fixed 0.50-reference vs. with-rating — but as **descriptive only** (see "The medal
permutation test" below for why). The prespecified alternative weights and a
leave-one-provider-out recomputation of the reference-comparison lift are reported
alongside them as sensitivity checks, not as a search for the most favorable weight.

## The medal permutation test

This is the headline test as of v1.4.0. It asks one question: do the bound medals
rank the held-out providers better than chance?

For each test provider it compares two predictors built from the *same* baseline
and the *same* blend weight, differing only in which anchor they blend toward:

```
p_medal = (1 - weight) * p_baseline + weight * anchor[bound_medal]
p_level = (1 - weight) * p_baseline + weight * mean(bound anchors across the cohort)
```

`T`, the statistic, is the provider-equal-weighted mean over test providers of
`Brier(p_level) - Brier(p_medal)`. Because `p_medal` and `p_level` receive the same
*average* shift (the cohort-mean bound anchor vs. each provider's own bound
anchor), `T` measures only the ranking information in *which* provider got which
medal — not a level/calibration shift. The null hypothesis is that bound medal
labels are exchangeable across providers: every distinct assignment of the
multiset of bound medals to providers is enumerated when there are at most 20,000
of them (`p = count/N`, the observed assignment counted among the N); otherwise
20,000 seeded Fisher-Yates shuffles (seed 20260923) are drawn instead
(`p = (1+count)/(1+N)`). `signal` is `positive` when `p_help <= 0.05` and `T`
exceeds the preregistered minimum lift, `negative` when `p_hurt <= 0.05` and `T` is
below minus that same lift, `not_testable` when the cohort holds fewer than two
distinct bound medals, and `inconclusive` otherwise.

**Why the primary test changed.** An independent adversarial review of the v1.3
design found that its `positive`/`negative` calls — based on the fixed 0.50
reference — rewarded any uniform upward shift in pass rate, not medal-specific
information: every anchor from Bronze up sits above 0.50, so a cohort that simply
passed often "improved" on the reference regardless of which medals its providers
actually held, and shuffled, rank-irrelevant medals could still score positive. No
real submission had ever been scored under v1.3; the flaw was caught before it
judged a real packet. The permutation test isolates medal-specific ranking
information from that level shift by holding both compared predictors to the same
average anchor.

**Locks added in v1.4.** A plan's inline `transform` must canonically hash to a
transform listed in `design/registry.json` — an edited or custom transform is held,
even if internally well-formed. Transform anchors must be strictly decreasing,
Platinum > Gold > Silver > Bronze > Underperforming. Every trial sharing a
`workload_sha256` must carry identical `gates`. Both predictors'
`training_providers` lists must be nonempty. A binding for a rating version that is
itself registered in `design/registry.json` (currently ClusterMAX 3.0) must cite
one of that entry's registered medal-table source digests as `binding.source.sha256`,
and every bound medal must equal the registered transcription's tier for that exact
provider name — an unregistered rating is still scored, just flagged
`source_unverified`.

## The coverage floor

Every held-out provider must supply, within the scored cohort:

* at least **10 trials**,
* at least **5 distinct `session_id` values** (a required field on every plan trial
  row), and
* at least **3 distinct UTC calendar dates** of `started_at`.

A provider short of any of these fails the packet with `HOLD` and a reason naming
the provider and the shortfall. This exists so a "provider" result can't rest on a
handful of jobs from one session on one day.

## The gates

1. **Frozen experiment.** The outcome packet must reference the SHA-256 of the exact
   plan bytes. Freeze the rating version (expected), the binding rules (which official
   medal-table and rubric sources the later binding must cite, and the frozen tier set),
   the transform, predictors, cohort, primary metric and minimum effect before any test
   job starts. Record whether this occurs before or after publication of the medals; do not claim pre-medal priority from a self-reported date.
2. **Bound, not backfilled.** The medal binding is a separate record (see "The three
   records" above), hash-referencing the exact plan it binds to. It must be bound at or
   after the plan's freeze and strictly before every trial's `started_at`, name the same
   rating and version as the plan, cite both the medal table and the rubric it relied on
   (each read at or before `bound_at`, never after), and cover exactly the plan's test
   providers with tiers drawn only from the frozen anchor set.
3. **Complete cohort.** Exactly one terminal record per planned trial. Retain timeouts,
   failed provisioning, restarts and errors. No duplicate, added or missing trials.
4. **Customer scope.** Both plan and outcome specify ordinary tenant permissions and
   standard support. Workload, service and session identities must match. Administrative
   visibility and special reviewer treatment cannot silently become customer proof.
5. **Prospective prediction.** Both models and each prediction predate the job. This
   checks declared chronology; publish the plan hash with an independent timestamp
   to prove it was actually locked before the outcomes became known.
6. **Held-out providers.** Test providers must be absent from both training sets.
   Predictor inputs must be identical except for the rating. The medal-to-probability
   transform is frozen before scoring; never choose anchors or weight after looking
   at test outcomes.
7. **Coverage floor.** See above.
8. **Incremental ranking value.** The primary test (see "The medal permutation
   test" above) is a medal-permutation significance test: does giving each
   held-out provider its own bound medal's anchor beat giving every provider the
   cohort-mean anchor, against a preregistered minimum useful lift? Give each
   provider equal weight; resample providers, not individual jobs, for the
   descriptive bootstrap interval. The v1.3 comparisons against the plain
   baseline and the fixed 0.50 reference are still computed and reported, but as
   descriptive context only — they include a level shift and do not isolate
   medal-specific information.

An admissible packet reports `PILOT_DESCRIPTIVE_RESULT` with a `signal` from the
medal permutation test: `positive` when `p_help <= 0.05` and the observed `T`
exceeds the preregistered minimum lift, `negative` when `p_hurt <= 0.05` and `T`
is below minus that same lift, `not_testable` when the cohort holds fewer than
two distinct bound medals, and `inconclusive` otherwise. Incomplete,
contradictory or out-of-scope records report `HOLD`. Absence of data reports
`NOT_TESTED` on the page. Exit codes: `0` for an admissible descriptive result,
`2` for `HOLD`. A `positive` or `negative` signal concerns this cohort, endpoint,
transform and predictor mapping — it is a pilot descriptive result, not a
certification, and not a claim about every possible use of a rating.

## What the endpoint means

The binary outcome is a completed job meeting **all** preregistered accepted-work,
tail-latency and total-cost gates. Noncompleted jobs count as failures. Accepted
work uses a named validator and workload digest; all charged resources, paid setup,
restarts and idle time belong in total cost. Source receipt IDs/hashes preserve a
reference, but this tool does not authenticate underlying billing or execution.

**Credits accounting.** An outcome row's `total_cost_usd` is the normal list-price
charge for that job, before any credits — the cost-max gate and
`cost_per_1000_accepted` are always computed from this list charge only, never a
credits-reduced figure. A row may separately declare an optional
`credits_redeemed_usd` (finite, ≥0, defaults to 0 when absent) for GPU-cloud credits
redeemed toward that job; the scorer holds the packet if a row's credits exceed its
own list charge. The `economics` output reports each row's list charge and its
credits redeemed as two separate numbers, and the result carries a top-level
`subsidized_trials` count of rows with nonzero credits. Subsidised testing must never
be allowed to appear to show a lower commercial operating cost than an ordinary
customer would pay — that is exactly what keeping the list charge as the only figure
used in gates and cost-per-accepted-unit protects against.

The experiment is predictive, not a causal experiment on what access caused. To
measure a reviewer-treatment effect, preregister paired ordinary/reviewer
allocations of the same service, alternate or randomize assignment, and keep the
two arms separate. This first release refuses reviewer rows in the ordinary-customer
claim rather than inventing a causal estimate from unmatched samples.

## Interpretation and limits

The baseline is supplied, not fitted by this tool. A weak baseline, fabricated
receipt, false training declaration or undisclosed model input can still bias an
apparently valid packet. Independent custody, timestamping and review are external
requirements. Hashes detect byte changes; they do not prove origin or honesty.

**What is not, and cannot be, locked.** The per-row `p_baseline` is the submitter's
own choice; nothing in this engine fits it or checks it against the outcomes. The
only defenses are structural: the plan (and its baseline's `model_sha256`) must be
frozen, and the binding made, strictly before the medal is known to determine
`p_baseline` from it (`bound_at` at or after `frozen_at`, and strictly before every
trial's `started_at`). A baseline chosen or quietly tuned after seeing the medals
would still pass every check here — this engine cannot detect that from the
numbers alone. And because ClusterMAX 3.0's medals became public on 2026-09-23 at
21:20 UTC, any plan frozen after that moment was necessarily written with the
medals already knowable; read any such result's baseline with that in mind, even
though the plan schema does not separately flag it beyond whatever the submitter
wrote in `disclosure`.

Provider grouping prevents treating repeated jobs at one provider as independent
providers. It does not remove common hardware, regional, customer or time shocks.
The default minimum of eight providers and the per-provider coverage floor are
explicit demonstration gates, not a power calculation or a universal sufficiency
threshold. Plan sample size and effect size for the actual study. A bootstrap
interval is descriptive under its sampling assumptions and does not guarantee
coverage in small or dependent cohorts.

The medal-to-probability transform is a modeling choice, not a fact about
ClusterMAX. A different weight or anchor set would produce different numbers; the
alternative-weight sensitivity check and the leave-one-provider-out recomputation
exist so a reader can see how much the headline result moves under that choice.

This endpoint tests one procurement-relevant claim. It does not measure rare-event
security, long-run reliability, default risk, recovery value or creditworthiness.
Those require different outcomes and observation windows. Do not turn this test into
another general-purpose badge.

## Disclosure

Hot Aisle provided $200 in compute credits for my own testing.

## ClusterMAX 3.0 release

The [77-provider transcription](launch/release-3.0/clustermax-3.0.json) and [transitions from 2.1](launch/release-3.0/transitions.json) from the parallel release are preserved. Our 17-provider scoped ledger complements that transcription; it does not replace it.

The [source-bound launch ledger](launch/index.html) is post-release. It records 17 selected assignments, the managed-cluster scope and the precise limits of this review. Actual benchmark and recovery testing are acknowledged; a separate prospective prediction study remains open.

Participation Ribbon is accepted by the observation ledger but refused by the original five-tier transform. Unavailable remains a separate assessment state. No probability is silently invented for either. A compatible future plan may be registered after medals are public and before its jobs; this cannot be called pre-medal registration.

[Read the R1 interpretation note](retrospective/READOUT.md): collection coverage is not proof of publication coverage; status-report counts are not customer failure rates. Original R1 inputs, plan and outputs are retained unchanged.

## Archive: earlier public-code probes

An earlier release ran seven controlled probes of the exact public
`audit_runner.py` at commit `97865af001e5bbf2f0ea5672ec0f8c0d7fb123f4`, with
mocked collector, reporter and target-detection dependencies. No host collector,
subprocess or provider was exercised. These established return-code control-flow
behavior only — they are narrow observations about the public API, **not findings
about the CLI**: the public CLI exits 2 on failed security checks. They do not
validate the full CLI, discovery, collectors or ratings, and they are archived, kept
separate from the standing predictive-value challenge above.

`python scripts/probe_audit_runner.py PATH_TO_audit_runner.py` reproduces them after
checking the pinned Git blob hash. The source tested is ClusterMAX commit
`97865af001e5bbf2f0ea5672ec0f8c0d7fb123f4`, file `cmax/audit_runner.py`, Git blob
`b8086eccad5ceb4bf65325355a47209d49bc1aa7`. Source is not redistributed in this kit.
The record is in `data/upstream-probes.json`.

## Glossary

* **HOLD.** The status a submitted packet gets when it fails a structural or
  provenance check (a missing field, an untimestamped prediction, a
  training/test leak, a missing disclosure, a hash that doesn't match, and so
  on). It is not a verdict on the provider or the rating -- see "What happens
  to a HOLD" in [SUBMITTING.md](SUBMITTING.md).
* **Binding.** The separate record (`binding.json`) that fills in, after the
  rating actually publishes, which medal each held-out provider got and where
  that medal table and rubric came from. It hash-references the exact
  `plan.json` it binds to, so a medal can't be quietly chosen once outcomes
  are known. See "The three records" above.
* **Transform.** `design/transform.json`: the frozen, uncalibrated mapping
  from an ordinal medal tier to a probability contribution (an anchor value
  per tier, a blend weight against the baseline, and a fixed 0.50 reference
  anchor used only in the descriptive v1.3 comparisons, not the primary test).
  Must canonically hash to an entry in `design/registry.json` since v1.4. See
  "The medal-to-probability transform" above.
* **Brier loss.** The squared error between a predicted probability and the
  actual binary outcome, `(prediction - outcome)^2`. Lower is better. The
  primary medal permutation test compares each provider's own-medal blend
  against a cohort-mean-anchor blend built from the same baseline and weight;
  the descriptive comparisons separately report the plain baseline and the
  fixed 0.50-reference blend. All are averaged within provider, then across
  providers.
* **Provider bootstrap.** The uncertainty procedure used throughout: resample
  held-out *providers* (not individual jobs) with replacement 5,000 times,
  recompute the mean lift each time, and report the 2.5th/97.5th percentile
  interval. Resampling providers rather than jobs keeps repeated jobs at one
  provider from being treated as independent evidence. Reported as descriptive
  context alongside the medal permutation test's p-values, not as the primary
  significance check.
* **Permutation test.** Since v1.4, the primary significance check for this
  challenge (see "The medal permutation test" above): how often does the same
  ranking statistic, computed after every distinct way of reassigning the
  bound medals to providers (or a large seeded sample of reassignments), reach
  or exceed the actually observed value? R1 separately uses a permutation test
  over incident counts; that one remains a secondary check alongside R1's
  bootstrap interval, not the primary read.
* **R1.** The standing shorthand for the one completed retrospective study in
  this repo -- [`retrospective/PLAN.md`](retrospective/PLAN.md) asks whether
  ClusterMAX medals track providers' own public incident-report counts. It is
  a look-back association study, not the prospective customer-outcome test
  this page is about. See "Other work on this challenge" above and
  [`retrospective/READOUT.md`](retrospective/READOUT.md) for its interpretation
  and limits, including a post-hoc sensitivity addendum.

## Files and maintenance

`index.html` is a standalone browser scorer with the same input contract. It makes
no requests when evaluating files. `scripts/challenge.py` is the reference scorer;
`tests/` tests failure modes and synthetic positive/negative controls;
`tests/test_engine.cjs` checks Python/JS numeric parity (set `PYTHON` if neither
`python` nor the platform default resolves). `design/transform.json` is the frozen
medal-to-probability transform. `scripts/make_demo.py` writes the synthetic
`data/demo-plan.json` / `data/demo-binding.json` / `data/demo-outcomes.json` triple.
`scripts/submit_check.py` validates one `submissions/<id>/` directory's four files.
`scripts/release_check.py` is a separate, human-facing release gate: it fails while
`index.html`/`README.md` still carry an unanswered `[CONFIRM: ...]` disclosure marker
or similar placeholder (see "The three records" above), independent of whether the
test suite passes — CI runs it as its own `release-readiness` job so a red release
gate never blocks the (green) test job. `scripts/build_manifest.py` recomputes
`data/build.json`'s source hashes. `launch/README.md` and
`launch/claims-3.0.template.json` (schema `secondrun.launch-claims.v1`) are the
ClusterMAX 3.0 launch kit; `scripts/launch_ledger.py` validates a filled ledger and
can emit a binding draft from it (see "ClusterMAX 3.0 is out" above). Source and
protocol references are in `data/sources.json`. All files are steward-owned; no
scheduled task writes them. Original code is MIT licensed. ClusterMAX belongs to
SemiAnalysis; no affiliation or endorsement is implied.

What can rot: upstream paths and API contracts, public pricing assumptions used by
a submitter, and browser APIs. A changed upstream file is refused by the pinned
probe. New targets require a separate reviewed snapshot. Do not overwrite the
recorded results to make a later version look as though it was tested earlier.
