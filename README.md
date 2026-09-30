# Cantos

The root page (`index.html`) is the Cantos decision workspace: a single file that opens locally and loads the verified Run 3 decision (MI300X against H100) from Ctrl K. Its source, tests and build live in `app/` (see `app/BUILD.md`). The distance-to-the-floor page is at `floor/index.html` and the circulation receipts are at `circulate/index.html`; both are linked from the workspace.

Cantos rates every GPU cloud against a written floor for what a properly set up neocloud delivers, names the exact shortfall behind each miss, prescribes the fix, and keeps all of it current from public data every night. Where public data cannot answer, the practice inside it, Second Run, rents a seat, runs the workload, and retains everything so the answer can be recomputed by anyone.

It exists because the market has one rating system, it is relative, it is behind a paywall, it comes with no prescription, and its own review text shows the same operational gaps rebuilt by shop after shop. A buyer choosing a provider, a shop trying to reach the floor, and an analyst who wants numbers with receipts all need the same thing: the distance, the reason, the fix, and the evidence, refreshed without anyone asking.

## What the first cycle found

- **The floor is mostly configuration.** Across 85 reviewed providers the most common shortfalls are wired GPU health checks (25 providers), a working monitoring dashboard (23), Slurm or Kubernetes delivered working (16), and a usable shared filesystem (13). None of these is capital. The target state for each is documented in pages already captured here.
- **One provider is a clean zero.** Nebius, with 28 evidence items and no unknowns. Thirty others sit at zero only because their public record is a stub, and the table fades them so a thin row never reads as a pass.
- **The reference does not pass its own floor on public evidence.** Hot Aisle, the shop whose measured performance anchors the floor, rates distance 4 on its November 2025 review sentences and on having no status page with history. The rating uses only public evidence, so this is the first prescription and it is Hot Aisle's own: publish the status history, the health-check and monitoring surfaces, and the current attestation.
- **The biggest waste is on the customer's side of the seat.** Serving below the concurrency knee swings cost per thousand requests 23x on the MI300X. In the qualified run, 67 percent of decode tokens went to requests that failed grading, and output sanitizing lifts total correct by 42 percent. The same 4,336 accepted requests price five ways, 1.57x apart, with no invoice reconciling any of them.
- **The market disagrees with itself about price.** Same-SKU on-demand prices spread 3.0x to 3.6x across providers in July 2026, aggregators differ 2x on one provider's H100, and the incumbent research house's TCO priors sit below 1 percent of observed listings.
- **The medal does not yet predict the job.** Two frozen retrospectives of ClusterMAX medals against provider incident histories are both inconclusive and both flip with the bootstrap seed. The standing version reruns nightly on a rolling window.

## What it does each cycle

The loop pulls new public rows from the InferenceX benchmark artifacts, the OpenComputePrices release, provider status pages, and the SemiAnalysis newsletter, pushes them through every instrument, hash-checks the frozen studies, recomputes the economics and the standing retrospective, rebuilds the Research Desk packet, refreshes the front door, runs seven test suites, and leaves a receipt. Eleven probes then try to break each joint: a tampered packet, a tampered evidence file, a shifted price, a truncated artifact, a gated dataset, a stale kit, a perturbed study, a mislabeled status platform, a killed run, a duplicated artifact, a credential scan. The first real cycle was clean.

Three rules hold everywhere. No value is invented; a missing or gated source records HOLD, never a number. Every row carries who produced it and under what conditions, and an imported row stays labelled imported. A measured row is one whose raw bytes and invoice are retained here, so anyone can recompute the receipt.

## What is next

- **The rental tier.** The shop-eval kit rates a rented seat against the floor with the same workload the reference ran. It has not yet run on a second shop. The first is a same-silicon MI300X at another provider, which answers whether the reference's number is the silicon or the shop.
- **The nightly schedule.** The loop runs by hand today. Its workflow is the Pages deploy plus the driver and probes in one job.
- **Prescriptions with prices.** Each shortfall has a fix and an effort class. The next pass attaches what it costs a shop to close and what it costs a customer to leave open.

## Layout

| Directory | Page |
|---|---|
| [`floor/`](floor/) — the floor (86 sourced items, 8 explicitly unknown), the rating of 85 providers, 35 prescriptions, and the telemetry and market findings behind them | [Distance to the floor](floor/index.html) |
| [`circulate/`](circulate/) — the driver, the probes, the receipts | [Receipts](circulate/index.html) |
| [`hot-aisle/`](hot-aisle/) — the qualified campaign on Hot Aisle MI300X against a DigitalOcean H100, the runner, the backfill of the public InferenceX and MLPerf history, the price-history join, the shop-eval kit | [Workload report](hot-aisle/index.html) |
| [`clustermax-challenge/`](clustermax-challenge/) — the frozen R1 and R2 retrospectives, the 3.0 binding, standing incident collection | [Challenge](clustermax-challenge/index.html) |
| [`research-desk/`](research-desk/) — sources, claims, runs and conclusions with dependency pins and hash-chained history | [Research Desk](research-desk/index.html) |
| [`compute/`](compute/), [`integration/`](integration/), [`shelf/`](shelf/) — the provider-neutral decision desk, the runner that binds retained judgments to deterministic operations, the public shelf | [Compute desk](compute/index.html) |
| [`evidence/`](evidence/) — the inputs the product reads at run time, so a clean clone needs nothing else | |

```sh
python circulate/circulate.py              # one real cycle; writes circulate/receipts/<date>/
python circulate/probes/run_probes.py      # eleven probes; exits nonzero on any FAIL
python circulate/circulate.py --offline    # the same path on fixtures, no network
python floor/rate/rate.py                  # regenerate the rating from the evidence on disk
```

Each instrument's README states its tests and its qualification boundary. Nothing here rents, provisions, publishes, or contacts a provider on its own. Sponsor and funding terms for the qualified campaign are in [hot-aisle/campaign/DISCLOSURES.md](hot-aisle/campaign/DISCLOSURES.md). Extracted 2026-09-29 from the axm-tools demo shelf with full history.
