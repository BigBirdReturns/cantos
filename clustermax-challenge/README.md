# SecondRun · ClusterMAX Challenge

**Does the rating improve prediction of an ordinary customer's completed job?**

This is a test of incremental predictive value, not a competing provider rating.
Freeze a public-specs-and-price baseline, a version of that same predictor with the
rating added, and the customer test cohort. Then score held-out outcomes. Ordinary
customer authority and ordinary support are required; a curated reviewer allocation
belongs in a separate study.

## Run

Python 3.10+; standard library only. No installation, account, telemetry, network
requests, GPU allocation, or shell audit is required.

```sh
python scripts/make_demo.py
python scripts/challenge.py --plan data/demo-plan.json --outcomes data/demo-outcomes.json
python -m unittest discover -s tests -v
```

The demo is synthetic. It exercises the test, not ClusterMAX or any cloud. All
submitted results remain conditional on the truth and completeness of the supplied
records. No actual ClusterMAX 3.0 provider outcome packet has been tested here.

## The six gates

1. **Frozen experiment.** The outcome packet must reference the SHA-256 of the exact
   plan bytes. Freeze the rating version, rubric hash, predictors, cohort, primary
   metric and minimum effect before any test job starts.
2. **Complete cohort.** Exactly one terminal record per planned trial. Retain timeouts,
   failed provisioning, restarts and errors. No duplicate, added or missing trials.
3. **Customer scope.** Both plan and outcome specify ordinary tenant permissions and
   standard support. Workload and service identities must match. Administrative
   visibility and special reviewer treatment cannot silently become customer proof.
4. **Prospective prediction.** Both models and each prediction predate the job. This
   checks declared chronology; publish the plan hash with an independent timestamp
   to prove it was actually locked before the outcomes became known.
5. **Held-out providers.** Test providers must be absent from both training sets.
   Predictor inputs must be identical except for the rating. Freeze how the ordinal
   rating becomes a probability on training data; never choose that mapping after
   looking at test outcomes.
6. **Incremental value.** Compare Brier loss of the baseline and baseline-plus-rating
   on the same jobs. Average within provider, then give each provider equal weight.
   Resample providers, not individual jobs. Report the paired 95% percentile
   bootstrap interval and the preregistered minimum useful improvement.

An admissible packet with a lower interval bound above the minimum reports
`LIFT_DEMONSTRATED_ON_SUBMITTED_DATA`. An admissible packet without that evidence
reports `LIFT_NOT_DEMONSTRATED`. Incomplete, contradictory or out-of-scope records
report `HOLD`. Absence of data reports `NOT_TESTED`. A negative result concerns this
cohort, endpoint and predictor mapping, not every possible use of a rating.

## What the endpoint means

The binary outcome is a completed job meeting **all** preregistered accepted-work,
tail-latency and total-cost gates. Noncompleted jobs count as failures. Accepted
work uses a named validator and workload digest; all charged resources, paid setup,
restarts and idle time belong in total cost. Source receipt IDs/hashes preserve a
reference, but this tool does not authenticate underlying billing or execution.

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
The default minimum of eight providers is an explicit demonstration gate, not a
power calculation or a universal sufficiency threshold. Plan sample size and effect
size for the actual study. A bootstrap interval is descriptive under its sampling
assumptions and does not guarantee coverage in small or dependent cohorts.

This endpoint tests one procurement-relevant claim. It does not measure rare-event
security, long-run reliability, default risk, recovery value or creditworthiness.
Those require different outcomes and observation windows. Do not turn this test into
another general-purpose badge.

## Public-code probes

`python scripts/probe_audit_runner.py PATH_TO_audit_runner.py` executes the exact
upstream orchestration module after checking its pinned Git blob hash. Collector,
reporter and target-detection dependencies are synthetic test doubles. No host
collector, subprocess or provider is exercised. The probes establish return-code
behavior only; they do not validate the full CLI, discovery, collectors or ratings.

The source tested is ClusterMAX commit
`97865af001e5bbf2f0ea5672ec0f8c0d7fb123f4`, file `cmax/audit_runner.py`, Git blob
`b8086eccad5ceb4bf65325355a47209d49bc1aa7`. Source is not redistributed in this kit.
The inspection record is in `data/upstream-probes.json`. A zero return can coexist
with warnings/skipped checks, and with reported failures in the non-gating path.
These are documented control-flow semantics and a downstream integration risk,
not a claimed vulnerability or a finding that the private rating is broken.

## Files and maintenance

`index.html` is a standalone browser scorer with the same input contract. It makes
no requests when evaluating files. `scripts/challenge.py` is the reference scorer;
`tests/` tests failure modes and synthetic positive/negative controls. Source and
protocol references are in `data/sources.json`. All files are steward-owned; no
scheduled task writes them. Original code is MIT licensed. ClusterMAX belongs to
SemiAnalysis; no affiliation or endorsement is implied.

What can rot: upstream paths and API contracts, public pricing assumptions used by
a submitter, and browser APIs. A changed upstream file is refused by the pinned
probe. New targets require a separate reviewed snapshot. Do not overwrite the
recorded results to make a later version look as though it was tested earlier.
