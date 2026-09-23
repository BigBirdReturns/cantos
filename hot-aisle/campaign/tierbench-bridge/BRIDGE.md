# BRIDGE · Tier-Bench (which model tier) x Second Run fabric ledger (which seat)

Lane E, 2026-09-24 build. Nothing here asserts a result; it defines how two ledgers that measure different axes join on one Knot.

## 1. The two axes

Tier-Bench measures the **model-tier axis**: for a task class, which is the cheapest rung (model x effort) that clears a frozen,
hidden grader K times out of K (`docs/residue-broker.md`: no evidence -> cheapest rung; K/K -> seal; mixed -> collect more at the
same rung; 0/K -> next rung; a wall at the top rung is a human gate). Its unit is the **Call** (`experiments/breadth/ledger.py`),
reconciled against the provider bill ("a buffalo escaped" when the sum of calls misses the invoice).

The fabric ledger measures the **seat axis** (`../ledger/SCHEMA.md`): for one seat lease executing one Knot, what the capacity request
to release cost, how many attempts it took, what finished correctly within the gate, and how many weight traversals it took. Its unit is
the **run**, and its planner (`../ledger/waterline.py`) answers feasibility before price: fastest / cheapest / most efficient seat.

Neither answers the other's question. Tier-Bench treats hardware as free (`models.json`: local models cost 0) and knows nothing about
availability, leases or energy. The fabric ledger treats the model as given by the Knot and knows nothing about whether a cheaper model
would have sufficed. The bridge is the join:

```
task class ──(Tier-Bench receipts: K/K at the cheapest rung)──> minimal sufficient MODEL TIER
                                                                       │
                     ┌─────────────────────────────────────────────────┴───────────────────────────┐
              API / subscription tier                                                       open-weight tier
              (haiku, sonnet, luna, terra, sol ...)                                        (qwen 9B, Qwen3-Coder-30B ...)
              zero fabric seat for inference;                                              needs a seat: WATERLINE picks
              cost = provider bill per closure;                                            fastest / cheapest / most efficient
              still needs a GRADER seat (evaluator role)                                   among feasible seats, with receipts
```

`tier_waterline.py` walks this once per Knot. `import_tierbench.py` builds the evidence it reads. `RUN3-GRID.md` is the plan that
puts the open-weight tiers on the model-tier axis for the first time (today they have no Call rows at all).

### Sufficiency, as the bridge computes it

Per (task_id, model tier): decisive receipts are `pass | fail`; `error` and `partial` never decide (residue-broker). With K = 3:
K/K -> **sufficient**; pass and fail both present -> **unstable**; >= K decisive, 0 pass -> **wall**; fewer than K decisive ->
**insufficient-evidence**. The minimal sufficient tier for a task is the cheapest sufficient tier on the **ladder** (`tier-ladder.json`:
list-price proxy for 400 in + 300 out tokens, then effort; unpriced tiers last; ordering only, never a cost claim). A class's
**covering tier** is the dearest of its tasks' minimal tiers, with the undetermined tasks named.

Where `waterline.json` seals a task ("next_allowed_action: none -- sealed; do not re-derive"), the sealed tier wins and the importer's
own derivation is kept beside it as `derived_min_sufficient_tier` with `waterline_agrees`. On the full pinned ledger this matters once:
`task02_wildcard` has five `cheap`-rung verify passes, which the whole-window rule would call sufficient, while Tier-Bench sealed it above
the floor at sonnet@low after an unstable 3/5 haiku floor. The bridge reports sonnet@low and writes the disagreement.

Tier-Bench's stricter notion (rolling latest-K window, candidates decisive only after coordinator re-run) is not re-implemented; the
bridge consumes Tier-Bench's rows and seals, it does not adjudicate them.

### Evidence tags

Every imported record carries `tier`:
- `tierbench-measured`: cost basis `real-billed` (waterline.json says so for the task+model, or the row note says real-billed), or a
  route.py attempt with provider-reported tokens and an executable validator verdict.
- `tierbench-shadow-estimated`: everything else, including subagent split-estimates ("tokens=total subagent tokens split est 90/10"),
  shadow tokens with cost 0 (`cost_zero_unbilled: true`), rows with no tokens and no cost (`cost_basis: unbilled-zero`, "a logged
  blank"), and race6 subscription-derived aggregates. A priced row with no billing receipt named anywhere defaults here, never to measured.

## 2. Field mappings

### 2a. Tier-Bench Call row (`ledger.py` `Call`) -> `second-run/tierbench-call@1` -> `run-ledger@1` / `seats.json`

The run ledger is per **run**; a Call is per **trial**. The bridge does not flatten calls into a run record; it proposes a **sidecar**
`tierbench-calls.jsonl` next to each run ledger (see 2e) and maps the fields as follows.

| Call field | tierbench-call@1 | run-ledger@1 / seats.json | Note |
|---|---|---|---|
| `ts` | `ts` | `clocks.t_work_start..t_work_end` bound the calls of a run | a Call has one stamp; the run has six clocks |
| `account` | `account` | `identity.provider`, `money.payer` | Tier-Bench accounts are billing rungs (`claude-code-session-max20x`); the ledger names the provider and who paid |
| `model` | `model` | `identity.model.id` (+ `revision`, `precision`, `bytes` for open weights) | API models have no revision/bytes: null with reason |
| `tier` (`model@effort` or a rung name) | `model_tier` | not a ledger field. `identity.tier` there is the **tuning** tier (Run 3 T0/T1), a different axis | keep both; never overload |
| `task_id` | `task_id`, `task_class` (derived, section 2f) | `work.unit = task`; counts in `work.attempted/completed/correct/accepted`; per-class counts in `work.task_classes` | per-task outcomes live in the sidecar |
| `phase` | `phase` | `identity.run` + `identity.arm` | Run 3 phases would be `run3-A/T0`, `run3-N/T0`, `estate-arm` |
| `outcome` pass / fail / error / partial | `outcome`, `decisive` | pass -> `work.correct`; fail -> completed and not correct; error -> `work.lost` (transport) or completed-not-correct (grader timeout, PREREG); partial -> completed, grading hold | `accepted` additionally needs the latency gate, which Tier-Bench does not have |
| `effort` | `effort` | none (open-weight sampling is in the prereg) | |
| `input/output/cache_*_tokens` | `tokens{input, output, cache_read, cache_write, basis}` | not in run-ledger@1 ("cost per token remains a term inside this record", SYNTHESIS) | proposed sidecar field; vLLM usage gives exact counts on fabric seats |
| `cost_usd` | `cost_usd`, `cost_basis`, `cost_zero_unbilled` | API: provider bill per call. Fabric: `money.modeled_usd` (or billed) **allocated** per call = run cost / attempted, basis `allocated-from-seat-lease` | allocation is a declared rule, not a measurement |
| `latency_ms` | `latency_ms` | `work.acceptance_rule.e2e_ms` gate; `sustained.buckets` | |
| `trial` | `trial` | Run 3 cycle index (542 tasks per cycle; seed 700000 + request index) | |
| `note`, `extra.validators` | `note`, `outcome_basis` | `work.evaluator{name, frozen, ref}`; `notes[]` | Tier-Bench's validators block is the closest thing to `evaluator.ref` |
| (none) | `seat{seat_id, seat_kind, reason}` | `identity.seat_id` -> key in `seats.json` | API calls: `seat_id` null, reason "zero-seat provider cost" |
| (none) | `provenance{path, git_commit, git_head, sha256, line}` | `receipts.items[{kind, path, sha256}]` | |

### 2b. route.py receipt (`our-auto/run@1`) -> tierbench-call@1 -> run-ledger@1

One receipt is one bounded task routed through a cascade; each `attempts[i]` becomes one record.

| receipt field | tierbench-call@1 | run-ledger@1 | Note |
|---|---|---|---|
| `kind` structured / code / complex | `task_class = router-<kind>`, `route_kind` | `workload_id` | policy.json route orders define the ladder walked |
| `prompt_sha256`, `validator_sha256` | `task_id = route:<prompt12>:<validator12>`; `validator.validator_sha256` | `work.evaluator.ref` | the validator is executable but not hidden |
| `attempts[i].provider / model / effort` | `provider`, `model`, `effort`, `model_tier = model@effort` | `identity.model.id`, `runtime.engine = ollama` for local | |
| `attempts[i].call_status` + `validator.passed` | `outcome`: completed+passed -> pass; completed+failed -> fail; failed -> error; skipped -> skipped (never decisive) | `work.attempted/completed/correct` | cascade attempts are **model** attempts, not acquisition attempts |
| `prompt_eval_count / eval_count` (ollama) or `usage{input_tokens, cached_input_tokens, output_tokens}` (codex) | `tokens{...}` with the key names used in `basis` | sidecar | aliases accepted: prompt_tokens / completion_tokens / cache_read_input_tokens |
| (none) | `cost_usd` **DERIVED** = tokens x list price (`models.json`, else race6 `pricing`, cached input x `cache_discount`); local ollama = $0 provider cost with the seat cost deferred to the fabric | `money.modeled_usd` for the seat; the provider term is separate | declared in `cost_basis: DERIVED: ...`; null with reason when no tokens or no price |
| `elapsed_seconds` | `latency_ms` | | |
| `started_at_utc / completed_at_utc` | `ts` | `clocks.t_work_start / t_work_end` | |
| `gpu_probe`, `reason: gpu_busy` | `note` | `acquisition` does **not** apply: the router skips, it does not provision | a skipped local attempt is a contention event, not a failed lease |
| `run_dir`, `receipt_paths`, `selected_candidate_sha256` | `provenance` | `receipts.items` | |

route.py records no host, so a local attempt's `seat.seat_id` is null with the reason written; `local_models.json` proposes a
`resource_key` (`gpu:3090`, per `docs/residue-resource-lanes.md`) as the join key until receipts carry the host.

### 2c. `map.json` -> summary / seats.json

| map.json | bridge | seats.json |
|---|---|---|
| `tasks[t].min_sufficient_tier` | `tasks[t].map_json_min_sufficient_tier`, `map_json_agrees` (cross-check; the bridge recomputes from rows) | |
| `tasks[t].measured{tier: "3/3"}` | `tiers[tier].pass / decisive` | `priors[task_class].accept_rate`, `n`, `receipt` (proposed: per task class x seat, filled from Run 3) |
| `cost_at_min`, `cost_if_max_everywhere`, `waste_avoided` | `cost_per_trial_at_min_usd` (class level) | none (fabric has no notion of a model ceiling); the API zero-seat plan carries `usd` from it |
| `escalations`, `unjustified_escalations` | `residue[].note` when a rung was taken from an unstable floor | Knot lifecycle event `REASSIGNED` is the seat-side analogue |

### 2d. `waterline.json` -> summary / run-ledger@1

| waterline.json | bridge | run-ledger@1 |
|---|---|---|
| `settled_floor[t].cheapest_measured`, `rung`, `score` | seals `min_sufficient_tier`; derivation kept beside it | Knot lifecycle `VERIFIED -> SETTLED` |
| `cost_basis: real-billed` | `tier: tierbench-measured` | `money.billed_usd` + `billed_ref` |
| `cost_basis: shadow-estimated` | `tier: tierbench-shadow-estimated` | `money.modeled_usd` (or lower bound) |
| `judgment_residue[t].residue_name`, `floor_instability` | `residue[].residue_name`, `floor_score` | `notes[]` |
| `next_allowed_action` | honoured: sealed tasks are not re-derived | `KNOT-LIFECYCLE.md` terminal states |
| `adjudications[].classification: transport_error_not_model_failure` | outcome `error`, non-decisive | `work.lost`, never `correct = false` |

### 2e. Proposed sidecar for fabric runs (not a schema edit)

For each `run3-<arm>.ledger.json` that `../ledger/ledger_build_run3.py` writes, a bridge step can emit `tierbench-calls.jsonl` beside it:
one `tierbench-call@1` record per graded request, `task_id = evalplus:<HumanEval|Mbpp>/<n>`, `task_class = evalplus-<dataset>-plus`,
`model_tier = qwen3-coder-30b-a3b-fp8@vllm` (or the AWQ/GGUF tier on the estate), `phase = run3-<arm>/<tier>`, `trial` = cycle,
`outcome` from `grade/evaluation.json` (pass = base AND plus), `tokens` from `detailed.json` usage (exact), `latency_ms` from
`latencies[i]`, `cost_usd` = allocated share of the run's modeled cost (`allocated-from-seat-lease`), `seat.seat_id` = the run's
`identity.seat_id`, `extra{accepted, ttft_ms, run_id}`. The run ledger itself is untouched; `receipts.items` gains a `file` entry
for the sidecar. `import_tierbench.py` already classifies `evalplus:` task ids so those rows join the same summary.

### 2f. Task classes

`task_id -> task_class`: `t{N}_*` -> `tierbench-T{N}` (Tier-Bench's declared difficulty tiers); `task02_wildcard` and `replay0N_*` ->
`breadth-task02-wildcard` (the sealed residue family); other `taskNN_*` -> `breadth-numbered`; `almanac_*` -> `arc-c-almanac`;
`b2_grade_*` -> `arc-d-b2-grade`; `evalplus:<dataset>/<n>` -> `evalplus-<dataset>-plus`; route receipts -> `router-<kind>`;
race6 -> `race6-solving-ladder` (aggregate only, never expanded into fake trials). A Knot names the classes whose receipts count in
`tierbench.task_classes`; the default map `graded-coding -> tierbench-T1` is an analogy the plan prints, not a measured equivalence.

## 3. SeatIdentity (Tier-Bench fabric) <-> `seats.json` (lane B)

Tier-Bench's `tier_runner/fabric/` (commits 98e12ac / 86d05f2, **after** the 9693cb9 pin) defines:

- `SeatIdentity(seat_id, host, pci_path, device_id, subsystem_id, capabilities, execution_profile, model_residences, memory_domain,
  link, contention_domain)` with `durable_key = host:PCI:DEVICE:SUBSYSTEM`; `seats.bind_present` refuses to run on a seat whose PCI
  identity is not observed exactly once (`SEAT_BINDING_FAULT`).
- SQLite tables `seats`, `seat_leases(lease_id, job_id, seat_id, attempt_id, acquired_at, expires_at, released_at, release_reason)`,
  `attempts(attempt_id, job_id, seat_id, lease_id, state, started_at, finished_at, worker_exit)`, `telemetry_samples`, `events`, with
  `one_live_lease_per_seat` enforced by a unique index; leases expire (`LEASE_EXPIRED` -> RETRYABLE or INTERRUPTED).

| Tier-Bench SeatIdentity / store | seats.json (`second-run/seat-registry@1`) | Mapping |
|---|---|---|
| `seat_id` (host-local) | `seat_id` (estate-w01-3090 ...) | different namespaces; keep a `tierbench_seat_id` alias on estate seats |
| `host` | `cell` for estate seats; the `estate-<host>-` prefix | |
| `pci_path`, `device_id`, `subsystem_id`, `durable_key` | none (`identity_receipt` points at env.json for cloud seats; estate seats cite receipts, not a PCI binding) | **proposed** `hardware_identity{host, pci_path, device_id, subsystem_id, durable_key, bound_by}` on estate seats |
| `capabilities` | `roles` (execute / grader / probe / custody / validator) + `software.recipes` | capabilities are what a job requires; roles are what the seat is qualified for |
| `execution_profile` | `software.recipes[i]` (llama.cpp-cuda, ollama, vllm-rocm ...) | |
| `model_residences` | `traversal.curves[].{model_class, format}` (measured residences with receipts) | the fabric's residences are declared; the registry's are measured |
| `memory_domain` | `accelerator.memory_domain` | same word |
| `link` | `link.path` (resident-hbm / streamed-thunderbolt ...) + `bytes_per_second` | |
| `contention_domain` | none | **proposed** `contention_domain` = `resource_key` from `docs/residue-resource-lanes.md` (`gpu:3090`); serialises two models on one card |
| `seat_leases.acquired_at / released_at / release_reason` | `clocks.t_request .. t_released` (run ledger), `KNOT-LIFECYCLE` events PROVISIONED / RELEASED | a fabric lease is a job lease on a present seat (seconds); a ledger lease is a cloud allocation (minutes to hours). Same words, different clocks |
| `attempts` (job attempts on a seat) | `acquisition.attempts` (provisioning attempts, `layer: delivered`) | **not the same denominator**: never merge. Job attempts map to `work.restarts` / `INTERRUPTED -> REASSIGNED` events |
| `telemetry_samples` | `power.watts_mean`, `traversal.measured[]` | the fabric samples what the registry cites as receipts |
| `circuit_breakers` | `status: unavailable`, `availability.declared_busy_until` | |

**Which should be authoritative, and why (proposal; neither file is edited here).**

- `seats.json` stays the **registry of record** for planning. It alone carries what WATERLINE needs and Tier-Bench's fabric lacks:
  cloud seats and their dated list prices, setup/release overheads, availability keyed to real probes and attempts, energy, roles, and
  receipts for every measured number. Tier-Bench's fabric has no cloud notion, no price, no availability layer.
- Tier-Bench's `SeatIdentity` is **authoritative for estate hardware identity**: its durable key is bound at run time against the
  observed PCI tree and refuses on mismatch, whereas seats.json's estate entries are declarations (e.g. the unresolved OCTO-L01 3090s in
  `not_in_registry`). Runtime-bound identity should win over a declared one.
- Therefore: seats.json imports `hardware_identity` from the fabric's `SEAT_REGISTERED` events (with the event as `identity_receipt`),
  and the fabric's `contention_domain` becomes the registry's key for the resource lanes. The run ledger's `acquisition` stays the
  cloud-side denominator; the fabric's `attempts` feed `restarts` and the lifecycle's interrupt/reassign events. This keeps one planner
  (WATERLINE) and one runtime binder (fabric), each authoritative for its own kind of fact.

## 4. Provenance (entry lock)

Only two paths were read under Tier-Bench. `W` HEAD is `27fbc0cb3d810b4d53ffb7370881b9bb1c77b5c5`, eight commits past the pin
`9693cb99694338e72c15d0ffbb87b5a1c5bbf16a` (2026-07-28); the worktree files match HEAD (clean). `R` is not a git repository.

| Input | Last commit | In pin 9693cb9 | sha256 |
|---|---|---|---|
| `W/experiments/breadth/ledger.py` | `0a6ae8b` 2026-07-09 | yes | `f87eaeb4…1731a7` |
| `W/experiments/breadth/run/ledger.jsonl` (151 rows) | `da9b0a9` 2026-07-13 | yes | `4e26a795…c27c1c` |
| `W/experiments/breadth/run/map.json` | `3683f46` 2026-07-08 | yes | `50dd5d85…109a79` |
| `W/experiments/breadth/run/waterline.json` | `681e275` 2026-07-08 | yes | `9520c6f9…6ed745e` |
| `W/models.json` | `ba58efb` 2026-07-26 | yes | `9e5d29f1…996cd8` |
| `W/docs/residue-broker.md` | `ca59834` 2026-07-12 | yes | `5dc44ae9…58e9e` |
| `W/docs/burden-discipline.md` | `7abaf45` 2026-07-09 | yes | `0ae723fa…6970` |
| `W/docs/residue-resource-lanes.md` | `8ece426` 2026-07-26 | yes | `70d521d0…5f68` |
| `W/tier_runner/fabric/seats.py`, `protocol.py` | `98e12ac` 2026-08-18 | **no** (post-pin) | `496e60ac…`, `235650d4…` |
| `W/tier_runner/fabric/store.py` | `86d05f2` 2026-08-20 | **no** (post-pin) | `07f89828…` |
| `R/references/policy.json` | (no git) mtime 2026-07-25 | n/a | `f74a911e…5a7924` |
| `R/references/race6-results.operator-diagnostic.json` | (no git) mtime 2026-07-17 | n/a | `28d2fe94…875653` |
| `R/scripts/route.py` | (no git) mtime 2026-07-24 | n/a | `ce5b94e1…70e280` |

Full hashes are in `fixtures/PROVENANCE.json`; every imported record repeats its source's path, commit and sha256. No route.py run
directory was read (they live under `S:\` and `exports\`, outside the lock); the receipts in `fixtures/router/` are synthetic and say so.
