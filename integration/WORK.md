# Shared operations, retained for the next request

The floor improves by class, not by user. `work.py` supplies one execution and
reuse path for nine existing deterministic operations. A different operator or
provider does not require another implementation. The source owners still decide
what the evidence supports.

## Start from the local record

```powershell
python -B integration/work.py --catalog
```

This prints the task classes, required artifact shapes, adapter coordinates and
execution command. A new process needs the request file and result-store address;
it does not need the earlier conversation. `tasks[].result` in each run receipt
points to the native output. Inspect its limits and unresolved work as well as the
outer `executed` or `reused` status.

On this estate, ongoing results are retained under the project home at
`../sessions/shared-work/`, outside the published checkout. Qualification uses
`S:/Scratch/Runs/` or `S:/Scratch/Temp/`. Scratch qualification is not durable
operating custody. A store is explicitly selected on each invocation; another
operator can keep the same format under their own custody.

From the repository root on this estate:

```powershell
python -B integration/work.py --request integration/examples/work.json --store S:/Scratch/Runs/shared-work
```

Run it again with the same store. On an empty store, the shipped example executes
six tasks. The second request reuses six checked results. Each invocation prints
its per-task status and writes a new run receipt. Result files contain the native
outputs, dependency hashes and semantic parameters; source files are read only.
Local qualification used Python 3.13.15 and Node 24.19.0. The existing CI is
configured for Python 3.12 and Node 22; a remote run remains pending. Other
operators can use an appropriate writable result directory on their own machines.

| Task class | Existing owner | Example and retained boundary |
|---|---|---|
| `provider-intake` | Campaign provider staging and target arithmetic | Two staged offers through the same adapter. Quotation, unit, retrieval date and unresolved fields survive. A modeled target is conditional on retained performance, not a provider measurement or verified rental. |
| `benchmark-import` | Campaign offline backfill importer | Five committed InferenceX fixtures: six source rows, 80 observations. Native IDs, provenance and fixture flags survive. Importing does not repeat a benchmark. |
| `run-recompute` | Run 3 recovery, grader join and deadline buckets | Retained A/T0 replay: 8,622 scheduled, 8,622 completed, 4,336 accepted. This rejoins retained EvalPlus results and recomputes acceptance; it does not execute EvalPlus or rent a GPU. |
| `run-diagnose` | Run 3 recovery, grader join and shelf consistency checks, plus static inspection | Same retained arm: the owner's recomputation runs first, then correct-but-late requests are partitioned into dispatch (`send_ts - scheduled_ts`), send-to-first (`first_token_ts - send_ts`), both and combined segments against the same one-second rule, and every delivered solution is classified as correct, syntax-valid but grade-failing, syntax-invalid, or a never-sent placeholder, by dataset and `ast` error family. Nothing generated is executed, sanitized or repaired. Categories are observations of retained bytes, not proof of repairability or of a provider, GPU or client cause. |
| `output-contract` | Retained Run 3 input and native grading layout | Selects candidate substrings for syntax-invalid responses, preserves raw output and baseline grading, and emits separately materializable grader input. Parsing is not correctness; no generated code is executed and no new accepted count is asserted. |
| `source-correction` | Research Desk event and dependency machinery | The shipped synthetic worked-history packet receives an explicitly illustrative correction. Its successor makes affected work stale and preserves historical reports. No human review or standing is granted. |
| `record-change` | Workload runner revalidation | The shipped synthetic workload record gets a price scenario. The owner recalculates economics, leaves performance intact and requires no execution. |
| `tier-plan` | Campaign Tier-Bench bridge and WATERLINE | A supplied Knot plus native evidence summary and ladder produce model/seat plans with source bases, wall clock, costs and missing measurements retained. This is a planning computation, not new model capability evidence or execution authority. |
| `pool-purchase` | Provider staging pool owner (`hot-aisle/campaign/providers/pool.py`) | `examples/pool.json`: five illustrative members against the staged offers. Whole-unit packing (each unit billed until its last member ends, or its stated minimum), a per-unit schedule, exact-decimal charges rounded per unit to cents and split by GPU-hours with largest-remainder cents that sum exactly to the bill, per-member standalone comparison against both the cheapest listed offer and the cheapest offer with no hold, coalition and break-even utilization. Holds on the pool offer and on each reference travel into a labelled conclusion. List-price arithmetic; not a quote, availability check or co-op agreement; `bindable_at_list` and `execution_authority` stay false. |

To diagnose the committed retained arm instead of only recomputing it:

```powershell
python -B integration/work.py --request integration/examples/diagnose.json --store S:/Scratch/Runs/shared-work
```

Point the same request shape at any other retained arm directory, from any provider,
to obtain the same partition and classes with the same stated limits. The diagnosis of
Hot Aisle baseline 1 (4,274 accepted) reproduced N01's retained figures exactly: 71 late
= 42 send-to-first only, 9 dispatch only, 1 both, 19 combined; 2,437 syntax-invalid and
1,836 syntax-valid grade failures; four never-sent MBPP placeholders excluded from parsing.

The larger local archive has a separate request:

```powershell
python -B integration/work.py --request integration/examples/archive-local.json --store S:/Scratch/Runs/shared-work
```

That request requires the already-retained `backfill/data-raw` archive, which is
excluded from Git. The local verification processed 100 artifacts, 198 source
rows and 3,620 observations. A clean checkout uses the smaller committed example;
the runner never fetches the missing archive automatically.

## Change an input, preserve what still holds

Tasks use `id`, `task_class` and `source`; source paths are relative to the request
file, or absolute. An optional `actor` labels the request in its execution receipt.
It is descriptive metadata, not authenticated identity or institutional standing.
Changing the task ID, actor or file location while retaining identical bytes does
not change the computation key.

To exercise economic reuse, add this field to the first provider task:

```json
"price_scenario": {"rate_usd_per_gpu_hour": 2.0}
```

With the initial six results retained, this executes one changed calculation and
reuses the other five, including the unchanged 4,336 accepted count. The original
quoted rate, native provider row and previous result file remain intact. Omitting
`offer_id` files the whole supplied staging file; it does not qualify availability.

For a reproducible supply check, add `"availability_review":
{"as_of":"2026-09-27T00:00:00Z","max_age_hours":24}` to a provider-intake task.
The timestamp and caller-selected window enter the computation key. A dated
`available` observation outside that window, an unavailable observation or an
unknown observation produces a placement hold; the conditional price target
remains visible. Without an explicit review, availability age is not assessed
and placement is held. Even an observation within the window is only a listing
snapshot: `rentable_now` remains false until a current offer, account access,
full billing and successful provisioning are checked. The runner does not fetch
a new quote or infer a universal freshness window.

To ingest an explicitly collected Vast.ai Search Offers response, retain its raw
JSON body as a local file and supply that file as `source`. Add
`"marketplace_snapshot": {"source_url":"https://console.vast.ai/api/v0/bundles",
"captured_at":"<timezone-aware capture timestamp>",
"evidence_class":"official_api_response"}`. The separate collection step uses
Vast's documented authenticated POST; `work.py` never contacts the marketplace.
The adapter accepts the documented `offers` array (or the documentation's
single-object example), preserves the raw snapshot hash and exact provider offer
ID, and maps `search.gpuCostPerHour` as USD compute per offer-hour divided by
`num_gpus`. It keeps `storage_cost` in USD/GB/month and the separate bandwidth
USD/TB fields; `search.totalHour` is retained as advertised metadata, not a
qualified bill. Capture time is caller-declared and does not prove a provider
quote or account access. A listing always carries a placement hold and
`rentable_now: false`, including an apparently fresh available listing.

For parser qualification, the official [Search Offers response example](https://docs.vast.ai/api-reference/search/search-offers)
can use `evidence_class: "official_documentation_sample"` with that page as
`source_url`. Its fictional machine, price and advertised availability remain a
sample: availability is unobserved and no modeled target is produced. Neither
source class is an obtained rental or a reservation. The API's Authorization
header is mandatory; the sample cannot substitute for a live response.

The existing record-change owner also accepts `gates`, `requirements`, `traffic`,
`runtime` and `evaluator` changes. Its result distinguishes recalculation,
reassessment of retained outputs and a minimal new execution plan. This runner
returns that plan; execution and authorization remain with the workload runner.
When a change requires execution, the proposed native job now retains simultaneous
price, gate and acceptance-requirement changes, including a requested quality gate.
It contains only the requested cells and clears a historical primary cell when
that cell is absent from the proposed rerun.
Source corrections use a record ID and a bounded patch through Research Desk.
Their event actor identifies this deterministic procedure; the separate run
receipt records the caller label. Reusing a calculation does not create a second
review, author or correction event.

## Why a result may be reused

The key includes task class, semantic arguments, Python/Node runtime versions and
the bytes of every declared input and native procedure, including this runner.
Missing optional retrieval sidecars have an explicit identity; adding one changes
the key. Fresh worker processes load source rather than old bytecode and check
dependencies before and after execution. A cache hit verifies the retained
result checksum and rechecks the current dependencies.

Hash equality identifies the same declared computation. It does not authenticate
the producer, establish source truth, renew an observation date or grant Canon
standing. Reuse is deliberately conservative: changing an unrelated row in a
shared provider file invalidates that file's operations too. This implementation
does not claim field-level dependency precision for every source format.

Byte identity also includes text serialization. The local verification records two
existing CRLF inputs whose Git blobs use LF. Both hashes are retained in its report;
a differently serialized checkout recalculates those operations instead of reusing
the old result. Neither the input files nor the earlier results were rewritten.

Results and invocation receipts are append-only. A damaged cache entry is held
with a reason; it is not silently repaired or overwritten. Missing evidence,
unsupported task classes, misspelled change fields and disagreements between a
retained grading mask and its underlying results hold that task. Other independent
tasks continue. Use a new store to recompute after investigating damaged cache
data; the original remains available for inspection.

An `executed` task can still contain native unresolved fields or applicability
holds. That status means the procedure ran, not that its conclusions were accepted.

## Bring model and seat evidence into the same reuse path

A `tier-plan` task names a retained Knot JSON and a directory produced by the
existing `hot-aisle/campaign/tierbench-bridge/import_tierbench.py`:

```json
{
  "tasks": [{
    "id": "next-estate-plan",
    "task_class": "tier-plan",
    "source": "knot.json",
    "evidence": "tier-evidence"
  }]
}
```

`tier-evidence` must contain native `tierbench-summary.json` and
`tier-ladder.json`. Optional `seats`, `availability` and `local_models` paths
replace the native owners' defaults. Every supplied file and both planners enter
the computation identity. Changing one of those inputs recalculates that plan;
it does not invalidate an independent retained-run recomputation. Missing files
hold the task, and identical evidence copied to a new location can be reused.

The adapter calls the native planner and retains its entire result. The native
`chosen_tier` is an evidence-based model candidate; even `chosen_mode: full`
does not mean its projected wall time meets the deadline. The retained Run 3
example uses a declared analogy to one historical T1 task: its API projection
takes 21,570.5 seconds against a 5,400-second deadline at concurrency one. The
open-weight tier remains unmeasured. These are useful remaining measurement and
placement questions, not an authorized route.

The native result now also contains `plan.placement` and a placement verdict on
each grid row. These join full model-evidence coverage to projected deadline,
budget and evaluator-role constraints. Read `plan.placement.chosen_tier` for the
lowest ladder-ranked modeled-feasible candidate; it may be null while the
historical evidence-only `chosen_tier` remains populated. Unknown cost/time,
partial class coverage and unmeasured fabric timing remain unresolved. Native
refusals and cost bases survive. An API concurrency scenario can change the
projected verdict but does not measure parallel throughput or grant execution
authority. The bridge's `--require-placement` CLI flag supplies a nonzero exit
when a modeled placement is required and none exists. Shared work status still
means the deterministic computation ran, not that placement passed.

`TIER-VERIFICATION.json` records this join using 52 retained Tier-Bench call rows
and nine operator-diagnostic aggregates, excluding synthetic route receipts.
It also records cold execution, reuse by another caller and a changed seat-price
scenario beside the untouched 4,336 accepted requests. Dates and evidence bases
remain historical; this does not run rolling frontier tests or refresh offers.

Live Tier-Bench intake must resolve its current authority before use. During this
join, the resolver's pinned commit and checkout HEAD differed. The already-retained
excerpts remain usable as historical inputs; this adapter does not silently select
another checkout or reclassify those excerpts as current measurements.

## Optional supply-to-placement join

`tier-plan` accepts `supply` with a retained provider JSONL `source`, optional
native `availability_review`, and exact `bindings` keyed by seat ID:

```json
"supply": {
  "source": "live-hotaisle.jsonl",
  "availability_review": {"as_of": "2026-09-27T00:00:00Z", "max_age_hours": 24},
  "bindings": {
    "hotaisle-mi300x-1x-enc1": {
      "provider_id": "hotaisle", "offer_id": "hotaisle-mi300x-1",
      "seat_sku": "vm-mi300x-1x", "seat_gpu": "AMD Instinct MI300X VF",
      "offer_gpu": "MI300X"
    }
  }
}
```

The adapter executes the existing offline provider-intake operation, retaining its
full output and declaring its code, source and reference dependencies. The native
tier owner checks exact IDs, explicit SKU/GPU labels, provider, GPU count, region
and price agreement. Bindings declare correspondence; they do not authenticate
hardware identity. Unknown IDs or mismatches remain held. No matching by display
name or automatic GPU-name normalization occurs.

`plan.supply.seat_reviews` carries native availability reviews and holds. Each grid
row's `supply_eligibility` evaluates the same cheapest-or-fastest candidate used by
modeled placement. `listing_eligible` means only that the declared correspondence,
price and native intake checks pass at the explicit review time.
`modeled_and_listing_eligible` additionally requires modeled feasibility. API,
subscription and unmapped seats remain unassessed by this GPU-offer join. No
alternative seat is selected. Existing `placement` facts and arithmetic are intact.

Even a passing listing leaves `ready`, `reserved` and `execution_authorized` false.
Account access, provisioning, complete billing terms and evaluator readiness are
not established. Without `supply`, existing output is unchanged. Changing source
bytes, review time/window or bindings invalidates this task's reuse; identical
relocated bytes reuse the result. Reuse never fetches or renews an observation.

## Qualification

```powershell
python -B -m unittest discover -s integration/tests -p "test_task_*.py" -v
python -B -m unittest discover -s integration/tests -p "test_work.py" -v
python -B -m unittest discover -s integration/tests -p "test_task_diagnose.py" -v
```

The tests cover cross-operator reuse, relocated evidence, selective price changes,
new retrieval receipts, corrupt caches, missing evidence, inconsistent grading,
native runtime/evaluator revalidation and preserved correction history. They
exercise actual owners, with mutations confined to disposable copies.

The workload owner's unsupported-change no-op was also fixed: an unknown change
now refuses instead of returning an empty set of conclusions. Generated desk and
browser projections carry the same fix.

`WORK-VERIFICATION.json` records the concrete local handoff. Its real retained
evidence and synthetic change examples are identified separately. These operations
make no model calls and run no new GPU work. That establishes reuse of these
deterministic procedures; it does not qualify general task decomposition, batching,
warm placement, unattended provisioning or cross-domain adoption.


## Four-lane local integration, 27 September 2026

The shared catalog now includes run-diagnose and pool-purchase, plus explicit
provider availability review and buyer placement constraints. Original source
owners and evidence classes remain unchanged. Pooling is staged-price arithmetic;
arithmetic_no_worse describes the modeled member comparison only. bindable_at_list
remains false even for an apparently available source row: current supply,
account eligibility, full billing terms, a reservation and purchase authority are
not established by this operation. Historical and synthetic examples remain so.
This integration is a local candidate; it activates no execution or publication.

## Second four-lane integration

The output-contract candidate has a separate task and materializer:
`python -B integration/work.py --request integration/examples/contract.json --store <store>`.
`python -B integration/task_contract.py materialize <result.json> <arm> <new-directory>`
retains source mapping and candidate lineage in the existing grader-input layout. It
performs no grading; original acceptance and deadlines remain unchanged. Some retained
candidates are partial or comment-only, so syntax improvement never means useful completion.

Provider intake also accepts explicit retained Vast Search Offers snapshots. Collection
is separate and the documentation sample remains fictional: no available capacity or
modeled price target follows from it. A tier-plan supply argument can pass the same
marketplace_snapshot descriptor to that native intake; it preserves every hold and
requires explicit seat/offer bindings before any listing-eligibility conclusion.

Pool charges now release each modeled unit at its own last completion, reconcile integer
cents across member shares, and preserve standalone-reference qualifications. Per-unit
rounding differences are reported separately from usage and idle charges. Status words
in pool conclusions concern arithmetic qualifications, never verified capacity or approval.
This remains a locally qualified candidate, without production activation or a rental.

## Controller reconciliation, 28 September 2026 UTC

Two local Round 2 candidates carried complementary controller repairs. The current r2-integration preserves per-unit rounding separately from idle cost and also inherits the earlier candidate-export checksum/dependency checks and conditional/modeled_no_worse labels. Both original candidate refs and their observations remain historical. Export verifies the current computation before writing grader input; candidate parsing remains distinct from correctness and deadlines.

## Supply qualification shared by intake, pooling and placement

`pool-purchase` now consumes its `offers` through the existing provider-intake operation. Optional `availability_review` and `marketplace_snapshot` arguments have exactly the intake semantics above. All native source dependencies and review parameters enter the pool computation key. Supply holds bind to exact unique offer IDs and reach both pooled-offer and standalone-reference comparisons. `standalone_unqualified` means no holds under this declared review, not authenticated or reserved supply. The direct `pool.py` CLI remains a list-arithmetic interface without intake review; use `work.py` for the joined path.

Malformed, absent or future availability timestamps are per-offer `invalid_observation` holds retaining the original row and exact error. A defect in one availability observation no longer stops inspection of other offers. Request-time syntax, monetary units, duplicate identities and structural validation remain strict. These changes neither move a future date into the present nor infer that a timestamp denotes a forward reservation. Fictional documentation snapshots remain inspectable in the intake and are excluded from pool price arithmetic.

Qualification exercised the complete retained catalog and a linked five-task request: intake, pool, placement, independent benchmark import, and the new 4,274-accepted baseline recomputation. A fresh process reused all five. Explicitly synthetic availability and price interventions changed the same source for intake/pool/placement, recalculated those three tasks and reused the two independent results. All three consumers returned identical native intake values. Availability changed listing eligibility; changing the offer price changed the standalone comparison and caused the planner to demand explicit repricing, preserving its original model arithmetic. No reservation or performance improvement followed from either intervention.

Native regression: `python -B integration/tests/test_task_pool_supply.py -v`. Retained request files and controller assertions live in the project session's `continuation-20260928/pool-supply/linked-verification/`. Use a separate store for a new cold run. This is local software qualification over historical material and labeled scenarios, with zero inference, purchase or deployment.
