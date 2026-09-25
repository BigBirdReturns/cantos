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
| hotaisle-blog | a provider's statement about itself | Hot Aisle self-statement · blog 2026-07-14 · MI300X $1.99 to $2.99; full-capacity and queue claims · attributed · not September capacity evidence |

`cards.jsonl` holds the full cards. Each answers five questions: what is claimed and when; what
population, denominator and acceptance rule produced the number; who observed, controlled, granted
access and paid; what a reader can obtain; and whether anyone inspected, recomputed or repeated it,
as three separate facts. Measured, imported, modeled and attributed are four separate flags, not one
grade. Unknown is null, never a guess.

## The checks

`python validator.py` runs five machine checks with no dependencies:

1. every card carries the five answers, the four flags and the three checks, with dated periods and a funding field;
2. changing the H100 list price moves the modeled ranking and never the accepted counts; changing the evaluator moves "correct" and never the registered "accepted";
3. 4,336 accepted and $0.74 / $0.90 come back from the retained Run 3 bytes through the campaign's own grader rule;
4. six invalid combinations are refused, each naming its rule (an hourly index is not a per-accepted cost; a latency aggregate is not accepted work; a managed-cluster medal is not a seat property; a list price is not a measured cost; prices from different months do not combine without the period; a retrieval date never fills an experiment date);
5. the run card carries both cost scopes with what each supports, and the credit on its spine.

The sixth check is a person. On 2026-09-24 an agent with none of our context and only `cards.jsonl`
filed Latitude.sh's $1.68 H100 as a sixth card and answered "which cards support 'MI300X is cheaper
per accepted request than H100 on a self-serve seat in September 2026', and how far". It cited the
run card with its limits and refused the other five with the right reason each. It also set a
publication date equal to the day it read the page, wrote the unit as "USD/hour", and asked for a
field recording whether the observer benefits from the outcome. Its filing and answer are in
`stranger-2026-09-24/`, unedited. Those errors are the next schema changes.

## Glossary for a stranger

- **accepted**: the answer passed the EvalPlus tests, the first token arrived within 1 s, and the
  answer finished within 60 s of the moment the request was scheduled to arrive.
- **trace / replay factor**: requests arrive on the timestamps of a public Azure code-inference
  trace, compressed by the factor (0.95 means slightly faster than recorded), so bursts are real.
- **own-seat equivalent vs shared seat**: $0.74 prices this arm as if it had its own VM; $0.90 is
  what the actual VM cost across everything run on it. Both are list price, not an invoice.

## Disclosure

Hot Aisle's credit paid for the AMD arm on the run card and Hot Aisle is a sales prospect. The H100
arm was paid in cash. One run per arm, no repeats.
