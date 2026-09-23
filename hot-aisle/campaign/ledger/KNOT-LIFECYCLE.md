# Knot lifecycle · states, transitions, event log

Implemented in `knot_lifecycle.py` (stdlib). A Knot is one bounded unit of contracted work (CAIRN v0.3 §8): a task batch with a model class, memory need, traversal profile, deadline, evaluator and payer. The ledger's state machine follows it; CAIRN's Genesis/PLOT/APERTURE/Spectra machinery stays out (SYNTHESIS "Hold").

## States

| State | Meaning | Required event data |
|---|---|---|
| `ISSUED` | Knot spec frozen and offered | `spec` |
| `QUOTED` | a seat quoted a price/window (optional step) | |
| `RESERVED` | capacity requested; **this is `t_request`** and counts as one acquisition attempt | |
| `PROVISIONED` | seat reached ssh / engine health | `seat_id`, `t_ssh_or_ready` |
| `RUNNING` | first recorded unit of work started | `t_work_start` |
| `DELIVERED` | seat says the work finished | `attempted`, `completed`, `t_work_end` |
| `KNOT_VERIFIED` | the frozen evaluator ran (on a grader seat) | `evaluator`, `correct`, `accepted` |
| `SETTLED` | money or energy reconciled | `settlement{authority: invoice\|credit\|energy\|none, ref, usd}` |
| `RELEASED` | provider confirmed the seat is gone; billing stops. **`t_released`** | `t_released` |
| `PROVISIONING_FAILED` | create/provision did not reach ssh (out of capacity, limit 0, create failed) | `reason` |
| `INTERRUPTED` | seat lost or deliberately stopped mid-work | `reason`, `unfinished_ids` |
| `REASSIGNED` | unfinished ids handed to a new Knot on another seat; the original seat still settles its partial work and releases | `to_knot_id`, `unfinished_ids` |
| `DELIVERY_REJECTED` | delivered bytes fail the receipt check (manifest, identity) | |
| `VERIFICATION_FAILED` | evaluator ran and the acceptance predicate failed | `evaluator`, `reason` |
| `EXPIRED` | no seat within the Knot's deadline (terminal) | `reason` |
| `CANCELLED` | withdrawn by the operator (terminal after RELEASED) | `reason` |

Terminal: `RELEASED`, `EXPIRED`. `REASSIGNED` and `CANCELLED` are not terminal: the seat keeps billing until the provider confirms release, so `REASSIGNED → SETTLED → RELEASED` (or `REASSIGNED → RELEASED`) records the original seat's final clock. `append` verifies the whole chain before writing; a broken log is never extended.

## Allowed transitions

```
BIRTH               -> ISSUED
ISSUED              -> QUOTED | RESERVED | PROVISIONED | EXPIRED | CANCELLED
QUOTED              -> RESERVED | PROVISIONED | EXPIRED | CANCELLED
RESERVED            -> PROVISIONED | PROVISIONING_FAILED | EXPIRED | CANCELLED
PROVISIONED         -> RUNNING | PROVISIONING_FAILED | INTERRUPTED | CANCELLED | RELEASED
PROVISIONING_FAILED -> ISSUED | RESERVED | CANCELLED | RELEASED      (ISSUED/RESERVED = retry = a new attempt)
RUNNING             -> DELIVERED | INTERRUPTED | CANCELLED
INTERRUPTED         -> RUNNING | REASSIGNED | CANCELLED
DELIVERED           -> KNOT_VERIFIED | VERIFICATION_FAILED | DELIVERY_REJECTED | SETTLED*
DELIVERY_REJECTED   -> RUNNING | CANCELLED
VERIFICATION_FAILED -> RUNNING | DELIVERED | CANCELLED
KNOT_VERIFIED       -> SETTLED | RELEASED
SETTLED             -> RELEASED
REASSIGNED          -> SETTLED | RELEASED
CANCELLED           -> RELEASED
```
`*` `DELIVERED -> SETTLED` skips verification and is allowed only with `data.verifier == "none"` (Run 1 style: no evaluator existed). A `SETTLED` event with `authority: none` must carry `usd: 0` or none; it must not pretend money moved (CAIRN dry-run rule).

Self-serve seats (Hot Aisle TUI, DigitalOcean console) go `ISSUED -> PROVISIONED` directly when no reservation step exists; the acquisition attempt is then logged in the ledger's `acquisition.attempts`, not as a `RESERVED` event.

## Event log format

JSONL, append-only, hash-chained. One line:

```json
{"seq": 3, "ts": "2026-09-24T18:02:11Z", "knot_id": "knot-…", "event": "PROVISIONED->RUNNING",
 "from": "PROVISIONED", "to": "RUNNING", "actor": "operator|runner|waterline",
 "seat_id": "do-h100-nyc2", "data": {"t_work_start": "2026-09-24T18:02:11Z"},
 "prev": "<sha256 of previous line>", "hash": "<sha256 of this line without hash>"}
```

- `seq` is contiguous from 0; `prev` of line 0 is 64 zeros.
- `hash` = SHA-256 of the canonical JSON (sorted keys, no spaces) of the line without `hash`.
- `verify` replays the file: sequence, chain, recorded `from` against the replayed state, and every transition against the table and its required data. Editing any line breaks the chain from that line on.
- One file may hold many Knots (the campaign's `events.jsonl`); `state` lists each Knot's current state.

## Mapping to the ledger

| Ledger clock | Event |
|---|---|
| `t_request` | `RESERVED` (or the attempt line for self-serve seats) |
| `t_ssh` / `t_ready` | `PROVISIONED.data.t_ssh_or_ready` |
| `t_work_start` | `RUNNING` |
| `t_work_end` | `DELIVERED` |
| `t_released` | `RELEASED` |

`ledger_build_run1.py` writes a **reconstructed** event log per Run 1 arm (`examples/run1-<arm>.events.jsonl`, `data.reconstructed: true`) so the worked example exercises the same machine; those are not contemporaneous records.
