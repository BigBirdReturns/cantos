# <shop> workload evaluation

Each comparison must bind the candidate benchmark table to a scope file using its SHA-256. Use `diagnose/diagnose.py --scope scope.json --reference-scope-id <id>`. The reference scope IDs and evidence are in `diagnose/reference/hotaisle-2026-09.json`. If workload identity, acceptance rule, cost window, rate, or complete configuration cannot be verified, report **not comparable** and omit the ratio. `UNKNOWN` means the field was not observed; it is not a shop failure.

## Comparison decision

- **Label:** <matched | different complete configuration | historical | not comparable>
- **Scope and acceptance:** <workload id, model/tokenizer revisions, precision, cache policy, load profile, quality rule, latency/deadline gates>
- **Configuration:** <GPU model/count, runtime image digest/version, backend/kernel, tensor parallelism, plus material host details>
- **Evidence:** <paths/URLs and SHA-256 of scored table>
- **Economic comparison:** <allowed for this exact workload, acceptance rule and cost scope | unavailable, with reason>
- **Operator causality:** <not established unless a controlled intervention isolates one variable>

## Cost views

| View | Candidate | Hot Aisle | Evidence and denominator |
|---|---:|---:|---|
| Best qualifying cell, modeled at list rate | | | Same acceptance rule; per-cell work only |
| Arm own-window, modeled | | | Clearly stated arm request/start-to-end window |
| Whole-seat, modeled | | | Request-to-release including setup and idle time |
| Billed amount | | | Invoice/usage record; keep separate from modeled values |
| Customer total cost for this work | | | Include compute, minimums, network/storage, engineering, and retry cost only when sourced; otherwise `UNKNOWN` |
| Customer value from accepted work | | | Requires a customer value model; otherwise `UNKNOWN` |
| Operator economics | | | Margin, energy, depreciation, support, and internal labor basis usually unobserved; otherwise `UNKNOWN` |

Show a ratio only for matching workload identity, acceptance semantics, and cost scope after the tool validates both scopes. Keep cell, arm-window, whole-seat, billed, customer-total-cost, customer-value, and operator-cost views separate. A customer workload matched across GPUs can support an economic comparison for that workload; configuration differences still do not identify operator skill or cause. Do not infer customer value or operator margin from provider list rates.

## Findings

For each **WRONG** finding, cite the observed value and source, competing plausible causes, the minimum discriminating test, a bounded reversible intervention, acceptance criteria, rollback, and the access needed. Treat hardware, clock, PCIe, firmware, RAS, NUMA, tenant, stack, and power readings as signals unless a scoped test establishes impact. Do not infer hidden host cooling, PSU, tenant, or topology causes from customer-visible output. Never recommend generic power-limit changes or ACS overrides.

| Status | Observation and evidence | Competing causes / discriminating test | Bounded change, acceptance and rollback | Access |
|---|---|---|---|---|
| WRONG / SIGNAL / RIGHT / UNKNOWN / NOT COMPARABLE | | | | |

## Reusable learning

- **Right:** <confirmed strengths, with the tested scope>
- **Could improve:** <measured gap or explicit hypothesis>
- **Unknown:** <important missing evidence and how to obtain it>
- **Next controlled test:** <one variable, fixed workload, repeat count, pass/fail metric>

Do not rank a composite counter score as provider quality. Report its observed dimensions and provenance. Availability outcomes need actual attempt counts; no offer or missing telemetry is not proof of failure. Label historical results with their date and limits.

## Provenance and disclosure

- **Evaluator/date:** <name or handle, UTC date>
- **Funding and relationship:** <plain disclosure>
- **Offer/seat:** <SKU, region if known, requested, ready, released times>
- **Spend:** <modeled list-rate compute, invoice amount, other test cost; separate totals>
- **Unmeasured limits:** <repetition variance, current capacity, support, recovery, host telemetry, etc.>
- **Artifacts:** <scope JSON, raw cells, scored table, fingerprint, counter, logs, manifest>
