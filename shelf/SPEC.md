# The shelf: card format, filing version 2

A card is one JSON object describing one claim about compute. Cards are filed one per line
in a `cards.jsonl`. This document is normative for what `shelf.py validate` checks and what
the page displays. It was derived from five real cards filed on 2026-09-24, not imposed on
them; the earlier five-card edition is retained in the repository history.

## What a card is for

Someone who was not there should be able to see, from the card alone, what the claim
supports and what it does not, and then go and get the material. The card does not rank
the claim. It does not certify that the claim is true. It records who said what, under
which conditions, from what population, who paid, what a reader can obtain, and which
checks have actually been performed by a named party.

## Top level

| key | type | rule |
|---|---|---|
| `id` | string | lowercase slug, `[a-z0-9][a-z0-9._-]{0,63}`, unique on a shelf |
| `title` | string | one line |
| `spine` | string | the card in one line: who/what, when, the number and unit, which of the four flags apply, who paid, which checks were done. The disclosure that matters most belongs here, not only in a nested field |
| `dimensions` | object | exactly four keys, each `true`, `false` or `null`: `measured`, `imported`, `modeled`, `attributed`. These are separate flags, never one grade |
| `a_claim` | object | question (a) |
| `b_population` | object | question (b) |
| `c_parties` | object | question (c) |
| `d_materials` | object | question (d) |
| `e_checks` | object | question (e) |
| `filing_version` | integer | `2` |

Unknown is `null`, never a guess, never `false`, never an empty string. Integers are not
booleans; `1` is refused where `true` is meant.

## Values with a source

A measured or quoted value is an object, not a bare number:

```json
{"value": 2.99, "unit": "USD / GPU-hour", "source": "https://...", "source_date": "2026-09-24", "supports": "what this number can support, in words"}
```

`source_date` is the date of the cited source statement, or `null`. `supports` is optional
but strongly recommended on any number a reader might be tempted to compare.

## (a) `a_claim`: what is claimed, when, under what conditions

- `statement`: what exactly is claimed and what it does not establish.
- `period`: an object of dated fields. Every key ending in `_date`, plus `retrieved_at`
  and `artifact_created_at`, must hold a string or an explicit `null`. At least one such
  field is required. The recognised observation dates, in order of preference, are
  `experiment_date`, `index_date`, `artifact_created_at`, `publication_date`.
  `retrieved_at` is when someone obtained the source; it never supplies an observation
  date. `publication_date` is `null` unless the source establishes publication, and when
  it is set `publication_date_basis` must cite the dated source statement. A date the
  filer was told belongs in `reported_publication_date` with its own `_basis`; it does
  not fill the source's missing publication date.
- `conditions`: provider, hardware, `gpus` (object with an integer `value`), model,
  engine, purchase basis, commitment, and whatever else fixes what was observed.
- `results`: named values with units. Monetary hourly rates must be exactly
  `USD / GPU-hour` (one GPU) or `USD / seat-hour` (a whole configuration, which then
  requires a positive integer `conditions.gpus`). `USD/hour` is ambiguous and refused.
  Accepted-work prices use `USD / 1000 accepted requests`. Latency uses `milliseconds`.
  If the source leaves the billing basis unclear, keep its quote and leave `value` null.
- `limits`: a list of sentences stating what the result does not establish.
- `does_not_establish`: one sentence, for cards without a `limits` list.

## (b) `b_population`: what produced the number

`population`, the denominator (`scheduled`, `completed`, `accepted`, `total`, `reviewed`,
or `denominator`), `acceptance_rule`, `exclusions`, and the observation window. A rating
or index records what was rated or sampled and what was withheld.

## (c) `c_parties`: who observed, controlled, granted access and paid

- `observer`, `conditions_controller`, `access` (provider, mode, account class).
- `funding`: required, `null` allowed. Who paid, and their relationship to the claim.
- `observer_benefit`: required, with `benefits_from_outcome` (`true`, `false` or `null`),
  `relationship` and `basis`. A known judgment needs a basis. Funding and benefit are
  different facts. Say whose interest the field describes. A relationship does not
  establish misconduct; an unknown is `null`, not `false`.

## (d) `d_materials`: what a reader can obtain

`sources` (a list of objects with `path_or_url`, `publication_date`,
`publication_date_basis`, `experiment_date`, `retrieved_at`, `local_inspection_date`),
`primary_url`, `obtainable` (what the reader can actually get), `procedure` (how to
reproduce, or `null`), `missing` (what the filer could not obtain), and where possible a
`capture_sha256` of the retained source bytes.

## (e) `e_checks`: what has actually been checked, by whom

Three separate facts, each an object with `who` and `when` (strings or `null`) and an
optional `scope`:

- `inspected`: someone read the evidence.
- `recomputed`: someone recomputed the number from retained material.
- `repeated`: someone independently repeated the operation.

A machine filing check is none of these. A model reading a page is none of these unless
the card says so with the model named as `who`.

## Composition rules

Records combine only when identities, periods, scopes and assumptions agree. The engine
refuses these compositions and names the rule:

| purpose | refused when |
|---|---|
| `cost_per_accepted` | either side lacks a known numeric result in an explicit accepted-request unit |
| `accepted_work` | B has no accepted-request result (throughput or latency is not accepted work) |
| `seat_property` | B is not `measured: true` (a rating is not a property of a seat) |
| `measured_cost` | B is not `measured: true` (a list price is not a measured cost) |
| `same_period` | either observation date is unknown, or they differ |

Finding no refusal is not admission. Source checks remain separate and identify
the person or procedure that performed them.

Accepted-request units normalize to exactly `usd/1000acceptedrequests` or
`acceptedrequests`, with a finite nonnegative value. Substrings such as `unaccepted`
or `accepted bananas` do not establish that denominator. Both operands must pass the
filing check. Directional purposes retain their stated A/B roles; this is not a
general compatibility, configuration or admission engine.

## Which cards can support a question

`shelf.py which --unit U [--period P] [--measured]` reports, per card, either `SUPPORTS`
with the matching results, the card's limits, its recorded checks and a `how_far`
sentence, or `CANNOT_USE` with the rule. A card supports a question only if it has a
result in exactly that unit, is `measured: true` when a measurement is required, and has
a known observation date inside the period when one is asked. Nothing ranks.

Invalid filings and duplicate IDs receive `CANNOT_USE`; independent valid cards still
receive their own results. A null value does not supply a result. Date queries accept
valid ISO years, months, days or inclusive day ranges; a partial or invalid source
date cannot manufacture precision or fall through to a later publication date.

## Hubs, pulling and standing

A hub is any URL that serves a `cards.jsonl` or a single card. `shelf.py pull LOCATION
--hub NAME` writes `data/staging/<hub>/<time>/` with the exact bytes (`source.bytes`),
their SHA-256, the retrieval time, the parsed cards and each card's filing errors
(`provenance.json`, `standing: imported/candidate`). Pulling never writes to
`data/cards.jsonl`. Moving a staged card onto a shelf is a recorded local decision by
an authorized person or procedure,
appended to `data/promotions.jsonl` as `{"id", "from", "sha256", "who", "when", "why"}`.
`from` is the capture folder relative to staging (`hub/stamp`) and must exist; `sha256`
must equal that capture's provenance hash; the card must appear in that capture exactly
once and its content outside `e_checks` must equal the shelf's copy; `who` and `why` are nonempty;
`when` is an ISO date or UTC timestamp. `check_staging.py` refuses a staged card on the
shelf without such a record, and refuses forged or incomplete records. Shelf ids are unique. Promotion carries no
inspection, recomputation or repetition into local authority. Source assertions remain
in the capture; local checks are separately recorded in `e_checks`. A changed name or
date does not mechanically prove independence. Staged canonical cards, filing diagnostics
and counts must match the retained source bytes. Changed successor captures remain
available without overwriting their predecessors.

## Versioning

`filing_version` identifies the rules a card was filed under. A change to a rule is a new
filing version and a note here. Earlier cards are not edited to match; they are refiled
or left with their version.
