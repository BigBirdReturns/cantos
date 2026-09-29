# The reference floor for a properly set up neocloud

Built 2026-09-29. Local draft: not committed, not pushed. Machine form: `floor.json` (same item ids). Companion: `PRESCRIPTIONS.md` / `prescriptions.json`, `SOURCES.md` (every file cited, with sha256).

## Reading rules

- Paths are relative to `D:/Projects/Organs/AXM/axm-tools/`. Every number below carries a source. Where the estate has no number the item says UNKNOWN and states what would establish it.
- Evidence class is the kit vocabulary from `main/hot-aisle/campaign/shop-eval/MANUAL.md`: published_claim, operator_report, measured, derived, hypothesis. The field `origin` separates **ours** (Second Run/Hot Aisle campaign) from **imported** (InferenceX, MLPerf, SemiAnalysis, OpenComputePrices; not reproduced by us).
- Hot Aisle is a dated reference observation, one allocation, one run per arm. Where a figure is a Hot Aisle measurement the floor says so; where Hot Aisle itself misses the floor, per its own SemiAnalysis 2.0 review, the item says so (Section 5).
- Funding disclosure (`main/hot-aisle/campaign/DISCLOSURES.md`): the Hot Aisle arms ran on a $200 credit Hot Aisle gave to Second Run, which is pitching Hot Aisle a paid engagement; costs are undiscounted list. The DigitalOcean arm was self-funded.
- The review sentences are SemiAnalysis ClusterMAX text, mostly the 2.0 pages published 2025-11-06 (28 rows from 2.1 updates dated 2026-04-20). They are quoted verbatim as evidence of what was penalized. SemiAnalysis's legal notice on every page prohibits use of the ratings to create financial products without written consent; this document does not do that.

## Key numbers

| what | figure | source | origin |
|---|---|---|---|
| Request to SSH, 1x MI300X (Hot Aisle) | 122 s, n=1 | `main/hot-aisle/campaign/shop-eval/counter/records/hotaisle-2026-09.json` | ours, measured |
| Request to SSH, 1x H100 (DigitalOcean) | 83 s, n=1 (60 s in Run 1 arm B) | `main/hot-aisle/campaign/results/run3-scored-n-t0/closure.json`, `main/hot-aisle/campaign/availability/observations.jsonl` | ours, measured |
| Accepted per GPU-hour, MI300X / H100 | 4022 / 3678 (request-to-end windows; other windows in Section 2) | `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` | ours, derived |
| Cost per 1,000 accepted at list, MI300X / H100 | $0.74 / $1.20 | `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` | ours, derived |
| Tie line, H100 / MI300X | $2.72 published (2.734 unrounded) / $2.99 per GPU-hour | `main/hot-aisle/campaign/shop-eval/SHORTLIST.md` | ours, derived |
| TTFT p50/p95/p99, MI300X | 53/155/571 ms | `main/hot-aisle/campaign/results/run3-scored-a-t0/detailed.json` | ours, measured |
| TTFT p50/p95/p99, H100 | 35/76/2254 ms | `main/hot-aisle/campaign/results/run3-scored-n-t0/detailed.json` | ours, measured |
| Run 3 acceptance | TTFT <= 1,000 ms, done <= 60 s from scheduled arrival, EvalPlus base and plus pass | `main/hot-aisle/campaign/run3/PREREG.md` | ours |
| Accepted rate | 50.3% (MI300X) / 49.6% (H100) of 8,622 | `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` | ours, measured |
| Run 1 registered cell gates | p95 TTFT <= 1,000 ms, p95 E2E <= 15,000 ms, failed <= 1% | `main/hot-aisle/campaign/identity.json` | ours |
| Incidents per 180 days (17 status pages) | major/critical median 4, range 0 to 58; all median 10, range 0 to 85 | `main/clustermax-challenge/retrospective/results/R2-result.md` | ours, derived from provider self-reports |
| SemiAnalysis "ClusterMAX 2.0 real" MTBF | 10,000 GPU-hr (Nebius blog preset 169,800) | `sessions/clustermax-cloudreview-20260929/tco-model.json` | imported |
| July 2026 median on-demand $/GPU-hr | MI300X $3.04 (7 providers); H100 $2.99 (42) | `main/hot-aisle/campaign/market/MARKET.md` | imported |
| Minimum versions | container toolkit >= 1.19.1, CUDA >= 13.1, DCGM >= 4.5.3, dcgm-exporter >= 4.8.2, Docker >= 29.7.0, ROCm MI300X >= 6.4.2 | `sessions/public-tail-20260929/lanes/cmax-audit/repo/cmax/scripts/1-audit/minimum-versions.json` | imported |

## 1. Access and acquisition

A shop meets this section when a stranger with a card can go from signup to a running seat without a sales call, in minutes once the account exists, and can tell from the console whether a SKU is really available. Two reference seats were timed: Hot Aisle once (122 s create to SSH) and DigitalOcean twice (83 s in Run 3, 60 s in Run 1 arm B). The signup-to-first-create time, the KYC bound and any quota-approval bound were never measured (A-03 is UNKNOWN).

**Anti-pattern from the review sentences.** Weeks to login: GMI (`cmcr-gmi-05`: "We did not get access to a self-service console or monitoring dashboard of any kind, and it took over a month from our initial request, and multiple follow ups to finally login."), Mithril (`cmcr-mithrilmlfoundry-12`: "Source: a 3-month wait, and counting."), IREN (no capacity for over three months, `cmcr-irenirisenergy-09`). Account deactivation: IBM (`cmcr-ibmcloud-07`: "Unfortunately, when we tried to line up testing with IBM, they went so far as to deactivate our account and block us from making new sign-ups"; `cmcr-ibmcloud-13`: "We were about halfway through a simple download speed test using docker when IBM once again found our account and shut us down."). KYC block: Bitdeer (`cmcr-bitdeer-06`), E2E Networks (`cmcr-e2enetworks-06`). Not self-serve: Aethir (`cmcr-aethir-05`), STN (`cmcr-stn-06`), Lambda 1-Click (`cmcr-lambda-09`).

#### A-01. The SKU under test can be rented with no sales conversation, and API-token issuance is self-serve.

- Threshold or reference: sales_gate = false (a sales conversation required before any create attempt disqualifies) (boolean).
- Evidence class: derived. Origin: ours (compiled from retained campaign evidence, not an end-to-end counter run).
- Sources: `main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md` :: step 1 and step 5; `main/hot-aisle/campaign/shop-eval/SHORTLIST.md` :: rule 1 (self-serve); `main/hot-aisle/campaign/shop-eval/counter/records/hotaisle-2026-09.json` :: account_creation.sales_gate=false, api_cli_tui_quality.token_issuance=self-serve.
- Verified by: counter:step-1 (account_creation.sales_gate); counter:step-5 (token_issuance, list/create/delete).
- Penalized by 7 review sentences across 5 providers: `cmcr-aethir-05`, `cmcr-stn-06`, `cmcr-lambda-09`, `cmcr-lambda-14`, `cmcr-exabits-06`, `cmcr-gcore-10` and 1 more (full list in floor.json).
  - `cmcr-aethir-05` (Aethir): "Unfortunately, Aethir is not truly a self service experience, requiring prospective buyers to fill out a form in order to purchase GPU time on their platform."
- Note: Hot Aisle record is class derived: it was compiled from Run 3 notes, not produced by running the counter protocol (PROTOCOL.md preamble).

#### A-02. Time from submitting create to first successful SSH on a single-GPU seat.

- Threshold or reference: <= 300 s (kit target FLEET-01, a buyer-selected 5-minute target, not a Hot Aisle standard); Hot Aisle-grade reference < 180 s (counter PROTOCOL step 3) (seconds).
- Evidence class: measured. Origin: ours.
- Sources: `main/hot-aisle/campaign/shop-eval/counter/records/hotaisle-2026-09.json` :: provisioning.attempts[0] = 122 s (2026-09-24T00:08:55Z to 00:10:57Z), n=1; `main/hot-aisle/campaign/results/run3-scored-n-t0/closure.json + main/hot-aisle/campaign/results/run3-scored-n-t0/ledger-times.json` :: DigitalOcean 1x H100, t_request 2026-09-24T04:08:03Z to t_ssh 04:09:26Z = 83 s, n=1; `main/hot-aisle/campaign/availability/observations.jsonl` :: DigitalOcean 1x H100 console create 2026-09-23T17:49:00Z time_to_ssh_s=60, n=1 (Run 1 arm B); `main/hot-aisle/campaign/shop-eval/diagnose/RUBRIC.md` :: FLEET-01; `main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md` :: step 3; `sessions/clustermax-cloudreview-20260929/claims.all.jsonl` :: cmcr-gpunet-06 (about 2 minutes), cmcr-cudocompute-08 (under 4 minutes), cmcr-qubrid-06 (around 8 minutes), cmcr-dstacksky-20 (under 5 minutes to a connected 2x H100).
- Verified by: counter:step-3 (three timed creates, delete each on SSH); rubric:FLEET-01; evaluate.sh timestamps t_request/t_ssh.
- Penalized by 5 review sentences across 4 providers: `cmcr-amazonwebservices-13`, `cmcr-gcore-12`, `cmcr-hyperstacknexgen-06`, `cmcr-hyperstacknexgen-10`, `cmcr-voltagepark-09`.
  - `cmcr-amazonwebservices-13` (Amazon Web Services (AWS)): "The provisioning process for a single cluster can take about two hours, as each node can take upwards of 30 minutes to deploy (if capacity is available)."
- Note: Each of our figures is a single allocation. measured_3x is false for both shops. The four review figures are SemiAnalysis published claims, not ours.

#### A-03. Time from the first sign-up screen to the first create attempt (signup_to_active_account_s).

- Threshold or reference: UNKNOWN (seconds).
- Evidence class: none (UNKNOWN). Origin: ours (unobserved).
- Sources: `main/hot-aisle/campaign/shop-eval/counter/records/hotaisle-2026-09.json` :: account_creation.signup_to_active_account_s = "unobserved"; `main/hot-aisle/campaign/shop-eval/counter/records/digitalocean-2026-09.json` :: account_creation.signup_to_active_account_s = "unobserved"; quota_gate = soft; GPU Droplet limit 0 on a new account, raised to 1 by support ticket in "under a day" (campaign fact, not timed).
- Verified by: counter:step-1 (stopwatch from first sign-up screen to first create attempt).
- Penalized by 5 review sentences across 5 providers: `cmcr-gmi-05`, `cmcr-mithrilmlfoundry-12`, `cmcr-ibmcloud-07`, `cmcr-stn-06`, `cmcr-clore-05`.
  - `cmcr-gmi-05` (GMI): "We did not get access to a self-service console or monitoring dashboard of any kind, and it took over a month from our initial request, and multiple follow ups to finally login."
- **UNKNOWN.** What would establish it: Run counter step 1 with a fresh email on at least the shortlisted shops and set the bound from the measured distribution. No source sets a signup-to-seat bound; the review corpus supplies only the anti-pattern (over a month at GMI, a 3-month wait at Mithril).
- Note: The only timed access delay in the estate is the DigitalOcean quota ticket, "under a day", an operator report that was not stopwatched.

#### A-04. No KYC beyond card plus prepaid balance; quota gate none or soft; no account deactivation after sign-up verification.

- Threshold or reference: kyc beyond card = none; quota_gate in {none, soft}; hard or sales gate fails (enum).
- Evidence class: derived. Origin: ours (Hot Aisle-grade definition from the counter protocol).
- Sources: `main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md` :: step 1 (Hot Aisle-grade: self-serve, no sales team, no KYC beyond a card, prepaid Stripe credit, $20 minimum); `main/hot-aisle/campaign/shop-eval/counter/records/hotaisle-2026-09.json` :: kyc_required=unobserved, quota_gate=unobserved, card_required=true; `main/hot-aisle/campaign/shop-eval/counter/records/digitalocean-2026-09.json` :: quota_gate=soft, kyc_required=unobserved.
- Verified by: counter:step-1 (kyc_required, card_required, quota_gate, sales_gate).
- Penalized by 15 review sentences across 12 providers: `cmcr-ibmcloud-07`, `cmcr-ibmcloud-08`, `cmcr-ibmcloud-09`, `cmcr-ibmcloud-13`, `cmcr-bitdeer-06`, `cmcr-e2enetworks-06` and 9 more (full list in floor.json).
  - `cmcr-ibmcloud-07` (IBM Cloud): "Unfortunately, when we tried to line up testing with IBM, they went so far as to deactivate our account and block us from making new sign-ups"
- Note: For both reference shops KYC and (for Hot Aisle) quota gate are unobserved, not passed. No create was ever refused at Hot Aisle, so absence of a quota gate is untested.

#### A-05. Listed availability equals deliverable availability: a SKU shown as available provisions when a create is attempted.

- Threshold or reference: every create attempted on a listed-available SKU succeeds (rubric PRICE-03: a listed SKU with an unsuccessful attempt is WRONG for that attempt) (created / attempted).
- Evidence class: measured. Origin: ours.
- Sources: `main/hot-aisle/campaign/availability/observations.jsonl` :: Hot Aisle 1x MI300X VM listed 2026-09-24T00:02:15Z, delivered 00:10:45Z; DigitalOcean 1x H100 delivered 2026-09-23T17:49:00Z and 2026-09-24T04:08:59Z; DigitalOcean MI300X and H200 out_of_capacity in every region checked (2026-09-23 18:55 to 19:13Z, 2026-09-24 04:08:02Z and 05:19:18Z); `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` :: What it says, item 5; `main/hot-aisle/campaign/shop-eval/diagnose/RUBRIC.md` :: PRICE-03; `main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md` :: step 4.
- Verified by: counter:step-4 (ledger_attempts, listed vs delivered layers); rubric:PRICE-03; availability/observations.jsonl (campaign ledger).
- Penalized by 15 review sentences across 12 providers: `cmcr-akashnetwork-05`, `cmcr-akashnetwork-07`, `cmcr-deepinfra-05`, `cmcr-e2enetworks-09`, `cmcr-exabits-05`, `cmcr-gpunet-05` and 9 more (full list in floor.json).
  - `cmcr-akashnetwork-05` (Akash Network): "Unfortunately, we weren’t able to access any H100 or H200 on the platform."
- Note: Delivered creates in the whole campaign ledger: 3 (Hot Aisle 1, DigitalOcean 2), 3 succeeded. A rate at n=3 is not a claim. Listing observations are not create attempts (PROTOCOL step 4).

#### A-06. Billing granularity finer than one hour, minimum stated in one place, and billing stops at delete.

- Threshold or reference: per-minute or per-second billing (rubric PRICE-01: hourly-or-coarser is WRONG against a sub-hour requirement); billing stops at delete, confirmed by balance or invoice delta (granularity).
- Evidence class: published_claim. Origin: ours (observed page and balance behaviour; invoice not reconciled).
- Sources: `main/hot-aisle/campaign/shop-eval/counter/records/hotaisle-2026-09.json` :: billing_quantum: 1 minute minimum then per-minute for 1x MI300X VM; 1-hour minimum observed on the 2x VM 2026-09-23; stop_on_delete_verified=true via balance behaviour, invoice_matches_balance=unobserved; `main/hot-aisle/campaign/shop-eval/counter/records/digitalocean-2026-09.json` :: per-second billing; minimum disputed between pricing page (5 minutes) and docs (60 seconds); stop_on_delete_verified=unobserved; `main/hot-aisle/campaign/shop-eval/diagnose/RUBRIC.md` :: PRICE-01; `main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md` :: step 6; `sessions/clustermax-cloudreview-20260929/raw/expectations_standalone.html` :: Hardware Support, "Flexible billing granularity (second, minute, hour, day)"; `sessions/clustermax-cloudreview-20260929/providers/hotaisle/pricing.html` :: $2.99/GPU/hr, 1, 2 and 4x MI300X VMs, billed by the minute; 8x bare metal $3.39/GPU/hr.
- Verified by: counter:step-6 (balance before and after delete); counter:step-2 (price transparency); rubric:PRICE-01.
- Penalized by 5 review sentences across 4 providers: `cmcr-hydrahost-07`, `cmcr-qubrid-12`, `cmcr-voltagepark-22`, `cmcr-e2enetworks-11`, `cmcr-qubrid-07`.
  - `cmcr-hydrahost-07` (Hydra Host): "Unfortunately, in order to actually get access to one of these servers, Hydra forces users to pre-pay for a weekly bill, and promises to “refund for the unused portion” rather than running ..."
- Note: DigitalOcean's pricing page and docs give two different minimums for the same SKU. Treat them as separate claims until an invoice line resolves them.

#### A-07. Public price per GPU-hour for the SKU, visible without login, with minimum billing stated.

- Threshold or reference: published = true; $/GPU-hr stated per SKU (boolean).
- Evidence class: published_claim. Origin: ours (page reads).
- Sources: `main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md` :: step 2; `main/hot-aisle/campaign/shop-eval/counter/records/hotaisle-2026-09.json` :: price_transparency.published=true, per_gpu_hour_usd=2.99; `main/hot-aisle/campaign/shop-eval/counter/records/digitalocean-2026-09.json` :: per_gpu_hour_usd=4.41 (gpu-h100x1-base); `main/hot-aisle/campaign/identity.json` :: arms.hotaisle-mi300x.list_rate=2.99 (retrieved from the Hot Aisle API at plan time), arms.do-h100.list_rate=4.41.
- Verified by: counter:step-2; rubric:PRICE-01.
- Note: Egress and storage rates were never located for either shop (egress_rate and storage_rate unobserved); see O-25.

#### A-08. Direct SSH to a public IP (or a documented equivalent) with no mandatory VPN and no short-lived console token in the path.

- Threshold or reference: public IP assigned; direct SSH works on first boot (boolean).
- Evidence class: derived. Origin: ours.
- Sources: `main/hot-aisle/campaign/shop-eval/counter/records/hotaisle-2026-09.json` :: network_path.public_ip_assigned=true; `main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md` :: step 8; `sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html` :: Access, "Head node provisioned and accessible via a simple SSH command".
- Verified by: counter:step-8 (public_ip_assigned, firewall_default, open_ports_first_boot); counter:step-3.
- Penalized by 4 review sentences across 2 providers: `cmcr-firmussustainablemetalcloud-07`, `cmcr-firmussustainablemetalcloud-08`, `cmcr-firmussustainablemetalcloud-09`, `cmcr-amazonwebservices-20`.
  - `cmcr-firmussustainablemetalcloud-07` (Firmus / Sustainable Metal Cloud (SMC)): "Our testing began with a difficult wrinkle: cluster access is gated behind a mandatory VPN."
- Note: Default firewall posture and first-boot port scan were never recorded for Hot Aisle (unobserved).

#### A-09. List, create and delete work through an API, CLI or TUI without a support ticket; SSH key upload and management exist.

- Threshold or reference: list, create, delete all true; idempotency recorded (boolean).
- Evidence class: derived. Origin: ours.
- Sources: `main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md` :: step 5; `main/hot-aisle/campaign/shop-eval/counter/records/hotaisle-2026-09.json` :: list_op, create_op, delete_op true; idempotent_create and idempotent_delete unobserved; `sessions/clustermax-cloudreview-20260929/raw/expectations_standalone.html` :: Access, "API automation support", "SSH key upload and management".
- Verified by: counter:step-5.
- Penalized by 2 review sentences across 2 providers: `cmcr-lambda-14`, `cmcr-oracle-13`.
  - `cmcr-lambda-14` (Lambda): "During our testing, we evaluated both their new (self-managed) and old (rancher-based) Kubernetes offerings, and their newly available slurm offering. Neither of these is UI or CLI driven, ..."
- Note: Idempotency was never deliberately tested at either shop.


## 2. Delivered performance per seat

**Ours or imported.** P-00 to P-07 and P-11 are ours (Run 3, Run 2 exploration): Qwen3-Coder-30B-A3B-Instruct-FP8 on vLLM 0.30.0, one run per arm, list prices, funding disclosed. P-08 (InferenceX) and P-09 (MLPerf) are imported and are software-configuration ceilings for other models; they are not comparable to Run 3 and are not our measurements.

Accepted per GPU-hour and cost per 1,000 accepted for the Run 3 workload, by window. The windows are different kinds and must not be averaged (MANUAL section 4):

| arm | rate | window | minutes | accepted | accepted per GPU-hour | $ per 1,000 accepted |
|---|---:|---|---:|---:|---:|---:|
| Hot Aisle 1x MI300X (A/T0) | $2.99 | replay only | 60.11 | 4,336 | 4328 | 0.6908 |
| Hot Aisle 1x MI300X (A/T0) | $2.99 | arm script | 62.65 | 4,336 | 4152 | 0.7201 (published $0.72) |
| Hot Aisle 1x MI300X (A/T0) | $2.99 | 122 s request-to-SSH plus arm script | 64.68 | 4,336 | 4022 | 0.7434 (published $0.74) |
| Hot Aisle seat, whole | $2.99 | request to release incl. smoke, A/T1, idle (mixed) | 2.73 h | 9,086 | n/a | 0.897 (published $0.90; invoice unreconciled) |
| DigitalOcean 1x H100 (N/T0) | $4.41 | replay only | 60.11 | 4,280 | 4272 | 1.0322 |
| DigitalOcean 1x H100 (N/T0) | $4.41 | arm script | 66.03 | 4,280 | 3889 | 1.1339 |
| DigitalOcean 1x H100 (N/T0) | $4.41 | request to release | 69.82 | 4,280 | 3678 | 1.1990 (published $1.20) |

Hot Aisle A/T1 (forced ROCM_AITER_FA) accepted 4,292 (published $0.73 own window); it is a declared tuning tier, never the headline.

**Imported ceilings (InferenceX, closest matched pair).** Maximum output tokens/s per GPU over all concurrencies, no latency gate, vllm, fixed-sequence, one GPU:

| model | precision | hardware | ISL/OSL | best tok/s/GPU | at concurrency | rows | artifact |
|---|---|---|---|---:|---:|---:|---|
| Qwen/Qwen3.8-27B-FP8 | FP8 | H100 | 1024/1024 | 3070.5 | 64 | 33 | 10591762755 (2026-09-19) |
| Qwen/Qwen3.8-27B-FP8 | FP8 | MI300X | 1024/1024 | 2248.2 | 128 | 32 | 10591384039 (2026-09-19) |
| Qwen/Qwen3.8-27B | BF16 | H100 | 1024/1024 | 1803.8 | 32 | 44 | 10599917642 (2026-09-20) |
| Qwen/Qwen3.8-27B | BF16 | MI300X | 1024/1024 | 2483.9 | 128 | 42 | 10599987525 (2026-09-20) |

**Imported ceilings (MLPerf Inference, closed division, latest release with data, derived per accelerator).**

| release | SKU | benchmark | scenario | tok/s/accelerator | system | accelerators |
|---|---|---|---|---:|---|---:|
| v5.1 | H100 | llama2-70b-99 | Offline | 3902.5 | HGX-H100_H100-SXM-80GBx32_TRT | 32 |
| v5.1 | H100 | llama2-70b-99 | Server | 3821.1 | HGX-H100_H100-SXM-80GBx32_TRT | 32 |
| v5.0 | H100 | mixtral-8x7b | Offline | 6590.6 | C885A_H100_SXMx8_TRT | 8 |
| v5.0 | H100 | mixtral-8x7b | Server | 6662.4 | C885A_H100_SXMx8_TRT | 8 |
| v5.1 | MI300X | llama2-70b-99 | Offline | 3524.9 | 32xMI300X_2xEPYC_9534_16xMI325X_2xEPYC_9655 | 48 |
| v5.1 | MI300X | llama2-70b-99 | Server | 3189.1 | 32xMI300X_2xEPYC_9534_16xMI325X_2xEPYC_9655 | 48 |
| v5.1 | MI300X | mixtral-8x7b | Offline | 6666.7 | XE9680_MI300X_192GBx8 | 8 |
| v5.1 | MI300X | mixtral-8x7b | Server | 5975.5 | 8xMI300X_2xEPYC_9575F | 8 |

#### P-00. All Section 2 delivery figures are for one pinned workload; any change is a new comparison scope.

- Threshold or reference: Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8 (revision dcaee4d4dfc5ee71ad501f01f530e5652438fde0), vLLM 0.30.0, TP=1, max-model-len 16384, max-num-seqs 256, gpu-memory-utilization 0.90, prefix caching off; 542 EvalPlus tasks (HumanEval+ 164, MBPP+ 378) cycled; Azure LLM inference CODE trace 2023 at rate factor 0.95, 8,622 scheduled requests over 3,600 s; temperature 0.2, max_tokens 1024, seed 700000+index (workload identity).
- Evidence class: measured. Origin: ours.
- Sources: `main/hot-aisle/campaign/run3/PREREG.md` :: Question, arms and identities; Workload and arrival freeze; `main/hot-aisle/data/run3/source/invocation.json`; `main/hot-aisle/data/run3/source/env.json`; `main/hot-aisle/campaign/run3/freeze-2026-09-24/FREEZE.md`; `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` :: Workload.
- Verified by: run3:arm3.sh (invocation.json, env.json); run3:grade.sh (EvalPlus 0.3.1 sidecar).
- Note: One run per arm, no repeats (RUN3-RESULTS Caveats). Grader-blind tasks HumanEval/32, Mbpp/255, Mbpp/392 stay in the denominators.

#### P-01. Accepted requests per GPU-hour on a 1x MI300X seat (Hot Aisle A/T0), Run 3 workload.

- Threshold or reference: reference 4022 (request-to-arm-end window 64.68 min); 4152 (arm script window 62.65 min); 4328 (replay window 60.11 min). 4,336 accepted of 8,622. n=1, not a tolerance (accepted requests per GPU-hour).
- Evidence class: derived. Origin: ours (measured counts; per-hour figure derived by division).
- Sources: `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` :: A/T0 column; `main/hot-aisle/data/run3/source/ledger-times.json` :: t_script_start, t_script_end; `main/hot-aisle/campaign/results/run3-scored-a-t0/detailed.json` :: duration=3606.58 s; `main/hot-aisle/campaign/shop-eval/counter/records/hotaisle-2026-09.json` :: provisioning 122 s; `main/hot-aisle/campaign/results/RUN3-HOTAISLE-SUMMARY.md`.
- Verified by: run3:arm3.sh + grade.sh; diagnose PRICE-02 (scoped economic gate).
- Note: Windows differ on purpose and must not be averaged (MANUAL section 4). The 4,022 window adds the 122 s request-to-SSH to the arm script window. Load was bounded by the trace, not by capacity (FREEZE.md): these are not peak-throughput figures.

#### P-02. Accepted requests per GPU-hour on a 1x H100 seat (DigitalOcean N/T0), Run 3 workload.

- Threshold or reference: reference 3678 (request-to-release window 69.82 min); 3889 (arm script window 66.03 min); 4272 (replay window 60.11 min). 4,280 accepted of 8,622. n=1, not a tolerance (accepted requests per GPU-hour).
- Evidence class: derived. Origin: ours (measured counts; per-hour figure derived by division).
- Sources: `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` :: N/T0 column; `main/hot-aisle/campaign/results/run3-scored-n-t0/closure.json` :: t_request, t_released; `main/hot-aisle/campaign/results/run3-scored-n-t0/ledger-times.json`; `main/hot-aisle/campaign/results/run3-scored-n-t0/detailed.json` :: duration=3606.39 s.
- Verified by: run3:arm3.sh + grade.sh.
- Note: DigitalOcean window is request to release (69.82 min, fully closed ledger). The two shops' windows are not the same kind, see MANUAL section 4. Invoice not reconciled; DigitalOcean cash about $5.13 (RUN3-RESULTS Money actually spent).

#### P-03. Cost per 1,000 accepted requests at list price, 1x MI300X, Run 3 workload.

- Threshold or reference: $0.7434 (own-seat equivalent, 64.68 min, rate $2.99/h; published as $0.74); $0.7201 (arm window; published $0.72); $0.6908 (replay window only); $0.90 (whole seat 2.73 h incl. smoke, A/T1 and idle, 9,086 accepted, mixed window, invoice unreconciled) (USD per 1,000 accepted).
- Evidence class: derived. Origin: ours.
- Sources: `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` :: $/1k accepted row; Money actually spent; `main/hot-aisle/campaign/results/RUN3-HOTAISLE-SUMMARY.md` :: cost correction, whole seat $0.90; `main/hot-aisle/data/run3/headline.json` :: sides[0].cost_per_1000=0.6908; `main/hot-aisle/campaign/shop-eval/MANUAL.md` :: section 4 (cost bases stay separate); `main/hot-aisle/campaign/DISCLOSURES.md` :: Funding and relationship (undiscounted list; run paid from a $200 Hot Aisle credit; Second Run is pitching Hot Aisle).
- Verified by: diagnose PRICE-02 and PROOF-02; run3 ledger closure (billed_usd stays null until invoice).
- Note: Four windows, four figures, none an invoice. The whole-seat $0.90 is 20.7% above $0.743 and is the measured price of smoke, setup and idle time on a shared seat. Not steady-state. Funding disclosure applies.

#### P-04. Cost per 1,000 accepted requests at list price, 1x H100, Run 3 workload.

- Threshold or reference: $1.1990 (request to release, 69.82 min, $4.41/h; published as $1.20); $1.1339 (arm window); $1.0322 (replay window only) (USD per 1,000 accepted).
- Evidence class: derived. Origin: ours.
- Sources: `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` :: N/T0 column; `main/hot-aisle/campaign/results/run3-scored-n-t0/closure.json`; `main/hot-aisle/campaign/results/run3-scored-n-t0/ledger-times.json`; `main/hot-aisle/campaign/DISCLOSURES.md` :: DigitalOcean arm self-funded at list.
- Verified by: diagnose PRICE-02; run3 ledger closure.
- Note: $4.41 is the DigitalOcean list rate on 2026-09-24 (self-funded). DigitalOcean changed its price on 2026-08-01 per MARKET.md; the public series carries $3.39 for the same SKU. See Section 6.

#### P-05. Cost per 1,000 accepted must not exceed the reference by more than 5% on validated same-scope evidence.

- Threshold or reference: <= $0.7806 per 1,000 accepted (1.05 x $0.7434); PRICE-02 is WRONG only above this and only when workload, model and tokenizer revisions, precision, cache policy, load profile, acceptance rule, latency gates, cost scope and rate all match (USD per 1,000 accepted).
- Evidence class: derived. Origin: ours (kit rule).
- Sources: `main/hot-aisle/campaign/shop-eval/diagnose/RUBRIC.md` :: Economic comparison gate; PRICE-02.
- Verified by: diagnose PRICE-02 (needs scope JSON bound to the scored table by SHA-256).
- Note: A different GPU, runtime, backend or kernel does not establish operator causality (RUBRIC).

#### P-06. Selected attention backend and FP8 linear kernel are recorded from the serve log, not from requested flags, before any performance claim.

- Threshold or reference: env.json holds = [] and selected backends named; T1 requires ROCM_AITER_FA as the sole attention selection (record present).
- Evidence class: measured. Origin: ours.
- Sources: `main/hot-aisle/data/run3/source/env.json` :: attention_backend [ROCM_ATTN], linear_kernel [AiterFp8BlockScaledMMKernel], holds []; `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` :: table row Backends (N/T0: FLASH_ATTN, FlashInferFp8DeepGEMMDynamicBlockScaledKernel, MoE TRITON); `main/hot-aisle/campaign/backfill/RERUN-POLICY.md` :: Carry lessons forward (verify backend selection); `main/hot-aisle/campaign/run3/README.md` :: env.json holds semantics; `sessions/public-tail-20260929/lanes/github-issues-deep/summary/coverage.md` :: vllm-project/vllm issues per month 2026-09: 841 (regex heuristic, issues only).
- Verified by: run3:arm3.sh env.json; diagnose STK-02.
- Note: vLLM issue volume is context for why versions and backends must be pinned and read back; it is a title/body regex count, not a defect rate.

#### P-07. Cost of an unverified backend selection (documented uplift when the shop-side default was overridden).

- Threshold or reference: Llama-3.3-70B FP8 on 1x Hot Aisle MI300X, forced ROCM_AITER_FA vs auto-selected ROCM_ATTN, one repeat, post-hoc: long c8 +28.3% req/s, long c32 +45.7% (p95 TTFT 57 s to 37 s), short c32 +9.1%, short c64 +11.3%, c1 unchanged. On the Run 3 MoE workload: no gain (accepted 4,336 to 4,292) and p99 TTFT 571 to 1,119 ms (percent req/s).
- Evidence class: measured. Origin: ours (post-hoc exploration, never a headline).
- Sources: `main/hot-aisle/campaign/DISCLOSURES.md` :: Added 2026-09-23 late (28% and 46%); `main/hot-aisle/campaign/run2/EXPLORE.md`; `main/hot-aisle/campaign/results/run2-hotaisle-mi300x/cell-*-r0.json vs main/hot-aisle/campaign/results/run2-explore-hotaisle-mi300x/cell-*-r0.json (request_throughput ratios recomputed here)`; `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` :: What it says, item 4.
- Verified by: run3:arm3.sh T1 tier (declared tuned arm); rerun policy: backend/kernel change triggers sentinel rerun.
- Note: Transferable lesson is to verify backend selection. The uplift does not transfer to MoE, another precision or another version without a targeted confirmation (RERUN-POLICY). Not pre-registered.

#### P-08. Software-config ceiling, InferenceX (imported): best published output tokens/s per GPU on the closest matched single-GPU dense-model pair on H100 and MI300X.

- Threshold or reference: H100 Qwen/Qwen3.8-27B-FP8 vllm 1024/1024 1 GPU: 3070.5 tok/s/GPU at c64 (max of 33 rows); MI300X Qwen/Qwen3.8-27B-FP8 vllm 1024/1024 1 GPU: 2248.2 tok/s/GPU at c128 (max of 32 rows); H100 Qwen/Qwen3.8-27B vllm 1024/1024 1 GPU: 1803.8 tok/s/GPU at c32 (max of 44 rows); MI300X Qwen/Qwen3.8-27B vllm 1024/1024 1 GPU: 2483.9 tok/s/GPU at c128 (max of 42 rows) (output tokens/s/GPU).
- Evidence class: published_claim. Origin: imported (InferenceX results_bmk aggregates via GitHub Actions artifacts; not our measurement, not reproduced).
- Sources: `sessions/public-tail-20260929/lanes/inferencex-history/REPORT.md`; `main/hot-aisle/campaign/backfill/IMPORT-SUMMARY.md` :: Full history 2026-09-29; `sessions/public-tail-20260929/lanes/inferencex-history/rows/inferencex.jsonl` :: rows hardware in {H100, MI300X}, metric output_throughput_per_gpu (recomputed here, maximum per group).
- Verified by: none: imported prior. A rerun would follow RERUN-POLICY (comparable raw gap > 20 percent, three frozen repeats).
- Note: Maximum over concurrency with no latency gate applied: a throughput ceiling, not a gated frontier. No H100 or MI300X InferenceX row carries Qwen3-Coder-30B-A3B, so nothing here is comparable to Run 3 (delta report: 0 comparable observations, backfill/DELTA-2026-09-29.md). Model names are as the producer wrote them. The ordering flips between FP8 (H100 higher) and BF16 (MI300X higher) on this pair, so no hardware ranking follows. Latency-gated frontier for our workload: UNKNOWN.

#### P-09. Software-config ceiling, MLPerf Inference (imported): per-accelerator output tokens/s on the closest published LLM benchmarks for H100 and MI300X.

- Threshold or reference: v5.1 H100 llama2-70b-99 Offline: 3902.5 tok/s/accel (HGX-H100_H100-SXM-80GBx32_TRT, 32 accel); v5.1 H100 llama2-70b-99 Server: 3821.1 tok/s/accel (HGX-H100_H100-SXM-80GBx32_TRT, 32 accel); v5.0 H100 mixtral-8x7b Offline: 6590.6 tok/s/accel (C885A_H100_SXMx8_TRT, 8 accel); v5.0 H100 mixtral-8x7b Server: 6662.4 tok/s/accel (C885A_H100_SXMx8_TRT, 8 accel); v5.1 MI300X llama2-70b-99 Offline: 3524.9 tok/s/accel (32xMI300X_2xEPYC_9534_16xMI325X_2xEPYC_9655, 48 accel); v5.1 MI300X llama2-70b-99 Server: 3189.1 tok/s/accel (32xMI300X_2xEPYC_9534_16xMI325X_2xEPYC_9655, 48 accel); v5.1 MI300X mixtral-8x7b Offline: 6666.7 tok/s/accel (XE9680_MI300X_192GBx8, 8 accel); v5.1 MI300X mixtral-8x7b Server: 5975.5 tok/s/accel (8xMI300X_2xEPYC_9575F, 8 accel) (output tokens/s/accelerator (derived)).
- Evidence class: published_claim. Origin: imported (MLCommons submissions; per-accelerator value derived by us as total / explicit accelerator count).
- Sources: `sessions/public-tail-20260929/lanes/mlperf/summary/coverage.md` :: Per-accelerator normalized output throughput (DERIVED), closed division, status available, max over systems; `sessions/public-tail-20260929/lanes/mlperf/REPORT.md`; `main/hot-aisle/campaign/backfill/IMPORT-SUMMARY.md` :: MLPerf section.
- Verified by: none: imported prior. MLPerf reproduction would need accuracy and compliance evidence (RERUN-POLICY).
- Note: Latest release with data per group, from the full table in the source. Not a producer field; multi-node, framework and quantization differ; VALID is LoadGen validity only, accuracy not evaluated. The v5.1 MI300X llama2-70b system is a 48-accelerator mixed MI300X/MI325X system (32xMI300X + 16xMI325X), so that per-accelerator figure is not a clean MI300X number; the v5.0 32xMI300X and v4.1 1xMI300X rows are cleaner. Neither benchmark is our model.

#### P-10. Peak sustainable accepted rate at the latency gates on a seat.

- Threshold or reference: UNKNOWN (accepted requests per second).
- Evidence class: none (UNKNOWN). Origin: ours (not measured).
- Sources: `main/hot-aisle/campaign/run3/freeze-2026-09-24/FREEZE.md` :: Calibration outcome: load bounded by the trace, not calibrated to 70% of capacity; `main/hot-aisle/campaign/run3/PREREG.md` :: capacity calibration procedure.
- Verified by: run3:PREREG calibration (backlog, at most 256 outstanding, up to 5 minutes).
- **UNKNOWN.** What would establish it: Run the PREREG calibration on each arm: continuous backlog, at most 256 outstanding requests, up to five minutes after readiness; capacity C is valid only if throughput was stable. Run 3 offered 8,622 requests in 3,600 s (2.395 req/s average, peak 531 arrivals in one minute) with 0 transport failures on A/T0 and N/T0, so capacity is above that but unmeasured.

#### P-11. Image pull, model download and health-ready time on a fresh seat with working Docker and GPU runtime.

- Threshold or reference: <= 2,400 s (PREREG phase budget); stop rule at 40 minutes (seconds).
- Evidence class: measured. Origin: ours.
- Sources: `main/hot-aisle/data/run3/source/ledger-times.json` :: t_script_start to t_ready = 143.5 s (A/T0); `main/hot-aisle/campaign/results/run3-scored-n-t0/ledger-times.json` :: t_script_start to t_ready = 349.1 s (N/T0); `main/hot-aisle/campaign/run3/PREREG.md` :: Schedule, watchdog and cash; Stop rules.
- Verified by: run3:arm3.sh ledger-times.json.
- Penalized by 4 review sentences across 4 providers: `cmcr-amazonwebservices-18`, `cmcr-cudocompute-12`, `cmcr-latitudesh-10`, `cmcr-buzzhpc-08`.
  - `cmcr-amazonwebservices-18` (Amazon Web Services (AWS)): "Following the console guide results in a GPU instance provisioned without any Nvidia drivers installed, and a default root volume size of 8GB, which is insufficient to even install the ..."
- Note: Both seats already had Docker and a working GPU runtime. Time to install a missing driver or toolkit is not in these numbers (UNKNOWN for image-poor shops).


## 3. Tail and gates

Two gate families exist and they are different scopes. `identity.json` registers cell-level gates for Run 1 (p95 TTFT 1,000 ms, p95 E2E 15,000 ms, failed 1%). Run 3 does not use them: it scores each request against a 1,000 ms TTFT and a 60 s deadline from the scheduled arrival, with EvalPlus correctness, and gates qualification on transport failure at 1%. Run 1 and Run 3 are not comparable (RUBRIC). Tail differences between shops are outcomes; they do not invalidate a comparison.

| arm | TTFT p50/p95/p99 ms | p95 latency ms | correct | accepted | accepted rate | weakest 5-min bucket | median bucket | failed transport |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A/T0 Hot Aisle MI300X | 53/155/571 | 12355 | 4,371 | 4,336 | 50.3% | 40.9% | 50.8% | 0 |
| A/T1 forced ROCM_AITER_FA | 60/202/1119 | 12805 | 4,334 | 4,292 | 49.8% | 39.7% | 51.0% | 7 |
| N/T0 DigitalOcean H100 | 35/76/2254 | 12069 | 4,329 | 4,280 | 49.6% | 39.3% | 49.7% | 0 |

#### T-01. Run 3 acceptance definition: completed, EvalPlus base and plus pass, first token <= 1 s, done <= 60 s from the scheduled arrival.

- Threshold or reference: ttft <= 1,000 ms per request; e2e <= 60,000 ms from scheduled arrival; engine settings ttft=1000, e2e=60000, queue=true, quality=true (ms).
- Evidence class: measured. Origin: ours (registered pre-run in PREREG; frozen 2026-09-24, commit 0b032ac).
- Sources: `main/hot-aisle/campaign/run3/PREREG.md` :: Gates and metrics; `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` :: Workload.
- Verified by: run3:grade.sh + engine_check.cjs.
- Note: "Pre-registered" here means privately recorded before the data, not publicly timestamped (DISCLOSURES.md Timestamps).

#### T-02. Registered Run 1 cell gates from identity.json (random 2048/256, warm, latency-only, no correctness sidecar).

- Threshold or reference: p95 TTFT <= 1,000 ms; p95 E2E <= 15,000 ms; failed <= 1% (ms / ms / fraction).
- Evidence class: measured. Origin: ours (scope run1-cell-c64).
- Sources: `main/hot-aisle/campaign/identity.json` :: requirements {max_p95_ttft_ms:1000, max_p95_e2e_ms:15000, max_failure_rate:0.01}, pinned_on 2026-09-23; `main/hot-aisle/campaign/DISCLOSURES.md` :: Run 1 (H100 c64 fails p95 TTFT 1.9 s; MI300X qualifies at c64; ROCm image did not write per-request latencies so the AMD E2E gate was held); `main/hot-aisle/campaign/shop-eval/diagnose/RUBRIC.md` :: scope IDs run1-cell-c64.
- Verified by: engine gate check against the scoped table; diagnose PRICE-02 scope JSON.
- Note: Run 1 and Run 3 are not comparable (RUBRIC). These gates do not apply to Run 3 numbers. In Run 1 the AMD E2E gate was never restored; derived AMD E2E peaked at 5.34 s.

#### T-03. TTFT percentiles on the Run 3 stream, reported as outcomes with the window they came from.

- Threshold or reference: A/T0 MI300X p50/p95/p99 = 53/155/571 ms; A/T1 = 60/202/1119 ms; N/T0 H100 = 35/76/2254 ms. Reference values, no pass/fail gate on p95 or p99 was registered for Run 3 (ms).
- Evidence class: measured. Origin: ours.
- Sources: `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` :: table; `main/hot-aisle/campaign/results/run3-scored-a-t0/detailed.json` :: ttfts (nearest-rank recomputation here); `main/hot-aisle/campaign/results/run3-scored-a-t1/detailed.json`; `main/hot-aisle/campaign/results/run3-scored-n-t0/detailed.json`.
- Verified by: run3:replay.py requests.jsonl; engine_check.cjs.
- Note: One run per arm on one allocation on one day; no repeat variance is available. A tail difference alone does not invalidate a comparison (MANUAL section 2).

#### T-04. p95 end-to-end request latency on the Run 3 stream.

- Threshold or reference: A/T0 12354 ms (headline.json); A/T1 12805 ms and N/T0 12069 ms (nearest-rank, recomputed from detailed.json latencies); against the 60,000 ms deadline (ms).
- Evidence class: measured. Origin: ours.
- Sources: `main/hot-aisle/data/run3/headline.json` :: sides[0].p95_e2e_ms; `main/hot-aisle/campaign/results/run3-scored-a-t0/detailed.json` :: latencies; `main/hot-aisle/campaign/results/run3-scored-n-t0/detailed.json` :: latencies.
- Verified by: run3:replay.py; engine_check.cjs.
- Note: Latency here is per-request latency from detailed.json; the acceptance deadline is measured from the scheduled arrival.

#### T-05. Failed transport across all scheduled arrivals, including never-sent client-limit rejections.

- Threshold or reference: <= 1% of scheduled arrivals (exactly 1% passes); measured 0/8,622 (A/T0), 7/8,622 = 0.081% (A/T1, client-limit rejections), 0/8,622 (N/T0) (fraction).
- Evidence class: measured. Origin: ours.
- Sources: `main/hot-aisle/campaign/run3/PREREG.md` :: Serving-host loopback client; `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` :: Completed / failed; `main/hot-aisle/campaign/results/run3-scored-a-t1/grade/quality-buckets.json` :: bucket 4 failed=7.
- Verified by: run3:convert.py + summary.
- Note: More than 1% blocks useful-throughput qualification. Do not discard overloads.

#### T-06. Accepted-rate expectation on the Run 3 workload.

- Threshold or reference: reference band for this exact freeze: 49.6% (N/T0, 4,280) to 50.3% (A/T0, 4,336) of scheduled arrivals, n=1 each; weakest 5-minute bucket 39.3% (N/T0) to 40.9% (A/T0); median bucket 49.7% to 50.8%; 99.2% (A/T0) and 98.9% (N/T0) of correct outputs also met the deadlines (fraction of scheduled arrivals).
- Evidence class: derived. Origin: ours.
- Sources: `main/hot-aisle/campaign/results/run3-scored-a-t0/grade/quality-buckets.json`; `main/hot-aisle/campaign/results/run3-scored-n-t0/grade/quality-buckets.json`; `main/hot-aisle/campaign/results/run3-scored-a-t1/grade/quality-buckets.json`; `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` :: Correct (raw, registered) 4,371 / 4,334 / 4,329 and item 3 (post-hoc sanitizer regrade 4,371 to 6,192 correct, deadline intersection not recomputed); `main/hot-aisle/campaign/run3/PREREG.md` :: useful-throughput requirements.
- Verified by: run3:grade.sh buckets (12 five-minute buckets, min, median, last/first quarter).
- Note: The accepted rate is set by correctness under the raw-completion output contract, not by shop latency: latency removed 35 of 4,371 correct outputs on A/T0 and 49 of 4,329 on N/T0. A post-hoc sanitizer regrade lifted total correct from 4,371 to 6,192 on the same retained run; the accepted count under that regrade is unmeasured. So an accepted rate below the band on the same freeze is a signal to check the contract and the backend before blaming the shop.

#### T-07. p99 TTFT ceiling for burst traffic.

- Threshold or reference: UNKNOWN (ms).
- Evidence class: none (UNKNOWN). Origin: ours (not registered).
- Sources: `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` :: p99 571 ms (MI300X) vs 2,254 ms (H100), a 3.9x difference on the same trace; `main/hot-aisle/campaign/shop-eval/MANUAL.md` :: section 2 (tail latency is an outcome).
- Verified by: run3 replay + engine_check.
- **UNKNOWN.** What would establish it: Register a p99 TTFT gate before the next arm from the intended customer SLO, then freeze it with the other gates. No source sets one.


## 4. Reliability

The evidence here is thin and mostly not ours. What exists: incident histories that providers publish about themselves (R2), SemiAnalysis's public MTBF assumptions, and review sentences about billing during outages. What does not exist: any fleet MTBF, recovery time or outage-billing test on a real shop by the estate.

Incidents on the provider's own status page, 2026-03-27 to 2026-09-23 (180 days), scheduled maintenance excluded. Derived from `main/clustermax-challenge/retrospective/results/R2-result.md` and `main/clustermax-challenge/retrospective/incidents/*.json` (14 of 17 recounted here, all matched):

| provider | 3.0 tier | major or critical | all non-maintenance | incident hours | coverage rule |
|---|---|---:|---:|---:|---|
| Nebius | Platinum | 17 | 39 | 179.8 | declared_coverage |
| Google Cloud | Gold | 5 | 5 | 546.9 | capped_feed_rule (oldest record 2026-02-27 < window start 2026-03-27) |
| Lambda | Silver | 2 | 16 | 1443.0 | capped_feed_rule (oldest record 2026-02-13 < window start 2026-03-27) |
| GCore | Bronze | 58 | 85 | 1027.9 | declared_coverage |
| Verda | Bronze | 0 | 6 | 17.5 | declared_coverage |
| Prime Intellect | Bronze | 2 | 10 | 1689.0 | declared_coverage |
| together.ai | Bronze | 0 | 0 | 0.0 | declared_coverage |
| Crusoe | Bronze | 5 | 21 | 139.2 | declared_coverage |
| DigitalOcean | Bronze | 8 | 59 | 332.9 | declared_coverage |
| Hyperstack | Bronze | 9 | 10 | 57.3 | declared_coverage |
| RunPod | Participation Ribbon | 11 | 33 | 439.2 | declared_coverage |
| Radiant | Participation Ribbon | 0 | 0 | 0.0 | declared_coverage |
| latitude.sh | Participation Ribbon | 4 | 9 | 54.7 | declared_coverage |
| Sharon AI | Underperforming | 1 | 1 | 0.5 | declared_coverage |
| Hydra | Underperforming | 0 | 0 | 0.0 | declared_coverage |
| Akamai | Underperforming | 0 | 59 | 2706.2 (capped, open incidents) | declared_coverage |
| Mithril | Underperforming | 4 | 6 | 38.7 | declared_coverage |

**What "no incidents reported" means.** Together AI (0 incidents, 0 hours) sits next to a review sentence saying it draws the most reliability complaints from users of clusters of 64 GPUs or more (`cmcr-together-05`). Hydra, Cudo Compute and Fluidstack also show 0 in the collection window. Radiant shows only maintenance notices, and its empty months return 404 rather than a "no incidents" page. So a zero is a fact about what the provider chooses to post, not about availability. R2 found a positive but inconclusive rank correlation between medal and reported incident count (rho 0.44, permutation p 0.0762, n=17): better-rated providers report more.

**MTBF presets in SemiAnalysis's TCO model** (`sessions/clustermax-cloudreview-20260929/tco-model.json`, captured 2026-09-29):

| preset | MTBF GPU-hr |
|---|---:|
| Maximum (Nebius blog) | 169800 |
| Round number (high) | 64000 |
| Meta paper claim | 50677 |
| Round number (mid) | 32000 |
| Nebius blog sample | 26446 |
| Round number (low) | 16000 |
| ClusterMAX 2.0 real | 10000 |

The 10,000 GPU-hr "ClusterMAX 2.0 real" figure is the low end; the Nebius review (`cmcr-nebius-34`) attributes "less than 10,000 GPU-hr" to gold and silver providers on customer reports, and calls the 169,800 figure cherry-picked (`cmcr-nebius-36`). Goodput-loss assumptions in the same model (percent of GPU spend): example 2.05 gold or hyperscaler vs 3.43 silver; pretrain 2.80 vs 4.98; RL 0.24 vs 0.75; inference on H200 0.02 vs 0.49.

#### R-01. Public status page with a machine-readable incident history reaching back at least 180 days.

- Threshold or reference: history reachable back to the start of a 180-day window (R2 eligibility rule: coverage_start <= window start, or an accepted capped-feed rule) (days).
- Evidence class: derived. Origin: ours (collection over provider status pages).
- Sources: `main/clustermax-challenge/retrospective/results/R2-result.md` :: Primary release, Eligible providers (17) and Excluded providers; `main/clustermax-challenge/retrospective/PLAN-R2.md` :: Window and eligibility; `main/clustermax-challenge/retrospective/incidents/SCHEMA.md`; `sessions/clustermax-cloudreview-20260929/reports/batch-A.md` :: status column (Hot Aisle: status.hotaisle.xyz does not resolve; batch B row hotaisle); `sessions/clustermax-cloudreview-20260929/reports/batch-B.md`; `sessions/clustermax-cloudreview-20260929/reports/batch-C.md`; `sessions/clustermax-cloudreview-20260929/reports/batch-D.md`.
- Verified by: clustermax-challenge/scripts/collect_status.py (Atlassian, status.io, Better Stack, Instatus modes vary); R2 eligibility check.
- Note: Of 45 providers with a rated (not Unavailable) tier in the R2 3.0 table, 17 were eligible; 2 had a status feed that could not reach the window (CoreWeave, OVHcloud); 26 had no incident file collected (the study did not distinguish no status page from not collected). 32 Unavailable-tier providers were excluded by plan. Across the four batch reports (by my parse of their tables), 55 providers have a recorded status-surface outcome: 34 reachable (32 plus 2 JS-shell stubs), 21 not reachable (DNS failure, 403/404 and similar). A failed fetch is not proof there is no page. Hot Aisle: no status page found in the 2026-09-29 capture.

#### R-02. Incident counts on the provider's own status page per 180 days (2026-03-27 to 2026-09-23), scheduled maintenance excluded. Reference distribution only.

- Threshold or reference: no ceiling is set by any source. 17 eligible providers: major or critical count min 0, median 4, max 58; all non-maintenance count min 0, median 10, max 85; incident hours min 0, median 139.2, max 2706.2 (incidents per 180 days).
- Evidence class: derived. Origin: ours (status pages are provider self-reports).
- Sources: `main/clustermax-challenge/retrospective/results/R2-result.md` :: Analysis (Spearman rho 0.44, bootstrap 95% [-0.007, 0.749], permutation p 0.0762, reading inconclusive); `main/clustermax-challenge/retrospective/incidents/*.json (17 eligible files; counts recomputed here for 14 of them and match)`; `main/clustermax-challenge/retrospective/PLAN-R2.md` :: Known limits.
- Verified by: R2 pipeline: clustermax-challenge/retrospective/run_r2.py.
- Note: Higher medals do not mean fewer reported incidents: rho is positive (0.44) between 3.0 tier ordinal and major/critical count, inconclusive at p = 0.0762 with n = 17. Status pages are self-reported, severity vocabularies differ, and the medal is dated at the window end, so this is concurrent, not predictive.

#### R-03. A page that reports zero incidents is treated as a reporting-policy fact, not an availability fact.

- Threshold or reference: n/a (interpretation rule) (n/a).
- Evidence class: derived. Origin: ours.
- Sources: `main/clustermax-challenge/retrospective/incidents/together-ai.json, hydra.json, cudo-compute.json, fluidstack.json (Better Stack, 0 incidents 2026-01 to 2026-09)`; `main/clustermax-challenge/retrospective/incidents/radiant.json (4 notices, all maintenance; months without notices return 404 rather than an explicit "no incidents" page)`; `main/clustermax-challenge/retrospective/results/R2-result.md` :: together.ai 0/0/0.0 h; `sessions/clustermax-cloudreview-20260929/claims.all.jsonl` :: cmcr-together-05.
- Verified by: R2 eligibility: an explicit archive boundary or paginated-to-start evidence is required for coverage_start.
- Penalized by 1 review sentence across 1 provider: `cmcr-together-05`.
  - `cmcr-together-05` (Together): "Together is among a few providers for which we tend to hear the most reliability complaints about from users operating clusters of 64 GPUs or more."
- Note: Together AI shows 0 incidents in the window while SemiAnalysis (cmcr-together-05) says Together is among the providers with the most reliability complaints from users operating 64+ GPU clusters. Akamai shows 59 incidents and 2,706 h (capped, open incidents). Zero and very large numbers are both policy outputs until the incident definition and coverage are published.

#### R-04. MTBF must be quoted in GPU-hours with the cluster size and window behind it; SemiAnalysis TCO presets are the reference points.

- Threshold or reference: Maximum (Nebius blog) = 169800 GPU-hr; Round number (high) = 64000 GPU-hr; Meta paper claim = 50677 GPU-hr; Round number (mid) = 32000 GPU-hr; Nebius blog sample = 26446 GPU-hr; Round number (low) = 16000 GPU-hr; ClusterMAX 2.0 real = 10000 GPU-hr. The "ClusterMAX 2.0 real" preset is 10,000 GPU-hr (GPU-hours).
- Evidence class: published_claim. Origin: imported (SemiAnalysis AI Cloud TCO model, embedded in the clustermax.ai JS bundle, captured 2026-09-29).
- Sources: `sessions/clustermax-cloudreview-20260929/tco-model.json` :: goodput_presets; `sessions/clustermax-cloudreview-20260929/README.md` :: Findings, item 3; `sessions/clustermax-cloudreview-20260929/claims.all.jsonl` :: cmcr-nebius-32 (26,446), cmcr-nebius-33 (50,677), cmcr-nebius-34 (less than 10,000 for gold and silver tier customers), cmcr-nebius-36 (169,800 called cherry-picked), cmcr-coreweave-48/49 (466 interruptions in 54 days, 2,111 H100-days).
- Verified by: none in kit: fleet MTBF is not measurable from one seat.
- Penalized by 1 review sentence across 1 provider: `cmcr-nebius-36`.
  - `cmcr-nebius-36` (Nebius): "Later in the blog, Nebius claims to have had single 3,000 GPU cluster operate uninterrupted for 169,800 GPU hours or 56.6 hours of stable operation. This would translate to an absurdly high ..."
- Note: Derived here: at 10,000 GPU-hr a 1,024-GPU job sees a failure about every 9.8 h (10,000 / 1,024). The 10,000 preset carries source label "ClusterMAX" with the site root URL; the closest review sentence is cmcr-nebius-34 (customers at 1k to 2k GPUs report "as much as 5+ failures per day", which is 4,800 to 9,600 GPU-hr by our arithmetic, customer hearsay); the preset itself carries no derivation. The TCO model turns this into goodput loss as percent of GPU spend: example 2.05% gold/hyperscaler vs 3.43% silver; pretrain 2.80% vs 4.98%; RL 0.24% vs 0.75%; inference (H200) 0.02% vs 0.49% (tco-model.json scenario rows). Model assumptions, not measurements.

#### R-05. No charge for time the instance is unusable; written compensation for downtime; refunds on a stated clock.

- Threshold or reference: billing stops when the instance is not usable; Verda reference commitment: credit of at least 2x the cost of affected instances, refunds within 24 h on weekdays (next Monday for weekend downtime) (policy).
- Evidence class: published_claim. Origin: imported (SemiAnalysis review sentences).
- Sources: `sessions/clustermax-cloudreview-20260929/claims.all.jsonl` :: cmcr-verdadatacrunch-21, -23 (commitment); cmcr-verdadatacrunch-16, -17, -19 (charged during outages, SLA not upheld); cmcr-e2enetworks-11, -13, -15 ($7,061.05 owed for a cluster stuck in creating); cmcr-voltagepark-22 (Shutdown halts instances but still bills); cmcr-qubrid-07; `sessions/clustermax-cloudreview-20260929/raw/criteria_reliability.html` :: MSA SLA evaluation (99%, 99.9%, etc.).
- Verified by: counter:step-6 (billing stops at delete); counter:step-10; desk review of SLA/credit terms.
- Penalized by 9 review sentences across 4 providers: `cmcr-e2enetworks-11`, `cmcr-e2enetworks-13`, `cmcr-e2enetworks-15`, `cmcr-qubrid-07`, `cmcr-verdadatacrunch-16`, `cmcr-verdadatacrunch-17` and 3 more (full list in floor.json).
  - `cmcr-e2enetworks-11` (E2E Networks): "The most serious issue occurred while we were stuck in this queue, waiting for our slurm cluster to be deployed. We watched as our credit balance was drained, and then went into the ..."
- Note: Hot Aisle was observed stopping billing at delete by balance behaviour; billing during an outage or a stuck create was never tested at either reference shop (UNKNOWN).

#### R-06. Numeric SLA floor (monthly uptime percentage and credit schedule).

- Threshold or reference: UNKNOWN (percent).
- Evidence class: none (UNKNOWN). Origin: n/a.
- Sources: `sessions/clustermax-cloudreview-20260929/raw/criteria_reliability.html` :: MSA SLA evaluation (99%, 99.9%, etc.), no floor stated; `sessions/clustermax-cloudreview-20260929/claims.all.jsonl` :: cmcr-firmussustainablemetalcloud-16 (a claimed 99.94% SLA), cmcr-stn-13, cmcr-googlecloud-42.
- Verified by: desk review of the MSA.
- Penalized by 4 review sentences across 4 providers: `cmcr-stn-13`, `cmcr-verdadatacrunch-19`, `cmcr-googlecloud-42`, `cmcr-amazonwebservices-37`.
  - `cmcr-stn-13` (STN): "We suggest that in the future, STN focus on actual cluster reliability instead of reporting fake “Uptime SLA” metrics to Grafana."
- **UNKNOWN.** What would establish it: No source states a minimum. Establish from the intended buyer's outage cost: a floor needs the buyer's own downtime cost per hour and the shop's credit schedule, neither of which the estate has.

#### R-07. Recovery: detection, acknowledgement, repair, readiness, resumed useful work, rework, operator minutes after a controlled failure of a disposable job.

- Threshold or reference: UNKNOWN (minutes).
- Evidence class: none (UNKNOWN). Origin: ours (never run on a real shop).
- Sources: `main/hot-aisle/campaign/shop-eval/MANUAL.md` :: section 5 (recovery drill), section 2 (failure tests need host authority); `MANUAL.md preamble: the kit has not yet been qualified on a new Linux/GPU shop`.
- Verified by: MANUAL section 5 recovery drill.
- Penalized by 3 review sentences across 2 providers: `cmcr-radiantori-07`, `cmcr-stn-10`, `cmcr-stn-11`.
  - `cmcr-radiantori-07` (Radiant/Ori): "Our testing of a simple hardware failure simulation showed that the system did not trigger any automated alerting or node replacement over an 18-hour window."
- **UNKNOWN.** What would establish it: Run the section 5 drill on a disposable supervised process on each shortlisted shop, and record every timestamp named there. Fleet MTBF cannot be measured from one seat; it needs an agreed fleet sample from the operator (Cooperative host mode).


## 5. Operations checklist

Each item names the audit check ids that verify it (from `checks-inventory.json`: 59 graded checks, 29 that run on a standalone machine; 27 of the 73 vendored catalog rows have no graded CLI check), the kit steps that verify it, and the review sentences that penalize its absence. `audit:` ids come from SemiAnalysis's ClusterMAX audit tool, which was installed on Windows and run only for help pages, check listing, a dry-run and two fixture reviews; no Linux collection was executed on any GPU host (audit REPORT). Standalone VMs cannot establish scheduler, fabric or RDMA items.

**Where the reference shop stands, per its own 2.0 review (dated 2025-11-06):** Hot Aisle was rated Bronze and left the 3.0 table. SemiAnalysis wrote that it "does not have shared storage, monitoring dashboards, health checks, modern security practices, RBAC, vertically integrated support, or the ability to run at scale" (`cmcr-hotaisle-09`), that Slurm/Kubernetes were advertised but not set up (`cmcr-hotaisle-10`), and that it had no VMs available on first try (`cmcr-hotaisle-11`). It also credited a SOC 2 Type I attestation (`cmcr-hotaisle-04`); its live trust page now states SOC 2 Type 2 (provider claim, fetched 2026-09-29). Hot Aisle is the reference for Section 2 economics, not for this checklist.

#### O-01. DCGM background health checks enabled and plugged into the Slurm HealthCheckProgram (or vendor equivalent).

- Threshold or reference: enabled and integrated (scontrol show config | grep HealthCheckProgram non-empty) (boolean).
- Evidence class: published_claim. Origin: imported (SemiAnalysis expectation).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html` :: Monitoring and Health Checks; `sessions/clustermax-cloudreview-20260929/raw/expectations_health-checks.html` :: Passive: GPU Health Monitoring.
- Verified by: audit:healthChecks.dcgmInstalled; audit:healthChecks.dcgmSlurm; audit:healthChecks.nhcInstalled.
- Penalized by 10 review sentences across 8 providers: `cmcr-fluidstack-22`, `cmcr-stn-12`, `cmcr-radiantori-06`, `cmcr-tensorwave-13`, `cmcr-azure-09`, `cmcr-azure-10` and 4 more (full list in floor.json).
  - `cmcr-fluidstack-22` (Fluidstack): "We found that DCGM’s background health checks were not enabled."
- Note: Audit checks are Slurm-harness only and NVIDIA-oriented; a standalone VM cannot establish this item. Hot Aisle: the SemiAnalysis 2.0 review says no health checks (cmcr-hotaisle-09).

#### O-02. Passive and active health coverage: XID/SXID, ECC, PCIe errors, link flaps, GPU temperature; active dcgmi diag r3, nvbandwidth, local NCCL and ib_write_bw tests.

- Threshold or reference: passive set present; active tests run on idle nodes weekly (checklist).
- Evidence class: published_claim. Origin: imported (SemiAnalysis expectation).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/expectations_health-checks.html` :: Passive and Active sections; Automation, "Weekly scheduled active health checks on idle nodes"; `sessions/clustermax-cloudreview-20260929/raw/criteria_reliability.html` :: Key Requirements; `main/hot-aisle/campaign/shop-eval/diagnose/RUBRIC.md` :: HW-01, HW-02, HW-03, PWR-01.
- Verified by: catalog:xid-monitoring (partial, no graded check); probe/fingerprint.sh (PCIe link, RAS counters, firmware age, clocks); rubric:HW-01; rubric:HW-02; rubric:HW-03; rubric:PWR-01.
- Penalized by 31 review sentences across 25 providers: `cmcr-azure-09`, `cmcr-azure-10`, `cmcr-buzzhpc-11`, `cmcr-buzzhpc-12`, `cmcr-cudocompute-16`, `cmcr-digitalocean-06` and 25 more (full list in floor.json).
  - `cmcr-azure-09` (Azure): "In stark contrast, CycleCloud relies on the traditional HPC model via slurm’s HealthCheckProgram. However, CycleCloud does not provide a good default, like LBNL’s Node Health Check ..."
- Note: Rubric thresholds are SIGNALs, not defects: PCIe below supported max, any uncorrectable or over 100 correctable RAS counters, firmware older than 270 days, throttle or clock slope over 15%.

#### O-03. Automatic node drain and replacement after a detected fault.

- Threshold or reference: fault injected on a disposable node leads to drain without customer action (boolean).
- Evidence class: published_claim. Origin: imported (SemiAnalysis expectation).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/expectations_health-checks.html` :: Automation, "GPU/node health detection ... with automated cordon/drain and repair/replace"; `sessions/clustermax-cloudreview-20260929/claims.all.jsonl` :: cmcr-fluidstack-23 (dcgmi test --inject --gpuid 0 -f 202 did not drain), cmcr-radiantori-07 (18 h with no alert or replacement).
- Verified by: catalog:auto-remediation (partial, no graded check); MANUAL section 5 recovery drill (needs host operator authority).
- Penalized by 12 review sentences across 9 providers: `cmcr-fluidstack-23`, `cmcr-googlecloud-33`, `cmcr-googlecloud-36`, `cmcr-oracle-32`, `cmcr-radiantori-07`, `cmcr-stn-11` and 6 more (full list in floor.json).
  - `cmcr-fluidstack-23` (Fluidstack): "By injecting PCIe replay errors (dcgmi test --inject --gpuid 0 -f 202), we confirmed that the node would not automatically drain."

#### O-04. Prolog and epilog lightweight.

- Threshold or reference: < 30 s to get on a node via srun (seconds).
- Evidence class: published_claim. Origin: imported (SemiAnalysis expectation).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html` :: Monitoring and Health Checks, "time srun -N1 hostname"; `sessions/clustermax-cloudreview-20260929/claims.all.jsonl` :: cmcr-firmussustainablemetalcloud-10 and cmcr-fluidstack-11 (over a minute), cmcr-amazonwebservices-25 (deep health checks 60-120 minutes).
- Verified by: catalog:prolog-fast (no graded check); manual: time srun -N1 hostname.
- Penalized by 5 review sentences across 3 providers: `cmcr-firmussustainablemetalcloud-10`, `cmcr-firmussustainablemetalcloud-11`, `cmcr-fluidstack-11`, `cmcr-fluidstack-12`, `cmcr-amazonwebservices-25`.
  - `cmcr-firmussustainablemetalcloud-10` (Firmus / Sustainable Metal Cloud (SMC)): "Once connected, our slurm environment also had some configuration issues. The standard topology.conf file was not set for topology-aware scheduling, and a simple “srun -N1 –gpus-per-node=8 ..."

#### O-05. Monitoring stack: Grafana/kube-prometheus-stack, DCGM exporter, alerting, job accounting integration.

- Threshold or reference: dashboard present with GPU health and Slurm/K8s job views (boolean).
- Evidence class: published_claim. Origin: imported (SemiAnalysis expectation).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/expectations_monitoring.html` :: Cluster Overview through Resource Management; `sessions/clustermax-cloudreview-20260929/raw/criteria_monitoring.html` :: Out-of-the-box detailed managed Grafana; `sessions/clustermax-cloudreview-20260929/raw/expectations_kubernetes.html` :: Other.
- Verified by: audit:healthChecks.monitoringStack.dcgmExporter (partial; no dashboard-quality proof); audit:securityVersions.dcgmExporter.status.
- Penalized by 30 review sentences across 23 providers: `cmcr-amazonwebservices-26`, `cmcr-azure-11`, `cmcr-buzzhpc-13`, `cmcr-cudocompute-16`, `cmcr-digitalocean-06`, `cmcr-gcore-17` and 24 more (full list in floor.json).
  - `cmcr-amazonwebservices-26` (Amazon Web Services (AWS)): "Unfortunately, monitoring dashboards for slurm or Kubernetes cluster health, performance, and job stats are basically non-existent beyond standard, manual, open source tooling."
- Note: Hot Aisle: no monitoring dashboards per the 2.0 review (cmcr-hotaisle-09).

#### O-06. Shared filesystem at the default home directory, RWX StorageClass, storage mounts stay mounted, performance measured.

- Threshold or reference: findmnt -T $HOME shows a shared mount; default StorageClass provisions PVCs without hanging; fio result documented (boolean).
- Evidence class: published_claim. Origin: imported (SemiAnalysis expectation).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html` :: Access, shared filesystem; `sessions/clustermax-cloudreview-20260929/raw/expectations_kubernetes.html` :: Configuration, CSI provider with ReadWriteMany; `sessions/clustermax-cloudreview-20260929/raw/criteria_storage.html` :: Key Requirements.
- Verified by: audit:storage.rwxStatus (k8s harness only); catalog:shared-fs (partial, no graded check); catalog:default-storage-class (no graded check); manual: fio per expectations page.
- Penalized by 16 review sentences across 13 providers: `cmcr-buzzhpc-06`, `cmcr-cudocompute-10`, `cmcr-cudocompute-16`, `cmcr-crusoe-24`, `cmcr-crusoe-30`, `cmcr-digitalocean-06` and 10 more (full list in floor.json).
  - `cmcr-buzzhpc-06` (BuzzHPC): "initially, no NFS mount, and then user’s default workdir was not on the shared filesystem"
- Note: Our single-GPU arms never exercised shared storage (UNKNOWN).

#### O-07. Slurm commands functional and job accounting available.

- Threshold or reference: sinfo, squeue, scontrol, salloc, sbatch, srun work for users; sacct returns jobs (boolean).
- Evidence class: published_claim. Origin: imported (SemiAnalysis expectation).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html` :: Access.
- Verified by: audit:access.slurmCommandsOk; audit:slurm.accounting.sacctAvailable.
- Penalized by 4 review sentences across 2 providers: `cmcr-gmocloud-05`, `cmcr-gmocloud-06`, `cmcr-gmocloud-07`, `cmcr-azure-13`.
  - `cmcr-gmocloud-05` (GMO Cloud): "We focused on slurm as kubernetes is not available, and quickly found that sinfo and scontrol are completely disabled for end-users."

#### O-08. Slurm and Kubernetes actually working at handover: head node reachable, kubeconfig downloadable, GPU Operator, Network Operator, MPI Operator, load balancer.

- Threshold or reference: first-use test passes without vendor engineer intervention (boolean).
- Evidence class: published_claim. Origin: imported (SemiAnalysis expectation).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/expectations_kubernetes.html` :: Access and Configuration; `sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html` :: Access; `sessions/clustermax-cloudreview-20260929/raw/criteria_orchestration.html` :: Slurm and Kubernetes requirements.
- Verified by: audit:storage.rwxStatus; audit:kubelet_cpu_manager_policy.status; catalog:gpu-operator (no graded check); catalog:network-operator (no graded check); catalog:load-balancer (no graded check).
- Penalized by 49 review sentences across 30 providers: `cmcr-amazonwebservices-05`, `cmcr-amazonwebservices-06`, `cmcr-amazonwebservices-07`, `cmcr-amazonwebservices-11`, `cmcr-amazonwebservices-12`, `cmcr-buzzhpc-04` and 43 more (full list in floor.json).
  - `cmcr-amazonwebservices-05` (Amazon Web Services (AWS)): "Our initial setup process following the primary documentation path for creating a slurm cluster through the SageMaker console. This path proved to be a dead end."

#### O-09. Topology-aware scheduling configured (topology.yaml or topology.conf, topology/block or topology/tree).

- Threshold or reference: configured (boolean).
- Evidence class: published_claim. Origin: imported (SemiAnalysis expectation).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html` :: Configuration.
- Verified by: audit:networking.topologyConfigured.
- Penalized by 6 review sentences across 6 providers: `cmcr-firmussustainablemetalcloud-10`, `cmcr-gmocloud-09`, `cmcr-neysa-10`, `cmcr-stn-09`, `cmcr-vultr-06`, `cmcr-tensorwave-13`.
  - `cmcr-firmussustainablemetalcloud-10` (Firmus / Sustainable Metal Cloud (SMC)): "Once connected, our slurm environment also had some configuration issues. The standard topology.conf file was not set for topology-aware scheduling, and a simple “srun -N1 –gpus-per-node=8 ..."

#### O-10. Container runtimes for Slurm: Pyxis, Enroot, Docker on workers with a current NVIDIA Container Toolkit, Apptainer/Singularity.

- Threshold or reference: Pyxis --container-image present; enroot works; docker run --gpus all nvidia-smi works (boolean).
- Evidence class: published_claim. Origin: imported (SemiAnalysis expectation).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html` :: Containers; `sessions/clustermax-cloudreview-20260929/raw/expectations_standalone.html` :: Configuration (NVIDIA Container Toolkit with Docker; ROCm container toolkit with --device=/dev/kfd --device=/dev/dri for AMD).
- Verified by: audit:containers.pyxisRuntimeWorks; audit:containers.enroot; audit:containers.enrootImportWorks; audit:containers.dockerOnWorkers; audit:containers.nvidiaContainerToolkit; audit:containers.singularity.
- Penalized by 6 review sentences across 5 providers: `cmcr-buzzhpc-10`, `cmcr-gmocloud-11`, `cmcr-gmocloud-12`, `cmcr-primeintellect-08`, `cmcr-vultr-06`, `cmcr-runpod-04`.
  - `cmcr-buzzhpc-10` (BuzzHPC): "no pyxis or enroot"

#### O-11. HPC toolchain present without hunting: nvcc, HPC-X or equivalent MPI, NCCL up to date, Lmod.

- Threshold or reference: present; NVHPC on a current-or-previous release: copy table minimum 26.3 with current 26.5 (generated 2026-08-30); upstream table minimum 26.5 with current 26.9 (generated 2026-09-25) (boolean).
- Evidence class: published_claim. Origin: imported (SemiAnalysis expectation).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html` :: Configuration; `sessions/public-tail-20260929/lanes/cmax-audit/repo/cmax/scripts/1-audit/minimum-versions.json` :: components.nvhpc; `sessions/public-tail-20260929/lanes/cmax-audit/raw/upstream-minimum-versions.json` :: components.nvhpc.
- Verified by: audit:software.nvhpc.status; audit:software.lmod.modulesStatus; audit:software.nccl.installed.
- Penalized by 8 review sentences across 7 providers: `cmcr-buzzhpc-09`, `cmcr-fluidstack-14`, `cmcr-gmi-06`, `cmcr-primeintellect-08`, `cmcr-runpod-11`, `cmcr-stn-09` and 2 more (full list in floor.json).
  - `cmcr-buzzhpc-09` (BuzzHPC): "modules not installed, also no hpcx, nccl, nvcc"

#### O-12. GPUDirect RDMA via dma_buf enabled; PCIe ACS disabled on the GPU-to-NIC path; two-node NCCL AllReduce at reference bandwidth.

- Threshold or reference: >= 300 GB/s bus bandwidth, two-node AllReduce, 128 MiB message (SemiAnalysis reference for top-tier neoclouds, cmcr-irenirisenergy-06); IREN measured 129.27 GB/s (GB/s).
- Evidence class: published_claim. Origin: imported (SemiAnalysis measurement of IREN, March 2025; reference figure stated in the same sentence).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html` :: Configuration, GPUDirect RDMA via dma_buf; `sessions/clustermax-cloudreview-20260929/claims.all.jsonl` :: cmcr-irenirisenergy-05..08, cmcr-buzzhpc-14 (about 10x lower than expected), cmcr-buzzhpc-16.
- Verified by: audit:gpus.gpuDirectRdmaPath; audit:gpus.gpuDirectRdmaPath.nvidiaPeermemLegacy; audit:gpus.pcieAcs.enabled; audit:gpus.gdrcopy.installed.
- Penalized by 9 review sentences across 4 providers: `cmcr-buzzhpc-14`, `cmcr-buzzhpc-16`, `cmcr-irenirisenergy-05`, `cmcr-irenirisenergy-06`, `cmcr-irenirisenergy-07`, `cmcr-irenirisenergy-08` and 3 more (full list in floor.json).
  - `cmcr-buzzhpc-14` (BuzzHPC): "To get around all of this, we ran a 2-node nccl test with the pytorch-bundled libnccl. Unfortunately, we did not see expected bandwidth (we about 10x lower than expected)."
- Note: NVIDIA and multi-node specific. The MI300X analogue is UNKNOWN in the estate; standalone harness cannot establish RDMA readiness (audit REPORT).

#### O-13. Base image AI-ready out of the box: GPU driver, Docker, container toolkit (or ROCm equivalent), python, pip, venv, current PyTorch.

- Threshold or reference: nvidia-smi && nvcc --version work; python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())" prints True and the GPU count; AMD: rocm/pytorch container runs with /dev/kfd and /dev/dri (boolean).
- Evidence class: published_claim. Origin: imported (SemiAnalysis expectation).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/expectations_standalone.html` :: Configuration.
- Verified by: audit:containers.nvidiaContainerToolkit; audit:securityVersions.nvidiaDriver.status; audit:software.nccl.installed; catalog:gpu-drivers (no graded check); probe/fingerprint.sh.
- Penalized by 20 review sentences across 14 providers: `cmcr-amazonwebservices-17`, `cmcr-amazonwebservices-18`, `cmcr-buzzhpc-08`, `cmcr-cudocompute-12`, `cmcr-cudocompute-13`, `cmcr-gmi-06` and 14 more (full list in floor.json).
  - `cmcr-amazonwebservices-17` (Amazon Web Services (AWS)): "In addition, the standard, documented path for getting started with a single GPU instance does not actually produce a working GPU instance."

#### O-14a. NVIDIA GPU driver at or above the minimum for its branch.

- Threshold or reference: branch minima: 535: 535.309.01, 570: 570.211.01, 580: 580.159.03, 590: 590.48.01, 595: 595.71.05 (bulletin: GPU Display Driver, May 2026) (version).
- Evidence class: published_claim. Origin: imported (SemiAnalysis ClusterMAX audit table; underlying vendor bulletins cited in the file).
- Sources: `sessions/public-tail-20260929/lanes/cmax-audit/repo/cmax/scripts/1-audit/minimum-versions.json` :: minimum-versions.json generated 2026-08-30T07:24:57Z, maxAgeDays 10, gracePeriodDays 3, schemaVersion 1 (the audit tool policy allows a table 10 days old plus 3 days grace; this copy is 30 days old on 2026-09-29); `sessions/public-tail-20260929/lanes/cmax-audit/raw/upstream-minimum-versions.json` :: upstream master table generated 2026-09-25T04:03:23Z (UTF-16 file); compared component by component with the copy: identical minima for every component except NVHPC; `sessions/public-tail-20260929/lanes/cmax-audit/REPORT.md` :: copied checkout is HEAD 97865af, four commits behind fetched master; `sessions/clustermax-cloudreview-20260929/raw/criteria_security.html` :: Every component patched to at least the published ClusterMAX minimum version.
- Verified by: audit:securityVersions.nvidiaDriver.status; rubric:STK-01.
- Penalized by 1 review sentence across 1 provider: `cmcr-cudocompute-12`.
  - `cmcr-cudocompute-12` (CUDO Compute): "Furthermore, the base Ubuntu image was not AI-ready out of the box. The driver version and nvidia container toolkit version provided were significantly out of date (meaning insecure)."

#### O-14b. NVIDIA Container Toolkit at or above minimum.

- Threshold or reference: >= 1.19.1 (June 2026 bulletin); criteria security also names CVE-2024-0132, CVE-2025-23359, CVE-2025-23266 (version).
- Evidence class: published_claim. Origin: imported (SemiAnalysis ClusterMAX audit table; underlying vendor bulletins cited in the file).
- Sources: `sessions/public-tail-20260929/lanes/cmax-audit/repo/cmax/scripts/1-audit/minimum-versions.json` :: minimum-versions.json generated 2026-08-30T07:24:57Z, maxAgeDays 10, gracePeriodDays 3, schemaVersion 1 (the audit tool policy allows a table 10 days old plus 3 days grace; this copy is 30 days old on 2026-09-29); `sessions/public-tail-20260929/lanes/cmax-audit/raw/upstream-minimum-versions.json` :: upstream master table generated 2026-09-25T04:03:23Z (UTF-16 file); compared component by component with the copy: identical minima for every component except NVHPC; `sessions/public-tail-20260929/lanes/cmax-audit/REPORT.md` :: copied checkout is HEAD 97865af, four commits behind fetched master; `sessions/clustermax-cloudreview-20260929/raw/criteria_security.html` :: Every component patched to at least the published ClusterMAX minimum version.
- Verified by: audit:securityVersions.nvidiaContainerToolkit.status.
- Penalized by 6 review sentences across 4 providers: `cmcr-cudocompute-12`, `cmcr-fluidstack-19`, `cmcr-gmocloud-14`, `cmcr-gmocloud-15`, `cmcr-voltagepark-26`, `cmcr-voltagepark-27`.
  - `cmcr-cudocompute-12` (CUDO Compute): "Furthermore, the base Ubuntu image was not AI-ready out of the box. The driver version and nvidia container toolkit version provided were significantly out of date (meaning insecure)."

#### O-14c. CUDA Toolkit at or above minimum.

- Threshold or reference: >= 13.1 (January 2026 bulletin) (version).
- Evidence class: published_claim. Origin: imported (SemiAnalysis ClusterMAX audit table; underlying vendor bulletins cited in the file).
- Sources: `sessions/public-tail-20260929/lanes/cmax-audit/repo/cmax/scripts/1-audit/minimum-versions.json` :: minimum-versions.json generated 2026-08-30T07:24:57Z, maxAgeDays 10, gracePeriodDays 3, schemaVersion 1 (the audit tool policy allows a table 10 days old plus 3 days grace; this copy is 30 days old on 2026-09-29); `sessions/public-tail-20260929/lanes/cmax-audit/raw/upstream-minimum-versions.json` :: upstream master table generated 2026-09-25T04:03:23Z (UTF-16 file); compared component by component with the copy: identical minima for every component except NVHPC; `sessions/public-tail-20260929/lanes/cmax-audit/REPORT.md` :: copied checkout is HEAD 97865af, four commits behind fetched master; `sessions/clustermax-cloudreview-20260929/raw/criteria_security.html` :: Every component patched to at least the published ClusterMAX minimum version.
- Verified by: audit:securityVersions.cudaToolkit.status.

#### O-14d. DCGM and DCGM exporter at or above minimum.

- Threshold or reference: DCGM >= 4.5.3; dcgm-exporter >= 4.8.2 (July 2026 bulletin) (version).
- Evidence class: published_claim. Origin: imported (SemiAnalysis ClusterMAX audit table; underlying vendor bulletins cited in the file).
- Sources: `sessions/public-tail-20260929/lanes/cmax-audit/repo/cmax/scripts/1-audit/minimum-versions.json` :: minimum-versions.json generated 2026-08-30T07:24:57Z, maxAgeDays 10, gracePeriodDays 3, schemaVersion 1 (the audit tool policy allows a table 10 days old plus 3 days grace; this copy is 30 days old on 2026-09-29); `sessions/public-tail-20260929/lanes/cmax-audit/raw/upstream-minimum-versions.json` :: upstream master table generated 2026-09-25T04:03:23Z (UTF-16 file); compared component by component with the copy: identical minima for every component except NVHPC; `sessions/public-tail-20260929/lanes/cmax-audit/REPORT.md` :: copied checkout is HEAD 97865af, four commits behind fetched master; `sessions/clustermax-cloudreview-20260929/raw/criteria_security.html` :: Every component patched to at least the published ClusterMAX minimum version.
- Verified by: audit:securityVersions.dcgm.status; audit:securityVersions.dcgmExporter.status.

#### O-14e. Docker Engine at or above minimum.

- Threshold or reference: >= 29.7.0 (2026-07-30 release notes) (version).
- Evidence class: published_claim. Origin: imported (SemiAnalysis ClusterMAX audit table; underlying vendor bulletins cited in the file).
- Sources: `sessions/public-tail-20260929/lanes/cmax-audit/repo/cmax/scripts/1-audit/minimum-versions.json` :: minimum-versions.json generated 2026-08-30T07:24:57Z, maxAgeDays 10, gracePeriodDays 3, schemaVersion 1 (the audit tool policy allows a table 10 days old plus 3 days grace; this copy is 30 days old on 2026-09-29); `sessions/public-tail-20260929/lanes/cmax-audit/raw/upstream-minimum-versions.json` :: upstream master table generated 2026-09-25T04:03:23Z (UTF-16 file); compared component by component with the copy: identical minima for every component except NVHPC; `sessions/public-tail-20260929/lanes/cmax-audit/REPORT.md` :: copied checkout is HEAD 97865af, four commits behind fetched master; `sessions/clustermax-cloudreview-20260929/raw/criteria_security.html` :: Every component patched to at least the published ClusterMAX minimum version.
- Verified by: audit:securityVersions.docker.status.

#### O-14f. runc at or above the fixed version for its minor line.

- Threshold or reference: minima: 0.1: 0.1.0, 1.0: 1.0.3, 1.1: 1.1.14, 1.2: 1.2.8, 1.3: 1.3.6, 1.4: 1.4.3, 1.5: 1.5.0-rc.3 (version).
- Evidence class: published_claim. Origin: imported (SemiAnalysis ClusterMAX audit table; underlying vendor bulletins cited in the file).
- Sources: `sessions/public-tail-20260929/lanes/cmax-audit/repo/cmax/scripts/1-audit/minimum-versions.json` :: minimum-versions.json generated 2026-08-30T07:24:57Z, maxAgeDays 10, gracePeriodDays 3, schemaVersion 1 (the audit tool policy allows a table 10 days old plus 3 days grace; this copy is 30 days old on 2026-09-29); `sessions/public-tail-20260929/lanes/cmax-audit/raw/upstream-minimum-versions.json` :: upstream master table generated 2026-09-25T04:03:23Z (UTF-16 file); compared component by component with the copy: identical minima for every component except NVHPC; `sessions/public-tail-20260929/lanes/cmax-audit/REPORT.md` :: copied checkout is HEAD 97865af, four commits behind fetched master; `sessions/clustermax-cloudreview-20260929/raw/criteria_security.html` :: Every component patched to at least the published ClusterMAX minimum version.
- Verified by: audit:securityVersions.runc.status.

#### O-14g. ConnectX/BlueField firmware at or above the fixed build for its train.

- Threshold or reference: trains: 28: 28.4702, 32: 32.1908, 35: 35.8002, 39: 39.8002, 43: 43.8002, 46: 46.3008 (June 2026 bulletin) (version).
- Evidence class: published_claim. Origin: imported (SemiAnalysis ClusterMAX audit table; underlying vendor bulletins cited in the file).
- Sources: `sessions/public-tail-20260929/lanes/cmax-audit/repo/cmax/scripts/1-audit/minimum-versions.json` :: minimum-versions.json generated 2026-08-30T07:24:57Z, maxAgeDays 10, gracePeriodDays 3, schemaVersion 1 (the audit tool policy allows a table 10 days old plus 3 days grace; this copy is 30 days old on 2026-09-29); `sessions/public-tail-20260929/lanes/cmax-audit/raw/upstream-minimum-versions.json` :: upstream master table generated 2026-09-25T04:03:23Z (UTF-16 file); compared component by component with the copy: identical minima for every component except NVHPC; `sessions/public-tail-20260929/lanes/cmax-audit/REPORT.md` :: copied checkout is HEAD 97865af, four commits behind fetched master; `sessions/clustermax-cloudreview-20260929/raw/criteria_security.html` :: Every component patched to at least the published ClusterMAX minimum version.
- Verified by: audit:securityVersions.connectxFirmware.status.
- Note: Scale-out harness only; standalone excluded. Not applicable to a single VM.

#### O-14h. BlueField VIRTIO-Net controller firmware at or above the fixed release line.

- Threshold or reference: lines: GA: 25.10.6, LTS23: 23.10.23, LTS24: 24.10.50, LTS25: 25.10.2 (version).
- Evidence class: published_claim. Origin: imported (SemiAnalysis ClusterMAX audit table; underlying vendor bulletins cited in the file).
- Sources: `sessions/public-tail-20260929/lanes/cmax-audit/repo/cmax/scripts/1-audit/minimum-versions.json` :: minimum-versions.json generated 2026-08-30T07:24:57Z, maxAgeDays 10, gracePeriodDays 3, schemaVersion 1 (the audit tool policy allows a table 10 days old plus 3 days grace; this copy is 30 days old on 2026-09-29); `sessions/public-tail-20260929/lanes/cmax-audit/raw/upstream-minimum-versions.json` :: upstream master table generated 2026-09-25T04:03:23Z (UTF-16 file); compared component by component with the copy: identical minima for every component except NVHPC; `sessions/public-tail-20260929/lanes/cmax-audit/REPORT.md` :: copied checkout is HEAD 97865af, four commits behind fetched master; `sessions/clustermax-cloudreview-20260929/raw/criteria_security.html` :: Every component patched to at least the published ClusterMAX minimum version.
- Verified by: audit:securityVersions.virtioNetBluefield.status; audit:securityVersions.virtioNetBluefield.exposure; audit:securityVersions.dpuHostIsolation.status.
- Note: Only where BlueField DPUs are deployed.

#### O-14i. ROCm at or above the minimum for the Instinct program (AMD seats).

- Threshold or reference: MI300X: 6.4.2; MI308X: 6.4.2; MI325X: 6.4.2; MI210, MI250, MI300A: 7.0.1 (version).
- Evidence class: published_claim. Origin: imported (SemiAnalysis ClusterMAX audit table; underlying vendor bulletins cited in the file).
- Sources: `sessions/public-tail-20260929/lanes/cmax-audit/repo/cmax/scripts/1-audit/minimum-versions.json` :: minimum-versions.json generated 2026-08-30T07:24:57Z, maxAgeDays 10, gracePeriodDays 3, schemaVersion 1 (the audit tool policy allows a table 10 days old plus 3 days grace; this copy is 30 days old on 2026-09-29); `sessions/public-tail-20260929/lanes/cmax-audit/raw/upstream-minimum-versions.json` :: upstream master table generated 2026-09-25T04:03:23Z (UTF-16 file); compared component by component with the copy: identical minima for every component except NVHPC; `sessions/public-tail-20260929/lanes/cmax-audit/REPORT.md` :: copied checkout is HEAD 97865af, four commits behind fetched master; `sessions/clustermax-cloudreview-20260929/raw/criteria_security.html` :: Every component patched to at least the published ClusterMAX minimum version.
- Verified by: audit:securityVersions.* has no ROCm-specific graded id in the 59-check inventory; rocm entry is in the table (programMap); rubric:STK-01.
- Note: The Run 3 A/T0 image was vllm/vllm-openai-rocm:v0.30.0; the host ROCm version on the Hot Aisle seat was not captured in the sources read here (UNKNOWN). The fingerprint probe is the place to capture it.

#### O-14j. Ubuntu noble kernel at or above the fixed package for Fragnesia, Januscape and VMSCAPE.

- Threshold or reference: linux fixed builds: Fragnesia 6.8.0-124.124 (USN-8373-1, CVE-2026-46300); Januscape 6.8.0-137.137 (USN-8630-1, CVE-2026-53359); VMSCAPE 6.8.0-87.88 (USN-7861-1, CVE-2025-40300) (version).
- Evidence class: published_claim. Origin: imported (SemiAnalysis ClusterMAX audit table; underlying vendor bulletins cited in the file).
- Sources: `sessions/public-tail-20260929/lanes/cmax-audit/repo/cmax/scripts/1-audit/minimum-versions.json` :: minimum-versions.json generated 2026-08-30T07:24:57Z, maxAgeDays 10, gracePeriodDays 3, schemaVersion 1 (the audit tool policy allows a table 10 days old plus 3 days grace; this copy is 30 days old on 2026-09-29); `sessions/public-tail-20260929/lanes/cmax-audit/raw/upstream-minimum-versions.json` :: upstream master table generated 2026-09-25T04:03:23Z (UTF-16 file); compared component by component with the copy: identical minima for every component except NVHPC; `sessions/public-tail-20260929/lanes/cmax-audit/REPORT.md` :: copied checkout is HEAD 97865af, four commits behind fetched master; `sessions/clustermax-cloudreview-20260929/raw/criteria_security.html` :: Every component patched to at least the published ClusterMAX minimum version.
- Verified by: audit:security.fragnesia.status; audit:security.januscape.status; audit:security.guestKernel.newerInstalled; catalog:security-vmscape (no graded check).

#### O-15. RBAC, user and group management, external IdP/SSO, sudo on the head node, passwordless SSH between nodes.

- Threshold or reference: user add via CLI or console; RBAC on cluster and storage; OIDC/OAuth IdP integration; sudo -n true; ssh node works without a password (boolean).
- Evidence class: published_claim. Origin: imported (SemiAnalysis expectation).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html` :: Access; `sessions/clustermax-cloudreview-20260929/raw/expectations_kubernetes.html` :: Access, RBAC options with remote SSO; `sessions/clustermax-cloudreview-20260929/raw/criteria_orchestration.html` :: RBAC and SSO implementation.
- Verified by: audit:access.sudoAvailable; audit:access.userManagement; audit:access.externalIdp.detected; audit:access.sshToComputeNodes; catalog:rbac-access (k8s, no graded check).
- Penalized by 15 review sentences across 13 providers: `cmcr-cudocompute-11`, `cmcr-crusoe-23`, `cmcr-dstacksky-14`, `cmcr-hotaisle-09`, `cmcr-neysa-06`, `cmcr-neysa-07` and 9 more (full list in floor.json).
  - `cmcr-cudocompute-11` (CUDO Compute): "We also found it unfortunate that we were logging into the VM as a shared root user, instead of passing RBAC-enforced auth credentials from the console to the underlying VMs."

#### O-16. Third-party security attestation: SOC 1/SOC 2 Type I or II, or ISO 27001.

- Threshold or reference: at least one published; SemiAnalysis labels its absence a Critical Failure (boolean).
- Evidence class: published_claim. Origin: imported (SemiAnalysis criterion); provider trust pages are provider claims.
- Sources: `sessions/clustermax-cloudreview-20260929/raw/criteria_security.html` :: Critical Failure: no SOC 2, ISO 27001 or any other bare minimum security attestation; `sessions/clustermax-cloudreview-20260929/claims.all.jsonl` :: cmcr-hotaisle-04 (SOC 2 Type I, HIPAA, 2.0 page); `sessions/clustermax-cloudreview-20260929/providers/hotaisle/trust.html` :: Hot Aisle states SOC 2 Type 2 and HIPAA (provider claim, fetched 2026-09-29).
- Verified by: desk review of trust page (MANUAL Public desk review mode); no graded audit check.
- Penalized by 10 review sentences across 10 providers: `cmcr-aethir-07`, `cmcr-deepinfra-05`, `cmcr-farmgpu-06`, `cmcr-gpunet-11`, `cmcr-hydrahost-02`, `cmcr-hyperbolic-08` and 4 more (full list in floor.json).
  - `cmcr-aethir-07` (Aethir): "Aethir does not have any security compliance attestation in place for users to assess if the company taking payments and managing the GPU access has access controls in place."
- Note: Provider trust-page statements are published claims until an auditor letter is seen.

#### O-17. Tenant and host isolation: BMC/IPMI restricted, IOMMU passthrough correct, PCIe passthrough boundary, NVLink boundary, InfiniBand PKeys and UFM secured profile, no tenant visibility of other endpoints.

- Threshold or reference: each isolation fact holds or is attested (checklist).
- Evidence class: published_claim. Origin: imported (SemiAnalysis criteria and audit).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/criteria_security.html` :: PKeys, SMKey/SAKey, UFM Secured Bare Metal Cloud profile; `sessions/clustermax-cloudreview-20260929/raw/expectations_standalone.html` :: Security, "BMC/IPMI restriction and security validation".
- Verified by: audit:bmc-ipmi; audit:pcie-passthrough; audit:vm_iommu.status; audit:nvlink-boundary; audit:ufm-profile; audit:security.januscape.status; catalog:ib-tenant-isolation (no graded check); rubric:TEN-01.
- Penalized by 2 review sentences across 2 providers: `cmcr-fptcloud-10`, `cmcr-radiantori-04`.
  - `cmcr-fptcloud-10` (FPT CLOUD): "Our testing showed that PKeys and SAKey were not configured correctly, allowing us to see every other endpoint on the network (i.e. every other customer)."
- Note: Several of these need provider attestation because a tenant cannot see the host (audit REPORT: hidden-host limitations).

#### O-18. Security patch process: proactive notification, NVIDIA embargo program membership, automated rollout of new Container Toolkit on CVE discovery.

- Threshold or reference: process exists; fixes land within hours of a report (hours).
- Evidence class: published_claim. Origin: imported (SemiAnalysis criterion; two review sentences as anchors).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/criteria_security.html` :: Part of NVIDIA security program; Automated rollout of new NVIDIA Container Toolkit versions; `sessions/clustermax-cloudreview-20260929/claims.all.jsonl` :: cmcr-fluidstack-20 (patched within minutes), cmcr-fluidstack-32 (under an hour) as positive anchors.
- Verified by: audit:securityVersions.* (versions only, not process).
- Penalized by 10 review sentences across 5 providers: `cmcr-cudocompute-12`, `cmcr-fluidstack-19`, `cmcr-fluidstack-30`, `cmcr-fluidstack-31`, `cmcr-gmocloud-14`, `cmcr-gmocloud-15` and 4 more (full list in floor.json).
  - `cmcr-cudocompute-12` (CUDO Compute): "Furthermore, the base Ubuntu image was not AI-ready out of the box. The driver version and nvidia container toolkit version provided were significantly out of date (meaning insecure)."

#### O-19. Profiling access for non-root users: Nsight Compute counters and perf.

- Threshold or reference: NVreg_RestrictProfilingToAdminUsers=0; perf_event_paranoid <= 1 and kptr_restrict = 0 (sysctl values).
- Evidence class: published_claim. Origin: imported (SemiAnalysis expectation).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html` :: Monitoring and Health Checks; `sessions/clustermax-cloudreview-20260929/raw/expectations_standalone.html` :: Monitoring and Health Checks; `sessions/clustermax-cloudreview-20260929/raw/expectations_monitoring.html` :: Performance Monitoring.
- Verified by: audit:software.ncu.installed; audit:software.ncu.profilingEnabled; audit:software.perf.installed; audit:software.perf.perfEventParanoid; audit:software.perf.kptrRestrict.
- Penalized by 8 review sentences across 3 providers: `cmcr-coreweave-40`, `cmcr-coreweave-41`, `cmcr-gmocloud-05`, `cmcr-gmocloud-06`, `cmcr-gmocloud-07`, `cmcr-firmussustainablemetalcloud-07` and 2 more (full list in floor.json).
  - `cmcr-coreweave-40` (CoreWeave): "The feedback is here is the security concerns from CoreWeave is way to limiting for a lot of power users. For example as default, systemd is not available, and a lot of CPU and GPU ..."
- Note: ncu is NVIDIA-only; the AMD profiling analogue is UNKNOWN in these sources.

#### O-20. Status page with a machine-readable incident history API.

- Threshold or reference: reachable status page; history back >= 180 days (boolean).
- Evidence class: derived. Origin: ours (R2 collection).
- Sources: `main/clustermax-challenge/retrospective/results/R2-result.md`; `main/clustermax-challenge/retrospective/incidents/SCHEMA.md`.
- Verified by: clustermax-challenge/scripts/collect_status.py.
- Note: See R-01. Hot Aisle: none found.

#### O-21. Honest billing on outages and stuck creates (no charge while unusable).

- Threshold or reference: see R-05 (policy).
- Evidence class: published_claim. Origin: imported.
- Sources: `sessions/clustermax-cloudreview-20260929/claims.all.jsonl` :: see R-05.
- Verified by: counter:step-6; counter:step-10.
- Penalized by 9 review sentences across 4 providers: `cmcr-e2enetworks-11`, `cmcr-e2enetworks-13`, `cmcr-e2enetworks-15`, `cmcr-qubrid-07`, `cmcr-verdadatacrunch-16`, `cmcr-verdadatacrunch-17` and 3 more (full list in floor.json).
  - `cmcr-e2enetworks-11` (E2E Networks): "The most serious issue occurred while we were stuck in this queue, waiting for our slurm cluster to be deployed. We watched as our credit balance was drained, and then went into the ..."

#### O-22. Underlying provider disclosed (who runs the machine).

- Threshold or reference: datacenter operator named in console or docs (boolean).
- Evidence class: published_claim. Origin: imported (SemiAnalysis).
- Sources: `sessions/clustermax-cloudreview-20260929/claims.all.jsonl` :: cmcr-sesterce-19, cmcr-qubrid-13 (ask providers to disclose); IP lookup used by reviewers in cmcr-qubrid-08 and cmcr-vastai-12.
- Verified by: desk review + IP/whois lookup on the delivered seat.
- Penalized by 21 review sentences across 9 providers: `cmcr-dstacksky-11`, `cmcr-dstacksky-12`, `cmcr-dstacksky-13`, `cmcr-dstacksky-19`, `cmcr-runpod-15`, `cmcr-runpod-16` and 15 more (full list in floor.json).
  - `cmcr-dstacksky-11` (Dstack Sky): "However, the abstraction comes with a significant lack of transparency."
- Note: The underlying-provider disclosure status of the two reference shops was not checked here (UNKNOWN).

#### O-23. Support: 24x7 availability and a direct-to-engineer path not routed through sales.

- Threshold or reference: channel exists and first human response time recorded (boolean).
- Evidence class: published_claim. Origin: imported (SemiAnalysis expectation).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/expectations_standalone.html` :: General Expectations; `main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md` :: step 9.
- Verified by: counter:step-9 (channel, first_response_time_s, sales_required).
- Penalized by 5 review sentences across 5 providers: `cmcr-cudocompute-16`, `cmcr-hotaisle-09`, `cmcr-neysa-17`, `cmcr-googlecloud-39`, `cmcr-amazonwebservices-40`.
  - `cmcr-cudocompute-16` (CUDO Compute): "However, the platform is not ready for large scale training and inference due to a lack of managed slurm or kubernetes services, shared file storage, monitoring dashboards, health checks, ..."
- Note: first_response_time_s was never measured for Hot Aisle (unobserved).

#### O-24. Audit logs of resource actions with actor identity, API query, 90-day retention with export, admin-only access at no extra charge.

- Threshold or reference: minimum 90-day retention (days).
- Evidence class: published_claim. Origin: imported (SemiAnalysis criterion).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/criteria_lifecycle.html` :: Key Requirements, audit logs.
- Verified by: no audit check, no counter step.
- Note: No review sentence in the 1,273-row corpus penalizes absence of audit logs. Criterion only.

#### O-25. Egress and storage price transparency; no punitive egress or offboarding fees.

- Threshold or reference: egress and storage rates published (boolean).
- Evidence class: published_claim. Origin: ours (unobserved) and imported (criterion).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/criteria_lifecycle.html` :: No punitive data egress / offboarding fees; `sessions/clustermax-cloudreview-20260929/raw/expectations_standalone.html` :: External storage and network egress cost transparency; `main/hot-aisle/campaign/shop-eval/counter/records/hotaisle-2026-09.json` :: egress_rate, storage_rate unobserved; `main/hot-aisle/campaign/shop-eval/counter/records/digitalocean-2026-09.json`.
- Verified by: counter:step-2 (egress_rate, storage_rate).
- **UNKNOWN.** What would establish it: Read the egress and storage lines on the pricing page and one invoice for each shop.

#### O-26. Current-generation GPU roadmap.

- Threshold or reference: plans or signals to deploy B200, B300 or MI355X by the ClusterMAX 3.0 deadline of Aug 1; absence is a Critical Failure in SemiAnalysis criteria (boolean).
- Evidence class: published_claim. Origin: imported (SemiAnalysis criterion).
- Sources: `sessions/clustermax-cloudreview-20260929/raw/criteria_availability.html` :: Critical Failure.
- Verified by: desk review.
- Penalized by 6 review sentences across 6 providers: `cmcr-akamailinode-04`, `cmcr-hetzner-03`, `cmcr-saladcloud-03`, `cmcr-ovhcloud-05`, `cmcr-alibabacloud-08`, `cmcr-hotaisle-14`.
  - `cmcr-akamailinode-04` (Akamai/Linode): "Akamai has completely ignored all high end GPUs and instead focuses on the RTX 6000 Blackwell."
- Note: Hot Aisle 2.0 review: MI355X may not come until end of year or early next (cmcr-hotaisle-14). Relevant to fit, not to Run 3 economics.

#### O-27. Fresh tenant state on first login: no previous-tenant files, keys or history.

- Threshold or reference: empty home directories, empty shell history, only your key (boolean).
- Evidence class: derived. Origin: ours (unobserved).
- Sources: `main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md` :: step 7; `main/hot-aisle/campaign/shop-eval/counter/records/hotaisle-2026-09.json` :: tenant_hygiene fields unobserved.
- Verified by: counter:step-7.
- **UNKNOWN.** What would establish it: Run counter step 7 immediately after first SSH on each shop.

#### O-28. Default network exposure on first boot.

- Threshold or reference: only SSH open, or documented default-deny firewall (ports).
- Evidence class: derived. Origin: ours (unobserved).
- Sources: `main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md` :: step 8; `main/hot-aisle/campaign/shop-eval/counter/records/hotaisle-2026-09.json` :: firewall_default, open_ports_first_boot unobserved.
- Verified by: counter:step-8.
- **UNKNOWN.** What would establish it: Run a first-boot port scan on each shop.

#### O-29. Self-serve termination with billing confirmed stopped.

- Threshold or reference: delete via console/TUI/API; time_to_confirm_s recorded; billing_stopped_confirmed true (boolean).
- Evidence class: derived. Origin: ours.
- Sources: `main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md` :: step 10; `main/hot-aisle/campaign/shop-eval/counter/records/hotaisle-2026-09.json` :: stop_on_delete_verified=true (balance behaviour); `main/hot-aisle/campaign/shop-eval/MANUAL.md` :: section 6 (never claim billing stopped solely because a VM disappeared).
- Verified by: counter:step-10; counter:step-6.

#### O-30. Hardware fingerprint within kit rules: PCIe link at supported maximum, RAS counters clean, firmware not older than 270 days, no throttle or clock slope over 15%, idle/load power ratio not above 1.5, same-vendor stack versions consistent.

- Threshold or reference: HW-01, HW-02, HW-03, PWR-01, HEALTH-02, STK-01 not WRONG or SIGNAL (rule ids).
- Evidence class: derived. Origin: ours (kit rules; SIGNAL is not a defect).
- Sources: `main/hot-aisle/campaign/shop-eval/diagnose/RUBRIC.md` :: HW-01 to HW-03, PWR-01, HEALTH-02, STK-01, TEN-01, TEN-02.
- Verified by: probe/fingerprint.sh; diagnose/diagnose.py.
- Note: Snapshot and short-load evidence is diagnostic only, not proof of sustained performance or physical root cause (MANUAL section 3).


## 6. Price band

July 2026 per-provider median on-demand $/GPU-hour (imported OpenComputePrices listings, not quotes; series ends 2026-07-29):

| MI300X provider | $ | | H100 provider (lowest 12 and selected) | $ |
|---|---:|---|---|---:|
| digitalocean | 1.99 | | gpuai | 1.5 |
| hot_aisle | 1.99 | | gcore | 1.64 |
| runpod | 2.19 | | latitude | 1.7925 |
| cyfuture_ai | 3.04 | | cudo | 1.8528 |
| crusoe | 3.45 | | horizon | 1.95 |
| oracle | 6.0 | | voltagepark | 1.99 |
| azure | 7.86 | | gmicloud | 2.0 |
|  |  | | upcloud | 2.04 |
|  |  | | vastai | 2.200148 |
|  |  | | theta_edgecloud | 2.29 |
|  |  | | denvr | 2.3 |
|  |  | | imwt | 2.48 |
|  |  | | digitalocean | 5.95 |
|  |  | | lambda | 4.09 |
|  |  | | coreweave | 6.155 |

Medians of provider medians: MI300X $3.04 (7 providers), H100 $2.99 (42 providers). Hot Aisle's own July median shows $1.99 because its VM price rose to $2.99 on 2026-07-27/28; Run 3 used $2.99. In `MARKET.md` Hot Aisle at $2.99 sits at the 33rd percentile of six other MI300X providers.

#### PB-01. H100 tie line: the list $/GPU-hour at which a 1x H100 with DigitalOcean's measured delivery ties Hot Aisle's $0.74/1k on Run 3.

- Threshold or reference: $2.72/GPU-h as published (4.41 x 0.74 / 1.20, rounded inputs); $2.734 from unrounded figures (Hot Aisle $0.7434 per 1k, 4,280 accepted, 69.82-minute window) (USD per GPU-hour).
- Evidence class: derived. Origin: ours.
- Sources: `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` :: What it says, item 2; `main/hot-aisle/campaign/shop-eval/SHORTLIST.md` :: The rule, rule 3; `main/hot-aisle/campaign/market/MARKET.md` :: Run 3 economics by date.
- Verified by: diagnose PRICE-02; SHORTLIST rule 3.
- Note: Tie holds only if the candidate delivers 4,280 accepted per 69.82-minute request-to-release window and Hot Aisle delivers 4,336 per 64.68 minutes. The published $2.72 and the unrounded 2.734 differ by one cent; SHORTLIST calls Massed Compute at $2.73 a one-cent miss, and on unrounded figures it is a tie.

#### PB-02. MI300X tie line: the list $/GPU-hour at which a second MI300X shop delivering Hot Aisle's accepted rate ties $0.74/1k.

- Threshold or reference: $2.99/GPU-h (Hot Aisle's own rate) (USD per GPU-hour).
- Evidence class: derived. Origin: ours.
- Sources: `main/hot-aisle/campaign/shop-eval/SHORTLIST.md` :: rule 3; `main/hot-aisle/data/run3/source/RUN3-RESULTS.md`.
- Verified by: SHORTLIST rule 3; diagnose PRICE-02.
- Note: A same-silicon shop answers operator quality, not hardware economics (SHORTLIST). Cost per 1k for an MI300X-equivalent delivery at other rates: $1.99: 0.495, $2.19: 0.545, $2.39: 0.594, $2.59: 0.644, $3.04: 0.756, $3.45: 0.858, $3.99: 0.992.

#### PB-03. July 2026 per-provider median on-demand $/GPU-hour, MI300X.

- Threshold or reference: median of 7 provider medians = $3.04; digitalocean $1.99, hot_aisle $1.99, runpod $2.19, cyfuture_ai $3.04, crusoe $3.45, oracle $6.0, azure $7.86 (USD per GPU-hour).
- Evidence class: published_claim. Origin: imported (OpenComputePrices aggregator listings; not quotes, not measured).
- Sources: `main/hot-aisle/campaign/market/MARKET.md`; `main/hot-aisle/campaign/market/market-stats.json` :: monthly.2026-07.MI300X; `sessions/public-tail-20260929/lanes/opencomputeprices/REPORT.md`.
- Verified by: market/build_price_history.py.
- Note: Series ends 2026-07-29. Hot Aisle's July median is $1.99 because its 1x/2x/4x VM price moved from $1.99 to $2.99 on 2026-07-27/28; $2.99 is the run price. 3 of 7 providers are at or below $2.99.

#### PB-04. July 2026 per-provider median on-demand $/GPU-hour, H100.

- Threshold or reference: median of 42 provider medians = $2.99; 17 of 42 at or below $2.72; lowest five: gpuai $1.5, gcore $1.64, latitude $1.7925, cudo $1.8528, horizon $1.95; digitalocean $5.95; together $100 (outlier row) (USD per GPU-hour).
- Evidence class: published_claim. Origin: imported (OpenComputePrices; sources disagree).
- Sources: `main/hot-aisle/campaign/market/MARKET.md` :: Limits (getdeploying $3.39 vs skypilot $6.74 for DigitalOcean H100); `main/hot-aisle/campaign/market/market-stats.json` :: monthly.2026-07.H100.
- Verified by: market/build_price_history.py.
- Note: Row-weighted medians are misleading (about $9.0 vs $3.0 provider-median for H100). The full 42-provider table is in floor.json.

#### PB-05. "Above band" means list price above the tie line for that silicon.

- Threshold or reference: H100: list > $2.72 (published) puts cost per 1,000 accepted above $0.74 at DigitalOcean's measured delivery; MI300X: list > $2.99 puts it above at Hot Aisle's delivery. A PRICE-02 finding requires more than 5% above ($0.78) (USD per GPU-hour).
- Evidence class: derived. Origin: ours.
- Sources: `main/hot-aisle/campaign/shop-eval/SHORTLIST.md`; `main/hot-aisle/campaign/shop-eval/diagnose/RUBRIC.md` :: PRICE-02; `main/hot-aisle/data/run3/source/RUN3-RESULTS.md`.
- Verified by: SHORTLIST rule 3; diagnose PRICE-02.
- Note: "Band" is defined here by the tie lines because no source defines a price band. Market medians ($2.99 H100, $3.04 MI300X, July 2026) are context, not a threshold. Price only moves cost when delivery holds; a shop with worse accepted-per-hour has a lower tie line.

#### PB-06. Dated price sensitivity of the Run 3 comparison.

- Threshold or reference: Hot Aisle at $1.99 (2026-03-22 to 2026-07-26): $0.49 per 1k; at $2.99: $0.74. DigitalOcean H100 at $3.39 (public series): $0.92; at $4.41 as run: $1.20 (USD per 1,000 accepted).
- Evidence class: derived. Origin: ours.
- Sources: `main/hot-aisle/campaign/market/MARKET.md` :: Run 3 economics by date; `main/hot-aisle/campaign/market/RUN3-ECONOMICS-BY-DATE.jsonl`.
- Verified by: market/economics_by_date.cjs.
- Note: At listed public prices Hot Aisle is 46% cheaper at $1.99 and 19% cheaper at $2.99; the as-run 38% used DigitalOcean's $4.41, which is not in the public series.


## 7. Evidence classes and what a floor claim may and may not say

From `main/hot-aisle/campaign/shop-eval/MANUAL.md`, `.../counter/PROTOCOL.md`, `.../diagnose/RUBRIC.md` and `main/hot-aisle/campaign/DISCLOSURES.md`.

**May say.** "On [date], for [pinned workload], one allocation of [SKU] at [shop] delivered [count] accepted requests in [window] at list price [rate], costing $X per 1,000 accepted." Give window, config, sources, funding, and the evidence class. A candidate is WRONG on price only when validated same-scope cost exceeds the reference by more than 5%. Different hardware can be compared on buyer-level economics for the same accepted work and cost window.

**May not say.** That a shop is Hot Aisle-grade or meets "the floor" on the basis of unobserved fields (missing observations are not evidence; the checklist score is uncalibrated and cannot rank). That a single allocation characterizes a fleet. That a provider page is measured. That a ticket acknowledgement is a resolution. That a hash proves the source is true. That a benchmark import or a post-hoc regrade is our confirmed result. That different hardware isolates operator quality. That any figure is an invoice (billed_usd is null until reconciled). Provider operator economics (margin, utilization, capital cost, support labor) stay unknown and are never inferred from customer prices or benchmarks. A failure row and an unknown row are never the same result. The kit has not yet been qualified on a new Linux/GPU shop, and the scripted tests use synthetic fixtures.

#### E-01. Every figure carries a source path; measurements carry whose measurement and under what conditions.

- Threshold or reference: no bare numbers (n/a).
- Evidence class: derived. Origin: ours.
- Sources: `main/hot-aisle/campaign/shop-eval/MANUAL.md` :: section 1.
- Verified by: review of this document.

#### E-02. Evidence class labels stay visible: published_claim, operator_report, measured, derived, hypothesis.

- Threshold or reference: a provider page is a published claim until measured; an operator report is self-reported; a ticket acknowledgement is not a resolution; a hash preserves identity, not truth (n/a).
- Evidence class: derived. Origin: ours.
- Sources: `main/hot-aisle/campaign/shop-eval/MANUAL.md` :: section 1.
- Verified by: report status rules.

#### E-03. A failure row and an unknown row never collapse into one result.

- Threshold or reference: PASS, FAIL, UNKNOWN, N/A with reason (n/a).
- Evidence class: derived. Origin: ours.
- Sources: `main/hot-aisle/campaign/shop-eval/MANUAL.md` :: section 5; `main/hot-aisle/campaign/shop-eval/diagnose/RUBRIC.md` :: statuses WRONG, SIGNAL, RIGHT, UNKNOWN, NOT_COMPARABLE.
- Verified by: report status rules.

#### E-04. Hot Aisle is a dated reference observation, not a universal grade or fleet capability; one allocation does not characterize a fleet.

- Threshold or reference: n/a (n/a).
- Evidence class: derived. Origin: ours.
- Sources: `main/hot-aisle/campaign/shop-eval/MANUAL.md` :: preamble, section 1, section 4; `main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md` :: preamble.
- Verified by: review of this document.

#### E-05. Cost bases stay separate (steady-state, modeled allocation, invoice, customer total); never average windows; provider operator economics stay unknown.

- Threshold or reference: n/a (n/a).
- Evidence class: derived. Origin: ours.
- Sources: `main/hot-aisle/campaign/shop-eval/MANUAL.md` :: section 4.
- Verified by: review of this document.

#### E-06. The counter checklist score is uncalibrated and cannot rank providers; missing observations are not evidence a shop meets the floor.

- Threshold or reference: n/a (n/a).
- Evidence class: derived. Origin: ours.
- Sources: `main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md` :: preamble.
- Verified by: review of this document.


## UNKNOWN register

| item | what is unknown | what would establish it |
|---|---|---|
| A-03 | Time from the first sign-up screen to the first create attempt (signup_to_active_account_s). | Run counter step 1 with a fresh email on at least the shortlisted shops and set the bound from the measured distribution. No source sets a signup-to-seat bound; the review corpus supplies only the anti-pattern (over a month at GMI, a 3-month wait at Mithril). |
| P-10 | Peak sustainable accepted rate at the latency gates on a seat. | Run the PREREG calibration on each arm: continuous backlog, at most 256 outstanding requests, up to five minutes after readiness; capacity C is valid only if throughput was stable. Run 3 offered 8,622 requests in 3,600 s (2.395 req/s average, peak 531 arrivals in one minute) with 0 transport failures on A/T0 and N/T0, so capacity is above that but unmeasured. |
| T-07 | p99 TTFT ceiling for burst traffic. | Register a p99 TTFT gate before the next arm from the intended customer SLO, then freeze it with the other gates. No source sets one. |
| R-06 | Numeric SLA floor (monthly uptime percentage and credit schedule). | No source states a minimum. Establish from the intended buyer's outage cost: a floor needs the buyer's own downtime cost per hour and the shop's credit schedule, neither of which the estate has. |
| R-07 | Recovery: detection, acknowledgement, repair, readiness, resumed useful work, rework, operator minutes after a controlled failure of a disposable job. | Run the section 5 drill on a disposable supervised process on each shortlisted shop, and record every timestamp named there. Fleet MTBF cannot be measured from one seat; it needs an agreed fleet sample from the operator (Cooperative host mode). |
| O-25 | Egress and storage price transparency; no punitive egress or offboarding fees. | Read the egress and storage lines on the pricing page and one invoice for each shop. |
| O-27 | Fresh tenant state on first login: no previous-tenant files, keys or history. | Run counter step 7 immediately after first SSH on each shop. |
| O-28 | Default network exposure on first boot. | Run a first-boot port scan on each shop. |

Also stated as UNKNOWN inside items: latency-gated frontier for the Run 3 model on either imported benchmark (P-08, P-09); host ROCm and container-toolkit versions on the two reference seats (O-14i, O-14b); AMD profiling analogue to ncu (O-19); MI300X analogue of the NCCL bandwidth reference (O-12); disclosure status of the underlying provider for both reference shops (O-22); invoice-level reconciliation of every cost (P-03, P-04).
