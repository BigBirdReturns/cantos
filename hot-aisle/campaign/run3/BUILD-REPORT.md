# Lane A build report

Status: **Kit built; 17 offline tests PASS. No GPU run or real EvalPlus container evaluation performed.**
Scope: only `hot-aisle/campaign/run3/`. No commit, branch, push, provider API, rental,
SSH, publication or contact with another person. Read-only upstream documentation was used.
Other lane changes appeared concurrently and were left alone.

## Files built

| Files | Purpose |
|---|---|
| PREREG.md | Question, exact supplied pins, A/T0, A/T1, N/T0 and deferred L, workload, gates, disclosures, ledger fields, stop rules and budget |
| SOURCES.md | Exact intended upstream dataset releases/URLs, source citations and explicit UNVERIFIED byte/image identities |
| README.md | Commands for preparation, every script, offline tests, arm execution, recovery, grading and engine verification |
| common.py | Local deterministic JSON, SHA-256 verification, model/runtime constants |
| workload.py | Stdlib release loader; freezes prompts and full grading references, checks hashes/counts/unique IDs, refuses overwrite |
| replay.py | CODE arrival scaling, streaming completion client, distinct seeds, absolute request deadline, bounded concurrency, durable journal, loss recovery, five-minute buckets |
| convert.py | Request-order-preserving vLLM detailed arrays and exact source identities, queue time and explicit error masks |
| grade.py | EvalPlus sample/reference preparation, repeated-task result join, source-bound request-evaluation sidecar and quality buckets |
| grade.sh, grader.Dockerfile | CPU-seat-only EvalPlus 0.3.1 container preparation/evaluation, immutable image identity requirement, bounded runtime |
| arm3.sh, arm.py | Serve/health/environment/smoke/replay/manifest pipeline, AMD tiers, selected backend/kernel extraction, clocks and ledger, watchdog and failure retention |
| engine_check.cjs | Loads the real `../../index.html` report engine using the campaign engine_table.cjs approach |
| selftest.py | Seventeen offline tests including a real local fake streaming HTTP server and page-engine verification |
| fixtures/README.md, humaneval.jsonl, mbpp.jsonl, code-slice.csv, serve-amd.log | Five authored synthetic tasks, CODE-shaped synthetic timestamps and backend-selection fixture; no benchmark evidence |

## How to run

From the repository root:

```
python -B hot-aisle/campaign/run3/selftest.py
```

Full, copyable seat commands and required variables are in README.md. Execution sequence:
verify source assets -> workload.py -> freeze hashes/start/rate/grader image -> authorized
arm3.sh invocation -> verify retained manifest -> grade.sh on CPU -> engine_check.cjs.
Arm choices are `amd T0`, `amd T1`, `nvidia T0`, each in a fresh output directory.
No provider credentials are consumed by the kit itself.

## Test results

Final complete run:

```
Ran 17 tests in 3.302s
OK
ENGINE {"engine":"2.0.0","attempted":6,"completed":5,"accepted":2,"holds":[]}
```

- Workload: deterministic frozen bytes, five tasks with grading references, mismatched
  hashes/production counts/overwrite rejected.
- Replay: actual HTTP/SSE text and usage, sampling fields, exact schedule boundary,
  rate scaling and coverage refusal, six distinct seeds with task cycling, five-minute
  bucket emission, HTTP error, truncated SSE, missing usage and deadline failure.
- Failure preservation: overload attempts counted without a queue; truncated journal
  recovery retains all scheduled requests and marks absent results lost/unsent.
- Grading: repeat order and exact solution join, source/reference hash binding, missing
  result and reordered result refusal, unattempted-task scaffolding excluded, grading
  timeouts fail. A failed transport cannot become a passed sidecar entry.
- Engine: real page normalization and quality attachment, inclusive queue-aware latency
  intersection, expected 6/5/2 counts, no holds, wrong source hash and impossible quality
  mask rejected. This verifies software interoperability, not model output quality.
- Arm: selected versus overridden backend parsing, AMD T0/T1 and NVIDIA flags, watchdog
  arithmetic, mocked pull failure seals ledger/manifest with retained error output,
  shell/container contract assertions.
- All seven Python files parse; all five command-line tools' `--help` paths exit 0.

**Native shell check NOT RUN:** attempts to run `bash -n` on both shell scripts failed
before parsing because Git Bash cannot create its Windows file mapping in this sandbox
(`CreateFileMapping ... Win32 error 5`). Python structural checks pass but are not a Bash
parser or a Linux execution test. Docker image build, vLLM startup, real EvalPlus grading,
GPU timing and watchdog process-tree behavior on Linux remain NOT RUN.

The first test attempt exposed Python 3.13 TemporaryDirectory's restrictive Windows ACL
behavior in this sandbox. It failed before fixture writes. Tests now use uniquely named
directories with inherited permissions, and all later test directories clean up normally.
Eleven initial `.selftest-*` directories remain inaccessible; ordinary empty-directory
removal and ACL reset were denied. No test file was successfully written into them. They
are local cleanup remnants, not deliverable files, and cannot be committed as empty git
directories. An operator with suitable local filesystem access should remove those exact
run3 `.selftest-*` remnants. No elevation was requested or performed.

## Schedule and budget check

40 min pull/download/health + 2 min environment/smoke + 60 min arrivals + 65 sec drain
+ 115 sec bookkeeping = 105 min work alarm. Five minutes cleanup reserve = **110 min**
outer watchdog, with a final 30-second forced-kill allowance. Three invocations reserve
two billed hours each: 2 AMD x 2h x $2.99 + 1 NVIDIA x 2h x $4.41 = **$20.78**;
$4.22 contingency/CPU allowance brings the plan to **$25 of $50**. Acquisition and provider
release must fit that external cap. Container stop does not stop provider billing.

## Open questions / unverified prerequisites

1. Exact compressed dataset SHA-256s, Azure trace SHA and exact frozen slice start are
   UNVERIFIED. Release URLs and loader contracts were checked, but artifact bytes could
   not be fetched through the local restricted network. Scripts refuse UNVERIFIED hashes.
2. CPU base-image digest, installed dependency set and final grader image identity need
   a CPU-seat build, freeze and actual EvalPlus smoke. Supplied serving/model pins are
   retained exactly, with runtime verification still required on the GPU seat.
3. The explicitly declared multiplier is 0.10. It has **not** been calibrated to ~70%
   of graded-workload capacity. A replacement needs a pre-data protocol freeze; the kit
   never claims measured utilization or adapts rate independently per arm.
4. The lane's explicit 60-minute replay overrides the synthesis's 90-minute suggestion.
   One hour is implemented and budgeted. A longer window requires revised arithmetic.
5. CODE fixture is synthetic schema-shaped data, not a downloaded slice of the production
   trace. The real slice and release-byte validation are still seat preparation tasks.
6. Backend log syntax is checked with a fixture. If real selected attention/linear lines
   do not match, the arm stops with UNVERIFIED selections and retains serve.log for review.
7. Acquisition attempts, request/release timestamps, invoices, actual funding source,
   metered CPU/estate energy and traversal counters are external observations. Their ledger
   fields remain null pending a separate closure receipt. L remains a later streamed-seat
   experiment; nothing here establishes end-to-end estate capacity or closures per traversal.

## Operator must supply

- Reviewed source bytes and SHA-256s, exact trace start, task-file hash, final rate freeze,
  and immutable CPU grader image identity.
- Explicit approval of the real ~$25 campaign, self-funded A/T0 billing, any T1 credit
  substitution, and already authorized GPU/CPU seats. Build authorization did not rent them.
- Provider credentials only to the external acquisition/release workflow; observed t_ssh,
  capacity-request and release evidence, invoices/credit statements, and spend monitoring.
  The pinned model is ungated; no Hugging Face token is assumed or stored by this kit.
- A working Linux Bash/GNU timeout/Docker/Python environment for native shell/container
  qualification before a paid replay, plus prompt release after each arm.

No benchmark result, provider comparison, correctness rate or public registration is asserted.
