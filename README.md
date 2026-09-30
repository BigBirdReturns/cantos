# Cantos

Cantos is the umbrella for work that can be understood, continued, corrected, and built upon. It preserves the connection between evidence, judgment, decisions, execution, and consequences, so another person or a later session can continue meaningful work without reconstructing it: what was known, why a choice was reasonable, the alternatives considered, what actually happened, and what changed afterward. Failures, abandoned approaches, corrections, and contributor credit are kept on purpose; they are material for the next piece of work.

The workflow every surface here exposes is general:

**sources → claims → measurement → economics → recommendation → delivery → changed inputs → revised recommendation**

**Second Run** is the execution and reuse program inside Cantos. Its proposition is to turn resolved judgment into repeatable, inspectable execution, across three areas: software (qualify a recurring workflow, retain its procedure, measure failures, intervention, latency, and total cost per accepted outcome), production (restoration, rendering, and reconstruction with the source and processing record intact), and technical investigation (reconstruct a consequential claim, test its decisive assumptions, and establish what evidence would change the conclusion). Its operating rule: reuse a procedure while its preconditions hold, escalate changed conditions and unresolved judgment, and keep consequential commitments under human authority.

**AXM** supplies the foundations that let the knowledge and the work outlive their original context. Its thesis is records that outlive their infrastructure: [Genesis](https://github.com/BigBirdReturns/axm-genesis/blob/main/docs/THREE_LAYERS.md) binds claims to exact source material with verifiable identity and provenance, the journals record what was retrieved, evaluated, rejected, and concluded, and [Arc](https://github.com/BigBirdReturns/axm-arc/blob/main/README.md) separates authored artifacts, execution, persistent consequences, and presentation. [Start here](https://github.com/BigBirdReturns/axm-core/blob/main/START_HERE.md) for the ecosystem in one page.

Cantos makes knowledge and judgment compound. Second Run makes the applicable parts executable. AXM gives them durable identity, evidence, and continuity.

## What is in this repository

This repository holds one instance of that workflow carried all the way through, plus the instruments it produced. The instance is a Second Run software-area campaign: the same coding workload qualified on two rented GPU seats, its procedure retained, its outcome measured as cost per accepted request, and its record kept so the decision can be recomputed, challenged, and revised when an input changes. Around it sit the instruments that turned the campaign into standing capability.

| Directory | What it is | Page |
|---|---|---|
| [`app/`](app/) | The decision workspace. Opens on the campaign's retained decision (Run 3, Edition 01), with the scenario controls, review and retain, editions, the evidence plates, and the system map. A synthetic worked example is second in the rail. | [Workspace](index.html) |
| [`research-desk/`](research-desk/) | The desk that holds sources, claims, runs, calculations, and conclusions with dependency pins and hash-chained history. The first real packet has 1,847 public records. | [Research Desk](research-desk/index.html) |
| [`hot-aisle/`](hot-aisle/) | The campaign: the connected runner, the retained Run 1 to Run 3 records, the backfill of the public InferenceX and MLPerf history, the price-history join, and the shop-eval kit for rating a rented seat. | [Workload report](hot-aisle/index.html) |
| [`floor/`](floor/) | What the campaign and the public tail established about the market: a written floor for a properly set up neocloud (86 sourced items), every ClusterMAX-reviewed provider's distance from it on public evidence, 35 prescriptions ordered by providers affected, and the telemetry and market findings behind them. | [Distance to the floor](floor/index.html) |
| [`clustermax-challenge/`](clustermax-challenge/) | A technical investigation: does the ClusterMAX medal predict the job? Two frozen retrospectives, the 3.0 binding, standing incident collection. | [Challenge](clustermax-challenge/index.html) |
| [`circulate/`](circulate/) | The loop that keeps the record current: each cycle pulls new public rows through every instrument, hash-checks the frozen studies, leaves a receipt, and runs eleven probes that try to break each joint. | [Receipts](circulate/index.html) |
| [`compute/`](compute/), [`integration/`](integration/), [`shelf/`](shelf/) | The provider-neutral decision desk, the runner that binds retained judgments to deterministic operations, and the public shelf of bounded claims. | [Compute desk](compute/index.html) |
| [`evidence/`](evidence/) | The inputs the instruments read at run time, so a clean clone needs nothing else. | |

Second Run's production and investigation work outside this campaign (media restoration and reconstruction, the SemiAnalysis network study) is retained in the estate's own records and is not in this repository.

## What the campaign established

- **The floor is mostly configuration.** Across 85 reviewed providers the most common shortfalls are wired GPU health checks (25), a working monitoring dashboard (23), Slurm or Kubernetes delivered working (16), and a usable shared filesystem (13). None is capital.
- **One provider is a clean zero**, Nebius, on 28 evidence items. Thirty sit at zero only because their public record is a stub, and the table says so.
- **The reference does not pass its own floor on public evidence.** Hot Aisle, whose measured performance anchors the floor, rates distance 4 on its November 2025 review record. The first prescription is the reference's.
- **The biggest waste is on the customer's side of the seat.** Serving below the concurrency knee swings cost 23x. Two thirds of decode tokens in the qualified run went to requests that failed grading; output sanitizing lifts total correct 42 percent. The same 4,336 accepted requests price five ways, 1.57x apart, with no invoice reconciling them.
- **The market disagrees with itself about price.** Same-SKU on-demand prices spread 3.0x to 3.6x across providers in July 2026, aggregators differ 2x on one provider's H100, and the incumbent research house's TCO priors sit below 1 percent of observed listings.
- **The medal does not yet predict the job.** Both frozen retrospectives are inconclusive and both flip with the bootstrap seed. The standing version reruns on a rolling window.

## What comes next, from the record

The controller's disposition of 28 September sets the sequence, and it is about the workflow, not the campaign:

1. **Consume retained judgment through the existing owners**: a cold process locates the applicable retained work, identifies a valid next operation or a precise residual, and keeps the contribution and correction lineage. Acceptance is a request, a supported native result, a fresh-process continuation, one source correction, and only the affected work going stale.
2. **Bind performance evidence to the exact executable variant**, so selecting a seat resolves its implementation and preparation requirements, not just a name and an hourly price.
3. **Qualify preparation and residency economics** from the partitioned clock: preflight, image and model setup, warm readiness, work, drain, release; cold launch against prepared launch against continued warm residency under the same useful-work contract.
4. **Test the cheapest applicable cache mechanism**, conditional on the actual workload, with fresh-output semantics and full costs retained.
5. **Grade the existing output-contract candidate**, then qualify live timing separately.
6. **Prove transfer on recurring document and source updates** using the estate's own corpus: unchanged work reused, changed dependencies selectively rebuilt, deletions and permission changes reaching derived results, restart not duplicating completed effects.

Ahead of those, two bounded items: the rental tier of the shop-eval kit has never run on a second seat, and the loop runs by hand until its nightly workflow is added.

## Running it

```sh
python -B app/source/build.py                # rebuild the workspace; gates in app/tests/
python circulate/circulate.py                # one real cycle; writes circulate/receipts/<date>/
python circulate/probes/run_probes.py        # eleven probes; exits nonzero on any FAIL
python circulate/circulate.py --offline      # the same path on fixtures, no network
python floor/rate/rate.py                    # regenerate the rating from the evidence on disk
```

Three rules hold everywhere. No value is invented; a missing or gated source records HOLD, never a number. Every row carries who produced it and under what conditions, and an imported row stays labelled imported. A measured row is one whose raw bytes and invoice are retained, so anyone can recompute the receipt. Nothing here rents, provisions, publishes, or contacts a provider on its own. Funding terms for the campaign are in [hot-aisle/campaign/DISCLOSURES.md](hot-aisle/campaign/DISCLOSURES.md). Extracted 2026-09-29 from the axm-tools demo shelf with full history.
