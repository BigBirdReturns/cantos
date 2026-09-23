# Compute decision contracts

## The mining-calculator analogy

The useful pattern is immediate interaction: choose resources, enter your own costs, inspect a comparison, and act. The important difference is that AI output is not a fungible hashrate. Model identity, requested operation, quality, latency, data rights and context change what counts as useful work. This desk exposes price estimates immediately while preserving that qualification boundary.

There are three comparisons, deliberately distinct: the rental price of a stated allocation; the price of identical accepted work on different physical deployments; and the price of different procedures/models meeting one agreed outcome contract. The first cannot stand in for the latter two.

## Rental model

For reserved hours h, known minimum m, n GPUs, GPU-hour price p, hourly extra x and fixed extra f:

`C = (n × p + x) × max(h, m) + f` for a nonzero reservation.

This is a continuous-hour planning model. It does not infer short-session billing rounding, tax, unavailable stock or equivalent managed service. Whole-node minima stay visible. The eight-GPU one-month Hot Aisle example uses a 30-day / 720-hour planning month; the contractual month may differ. A listed single-GPU price can be a normalization rather than a purchasable one-GPU instance. The catalogue records that distinction.

Rate changes reprice a saved plan, producing a new checksum and retaining the prior decision. A price change does not by itself invalidate a hardware observation. Changing the artifact, runtime, workload, acceptance rule, traffic shape or relevant hardware does require renewed qualification of the affected result.

## Ownership model

Energy = `(activeHours × systemLoadW + idleHours × systemIdleW) / 1000 × electricityPrice × facilityMultiplier`. Amortization = `(purchase − expectedResidual) / months`. Add explicit maintenance and other operating costs. It uses a 30-day month. Human effort, capital cost, outages and tax require separately supplied costs or analysis.

When both work rates are supplied, rental hours = local active hours × local accepted-work rate / cloud accepted-work rate. These rates remain declarations until backed by comparable evidence. One allocation exceeding 720 hours is a capacity warning, not permission to invent parallelism. No hardware-buying recommendation follows solely from a crossing in this chart.

## Reuse model

Each workload family carries its share, baseline premium seconds per request, candidate time and cost, fallback fraction and premium-path designation. Failed lower-cost attempts still consume their full candidate cost. Their premium fallback consumes the corresponding baseline premium effort. Validation is charged to every request, qualification once per campaign. A strict cumulative-cost crossing requires more than the initial qualification cost in net recurring savings.

Shares are a scenario, not an observed universal 80/20 law. The default illustrates why 79% of requests moving can save only about 16.5% of premium time when demanding requests dominate runtime. Residency, batching, interference and allocation ownership are not simulated. Reported GPU-time reduction therefore does not imply released billable capacity.

Actual policy admission requires representative held-out tasks, a frozen acceptance contract, measured end-to-end deadlines, all retry costs, security/privacy compatibility and resource admission. Existing TierBench cost-per-success discipline informs this model; no historical TierBench task score is assigned to these GPUs.

## Integration contract

The browser, stdio MCP tools and command-line helpers use one economic engine. The bridge observes an operator-configured directory and endpoint; it does not maintain a second orchestrator or queue. Available results are selected by exact file hash. Unknown inputs produce holds. The source files remain authoritative and can be inspected without the public site.

The imported Aperture object is inventory evidence. Memory fitting is not measured task ability; endpoint connectivity is not performance; a transport-successful response is not a correct task. The retained vLLM engine preserves successful-request normalization and aggregate statistics without exporting generated content.

## Category progression

Implemented here: immediate price/ownership/reuse planning, dated sources, portable decisions, repricing lineage, read-only evidence discovery, runtime observation and MCP access. Native calibration remains the next producer-side step. An executor-backed campaign should reuse the existing lifecycle owner and acceptance machinery, adding an explicitly approved job plan and target adapter rather than implementing a new queue in this calculator.

A future multi-provider placement contract must additionally specify data locality, rights, resource limits, deadline, acceptance, verification, price, failure behavior and authority. Payment cannot promote unqualified evidence into a pass. Market settlement, knowledge admission and execution admission stay separate. A priceboard is not yet that market.

## Published scope and neutrality

Providers are catalog data. Rankings sort stated cost, never sponsorship or undisclosed referrals. Hot Aisle is one participant; it can win or lose the same calculation as every other provider. User-reported and independently reproduced evidence would require distinct attribution if introduced. No unsolicited customer data is used or shared by this release.
