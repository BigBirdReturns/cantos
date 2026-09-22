# Proposed first gift: one customer-workload comparison with a rerunnable receipt

Status: DESIGN / NOT EXECUTED. Free development/reporting scope; cloud capacity, customer data, publication and billable resource use require separate explicit authorization. Use an isolated approved VM or authorized existing raw runs, not production driver changes or customer traffic interception.

## The customer question

For a specified coding-assistant workload, how many accepted requests or completed tasks can a customer obtain per dollar while meeting the chosen latency and quality requirements? Start with one Hot Aisle MI300X VM and the model used in their own OpenCode guide: `Qwen/Qwen3-Coder-30B-A3B-Instruct`. This is a documented deployment example, not a universal recommendation or a performance result reproduced here. Model revision, tokenizer, representation and complete runtime/container digest must be fixed at campaign admission.

The guide warns that a tag called `rocm/vllm:latest` can point to an old build. Pin actual digests and retain ROCm/vLLM/driver/kernel versions. Use the least privilege required by the admitted runtime; this plan does not instruct running their tutorial's privileged deployment template on an occupied machine.

## Bounded scope

One workload, one primary Hot Aisle topology, one applicable competitor topology, one recipe and one public-ready comparison packet. Choose the counterpart the prospective customer would actually purchase, include its full billable GPU allocation, and record availability and quote terms. Any extra memory-stress workload, MI355X qualification or continuous re-testing is a separate scope. MI355X expansion plans are not evidence of currently available hardware.

1. Pin both systems and the agreed acceptance criteria before collecting performance. Use the same model representation, tokenizer, workload and quality gate for the controlled comparison. Hardware-specific supported kernels are recorded. A later separately labelled best-tuned-service comparison may permit different configurations if both meet the same quality target.
2. Use vLLM's serving benchmark for reproducible timing and per-request output; preserve tool version and the exact command. Its `--goodput` option applies request-latency objectives. Task correctness still needs an independent validator. Do not relabel latency-goodput as correct-task throughput.
3. Proposed diagnostic sweep: 2,048 and 16,384 input-token profiles, 256 output tokens, concurrency 1/8/32 as a bounded initial scan. These are proposed profiles, not a claim of actual customer traffic. Follow with an open-loop arrival-rate test of the admitted customer profile to expose queueing and overload. Report attempted requests, timeouts, errors, invalid responses, output length and truncation, and all repeats. Do not erase failed cells or tune the comparison from one unusually fast trial.
4. A small held-out tool/structured-output fixture can test exact validity and correctness at request level. Report both sides' pass rates and confidence limits. Coding-agent task claims require a separate fixed task set, equal tool/attempt budgets, isolated tests and outcome adjudication. Do not count requests as completed coding tasks.
5. Run and record cold start, ready-state load and a stop/recreate test separately. Freeze warmed caches/prefix reuse policy on both sides; report cold and warm paths separately. Timing begins at a declared clock boundary and uses monotonic elapsed time. Maintain enough client headroom that the driver does not cap server throughput.
6. Repeat complete measured trials. Keep the run count, exact windows and dispersion. Three runs can identify gross instability but cannot support a general reliability claim or a long-horizon availability percentage. Bootstrap at a justified independent unit; do not treat correlated requests as independent confidence evidence.
7. Record every billable interval, allocated GPU, readiness transition and extra cost. Produce a steady-state efficiency number and a separate scenario/actual-bill number. Billing policy can differ from readiness; Nebius Token Factory, for example, documents unbilled provisioning and replica restart periods. Compare its managed features separately from raw VM rentals.
8. A second operator reconstructs the cost and acceptance calculations from the retained raw evidence, without access to producer-only dashboards. Mutating a result, deleting a trial or changing a price must invalidate the bound report or visibly create a new version. This checks report derivation; independently rerunning hardware requires a separately recorded event.

## The three free deliverables

A public result page: workload, exact hardware/model/software, accepted work per dollar, tail latency and correctness/failure rates. Every headline links to the methodology and portable receipt. Produce price-only, producer-run and independently reproduced states visibly; publish an inconclusive result when warranted.

A customer sizing note: the measured operating region where the recipe meets its acceptance and latency requirements, total allocation cost and observed bottleneck. Keep interpolated or estimated regions separate. Turn a customer's stated workload into a bounded trial/quote, not a universal ranking of GPUs.

A recipe and evidence packet: model/revision/hash identities where permitted, container/runtime digests, declared host requirements, workload fingerprint, sanitized telemetry, raw timing/acceptance outputs, applicable price snapshot or redacted actual invoice, manifest and exact recomputation instructions. Keep credentials, internal addresses and customer material private; publish only explicitly permitted derivatives.

## Headline templates after data exists

- "[Workload/model/precision]: $[x] per 1,000 accepted requests, with [p95/p99 latency] at [arrival rate / concurrency]. [n] complete runs; [failure rate]; $[allocation charge]/hour."
- "For this pinned workload, the qualified Hot Aisle configuration delivers [ratio] accepted requests per dollar versus [exact comparable allocation and billing basis]. Raw runs and reproduction recipe attached."
- "[N] fixed coding tasks, [M] accepted within the same attempt budget; $[total paid cost]/accepted task. Transport/JSON validity alone does not count as task success."

None of these is a measured headline in this starter. An AMD loss or no-advantage cell remains part of the record.

## Higher-value follow-on experiment

For repeated customer work, compare a qualified retained procedure or rule against repeated model inference, while preserving the same acceptance and invalidation gates. Count the first-run compilation, verification and maintenance cost. This tests the Second Run thesis and may reduce required cloud work; do not make this the initial GPU-vendor comparison or assume savings in advance.

## Primary sources, reviewed 22 September 2026

- Pricing: https://hotaisle.xyz/pricing
- Hot Aisle operating model and July 14 price change: https://hotaisle.xyz/blog/why-we-raised-our-mi300x-price
- Existing customer deployment: https://hotaisle.xyz/blog/opencode-vllm-hotaisle
- Their current benchmark index: https://hotaisle.xyz/benchmarks-and-analysis
- Historical sponsored test, 9 October 2024: https://dstack.ai/blog/amd-mi300x-inference-benchmark/
- Comparator AI Cloud prices: https://nebius.com/prices
- Managed endpoint billing: https://docs.tokenfactory.nebius.com/ai-models-inference/dedicated-endpoints/billing-policy
- Serving benchmark output and goodput options: https://docs.vllm.ai/en/latest/cli/bench/serve/
