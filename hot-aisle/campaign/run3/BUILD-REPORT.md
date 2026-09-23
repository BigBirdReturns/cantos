# Lane A build report

Status: **Fix round 1 complete; 19 offline tests PASS. No GPU run or real EvalPlus container evaluation performed.**
The original build record below is historical; the appended Fix round 1 section supersedes
its backend stop behavior, timeout split, recovery counts and cleanup observations.
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

## Fix round 1

Scope: Lane A only. All file writes stayed in `hot-aisle/campaign/run3/`; other lanes
were left untouched. No commit, push, branch, rental, provider API or GPU operation.
The required Estate front-door probe failed before contact because its configured runtime
file at `S:\Scratch\Runs\Estate-Peer\known_hosts` is sandbox-denied. Continued only the
explicitly authorized local Lane A repair; no remote recovery or substitute execution.

Files changed/built:

- arm.py: parse the selected token in `Overriding with X` and `Using X backend
  (selected via --attention-backend)`, ignoring candidate lists. Unknown backend/kernel
  identity adds explicit env.json HOLDs while replay proceeds; T1 still requires AITER.
  Child wait is 3720 seconds. Flat ledger.json now identifies itself as
  `second-run/run3-arm-summary@1`; all previous fields retain their names.
- replay.py and convert.py: durable dispatch/sent journal events distinguish missing
  confirmed sends (`lost`) from never-sent and uncertain sends. Includes the unavoidable
  network-send/fsync crash window and legacy journals as uncertainty, never fabricated loss.
  Client-limit rejection is never-sent but remains a failed scheduled attempt.
  Added summary fields never_sent/send_unknown and corresponding detailed metadata counts.
- fixtures/serve-amd.log: exact selection lines copied from real Run 2 serve.log;
  fixtures/serve-amd-exploration.log: observed lines supplied in the fix brief;
  fixtures/serve-nvidia.log: explicitly AUTHORED, since no real CUDA log is available.
  fixtures/README.md records source and evidence limits.
- PREREG.md: 0.10 explicitly measures price/correctness, not capacity. Added one short
  pre-data reference calibration targeting approximately 70% measured A/T0 capacity,
  a common factor refreeze before scored data, fallback 0.10 and budget accounting.
  Documented client_concurrency_limit's inclusion in the <=1% failure gate.
- README.md: stable flat-summary field contract for Lane B's adapter, revised commands,
  backend HOLDs and event/recovery semantics. selftest.py adds regression coverage.

Run all offline tests from the repository root:

```text
python -B hot-aisle/campaign/run3/selftest.py
```

Result: **19 tests PASS** (3.917 seconds). Actual page-engine check:
`{"engine":"2.0.0","attempted":6,"completed":5,"accepted":2,"holds":[]}`.
Tests cover the real ROCm override/candidate line, supplied explicit AITER selection,
authored CUDA selection, unknown identity HOLDs, mocked T0 continuation and T1 refusal,
3720-second child timeout, renamed summary schema, mixed interruption recovery,
legacy uncertainty, overload counts and all previous workload/grading/SSE checks.
All seven Python AST parses and all five CLI `--help` paths PASS. `git diff --check`
passes for Lane A. No tmp*, .selftest-* or __pycache__ directories remain in this lane.
The old build's cleanup-remnant note no longer describes the current filesystem.

Watchdog arithmetic: 2400 startup + 120 environment/smoke + 3720 child wait
(3600 arrivals + 60 drain + 60 parse/load/recovery/exit) + 60 conversion/bookkeeping
= 6300 work alarm; +300 cleanup = 6600 outer watchdog. Timing remains unverified on a GPU.

Native Bash syntax checks were attempted for both unchanged shell scripts but could not
start: Git Bash `CreateFileMapping ... Win32 error 5`. Shell/container/Linux qualification
remains NOT RUN, not a passing test. No production calibration or performance result exists.

Open questions/operator inputs remain reviewed dataset hashes, trace start, final common
factor, serving/grader identity verification, calibration command/receipt, campaign funding
approval, authorized seats, acquisition/release records and invoices. The calibration driver
and Lane B closure adapter are external to this lane; no cross-lane edits were made.
No tokens are needed for these offline tests. Unknown environment identity still blocks
qualification even when the replay finishes, and production CUDA wording remains UNVERIFIED.
