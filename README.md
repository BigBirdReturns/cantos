# Cantos

Cantos is a body of work people can find, understand, reproduce, change, and extend. The bulk dataset supplies discovery and comparison; work histories preserve decisions and consequences; Second Run makes applicable work executable.

Cantos preserves the connection between evidence, judgment, decisions, execution, and consequences, so another person or a later session can continue meaningful work without reconstructing it: what was known, why a choice was reasonable, the alternatives considered where documented, what actually happened, and what changed afterward. Failures, abandoned approaches, corrections, and contributor credit are kept on purpose. Missing rationale stays missing; a configuration change establishes what changed without establishing why someone chose it.

The research-to-decision workflow is general:

**sources → claims → measurement → economics → recommendation → delivery → changed inputs → revised recommendation**

**Second Run** is the execution and reuse program inside Cantos. Its proposition is to turn resolved judgment into repeatable, inspectable execution, across three areas: software (qualify a recurring workflow, retain its procedure, measure failures, intervention, latency, and total cost per accepted outcome), production (restoration, rendering, and reconstruction with the source and processing record intact), and technical investigation (reconstruct a consequential claim, test its decisive assumptions, and establish what evidence would change the conclusion). Its operating rule: reuse a procedure while its preconditions hold, escalate changed conditions and unresolved judgment, and keep consequential commitments under human authority.

**AXM** supplies the foundations that let the knowledge and the work outlive their original context. Its thesis is records that outlive their infrastructure: [Genesis](https://github.com/BigBirdReturns/axm-genesis/blob/main/docs/THREE_LAYERS.md) binds claims to exact source material with verifiable identity and provenance, the journals record what was retrieved, evaluated, rejected, and concluded, and [Arc](https://github.com/BigBirdReturns/axm-arc/blob/main/README.md) separates authored artifacts, execution, persistent consequences, and presentation. [Start here](https://github.com/BigBirdReturns/axm-core/blob/main/START_HERE.md) for the ecosystem in one page.

Cantos makes knowledge and judgment compound. Second Run makes the applicable parts executable. AXM gives them durable identity, evidence, and continuity.

## What is in this repository

The [Cantos overview](index.html) is the entry point. Start a source-based investigation, reopen a decision packet, inspect the execution/reuse path, or choose a retained example. A fresh visit opens the overview; a previously saved decision resumes without being replaced. Returning to the overview does not change that decision.

The repository implements parts of the broader program: a general Research Desk, a bounded decision workspace, checked execution and reuse, and a substantial compute investigation. Run 3 is one retained experiment within that investigation. It supplies a useful test case; it does not define Cantos or Second Run. The existing pages keep their own calculation, evidence and execution boundaries.

| Directory | What it is | Page |
|---|---|---|
| [`app/`](app/) | Cantos overview and decision workspace. Choose Run 3 or the synthetic invoice example, or reopen a supported packet; revise assumptions, review, retain editions and export. The overview itself is navigation, not an invented decision record. | [Cantos](index.html) |
| [`research-desk/`](research-desk/) | The desk that holds sources, claims, runs, calculations, and conclusions with dependency pins and hash-chained history. The first real packet has 1,847 public records. | [Research Desk](research-desk/index.html) |
| [`corpus/`](corpus/) | Local interface over an independently retained bulk collection: search, compare conditions, inspect sources and projection changes, rebuild an observation, and export its extended native history. Requires a separate source bundle; the bulk payload is not shipped in this repository. | [Run locally](corpus/README.md) |
| [`hot-aisle/`](hot-aisle/) | The campaign: the connected runner, the retained Run 1 to Run 3 records, the backfill of the public InferenceX and MLPerf history, the price-history join, and the shop-eval kit for rating a rented seat. | [Workload report](hot-aisle/index.html) |
| [`floor/`](floor/) | An experimental desk rating based on captured public reviews and provider surfaces, with a proposed floor, shortfall labels, suggested fixes and explicit unknowns. This is one technical investigation, not a universal definition of provider quality. | [Distance to the floor](floor/index.html) |
| [`clustermax-challenge/`](clustermax-challenge/) | A technical investigation: does the ClusterMAX medal predict the job? Two frozen retrospectives, the 3.0 binding, standing incident collection. | [Challenge](clustermax-challenge/index.html) |
| [`circulate/`](circulate/) | A manually invoked public-data cycle and its receipts. Supported sources refresh when collected; HOLD, unsupported sources and unchanged historical inputs retain their limits. No nightly schedule is installed. | [Receipts](circulate/index.html) |
| [`compute/`](compute/), [`integration/`](integration/), [`shelf/`](shelf/) | The provider-neutral decision desk, the runner that binds retained judgments to deterministic operations, and the public shelf of bounded claims. | [Compute desk](compute/index.html) |
| [`evidence/`](evidence/) | The inputs the instruments read at run time, so a clean clone needs nothing else. | |

Second Run's production and investigation work outside this campaign (media restoration and reconstruction, the SemiAnalysis network study) is retained in the estate's own records and is not in this repository.

## Observations from the compute campaign

- **The captured reviews repeatedly describe configuration and operational gaps.** The desk labels health checks (25 providers), monitoring (23), Slurm or Kubernetes (16), and shared filesystems (13). These counts describe the captured review text, mostly from November 2025; they do not establish current deficiencies or the cost of fixing them.
- **One provider is a clean zero**, Nebius, on 28 evidence items. Thirty sit at zero only because their public record is a stub, and the table says so.
- **The reference does not pass its own floor on public evidence.** Hot Aisle, whose measured performance anchors the floor, rates distance 4 on its November 2025 review record. The first prescription is the reference's.
- **The measured workload exposes large differences in cost and accepted output.** Serving below the concurrency knee swings cost 23x. Two thirds of decode tokens in the qualified run went to requests that failed grading; output sanitizing lifts total correct 42 percent. The same 4,336 accepted requests price five ways, 1.57x apart, with no invoice reconciling them.
- **The market disagrees with itself about price.** Same-SKU on-demand prices spread 3.0x to 3.6x across providers in July 2026, aggregators differ 2x on one provider's H100, and the incumbent research house's TCO priors sit below 1 percent of observed listings.
- **The medal does not yet predict the job.** Both frozen retrospectives are inconclusive and both flip with the bootstrap seed. The standing version reruns on a rolling window.

## Current capability and remaining work

The 28 September disposition is historical direction. Subsequent code implements its first bounded handoff; repeating that item as wholly unstarted loses the work already done.

| Area | Present capability | Remaining boundary |
|---|---|---|
| Retained judgment to procedure | [`from_record`](integration/WORK.md#retained-judgment-procedure-handoff) verifies a named Research Desk revision and its dependencies, invokes an existing deterministic operation, and reuses its checked result. [Native tests](integration/tests/test_task_research_handoff.py) exercise reuse and blocking after a source correction invalidates the retained judgment. | The caller supplies an exact supported binding. There is no general natural-language dispatcher, automatic renewal of judgment, or authority to perform an external action. |
| Continuing a decision | The workspace preserves sources, assumptions, reviews, prior editions and a portable packet; the Research Desk supports general source and claim records. | The focused decision page supports its declared workflows, not every valid Research Desk packet. Browser interaction is not an estate job executor. |
| Execution and reuse | [Nine deterministic task classes](integration/WORK.md) share retained computation identities. Existing interruption checks cover restart between operations. | Domain transfer and recovery during a write or external transaction need their own qualification. |
| Compute qualification | Retained runs, exact runtime evidence, price scenarios, diagnosis, supply assessment and pool arithmetic are available within their documented scopes. | Recipe applicability, preparation/residency economics, cache experiments, candidate grading and prospective timing remain separate, bounded investigations. |

The product integration to build is **an indexed observation opens its work history; the history exposes a usable next attempt; the returned attempt extends the history**. The [local collection interface](corpus/README.md) now connects that path for source normalization: discover an observation, inspect its retained projection changes, re-import its exact raw source, and extend the native research journal with the actual result. Full producer decision histories, applicable benchmark execution, and returned measurement attempts remain to be connected; normalization does not establish those capabilities.

Bulk acquisition supplies the scale. Retain associated configurations, benchmark definitions, producing commits, issues, corrections and subsequent results wherever their relationships are available. Resolve those links programmatically; use expensive investigation for consequential gaps, contradictions and outliers. Preserve what was known at the time separately from later evidence. An extraordinary result is a lead to investigate under its actual conditions; a failed replication belongs beside its predecessor with changed conditions visible. A selected calibration is not a completed run, and no replication outcome is manufactured for a demonstration.

The [community hub](compute/community/README.md) already supports independently operated collections, portable result objects and local review histories. Its [board](compute/results.html) exposes retained results. Featuring or admitting a result governs that collection's presentation; it does not grant or revoke another operator's permission to investigate. Imports preserve attribution, evidence limits and original identities without inheriting another hub's approval.

Qualification should follow real material through discovery, history, the applicable native procedure and the returned attempt. The result must distinguish reproduction of a measurement from re-importing evidence, recomputing retained outputs or reusing a checked calculation. Preserve earlier attempts, changed conditions, unresolved inputs and source rights. A recurring document/source workflow is also a useful transfer case: retain original and changed inputs, reuse unaffected work, invalidate dependent judgments, propagate withdrawal and permission changes, and continue after interruption. Domain-native outcome checks decide what each attempt establishes.

**Progress is how much of another piece of work someone can use without reconstructing its history or depending on its original author.** Dataset size, passing software checks and interface quality support that outcome; none establishes independent adoption or reproducibility by itself.

The manually run circulation loop and a second-provider rental smoke are compute-program follow-ups. Their readiness does not establish priority for the wider Cantos program. A rental requires its own current authority and useful experimental question. No schedule, rental or broader integration is implied by this roadmap.

## Running it

```sh
python -B app/source/build.py                # rebuild the workspace; gates in app/tests/
python circulate/circulate.py                # one real cycle; writes circulate/receipts/<date>/
python circulate/probes/run_probes.py        # eleven probes; exits nonzero on any FAIL
python circulate/circulate.py --offline      # the same path on fixtures, no network
python floor/rate/rate.py                    # regenerate the rating from the evidence on disk
```

Missing or gated evidence stays unknown or HOLD, and synthetic examples are labeled. Imported observations retain their producer, date and conditions. Our measurements retain their source records, while each cost states its accounting basis; list-price estimates and credit changes are not invoices. Integrity checks establish unchanged bytes, not source truth or execution authority. The public pages do not rent, provision, publish or contact providers. Funding terms are in [hot-aisle/campaign/DISCLOSURES.md](hot-aisle/campaign/DISCLOSURES.md). The instruments were extracted from the axm-tools demo shelf on 2026-09-29 with their history.
