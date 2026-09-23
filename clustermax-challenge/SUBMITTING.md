# Submitting to the ClusterMAX challenge

There are two different things you can submit here, and they are evaluated
differently. Do not mix them in one submission.

1. **A prospective plan+binding+outcomes packet** -- you ran real GPU-cloud
   jobs as an ordinary customer, froze a design before running them (before a
   medal tier even existed for these providers, if applicable), separately
   recorded which medal each provider actually got once the rating published,
   and now have the terminal outcomes. This is what `scripts/challenge.py`'s
   `evaluate()` scores.
2. **A retrospective incidents correction** -- you have a more complete or more
   accurate status-page incident history for a provider than what's in
   `retrospective/incidents/`. This feeds `scripts/retrospective.py`'s R1
   study, not the prospective challenge.

## 1. Plan+binding+outcomes packets (the prospective test)

For claims about ClusterMAX 3.0, identify the managed-cluster service, configuration, region, ordinary customer permissions and standard support in SUBMITTER.md. Bare-metal-only or token-endpoint evidence belongs to a different claim. Maintainer review must verify this service match; the generic scorer cannot infer it from a provider name. The original five-tier transform still holds Participation Ribbon inputs.


### Requirements

- **Ordinary customer account.** No reviewer, admin, or special-access
  treatment. `plan.json`'s trials must declare `customer_role: "ordinary_tenant"`
  and `support: "standard"` -- anything else is held.
- **Plan frozen before jobs ran.** Record separately whether the medals were already public.
  Every trial's `predicted_at` timestamp must be at or before the plan's
  `frozen_at`, and strictly before the job's own `started_at`. `plan.json`
  carries no `medal` field and no rubric hash -- you cannot add or edit
  predictions after seeing outcomes, a published medal can be known at freeze time if that fact is disclosed. Instead `plan.json` commits to
  `rating_name`, `rating_version` (expected), and a `binding_rules` object
  (`medal_source`, `rubric_source` -- which official sources the later binding
  must cite -- and `tiers`, which must equal the transform's frozen anchor
  tiers exactly).
- **Binding filled in after the rating, before the attempt.** `binding.json`
  is a separate record: it names the rating and version, cites where you got
  the medal table (`source.url` and its `sha256`) and the rubric
  (`rubric.url` and its `sha256`), and stamps `bound_at`. `bound_at` must be
  at or after the plan's `frozen_at` and strictly before every trial's
  `started_at` -- you cannot bind a medal after a job already ran. Both
  `source.retrieved_utc` and `rubric.retrieved_utc` must be at or before
  `bound_at` -- you cannot cite a source you claim to have read after you
  already bound. `binding.medals` must cover exactly the provider set in
  `plan.json`, no more, no fewer, and every tier must be one of the five
  frozen anchor tiers (an unrated/unavailable provider is not silently
  "Underperforming" -- it's a missing-provider hold).
- **Credits, if any, reported honestly.** An outcome row's `total_cost_usd`
  is the normal list-price charge, before credits. If you redeemed GPU-cloud
  credits toward a job, declare the amount in that row's optional
  `credits_redeemed_usd` (defaults to 0 if omitted) -- it cannot exceed the
  row's own `total_cost_usd`. Gates and `cost_per_1000_accepted` are always
  computed from the list charge only; `evaluate()`'s `economics` output and
  top-level `subsidized_trials` count report the list charge and any credits
  redeemed separately, never netted against each other.
- **Every attempt retained.** Don't drop trials that failed, timed out, or
  cost more than expected. The plan's trial list and the outcomes' trial list
  must match exactly -- no extra, no missing.
- **Receipts referenced by hash.** Every outcome row needs a `receipt_sha256`
  and a `receipt_ref` pointing at your actual job receipt/invoice. Don't submit
  a receipt itself if it contains billing details you don't want public --
  reference it by hash and keep the receipt available if asked.
- **Disclosure answered in the plan itself.** `plan.json`'s `disclosure` object
  (`relationship`, `compensation`, `credits`, `special_support`,
  `editorial_influence`) must be filled in with real text -- `evaluate()`
  holds a packet whose disclosure fields are empty or still a placeholder
  (`CONFIRM`, `TBD`, `TODO`, `???`, "none / describe", etc.).
- **Redact secrets.** Strip API keys, account IDs, internal hostnames, and
  anything else identifying before you submit. `submit_check.py` does not
  redact anything for you.

None of this requires our involvement to prepare -- freeze your own plan,
run your own jobs, submit your own outcomes.

### How to submit

Pick one:

- **Open a GitHub issue** using the
  [ClusterMAX outcomes submission template](https://github.com/BigBirdReturns/axm-tools/issues/new?template=clustermax-outcomes.yml)
  (`.github/ISSUE_TEMPLATE/clustermax-outcomes.yml`). Paste your `plan.json`,
  `binding.json` and `outcomes.json` (or link to them) and fill in the
  disclosure section. A maintainer will run `scripts/submit_check.py` against
  what you provide and reply with the result.
- **Open a pull request** adding a new directory under
  `clustermax-challenge/submissions/<id>/` containing exactly:
  ```
  submissions/<id>/plan.json
  submissions/<id>/binding.json
  submissions/<id>/outcomes.json
  submissions/<id>/SUBMITTER.md
  ```
  See `submissions/README.md` for the directory layout and what `SUBMITTER.md`
  needs (in particular, a `## Disclosure` section: your relationship, if any,
  to any provider or rating in the plan). CI runs
  `python scripts/submit_check.py submissions/<id>` on every submission
  directory in the repo; it must pass (exit 0) before merge.

Before either path, you can self-check locally:

```
python scripts/submit_check.py submissions/<id>
```

This calls `scripts/challenge.py`'s `evaluate()` -- the same evaluator used in
CI -- and prints its `status`/`reason`, plus the SHA-256 of every file you
submitted. A `HOLD` status means something in the packet failed validation;
the `reason` field says what. Fix it and re-run before submitting.

## 2. Retrospective incident-history corrections

If you maintain, or have deeper access to, a provider's status-page history
than what's in `retrospective/incidents/<slug>.json` -- a longer confirmed
history, a corrected severity mapping, incidents the automated collector
missed -- you can submit a correction the same way: a pull request touching
`retrospective/incidents/<slug>.json` (and, if you fetched anything new,
`retrospective/incidents/raw/<slug>/` with the raw evidence and its SHA-256).

Requirements:

- Match `retrospective/incidents/SCHEMA.md` exactly.
- Only set `coverage_start`/`coverage_end` to dates you can justify (see
  SCHEMA.md's notes on this -- "the oldest incident I could see" is not the
  same claim as "I confirmed there's nothing older").
- Cite every raw file you're relying on, with its SHA-256, in `raw_files`.
- State your relationship to the provider, if any, in the PR description.

`retrospective/PLAN.md` and `retrospective/plan.json` are frozen and out of
scope for correction requests -- the repository records their commitment before collection (git time is self-reported, not an independent registration timestamp), and `scripts/retrospective.py` refuses to run if
`PLAN.md`'s hash no longer matches `plan.json`.

## What happens to a HOLD

`HOLD` is not a rejection of your GPU provider, your rating, or you -- it
means the submitted packet itself didn't pass structural or provenance
checks (a missing field, an untimestamped prediction, a training/test leak,
a receipt without a hash, a missing or placeholder disclosure, a binding that
doesn't reference the exact plan bytes, a binding bound before the plan froze
or after a job already started, a missing or incomplete rubric citation, a
source or rubric `retrieved_utc` after `bound_at`, a medal tier outside the
frozen anchors, a provider missing from or extra in the binding, or credits
redeemed on a job exceeding that job's own list charge). Every `HOLD` comes
with a `reason` string. Fix the packet and resubmit; there's no penalty for a
fixed resubmission.
