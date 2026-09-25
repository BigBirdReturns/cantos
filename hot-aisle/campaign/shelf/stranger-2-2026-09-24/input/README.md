# The shelf

Five claims about GPU compute, filed side by side in one structure, so that someone who was not
there can see what each one supports and what it does not. Nothing here ranks them. The structure
was derived from the five cards, not imposed on them.

## What is on it

| card | what it is | its spine |
|---|---|---|
| run3-at0 | our own measured run, narrowed | Run 3 A/T0 · 2026-09-24 experiment · $0.74/1k accepted own-seat equivalent; $0.90/1k actual shared-seat aggregate · measured + modeled · Hot Aisle credit-funded · inspected locally; no repeat |
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

1. every card carries the five answers, the four flags and the three checks, with dated periods and a funding field;
2. changing the H100 list price moves the modeled ranking and never the accepted counts; changing the evaluator moves "correct" and never the registered "accepted";
3. 4,336 accepted and $0.74 / $0.90 come back from the retained Run 3 bytes through the campaign's own grader rule;
4. six invalid combinations are refused, each naming its rule (an hourly index is not a per-accepted cost; a latency aggregate is not accepted work; a managed-cluster medal is not a seat property; a list price is not a measured cost; prices from different months do not combine without the period; a retrieval date never fills an experiment date);
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
