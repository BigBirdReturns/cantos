# Efficiency: inefficiency hunted in the imported market data, and the ten largest measured

Built 2026-09-29. Producer for sections 1-6 is **imported** (third-party data we retained; not our measurements, not provider quotes); the ranked list at the end also uses our own runs and marks which. Every number traces to a file and script in this folder and to a row in `findings.jsonl` (ids `M01`..`M14`, `T01`..`T21`). Evidence class is `derived` throughout sections 1-6: arithmetic on imported rows, with the keyword and matching rules stated. Imported rows cannot be `measured` by us; MANUAL.md's `published_claim` is the class of the underlying rows.

Inputs and hashes. InferenceX: `sessions/public-tail-20260929/lanes/inferencex-history/imported-main/inferencex-2026-09-29.jsonl` (1,268,669,867 bytes, sha256 `1eab076241673432f84802d83597161aeb31420c95a87b49ae4b64accf69bf2f`, 288,891 metric lines = 16,542 source rows, streamed by `ix_extract.py`; the hash equals the pointer file in `hot-aisle/campaign/backfill/imported/`). Prices: `.../opencomputeprices/rows/prices.jsonl` (1,689,060 rows, sha256 `390b25b1...73bd0`, equals MARKET.md). Issues: `.../github-issues-deep/rows/issues.jsonl` (37,075 issues, sha256 `c16661e1...e1ef0`). Reviews: `sessions/clustermax-cloudreview-20260929/claims.all.jsonl` (1,273 claims, sha256 `2c61f975...016f`). Incidents: `main/clustermax-challenge/retrospective/incidents/*.json` (25 provider files).

## 1. InferenceX: the same scenario under different frameworks (M01-M04)

**Method.** A key is (hardware, model, scenario, ISL, OSL or dataset, concurrency, precision). For each key with two or more frameworks reporting `output_throughput_per_gpu`, take each framework's best row and report best-framework / worst-framework. "Best row" may differ in TP, EP, GPU count, disaggregation and speculative decoding, so this is the spread a shop leaves on the table by not sweeping the stack, not a framework-only effect. 2,282 keys exist; 269 have two or more frameworks; 262 report the metric.

| Variant | Keys | Median | p25 | p75 | p90 | Max | Share >= 1.5x | >= 2x | >= 3x |
|---|---|---|---|---|---|---|---|---|---|
| All keys | 262 | **1.440x** | 1.131 | 2.079 | 3.919 | 84.897 | 47.3% | 28.6% | 16.4% |
| Clean (error-dropped records <= 5%) | 246 | 1.441x | 1.132 | 2.119 | 4.008 | 84.897 | 47.6% | 29.7% | 16.7% |
| Clean and best rows created <= 7 days apart | 129 | 1.543x | 1.192 | 2.119 | 9.155 | 53.154 | 50.4% | 30.2% | 20.2% |
| Like-for-like (clean, <= 7 days, identical TP/EP/GPUs/disagg/speculative) | 35 | **1.259x** | 1.093 | 1.400 | 1.478 | 2.119 | 11.4% | 5.7% | 0% |

Reading: the framework-and-config decision moves per-GPU throughput by a median 44% on the same silicon and model; framework alone (identical parallelism) moves it a median 26%, with a ceiling of 2.1x. The tail (tens of x) comes from rows that look like failed or badly configured runs (for example H200 GLM-5.2-FP8 agentic c3: dynamo-sglang 5.5 vs sglang 0.1 tok/s/GPU on 16 vs 8 GPUs) and should not be quoted as a framework fact. Most common best/worst pairs: atom over vllm (60 keys), vllm over sglang (28), sglang over vllm (27), sglang over sglang-disagg (20).

### By requested SKU

| SKU | Keys (all) | Median | Max | Keys (clean, <= 7 days) | Median | Max |
|---|---|---|---|---|---|---|
| H100 | 1 | 1.65x | 1.65x | 1 | 1.65x | 1.65x |
| H200 | 21 | 1.25x | 53.15x | 18 | 1.22x | 53.15x |
| B200 | 27 | 1.53x | 35.38x | 16 | 1.52x | 35.38x |
| MI300X | 6 | 2.29x | 36.06x | 4 | 12.56x | 36.06x |
| (MI355X, for scale) | 143 | 1.44x | 13.44x | 63 | 1.79x | 13.44x |

Cases: H100 has one comparable key (DeepSeek-V4.1-Flash fp4 agentic c1: vllm 17.3 vs sglang 10.5 tok/s/GPU). B200: DeepSeek-V4.1-Flash fp4 agentic c32, vllm 584.9 vs sglang 63.9 (9.15x); DeepSeek-V4-Pro agentic c16, vllm-router 141.2 on 2 GPUs (tp2 ep8 disagg mtp) vs sgl-router 4.0 on 16 GPUs (35.4x, different topology). MI300X has only six comparable keys: Qwen3-0.6B fp16 128/32 at c1 and c4 (vllm 463.6 and 1,346.0 vs atom 12.9 and 56.7 tok/s/GPU, atom on 2 GPUs; a toy model, not a serving fact) and Qwen3.5-397B-A17B-FP8 agentic-256k at c1/8/16/32 (sglang vs sglang-disagg 1.01x to 2.89x, with the winner changing by concurrency). The public record cannot choose a framework for MI300X or H100.

### Success rate (agentic-coding)

The published success rate is profiled/total records and includes warmup drops (IMPORT-SUMMARY: "not an error rate"). On the 117 agentic keys with two or more frameworks, the spread between frameworks is a median 2.6 points (p90 24.2, max 65.1) on that definition, but only a median 0.05 points (p90 8.31, max 36.0) when counting error-dropped records alone. Group-level rates from IMPORT-SUMMARY (all scenarios mixed, so indicative): H100 agentic sglang 80.74% vs vllm 95.02%; H200 agentic 24.00% (sgl-router), 38.55% (sglang), 56.84% (dynamo-sglang), 78.42% (vllm); B200 agentic 71.84% (vllm) to 98.21% (tilert); MI300X agentic sglang 76.33%, vllm 84.16%, sglang-disagg 94.68%. Fixed-sequence rows are almost always 100% or "unknown".

## 2. Prices: the same SKU across providers, July 2026 (M05-M07)

**Method.** On-demand rows with `snapshot_ts` in 2026-07 (through the last snapshot, 07-29), 93,534 rows for H100/H200/B200/MI300X; median per provider over all its rows and sources; then dispersion across provider medians. `together` is excluded from the primary view because its own-feed rows are $100 (H100) and $200 (H200, B200) per GPU-hour against $3.99, $5.99 and $8.19 for the same provider in the getdeploying feed: a 24-33x unit artefact that I flag and do not correct. Figures with it included are given beside.

| SKU | Providers | Median of provider medians | p10 | p90 | **p90/p10** | Min (provider) | Max (provider) | Max/min | Incl. Together: max/min |
|---|---|---|---|---|---|---|---|---|---|
| H100 | 41 (42) | $2.99 | $1.95 | $6.25 | **3.2x** | $1.50 (gpuai) | $12.84 (azure) | 8.6x | 66.7x |
| H200 | 32 (33) | $4.25 ($4.29 incl.) | $2.45 | $8.75 | **3.6x** | $2.25 (amaya) | $14.88 (massedcompute) | 6.6x | 88.9x |
| B200 | 22 (23) | $6.45 ($6.49 incl.) | $4.13 | $12.50 | **3.0x** | $3.74 (boostrun) | $42.20 (massedcompute) | 11.3x | 53.5x |
| MI300X | 7 | $3.04 | $1.99 | $6.00 | **3.0x** | $1.99 (digitalocean, hot_aisle tie) | $7.86 (azure) | 3.95x | same |

One-GPU rows only (excl. Together): H100 38 providers median $3.12, p90/p10 5.1x, $1.50 to $11.06 (thundercompute); H200 27, $4.29, 2.6x, $2.27 to $14.88; B200 18, $6.76, 2.7x, $3.75 to $42.20; MI300X 6, $2.62, 1.7x, $1.99 to $6.00 (oracle). MI300X July provider medians: DigitalOcean $1.99, Hot Aisle $1.99, RunPod $2.19, Cyfuture AI $3.04, Crusoe $3.45, Oracle $6.00, Azure $7.86. Hot Aisle's $1.99 is the July monthly median; the price was $2.99 from 07-27 (T13). Hyperscalers and marketplaces sit at the top; the middle 80% is a 3x band for identical silicon.

### Aggregator disagreement for the same provider and SKU (1-GPU rows, July 2026)

Of 26 provider-SKU pairs listed by two or more sources, 8 differ by 1.5x or more.

| SKU | Provider | Source medians ($/GPU-h, rows) | Ratio |
|---|---|---|---|
| H200 | Together AI | getdeploying 5.99 (36); together 200.00 (39) | 33.4x |
| H100 | Together AI | getdeploying 3.99 (36); together 100.00 (39) | 25.1x |
| B200 | Together AI | getdeploying 8.19 (34); together 200.00 (78) | 24.4x |
| H100 | MassedCompute | shadeform 2.73 (29); massedcompute 10.92 (594) | 4.0x |
| **H100** | **DigitalOcean** | **getdeploying 3.39 (29); skypilot 6.74 (54)** | **1.99x** |
| MI300X | RunPod | runpod 1.34 (108); skypilot 2.19 (29); getdeploying 2.19 (29) | 1.63x |
| H200 | vast.ai | vastai 3.75 (458); skypilot 2.35 (29) | 1.60x |
| H100 | RunPod | runpod 2.79 (324); skypilot 2.99 (87); getdeploying 1.99 (29) | 1.50x |

DigitalOcean's H100 appears at three prices: $3.39, $6.74 and the $4.41 on the pricing page used in Run 3; its MI300X appears at $1.99 in the series and $2.59 in the staged table cited by DISCLOSURES. Shapes (e.g. a multi-GPU instance divided by count) were not resolved, so a share of these gaps may be shape, not disagreement.

### Row median vs provider median

| SKU | Row median | Provider median | Ratio | Rows |
|---|---|---|---|---|
| H100 | $8.99 | $2.99 | 3.0x | 59,582 |
| H200 | $8.39 | $4.29 | 2.0x | 20,329 |
| B200 | $8.06 | $6.49 | 1.2x | 12,701 |
| MI300X | $2.19 | $3.04 | 0.72x (row median is lower: RunPod supplies 378 of 922 rows) | 922 |

Any single "market price" hides the weighting that made it (the lane REPORT's 9.0 vs 3.0 for H100 reproduces exactly).

## 3. Failures every shop re-hits: engine issues (M08-M10)

**Method.** `github-issues-deep`: 37,075 issues (vLLM 15,175 from 2024-07-12; llama.cpp 10,217; SGLang 7,640; TensorRT-LLM 4,043), issues only. Error classes are the lane's regex on title+body (first match; NCCL is inflated in vLLM by environment dumps that mention NCCL). Spec-decode and prefix-cache clusters are my regex on the **title** only (rows retain no body), so they are lower bounds.

| Class (first match) | vLLM | llama.cpp | SGLang | TRT-LLM | Total | Median days to close, completed | Closed as not_planned |
|---|---|---|---|---|---|---|---|
| build | 1,842 | 1,934 | 1,623 | 711 | 6,110 | 15.3 | 16.3% |
| NCCL (mentions) | 4,103 | 32 | 668 | 217 | 5,020 | 6.4 | 38.5% |
| crash | 732 | 1,607 | 356 | 306 | 3,001 | 12.8 | 22.4% |
| accuracy | 833 | 642 | 712 | 226 | 2,413 | 22.9 | 19.4% |
| performance regression | 815 | 713 | 303 | 158 | 1,989 | 20.7 | 30.4% |
| install | 743 | 411 | 329 | 234 | 1,717 | 16.2 | 26.3% |
| timeout | 486 | 412 | 608 | 125 | 1,631 | 28.4 | 20.2% |
| OOM | 587 | 292 | 302 | 125 | 1,306 | 13.7 | 29.9% |
| CUDA error | 578 | 318 | 206 | 156 | 1,258 | 13.4 | 27.3% |
| illegal memory access | 312 | 80 | 191 | 40 | 623 | 25.0 | 25.0% |
| other | 4,144 | 3,776 | 2,342 | 1,745 | 12,007 | 32.8 | 23.8% |

All ten named classes occur in all four engines. Counting an issue in every class it matches (any-match), crash 18,461, build 14,580, install 7,632, CUDA error 5,998, NCCL 5,568, performance regression 3,616, timeout 3,564, accuracy 3,285, OOM 1,344, illegal memory access 623.

**Clusters named in `lanes/github-issues/REPORT.md`.**

| Cluster (title regex) | vLLM | SGLang | llama.cpp | TRT-LLM | Total | Still open | Median days to close (all closed) |
|---|---|---|---|---|---|---|---|
| Speculative decoding / MTP / draft / EAGLE | 783 | 435 | 255 | 135 | **1,608** | 440 | 57.1 (vLLM 92.9, TRT-LLM 78.2, SGLang 60.6, llama.cpp 26.4) |
| Prefix cache / APC / radix | 231 | 149 | 5 | 12 | **397** | 125 | 60.5 (TRT-LLM 138.8, vLLM 120.6, SGLang 50.5, llama.cpp 0.0) |

The lane's five worked examples (vLLM #53142 prefix-cache resume crash, #53912 prefix cache + MTP corruption, #56443 spec-decode assert; llama.cpp #27282 and #26558 MTP failures) are in `findings.jsonl` M09.

**Open-to-close by class.** Over all 32,123 closed issues the median is 45.3 days, but that mixes three outcomes: `completed` 23,907 issues at a median 18.8 days, `not_planned` 7,980 at 121.8 days, `duplicate` 236 at 0.2 days. vLLM closed 5,881 of 12,625 (46.6%) as `not_planned`. The table above uses completed-only medians. A closed issue is not a verified fix (fix references exist for 217 issues).

## 4. Reviews: shortfalls repeated across providers (M11)

**Method.** ClusterMAX cloud-review claims (verbatim quotes; 85 providers, 1,273 claims, 483 with stance -1 = negative, in 72 providers). Provider = the slug in the claim id. Themes are keyword matches on the quote (a quote can match several themes, and a match can be a mention rather than a shortfall); the page text is ClusterMAX 2.0 (published 2025-11-06). SemiAnalysis's legal notice restricts financial use of ratings; these are text statistics only.

| Repeated shortfall | Providers (of 72 with a negative claim) | Quotes |
|---|---|---|
| Slurm setup / scheduler gaps | **34** | 64 |
| Monitoring / observability / dashboards | 32 | 51 |
| Networking / InfiniBand / NCCL | 32 | 50 |
| Node health checks / auto-drain / remediation | 31 | 47 |
| Kubernetes gaps | 28 | 43 |
| Reliability / outages / instability | 25 | 44 |
| Security / compliance attestation (SOC 2, ISO, HIPAA) | 23 | 31 |
| Onboarding / UX / signup friction | 21 | 32 |
| Storage / filesystem | 20 | 28 |
| ssh / root / login-node limitations | 18 | 27 |
| Billing / pricing transparency | 12 | 16 |
| Support / ticket response | 11 | 13 |
| OS image / driver / software stack out of date | 11 | 18 |
| Documentation / tutorials | 7 | 13 |

About 39-47% of the providers with a negative claim are criticised for each of the same five items (Slurm 47%, monitoring 44%, networking 44%, node health 43%, Kubernetes 39%): the "redundant reinvention" is that each neocloud builds and fails these separately.

## 5. Incidents: recurring title patterns across providers (M12)

**Method.** 25 provider files (21 with at least one incident): 2,941 incidents, 1,859 not flagged maintenance. Coverage windows differ (most 2025-01-01 to 2026-09-23/29; several from 2026-01-01; four have no coverage start; CoreWeave and OVHcloud expose 10 items by RSS), and Scaleway alone contributes 1,066 incidents, so counts are not rates: **providers with at least one incident in the class** is the recurrence measure. Multi-label keyword classes on titles; durations are started to resolved for non-maintenance incidents with a resolution.

| Title pattern | Providers | Incidents (non-maintenance) | Median duration (h) |
|---|---|---|---|
| Network / connectivity / DNS / latency | **18** | 311 | 2.35 |
| Generic outage / unavailable / down | 18 | 368 | 3.28 |
| Control plane / API / provisioning / instance create | 16 | 304 | 2.26 |
| Degraded performance / elevated errors | 16 | 266 | 3.78 |
| Storage / volumes / object storage / filesystem | 14 | 151 | 4.95 |
| Console / dashboard / website | 12 | 120 | 1.66 |
| GPU / node / host hardware | 10 | 249 | 4.08 |
| Inference / serverless endpoints | 10 | 94 | 3.25 |
| Authentication / login / account | 9 | 54 | 1.62 |
| Billing / payments | 7 | 25 | 5.49 |
| Kubernetes / Slurm / cluster services | 6 | 59 | 4.95 |
| Scheduled or emergency maintenance (label or keyword) | 16 | 1,018 all (30 not flagged) | 4.58 |

Exact-title matching (numbers and region ids stripped) found no title shared by three or more providers: recurrence is by category, not by wording.

## 6. Demand vs supply: where a shop has no public efficiency anchor on MI300X (M13-M14)

**Anchors on MI300X.** InferenceX MI300X rows cover 11 model names: DeepSeek-R1-0528, DeepSeek-V4-Pro, DeepSeek-V4.1-Flash, GLM-5.2-FP8, Kimi-K2.5, MiniMax-M3-MXFP8, Qwen3-0.6B, Qwen3.5-397B-A17B (and -FP8), Qwen3.8-27B (and -FP8). MLPerf Inference v4.1-v5.1 MI300X LLM summaries cover llama2-70b, llama3.1-70b and -405b, mixtral-8x7b and deepseek-v3. Nothing else. No Llama-3.2/3.3-8B, Gemma, Mistral, Phi or Qwen2.5/Qwen3-Coder row exists on MI300X, and none of them exists in InferenceX on any hardware.

**OpenRouter weekly top 10 (97.09T tokens, 2026-09-29).**

| Rank | Model | Tokens | Anchor on MI300X |
|---|---|---|---|
| 1 | DeepSeek V4.1 Flash | 20.80T | exact: InferenceX vllm agentic-coding, 4 source rows |
| 2 | Space Bunny Alpha | 18.20T | stealth, identity unknown |
| 3 | GLM 5.3 Flash | 13.30T | adjacent version only (GLM-5.2-FP8, sglang) |
| 4 | Hy4 preview | 8.97T | none on any hardware |
| 5 | GPT-5.6 Luna | 8.49T | closed |
| 6 | DeepSeek V4 Flash 0731 | 7.57T | adjacent only (V4.1-Flash, V4-Pro) |
| 7 | MiMo-V2.6-Flash | 6.93T | none |
| 8 | Nemotron 3 Ultra (free) | 5.89T | none on MI300X |
| 9 | GPT-6 Luna | 3.65T | closed |
| 10 | DeepSeek V4 Flash 0423 | 3.29T | adjacent only |

By level: exact 20.80T, adjacent-version 24.16T, none 21.79T, unknown 18.20T, closed 12.14T. Of the 66.75T of identified open-weight volume, 31.2% has an exact MI300X anchor and 67.4% has exact or adjacent; 32.6% has nothing. The exact anchor rests on one framework and one scenario.

**Ollama library (cumulative pulls, top 20 non-embedding of 200 captured = 667.7M).** No model has an exact MI300X anchor. 387.4M pulls (**58.0%**) have no InferenceX or MLPerf row on MI300X: llama3.2 84.6M, qwen2.5 41.3M, gemma3 40.8M, gemma2 33.7M, mistral 33.7M, gemma4 26.0M, llama3 25.4M, qwen2.5-coder 21.9M, phi3 18.2M, llava 15.0M, gpt-oss 13.3M (InferenceX has it on MI355X only), qwen3-coder 9.6M, gemma 8.3M, qwen 7.9M, phi4 7.7M. 280.3M (**42.0%**) are anchored only at a very different size: llama3.1 120.0M (MLPerf 70B/405B; the default pull is 8B), deepseek-r1 93.3M (671B only; default is an 8B distill), qwen3 38.3M (0.6B only), qwen3.5 21.2M (397B only), llama2 7.5M (70B only). Our own workload, Qwen3-Coder-30B-A3B, has no public row on any hardware; Runs 1-3 are the only anchor. Judgement map: `demand_anchor.py`. Caveats: pulls are cumulative and rounded; 40 of 240 Ollama models were not captured; OpenRouter exposes 10 weekly ranks in page HTML.

## 7. The ten largest measured inefficiencies, ranked

**Ordering rule.** Ranked by the size of the measured ratio between the bad and good operating point inside one measured population. Items 1, 4, 5, 6, 8, 9 are from our runs (producer ours; measured, derived or modeled); items 2, 3 and 10 are from imported data (producer imported); item 7 mixes both. Confidence is stated per item; an item with a large ratio and weak provenance ranks by its robust number, not its maximum. "Kit" means the tools already in `hot-aisle/campaign/` (shop-eval `evaluate.sh`, `run3/arm.py` + `grade.sh`, `ledger/`, `availability/probe.py`, `market/`, `shop-eval/counter/`).

| Rank | Inefficiency | Magnitude | Producer / class / confidence | Finding |
|---|---|---|---|---|
| 1 | Serving below the knee of the concurrency curve | Cost per request **23.4x** higher at c1 than c64 on the MI300X ($1.6751 vs $0.0717 per 1,000); 9.3x at c1 vs c32 on the H100 | ours / derived (Run 1, 3 repeats) / high | T14 |
| 2 | Stack and topology chosen without a sweep | Per-GPU throughput best/worst framework: median **1.44x**, p90 3.92x, >= 2x on 28.6% and >= 3x on 16.4% of 262 keys; framework-only (35 like-for-like keys) median 1.26x, max 2.12x | imported / derived / medium | M01, M02 |
| 3 | Buying the same SKU without price discovery | p90/p10 of provider medians **3.0-3.6x** (H100 3.2x, H200 3.6x, B200 3.0x, MI300X 3.0x); min/max 4.0-11.3x excl. Together (H100 8.6x, H200 6.6x, B200 11.3x, MI300X 3.95x) | imported / derived / medium-high | M05 |
| 4 | Output contract and runaway generation | HumanEval+ pass **3.4x** after sanitizing (24.4% to 82.4%); total correct +41.7% (4,371 to 6,192); 67.2% of decode tokens on requests that failed grading; 12.3% of requests (41.0% of tokens) hit the 1,024 cap | ours / measured + post-hoc / high for shares | T15, T07 |
| 5 | Running past the KV pool | Doubling concurrency (c32 to c64) gives **0.477x** throughput and **15.7x** median first-token time; c32 is already at 92% KV | ours / measured / high (preemption unmeasured) | T04 |
| 6 | Capacity sized for the burst | 10-s peak generation throughput is **8.9x** the median (8.0x, 9.5x on other arms); hourly mean is 9.4% of peak; 0 queued requests, KV <= 13.2% | ours / derived / medium (10-s ticks) | T16 |
| 7 | Price of record that nobody can pin down | Same provider, same SKU: **1.99x** (DigitalOcean H100 $3.39 vs $6.74; $4.41 on its page), 4.0x MassedCompute; a +50% list change moved a cost advantage from 46.3% to 19.3%; three tie prices ($1.77, $2.72, $2.73) | imported + ours / derived + modeled / medium | M06, T13, T21 |
| 8 | Unreconciled cost windows and idle seat time | Same 4,336 accepted requests cost **1.57x** more under the widest window ($0.6908 to $1.0845); 23.2% of billed seat time was not scored work (whole-seat +20.7%) | ours / modeled / high on arithmetic, no invoice | T12, T17 |
| 9 | Tuning flag carried across workloads | Forced attention backend: **+46%** req/s on long-context c32 but 1.97x p99 first-token latency and -1.0% accepted on the short MoE; sign depends on workload | ours / measured / medium (one forced repeat) | T01, T03 |
| 10 | Failures and shortfalls rediscovered separately | 1,608 speculative-decoding and 397 prefix-cache issues across four engines (57 and 61 days median to close); 34 of 72 criticised providers cited for Slurm setup, 32 for monitoring and networking, 31 for node health; network incidents at 18 of 21 providers with public incident history; 46.6% of vLLM closures are `not_planned` | imported / derived / medium | M09-M12 |

Just outside the ten: time to ready is 3.7-4.9x time to SSH (T10); 58.0% of top-20 Ollama pulls and 32.6% of identified open-weight OpenRouter volume have no MI300X anchor (M13-M14); the forced backend cuts c1 first-token time 8-13% while throughput does not move (T02).

### What a floor-conforming shop would do differently, and how the kit measures it

1. **Publish the concurrency curve; run at the knee.** Report cost, accepted/s and tail latency at a ladder of concurrencies with the registered gate, and operate at the highest concurrency that still passes it. Kit: `shop-eval/evaluate.sh` already runs c1/c8/c32/c64 x 3 and writes the engine table; add c16/c48 and report the cell ratio (best cell / c1) as a field.
2. **Sweep framework, parallelism and disaggregation on the buyer's model before committing; record the winner's config.** Kit: `run3/arm.py` tiers (T0 auto, T1 declared tune) extended with a framework axis; the ledger keeps image digest and flags; report best-of-sweep and the spread to the runner-up.
3. **Quote with a source, a date and a shape; compare within a source; confirm on the provider page.** Kit: `market/build_price_history.py` + `economics_by_date.cjs` keep every source value; the counter record holds `price_transparency`; publish the tie price computed from unrounded costs.
4. **Fix the output contract before buying capacity.** Stop sequences and sanitizer in the client; report raw and sanitized correctness both, plus the share of requests ending at `length` and the tokens spent on failed requests. Kit: `grade.sh` raw and `posthoc-sanitized/`; add `finish_reason` and token-waste fields to the ledger `work` block (already derivable from `replay/requests.jsonl`, `telemetry_run3_tokens.py`).
5. **Admit by KV tokens, not by request count.** Cap concurrency at a stated fraction of the KV pool and alert on waiting > 0. Kit: `arm.sh` should scrape `vllm:num_preemptions_total` and KV usage each second; run cells at 0.5x/0.9x/1.1x of the pool.
6. **Smooth arrivals or share the seat.** Publish the peak-to-median generation ratio and mean/peak for the actual trace; batch or queue non-interactive work into the troughs. Kit: ledger `sustained` buckets plus the serve.log tick summary (`telemetry_run3_util.py`).
7. **Keep price as a dated input and re-run the arithmetic when it moves.** Kit: `RUN3-ECONOMICS-BY-DATE.jsonl` pattern and `evaluate.sh --rescore <run> <rate>`; publish the window and the date next to every dollar figure.
8. **One boot, one declared window, four fields.** Batch scored arms in one boot, keep the smoke short, and record credit, modeled and invoice per allocation with the billing window named. Kit: ledger schema (`modeled`, `modeled_lower_bound`, `billed_usd`, `credits_usd`) and the builder fix for shared seats that MANUAL.md and RUN3-HOTAISLE-SUMMARY call for.
9. **Test every tuning flag per workload and per tier, interleaved, on both vendors.** Kit: T0/T1 tier design, three interleaved repeats, `client` worker cap above the burst peak so harness limits are not counted as failures.
10. **Adopt the shared floor for the repeated items and canary the risky features.** Specify Slurm setup, monitoring, node health checks/drain, networking tests and a public incident feed once; turn speculative decoding and prefix caching on only behind a correctness canary (same prompts with the feature off). Kit: `shop-eval/counter` rows (PASS/FAIL/UNKNOWN with denominator) for each item; an on/off canary arm in `run3/arm.py`; incident feed collected with `clustermax-challenge` `collect_status.py`.

## Could not do, or limits

- **Framework-only spread from InferenceX** is confounded by topology and image differences except in the 35 like-for-like keys; the tens-of-x extremes look like failed runs and I did not verify them.
- **Prices:** shapes were not resolved; Together AI rows are excluded as a flagged unit artefact rather than verified against the provider; provider price pages were not fetched (no network use in this task).
- **Issues:** no body text is retained in the rows, so spec-decode and prefix-cache counts are title-only lower bounds; the class regexes are the lane's; fix linkage is available for only 217 issues.
- **Reviews and incidents:** keyword themes, not manual coding; incident windows are not common across providers.
- **Demand:** name-level matching; OpenRouter exposes 10 ranks and its stealth model is unidentified; Ollama pulls are cumulative and rounded and cover 200 of 240 models.
- **Floor spec:** there is no `floor/` specification on disk yet (this folder is new), so "floor-conforming" behaviours in section 7 are the kit's existing procedures, not clauses of a floor document.

## Reproduce

```
WORK=<scratch dir>
python ix_extract.py <inferencex-2026-09-29.jsonl> $WORK/ix_rows.jsonl      # prints line count and sha256
python ix_spread.py  $WORK/ix_rows.jsonl $WORK ; python ix_spread2.py $WORK/ix_rows.jsonl $WORK
python price_dispersion.py <prices.jsonl> $WORK/price_dispersion_result.json ; python price_trim.py $WORK/price_dispersion_result.json $WORK/price_trim_result.json
python ha_price_change.py <prices.jsonl> $WORK/ha_price_change_result.json
python issues_classes.py <issues.jsonl> $WORK/issues_classes_result.json
python cloudreview_shortfalls.py <claims.all.jsonl> $WORK/cloudreview_shortfalls_result.json
python incident_patterns.py <incidents dir> $WORK/incident_patterns_result.json
python demand_anchor.py $WORK/ix_rows.jsonl $WORK/demand_anchor_result.json
# telemetry scripts (WORK exported) then:
python make_findings.py        # writes findings.jsonl
```
