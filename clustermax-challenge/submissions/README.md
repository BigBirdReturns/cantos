# submissions/

Each subdirectory here is one prospective plan+outcomes packet, submitted per
[`SUBMITTING.md`](../SUBMITTING.md). Directory name is the submission id
(short, url-safe, e.g. a provider slug plus a date: `acme-cloud-2026-11`).

```
submissions/<id>/plan.json       -- frozen design, schema secondrun.rating-plan.v4
submissions/<id>/binding.json    -- medal binding filled in after the rating
                                     published, schema secondrun.rating-binding.v2
submissions/<id>/outcomes.json   -- terminal job outcomes, schema secondrun.rating-outcomes.v4
submissions/<id>/SUBMITTER.md    -- who submitted this and why it should be trusted
```

There are three records, not two, because the plan must be freezable *before*
a rating tier even exists for the providers in your cohort -- `plan.json`
carries no `medal` field at all. `binding.json` is a separate record, filled
in only once the rating publishes: it references the exact `plan.json` bytes
by hash, names the rating and its version, cites where the medal table came
from, and stamps when it was bound. `outcomes.json` then references both by
hash. See the root [`README.md`](../README.md#the-three-records) for why this
split exists.

## `plan.json` / `binding.json` / `outcomes.json`

These follow the schemas `scripts/challenge.py` validates
(`secondrun.rating-plan.v4` / `secondrun.rating-binding.v2` /
`secondrun.rating-outcomes.v4`). Run
`python scripts/submit_check.py submissions/<id>` locally before opening a PR
-- it calls the same `evaluate()` CI uses and will tell you exactly what's
wrong if anything is. Note `plan.json` also carries its own structured
`disclosure` object (relationship, compensation, credits, special support,
editorial influence) that `evaluate()` checks directly -- this is separate
from `SUBMITTER.md`'s free-form disclosure section below.

`plan.json` carries no rubric hash -- a design frozen before a rating's next
version exists cannot know that version's rubric. It instead commits, via
`binding_rules`, to which official sources the later `binding.json` must
cite (`medal_source`, `rubric_source`) and the frozen tier set (`tiers`).
`binding.json` then carries both the medal-table citation (`source`) and the
rubric citation (`rubric`), each an `{url, sha256, retrieved_utc}` block read
at or before `bound_at`.

`outcomes.json` rows may optionally declare `credits_redeemed_usd` (defaults
to 0) for any GPU-cloud credits redeemed toward that job; it cannot exceed
the row's own `total_cost_usd` (the normal list-price charge, always used for
gates and cost-per-accepted-unit). `evaluate()`'s output reports the list
charge and any credits redeemed separately and never nets them against each
other.

## `SUBMITTER.md`

Free-form markdown, but it must contain a disclosure section -- a heading
containing the word "Disclosure" (e.g. `## Disclosure`) -- covering:

- Your relationship, if any, to any provider or rating named in `plan.json`
  (employee, investor, customer, no relationship, etc.).
- How the account used for these jobs was obtained (self-signup, ordinary
  paid plan -- not a reviewer/partner account; `plan.json`'s trials already
  assert `customer_role: "ordinary_tenant"` and CI's `evaluate()` call will
  hold the submission if that's false, but say so here too).
- Anything else a reader would want to know before trusting these numbers.

`scripts/submit_check.py` checks that the section exists; it does not (and
cannot) check that the disclosure is honest or complete. Reviewers read it.

## CI

`.github/workflows/clustermax-challenge-ci.yml` runs
`python scripts/submit_check.py submissions/<id>` for every directory here on
every push/PR touching `clustermax-challenge/**`. A `HOLD` or a missing
disclosure fails the check.
