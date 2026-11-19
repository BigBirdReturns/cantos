# Retry accounting

The retry campaign runs bounded attempts of the same versioned application task through the existing streamed capture, exact-output evaluator and source-bound external-grade validator. Each attempt starts a fresh conversation, includes every step of that conversation, and stops at the first accepted outcome or the configured attempt limit. Repeated trials, task attempts and HTTP conversation steps have separate identities.

## Run and inspect

Use a normal maintainer spec with the selected baseline or candidate endpoint already running and its actual model, implementation, tokenizer, precision and hardware declarations filled. Set protocol warmup to zero; a separately retained warmup remains a separate experiment. Put the retry policy beside it:

~~~json
{
  "schema": "cantos.maintainer.retry-policy/1",
  "max_attempts": 5,
  "backoff_s": 0.25,
  "retry_on": ["rejected", "transport_error"],
  "attempt_seed_stride": 0
}
~~~

~~~sh
python -B compute/maintainer/retry.py prepare \
  --spec /absolute/spec.json --arm baseline \
  --retry-policy /absolute/retry-policy.json

python -B compute/maintainer/retry.py run \
  --spec /absolute/spec.json --arm baseline \
  --retry-policy /absolute/retry-policy.json \
  --out /absolute/new-campaign --observation-id unique-observation

python -B compute/maintainer/retry.py validate --path /absolute/new-campaign
python -B compute/maintainer/retry.py inspect --path /absolute/new-campaign
~~~

The run records new HTTP requests. Exit 0 means a complete, internally consistent capture and accounting. It does not mean the tested model passed the workload. A complete campaign with every task rejected still exits 0 and reports zero accepted tasks. Exit 2 denotes unresolved/incomplete evidence; exit 3 denotes input or validation failure. Evaluate the recorded task counts and the separately declared comparison requirements for a deployment decision.

The parent workload, selected serving identity, measurement source, retry/seed policy, and acceptance controls enter the observation identity. Hourly prices do not. The two arms must use the same workload and declared retry policy for a comparison. Each trial/repetition/case has one task instance. Each task attempt has its own ordinary maintainer run and raw byte evidence, independently valid under the existing owner. A conversation's second HTTP step is part of the same task attempt.

Temperature remains zero under the existing capture protocol. The default stride retains the original seed at every attempt. A nonzero predeclared stride uses base_seed + (attempt_number - 1) * stride. This schedule is evidence of what was requested, not statistical independence or a promise that repetition will improve correctness. The collector never inserts the expected answer, test failure text or grading feedback into a retry.

## Accounting

The receipt retry-campaign.json carries these metrics:

| Field | Definition |
| --- | --- |
| offered_tasks | Every task/trial/repetition offered, including eventual transport failures and exhausted tasks. |
| accepted_tasks | Task instances eventually accepted within the bound and policy. |
| first_pass_successes / first_pass_success_rate | Tasks accepted on their first attempt, divided by all offered tasks. |
| total_task_attempts | All attempted solutions/conversations, including those belonging to tasks that never succeed. |
| retries_total | All task attempts after each task's first attempt. |
| retries_per_accepted_task | retries_total divided by accepted_tasks, charging exhausted-task retries to the workload's useful output. |
| retries_among_successes | Retry count from eventual successes only. |
| mean_retries_among_successes | retries_among_successes divided by accepted_tasks. |
| total_http_requests | Durably recorded POST dispatch intents; this may exceed task attempts for multi-step conversations. |
| campaign_duration_s | Whole measured campaign window, including task preparation, endpoint probes, queueing, backoff, capture, grading and journaling. |
| sum_task_elapsed_s | Sum of submit-to-terminal elapsed times; concurrent task windows can overlap and this is not campaign wall time. |

Ratios with zero accepted tasks remain null. HTTP dispatch and received token usage do not establish whether a timed-out or disconnected request consumed server work. Such attempts retain their transport state. Missing energy and actual spending remain null. The resource join must use the exact campaign receipt, observation identity, timebase and observation interval, and preserve its own sensor/accounting boundary.

Every task records submit, worker-start and terminal monotonic timestamps. Its duration includes client queueing, all retries, backoff and external grading. Every attempt records a separate evaluation timestamp; the total-task latency requirement is evaluated after its grading decision, while terminal bookkeeping remains included in task/campaign elapsed time. Startup, preflight, prior reservations and server idle outside the campaign remain outside this window.

The Linux timebase uses the observed hostname and OS boot ID with time.monotonic_ns. Both nanosecond and second aliases are bound in the receipt. On an OS without an exposed boot identity, the fallback clock identity is stable only within one producer process. Independent cross-process power collectors must establish the same timebase before attributing energy; a new process UUID cannot qualify that join.

## Crash and interruption

events.jsonl flushes and fsyncs request_start before dispatch, then records request_terminal only after raw evidence is written. Task attempts have distinct start and terminal records. A process interruption preserves an unclosed start as an unknown outcome. inspect counts the attempted dispatch, reports the unknown request IDs and always returns automatic_replay_authorized=false. validate refuses an incomplete receipt. Reusing an existing output directory is refused before new network work.

The collector does not resume or retry unknown dispatches automatically. Preserve the original campaign, inspect the server/request state, then use a separately identified new observation if a new run is warranted. The current implementation does not stream partial wire chunks durably during an outstanding request; an interrupted request may therefore have a known dispatch and unknown response/usage. The journal describes that gap directly.

## Existing isolated EvalPlus owner

For HumanEval complete-code tasks, use only the existing supported EvalPlus 0.3.1 contract and pinned local container from EVALPLUS-BRIDGE.md. The parent reference must contain exactly the workload's task IDs. No image build, download or fallback occurs in the retry runner. The named local image must already exist and image inspection must equal the workload's artifact SHA.

~~~sh
python -B compute/maintainer/retry.py run \
  --spec /absolute/humaneval-spec.json --arm baseline \
  --retry-policy /absolute/retry-policy.json \
  --evalplus-reference /absolute/humaneval-reference.jsonl \
  --evalplus-normalizer compute/maintainer/normalize.py \
  --grader-timeout-s 600 \
  --out /absolute/new-graded-campaign --observation-id unique-graded-observation
~~~

For each single-case attempt, the campaign selects the exact corresponding parent-reference JSON object, serializes that subset deterministically, and pins its new SHA in the derived single-case workload. Validation reconstructs this relationship from the original pinned reference. The original parent hash and case identity remain unchanged.

The adapter invokes the existing prepare command, runs EvalPlus in the digest-pinned networkless/read-only Docker image with dropped capabilities, no-new-privileges and explicit process/CPU/memory/time bounds, then calls the existing bind command and validates its result against the raw run. Generated Python executes only in that container. The trusted normalizer is separately pinned; model output never becomes a shell argument or host program. The actual command, image inspection, logs, preparation and complete grade closure remain with each attempt. The owned container is stopped after timeout. A grader infrastructure error yields an unresolved task and does not trigger a semantic retry.

## Verification and evidence classes

~~~sh
python -B -m unittest discover -s compute/maintainer/tests -p test_retry.py -v
~~~

These checks use a labeled local HTTP/SSE fixture and, for prepare/container/bind protocol coverage, a labeled Docker substitute which writes grader-shaped fixture results without executing generated code. They establish control flow, source binding, arithmetic, queue/grade timing and refusal behavior. They are not model, GPU-energy or actual EvalPlus execution measurements. A native model plus the existing actual sandbox image must be exercised separately before claiming empirical retry quality.

## Retained verification record

On 2026-11-18, OCTO-W03 durable job `cantos-retry-final-tests-20261118b` ran the focused unittest command above against the final retry source and completed with exit 0: 8 tests in 4.845 seconds. The broader maintainer suite previously completed 36 tests with exit 0 in `cantos-retry-integration-tests-20261118a`; subsequent changes tightened safe-path/JSON validation, retained the Docker no-pull flag, and repaired the direct CLI import before the final focused rerun. These jobs use CPU fixtures and establish software behavior, with actual model/sandbox and resource evidence qualified separately.
