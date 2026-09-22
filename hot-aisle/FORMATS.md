# Input formats and evidence boundaries

## vLLM inputs

The parser supports the flat serving-result layout in `vllm/benchmarks/serve.py`, inspected at upstream commit `4edb55169f69c76bb87ab9f154585917cb01bb17` (source blob `14c72386a5d01c1163c99497890004c43ac09338`). Source: https://github.com/vllm-project/vllm/blob/4edb55169f69c76bb87ab9f154585917cb01bb17/vllm/benchmarks/serve.py . This is a source-layout qualification, not execution of that runtime.

Required: `duration` in seconds (positive), `completed` (nonnegative integer). Optional: `num_prompts`, `failed`, `total_output_tokens`, `request_throughput`, `request_goodput`, percentile summary fields, model metadata and detailed arrays. Counts, supplied failures and array lengths must agree. Unknown schemas, malformed JSON, contradictory fields and nonfinite values are refused.

Detailed arrays: `errors` (empty string means success, checked against `completed`), `ttfts` (seconds), `latencies` (end-to-end seconds), `queue_times` (client queue seconds), `input_lens` and `output_lens`. Failed-request samples never enter successful-request percentiles. If success cannot be aligned to request indices, per-request qualification is held. With all requests completed, all indices are known successful without an errors array.

Older vLLM outputs may contain `request_goodput:` with a trailing colon, and may omit `latencies`. The former is retained as an observation. The latter prevents E2E gating; the tool never approximates full completion latency by summing inter-token gaps. Documented legacy layout: https://docs.vllm.ai/en/v0.9.1/api/vllm/benchmarks/serve.html .

Selected summaries: `median_ttft_ms` or `p50_ttft_ms`, `p95_ttft_ms`, `p99_ttft_ms`, and corresponding `e2el` fields. Absent fields stay unavailable. Reported zero-success summaries do not turn zero-filled latencies into favorable statistics. Multiple trials without complete raw samples show percentile ranges rather than an average of percentiles.

One file may contain a JSON object, an array of objects, newline-separated objects, or vLLM appended objects. A console block recognizes the exact numeric labels for successful/failed requests, duration and TTFT/E2EL percentiles. Console summaries lack request-level evidence. Limits: 25 MiB per file, 50 MiB per batch, 50 trials per side and 100,000 request indices per trial and 250,000 detailed rows per side. Summary statistics from very large campaigns should be pre-aggregated by the producer with their own evidence preserved.

## Comparison metadata

Read from top-level fields or the `metadata` object:

| Field | Meaning |
| --- | --- |
| `model_id` or `model` | Exact model identity |
| `model_revision` | Pinned revision |
| `precision` or `dtype` | Representation / quantization |
| `tokenizer_revision` | Pinned tokenizer |
| `workload_id` or `dataset_sha256` | Identity of the request set and protocol |
| `cache_policy` | Shared cold/warm/prefix policy |
| `load_profile` | Offered traffic, concurrency and output-length policy |
| `runtime_digest` or `runtime` | Runtime/container identity, retained for review |

When `load_profile` is missing, reported `request_rate`, `max_concurrency` and `burstiness` form a provisional load label. Workload identity must still cover the exact request/protocol shape. Missing identifiers can be supplied in the interface. These are user declarations, not machine-discovered facts. Conflicting supplied versus imported metadata holds the calculation. Hardware-specific runtime differences are retained but do not by themselves prevent a matched-workload comparison.

## Optional request-evaluation sidecar

First retain the exact benchmark bytes and compute SHA-256. Supply one boolean per original request in its original order, including failed requests. `record_index` is zero-based within the JSON/JSONL input file. Failed transport requests must have `false`.

```json
{
  "schema": "hot-aisle/request-evaluation@1",
  "source_sha256": "64_lowercase_hex_characters_of_the_exact_benchmark_file",
  "record_index": 0,
  "evaluator": "your-validator-name-and-version",
  "criterion_id": "your-frozen-correctness-contract",
  "passed": [true, false, true, false, false]
}
```

Import through the evaluation control after its benchmark, or drop both files in a single batch. Enable “Require evaluator-passed outcomes.” Latency and evaluation gates are intersected per request. The workbench does not validate the correctness criterion or execute submitted code. This is evaluator-declared request acceptance, not completed coding-agent task evidence.

## Reports and privacy

HTML is an inert printable report with escaped strings. JSON includes only selected identifiers, normalized counts/timings, price assumptions, selected gates and source hash/record-index commitments. Generated text, prompts, raw errors, original filenames and unknown metadata are omitted. The saved payload carries a SHA-256 checksum and can be recomputed with the exact page engine. Matching original files additionally bind normalization to the committed bytes.

A checksum is not a signature. Someone can intentionally create a different payload and checksum; that is a different object, not authenticated history. Selected model/workload/runtime names can themselves be identifying, so inspect exports before sharing. There is no localStorage, third-party request, automatic upload, endpoint call, GPU allocation or persistent account state.
