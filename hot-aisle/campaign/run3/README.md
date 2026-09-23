# Run 3 kit — lane A only

Build kit, not benchmark results. Python 3.10+ stdlib and dependency-free Node for offline
checks. Production orchestration requires Linux, Bash, GNU timeout, Docker and Python on
an already authorized seat. Read PREREG.md, SOURCES.md and ../DISCLOSURES.md first.
Nothing provisions or releases a provider VM. No credentials are required for the offline
tests. Scripts and fixtures are steward-owned; seat output directories are machine-written
immutable evidence after sealing. Never put real raw output into the public site accidentally.

## Offline qualification

From the repository root:

```text
python -B hot-aisle/campaign/run3/selftest.py
```

This exercises every Python component, real loopback HTTP/SSE, journal recovery, grading
joins, and the actual `hot-aisle/index.html` engine through engine_check.cjs. It creates
unique temporary directories inside run3 and removes them. Tests never run generated code,
Docker, pip, a provider API or SSH. Individual suites:

```text
python -B hot-aisle/campaign/run3/selftest.py WorkloadTests
python -B hot-aisle/campaign/run3/selftest.py ReplayTests
python -B hot-aisle/campaign/run3/selftest.py GradeTests
python -B hot-aisle/campaign/run3/selftest.py ArmTests
```

On Linux, shell entry-point checks use `bash arm3.sh --self-test` and
`bash grade.sh --self-test`; syntax checks use `bash -n arm3.sh` and `bash -n grade.sh`.
common.py is a library, tested through all suites; arm.py is tested through ArmTests;
convert.py and engine_check.cjs through GradeTests. The Dockerfile/build path is structurally
checked by ArmTests; a real image build and full EvalPlus run still require a CPU-seat test.

## Prepare and freeze on the CPU seat, before rental

These are future operator commands, not actions taken by the build. In a private working
directory, fetch the exact three source URLs in SOURCES.md with the seat's approved download
tool (for example `curl --fail --location URL --output FILE`). Retain the original files.
Record `sha256sum HumanEvalPlus.jsonl.gz MbppPlus.jsonl.gz AzureLLMInferenceTrace_code.csv`
in the freeze packet, with source URLs and date. A locally computed hash establishes retained
identity; it does not alone authenticate a release. Complete source review before freezing.

Set the shell variables below to the reviewed 64-hex values, not placeholder strings.
Set `KIT` to the absolute copied run3 directory and `WORK` to a new private working directory.

```bash
python3 -B "$KIT/workload.py" \
  --humaneval "$WORK/HumanEvalPlus.jsonl.gz" --humaneval-sha256 "$HE_SHA" \
  --mbpp "$WORK/MbppPlus.jsonl.gz" --mbpp-sha256 "$MBPP_SHA" \
  --out "$WORK/tasks.json"
sha256sum "$WORK/tasks.json"
```

The builder refuses overwrite, mismatched hashes, wrong task counts, duplicate IDs and
missing reference fields. Store its printed task SHA as `TASKS_SHA`. The full references
stay in the frozen file but only `task_id` and `prompt` enter model requests. The file is
deterministic for the same release bytes. The `--fixture` option bypasses production counts
and permanently marks the output synthetic; arm.py refuses it.

Choose and freeze `TRACE_START` according to PREREG.md and set `TRACE_SHA`. `RATE_FACTOR=0.10`
is the declared fallback multiplier, measuring price and correctness rather than capacity.
Follow PREREG's short pre-data calibration, then refreeze the same factor for all scored arms;
if unavailable, explicitly freeze the 0.10 fallback with capacity target UNVERIFIED.
At the fallback the selected source must cover at least six minutes after that
start, expanded to 3,600 seconds. The parser validates coverage over the full CSV; no repeat
or fabricated arrivals. Freeze the same task hash/start/rate/trace hash for every arm.

Prepare the CPU grader on the CPU seat (dependencies are installed **inside the image**):

```bash
export BASE_IMAGE='python:3.11-slim@sha256:REPLACE_WITH_REVIEWED_DIGEST'
bash "$KIT/grade.sh" --build-image
export EVALPLUS_IMAGE=$(docker image inspect run3-evalplus:0.3.1 --format '{{.Id}}')
docker image inspect "$EVALPLUS_IMAGE" > "$WORK/grader-image.json"
docker run --rm --entrypoint cat "$EVALPLUS_IMAGE" /evalplus-installed.txt > "$WORK/grader-packages.txt"
```

The literal placeholder is intentionally rejected. EvalPlus is pinned to 0.3.1; transitive
package versions are captured in the image's installed list, not installed into this repo.
Record the content-addressed image ID (or registry digest) before running. Use the same image
on all grading work. Base digest, final image ID and real container behavior are UNVERIFIED
in this build. Preserve a CPU smoke test before spending on GPU runs.

## Run one arm on the GPU seat

Copy the kit, frozen tasks and retained trace onto the approved GPU seat. Required variables:
`KIT`, `WORK`, `TASKS_SHA`, `TRACE_SHA`, `TRACE_START`, refrozen `RATE_FACTOR`, and the actual observed UTC
`SSH_READY` timestamp from acquisition. Docker must work for the operator, port 8000 must
be free, and `WORK/hf-cache` must be suitable for the pinned checkpoint. The ungated model
needs no model token; provider access stays with the external acquisition operator.

```bash
bash "$KIT/arm3.sh" amd T0 --approved-run \
  --tasks "$WORK/tasks.json" --tasks-sha256 "$TASKS_SHA" \
  --trace "$WORK/AzureLLMInferenceTrace_code.csv" --trace-sha256 "$TRACE_SHA" \
  --start "$TRACE_START" --rate-factor "$RATE_FACTOR" \
  --hf-cache "$WORK/hf-cache" --t-ssh "$SSH_READY" --out "$WORK/A-T0"
```

Run the declared tuned arm with `amd T1` and fresh output `A-T1`; the comparator uses
`nvidia T0` and fresh output `N-T0`. There is no NVIDIA T1. Each invocation has its own
110-minute watchdog and retains failed evidence. `--approved-run` records that the operator
already approved this bounded invocation; it is not rental authorization by itself.
No automatic restart/retry. Containers use unique names and are stopped, not deleted;
image and checkpoint caches are retained. **Provider release and its timestamp are external.**

Outputs: invocation.json, ledger-times.json, ledger.json, pull.log, container-id.txt,
serve.log, image-inspect.json, gpu.txt, env.json, three smoke JSONs, tasks.json,
replay/{plan.json,journal.jsonl,requests.jsonl,buckets.json,replay-status.json}, detailed.json,
container-stop.log, MANIFEST.sha256. Failure paths retain what exists plus failure.json
or recovery-failure.json. The manifest covers all files present at finalization except itself.
env.json contains selected attention_backend and linear_kernel lists plus a `holds` list.
Unknown selections are recorded as HOLDs and permit replay; T1 still requires the sole
attention selection ROCM_AITER_FA. Qualification must inspect these identity HOLDs separately
from the page engine's latency/quality checks. completed_ungraded does not imply qualification.

### Arm summary contract for the Lane B adapter

`ledger.json` has schema `second-run/run3-arm-summary@1`. It is a flat summary; a Lane B
adapter must build the grouped `second-run/run-ledger@1` and join external closure evidence.
Existing field names are retained:

| Fields | Meaning |
|---|---|
| schema, status, arm, tier | Summary identity; status failed or completed_ungraded; arm A or N |
| timestamps | t_request, t_ssh, t_ready, t_work_start, t_work_end, t_released, t_script_start, t_script_end; unavailable clocks null |
| hourly_list_usd, funding | Dated declared list rate and funding text, not invoice evidence |
| modeled_full_cost_usd, billed_usd, credits_usd, acquisition_attempts | External closure fields; null |
| restarts, attempted, completed, failed, lost | Restarts zero; attempted is scheduled arrivals, failed includes all missing/rejected/error arrivals; lost is confirmed sends without terminal results |
| never_sent, send_unknown | Added counts: never dispatched or client-limit rejected; dispatch with uncertain send or legacy missing result |
| correct, accepted, cost_per_accepted_usd, wall_seconds_per_accepted | Null until external grading/closure join |
| traversals_per_run, seconds_per_traversal, bytes_per_traversal, accepted_closures_per_traversal, energy_wh | Null, unmeasured |
| note | Null/release semantics |

Counts are null if detailed evidence could not be produced. `failed` includes `lost`,
`never_sent` and `send_unknown`; never sum them again into failed. detailed.json metadata
names those subsets `lost_requests`, `never_sent_requests`, and `send_unknown_requests`.
Known terminal errors such as HTTP 503 are failed but not lost. Replay bucket fields remain
offset_s/duration_s/attempted/completed/failed/correct/accepted/completed_per_s; adapters
must map these explicitly instead of treating this file as a grouped run ledger.

## Replay or recover retained evidence directly

Only for an already serving approved run (the normal arm calls this itself):

```bash
python3 -B "$KIT/replay.py" --tasks "$WORK/tasks.json" \
  --trace "$WORK/AzureLLMInferenceTrace_code.csv" --trace-sha256 "$TRACE_SHA" \
  --start "$TRACE_START" --rate-factor "$RATE_FACTOR" --out "$WORK/replay-new"
```

This writes a full schedule before issuing requests, with journal_events=1. Journal rows
are flushed and fsynced before dispatch (`event: dispatch`), after HTTPConnection.request
returns (`event: sent`, confirming client send, not server receipt), and as responses finish
(terminal rows have no event). request_index, not journal order, is the join identity.
Output timestamps are Unix seconds; durations within a request use a monotonic clock.
First token = first nonempty text chunk. Output token count is server usage, never characters
or SSE chunk count. Missing usage fails the request. Failed token-array slots become zero
only alongside the explicit error mask; they are excluded from engine successful metrics.

After an interruption, work on an unsealed copy of retained evidence:

```bash
python3 -B "$KIT/convert.py" "$WORK/replay-copy" "$WORK/recovered-detailed.json" \
  --runtime "$PINNED_SERVING_IMAGE"
```

convert.py reconstructs canonical requests.jsonl and buckets.json from the schedule and
journal. A truncated final journal line is ignored; a malformed complete line, duplicate
terminal index, duplicate/out-of-order event or wrong task/seed is refused. Absent results
become lost_after_send only with a retained sent event; no dispatch is
never_sent_after_interrupt. A dispatch without a sent event becomes
send_unknown_after_interrupt because network send and disk fsync cannot be atomic. Missing
results from legacy plans without journal_events=1 also remain send_unknown. Full planned
hour plus actual drain is the duration; incomplete runs are not sustained results. Conversion
does not manufacture missing tokens or correctness. Preserve the original manifest and bytes.
Client-limit rejections are never sent, yet count as failed transport in the <=1% gate,
with all scheduled arrivals as denominator. More than 1% rejects useful-throughput
qualification; exactly 1% passes this gate. No overload row is removed or retried.

## Grade on the CPU seat and verify with the page engine

Copy the sealed arm directory to CPU custody; verify its manifest (`sha256sum -c MANIFEST.sha256`
inside that directory). Keep grading output separate from that sealed directory.

```bash
bash "$KIT/grade.sh" "$WORK/A-T0/tasks.json" "$WORK/A-T0/replay" \
  "$WORK/A-T0/detailed.json" "$WORK/A-T0-grade"
node "$KIT/engine_check.cjs" "$WORK/A-T0/detailed.json" "$WORK/A-T0-grade/evaluation.json"
```

Run engine_check.cjs from the repository layout (it loads `../../index.html`), or bring
the matching page file in that relative layout. The Python CPU grading tools themselves
do not need the page. The wrapper uses two CPU containers, one dataset each, with no runtime
network, 4 CPUs, 8 GB memory, a 2-hour limit per dataset and a stop trap. The build step is
the only dependency-installing step. No GPU is used for grading. An exhausted grading limit
is a hold; preserve outputs, review CPU budget, and use a fresh grading directory if retried.

Direct components, useful for auditing and offline supplied evaluator output:

```bash
python3 -B "$KIT/grade.py" prepare TASKS_JSON REQUESTS_JSONL DETAILED_JSON NEW_GRADING_DIR
python3 -B "$KIT/grade.py" join TASKS_JSON REQUESTS_JSONL DETAILED_JSON GRADING_DIR EVALUATION_JSON
python3 -B "$KIT/grade.py" summary REPLAY_DIR EVALUATION_JSON DETAILED_JSON QUALITY_BUCKETS_JSON
```

prepare emits humaneval.jsonl and mbpp.jsonl, exact reference overrides, and mapping.json.
EvalPlus receives `solution = frozen prompt + raw completion`. Failed transports get `pass`
as a failing placeholder and can never pass the final mask. Tasks not attempted get null-index
scaffolding solely to satisfy EvalPlus's all-task assertion; they are excluded from every
request count. Within a task, results join in sample order, with exact solution comparison;
MD5 must match EvalPlus's local reference hash and SHA-256 binds all our retained inputs.
Use the sidecar's per-request booleans, not EvalPlus's printed pass@k over scaffolding.

The sidecar is `hot-aisle/request-evaluation@1`, tied to the exact detailed.json bytes and
record_index 0. Missing results, unknown statuses, stale bytes or reordered solutions stop
the join. grade summary emits 12 buckets, min/median accepted rate and final/initial quarter
ratio. Full-run acquisition, release, bills, credits, energy and traversal counters require
an operator closure receipt; the kit leaves them null, never zero by assumption.

## What can rot / qualification boundary

Release assets and Azure download location, CSV timestamp format, streaming usage support,
vLLM log wording, Docker GPU access, EvalPlus result format and transitive CPU dependencies
can change. Exact hashes and fail-closed joins expose drift. A successful offline build
does not verify production dataset bytes, GPU backends, model quality, image startup, real
container sandbox behavior, throughput, invoices, traversal counts or estate feasibility.
