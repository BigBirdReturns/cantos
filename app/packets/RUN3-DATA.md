# Run 3 per-request data (hands/run3data)

Result: the per-request records exist and reconcile exactly. 8,622 sent per arm; correct 4,371 (A/T0) and 4,329 (N/T0); accepted 4,336 and 4,280. Nothing fabricated. A/T1 also done as a bonus (accepted 4,292, correct 4,334, 7 failed; matches RUN3-RESULTS.md).

Files here: `run3-requests-a-t0.json`, `run3-requests-n-t0.json`, `run3-requests-a-t1.json` (bonus), `build.py` (reproduces all three; read-only on the campaign tree). Each JSON is a compact list in arrival order (request_index 0..8621; `scheduled_at_ms` non-decreasing, verified).

R = `D:/Projects/Organs/AXM/axm-tools/main/hot-aisle/campaign/results/run3-scored-<arm>/` with arm in `a-t0`, `n-t0`, `a-t1`.

## File layout (per arm, under R)
- `replay/requests.jsonl`: 8,622 lines, one record per request (11 MB). THE per-request source. Read as UTF-8 (output_text contains bytes cp1252 cannot decode).
- `replay/plan.json`: frozen schedule: `start_ts`, `duration_s` 3600, `rate_factor` 0.95, `request_timeout_s` 60, `max_tokens` 1024, `temperature`, `tasks_sha256`, `trace_sha256`, and `requests[]` = {request_index, scheduled_ts, seed, task_id}.
- `replay/journal.jsonl`: dispatch / sent events with `send_ts` (2 lines per request).
- `replay/replay-status.json`: `{end_ts, interrupted:false}`.
- `grade/evaluation.json`: `passed` = list of 8,622 booleans indexed by request_index (EvalPlus 0.3.1 base AND plus pass); also criterion_id, source_sha256 (of detailed.json), mapping_sha256. Schema `hot-aisle/request-evaluation@1`.
- `grade/buckets.json`, `replay/buckets.json`: 300 s bucket tallies (attempted/completed/failed/correct/accepted).
- `detailed.json`: benchmark-shaped arrays, one entry per request (`ttfts`, `latencies`, `queue_times` in seconds; `input_lens`, `output_lens`, `errors`), plus `completed`, `failed`, `duration`. Server/benchmark-side; not measured from scheduled arrival.
- `ledger/run3-run3-scored-<arm>.ledger.json`, `ledger-times.json`, `closure.json`, `tasks.json` (frozen tasks), `serve.log`, `env.json`, etc.: identity and money, see below.

## One record in replay/requests.jsonl (A/T0 request 0; output_text elided)
`end_ts` 1790210715.192183, `error` "", `finish_reason` "stop", `first_token_ts` 1790210712.4132895, `input_tokens` 118, `output_text` "...", `output_tokens` 400, `request_index` 0, `scheduled_ts` 1790210712.216173, `seed` 700000, `send_ts` 1790210712.2199106, `task_id` "HumanEval/0".
- `*_ts` are Unix epoch seconds (float, client clock). `scheduled_ts` = plan start_ts + trace offset; `send_ts` = actual send; `first_token_ts` = first non-empty streamed piece; `end_ts` = completion (or failure time). `error` is "" when completed; failed rows have a nonempty error and may have null first_token_ts / end_ts. `seed` = 700000 + request_index. `task_id` = EvalPlus task (HumanEval/n or Mbpp/n), cycled over 542 tasks.

## Acceptance definition (registered; run3/grade.py lines 121-124 and run3/replay.py lines 201-204)
`passed[request_index] and not error and first_token_ts - scheduled_ts <= 1 and end_ts - scheduled_ts <= 60` (seconds). Both latencies run from scheduled arrival on the client clock, not from send.

## Output JSON fields and provenance
| field | value | provenance (file, field) |
|---|---|---|
| id | integer request_index 0..8621 | R/replay/requests.jsonl `request_index` (same as R/replay/plan.json requests[].request_index) |
| scheduled_at_ms | (scheduled_ts - plan.start_ts) x 1000, rounded 0.1 ms | R/replay/requests.jsonl `scheduled_ts`; R/replay/plan.json `start_ts` (A/T0 1790210712.1825309; N/T0 1790223376.7728634; A/T1 1790214547.4329956). Relative to each arm's own start; max 3,599,441.1 ms in both arms (same schedule). |
| first_token_ms | (first_token_ts - scheduled_ts) x 1000, rounded 0.1 ms; null if no first token | R/replay/requests.jsonl `first_token_ts`, `scheduled_ts` |
| elapsed_ms | (end_ts - scheduled_ts) x 1000, rounded 0.1 ms; null if none | R/replay/requests.jsonl `end_ts`, `scheduled_ts` |
| correct | boolean, EvalPlus base+plus pass (raw, registered grading) | R/grade/evaluation.json `passed[request_index]` |
| accepted | correct AND no error AND first_token_ms <= 1000 AND elapsed_ms <= 60000; computed on unrounded floats | derived from the fields above plus R/replay/requests.jsonl `error` |
| task_id (extra) | EvalPlus task, for traceability; droppable | R/replay/requests.jsonl `task_id` |

Contract clause 2 wants `{id, scheduled_at_ms, attempts:[{status, first_token_ms, elapsed_ms, correct}]}`. `status` maps from `error` (all "" in A/T0 and N/T0, so uniformly completed; not carried in the JSON). Recomputing accepted from the rounded JSON values gives the same counts.

## Counts and reconciliation (build.py, from the files above)
| | A/T0 | N/T0 | A/T1 (extra) |
|---|---|---|---|
| sent (records) | 8,622 | 8,622 | 8,622 |
| errors / failed | 0 | 0 | 7 (8,615 completed) |
| correct | 4,371 | 4,329 | 4,334 |
| accepted | 4,336 | 4,280 | 4,292 |
| RUN3-RESULTS.md (completed / correct / accepted) | 8,622 / 4,371 / 4,336 | 8,622 / 4,329 / 4,280 | 8,615 / 4,334 / 4,292 |
| result | exact | exact | exact |

No discrepancy. Composition: A/T0 has 4,251 incorrect; of 4,371 correct, 35 miss the 1 s first-token limit, 0 miss the 60 s limit, 4,336 accepted. N/T0 has 4,293 incorrect; of 4,329 correct, 49 miss first token, 0 miss 60 s, 4,280 accepted. Requests with first token > 1 s regardless of correctness: 76 (A/T0), 116 (N/T0). The 60 s limit never binds on correct answers.

## Latency percentiles: two definitions, do not mix
- RUN3-RESULTS.md TTFT p50/p95/p99 (A/T0 53 / 155 / 571 ms; N/T0 35 / 76 / 2,254 ms) matches the benchmark-side `detailed.json` `ttfts` (from send; numpy check: A 53/155/569, N 35/76/2,234; tail digits differ by interpolation method).
- The JSON's `first_token_ms` is from scheduled arrival (the acceptance clock). Nearest-rank over the JSON: A/T0 56 / 171 / 575 ms; N/T0 35 / 78 / 2,255 ms. Cantos cards must say which one they show; the report's figures are the `detailed.json` ones.

## Money (not per-request; for the run records)
- List rates: A/T0 $2.99/h, N/T0 $4.41/h (ledger `money.list_rate_per_gpu_hr`; RUN3-RESULTS.md).
- N/T0 window 69.82 min ("t_request -> t_released from closure.json", ledger `money.modeled_minutes`). 4.41 x 69.82/60 = $5.1315; / 4,280 = $1.199 per 1k, matches $1.20 (ledger `derived.usd_per_1k_accepted` 1.1989, cost_basis "modeled").
- A/T0 window 64.7 min ("own-seat equivalent") appears ONLY in RUN3-RESULTS.md and results/receipt-run3.html line 105. It is NOT in the A/T0 ledger: there `money.modeled_minutes` is null, `t_request`/`t_released` are null (closure.json: shared seat), and only a lower bound of 94.37 min ($4.7026) exists, giving `derived.usd_per_1k_accepted` 1.0845 (cost_basis "modeled-lower-bound"). Check: 2.99 x 64.7/60 / 4,336 = $0.7435, matches $0.74. So 64.7 min is imported from the report/receipt, not recomputable from the retained A/T0 ledger; stamp it that way. I did not find where 64.7 was derived (RUN3-RESULTS.md caveats say provisioning latency plus arm window).
- Flip check: 4.41 x 0.74/1.20 = $2.72/h; at $2.49, N/T0 = 2.49 x 69.82/60 / 4,280 = $0.677 ($0.68), below A/T0 $0.74.

## Size
About 1.17 MB per arm JSON; two arms about 2.3 MB, well under the 12 MB packet limit.
