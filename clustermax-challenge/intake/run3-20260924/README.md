# Real Run 3 evidence intake

Four retained campaign records were read, including one unscored smoke run. Three scored arms span two providers and two distinct allocations. Exact response/evaluator/mapping/result hashes and request-level acceptance counts were checked; no new GPU work or grading ran.

**The existing calculator successfully consumes these real files.** The exported calculator-report.html and calculator-evidence.json use its exact embedded report engine and pass its recomputation verifier. The benchmark-window modeled comparison is $0.6908 versus $1.0322 per 1,000 evaluator-passed, latency-qualified requests: 33.1% lower on Hot Aisle for these retained inputs. This is not whole-bill or repeated-campaign savings.

## Why customer-outcome scoring is on hold
There is no submitted ClusterMAX prediction plan or medal binding. These are one-GPU allocations, not a service-matched managed-cluster cohort; there are only two providers, and actual invoices remain absent. The campaign preregistration is preserved, not replaced by a retroactive challenge preregistration.

## Cost boundary
Hot Aisle reused one seat for smoke, A/T0 and A/T1. Per-arm modeled lower bounds overlap and must not be added as separate bills. The Run 3 summary also reports an own-seat-equivalent scenario; this is distinct from the actual shared lease. DigitalOcean has a recorded request-to-release window with modeled cost but no reconciled invoice.

## Run intake
```sh
python scripts/campaign_intake.py --root ../hot-aisle --spec intake/run3-20260924/spec.json --output /tmp/run3-intake.json
```
Output paths must be new. Exit 0 means source intake succeeded; challenge_status remains HOLD. The converter never executes submitted code, creates a cloud resource, or uploads a bill.

## Add actual allocation bills
Supply --bills with {"bills":[...]} following billing.template.json. Each bill needs a local receipt hash, complete-run-roster declaration, gross/credits/cash reconciliation, all cost line items and explicit cost shares adding to exactly one. Cash, credits, full-invoice cost and the original modeled figures remain separate. The adapter never silently redefines v1.4 total_cost_usd. A retrospective intake cannot manufacture prior predictions.

## Files
intake.json retains source counts, clocks, economics and holds; calculator-report.html is the human-readable modeled-window comparison; calculator-evidence.json is its recomputable sealed record. calculator-replay.json records all three arms.
