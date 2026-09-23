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
