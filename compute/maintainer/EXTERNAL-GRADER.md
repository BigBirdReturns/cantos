# Generic captured-application grading

`external_grader.py` prepares captured text conversations for a recipient-owned
application grader and binds its per-observation outcomes back to the native
maintainer grade schema. It supports single-step and multi-step **captured text**
workloads. It does not implement structured tool calls, launch an agent, repair
responses, or establish that an application oracle is correct.

Preparation and binding execute no supplied code. Only the explicit `run`
command starts a grader, inside a locally available digest-pinned Docker image.
The existing EvalPlus-specific bridge remains useful for its stronger,
domain-specific solution/reference checks.

## Workload and identity

The final step of each externally graded case uses the existing expectation:

```json
{
  "kind": "external",
  "grader": {
    "name": "MyApplicationTests",
    "revision": "our-tests-2026-11-18",
    "criterion": "our-full-conversation-acceptance-v1",
    "artifact_sha256": "<immutable local Docker image ID, 64 lowercase hex characters>",
    "reference_sha256": "<SHA256 of the exact application reference file>"
  }
}
```

An optional `normalizer_sha256` pins a separate file supplied with `--normalizer`.
The adapter copies that file as data. A grader may use it **inside its sandbox**;
the host adapter never imports or executes it. Without this field the adapter
performs no normalization. One exact grader identity is supported per adapter
invocation; native exact-text/JSON cases in the same workload remain native.

The reference is opaque application data: retain its source, licensing and
acceptance rationale. An immutable image ID, reference digest and explicit
criterion pin what was selected; they do not independently prove oracle quality.
Use a separately pinned native grading contract to change the grader after
collection while keeping the original workload and observations unchanged.

## Prepare

```sh
python -B compute/maintainer/external_grader.py prepare \
  --run YOUR_CAPTURE/baseline/run.json \
  --reference YOUR_APPLICATION_REFERENCE \
  --out NEW_BASELINE_PREPARED_DIRECTORY
```

Add `--normalizer YOUR_PINNED_FILE` or `--grading-contract YOUR_CONTRACT.json`
when applicable. Preparation first invokes the existing native raw receipt
validator. It verifies bounded protocol cardinality, captured requests, response
streams, original workload and expected grader/reference identities.

The immutable preparation contains `prepared.json` and an `input/` directory
with `transcript.json`, `reference.bin` and optional `normalizer.bin`. Total
input is limited to 64 MiB. Its hashes bind the preparation to the run, workload,
adapter implementation and relevant native validator source.

`transcript.json` uses `cantos.external-transcript/1`. It contains `grader`,
`run_sha256`, `workload_sha256`, `reference_sha256`, `normalizer_sha256` and
`observations`. Every externally graded task/trial/repetition is included,
including failed or incomplete captures. Each observation contains:

- `task_id`, zero-based `trial` and `repetition`;
- `response_sha256` over the exact final captured UTF-8 response;
- `trajectory` with the original case, each actual request (including its full
  prior messages), every captured response/hash/error/finish reason and raw-file
  hash, plus `capture_eligible`;
- `trajectory_sha256` over the adapter's canonical JSON encoding of that full
  trajectory (sorted keys, compact separators, UTF-8, no nonfinite numbers).

An earlier exact-step failure, transport failure or incomplete stream stays
ineligible. A grader cannot convert it into accepted application work.

## Grader process contract

The recipient's image supplies executable `/grader/run`. It receives:

```text
/grader/run --transcript /input/transcript.json --reference /input/reference.bin
```

When pinned, `--normalizer /input/normalizer.bin` is appended. `/input` is a
read-only snapshot containing only these fixed data files. The grader writes
**one JSON document to stdout** and diagnostic text to stderr. No arbitrary
host output directory, Docker socket or other host path is mounted.

Output schema:

```json
{
  "schema": "cantos.external-results/1",
  "transcript_sha256": "<SHA256 of exact transcript.json bytes>",
  "grader": {"...": "the exact grader object from the transcript"},
  "results": [{
    "task_id": "original-case-id",
    "trial": 0,
    "repetition": 0,
    "response_sha256": "<copied exact response hash>",
    "trajectory_sha256": "<copied full trajectory hash>",
    "accepted": false,
    "reason": "optional application-specific explanation"
  }]
}
```

Exactly one result is required for every transcript observation. Missing,
duplicated, unexpected or mismatched identities/hashes fail closed. `accepted`
must be a JSON boolean. Ineligible captures must return `false`.

## Explicit bounded execution

```sh
python -B compute/maintainer/external_grader.py run \
  --prepared NEW_BASELINE_PREPARED_DIRECTORY \
  --out NEW_BASELINE_EXECUTION_DIRECTORY \
  --timeout-s 300 --cpus 2 --memory-mb 2048 --pids 128
```

The adapter checks that the selected Docker context uses a local Unix socket or
Windows named pipe and that `sha256:<artifact_sha256>` is already present. It
never pulls an image. Images declaring writable Docker volumes are refused.

Execution uses an argument array with `shell=False`, no network, a read-only
root, no capabilities, no-new-privileges, numeric unprivileged UID/GID, no
healthcheck, finite CPU/memory/swap/PID limits, and a 64 MiB noexec/nosuid `/tmp`.
Stdout is capped at 16 MiB and stderr at 256 KiB. There is a finite wall-clock
limit and an exact, unique owned container name for cleanup. The only bind
mount is the private read-only input snapshot. These are runtime controls,
not a claim that arbitrary hostile code is universally safe in Docker.

The output directory retains result bytes, bounded logs, image/context inspection,
invocation/limits, cleanup outcome and `execution.json`. Failed attempts retain
their receipt and available bounded partial output. A failed or timed-out
execution cannot be bound as a successful grader execution. Docker runtime
qualification on the recipient's platform remains a separate acceptance step.

## Bind and continue the native decision

```sh
python -B compute/maintainer/external_grader.py bind \
  --run YOUR_CAPTURE/baseline/run.json \
  --prepared NEW_BASELINE_PREPARED_DIRECTORY \
  --results NEW_BASELINE_EXECUTION_DIRECTORY/results.json \
  --execution-receipt NEW_BASELINE_EXECUTION_DIRECTORY/execution.json \
  --out NEW_BASELINE_GRADES_DIRECTORY
```

Binding revalidates original raw evidence, regenerates the full transcript,
checks source/grader/reference/normalizer identities and exact coverage, and
then invokes the **existing native `validate_grades`** on the emitted
`cantos.maintainer.grades/1` receipt. It retains the preparation, transcript,
reference, output, bridge source, original run identity and any execution closure.
Repeat for the candidate and pass both `grades.json` paths to the existing
`maintainer.py analyze` command or deployment job.

An independently run compatible grader may supply results without
`--execution-receipt`; that receipt is explicitly labelled
`operator_supplied_result_no_execution_attested`. The adapter never infers a
container execution from the output's claimed image ID. Recorded execution and
hashes preserve custody; they do not attest a remote producer or certify the
grader's application judgments.

Changing a grader, reference, normalizer or criterion requires an explicit native
grading contract and new grade/analysis directories. Changing the adapter or
native validator between prepare and bind requires a new preparation. Original
captures, dates and earlier grades remain immutable. No inference is performed
by any of these commands.

## Deployment-job integration

`validate_config(config, closure_root)` is read-only. The explicit live job can
call `grade_pair(runs, config, closure_root, new_output_directory)` after capture
and before final native analysis. Its configuration is:

```json
{
  "execute": true,
  "reference": "inputs/application-reference.json",
  "limits": {"timeout_s": 300, "cpus": 2, "memory_mb": 2048, "pids": 128}
}
```

Optional `normalizer` and `grading_contract` are also paths relative to the
self-contained job root. Escapes and unpinned inputs are rejected. The helper
prepares, explicitly runs and binds both arms, returning their native grade
receipt paths. It records two grader executions and zero inference requests.
`execute: true` is required; import, validation and retained decision/reanalysis
must never invoke this helper. They verify and reuse the already bound receipts.
