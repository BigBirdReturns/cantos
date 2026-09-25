# The shelf

Five claims about GPU compute, filed side by side in one structure, so that someone who was not
there can see what each one supports and what it does not. Nothing here ranks them. The structure
was derived from the five cards, not imposed on them.

## What is on it

| card | what it is | its spine |
|---|---|---|
| run3-at0 | our own measured run, narrowed | Run 3 A/T0 · 2026-09-24 experiment · $0.74/1k accepted own-seat equivalent; $0.90/1k actual shared-seat aggregate · measured + modeled · Hot Aisle credit-funded · inspected and recomputed locally; no repeat |
| inferencex-artifact | a good outside benchmark result | InferenceX B300 / DeepSeek-V4.1-Flash · experiment unknown; artifact 2026-09-22 · mean TTFT 7,152.69 ms · measured + imported + attributed · funding/access unknown · aggregate, no request-level acceptance |
| clustermax-coreweave | a provider rating with a partly withheld derivation | CoreWeave Platinum · ClusterMAX 3.0 published 2026-09-23 · managed-cluster rating · attributed · audit public; performance/reliability withheld |
| mercatus-index | a price index with a published method and withheld weights | Mercatus · index 2026-09-21 · MI300X $4.98; H100 $3.89 per GPU-hour · imported + modeled + attributed · volume-weighted on-demand; weights withheld |
| hotaisle-blog | a provider's statement about itself | Hot Aisle self-statement · publication unknown; July 14 attributed to the user · MI300X $1.99 to $2.99; full-capacity and queue claims · attributed · not September capacity evidence |

`cards.jsonl` holds the full cards. Each answers five questions: what is claimed and when; what
population, denominator and acceptance rule produced the number; who observed, controlled, granted
access and paid; what a reader can obtain; and whether anyone inspected, recomputed or repeated it,
as three separate facts. Measured, imported, modeled and attributed are four separate flags, not one
grade. Unknown is null, never a guess.

## Filing a card (version 2)

Copy the five sections from a relevant card, then cite the material that supports each populated
value. Keep these distinctions explicit:

- **Dates:** `a_claim.period.publication_date` is null unless the source establishes publication.
  Include `publication_date_basis` (a source and its dated statement, or null). `retrieved_at`
  records when someone obtained the source. Experiment, artifact creation, index period and
  publication are separate dates; they may coincide when separately supported. A user-attributed
  date can remain in `reported_publication_date` with its basis; it does not fill the source's
  missing publication date. Apply the same distinction to `d_materials.sources`.
- **Price units:** write `USD / GPU-hour` for one GPU's hourly price or `USD / seat-hour` for
  a whole configuration, with its GPU count in `a_claim.conditions.gpus`. `USD/hour` is ambiguous.
  Accepted-work prices use `USD / 1000 accepted requests`. If the source leaves the billing basis
  unclear, retain its quote and leave the normalized value null. A starting price is a lower-bound
  offer; it does not establish an obtainable seat, a minimum bill, or a measured running cost.
- **Observer benefit:** include `c_parties.observer_benefit` with `benefits_from_outcome`
  (true, false or null), `relationship` and `basis` (text or null). A non-null judgment needs a
  basis. Funding and potential benefit are different facts. Identify whose interest the field
  describes; unknown interests are null, not false. A relationship does not establish misconduct.

`python validator.py --card path/to/card.json` checks one filing. This checks structure and
required disclosures; a reviewer must still check whether the cited sources warrant the values.
Filing and machine validation do not grant standing or establish independent repetition.

## The checks

`python validator.py` runs five machine checks with no dependencies:

1. every card carries the five answers, separate dimensions and checks, publication-date basis, observer-benefit fields and explicit hourly units;
2. changing the H100 list price moves the modeled ranking while retaining accepted counts; the separate HumanEval sanitizer regrade changes correct outputs from 640 to 2,161 of 2,624, without creating a post-hoc accepted count;
3. 8,622 scheduled, 8,622 completed and 4,336 accepted are recovered from the replay journal and rejoined retained EvalPlus results through the campaign's native grader. Missing or corrupt replay fails; there is no summary fallback. The $0.74 / $0.90 calculations use the card's declared prices, duration and shared totals, not new invoice reconciliation or a regrade of every shared arm;
4. six bounded invalid combinations are refused, each naming its rule: index versus accepted-work units, latency as accepted work, managed-cluster medal as seat evidence, provider list price as measured cost, an unknown comparison period, and retrieval copied into publication without dated-source support;
5. the run card carries both cost scopes with what each supports, and the credit on its spine.

The sixth check is a blind model handoff, separate from independent human use. On 2026-09-24 a
Haiku agent with none of our context and only `cards.jsonl`
filed Latitude.sh's $1.68 H100 as a sixth card and answered "which cards support 'MI300X is cheaper
per accepted request than H100 on a self-serve seat in September 2026', and how far". It cited the
run card with its limits and refused the other five with the right reason each. It also set a
publication date equal to the day it read the page, wrote the unit as "USD/hour", and asked for a
field recording whether the observer benefits from the outcome. Its filing and answer are in
`stranger-2026-09-24/`, unedited. Version 2 adds the three filing rules above. The earlier five-card
edition remains in commit `3595615`; the Hot Aisle exact publication date and Mercatus publication
date are now unknown where source support was absent. A second model handoff tests the revised
instructions; one success would not establish human usability or isolate the cause of improvement.

The [second handoff](stranger-2-2026-09-24/ASSESSMENT.md) used `gpt-6-luna` with a fresh context and
a captured [Voltage Park source](https://www.voltagepark.com/pricing). Its seventh card passes the
single-card filing check, avoids both earlier filing errors, distinguishes the two Run 3 cost
scopes, and explicitly refuses to treat Mercatus as a rental offer. It leaves the provider's
observer-benefit relationship unknown and its inspection actor/time incomplete. Its response is
retained unchanged; a structural pass does not make those omissions disappear.

Twelve focused regressions run with `python -m unittest test_validator -v`. The preserved first
stranger's card intentionally fails the revised filing check for the three documented reasons.

## One card through the existing estate tools

The [Run 3 join](join/README.md) retains the current card with `binding.json`, `standing.json`
and `applicability.json` in `join/run3-v3/`. Native Genesis verifies its signed bytes using an
explicit local test key. Native Canon validates the three propositions as machine-extracted
evidence and refuses a reviewed label without a reviewer. That establishes evidence-bundle
compatibility, not human reconciliation or accepted standing.

The record remains filed/candidate. Its historical applicability check passes only while the
recorded conditions and dependency bytes match. A changed evaluator requires revalidation;
the earlier bound record remains intact. The join README supplies the commands and limits.
The Run 3 card now records the bounded local recomputation; independent repetition remains null.

## Glossary for a stranger

- **accepted**: the answer passed the EvalPlus tests, the first token arrived within 1 s, and the
  answer finished within 60 s of the moment the request was scheduled to arrive.
- **trace / replay factor**: a trace is a retained sequence of request-arrival timestamps. The
  runner divides offsets by the rate factor: 0.95 spreads arrivals slightly farther apart, making
  them slower than recorded. The selected Azure code-inference trace supplies the burst pattern.
- **own-seat equivalent vs shared seat**: $0.74 prices this arm as if it had its own VM; $0.90 is
  what the actual VM cost across everything run on it. Both are list price, not an invoice.

## Disclosure

Hot Aisle's credit paid for the AMD arm on the run card and Hot Aisle is a sales prospect. The H100
arm was paid in cash. One run per arm, no repeats.

## The public tool

The format, the filing check, the composition refusals and a mechanical "which cards can
support this question" check now live as a self-contained tool at [`/shelf/`](../../../shelf/),
with a browser engine held to the CLI by one shared fixture and a `pull` command that imports
other hubs' cards as candidates. This directory remains the retained evidence record for the
first five cards and the two model handoffs; `shelf/data/cards.jsonl` is checked byte-for-byte
against `cards.jsonl` here in CI. The Run 3 recomputation, propagation and narrowing checks
stay here with the campaign bytes they need.
