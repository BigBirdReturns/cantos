# Empirical qualification: vLLM, HumanEval+ and retained analysis

The [portable empirical archive](evidence/vllm-humaneval-20261118.zip) and its [SHA-256 receipt](evidence/SHA256SUMS.txt) are included in the maintainer kit. The paths in the empirical sections below refer to that archive after extraction. Current source commands are in [README.md](README.md); the packet adapter connects the retained analysis to the existing decision workbench.

From the extracted kit root, run the exact-recipient check without a model server:

```sh
python -B app/tests/check_maintainer_evidence.py
```

This verifies the evidence archive, repeats analysis with the delivered source, imports both packets through the existing workbench engine, retains the original 80% acceptance requirement in decision history, and repeats a price-only scenario with zero new inference. The fixture suites separately exercise pass/regression/incomparable/error exits, artifact tampering, raw-stream failures, accepted-task losses, dependency invalidation, explicit fresh requests and concurrent observation exclusion. The release pipeline runs the recipient path on Linux with Python 3.10 and Windows with Python 3.12; a CI result qualifies the exact source identity recorded by that run.

## Observed result

The delivered maintainer CLI captured 192 actual streaming inference requests and joined independently executed EvalPlus grades to exact response hashes. Both configurations accepted 21 of 96 observations, or seven of the 32 distinct functions in each of three trials. The unchanged policy requires 80% acceptance. The final analyzer therefore returns `incomparable` with exit code 2. This is an observed rejection of an insufficient reference configuration, and supplies no basis for promoting the cache change.

| Measurement | Prefix cache disabled | Prefix cache enabled |
| --- | ---: | ---: |
| Observations | 96 | 96 |
| Accepted by both base and plus tests | 21 | 21 |
| Acceptance fraction | 0.21875 | 0.21875 |
| p95 task latency, matched accepted pairs | 6.493972 s | 6.359380 s |
| p95 first visible content, matched accepted pairs | 0.122014 s | 0.124774 s |
| Accepted observations per second | 0.203093 | 0.198010 |
| Peak client request concurrency | 4 | 4 |
| GPU board energy during measured trials | 8812.171 J | 9002.659 J |
| GPU board joules per accepted observation | 419.627 | 428.698 |
| Price and full operating cost | Unpriced | Unpriced |

The reported p95 latency and visible-TTFT values use the observations accepted in both matched arms. They do not describe all 96 requests per arm. Accepted throughput uses accepted outcomes divided by total measured trial duration, and every accepted or rejected request remains in the raw evidence and application denominator.

The first capture correctly withheld a verdict while external application grades were absent. The original capture producer is retained under `source/`. Independent review found that its inherited report displayed zero cost without supplied prices. The separate analyzer from commit `bb4d21bd16b3e2d8b62138a7e4dbfcce16c6bfdc`, retained under `analyzer/`, reanalyzed the same immutable observations and grades without inference and reports `unpriced`. Original outputs remain under `vllm-graded-analysis/`; the corrected presentation and unchanged qualification outcome are under `vllm-public-reanalysis/`.

## Source, selection and protocol

The workload came from the retained Run3 `tasks.json`, SHA256 `6c508237082261ac927b96825e2f097782389b1cebc3f78360f0665a8db3501f`. The source HumanEvalPlus v0.1.10 reference has SHA256 `42526ec0e7d5f3ee0b06d6ced98f8c8bae3d76519151bfb3d36f79010645bd7f`. Before generating responses, the session sorted all 164 HumanEval tasks by numeric task ID and selected ordinal `floor(i*164/32)` for `i=0..31`. `selection.json` records every selected ID and the exact reference/workload/normalizer hashes. No task was removed or replaced in response to model performance. This is a fixed 32-case subset, with correlated repeated observations, rather than a full 164-case score or a population confidence claim.

Both endpoints served the same retained Qwen3-0.6B FP16 weights, SHA256 `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b`, using vLLM 0.33.0 and Torch 2.14.0+cu132 on the same Quadro RTX8000. The endpoints remained resident on the same physical GPU. Prefix caching was the declared difference. Both used a 4096-token context limit, four maximum sequences, eager mode and 0.2 GPU-memory utilization. The client used three matched trials, one repetition, concurrency four, seed 1729, 512 maximum output tokens, temperature zero, disabled thinking, no warmup and no request retries. Raw stream events, request bodies, exact output text, usage, observed response identities, timing and failures are retained in each run closure. The controller recorded all 192 requests without transport or incomplete-stream errors.

The two endpoint copies shared a GPU and the existing host resource class. A bounded CPU-only CUDA compilation began during the latter portion of collection. This co-tenancy is retained as an observed host condition; the timing differences above describe these paired runs and do not establish an isolated hardware limit or a general cache improvement. Generated content chunks are not tokens. The measurements report time to first visible content and client task latency, without manufacturing a per-token latency metric.

## Application oracle and failure handling

The grading image is `sha256:803e956852925ff35f8d7a9f55a97fbcfad09a8dfa77a439f5b2ac537702563d`, with EvalPlus 0.3.1. Generated Python executed only in the existing network-disabled, read-only-root, non-root container with dropped capabilities, no-new-privileges, 8 GiB memory, four CPUs and a 512-PID limit. The pinned normalizer unwraps one complete Python code fence or preserves raw text; it performs no repair. Both base and plus outcomes must pass. The reusable bridge verifies the full raw-stream closure, run/workload/reference/normalizer hashes, exact response-to-solution mapping, every trial/repetition, complete evaluator coverage and the grading artifact closure before emitting acceptance receipts. The two arms preserve all 192 outcomes.

A current oracle canary executed all 32 selected canonical solutions using the identical reference, image and evaluation limits. All 32 passed both base and plus checks, including HumanEval/15. A retained Nov13 campaign reported a canonical failure for HumanEval/15 under its own setup. This session preserves that historical qualification and records the current successful check, without claiming to have identified the earlier cause or universally repaired the evaluator.

After owned endpoint cleanup, the CLI performed 96 real HTTP attempts against the now unavailable candidate endpoint. Every attempt failed, the run retained all 96 failures and zero accepted observations, and `observe` exited 3. This establishes the actual unavailable-endpoint path. It does not represent 96 GPU inference executions.

## Energy and operating scope

GPU0 board telemetry brackets each measured trial. Integration uses linear boundary interpolation and the trapezoidal rule; the largest observed sampling gap was 0.665175 seconds. The existing 200 W cap remained unchanged, and the observed peak GPU temperature was 66 C. The totals include the GPU board with both endpoint copies resident and all measured failed or accepted application attempts. They exclude host CPU power, the other GPU, facility overhead, idle allocation outside trial windows, capital cost, staffing, networking and full operating spend. `VLLM-EMPIRICAL-RECEIPT.json` reports the measured energy and explicitly leaves prices unknown. The owner wrapper stopped only its own processes and released its lease; the terminal reservation ledger was empty.

## Portable inspection and reanalysis

The export contains exact raw capture/grade/oracle closures, both producer source snapshots, original policy, measured board samples, source selection and license notices. `MANIFEST.json` binds every included file by SHA256 and byte count. Run `python3 verify.py` after extracting the export to verify the manifest, validate original raw observations and reproduce the expected exit-2 qualification using the separately retained final analyzer. No inference, provider access or GPU is required for that path. For a new serving experiment, use the public maintainer CLI with new observation identities and explicit local endpoint/runtime declarations; the retained estate wrapper is evidence of this session's execution environment.

The fixed reference and expanded test inputs retain EvalPlus licensing and OpenAI HumanEval notices. The workflow source retains the existing compute MIT license. Qwen's model license is included as attribution; model weights and the private Docker image are not redistributed in the evidence archive. Each has an exact identity and a documented role. The original A/B/C product outcome also requires broader representative workloads and configurations, operational audits and fuller measured economics. This empirical package qualifies the scoped streaming, grading, refusal and retained-analysis paths described above.

Native filesystem paths, host labels and GPU identities in original command receipts, runtime declarations and `source/SOURCES.json` are retained provenance. They are not recipient path requirements. Public verification and the commands above resolve the extracted relative tree; recipients can unpack it at any local path. The public archive contains only the fixed open HumanEval+ workload, its source tests and generated responses, the owned runtime evidence and the named source snapshots. It contains no model weights, provider credentials, private customer workload, external message, or unrelated project result.

## Frozen SecondRun and operating-envelope evidence

Two additional archives extend the same retained evidence. They preserve actual state transitions and resource failures independently of the completed vLLM comparison. All three archive digests are in [SHA256SUMS.txt](evidence/SHA256SUMS.txt).

| Archive | Exact bytes | SHA256 | Supported conclusion |
| --- | ---: | --- | --- |
| [SecondRun retained-evidence replay](evidence/secondrun-empirical-20261118.zip) | 356,306 | `085ebecf6cb97bd1520d183bbf724698f8e2aef25e46f23e9747e00dbd2591e3` | Initial execution, unchanged reuse, price-only recalculation and native failure propagation on the same real vLLM evidence. |
| [30B guarded operating-envelope attempts](evidence/thermal-envelope-20261118.zip) | 1,442,165 | `c36078e40c73d829e55c5d2b18b526d8778a9c363eab5e79e228b68b02fe31d0` | Two incomplete serving attempts stopped at the unchanged 80 C guard; completed-response grades and owned-process cleanup remain inspectable. |

From the extracted kit root, extract the three archives to a new directory. The archive filenames below differ from their self-contained extracted root names; the commands use both exact names.

```sh
python -m zipfile -e compute/maintainer/evidence/vllm-humaneval-20261118.zip /absolute/new/evidence
python -m zipfile -e compute/maintainer/evidence/secondrun-empirical-20261118.zip /absolute/new/evidence
python -m zipfile -e compute/maintainer/evidence/thermal-envelope-20261118.zip /absolute/new/evidence
python -B /absolute/new/evidence/cantos-vllm-humaneval-evidence-20261118/verify.py
python -B /absolute/new/evidence/cantos-thermal-envelope-20261118/verify.py
python -B /absolute/new/evidence/cantos-secondrun-empirical-20261118/verify-secondrun.py \
  --evidence /absolute/new/evidence/cantos-vllm-humaneval-evidence-20261118 \
  --source . --out /absolute/new/secondrun-recipient-output
```

The output directory must be new. `--source .` exercises the delivered kit's `integration/work.py` and `compute/maintainer` from the kit root. Omitting `--source` exercises the source snapshot included in the SecondRun archive. The original snapshot remains bound to commit `92a39104c5210d2d66afda84b7c899ba97ebfcef`; each replay records the source bytes it actually uses. These checks use Python and its standard library, make no model requests and require no GPU. They replay retained observations and grades without executing generated Python solutions.

### Actual retained-work transitions

The first SecondRun invocation executes two comparisons and returns native verdict exit 2 for the unchanged 21/96 acceptance result. An unchanged invocation reuses both. Changing one task's declared hourly price recalculates that comparison and reuses its independent peer. Replacing that task's candidate with the retained 96-connection-refusal receipt recalculates one comparison, reuses one and propagates native error exit 3. All four invocations record zero model calls, GPU runs and new observations. The enclosing verifier returns zero only after those distinct state transitions and native exits match the expected evidence. Hourly prices of 1.0 and 2.0 remain illustrative assumptions. The immutable inference receipts, grades, original 80% floor and observation identities remain unchanged.

### Thermal failures and completed application work

Two attempts used the retained Qwen3-Coder-30B-A3B-Instruct Q4_K_M weights and pinned llama.cpp source. Each compared one serving slot with four slots on one RTX 8000, with 4,096 context tokens per slot, the same predetermined 32 HumanEval+ tasks, three planned paired trials, concurrency four, temperature zero and max_tokens 1024. GPU1 retained its existing 260 W cap; GPU0 retained its existing 200 W cap. Both reached the unchanged 80 C guard before completing the comparison. Their different devices, caps and shared host conditions prevent a controlled causal comparison of the two attempts.

| Completed evidence | GPU1 attempt | GPU0 attempt |
| --- | ---: | ---: |
| Accepted baseline responses, complete first pass | 31/32 | 31/32 |
| Accepted candidate responses, censored subset | 17/18 | 9/9 |
| Retained raw response streams | 51 | 41 |
| Completed paired trials | 0 | 0 |
| Collector exit after owned thermal stop | -15 | -15 |

The thermal archive grades all 91 persisted completed observations against their exact response and normalizer hashes. The extra GPU1 candidate stream lacks a persisted completion row and remains ungraded. Termination can leave other initiated requests without durable records, so total initiated requests remain unknown. The candidate fractions describe censored subsets and supply no full-workload acceptance estimate. No complete `run.json` was synthesized, no comparison passed, and the 80% requirement and minimum three trials remained intact. The different model, precision, runtime and output limit also prevent treating these partial outcomes as a controlled improvement over the separate 0.6B vLLM experiment.

The guard stopped only its owned collector and servers, released its leases and retained the original caps. The cleanup receipt checked all six owned PIDs absent and all four loopback ports closed. The first wrapper's outer exit zero remains recorded alongside the actual thermal failure and collector exit -15; the corrected second wrapper propagated exit 3. A new sustained experiment needs a consequential changed operating condition and an explicit new protocol. The offline verifier checks the complete manifest, exact raw-to-grade joins, thermal telemetry and retained cleanup evidence. Board power samples remain board observations; these failures establish no facility energy, provider SLA, full-cost result or qualified serving recommendation.

The source archives retain their supplied MIT, HumanEval and EvalPlus license notices and publication reviews. They exclude model weights, runtime binaries, compiler installations and container layers while retaining exact source/build/runtime identities. The broader accelerator, provider-operation and full-cost outcome remains open.

## Explicit grading revisions and current workbench

The [external grading contract](EVALPLUS-BRIDGE.md) separates acquisition identity from a later application acceptance definition. Both arms must bind the same selected contract to their original workload and exact response hashes. Revised outcomes receive a distinct workbench comparison identity while original capture and grade receipts remain intact. The fixture contract changes normalized output and verifies that both SecondRun observations are reused; mismatched contracts produce an incomparable verdict. A separate retained-vLLM replay changed the normalizer source digest while confirming byte-identical normalized samples before reusing the original independent evaluator outcomes. That replay retained 21/96 accepted observations per arm, the original 80% floor and no eligible configuration, with zero new inference or independent grader execution.

The delivered workbench adds atomic publication of saved records and a scoped operational evidence interface. The public kit supports collecting and importing operations on recipient-owned resources. Its independently exercised loopback protocol completed 18/18 requests; it produced no inference or application-success claim. Installations with the retained owned-host source closure additionally reverify their original peer-command, storage and controlled-recovery records. The public projection and exact dependency digest are recorded in `public/open-compute/WORKBENCH-RELEASE.json`.
