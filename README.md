# Cantos

A written floor for a properly set up neocloud, every reviewed shop's distance from it on public evidence, the prescriptions that close each gap, and the loop that keeps all of it current. Cantos is the product. Second Run is the practice it runs: qualify a deployment on a real seat, retain everything, and rerun only when a decision needs conditions no retained row covers.

Three rules travel with everything here. No value is invented; a missing or gated source records HOLD, never a number. Every row carries who produced it and under what conditions, and an imported row stays labelled imported. The sponsor disclosure travels with anything published.

## Start here

| Directory | What it is | Page |
|---|---|---|
| [`floor/`](floor/) | The floor (86 sourced items, 8 explicitly unknown), the desk-tier rating of 85 ClusterMAX-reviewed providers on six dimensions from public evidence only, 35 prescriptions ordered by providers affected, and the telemetry and market findings behind them | [Distance to the floor](floor/index.html) |
| [`circulate/`](circulate/) | The loop. Each cycle pulls new public rows (InferenceX artifacts, OpenComputePrices, provider status pages, the SemiAnalysis newsletter) through every joint below, hash-checks the frozen studies, leaves a receipt, and runs eleven probes that try to break each joint | [Receipts](circulate/index.html) |
| [`hot-aisle/`](hot-aisle/) | The qualified campaign on Hot Aisle MI300X against a DigitalOcean H100: the connected runner, the retained Run 1 to Run 3 records, the backfill of the full public InferenceX and MLPerf history, the price-history join, the shop-eval kit for rating a rented shop | [Workload report](hot-aisle/index.html) |
| [`clustermax-challenge/`](clustermax-challenge/) | Does the ClusterMAX medal predict the job? The frozen R1 and R2 retrospectives (both inconclusive, both seed-fragile), the 3.0 binding, standing incident collection for 23 providers | [Challenge](clustermax-challenge/index.html) |
| [`research-desk/`](research-desk/) | The desk that holds sources, claims, runs and conclusions with dependency pins and hash-chained history; the first real packet has 1,847 public records | [Research Desk](research-desk/index.html) |
| [`compute/`](compute/), [`integration/`](integration/), [`shelf/`](shelf/) | The provider-neutral decision desk, the runner that binds retained judgments to deterministic operations, and the public shelf | |

## What the first cycle says

- Only one provider, Nebius, is a well-evidenced zero distance from the floor. Thirty sit at zero because their public record is a stub, and the table fades them.
- The reference shop does not pass its own floor on public evidence. Hot Aisle rates distance 4 on its November 2025 review sentences and on having no status page with history. The project's private measurements say otherwise on delivered performance and are not used in the rating. The first prescription is therefore Hot Aisle's own.
- The most common shortfalls are configuration and process: wired GPU health checks (25 providers), a working monitoring dashboard (23), Slurm or Kubernetes delivered working (16), a usable shared filesystem (13).
- The largest measured inefficiencies are on the customer's side of the seat: serving below the concurrency knee, runaway generation, and unreconciled cost windows.

## Running it

```sh
python circulate/circulate.py              # one real cycle; writes circulate/receipts/<date>/
python circulate/probes/run_probes.py      # eleven probes; exits nonzero on any FAIL
python circulate/circulate.py --offline    # the same path on fixtures, no network
python floor/rate/rate.py                  # regenerate the rating from the evidence on disk
```

Each instrument's own README states its tests and its qualification boundary. Nothing here rents, provisions, publishes, or contacts a provider on its own.

## History and disclosure

Extracted 2026-09-29 from the axm-tools demo shelf with full history, so every frozen study hash and every retained receipt still resolves. The Hot Aisle arms of the qualified campaign ran on a $200 credit given by Hot Aisle to the Second Run team, which is pitching Hot Aisle a paid engagement; costs are computed at undiscounted list price; the DigitalOcean arm was self-funded at list price. Hot Aisle's row in the rating uses public evidence only.
