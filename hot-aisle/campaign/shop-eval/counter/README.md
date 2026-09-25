# The counter · shop-eval lane

Evaluates a GPU compute shop's customer-facing side against Hot Aisle, the
reference operator: everything observable from signing up through releasing
the machine, without touching the GPU. Companion lane to `../../availability/`
(does the SKU actually provision) and `../../providers/` (published price
staging); this lane is account creation, price transparency, provisioning
time, availability honesty, API/CLI/TUI quality, billing granularity,
tenant hygiene, network path, support, and termination.

Python 3.9+ standard library only. No third-party packages, no network
access from these scripts.

## Files

- `PROTOCOL.md` -- the 10-step evaluation procedure. Read this before running
  the protocol against a new shop; under 2 hours and under $10 per shop.
- `counter_record.schema.json` -- the record shape
  (`second-run/counter-record@1`). Human-readable reference; not itself
  imported by the script.
- `counter_record.py` -- `validate`, `score`, `compare`. No `jsonschema`
  dependency; type checks are hand-rolled against the same shape the schema
  documents.
- `records/hotaisle-2026-09.json` -- the reference record, filled from known
  campaign facts. Every field not actually observed is the string
  `"unobserved"`.
- `records/digitalocean-2026-09.json` -- the first candidate record, same
  rule.
- `test_counter.py` -- stdlib `unittest`.

## Run

```sh
python -B counter_record.py validate records/hotaisle-2026-09.json
python -B counter_record.py score    records/hotaisle-2026-09.json
python -B counter_record.py compare  records/digitalocean-2026-09.json records/hotaisle-2026-09.json
python -B test_counter.py
```

## Scoring

The numeric output is an **uncalibrated checklist heuristic**, retained for
compatibility. Its weights and unknown-value defaults have not been validated
against customer outcomes. It must not rank providers or establish an operator
standard; `provider_ranking_permitted` is always false. Compare the underlying
observations, their sources and their coverage instead.

Availability calculations include only resolved actual creates, and only within
one known SKU/region group. Listing rows stay in the record but never count as
failed creates. Even 1/1 delivered is an observed sample, not a reliability or
truthfulness estimate. Unknown groups and mixed groups are not pooled.

`counter_record.py` scores 10 weighted dimensions, weights and the exact
arithmetic rule behind every number printed by `score`. A dimension with no
observed fields at all scores a neutral 50/100 rather than being penalized
for silence. A record carrying any entry in `disqualifying_observations`
(previous-tenant residue, billing that didn't stop at delete, a sales gate
in front of self-serve access, etc.) has its final score capped at 40/100
regardless of the weighted total -- see `DISQUALIFYING_CAP` in
`counter_record.py`.

## Provenance and disclosure

Every record's `provenance` block says who ran it, when, on which account,
how much was actually spent, and carries a one-line disclosure of any
funding relationship (or "none"), matching the convention in
`../../DISCLOSURES.md`. An unreconciled `money_spent_usd` remains `"unobserved"`;
any historical estimate belongs in `modeled_cost_usd` with its scope stated.
Compiled historical records are labeled `evidence_class: "derived"`; this does
not promote every source note to a direct measurement. Other supported classes
are published_claim, operator_report, measured and hypothesis.

## Scope

This lane does not touch the GPU: no model weights, no benchmarks, no
inference. That is `../../` (the campaign root) and its `results/`,
`ledger/`, and `tierbench-bridge/` lanes. This directory only reads the five
files listed at the top of `PROTOCOL.md`'s context and known prior-session
facts; it makes no provider API or console calls itself.
