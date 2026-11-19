# Maintainer instrument

Run the same versioned application workload against baseline and candidate serving endpoints, retain the streamed evidence, and obtain a machine-readable regression verdict. The instrument connects the existing Open Compute Ledger exact evaluator and paired comparison to streamed execution and the independent vLLM concurrency auditor. `SOURCES.json` identifies the unchanged native owner modules and their hashes. Python 3.10 or later and the standard library are sufficient for collection and comparison; model servers and application graders keep their own environments.

## Decide which deployment to operate

The [deployment job](DEPLOYMENT-JOB.md) joins this native comparison to required operational checks and attributed cost or energy inputs. Configure your own workload and existing endpoints, validate the manifest, collect supported local operations, run the comparison and export one retained result. Required unknown evidence blocks a deployment selection. Changing prices or requirements creates a child analysis over the original capture; changing serving conditions requires new observations. The [external grader adapter](EXTERNAL-GRADER.md) binds exact captured text conversations to a pinned evaluator and supports explicit, bounded local Docker execution.

The workbench's **Decide what to run** view prepares the inputs and imports the returned bundle. [MAINTAINER-START.md](../../MAINTAINER-START.md) gives the runnable kit entry point. A blank [resource worksheet](examples/deployment-resources.json) names the cost fields and allocations; its unknown values must be replaced with your own sourced assumptions before economics can resolve. Supported operational tests and modeled accounting retain their scopes; this workflow does not establish broader provider, accelerator or application coverage.

The [operational HTTP auditor](OPERATIONAL-HTTP.md) runs bounded authorized HEAD availability probes or GET response-body identity checks with explicit expected SHA-256, direct transport and fail-closed receipt handling. It provides observed client-vantage network and content-distribution evidence for operational requirements, without claiming provider-side SLA or application acceptance.

The [TLS certificate auditor](OPERATIONAL-TLS.md) collects bounded direct, authorized HTTPS-origin handshakes using default CA and hostname validation. Its externally pinned, offline-replayable receipts bind leaf DER identity, expiry policy and observed failure classes without converting them into provider security or SLA claims.

The [single-connection HTTPS auditor](OPERATIONAL-HTTPS-JOINT.md) joins the verified TLS leaf and bounded HTTP response on the same direct socket. It records exact connection-level identities, rejection classes and observed response integrity in an externally pinned, offline-replayable receipt; no provider-wide SLA is inferred.

## Retry campaigns and measured resources

[RETRY.md](RETRY.md) documents the separate bounded retry campaign: first-pass success, every solution attempt and HTTP step, exhausted work, full task latency, durable interruption evidence, and source-bound sandboxed EvalPlus grading. [RETRY-RESOURCES.md](RETRY-RESOURCES.md) documents the exact campaign join to GPU board power and declared cost scenarios. [GRADE-DIAGNOSIS.md](GRADE-DIAGNOSIS.md) joins pinned raw coding responses to independent EvalPlus outcomes. [EMPIRICAL-ECONOMICS.md](EMPIRICAL-ECONOMICS.md) recomputes actual captured board joules per accepted application task, validates source provenance, and conditionally prices explicit scenarios. The original paired comparison below keeps its existing one-attempt protocol. Each retry arm needs its own immutable campaign under the same workload and retry policy; a retry receipt alone supplies no paired deployment verdict. The [Hy4 Flash readiness package](experiments/hy4-flash/README.md) pins model/runtime metadata and refuses unsupported or incomplete deployment inputs before inference.

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
    "criterion": "humanevalplus-v0.1.10-base-and-plus-chat-complete-code-v1",
    "normalizer_sha256": "<64 lowercase hex characters>"
  }
}
```

The external grade receipt uses schema `cantos.maintainer.grades/1`, `run_sha256` over exact `run.json` bytes, `workload_sha256`, the exact declared `grader`, and `results`. Every result contains `task_id`, zero-based `trial` and `repetition`, SHA256 of the exact UTF-8 final `response_text`, a boolean `accepted`, and `evidence` paths. Its `artifacts` closure retains the grader inputs, results and logs using the same relative path/SHA256/bytes records. All completed external responses require results; duplicate, missing or mismatched joins fail closed. The instrument verifies these bindings and hashes, then imports outcomes into the existing OCL paired accounting. Evidence integrity does not turn a grader self-report into independent hardware or identity attestation.

For the existing EvalPlus 0.3.1 owner, [EVALPLUS-BRIDGE.md](EVALPLUS-BRIDGE.md) gives the public `evalplus_bridge.py prepare` → bounded container → `bind` commands. `normalize.py` is the explicit whole-response Python-fence transform, with no repair. The binder rechecks the full raw run, reruns that pinned transform on the exact answer, joins every result to its task/trial/repetition and rejects changed or missing solutions. A compatible recipient-built grader uses its own explicitly pinned image identity. The guide's explicit grading contract applies a changed evaluator or normalizer to both arms of the same retained capture without sending inference requests.

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

### Retain the result in the existing Cantos workbench

After complete grading, `analyze` also emits `baseline.ocl.json`, `candidate.ocl.json`, and `resolved-policy.json`. These are validated projections into the existing `ocl.run/1` receipt schema, with original run/workload/grade hashes, capture producer identity, raw artifact manifest and exact applied policy. The original observation time stays original. Native task repetition IDs flatten trial/repetition for the existing owner, while `trial` and `source_repetition` retain the original coordinates. A final attempt uses native stage `final` and preserves its captured stage as `source_stage`. External outputs awaiting their application grades produce no native receipt export, so ungraded work cannot become an invented failure count.

Use the qualified public workbench ZIP as the explicit, pinned collector/engine dependency. The maintainer recipient kit includes it at `public/open-compute/open-compute-workbench.zip`; its SHA256 is `a0df6c8fcf1b66e10b78cc640dc3f3e627a64bad4fc3f40964543ca90915870b`. [WORKBENCH-RELEASE.json](../../public/open-compute/WORKBENCH-RELEASE.json) records its source lineage and public projection; the archive manifest binds every shipped source file. This edition includes atomic retained decisions and the operational evidence interface. The exporter checks this identity before loading code and bounds extraction while rejecting traversal and symlinks.

```bash
python -B compute/maintainer/maintainer.py export-packets \
  --analysis /absolute/path/to/new-analysis \
  --bundle public/open-compute/open-compute-workbench.zip \
  --out /absolute/path/to/new-workbench-export
```

`export-packets` executes the existing collector's `ingest` operation for acceptance accounting and financial validation. It retains the collector's original output, then maps the application workload, already validated matched latency metrics, original observation date and evidence closure into the existing `ocl.instrument-packet/1` schema. This explicit adapter removes the old collector's synthetic-suite defaults without replacing its arithmetic. Raw run and grade artifacts, original/resolved policies, source manifests and the pinned owner archive travel with each final packet.

In the running workbench's **Collect & import**, select `baseline/packet.json` and `candidate/packet.json` from the export directory. The exporter already exercises the same existing `Ledger.import_packet` owner, verifies idempotent reimport, and retains a decision/history in `workbench-verification-store`. `workbench-import.json` records that actual import; `export.json` records the complete export closure. The verification decision uses the original quality floor and any declared per-request latency requirements. An `incomparable` maintainer result remains attached to provenance, and a configuration below the original acceptance floor remains ineligible. Choosing a lower floor later creates an explicitly different decision scenario.

Packet costs remain unknown by default. `--baseline-financials FILE` and `--candidate-financials FILE` accept the existing collector's sourced costs/energy input format. To carry supplied policy hourly assumptions, add `--policy-prices-usd`, explicitly declaring their currency and measured-window scope. That option copies the already validated modeled totals into the native financial-input owner; it performs no new measurement and infers no invoice or energy data. It cannot be combined with independent financial inputs for the same priced arm. Missing rates stay unknown; an explicit zero retains its declared zero-cost scenario. Changing only price and repeating retained analysis/export preserves the measured acceptance counts and source observation identities.

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
| `prices.baseline_per_hour` / `prices.candidate_per_hour` | `null` / `null` | Declared modeled hourly rates, never inference dependencies; absent prices remain unknown. |
| `max_cost_per_accepted_increase` | `null` | Optional modeled-cost ratio gate; requires positive baseline rate and accepted work. |
| `require_observed_model` / `require_observed_version` | `true` / `false` | Require response/model-list consistency and optional `/version` availability. |

Workload bytes, procedure files, trial count, repeats and seed remain mandatory pairing conditions even if a broad `allowed_changes` entry is supplied. Other unexpected differences produce `incomparable`; declared experimental changes remain visible in `changed_factors`. The report distinguishes paired alternating trials from separately collected retained observations. A configuration change creates an experimental comparison with changed conditions; it does not establish a hardware speedup by itself.

Latency and TTFT use exactly matched task/trial/repetition instances accepted in **both** arms. A candidate cannot appear faster by failing a harder task that disappears from its accepted population. The full native OCL comparison retains both-accepted, baseline-only, candidate-only and both-failed counts and task transitions. New task losses have their own gate, so equal aggregate acceptance cannot conceal changed failures. Accepted throughput includes all measured trial time and failed work. Per-trial ratios and ranges remain visible; their median is the specified operational gate, not a statistical population claim. Small sample p95 estimates and repeated fixtures retain their limitations.

Absent prices produce null cost and cost-per-accepted metrics. An explicit zero rate represents the operator's zero-cost scenario; a missing price never implies free work. Modeled cost equals the declared hourly rate multiplied by the sum of measured trial windows. It includes failed requests inside those windows and excludes warmup, identity probes, server startup, between-trial idle, setup, and other reserved time. It measures no energy or provider invoice. A deployment-capacity or total-reservation analysis should supply its own independently measured allocation window rather than interpret this metric as full cluster TCO.

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


### Reopen the exported decision

The export's `workbench-verification-store/` contains both imported configurations and the actual decision under the original acceptance requirement. From the same working directory used for `--out new-packets`, open that retained store:

```sh
python -B new-packets/workbench-owner/cantos/open-compute-ledger/run.py --store new-packets/workbench-verification-store --open
```

Select **History** to inspect the saved decision. The workbench owner is the verified bundle already extracted during export. Importing the two packet files into a different workspace creates a separate operator import; explicitly set requirements when making a new decision there.

## Failure-inclusive serving verdicts

Raw-verifiable HTTP 429 and 5xx responses are completed *failed endpoint requests*.
They count against task acceptance, throughput, and cost per accepted task, and can
produce a CI regression when the pinned baseline is usable. A failed HTTP request
does not attest the model behind the endpoint: before/after model advertisements
remain required under the observed-identity policy, and the declared hardware and
weights remain operator claims. Authentication failures, other HTTP errors, broken
streams, network failures and incomplete captures remain instrument errors.
The native receipt retains `status=error` for failed HTTP attempts; the paired
verdict separately records service failure counts and only promotes verifiable
service responses into failure-inclusive quality comparisons. A retained receipt
can be reanalyzed without repeating inference.

### Publication lineage preflight

The recipient kit includes `tools/check_release_promotion.py`. Before any source promotion, invoke it with the exact candidate commit, expected live public-main commit, independently protected root-owner commit, and candidate kit SHA-256 and byte count. It performs live read-only remote-head verification, requires both accepted lineages to be ancestors of the candidate, checks a clean exact HEAD, and verifies the candidate's committed kit bytes. A `HOLD` exits 2. Passing this source preflight does not establish hosted CI or GitHub Pages deployment. Custom remotes are explicitly classified as fixtures, not evidence of public GitHub state.
