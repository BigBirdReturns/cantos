# Cantos maintainer verdict

**INCOMPARABLE**

- undeclared changed condition: observed.version

| Metric | Baseline | Candidate |
| --- | ---: | ---: |
| total_tasks | 12 | 12 |
| accepted_tasks | 12 | 12 |
| acceptance_rate | 1.0 | 1.0 |
| p95_latency_s | 227.12695851842864 | 206.3553885810193 |
| p95_ttft_s | 227.06750231523756 | 206.29665737515307 |
| accepted_per_s | 0.011429450528025513 | 0.012140951239356896 |
| peak_request_concurrency | 1 | 1 |
| cost_per_accepted | unpriced | unpriced |

## Evidence scope

- This verdict covers the supplied workload, serving endpoints and policy only.
- Declared weights, hardware, tokenizer and server flags are operator declarations; HTTP probes do not attest them.
- Repeated cases are correlated. Trial ranges describe variation and are not a population confidence guarantee.
- TTFT measures first visible content at the client, including network and queueing; content chunks are not tokens.
- Token counts come from server usage. The instrument does not manufacture per-token timings, power or GPU run counts.
- No request retries. Transport and incomplete stream failures are retained and force an error verdict.
- Server cache state, co-tenancy, thermals and load require operator controls and declared identity settings.
