# Shared operations, retained for the next request

The floor improves by class, not by user. `work.py` supplies one execution and
reuse path for five existing deterministic operations. A different operator or
provider does not require another implementation. The source owners still decide
what the evidence supports.

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
| `source-correction` | Research Desk event and dependency machinery | The shipped synthetic worked-history packet receives an explicitly illustrative correction. Its successor makes affected work stale and preserves historical reports. No human review or standing is granted. |
| `record-change` | Workload runner revalidation | The shipped synthetic workload record gets a price scenario. The owner recalculates economics, leaves performance intact and requires no execution. |

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

The existing record-change owner also accepts `gates`, `requirements`, `traffic`,
`runtime` and `evaluator` changes. Its result distinguishes recalculation,
reassessment of retained outputs and a minimal new execution plan. This runner
returns that plan; execution and authorization remain with the workload runner.
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

Results and invocation receipts are append-only. A damaged cache entry is held
with a reason; it is not silently repaired or overwritten. Missing evidence,
unsupported task classes, misspelled change fields and disagreements between a
retained grading mask and its underlying results hold that task. Other independent
tasks continue. Use a new store to recompute after investigating damaged cache
data; the original remains available for inspection.

An `executed` task can still contain native unresolved fields or applicability
holds. That status means the procedure ran, not that its conclusions were accepted.

## Qualification

```powershell
python -B -m unittest discover -s integration/tests -p "test_task_*.py" -v
python -B -m unittest discover -s integration/tests -p "test_work.py" -v
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
