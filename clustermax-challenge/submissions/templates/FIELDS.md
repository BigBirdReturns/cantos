# Template field reference

`plan.template.json`, `binding.template.json` and `outcomes.template.json` in
this directory are minimal, internally-consistent, one-trial examples of the
three files `scripts/challenge.py`'s `evaluate()` scores (see
[`../../README.md#the-three-records`](../../README.md#the-three-records) for
why there are three separate files instead of one). They are **templates, not
submittable packets** -- every field a real submitter must supply is marked
`TEMPLATE -- replace:` with an example of the kind of value expected. A real
submission also needs at least 8 held-out providers, each with at least 10
trials / 5 sessions / 3 UTC dates -- see "Minimum you need before you start"
in [`../../SUBMITTING.md`](../../SUBMITTING.md); these templates show one
trial for one provider purely to keep the file readable.

Each template carries a `_template_note` root field that is not part of the
real schema -- `evaluate()` ignores unrecognized fields, but delete it before
submitting anyway.

The `plan_sha256` inside `binding.template.json`, and the `plan_sha256`/
`binding_sha256` inside `outcomes.template.json`, are the *real*, freshly
computed SHA-256 hashes of the other two template files' exact bytes (see
"Exact hashing rules" in SUBMITTING.md) -- that's why the three templates
validate as a hash-consistent triple against each other, even though the rest
of their content is placeholder. Once you edit `plan.template.json`, its
bytes change and its hash changes with them; you must recompute
`plan_sha256` in your binding and outcomes files (or just run
`scripts/csv_to_packet.py`, which always computes fresh hashes for you).

## `plan.template.json` (schema `secondrun.rating-plan.v4`)

| Field | Meaning |
|---|---|
| `schema` | Always the literal string `secondrun.rating-plan.v4`. |
| `synthetic` | `true`/`false`. `false` for a real submission -- `true` is reserved for the repo's own demo/test fixtures. |
| `study_id` | A short slug you choose, identifying this study. Free text, must be nonempty. |
| `rating_name` | The rating this plan is about, e.g. `"ClusterMAX"`. Must match `binding.json`'s `rating_name` exactly. |
| `rating_version` | The version you *expect* the binding to name, e.g. `"3.0"`. Must match `binding.json`'s `rating_version` exactly (this is how the scorer catches a binding to the wrong rating vintage). |
| `frozen_at` | RFC3339 UTC timestamp: when you locked this design, before any trial's `predicted_at`/`started_at`. Everything below this point in the plan must exist by this moment. |
| `minimum_providers` | Integer, must be `>= 8`. The hard floor on distinct held-out providers. |
| `minimum_lift` | Number in `[0, 1]`: the smallest medal-permutation-test ranking gain `T` (see "The medal permutation test" in [`../../README.md`](../../README.md#the-medal-permutation-test)) you'd call a real (not just nonzero) `positive`/`negative` signal, decided before you see outcomes. |
| `outcome_definition` | Free text: the plain-English endpoint your per-trial `gates` encode (e.g. "complete with >=950/1000 accepted, p95<=500ms, cost<=$25"). |
| `disclosure` | Object with five **required, nonempty, non-placeholder** string fields -- see below. `evaluate()` holds the packet if any is empty or still says `CONFIRM`/`TBD`/`TODO`/`???`/"describe"/etc. |
| `disclosure.relationship` | Your relationship, if any, to any provider or rating named in this plan (employee, investor, customer, none, ...). |
| `disclosure.compensation` | Any compensation you received connected to this plan or its providers/rating. |
| `disclosure.credits` | Any GPU-cloud credits received (name provider + amount, or state none). |
| `disclosure.special_support` | Any non-ordinary account access or support you received (or state none -- `customer_role`/`support` on every trial must independently say `ordinary_tenant`/`standard` regardless of what you write here). |
| `disclosure.editorial_influence` | Whether any named party reviewed, approved or influenced this plan before you froze it. |
| `binding_rules` | Object committing, in advance, to which official sources the *later* binding must cite and which tier set it must use. |
| `binding_rules.medal_source` | Free text naming the official source you expect the binding's `source` to point at (e.g. "the official ClusterMAX medal table page"). |
| `binding_rules.rubric_source` | Same, for the rubric the binding's `rubric` will point at. |
| `binding_rules.tiers` | List of tier names -- must be exactly the five keys of `transform.anchors` (order doesn't matter, set equality does). |
| `transform` | The complete medal-to-probability transform object, inline -- copy the exact contents of [`../../design/transform.json`](../../design/transform.json); its canonical hash must match an entry in [`../../design/registry.json`](../../design/registry.json)'s `transforms` array or the packet holds. Schema `secondrun.rating-transform.v1`, with `anchors` (one probability per medal tier, strictly decreasing Platinum > Gold > Silver > Bronze > Underperforming), `weight`, `reference_anchor`, `alternative_weights`, `description`. |
| `transform_sha256` | SHA-256 of the **canonical JSON** encoding of the `transform` object above -- `json.dumps(transform, sort_keys=True, separators=(',',':'), ensure_ascii=False)`, then SHA-256 of the UTF-8 bytes. This is the *one* hash in this repo that is not a plain file-bytes hash -- see "The medal-to-probability transform" in README.md. `scripts/csv_to_packet.py` and `make_demo.py` both compute it the same way; do it by hand only if you're not using the converter. |
| `baseline` / `with_rating` | The two predictor definitions for the ablation -- same shape, `with_rating.inputs` must be `baseline.inputs` plus exactly one extra input named `"rating"`, and both must share the same `training_providers` set. |
| `*.description` | Free text describing the predictor. |
| `*.model_sha256` | SHA-256 of the exact file/artifact that defines this predictor (a model file, a spec document, a scoring formula -- whatever you'd need someone else to inspect to check your predictor). |
| `*.inputs` | List of distinct input-feature names. |
| `*.training_providers` | Nonempty list of provider ids used to fit/tune this predictor -- an empty list holds the packet (the held-out claim is vacuous without training providers), and every id must also be disjoint from every trial's `provider_id` below (a held-out provider leaking into training holds the packet). |
| `*.frozen_at` | RFC3339 timestamp, must be `<= plan.frozen_at`. |
| `trials` | List of per-job plan rows (the "design" side; `outcomes.json` supplies the matching terminal-outcome side per `trial_id`). |
| `trials[].trial_id` | Your own unique id for this planned job; must also appear, unchanged, in the matching `outcomes.json` row. |
| `trials[].provider_id` | Which held-out provider this trial tests. If your binding names a registered rating version (currently ClusterMAX 3.0), this must exactly match that provider's key in the registered transcription -- see [`../../launch/release-3.0/clustermax-3.0.json`](../../launch/release-3.0/clustermax-3.0.json) (or `design/registry.json`'s `ratings[].transcription.tiers`) for the exact spelling. |
| `trials[].service_id` | Which specific service/product/SKU on that provider (a managed-cluster claim needs a managed-cluster `service_id`, not a bare-metal or token-endpoint one). |
| `trials[].region` | Region/location of the job. |
| `trials[].workload_sha256` | SHA-256 of the exact workload spec file this job ran -- see "What `workload_sha256` and `validator_sha256` mean" in SUBMITTING.md. |
| `trials[].validator_sha256` | SHA-256 of the exact acceptance-validator file/script used to decide `accepted`/`attempted` for this job. |
| `trials[].customer_role` | Must be the literal string `"ordinary_tenant"` -- anything else holds the packet. |
| `trials[].support` | Must be the literal string `"standard"` -- anything else holds the packet. |
| `trials[].session_id` | Which test session this trial belongs to (used for the >=5-distinct-sessions-per-provider floor). |
| `trials[].predicted_at` | RFC3339 timestamp of this specific prediction; must be `<= plan.frozen_at` and strictly before this trial's `started_at` in `outcomes.json`. |
| `trials[].p_baseline` | Number in `[0, 1]`: the baseline model's predicted probability of success for this job, computed before the job ran. |
| `trials[].gates` | Object: `accepted_min` (positive integer), `p95_max_ms` (number), `cost_max_usd` (number) -- the pass/fail thresholds for this specific job. These must be byte-for-byte identical across every trial sharing a `workload_sha256` -- the scorer holds the packet otherwise -- decided before you know the provider's medal; see "Minimum you need before you start" in SUBMITTING.md. |

## `binding.template.json` (schema `secondrun.rating-binding.v2`)

| Field | Meaning |
|---|---|
| `schema` | Always `secondrun.rating-binding.v2`. |
| `plan_sha256` | SHA-256 of the **exact bytes** of the `plan.json` file this binding is for. Not canonicalized -- literally `sha256(open('plan.json','rb').read())`. |
| `rating_name` / `rating_version` | Must equal the plan's `rating_name`/`rating_version` exactly. |
| `source` | Where you got the medal table. `source.url`, `source.sha256` (of the exact page/image bytes you retrieved), `source.retrieved_utc` (RFC3339, must be `<= bound_at`). |
| `rubric` | Same shape, for the rubric/methodology document the medals were graded against. |
| `bound_at` | RFC3339 timestamp: when you actually filled in this binding. Must be `>= plan.frozen_at` and strictly before **every** trial's `started_at` in `outcomes.json` -- you cannot bind a medal after a job already ran. |
| `medals` | Object mapping every `provider_id` that appears in `plan.trials` (no more, no fewer) to one of the five frozen tier names (`Platinum`/`Gold`/`Silver`/`Bronze`/`Underperforming`). An unrated/Unavailable provider cannot be silently mapped to a tier -- drop it from the plan's provider set instead. If `rating_name`/`rating_version` names a rating registered in `design/registry.json` (currently ClusterMAX 3.0), every key here must be spelled exactly as in that rating's registered transcription and its value must equal that provider's registered tier, or the packet holds. |

## `outcomes.template.json` (schema `secondrun.rating-outcomes.v4`)

| Field | Meaning |
|---|---|
| `schema` | Always `secondrun.rating-outcomes.v4`. |
| `plan_sha256` | Same value as `binding.json`'s `plan_sha256` (both must point at the same plan bytes). |
| `binding_sha256` | SHA-256 of the **exact bytes** of the `binding.json` file. |
| `trials` | List of terminal outcome rows, one per `plan.trials[].trial_id`, no more, no fewer. |
| `trials[].trial_id` ... `session_id` | Must exactly match the corresponding fields on the `plan.json` row with the same `trial_id` (the scorer checks every `CONTEXT` field for an exact match -- a changed value here is treated as a plan/outcome mismatch, not an update). |
| `trials[].started_at` | RFC3339 timestamp the job actually started; must be strictly after this trial's `predicted_at` and after `plan.frozen_at`. |
| `trials[].finished_at` | RFC3339 timestamp the job ended; must be `>= started_at`. |
| `trials[].status` | One of `complete`, `timeout`, `error`, `provision_failed`, `aborted`. Every attempted trial gets a terminal status -- don't drop failed ones. |
| `trials[].accepted` / `trials[].attempted` | Integers, `0 <= accepted <= attempted`. |
| `trials[].p95_ms` | Number, or JSON `null` if genuinely unavailable (e.g. the job never completed) -- but a `status: "complete"` row must have a real number here. |
| `trials[].total_cost_usd` | The normal list-price charge for this job, **before** any credits. Always what gates and `cost_per_1000_accepted` are computed from. |
| `trials[].credits_redeemed_usd` | Optional, defaults to `0`. Any GPU-cloud credits redeemed toward this specific job; cannot exceed `total_cost_usd`. |
| `trials[].receipt_ref` | Free text pointing at your actual receipt/invoice (an id, filename, or URL) -- don't publish the receipt itself if it has billing details you want private. |
| `trials[].receipt_sha256` | SHA-256 of that receipt/invoice file. |

## CSV_to_packet.py header JSON

`scripts/csv_to_packet.py` takes a jobs CSV (one row per trial: `trial_id,
provider_id, service_id, region, session_id, predicted_at, p_baseline,
started_at, finished_at, status, accepted, attempted, p95_ms,
total_cost_usd, credits_redeemed_usd, receipt_ref, receipt_sha256`) plus a
second, small JSON file -- the "header" -- carrying everything that's
constant across the cohort rather than per-row. The header's top-level
fields map straight onto the `plan.template.json` fields documented above,
plus a `binding` object and the two shared per-job hashes/gates that the CSV
itself does not carry a column for:

| Header field | Goes into | Meaning |
|---|---|---|
| `study_id`, `rating_name`, `rating_version`, `frozen_at`, `minimum_providers`, `minimum_lift`, `outcome_definition`, `disclosure`, `binding_rules`, `transform`, `baseline`, `with_rating` | `plan.json` (same field name, copied straight through) | See the `plan.template.json` table above -- identical meaning. |
| `synthetic` | `plan.json` | Optional, defaults to `false`. |
| `workload_sha256` | every `plan.json`/`outcomes.json` trial row | The one workload hash applied to every CSV row. If you ran more than one distinct workload, split your CSV (and run the converter once per workload) rather than trying to vary this per row -- the converter does not support a per-row override. |
| `validator_sha256` | every `plan.json`/`outcomes.json` trial row | Same, for the acceptance validator. |
| `customer_role` | every `plan.json`/`outcomes.json` trial row | Optional, defaults to `"ordinary_tenant"`. |
| `support` | every `plan.json`/`outcomes.json` trial row | Optional, defaults to `"standard"`. |
| `gates` | every `plan.json` trial row | The shared `{accepted_min, p95_max_ms, cost_max_usd}` object applied to every row -- see "Uniform gates per workload" in SUBMITTING.md. |
| `binding.source`, `binding.rubric`, `binding.bound_at`, `binding.medals` | `binding.json` | Copied straight into the generated `binding.json` -- see the `binding.template.json` table above. |

Worked example header JSON (paired with a CSV that has one row per trial for
providers `ACME_CLOUD` and `ZETA_GPU`, and so on for at least 6 more to clear
the 8-provider floor):

```json
{
  "study_id": "acme-cloud-inference-2026-11",
  "rating_name": "ClusterMAX",
  "rating_version": "3.0",
  "frozen_at": "2026-11-01T00:00:00Z",
  "minimum_providers": 8,
  "minimum_lift": 0.01,
  "outcome_definition": "Complete with >=950/1000 accepted, p95<=500ms, cost<=$25.",
  "disclosure": {
    "relationship": "No relationship with any provider or rating named in this plan.",
    "compensation": "None received.",
    "credits": "None redeemed toward these jobs.",
    "special_support": "None; ordinary self-signup account and standard support only.",
    "editorial_influence": "None."
  },
  "binding_rules": {
    "medal_source": "Official ClusterMAX medal table page, as published by SemiAnalysis.",
    "rubric_source": "Official ClusterMAX rubric/methodology document for the bound rating_version.",
    "tiers": ["Platinum", "Gold", "Silver", "Bronze", "Underperforming"]
  },
  "transform": { "...": "paste the exact contents of design/transform.json here" },
  "baseline": {
    "description": "Specs-and-price baseline: GPU type, allocation size, list price/hour.",
    "model_sha256": "<sha256 of your baseline model/spec file>",
    "inputs": ["gpu_type", "allocation_size", "list_price_per_hour", "workload_class", "region"],
    "training_providers": ["TRAIN_PROVIDER_A", "TRAIN_PROVIDER_B"],
    "frozen_at": "2026-10-25T00:00:00Z"
  },
  "with_rating": {
    "description": "Same baseline plus the ClusterMAX medal.",
    "model_sha256": "<sha256 of your with-rating model/spec file>",
    "inputs": ["gpu_type", "allocation_size", "list_price_per_hour", "workload_class", "region", "rating"],
    "training_providers": ["TRAIN_PROVIDER_A", "TRAIN_PROVIDER_B"],
    "frozen_at": "2026-10-25T00:00:00Z"
  },
  "workload_sha256": "<sha256 of bench.yaml, the exact workload spec you ran>",
  "validator_sha256": "<sha256 of validate.py, the exact acceptance validator you used>",
  "customer_role": "ordinary_tenant",
  "support": "standard",
  "gates": {"accepted_min": 950, "p95_max_ms": 500, "cost_max_usd": 25.0},
  "binding": {
    "source": {"url": "https://...medal-table...", "sha256": "<sha256 of that page/image>", "retrieved_utc": "2026-11-02T00:00:00Z"},
    "rubric": {"url": "https://...rubric...", "sha256": "<sha256 of that document>", "retrieved_utc": "2026-11-02T00:00:00Z"},
    "bound_at": "2026-11-02T01:00:00Z",
    "medals": {"ACME_CLOUD": "Gold", "ZETA_GPU": "Silver"}
  }
}
```

Run it, then self-check with `submit_check.py` the same as a hand-authored
packet:

```sh
python scripts/csv_to_packet.py --csv jobs.csv --header plan-header.json \
  --plan-out submissions/acme-cloud-2026-11/plan.json \
  --binding-out submissions/acme-cloud-2026-11/binding.json \
  --outcomes-out submissions/acme-cloud-2026-11/outcomes.json
python scripts/submit_check.py submissions/acme-cloud-2026-11
```
