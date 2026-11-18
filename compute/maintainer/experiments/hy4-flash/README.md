# Hy4 Flash readiness and pinned experiment

**Status: blocked on the observed OCTO-W03 environment.** This package verifies released model identities, publisher shard manifests, container metadata, native Cantos input contracts and the actual hardware inventory. It records zero Hy4 inference requests and zero Hy4 energy measurements. It downloaded public metadata only. It does not install software, download weights or container layers, reserve devices, launch a server, change power settings, or send requests to a model endpoint.

## Exact comparison

| Arm | Published repository | Revision | Weight payload bytes |
| --- | --- | --- | ---: |
| Instruction BF16 baseline | [tencent/Hy4-flash](https://huggingface.co/tencent/Hy4-flash) | d88c9dfd96ba4f2e6b92adba0b8e8f1c8696f959 | 440,521,065,214 |
| Instruction FP8 candidate | [tencent/Hy4-flash-FP8](https://huggingface.co/tencent/Hy4-flash-FP8) | 003107fa248f5892064ab1c43af0a7003dd68c9b | 287,073,390,118 |
| Separate pretrained Base | [tencent/Hy4-flash-base](https://huggingface.co/tencent/Hy4-flash-base) | 95b9f8239e2f63cb837c91704f070ae47332ebdf | 438,829,681,356 |

The primary experiment compares the published instruction BF16 and FP8 variants. Their tokenizer and chat-template Git blob identities match. FP8 versus Base also changes training stage; it cannot isolate quantization. The Base entry remains a separate, unconfigured task-fit proposal. Publisher provenance does not independently establish an identical underlying posttraining trajectory between released checkpoints.

The exact 148/148/139 shard closures and publisher SHA256 values live in model-manifests/. These are publisher metadata, not locally verified weight payloads. The native template deliberately leaves its local weights-manifest hash, physical device identities, effective caching and runtime controls unbound. Cantos prepare refuses both arms until those declarations are replaced in an operator copy.

## Serving requirements and observed blocker

The [vLLM recipe](https://recipes.vllm.ai/tencent/Hy4-flash) identifies a dedicated image and Hopper/Blackwell data-center hardware. It does not currently qualify AMD Instinct or a generic released vLLM wheel for this architecture. The retained canonical recipe selects eight H200 GPUs with tensor parallelism 8, BF16 compute, an 8192-token context limit, four sequences and 8192 batched tokens. DFly speculation is disabled for both primary arms so it does not add another changed factor. Eight H200s describes this retained configuration; the package establishes no universal minimum GPU count.

The registry manifest-list digest is:

    vllm/vllm-openai@sha256:6b645bfbf4b89602d38f6e93c1c418516ec0bfbf54b64cd661b8075bfec01da1

The amd64 manifest is f4c3ca45840d5612d673b9723f8a82740707a2e5ff06c02df03246f4276a7c69. The arm64 manifest is 5e2c1badbca60595d6591c60feb4b8547f59da96e7a91710d40239250e721aba. Registry layer sizes sum to 9,943,497,064 compressed bytes for amd64; extracted disk usage remains unmeasured.

At 2026-11-18T05:35:12Z, W03 exposed two Quadro RTX 8000 GPUs with compute capability 7.5 and 49,152 MiB each. Host RAM totaled 132,342,702,080 bytes. Local Docker inspection reported the pinned image absent. Both GPUs had memory allocated by other work. This package's collection did not start that work. The observed GPUs do not match the documented accelerator families or the retained eight-H200 recipe.

Engram tables default to host-memory offload. The recipe's approximate 529 GB BF16 / 345 GB FP8 hints derive from download bytes multiplied by 1.2; they are not measured GPU allocation minima. Host RAM, GPU allocation peaks, interconnect behavior and target concurrency require actual qualification. A 1,048,576-token advertised context does not establish operational capacity at that length. The retained smoke is text-only and short-context.

## Read-only preflight

From the repository root:

    python -B compute/maintainer/experiments/hy4-flash/preflight.py

This verifies retained source bytes and publisher weight manifests, calls the existing native workload/protocol/policy validators, confirms intentional native-template refusal, and replays the dated hardware snapshot. To inspect current local OS/GPU/container metadata:

    python -B compute/maintainer/experiments/hy4-flash/preflight.py --live

Exit 2 means blocked or unqualified readiness; exit 3 means invalid evidence or input. No exit value from this preflight certifies a running model. The JSON includes observation time, evidence scope, every specific hold and ready_to_launch=false. A synthetic compatible inventory also remains blocked by absent local weight verification and unbound deployment identity.

## Native experiment contract

spec.precision.template.json uses cantos.maintainer.spec/1. It references the genuine native policy and workload schemas. The four authored exact JSON cases test transport, answer extraction and acceptance wiring. Three trials, one repetition and concurrency one define 12 measured task attempts per arm, before any future retry-campaign extension. These cases do not establish application-population quality or an efficiency ranking.

The shared request uses reasoning_effort=no_think and top_p=1. The native collector supplies its fixed temperature=0; this is a declared deterministic smoke configuration, distinct from Tencent's recommended sampling settings. The policy requires all four cases to pass and rejects new failures. Performance and price gates are disabled or unconstraining because this smoke supplies no representative performance claim. Prices remain unknown.

The composed release supplies the separate [retry campaign](../../RETRY.md) and [resource join](../../RETRY-RESOURCES.md). Copy retry-policy.json beside the operator-bound spec to declare up to three attempts, 0.25-second backoff and the same seed on each fresh conversation. The campaign inserts no correctness feedback. Use retry.py run --spec YOUR_BOUND_SPEC --arm baseline --retry-policy retry-policy.json --out NEW_BASELINE --observation-id UNIQUE_BASELINE and a separately identified candidate campaign under the same policy. Endpoint lifecycle and full-window telemetry remain explicit. These instructions add no unsupported retry keys to the original native spec. The local Qwen instrumentation qualification demonstrates the retry path; this Hy4 package still records zero Hy4 execution.

After hardware/runtime/weights qualification, copy the template, workload and policy into an experiment directory outside the source checkout, bind actual identities and run the native prepare operation. Endpoint URLs default to loopback and require an operator-owned arrangement. Two simultaneous endpoints on the same GPUs would confound contention; a sequential same-allocation comparison or separate fully identified equivalent allocations requires explicit lifecycle control outside this package.

The real experiment must preserve the original fixed task population and acceptance rule; first-pass success, retries, failures, visible answer timing, token usage and energy remain distinct evidence. All failed work belongs in total-work accounting. With zero accepted tasks, per-accepted-task ratios remain undefined. GPU-board joules exclude CPU, host RAM, networking and wall losses, which matter for Engram offload. Whole-system energy requires independently measured system coverage.

## Exact command proposals

The unmodified vendor JSON argv and Docker argv are retained in snapshots/bf16.recipe.json and snapshots/fp8.recipe.json. The canonical API selector for BF16 is variant=default; variant=fp8 selects FP8. Both retained requests returned no parameter adjustments.

render_recipe.py prints a proposed command using the pinned container digest, a read-only local snapshot mount, offline HF/Transformers settings, eight explicit GPU UUIDs and a loopback API port:

    python -B compute/maintainer/experiments/hy4-flash/render_recipe.py \
      --variant instruct-fp8 \
      --snapshot /absolute/operator-verified/fp8-snapshot \
      --gpu-uuids GPU-UUID1,GPU-UUID2,GPU-UUID3,GPU-UUID4,GPU-UUID5,GPU-UUID6,GPU-UUID7,GPU-UUID8 \
      --port 8000

The UUID example is intentionally invalid until replaced with eight actual distinct UUIDs. This program prints JSON and shell text; it never executes Docker. It omits the vendor example's privileged flag and records that adaptation explicitly. Its deployment behavior remains unqualified. The image and local model must already exist; --pull=never and offline model settings prevent the command proposal from implicitly fetching them.

## Provenance and terminal conditions

sources.json records source URLs, retrieval times and SHA256/byte receipts for retained factual metadata. The Tencent README is pinned to commit 7ab20f35602b1d3fc863f85aee20cb87eb8e53c5; its response hash is retained without republishing the whole document. Official recipes are mutable, so their exact retrieved JSON bytes are included. Docker registry metadata and pinned HF revisions bind the variants independently of mutable tags.

hardware-observed.json is a dated read-only observation. READINESS.json records package verification and native job identities. Tests cover source tampering, native schema preparation/refusal, unsupported GPUs, a synthetic compatible inventory that still cannot claim readiness, and offline pinned command rendering. The synthetic fixture is explicitly labelled and supplies no live deployment evidence.

This scope closes when package provenance, schema use and refusal behavior are verified. Hy4 deployment remains open until a compatible allocated machine, locally verified payloads, actual runtime/kernel startup, accepted streamed smoke and applicable telemetry coverage produce their own source-bound receipts. No performance, energy, retry or competitor-displacement result follows from this package.
