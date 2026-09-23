# Run 3 preregistration kit — lane A

Status: **BUILT, NOT RUN; freeze packet incomplete until SOURCES.md prerequisites are supplied.**
This file is a proposed protocol, not proof of public registration. No commit or publication
is performed by this lane. Freeze this file, script hashes, datasets, task file, CPU grader
image, exact trace start, and rate factor before renting. Preserve all failed attempts.

## Question, arms and identities

For a real graded coding task stream, what does an accepted closure cost from capacity
request through confirmed release, and does useful throughput persist for a full hour?
Primary comparison is A/T0 versus N/T0. A/T1 is a separately reported, declared tuning
tier; never silently replace A/T0 with the best-looking tier.

- A/T0: Hot Aisle 1x MI300X VM, self-funded at dated list $2.99/GPU-hour.
  Only AMD tuning is `VLLM_ROCM_USE_AITER=1`; attention backend auto-selects.
- A/T1: same allocation type, separate run, T0 plus `--attention-backend ROCM_AITER_FA`.
  Budget below assumes self-funded too. If credit funds this tier, disclose it separately.
- N/T0: DigitalOcean 1x H100, self-funded at dated list $4.41/GPU-hour, CUDA image defaults.
- L: estate, later and separately approved; no launch implementation or equivalence claim
  in this cloud kit. Judge an end-to-end streamed model on traversal cost versus deadline,
  at increasing batch depth with metered energy. Do not reject it merely for exceeding VRAM.
  Any quantization/runtime difference requires separate identity and protocol before execution.

Pins (full strings also in common.py):

```
model Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8
revision/tokenizer dcaee4d4dfc5ee71ad501f01f530e5652438fde0
CUDA vllm/vllm-openai@sha256:8a69ffad015f138d7170c4ddc429e230a3bc1c1719f67e14324749df200a4b90
ROCm vllm/vllm-openai-rocm:v0.30.0@sha256:2e7da1ad1c66836802072588adea75f9f4991da5f9545b4318e91d422c22ce6a
EvalPlus 0.3.1; HumanEval+ v0.1.10; MBPP+ v0.2.0
```

Both vendors must actually report vLLM 0.30.0. Common serve flags: max model length
16,384, max sequences 256, GPU utilization 0.90, tensor parallel 1, prefix caching off;
KV dtype defaults. `serve.log` retained in full, selection lines extracted into env.json.
Unrecognized selection stops before replay for review, with no guessed kernel identity.
Three fixed greedy smoke prompts, seed 0, max 64 output tokens. Smoke is not correctness.

## Workload and arrival freeze

Freeze all 164 HumanEval+ and 378 MBPP+ prompts and complete grading references. Task
order: HumanEval IDs ascending numerically, then MBPP IDs ascending numerically; cycle
542 tasks. Seed = 700000 + request index, same across arms and distinct within each run.
Use raw function completion prompts, temperature 0.2, max_tokens 1024, EOS honored,
no ignore-eos, no repair, chat wrapper, sanitizer, retry or task-result reuse.

Replay a **60-minute recorded arrival window**, as the lane brief explicitly requests.
This narrows the synthesis's suggested 90-minute recorded duration; it preserves its
minimum sustained hour. Every arm uses the identical frozen trace bytes/start/factor.
Choose the first full hour boundary in the source CSV with coverage of the selected window;
record its exact timezone-qualified start before renting. Naive Azure CSV timestamps are
interpreted as UTC for reproducible ordering, not as a claim about upstream clock geography.

Declared rate multiplier **0.10**: scheduled offset = (source timestamp - frozen start)/0.10,
retaining offsets in [0,3600). Thus six source minutes expand into one replay hour, keeping
bursts and relative interarrival spacing. Do not loop or pad a short source. At most 100,000
scheduled requests, fitting the page engine's detailed input limit. This is a conservative
declared rate, **not evidence of 70% measured capacity**. The synthesis's ~70% target is
UNVERIFIED without a graded-workload calibration. A calibration-derived replacement factor
requires a new pre-data freeze and budget allocation; no per-arm adaptation or mid-run tuning.

Serving-host loopback client, max 256 outstanding requests, no waiting client queue.
An arrival at the limit is retained as a failed `client_concurrency_limit`, never delayed
into a later arrival or omitted. Actual dispatch delay is measured separately. A 60-second
absolute request deadline bounds even trickling SSE. No automatic retries. Client failure,
missing token usage or incomplete SSE is a failed completion. Text and usage remain retained.

## Gates and metrics

Correct = EvalPlus base **and** plus pass for that exact raw completion. A transport
failure cannot pass. EvalPlus sample timeout is a failed grade; missing/incomplete evaluator
output is a grading hold, not a fabricated false result. Report task classes separately as
well as combined; repeated seeds are samples, not additional distinct benchmark problems.

Accepted = completed AND correct AND first text <= 1 second AND end <= 60 seconds from
the **scheduled** arrival. Engine settings: ttft=1000 ms, e2e=60000 ms, queue=true,
quality=true. The engine intersects request masks; do not multiply aggregate percentages.
TTFT measures arrival of the first nonempty SSE text chunk (not a GPU internal timestamp).

Report all 12 five-minute buckets by scheduled arrival, including empty buckets and failed
requests. After grading: attempted/completed/correct/accepted, accepted rate, minimum and
median bucket accepted rate, and last-quarter / first-quarter accepted count (null when
first quarter is zero). Useful-throughput comparison requires a complete uninterrupted hour,
both datasets represented, no identity/quality holds, and failed transport <=1%. Latency
rejections and incorrect outputs remain in denominators. No p95 claim from a few samples.

Headline: full modeled allocation cost / accepted closures (also per 1,000) and full
capacity-request-to-release seconds / accepted closure. Zero accepted => null cost per unit,
not zero cost. Window engine economics are supporting evidence only; use a supplied total
charge for full-run engine costing after ledger closure. Show invoices, credits, failed
acquisitions, startup and idle separately. This kit does not assert a winner or acceptance rate.

## Schedule, watchdog and cash

One invocation per tier; no hidden three-repeat plan:

| Phase | Maximum seconds |
|---|---:|
| Image pull + model download + health, combined | 2400 |
| Environment inspection + three smoke requests | 120 |
| Recorded arrivals | 3600 |
| Final request drain + child exit slack | 65 |
| Conversion / normal bookkeeping slack | 115 |
| Cleanup / log and manifest reserve | 300 |
| **Total outer watchdog** | **6600 = 110 minutes** |

2400 + 120 + 3600 + 65 + 115 = 6300 seconds: the work alarm. Cleanup reserve takes
the total to 6600. Outer GNU timeout sends TERM at 110 min and KILL after 30 seconds
if hung. The budget conservatively reserves **two billed hours per invocation**, covering
110.5 minutes plus at most 9.5 minutes total acquisition/release overhead. External operator
release must keep that cap; killing a container does not stop a VM bill.

Two AMD invocations: 2 x 2h x $2.99 = $11.96. One NVIDIA: 2h x $4.41 = $8.82.
Cloud ceiling for this schedule = **$20.78**. Reserve **$4.22** for acquisition failures,
release lag and CPU grading/energy => **$25** of the overall **$50** allowance. This is a
plan, not an invoice. Stop rather than consume the other $25 automatically. No CPU rental
is implied; use an already authorized CPU seat. Its energy/cost must be entered later.

## Stop rules and ledger

Stop if funding, approval, source lock or identity is missing; if capacity cannot be acquired
within the external budget; if health misses 40 min including downloads; if preparation
misses 42 min; if selected backend/kernel is unknown; if T1 fails to select ROCM_AITER_FA;
if the replay or watchdog fails; or if the $25 run allowance is exhausted. No crash restart
or repeat without a new logged attempt and budget check. Preserve journals and logs.
An interrupted hour is retained as incomplete, never promoted to sustained qualification.

arm.py emits ledger-times.json and ledger.json. Observed here: supplied t_ssh, script start,
t_ready, t_work_start, t_work_end, script end; arm/tier, hourly list price, funding declaration,
attempted/completed/failed/lost counts, restarts=0. It emits null for externally owned or
unmeasured fields: t_request, t_released, acquisition_attempts, modeled full cost, billed USD,
credits, correct, accepted, cost/wall seconds per accepted, energy Wh, traversals per run,
seconds and bytes per traversal, accepted closures per traversal. Grading adds source-bound
quality evidence in its own sidecar and bucket file. Operator closure joins those receipts
and adds acquisition/release/invoice evidence **in a new closure record**, never editing
hashed raw artifacts. Token counts do not substitute for measured weight traversals.

## Disclosures carried forward

Read ../DISCLOSURES.md with any eventual result. Prior Hot Aisle work used a $200 provider
credit, and Second Run is pitching Hot Aisle a paid engagement. Run 3 A/T0 is explicitly
self-funded at list; verify the actual bill before saying it was. NVIDIA is self-funded.
Credit, modeled list cost and invoice are three different fields. No provider endorsement.

Run 1 had unequal vLLM versions, tuned AMD versus default NVIDIA kernels, short synthetic
windows, no correctness measurement, missing AMD per-request E2E, and post-hoc TTFT-only
scoring distinct from its registered cell gates. Run 2 lacked a comparator and its planned
repeats did not fit its watchdog; forced AITER exploration was post-hoc. This new protocol
does not repair those old claims. DigitalOcean MI300X control remains omitted; no claim
says Hot Aisle is the cheapest MI300X provider. Serving-host timing excludes remote-client
network effects. Private local ordering is not independent public timestamping. Estate
streaming evidence remains partial; no closures-per-traversal result has been established.
