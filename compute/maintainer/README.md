# Maintainer instrument

Run the same versioned application workload against baseline and candidate serving endpoints, retain the streamed evidence, and obtain a machine-readable regression verdict. The instrument connects the existing Open Compute Ledger exact evaluator and paired comparison to streamed execution and the independent vLLM concurrency auditor. `SOURCES.json` identifies the unchanged native owner modules and their hashes. Python 3.10 or later and the standard library are sufficient for collection and comparison; model servers and application graders keep their own environments.

## Run a comparison

From a Cantos checkout, copy `compute/maintainer/examples/` into a working directory, set the two endpoint URLs and served model names, and replace every identity placeholder in `spec.json`. The example deliberately refuses live requests until it is configured. Preserve the actual implementation revision or container digest, weights manifest SHA256, tokenizer revision, hardware identifiers, precision, context limit and serving flags. Set the shared request controls and choose a representative workload file. The two illustrative exact-output cases demonstrate the file contract; they establish no model or hardware ranking.

```bash
python -B compute/maintainer/maintainer.py prepare \
  --spec /absolute/path/to/spec.json --arm baseline

python -B compute/maintainer/maintainer.py run \
  --spec /absolute/path/to/spec.json --out /absolute/path/to/new-comparison
```

`run` performs real streamed requests. It creates a new output directory, preflights the input and policy, records declared and endpoint-observed identities, applies any declared warmup, and alternates baseline/candidate ordering as AB, BA, AB across paired trials. Both arms receive the same seeded case order within each trial. A task's later conversation steps include the actual preceding answer. An exact failure stops that task's remaining steps, as in the native OCL runner. No request is retried.

The endpoints must already be running. The instrument does not launch servers, reserve or reset GPUs, clear server caches or evict other processes. Use the serving project's established lifecycle and record its relevant controls in `identity.settings`. Existing endpoints are useful for CI, two containers, remote servers or explicitly sequenced local builds. The same URL used twice identifies two observations only when the operator has changed and identified the serving implementation. Endpoint URL equality provides no runtime identity proof.

The directory contains `baseline/run.json`, `candidate/run.json`, each run's input workload, plan, before/after identity probes, append-only observation journal, and raw byte chunks with monotonic arrival times. `verdict.json` and `report.md` are convenient top-level copies of the retained analysis outputs in `analysis/`. Every run receipt lists the relative path, SHA256 and byte size of its evidence artifacts. A complete receipt never replaces an earlier attempt. A crashed or interrupted attempt retains its existing files; run a new observation with a new output directory and identity after inspecting the failed attempt.

| Command outcome | Exit | Meaning |
| --- | ---: | --- |
| `pass` | 0 | Declared comparability, exact accepted work and requested thresholds pass for this evidence. |
| `regression` | 1 | A comparable candidate fails a quality, matched latency, throughput or modeled-cost requirement. |
| `incomparable` | 2 | A required condition, identity, external grade, usable reference or metric is missing or uncontrolled. |
| `error` | 3 | Input/evidence validation, transport or stream completeness failed. Raw failed responses remain evidence. |

`observe` returns 0 for a complete capture, even when answers are wrong or await an external application grader. Its receipt records capture `status` separately from task acceptance. A transport or stream error returns 3. `run` and `analyze` return the verdict exits above. CI and bisection scripts should use the terminal verdict exit and retain `verdict.json`, rather than treating successful process execution or HTTP 200 as accepted work.

## Workloads and independent application grading

Each external workload is a JSON object with schema `cantos.maintainer.workload/1`, a `name`, `version`, optional `source` and `description`, and a nonempty `cases` list. Case IDs are unique and stable. A single-step case contains text `messages` and `expect`; a conversation contains `steps`, each with additional messages and an expectation. Supported message roles are `system`, `user`, and `assistant`. Structured streamed tool calls need a task-specific adapter; the provided OCL lookup workload uses the existing exact JSON conversation protocol.

```json
{
  "schema": "cantos.maintainer.workload/1",
  "name": "Order summary application contract",
  "version": "2026-11-18",
  "source": "Our versioned evaluation cases and independent expected results",
  "cases": [{
    "id": "order-001",
    "messages": [{"role": "user", "content": "Return the sum of 17 and 25 as {\"sum\":integer}."}],
    "expect": {"kind": "json_exact", "value": {"sum": 42}}
  }]
}
```

`json_exact` reuses OCL's strict duplicate-key and nonfinite rejection and type-aware equality. The native evaluator allows its existing single JSON Markdown fence. JSON booleans, integers, strings and nulls retain their types. `text_exact` compares the full visible answer string, including whitespace. The expectation is fixed before live collection and travels with the raw evidence. Changing the workload or oracle creates a new observation identity.

For code or other application tasks, use a final expectation with `kind: "external"` and an independently pinned `grader` object. Required fields are `name`, `revision`, `artifact_sha256`, and `reference_sha256`; optional `criterion` and `normalizer_sha256` pin the acceptance rule and transformation. A complete streamed response remains ungraded until an independent application grader supplies a matching receipt. The collector never executes generated code.

```json
{
  "kind": "external",
  "grader": {
    "name": "EvalPlus",
    "revision": "0.3.1",
    "artifact_sha256": "<64 lowercase hex characters>",
    "reference_sha256": "<64 lowercase hex characters>",
    "criterion": "base_status == pass and plus_status == pass",
    "normalizer_sha256": "<64 lowercase hex characters>"
  }
}
```

The external grade receipt uses schema `cantos.maintainer.grades/1`, `run_sha256` over exact `run.json` bytes, `workload_sha256`, the exact declared `grader`, and `results`. Every result contains `task_id`, zero-based `trial` and `repetition`, SHA256 of the exact UTF-8 final `response_text`, a boolean `accepted`, and `evidence` paths. Its `artifacts` closure retains the grader inputs, results and logs using the same relative path/SHA256/bytes records. All completed external responses require results; duplicate, missing or mismatched joins fail closed. The instrument verifies these bindings and hashes, then imports outcomes into the existing OCL paired accounting. Evidence integrity does not turn a grader self-report into independent hardware or identity attestation.

The OCL synthetic two-turn task generator remains available for a bounded protocol check:

```bash
python -B compute/maintainer/maintainer.py export-ocl --out /absolute/path/to/new-ocl-workload.json
```

Its twelve generated tasks retain their original scope. Supply your own versioned application cases and acceptance oracle for a consequential engineering decision.

## Retained analysis and policy

`analyze` validates every raw artifact, replays the stream parser, checks actual request bodies against the captured workload and protocol, regrades exact answers, and compares the retained runs. It makes no network requests. Supply optional external grading receipts when required:

```bash
python -B compute/maintainer/maintainer.py analyze \
  --baseline /absolute/path/to/baseline/run.json \
  --candidate /absolute/path/to/candidate/run.json \
  --policy /absolute/path/to/policy.json \
  --baseline-grades /absolute/path/to/baseline-grades/grades.json \
  --candidate-grades /absolute/path/to/candidate-grades/grades.json \
  --out /absolute/path/to/new-analysis
```

Omit the two grade arguments for exact JSON/text workloads. Change acceptance latency limits, permitted finish reasons, performance thresholds or hourly prices in a policy file, then reanalyze the existing observations. Acceptance-policy changes may change the accepted count; a price-only change preserves it. The original raw receipt and its initial grade remain unchanged.

The policy schema is `cantos.maintainer.policy/1`. Unknown fields are rejected. The example lists the usual requirements; omitted fields use conservative defaults.

| Policy field | Default | Gate |
| --- | --- | --- |
| `allowed_changes` | `[]` | Explicit dotted factors such as `identity.implementation.revision`, `identity.settings.prefix_cache`, or `implementation_inputs`. A parent path allows its descendants. |
| `min_trials` | 3 | Required repeated trials per arm. |
| `min_baseline_acceptance` / `min_candidate_acceptance` | 1 / 1 | Minimum exact task acceptance fractions. Zero accepted reference work cannot pass. |
| `max_acceptance_drop` | 0 | Maximum baseline minus candidate acceptance fraction. |
| `max_new_failures` | 0 | Maximum baseline-accepted task instances that newly fail, independent of offsetting newly passed tasks. |
| `max_p95_latency_increase` / `max_p95_ttft_increase` | 0.15 / 0.15 | Maximum fractional increase in the median of per-trial candidate/baseline ratios. `null` disables either gate. |
| `max_accepted_throughput_drop` | 0.15 | Maximum fractional loss in accepted tasks/second over full measured trial windows. |
| `acceptance.max_latency_s` / `acceptance.max_ttft_s` | `null` / `null` | Per-task duration and per-request visible TTFT limits. |
| `acceptance.finish_reasons` | `["stop"]` | Explicitly accepted terminal reasons. Truncation is preserved and rejected by default. |
| `prices.baseline_per_hour` / `prices.candidate_per_hour` | 0 / 0 | Declared modeled hourly rates, never inference dependencies. |
| `max_cost_per_accepted_increase` | `null` | Optional modeled-cost ratio gate; requires positive baseline rate and accepted work. |
| `require_observed_model` / `require_observed_version` | `true` / `false` | Require response/model-list consistency and optional `/version` availability. |

Workload bytes, procedure files, trial count, repeats and seed remain mandatory pairing conditions even if a broad `allowed_changes` entry is supplied. Other unexpected differences produce `incomparable`; declared experimental changes remain visible in `changed_factors`. The report distinguishes paired alternating trials from separately collected retained observations. A configuration change creates an experimental comparison with changed conditions; it does not establish a hardware speedup by itself.

Latency and TTFT use exactly matched task/trial/repetition instances accepted in **both** arms. A candidate cannot appear faster by failing a harder task that disappears from its accepted population. The full native OCL comparison retains both-accepted, baseline-only, candidate-only and both-failed counts and task transitions. New task losses have their own gate, so equal aggregate acceptance cannot conceal changed failures. Accepted throughput includes all measured trial time and failed work. Per-trial ratios and ranges remain visible; their median is the specified operational gate, not a statistical population claim. Small sample p95 estimates and repeated fixtures retain their limitations.

Modeled cost equals the declared hourly rate multiplied by the sum of measured trial windows. It includes failed requests inside those windows and excludes warmup, identity probes, server startup, between-trial idle, setup, and other reserved time. It measures no energy or provider invoice. A deployment-capacity or total-reservation analysis should supply its own independently measured allocation window rather than interpret this metric as full cluster TCO.

## Timing and identity boundaries

Raw evidence contains every received byte chunk, its monotonic arrival time, exact request body, HTTP status, stream errors and partial answer. The parser requires a completed SSE frame sequence, a finish reason, `[DONE]`, and nonempty visible content. A role-only or reasoning-only delta does not establish answer TTFT. `ttft_s` is time from request start to the first nonempty visible `delta.content`, measured at the client; it includes connection, network, queue and prefill delays.

`inter_content_chunk_s` records arrival gaps between visible-content chunks. A chunk may contain several tokens, so this is not token ITL. `input_tokens` and `output_tokens` come only from server `usage`, with an explicit source label; missing values stay null. The instrument emits no invented TPOT or per-token timing. The independent vLLM auditor computes exact simultaneous request overlap using half-open intervals, including failed measured requests for concurrency accounting, rather than whole-second buckets.

Declared server identity is stored separately from observed `/version`, `/v1/models`, and response model fields. Missing required identity, model disagreement or a version change during capture prevents a pass. Operator declarations of weights, tokenizer, physical devices and serving flags remain declarations. Pin optional `implementation_files` beside the spec to capture actual local implementation/source/container-manifest changes. Record remote immutable artifact identity when local files do not represent the serving binary. HTTP probes cannot independently attest physical hardware or code revisions.

## SecondRun and fresh observations

The importable contract is `prepare(spec_path, arm)`, `observe(spec_path, arm, out_dir, observation_id)`, `validate_receipt(run_path)`, `validate_grades(grades_path, run_path)`, and `analyze_receipts(baseline_path, candidate_path, policy_path, out_dir, baseline_grades=None, candidate_grades=None)`. The CLI has corresponding `prepare`, `observe`, and `analyze` commands.

`prepare` returns a canonical selected-arm observation `identity`, its `observation_key`, and absolute `dependencies`. These include the exact workload, shared execution protocol, selected endpoint/configuration, actual producer modules and declared implementation input hashes. They exclude the whole spec's bytes, the other arm, the policy file and all policy prices. Editing candidate implementation inputs invalidates candidate observation and dependent analysis while preserving unaffected baseline evidence. Editing price invalidates analysis alone. Changing the actual measurement procedure invalidates its observations.

`observe` requires an explicit `observation_id`. It always performs new requests into a new directory; cached evidence belongs to the prior observation and retains its original timestamps. The SecondRun adapter owns reuse decisions, artifact validation and fresh epochs. A reused result never becomes a fresh measurement because a caller changes its label. See `integration/WORK.md` and its maintainer example for dependency-runner commands and the optional maintainer-verdict CI gate.

## Verification

```bash
python -B -m unittest discover -s compute/maintainer/tests -v
```

The tests use a labeled local HTTP/SSE protocol fixture. They exercise incomplete and malformed streams, HTTP errors, duplicate JSON, wrong answers, truncated output, missing identity, unexpected versus declared factor changes, raw evidence tampering, balanced task wins/losses, matched performance populations, external grade binding, price-only retained analysis and CI exits. Fixture timing tests establish instrument behavior; they make no physical accelerator or model-quality claim. Real endpoint/application qualification receipts remain separately identified.
