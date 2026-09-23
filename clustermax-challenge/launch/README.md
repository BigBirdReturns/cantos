# ClusterMAX 3.0 launch kit

This challenge is frozen before ClusterMAX 3.0 exists: the plan, the
medal-to-probability transform and the binding rules are all locked ahead of time
(see the root [README.md](../README.md), "The three records"). Nobody involved in
this repo knows what SemiAnalysis will put in 3.0's rubric or medal table, and this
kit makes no claim about what the release will or will not contain, when it will
ship, or what it will omit.

What this kit *does* do, mechanically, once 3.0 actually ships:

1. **Record a ledger, per medal, of what the release actually supplies.**
   [`claims-3.0.template.json`](claims-3.0.template.json) (schema
   `secondrun.launch-claims.v1`) has five fields per provider medal:

   - `scope` — the service/product and region the medal covers
   - `observation_conditions` — the customer permissions and support tier that
     produced the observations (ordinary vs. reviewer/white-glove)
   - `evidence` — evidence published for the medal and how it yields the tier
     (rubric link + per-criterion scores, if published)
   - `test_dates` — when the observations were made
   - `predictive_check` — whether the release provides anything allowing a
     predictive check

   Each field carries a `status`: `SUPPLIED` (with a cited `source` — `url` +
   `sha256` — and a `value`), `OMITTED` (with the exact `omitted_claim` that
   consequently remains unevaluable), or `NOT_YET_RELEASED`.

2. **Bind supplied medals to the frozen test, mechanically.**
   `../scripts/launch_ledger.py` validates a filled ledger, prints a
   supplied/omitted/not-yet-released summary per field and the list of
   unevaluable claims, and — only when the ledger supplies a medal for every
   plan provider plus a medal-table source and a rubric source — emits a
   `binding.json` draft (schema `secondrun.rating-binding.v2`) for a given
   frozen `--plan`, so the prospective test in this repo can be bound without
   hand-editing.

## Filling in the ledger

Copy `claims-3.0.template.json`, replace `EXAMPLE_PROVIDER` with the real
provider ids from your frozen plan's cohort (one entry per provider), and set
each of the five fields' `status` based on what the release actually
publishes for that provider:

- If the release gives you enough to check the field, set `status: "SUPPLIED"`,
  fill in `value`, and cite the exact page/document you read it from in
  `source.url` / `source.sha256` (a lowercase SHA-256 of the bytes you
  retrieved) / `source.retrieved_utc`.
- If the release does not give you enough, set `status: "OMITTED"` and write
  the exact claim that consequently remains unevaluable in `omitted_claim` —
  be specific about what's missing, not just "insufficient data".
- Leave `status: "NOT_YET_RELEASED"` for anything the release genuinely
  hasn't published yet.

Also fill in `medal_table_source` and `rubric_source` at the top level (the
same `url` / `sha256` / `retrieved_utc` shape) once you have both — these feed
`binding.source` / `binding.rubric` directly.

```sh
python ../scripts/launch_ledger.py path/to/filled-ledger.json
python ../scripts/launch_ledger.py path/to/filled-ledger.json --plan ../data/demo-plan.json --output binding-draft.json
```

The first form just validates the ledger and prints the summary table and the
unevaluable-claims list. The second additionally emits a binding draft once the
ledger covers every provider in the given plan. The emitted `bound_at` is
stamped at the moment you run the command — confirm that's actually when you
read the medal table and rubric, and that it still lands strictly before every
trial's `started_at`, before treating the draft as a real binding (see the root
README's "Bound, not backfilled" gate).

## What this is not

This kit does not predict, describe, or speculate about ClusterMAX 3.0's rubric,
medal table, release date, or what it will or will not include. It is a fixed
procedure, written and frozen before 3.0 ships, for turning whatever 3.0 actually
publishes into a ledger and, where the ledger supports it, a binding — nothing
here is written from foreknowledge of the release.
