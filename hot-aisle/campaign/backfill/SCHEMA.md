# imported-observation@1

One JSON object per metric per source row. `schema` is exactly `imported-observation@1`; `tier` is always `imported`, including fixtures. `fixture` is a required boolean. Fixture status is independent of tier and must never be dropped during downstream export.

Required provenance: `source` (`inferencemax` or `mlperf`), `provenance.url`, `provenance.revision` (commit or tag), timezone-aware `provenance.retrieved_at`, lowercase 64-hex `provenance.sha256` over the original raw file bytes. `manifest_sha256` binds curator metadata; `row_index` is zero-based. `id` is SHA-256 over sorted-key JSON of the complete observation before adding `id`. Retrieval time changes create new IDs. Preserve prior records rather than merging them by model name.

Required identity fields: `hardware`, `gpus`, `model`, `model_class`, `model_revision`, `precision`, `precision_detail`, `framework`, `framework_version`, `image_digest`, `backend`, `config`, `gates`. Missing strings are `UNVERIFIED`; missing counts, class and shape numbers are null. GPU count, if present, is positive and integral. `observed_at` is nullable; never substitute retrieval time.

`workload` contains `input_tokens`, `output_tokens`, `concurrency`, `dataset`, `scenario`, `request_rate`. Fixed-length InferenceX data supplies token lengths; MLPerf variable workload dimensions stay null. Original configuration, including otherwise unsupported flags/topology, is retained in `config`. No derived traversal count or accepted-work count exists.

`metric` contains `name`, finite nonnegative `value`, and `units`. Supported mappings:

| Producer field | Normalized metric | Units / transformation |
|---|---|---|
| InferenceX `output_tput_per_gpu` | `output_throughput_per_gpu` | tokens/s/GPU; already normalized |
| InferenceX `tput_per_gpu` | `total_token_throughput_per_gpu` | tokens/s/GPU; input plus output, not output alone |
| InferenceX `request_throughput` | `request_throughput` | requests/s |
| InferenceX `p95_ttft`, `median_ttft`, `median_tpot` | corresponding names ending `_ms` | seconds × 1000 |
| MLPerf `Tokens per second`, `Completed tokens per second` | `output_throughput` | tokens/s; never silently divided by GPU count |
| MLPerf token rates marked `(inferred)` | `inferred_output_throughput` | tokens/s; not used for ratios |
| MLPerf sample rates | `sample_throughput` | samples/s; not requests/s |
| MLPerf `99.00 percentile latency (ns)` | `p99_latency_ns` | ns; not substituted for TTFT |

`data_kind` is `per-run-summary`. `warnings` is an array; optional `comparison_hold` prohibits ratio emission. No importer result is a qualified buyer receipt. See source links and boundaries in [SOURCES.md](SOURCES.md).

## Real InferenceX adapter (Fix round 1)

Both fixed-sequence (scenario_type absent) and agentic-coding list rows are accepted. Agentic token distributions remain in config.request_metrics.tokens; their means are never substituted for fixed sequence lengths. Raw nested request/server metrics and all topology/power fields remain in config. All supported latency statistics are seconds multiplied by 1000, including nested request_metrics.latency.{ttft,e2el,itl,tpot}.{mean,p50,p90,p95,p99}; p50 becomes median. Nested throughput.output.tokens_per_second maps to output_throughput; throughput.per_gpu.{output_tput_tps,total_tput_tps} maps to existing per-GPU metrics. Nested qps.mean is window_mean_qps, deliberately excluded from whole-run request-throughput ratios.

Physical GPU count precedence (gpu_count_rule records the branch):
1. Explicit num_gpus.
2. Explicit num_aggregate_gpu.
3. Explicit num_prefill_gpu + num_decode_gpu (zero decode is allowed for aggregate-mode topology).
4. Single-node, non-disaggregated TP * PP * PCP (PCP defaults to 1).
5. Otherwise null/UNVERIFIED. Never multiply overlapping EP or DCP, or infer counts from power ratios. Explicit allocation fields take precedence over topology hints.

Provenance adds artifact_id, workflow_run_id (null when absent), head_sha and created_at; sha256 remains the exact agg_bmk.json hash. revision equals head_sha for these artifacts. observed_at remains null unless an actual measurement timestamp is supplied. created_at is an artifact timestamp, not a run start. Repeated source bytes in different artifact IDs remain distinct provenance, not independent-run claims.

num_requests_total and num_requests_successful copy explicit agentic counts, or fixed-sequence benchmark_outcome.requested/completed. success_rate is successful/total; null when counts are missing or total is zero. A total=0/successful=0 row is still a failure. request_accounting and request_count_basis explain the denominator: agentic total includes warmup drops, so 1-success_rate is not an error rate. Successful/profiled does not mean correct. Failed/zero-success outcomes set comparison_hold. Unknown benchmark_outcome status also holds; passed status permits contextual comparison under all existing compatibility checks. Every available successful count emits successful_requests (requests), retaining failures even without performance metrics. That metric is not ratio-compatible.

Top-level avg_power_w, avg_total_gpu_power_w, total_gpu_energy_j, joules_per_successful_query and joules_per_output_token are copied without conversion; missing values are null. power_valid and power_invalid_reasons are retained. avg_power_w is the producer's per-GPU average, not assumed whole-system draw. Only power_valid=1 values enter summary energy ranges; invalid readings remain inspectable in the observation. No facility/CPU energy or traversal efficiency is inferred.

An empty aggregate list emits no metric observations and remains hash-bound in the manifest and named in the import summary. A nonempty row without either supported metrics or request counts fails loudly. IDs still bind the complete expanded metric observation. Source-row counts deduplicate only expansion by (artifact_id, sha256, row_index), never by hardware/model.
