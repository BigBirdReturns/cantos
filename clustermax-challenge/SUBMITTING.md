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

## Minimum you need before you start

Read this before you invest time building a packet -- these are hard floors,
not suggestions, and the scorer `HOLD`s a packet that falls short of any of
them.

- **At least 8 held-out providers.** `plan.trials` must cover 8 or more
  distinct `provider_id` values, none of which appear in either predictor's
  `training_providers` list. Twelve job logs from two clouds, for example,
  cannot pass: two providers is four short of the floor regardless of how
  many jobs each ran.
- **Per provider: at least 10 trials, 5 distinct sessions, 3 distinct UTC
  dates.** Every one of the 8+ providers must independently clear all three;
  a provider that's short on any one of them holds the whole packet, naming
  that provider and the shortfall. In practice this means at least 80 total
  trial rows (8 providers x 10), not 8.
- **Uniform gates per workload.** `gates.accepted_min` / `p95_max_ms` /
  `cost_max_usd` and `p_baseline` must be set the same way for every trial
  that shares a `workload_sha256`, decided before you know which provider a
  row belongs to. A submission that quietly loosens the cost gate only on
  rows for one medal tier (or sets `p_baseline` differently by provider after
  the medals are known) is exactly the kind of post-hoc tuning the frozen
  `plan.json` + `binding.json` split exists to prevent, even though nothing
  in the current scorer mechanically forbids per-row values -- reviewers will
  reject or flag a packet that does this. Keep it simple: one `gates` object
  and one `p_baseline` policy per `workload_sha256`.
- **Registered transform only.** `plan.transform` must canonically hash to one of
  the entries listed in [`design/registry.json`](design/registry.json)'s
  `transforms` array — currently just the shipped
  [`design/transform.json`](design/transform.json). Copy that file's exact
  contents into your plan's `transform` field rather than hand-editing your own;
  an unregistered transform holds the packet even if it is otherwise
  well-formed (anchors strictly decreasing, weight and alternative weights in
  range, and so on).
- **Exact provider names for a registered rating's binding.** If
  `binding.rating_name`/`rating_version` names a rating that is itself
  registered in `design/registry.json` (currently `"ClusterMAX"` / `"3.0"`),
  every key in `binding.medals` must be spelled exactly as it appears in that
  entry's registered transcription -- see
  [`launch/release-3.0/clustermax-3.0.json`](launch/release-3.0/clustermax-3.0.json)
  (or `design/registry.json`'s own `ratings[].transcription.tiers`) for the
  exact strings, e.g. `"CoreWeave"`, not `"Coreweave"` or `"CoreWeave, Inc."`
  -- and the bound tier for that provider must equal the registered
  transcription's tier for it exactly. A rating that is not listed in the
  registry is still scored, just flagged `source_unverified`; the exact-name
  rule only binds a registered rating.
- **Exact hashing rules.** Every hash in this repo is a lowercase hex SHA-256
  of exact file bytes -- never of a canonicalized, pretty-printed, or
  re-serialized copy, except `transform_sha256` specifically (see "The
  medal-to-probability transform" in [README.md](README.md#the-medal-to-probability-transform),
  which is a canonical-JSON hash by design). `plan_sha256` in `binding.json`
  and `outcomes.json` is `sha256(the exact bytes of your plan.json file)`;
  `binding_sha256` in `outcomes.json` is `sha256(the exact bytes of your
  binding.json file)`. If you re-save either file (different indentation, a
  trailing newline appears or disappears, CRLF vs LF) after computing its
  hash, the hash goes stale and the packet holds with a hash-mismatch reason.
  Compute the hash last, from the file you are actually going to submit.
- **LF line endings.** Commit `plan.json`, `binding.json` and `outcomes.json`
  with Unix (`\n`) line endings, not Windows (`\r\n`) -- a CRLF roundtrip
  changes the file's bytes without changing what a human reads, which changes
  its SHA-256 and breaks every hash reference above. `submissions/**` is
  already marked `-text` in [`.gitattributes`](.gitattributes), which stops
  Git from doing this conversion for you (silently, in either direction); if
  you generate these files with `scripts/csv_to_packet.py` (below) they are
  already written LF-only. If you hand-author them on Windows, check with
  `git diff --stat` (no rewrite churn on an unrelated commit) or open the
  file in an editor that shows line-ending mode explicitly.

**Templates and a converter.** `submissions/templates/{plan,binding,outcomes}.template.json`
are annotated, minimal, one-trial examples of each file (field-by-field
explanations in the sibling
[`submissions/templates/FIELDS.md`](submissions/templates/FIELDS.md)).
If you already have job logs as a CSV, `scripts/csv_to_packet.py` converts a
jobs CSV plus a small plan-header JSON straight into a correctly hashed
`plan.json` + `outcomes.json` pair -- see "Converting a CSV" below.

### What `workload_sha256` and `validator_sha256` mean

Both are required on every trial row (in `plan.json`, and again -- unchanged
-- on the matching row in `outcomes.json`). They are not free-form labels;
they are exact hashes of files, the same way `plan_sha256`/`binding_sha256`
are.

- **`workload_sha256`** is the SHA-256 of the exact workload specification you
  ran -- the file (prompt set, dataset manifest, benchmark config, training
  script + args, whatever fully determines "what job we asked the provider to
  run") byte-for-byte, computed the same way you'd compute any other file
  hash: `sha256sum llama3-70b-inference-bench-v3.yaml` on Linux/macOS, or
  `Get-FileHash -Algorithm SHA256 llama3-70b-inference-bench-v3.yaml` on
  Windows. Two trials that ran literally the same workload file must carry
  the same `workload_sha256`; a changed config is a different workload and
  gets a different hash.
- **`validator_sha256`** is the SHA-256 of the exact acceptance-validator --
  the script or program that actually decided each row's `accepted` count out
  of `attempted` (a correctness checker, an eval harness, a golden-output
  diff, whatever your `outcome_definition` in `plan.json` describes). Same
  mechanics: `sha256sum accept_check.py`.

**Example.** If you ran the same inference benchmark config
(`bench.yaml`, sha256 `9f86d0...`) against every provider, checked each job's
outputs with the same validator script (`validate.py`, sha256 `e3b0c4...`),
every single trial row in both `plan.json` and `outcomes.json` carries
`"workload_sha256": "9f86d0..."` and `"validator_sha256": "e3b0c4..."` --
identical across all providers and all rows, because it was the same workload
and the same validator. If you ran two different benchmark configs against
different subsets of providers, rows from each subset carry that subset's own
workload hash; the scorer does not require every row to share one hash, only
that the recorded hash is the real hash of the file that actually governed
that row.

### Converting a CSV

If your job logs are already in a spreadsheet or a database export, write
them out as a CSV with these columns (`scripts/csv_to_packet.py --help` shows
the same list):

```
trial_id, provider_id, service_id, region, session_id, predicted_at,
p_baseline, started_at, finished_at, status, accepted, attempted, p95_ms,
total_cost_usd, credits_redeemed_usd, receipt_ref, receipt_sha256
```

Everything that's constant across the whole cohort (or constant per
workload) -- `study_id`, `rating_name`, disclosure text, the transform, the
baseline/with-rating predictor definitions, `workload_sha256`,
`validator_sha256`, the shared `gates`, and the binding (medals, sources,
`bound_at`) -- goes in a separate small header JSON, documented with a
worked example in
[`submissions/templates/FIELDS.md`](submissions/templates/FIELDS.md#csv_to_packetpy-header-json).
Then:

```sh
python scripts/csv_to_packet.py --csv jobs.csv --header plan-header.json \
  --plan-out plan.json --binding-out binding.json --outcomes-out outcomes.json
```

This writes all three files LF-only with correct, freshly computed
`plan_sha256` / `binding_sha256` cross-references -- run
`python scripts/submit_check.py <output dir>` afterward the same as for a
hand-authored packet; the converter does no validation of its own beyond
basic type coercion.

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
redeemed on a job exceeding that job's own list charge). Since v1.4 this also
includes: a `transform` that doesn't canonically hash to a registered entry in
`design/registry.json`, transform anchors that aren't strictly decreasing,
`gates` that differ between trials sharing a `workload_sha256`, an empty
`training_providers` list on either predictor, or -- for a binding against a
rating version that is itself registered -- a `binding.source.sha256` that
isn't one of that rating's registered medal-table digests, a bound provider
name that isn't spelled exactly as in the registered transcription, or a
bound tier that differs from the registered transcription's tier for that
provider. Every `HOLD` comes with a `reason` string. Fix the packet and
resubmit; there's no penalty for a fixed resubmission.
