# floor — a written floor for a properly set up neocloud, and every reviewed shop's distance from it

Built 2026-09-29 from the public tail captured that day (ClusterMAX reviews and rubric, SemiAnalysis expectations pages and audit tool, InferenceX and MLPerf, provider status histories, OpenComputePrices) and from this project's own Run 1 to Run 3 telemetry. Read [index.html](index.html) for the table, or the files directly:

| File | What it is |
|---|---|
| [FLOOR.md](FLOOR.md), [floor.json](floor.json) | The floor: 86 items across access, delivered performance, tail and gates, reliability, operations, price band, and claim limits. Every number carries a source, its producer (ours or imported), and its window. Eight items are UNKNOWN on purpose and say what would establish them. |
| [PRESCRIPTIONS.md](PRESCRIPTIONS.md), [prescriptions.json](prescriptions.json) | 35 recurring shortfalls found across the 85 review pages, ordered by providers affected, each with what the customer observes, what it costs where we measured it, the likely fix with its source, effort class, and how the kit verifies the fix. |
| [rate/RATINGS.md](rate/RATINGS.md), [rate/RATINGS.jsonl](rate/RATINGS.jsonl), [rate/rate.py](rate/rate.py) | Desk-tier rating of all 85 providers on six dimensions from public evidence only. MEETS / SHORT / UNKNOWN per dimension with evidence ids; distance to floor counts only SHORT. ClusterMAX medals are shown as context and are never inputs. `python rate.py` regenerates; `python -m unittest test_rate` checks. |
| [findings/TELEMETRY.md](findings/TELEMETRY.md) | 21 measured facts from our own runs that the front door does not show, with evidence class and window. |
| [findings/EFFICIENCY.md](findings/EFFICIENCY.md), [findings/findings.jsonl](findings/findings.jsonl) | 14 market inefficiencies quantified from the imported data, ranked by magnitude, each with what a floor-conforming shop would do and how the kit measures it. |
| [SOURCES.md](SOURCES.md) | Every cited file with its sha256. |

## What the first run says

- Only one provider, Nebius, is a well-evidenced zero. Thirty providers sit at distance zero because their pages are stubs and nearly every dimension is UNKNOWN; the table fades rows with fewer than three evidence items so that is visible.
- The reference shop does not pass its own floor on public evidence. Hot Aisle rates distance 4 from the November 2025 review sentences (health checks, monitoring, shared storage, RBAC, Slurm not set up) and from having no status page with history. The project's private measurements say otherwise on delivered performance, and are not used here. The first prescription therefore applies to the reference: publish the status history, the health-check and monitoring surfaces, and the current attestation, so the public record catches up with the operation.
- The most common shortfalls are the cheapest to fix: 25 providers lack wired GPU health checks, 23 lack a working monitoring dashboard, 16 deliver Slurm or Kubernetes broken, 13 have no usable shared filesystem. All four are configuration and process, and the SemiAnalysis expectations pages document the target state.
- The largest measured inefficiencies are on the customer's side of the seat, not the shop's: serving below the concurrency knee (23x cost swing on the MI300X), runaway generation (67 percent of decode tokens spent on requests that failed grading; sanitizing lifts total correct 42 percent), and unreconciled cost windows (the same 4,336 accepted requests priced five ways, 1.57x apart, with no invoice).
- Same-SKU price dispersion across providers in July 2026 is 3.0x to 3.6x at p90 over p10, and the reference shop's own price page disagrees with the public feed.

## Limits

Review text is mostly ClusterMAX 2.0, dated November 2025; providers may have fixed items since, and each shortfall marks sentences that describe an initial test round. Shortfall labels are hand-assigned to sentences with regex assistance; recall is incomplete. Reliability has no threshold because none is defined in any input; counts are reported. Only 24 providers have an incident file and 55 have fetched surfaces. Nothing here was rented or re-measured; the rental tier is the shop-eval kit, which has not yet run on a second shop.

## Disclosure

The Hot Aisle arms of the qualified campaign ran on a $200 credit given by Hot Aisle to the Second Run team, which is pitching Hot Aisle a paid engagement. Costs are computed at undiscounted list price. The DigitalOcean arm was self-funded at list price. Hot Aisle's row in the rating uses public evidence only.
