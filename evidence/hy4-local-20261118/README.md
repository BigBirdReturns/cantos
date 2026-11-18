# Hy4 flash on our own hardware, 2026-11-18

Tencent's Hy4 flash ran end to end on hardware we own, through the Cantos maintainer instrument at commit
`22ce99c`. No rented capacity was used. Before these runs the Hy4 experiment in this repository had sent
zero requests to the model.

## Results

| Run | Hardware | Result |
| --- | --- | --- |
| Publisher 3-bit GGUF build, 32 fixed HumanEval+ tasks, three trials | two Quadro RTX 8000 | 93 of 96 accepted: 31 of 32 in every trial. EvalPlus base tests 1.000, base plus extra tests 0.969. No capture errors. |
| Same build, the four Hy4 smoke cases, three trials | two Quadro RTX 8000 | 12 of 12 accepted, about 31 tokens per second decode. |
| Exact BF16 (441 GB) and FP8 (287 GB) payloads, the four smoke cases, three trials each | processors only: 2 x Xeon Platinum 8276L, 2 TB memory, no accelerator | 12 of 12 accepted on each arm, identical answers. Maintainer verdict under the pinned policy: **pass**. |

On the same 32 tasks and the same pinned grader, the Qwen3-0.6B runs published in
`compute/maintainer/evidence/vllm-humaneval-20261118.zip` accepted 7 of 32 per trial.

Gross GPU board energy for the coding run was 118,460 J over the 457 s capture window, 1,274 J per accepted
task. That covers both boards at one-second sampling, uncalibrated, including thermal pauses and gaps between
requests. It leaves out processors, memory, the grader and wall losses.

`RESULTS.json` holds the same facts in machine-readable form.

## What this shows

- Hy4 flash executes on hardware outside the publisher's documented accelerator list, and does real work there:
  31 of 32 fixed coding tasks, repeatedly, on two cards from 2018.
- The pinned BF16 against FP8 comparison runs end to end through the instrument on a machine with no accelerator.
- All 148 weight files of each exact payload, and both GGUF files, match the publisher's SHA-256 values.

## What this does not show

- Whether FP8 costs accepted work against BF16. The four smoke cases test transport, answer extraction and
  acceptance wiring; any working copy of the model passes them. The coding run used one arm, the 3-bit build.
- Anything about the vendor vLLM recipe, H200-class hardware, or serving speed. Request times in the coding run
  include thermal pauses; the processor arms take 20 to 170 seconds a request.
- Thinking mode. Every request used `reasoning_effort: no_think`.
- Whole-system energy. No power was measured on the processor arms.

## How the exact arms differ from the pinned recipe

- Runtime: the publisher's transformers model code (pull request 50903, commit `c2ec8505`) on processors behind
  `exact-arms/scripts/serve_hy4.py`, not the pinned vLLM image on eight H200s.
- Arithmetic: float32 on both arms. BF16 weights widen exactly. The vendor path computes in BF16.
- Client timeout 600 s, not 120 s. That is the largest value the instrument accepts.
- The arms were captured one after the other, BF16 then FP8, because both do not fit in memory together as
  float32. Each arm received one readiness request before its capture.

### The FP8 arm is an emulation

At this commit the library's processor fallback for the FP8 checkpoint does not produce a runnable model: its
first request failed, and its load report shows the experts' scale tables and 41 gate weights unapplied
(`exact-arms-first-capture/fp8-library-fallback-attempt/`). The server therefore loads the model structure from
the BF16 files and overwrites every parameter from the FP8 checkpoint:

- 1,832 of 1,832 model parameters overwritten, none unmapped.
- 205 FP8 tensors multiplied by their checkpoint block scales with the library's own dequantize routine. Their
  cosine similarity to the BF16 weights is 0.9994 to 0.9997.
- The other 1,672 tensors are bit-identical to the BF16 release.
- The inputs of the 123 linear layers and 41 expert blocks whose weights are FP8 are rounded through FP8 before
  each multiply, with the scaling of the `kernels-community/finegrained-fp8` kernels: per row, per block of 128
  along the input, scale = max|x| / 448.

This reproduces the FP8 arithmetic in float32. It is not the vendor kernels, which need a supported accelerator.

The first capture (`exact-arms-first-capture/`) returned the same answers but the verdict `incomparable`,
because our server printed the arm in its version string. `exact-arms/` is the second capture with one version
string on both arms.

## How the card runs were served

- `AngelSlim/Hy4-flash-GGUF` revision `f8def04a`, files `Hy4-flash-Q3_K-0000{1,2}-of-00002.gguf`.
- llama.cpp pull request 32517 at commit `0a054d0b` (unmerged), CUDA build for compute capability 7.5.
- Both cards with their existing power limits. In the coding run `coding-tasks/scripts/guard2.py` paused the
  server at 76 C and resumed it at 68 C: nine pauses, 168 s, peak 76 C.
- Deviations from the protocol of the session that defined the coding workload are in
  `coding-tasks/spec/DEVIATIONS.json`.

## Files

- `coding-tasks/`: spec, raw capture, prepared samples, grader output and log, bound grades, board power.
- `gguf-smoke/`: spec, raw capture and board power for the smoke cases on the cards.
- `exact-arms/`: spec, both raw captures, analysis and verdict, server status with load accounting, payload
  checksum reports, scripts.
- `exact-arms-first-capture/`: the superseded first capture and the failed library fallback.
- `LICENSE-HUMANEVAL.txt`, `LICENSE-EVALPLUS.txt`: licences of the task data retained with the coding run.

## Check it

```bash
cd evidence/hy4-local-20261118 && sha256sum -c SHA256SUMS.txt
python -B compute/maintainer/maintainer.py analyze \
  --baseline evidence/hy4-local-20261118/exact-arms/run2/observe-bf16/run.json \
  --candidate evidence/hy4-local-20261118/exact-arms/run2/observe-fp8/run.json \
  --policy evidence/hy4-local-20261118/exact-arms/run2/spec/policy.precision.json \
  --out /tmp/hy4-reanalysis
```

`analyze` replays the retained streams and regrades them without sending requests.
