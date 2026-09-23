# SecondRun · ClusterMAX Challenge

**Does the rating predict the job?**

ClusterMAX calls itself the industry standard. We could find no published study testing
whether its medals predict customer outcomes. Here is the test. Anyone with job records can run
it: add the rating to a public-specs-and-price predictor, then measure whether it
improves predictions on ordinary customer jobs at held-out providers. This is a
standing, open challenge, not a one-off report — it stays open until someone runs it
on real records.

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
   for the providers under test, so nothing here can depend on knowing a
   medal in advance. It also carries no rubric hash: a design frozen before
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
  independent timestamp), run 2026-09-23: 9 of 59 providers rated in 2.0 publish
  status history deep enough to check; reading **inconclusive** (Spearman rho +0.64
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
**reference anchor** (0.50), and two prespecified alternative weights (0.10, 0.40)
for sensitivity. These are SecondRun's uncalibrated research assumptions, adopted to
make the mapping concrete enough to test — **not probabilities asserted by
SemiAnalysis**, and not fitted to any real outcome data.

A plan carries the transform object inline plus `transform_sha256`, the SHA-256 of
its canonical JSON bytes (`sort_keys=True, separators=(',', ':')`, identical
Python/JS). The scorer recomputes, per trial, from the medal in the bound
binding record (see "The three records" above — the plan itself carries no
medal):

```
p_with_rating = (1 - weight) * p_baseline + weight * anchor[bound_medal]
p_reference    = (1 - weight) * p_baseline + weight * reference_anchor
```

Results report **two** paired comparisons: baseline vs. with-rating,
and **reference vs. with-rating** — the second isolates medal-specific information
from the mere presence of a rating input, since both blends use the same weight and
differ only in whether the anchor is medal-aware. The prespecified alternative
weights and a leave-one-provider-out recomputation of the reference-comparison lift
are reported alongside the primary result as sensitivity checks, not as a search for
the most favorable weight.

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
   job starts — before, in general, a medal even exists for the test providers, and
   before the rating's own rubric for that version is even known.
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
8. **Incremental value.** Compare Brier loss of the baseline and baseline-plus-rating,
   and separately of the medal-blind reference and baseline-plus-rating, on the same
   jobs. Average within provider, then give each provider equal weight. Resample
   providers, not individual jobs. Report the paired 95% percentile bootstrap
   interval for both comparisons and the preregistered minimum useful improvement.

An admissible packet reports `PILOT_DESCRIPTIVE_RESULT` with a `signal`:
`positive` when the lower bound of the reference-comparison bootstrap interval
exceeds the preregistered minimum lift, `negative` when the upper bound is below
zero, and `inconclusive` otherwise. Incomplete, contradictory or out-of-scope
records report `HOLD`. Absence of data reports `NOT_TESTED` on the page. Exit codes:
`0` for an admissible descriptive result, `2` for `HOLD`. A `positive` or `negative`
signal concerns this cohort, endpoint, transform and predictor mapping — it is a
pilot descriptive result, not a certification, and not a claim about every possible
use of a rating.

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

Hot Aisle provided $200 in compute credits to support tests I had already planned
independently. I have also built and shared tooling for its service. Hot Aisle is
excluded from the primary ClusterMAX comparison. It was rated Underperforming in
ClusterMAX 1.0 and Bronze in 2.0 and 2.1. I have publicly criticised SemiAnalysis.

## When ClusterMAX 3.0 ships

This challenge does not know what ClusterMAX 3.0's rubric or medal table will
contain, and makes no claim about what the release will or won't include. When it
ships, [`launch/README.md`](launch/README.md) is the procedure this repo follows: it
records, per medal, exactly which particulars the release supplies — the
service/product and region the medal covers, the customer permissions and support
tier that produced the observations, the evidence published for the medal and how it
yields the tier, the test dates, and whether the release provides anything allowing a
predictive check — and which particulars it omits, then binds supplied medals to this
frozen test. `scripts/launch_ledger.py` validates a filled ledger against
`launch/claims-3.0.template.json`'s schema and, once the ledger supplies medals plus a
medal-table source and a rubric source, can emit a `binding.json` draft for a frozen
plan.

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
can emit a binding draft from it (see "When ClusterMAX 3.0 ships" above). Source and
protocol references are in `data/sources.json`. All files are steward-owned; no
scheduled task writes them. Original code is MIT licensed. ClusterMAX belongs to
SemiAnalysis; no affiliation or endorsement is implied.

What can rot: upstream paths and API contracts, public pricing assumptions used by
a submitter, and browser APIs. A changed upstream file is refused by the pinned
probe. New targets require a separate reviewed snapshot. Do not overwrite the
recorded results to make a later version look as though it was tested earlier.
