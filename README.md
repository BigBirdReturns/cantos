# Cantos

**AI workflow software for continuing work across engineers, models and infrastructure.**

Cantos connects a job's inputs, decisions and results to reusable procedures. **Second Run**, its execution-and-reuse capability, runs supported procedures, reuses verified results and identifies work requiring requalification when declared dependencies change. AXM supplies the record and execution foundations.

## Start with the work already available

[Explore the historical record](https://bigbirdreturns.github.io/cantos/corpus/history.html) to search measurements, configurations, issues, price snapshots, workload traces and research. Each observation retains its source, dates and operating conditions. Filter a collection, inspect the original source, compare conditions and export the evidence relevant to your next job.

The delivered public projection contains **2,059,261 captured source observations** from **20 retained source files**. Counts describe source observations; repeated captures remain separate records.

| Collection | Captured observations |
|---|---:|
| Benchmark measurements and configurations | 293,172 |
| Producer issue / PR captures | 62,375 |
| Historical price snapshots | 1,689,060 |
| Model, workflow and demand metadata | 14,211 |
| Workload trace summaries | 11 |
| Research articles and podcast references | 427 |
| Dataset metadata | 5 |

The public projection includes the complete selected row files. Benchmark observations retain producer configuration and measurement conditions; price observations retain GPU-hour and instance-hour accounting, commitment terms and snapshot time. Research entries contain bibliographic metadata linked to the original publications. The source manifests and sharded data are in [`corpus/history/`](corpus/history/manifest.json).

## Continue a decision or procedure

[Open Cantos](https://bigbirdreturns.github.io/cantos/) to open a work record or choose a supported example. [The Chapek handover](https://bigbirdreturns.github.io/cantos/compute/chapek/) connects recorded work to its next executable action and a portable package. It demonstrates price scenarios, model-change planning, software-change requalification and successor handover. The model-change workload is labelled synthetic; retained measurements keep their original hardware and conditions.

For a local six-operation example, install Python 3.12+ and Node 22+, then run from this checkout:

```sh
python -B integration/work.py --request integration/examples/work.json --store .cantos-example-results
```

The first call executes six tasks. Repeating it reuses six verified results. Direct requests recompute when declared computation dependencies change. Record-bound requests hold when the retained binding no longer matches, so a successor can be established explicitly. [`integration/WORK.md`](integration/WORK.md) lists the supported operations and their inputs.

## Components

| Component | Use |
|---|---|
| [Historical collection](corpus/README.md) | Discover source observations, inspect conditions, compare and export; use the local collection tools to replay supported source normalization and extend its history. |
| [Decision workspace](app/README.md) | Retain sources, assumptions, reviews and earlier editions; revise and export a decision. |
| [Research Desk](research-desk/README.md) | Build source and claim histories using portable, append-only records. |
| [Second Run execution](integration/WORK.md) | Resolve retained procedure bindings, execute supported operations and reuse checked results. |
| [Compute tools](compute/README.md) | Compare allocations and model capacity costs using dated prices and explicit workload assumptions. |
| [Workload report](hot-aisle/README.md) | Inspect retained measured runs and carry qualified outputs into decisions. |
| [Community collections](compute/community/README.md) and [claim shelf](shelf/README.md) | Compare attributed results, apply local review criteria and operate independent collections. |
| [Provider research](floor/README.md), [ClusterMAX investigation](clustermax-challenge/README.md), [source updates](circulate/README.md) | Inspect captured operational evidence, historical studies and subsequent source changes. |

Cantos covers recurring software work, production and technical investigation. The compute campaign is one application. Original sources, failed attempts, corrections and contributor credit remain attached to their histories. An imported observation can support discovery before a task-specific execution procedure exists; the interface labels the available next action.

## Build and qualification

```sh
python -B app/source/build.py
python -B app/tests/check_build.py
python -B corpus/build_history.py --check
python -B app/tests/site_surface_check.py
```

**Cantos qualification** is the single CI entry for the workspace, historical reader, execution instruments, shelf and ClusterMAX checks. The existing Pages workflow deploys only after that CI passes for the exact relevant source state. Component guides retain their native test commands. [`app/BUILD.md`](app/BUILD.md) explains the source-driven page build; [`app/PRESENTATION.md`](app/PRESENTATION.md) defines the shared reader-facing language.

## Source context

Original source dates, measurements, accounting bases and disclosures stay with the relevant observation or study. Run 3 is a retained campaign, whose funding and accounting are documented in [`hot-aisle/campaign/DISCLOSURES.md`](hot-aisle/campaign/DISCLOSURES.md). The historical source payloads remain in their owning collections; the public projection exposes the factual fields and source links needed for discovery. Each component keeps its own licence and operating contract.
