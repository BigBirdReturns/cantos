# Backfill import summary

Current state: Sept 29 full public InferenceX history and MLPerf LLM rounds. The Sept 23 100-artifact sample section follows unchanged as history. Delta against retained campaign cells: DELTA-2026-09-29.md (0 comparable observations).


<!-- circulate:standing:begin -->
### Standing additions (circulate)

**Imported external observations; not our measurements or qualified results.** Written by `circulate/stages/inferencex.py`; rows are `imported-observation@1` from the same adapter as the full-history import, appended under `imported/daily/`.

Updated 2026-09-29. `history-index.json` holds 4168 artifacts (4161 in the 2026-09-29 baseline, 7 added since, 0 refused by the importer and kept with the reason).

| Day file | New artifacts | Source rows | Metric observations | Empty aggregates |
|---|---:|---:|---:|---:|
| 2026-09-29 | 7 | 28 | 526 | 3 |

| Hardware | Framework | Scenario | Rows | Successful / total |
|---|---|---|---:|---:|
| B200 | sglang | agentic-coding | 11 | 40855 / 44584 |
| GB200 | dynamo-vllm | agentic-coding | 8 | 18314 / 19882 |
| MI355X | sglang-disagg | fixed-sequence | 1 | 80 / 80 |
| MI355X | vllm | agentic-coding | 8 | 3586 / 4614 |
<!-- circulate:standing:end -->

## Full history, 2026-09-29 (InferenceX results_bmk)

**Imported external observations; not our measurements or qualified results.**

4161 artifacts; 16542 source rows; 288891 metric observations. 1883 empty aggregate files retained in the manifest (data-raw/import-manifest-2026-09-29.json). 391 zero-success/failure rows retained with comparison_hold. Prior sample (Sept 23 section below): 100 artifacts, 198 rows, 3620 observations.

Same conventions as the Sept 23 table: counts are source rows; success = sum(successful)/sum(total) over rows with both counts (agentic totals include warmup drops, not an error rate); energy ranges use only power_valid=1 rows with a reported J/query. Hardware is normalized from hw strings (CLUSTER:B200 -> B200). Flat early-July agentic rows carry mean/p90/p95 latency only, with seconds assumed.

| Hardware | Framework | Scenario | Rows | Successful / total | Success rate | Valid energy rows | J/successful query range |
|---|---|---|---:|---:|---:|---:|---:|
| B200 | dynamo-sglang | agentic-coding | 48 | 145255 / 158008 | 91.93% | 6 | 3273.305–39589.682 |
| B200 | dynamo-sglang | fixed-sequence | 118 | 160 / 160 | 100.00% | 20 | 768.022–49718.295 |
| B200 | dynamo-trt | fixed-sequence | 119 | 10 / 10 | 100.00% | 0 | unknown |
| B200 | dynamo-vllm | agentic-coding | 40 | 63501 / 72848 | 87.17% | 33 | 8134.074–92159.577 |
| B200 | dynamo-vllm | fixed-sequence | 398 | unknown | undefined | 20 | 1089.200–82995.057 |
| B200 | sgl-router | agentic-coding | 1 | 124 / 157 | 78.98% | 0 | unknown |
| B200 | sglang | agentic-coding | 112 | 127584 / 146319 | 87.20% | 82 | 1238.825–41327.682 |
| B200 | sglang | fixed-sequence | 551 | 147980 / 147980 | 100.00% | 315 | 443.521–69869.961 |
| B200 | tilert | agentic-coding | 3 | 822 / 837 | 98.21% | 1 | 44543.910–44543.910 |
| B200 | tilert | fixed-sequence | 18 | 192 / 192 | 100.00% | 6 | 21801.621–22766.884 |
| B200 | trt | agentic-coding | 3 | 671 / 778 | 86.25% | 3 | 5369.172–21332.555 |
| B200 | trt | fixed-sequence | 4 | 1400 / 1400 | 100.00% | 4 | 665.220–3073.751 |
| B200 | vllm | agentic-coding | 688 | 1120441 / 1559639 | 71.84% | 222 | 773.153–44886.107 |
| B200 | vllm | fixed-sequence | 1608 | 12980 / 12980 | 100.00% | 278 | 545.370–78835.045 |
| B200 | vllm-router | agentic-coding | 2 | 622 / 688 | 90.41% | 0 | unknown |
| B300 | dynamo-sglang | agentic-coding | 54 | 252873 / 301617 | 83.84% | 29 | 1290.398–43228.203 |
| B300 | dynamo-sglang | fixed-sequence | 44 | unknown | undefined | 11 | 692.150–1000.235 |
| B300 | dynamo-trt | agentic-coding | 4 | 8042 / 8931 | 90.05% | 0 | unknown |
| B300 | dynamo-trt | fixed-sequence | 44 | 720 / 720 | 100.00% | 0 | unknown |
| B300 | dynamo-vllm | agentic-coding | 2 | 1720 / 2263 | 76.01% | 0 | unknown |
| B300 | dynamo-vllm | fixed-sequence | 664 | unknown | undefined | 0 | unknown |
| B300 | sglang | agentic-coding | 115 | 165670 / 213946 | 77.44% | 63 | 1005.374–45496.998 |
| B300 | sglang | fixed-sequence | 515 | 30710 / 30710 | 100.00% | 180 | 421.950–26103.597 |
| B300 | trt | agentic-coding | 6 | 2160 / 2313 | 93.39% | 6 | 1427.867–53939.554 |
| B300 | vllm | agentic-coding | 386 | 1158328 / 1243605 | 93.14% | 163 | 568.912–40480.831 |
| B300 | vllm | fixed-sequence | 2221 | unknown | undefined | 100 | 699.717–18987.718 |
| GB200 | dynamo-sglang | agentic-coding | 38 | 129909 / 140962 | 92.16% | 21 | 4252.150–37655.349 |
| GB200 | dynamo-sglang | fixed-sequence | 401 | 30 / 30 | 100.00% | 177 | 530.500–61372.013 |
| GB200 | dynamo-trt | agentic-coding | 2 | 471 / 489 | 96.32% | 0 | unknown |
| GB200 | dynamo-trt | fixed-sequence | 183 | unknown | undefined | 0 | unknown |
| GB200 | dynamo-vllm | agentic-coding | 36 | 495106 / 541503 | 91.43% | 1 | 101786.513–101786.513 |
| GB200 | dynamo-vllm | fixed-sequence | 110 | unknown | undefined | 0 | unknown |
| GB200 | llm-d-vllm | fixed-sequence | 40 | unknown | undefined | 0 | unknown |
| GB200 | llmd-vllm | agentic-coding | 13 | 118238 / 133681 | 88.45% | 0 | unknown |
| GB200 | llmd-vllm | fixed-sequence | 37 | unknown | undefined | 0 | unknown |
| GB200 | sglang | agentic-coding | 11 | 8733 / 9878 | 88.41% | 7 | 2230.997–19033.618 |
| GB200 | vllm | agentic-coding | 36 | 75594 / 82220 | 91.94% | 17 | 807.141–13569.478 |
| GB200 | vllm | fixed-sequence | 4 | unknown | undefined | 0 | unknown |
| GB200 | vllm-router | agentic-coding | 14 | 6558 / 7048 | 93.05% | 0 | unknown |
| GB300 | dynamo-sglang | agentic-coding | 70 | 977423 / 1087390 | 89.89% | 10 | 1873.885–23852.444 |
| GB300 | dynamo-sglang | fixed-sequence | 686 | 110 / 110 | 100.00% | 175 | 359.687–26059.549 |
| GB300 | dynamo-trt | agentic-coding | 1 | 151 / 153 | 98.69% | 0 | unknown |
| GB300 | dynamo-trt | fixed-sequence | 107 | 420 / 420 | 100.00% | 0 | unknown |
| GB300 | dynamo-vllm | agentic-coding | 52 | 184797 / 209028 | 88.41% | 0 | unknown |
| GB300 | dynamo-vllm | fixed-sequence | 94 | unknown | undefined | 0 | unknown |
| GB300 | sglang | agentic-coding | 35 | 43201 / 51013 | 84.69% | 35 | 804.843–29612.693 |
| GB300 | sglang | fixed-sequence | 5 | unknown | undefined | 0 | unknown |
| GB300 | trt | fixed-sequence | 58 | unknown | undefined | 0 | unknown |
| GB300 | vllm | agentic-coding | 77 | 292939 / 317536 | 92.25% | 77 | 576.327–24374.628 |
| H100 | dynamo-sglang | fixed-sequence | 4 | 40 / 40 | 100.00% | 0 | unknown |
| H100 | dynamo-vllm | fixed-sequence | 82 | unknown | undefined | 0 | unknown |
| H100 | sglang | agentic-coding | 38 | 4552 / 5638 | 80.74% | 33 | 6895.373–531005.741 |
| H100 | sglang | fixed-sequence | 111 | 10830 / 10830 | 100.00% | 85 | 1420.571–12375.028 |
| H100 | trt | fixed-sequence | 15 | 3510 / 3510 | 100.00% | 15 | 202.738–597.749 |
| H100 | vllm | agentic-coding | 14 | 4997 / 5259 | 95.02% | 12 | 146.706–65758.541 |
| H100 | vllm | fixed-sequence | 77 | 23110 / 23110 | 100.00% | 77 | 193.146–6717.246 |
| H200 | dynamo-sglang | agentic-coding | 69 | 21122 / 37163 | 56.84% | 13 | 12695.869–51215.193 |
| H200 | dynamo-sglang | fixed-sequence | 2 | 10240 / 10240 | 100.00% | 0 | unknown |
| H200 | dynamo-trt | fixed-sequence | 5 | 1280 / 1280 | 100.00% | 0 | unknown |
| H200 | sgl-router | agentic-coding | 1 | 6 / 25 | 24.00% | 0 | unknown |
| H200 | sglang | agentic-coding | 64 | 13248 / 34368 | 38.55% | 46 | 4322.401–491903.411 |
| H200 | sglang | fixed-sequence | 196 | 15010 / 15010 | 100.00% | 150 | 1272.015–11964.918 |
| H200 | trt | fixed-sequence | 5 | 3920 / 3920 | 100.00% | 5 | 1548.576–7690.718 |
| H200 | vllm | agentic-coding | 66 | 21470 / 27377 | 78.42% | 32 | 7302.025–867099.576 |
| H200 | vllm | fixed-sequence | 160 | 15544 / 15544 | 100.00% | 89 | 148.043–76803.044 |
| MI300X | atom | fixed-sequence | 10 | unknown | undefined | 0 | unknown |
| MI300X | atom-disagg | fixed-sequence | 12 | unknown | undefined | 0 | unknown |
| MI300X | sglang | agentic-coding | 123 | 12317 / 16136 | 76.33% | 16 | 10282.286–163217.559 |
| MI300X | sglang | fixed-sequence | 53 | 5936 / 5936 | 100.00% | 45 | 0.000–17310.061 |
| MI300X | sglang-disagg | agentic-coding | 9 | 4839 / 5111 | 94.68% | 0 | unknown |
| MI300X | vllm | agentic-coding | 14 | 3660 / 4349 | 84.16% | 11 | 16511.495–74604.905 |
| MI300X | vllm | fixed-sequence | 278 | 22970 / 22970 | 100.00% | 76 | 277.508–44592.503 |
| MI325X | sglang | agentic-coding | 97 | 12927 / 23334 | 55.40% | 13 | 63170.559–247442.933 |
| MI325X | sglang | fixed-sequence | 24 | 160 / 160 | 100.00% | 20 | 4232.623–21278.748 |
| MI325X | sglang-disagg | agentic-coding | 1 | 49 / 220 | 22.27% | 0 | unknown |
| MI325X | vllm | agentic-coding | 13 | 595 / 1181 | 50.38% | 1 | 49035.987–49035.987 |
| MI325X | vllm | fixed-sequence | 170 | 20400 / 20400 | 100.00% | 0 | unknown |
| MI355X | atom | agentic-coding | 364 | 489772 / 548798 | 89.24% | 165 | 1654.971–88528.180 |
| MI355X | atom | fixed-sequence | 343 | 15720 / 15720 | 100.00% | 24 | 2091.498–7567.514 |
| MI355X | atom-disagg | agentic-coding | 11 | 74888 / 88618 | 84.51% | 0 | unknown |
| MI355X | atom-disagg | fixed-sequence | 214 | 40 / 40 | 100.00% | 0 | unknown |
| MI355X | sglang | agentic-coding | 234 | 364742 / 428869 | 85.05% | 117 | 1215.856–51145.154 |
| MI355X | sglang | fixed-sequence | 985 | 85830 / 85830 | 100.00% | 582 | 608.151–26735.356 |
| MI355X | sglang-disagg | agentic-coding | 304 | 1624715 / 1902642 | 85.39% | 0 | unknown |
| MI355X | sglang-disagg | fixed-sequence | 388 | 37608 / 37608 | 100.00% | 0 | unknown |
| MI355X | tilert | agentic-coding | 3 | 745 / 778 | 95.76% | 0 | unknown |
| MI355X | tilert | fixed-sequence | 2 | 32 / 32 | 100.00% | 0 | unknown |
| MI355X | vllm | agentic-coding | 767 | 551526 / 713044 | 77.35% | 198 | 888.986–210877.272 |
| MI355X | vllm | fixed-sequence | 787 | unknown | undefined | 69 | 3254.780–17955.126 |
| MI355X | vllm-disagg | agentic-coding | 67 | 67885 / 78993 | 85.94% | 0 | unknown |
| MI355X | vllm-disagg | fixed-sequence | 412 | 40 / 40 | 100.00% | 0 | unknown |
| cluster:rtx6000pro-lat | vllm | agentic-coding | 5 | 92 / 385 | 23.90% | 0 | unknown |
| rtx6000pro-lat | sglang | fixed-sequence | 24 | unknown | undefined | 0 | unknown |
| rtx6000pro-lat | vllm | fixed-sequence | 41 | unknown | undefined | 0 | unknown |

94 hardware x framework x scenario groups.

## MLPerf Inference v4.0, v4.1, v5.0, v5.1 (LLM LoadGen summaries), 2026-09-29

**Imported external observations; not our measurements or qualified results.**

1474 performance-run summaries (all `Result is : VALID`); 4281 metric observations, from imported/mlperf-2026-09-29.jsonl (lane rows, unchanged). Validity is LoadGen validity only; accuracy and compliance were not evaluated. Hardware is the importer's SKU token where one matches, else the submitted accelerator string; GB200/GB300 are separate from B200. Systems are counted per release. Held = observations carrying comparison_hold (inferred throughput, open division).

| Hardware | Scenario | Summaries | Systems | Models | Releases | Observations | Held |
|---|---|---:|---:|---:|---|---:|---:|
| A100-SXM-80GB | Offline | 1 | 1 | 1 | v4.0 | 3 | 3 |
| B200 | Offline | 78 | 17 | 10 | v4.1, v5.0, v5.1 | 234 | 12 |
| B200 | Server | 103 | 17 | 10 | v4.1, v5.0, v5.1 | 309 | 3 |
| GB200 | Offline | 11 | 5 | 5 | v5.0, v5.1 | 33 | 0 |
| GB200 | Server | 15 | 6 | 5 | v5.0, v5.1 | 45 | 3 |
| GB300 | Offline | 3 | 2 | 2 | v5.1 | 9 | 0 |
| GB300 | Server | 3 | 2 | 2 | v5.1 | 9 | 0 |
| H100 | Offline | 195 | 63 | 10 | v4.0, v4.1, v5.0, v5.1 | 553 | 85 |
| H100 | Server | 192 | 63 | 13 | v4.0, v4.1, v5.0, v5.1 | 549 | 81 |
| H200 | Offline | 223 | 53 | 18 | v4.0, v4.1, v5.0, v5.1 | 667 | 113 |
| H200 | Server | 232 | 51 | 16 | v4.0, v4.1, v5.0, v5.1 | 692 | 92 |
| Intel® Gaudi® 2 AI Accelerator | Offline | 1 | 1 | 1 | v4.0 | 3 | 0 |
| Intel® Gaudi® 2 AI Accelerator | Server | 1 | 1 | 1 | v4.0 | 3 | 0 |
| MI300X | Offline | 32 | 16 | 9 | v4.1, v5.0, v5.1 | 96 | 24 |
| MI300X | Server | 31 | 14 | 5 | v4.1, v5.0, v5.1 | 93 | 9 |
| MI325X | Offline | 36 | 13 | 3 | v5.0, v5.1 | 108 | 0 |
| MI325X | Server | 46 | 13 | 3 | v5.0, v5.1 | 138 | 0 |
| MI355X | Offline | 8 | 3 | 4 | v5.1 | 24 | 24 |
| N/A (no accelerator) | Offline | 24 | 16 | 3 | v4.0, v4.1, v5.0, v5.1 | 67 | 13 |
| N/A (no accelerator) | Server | 24 | 16 | 3 | v4.0, v4.1, v5.0, v5.1 | 67 | 13 |
| NVIDIA GH200 Grace Hopper Superchip 144GB | Offline | 27 | 3 | 5 | v4.1, v5.0 | 81 | 16 |
| NVIDIA GH200 Grace Hopper Superchip 144GB | Server | 27 | 3 | 5 | v4.1, v5.0 | 81 | 16 |
| NVIDIA GH200 Grace Hopper Superchip 96GB | Offline | 15 | 3 | 5 | v4.1, v5.0 | 45 | 14 |
| NVIDIA GH200 Grace Hopper Superchip 96GB | Server | 13 | 3 | 5 | v4.1, v5.0 | 39 | 8 |
| NVIDIA GH200-GraceHopper-Superchip | Offline | 4 | 2 | 3 | v4.0 | 9 | 0 |
| NVIDIA GH200-GraceHopper-Superchip | Server | 4 | 2 | 3 | v4.0 | 9 | 0 |
| NVIDIA GeForce RTX 4090 | Offline | 9 | 5 | 6 | v4.0, v4.1, v5.1 | 23 | 15 |
| NVIDIA GeForce RTX 4090 | Server | 4 | 3 | 3 | v4.0, v4.1 | 10 | 6 |
| NVIDIA GeForce RTX 4090 | SingleStream | 4 | 2 | 2 | v4.0 | 4 | 0 |
| NVIDIA Jetson AGX Orin 64G | Offline | 3 | 2 | 2 | v4.1 | 9 | 5 |
| NVIDIA Jetson AGX Orin 64G | SingleStream | 6 | 2 | 2 | v4.0, v4.1 | 6 | 0 |
| NVIDIA Jetson AGX Thor 128G | Offline | 2 | 1 | 2 | v5.0 | 6 | 6 |
| NVIDIA Jetson AGX Thor 128G | SingleStream | 1 | 1 | 1 | v5.1 | 1 | 1 |
| NVIDIA L40S | Offline | 41 | 21 | 6 | v4.0, v4.1, v5.0, v5.1 | 109 | 28 |
| NVIDIA L40S | Server | 35 | 19 | 5 | v4.0, v4.1, v5.0, v5.1 | 93 | 14 |
| NVIDIA L40S | SingleStream | 1 | 1 | 1 | v4.1 | 1 | 0 |
| NVIDIA RTX PRO 6000 Blackwell Server Edition | Offline | 4 | 1 | 4 | v5.1 | 12 | 0 |
| NVIDIA RTX PRO 6000 Blackwell Server Edition | Server | 5 | 1 | 4 | v5.1 | 15 | 0 |
| TPU v5e | Offline | 1 | 1 | 1 | v4.0 | 2 | 0 |
| TPU v5e | Server | 1 | 1 | 1 | v4.0 | 2 | 0 |
| [MAXSUN] MS-Intel Arc Pro B60 Dual 48G Turbo | Offline | 4 | 2 | 4 | v5.1 | 12 | 0 |
| [MAXSUN] MS-Intel Arc Pro B60 Dual 48G Turbo | Server | 3 | 1 | 3 | v5.1 | 9 | 0 |
| [MAXSUN] MS-Intel Arc Pro B60 Dual 48G Turbo | SingleStream | 1 | 1 | 1 | v5.1 | 1 | 0 |

43 hardware x scenario groups.


## History: Sept 23 sample (100 artifacts)

**Imported external observations; not our measurements or qualified results.**

100 artifacts; 198 source rows; 3620 metric observations. 28 empty aggregate files are retained in the manifest. 3 zero-success/failure rows retained.

Declared retrieval times: 2026-09-23T23:40:00Z. The initial 2026-09-23 23:40 UTC download time is approximate, supplied by the operator; it is not a measurement timestamp. 3 artifact entries have workflow run IDs; missing IDs remain null. Initial artifact IDs, creation times and head SHAs come from index-100.txt, with run IDs from latest.txt. Subsequent fetches use artifact sidecars. Every aggregate is SHA-256 bound in the import manifest.

Counts below are source rows (artifact ID + file hash + row index), not the expanded metric records. Request success is sum(successful)/sum(total) over rows with both counts. Agentic totals include warmup drops: the complement of this ratio is not an error rate or correctness rate. Ranges use only power_valid=1 rows with a reported J/query; missing/invalid power is not zero.

| Hardware | Framework | Scenario | Rows | Successful / total | Success rate | Valid energy rows | J/successful query range |
|---|---|---|---:|---:|---:|---:|---:|
| B200 | sglang | agentic-coding | 2 | 2943 / 3207 | 91.77% | 2 | 2805.495–3046.021 |
| B200 | sglang | fixed-sequence | 38 | 36530 / 36530 | 100.00% | 38 | 615.176–11882.498 |
| B200 | trt | fixed-sequence | 4 | 1400 / 1400 | 100.00% | 4 | 665.220–3073.751 |
| B200 | vllm | agentic-coding | 4 | 4382 / 22095 | 19.83% | 4 | 10854.134–12984.548 |
| B300 | dynamo-sglang | agentic-coding | 3 | 2464 / 2649 | 93.02% | 1 | 40083.503–40083.503 |
| B300 | sglang | agentic-coding | 1 | 1438 / 1615 | 89.04% | 1 | 4062.984–4062.984 |
| B300 | sglang | fixed-sequence | 10 | 5120 / 5120 | 100.00% | 10 | 889.328–8161.496 |
| GB200 | dynamo-sglang | fixed-sequence | 28 | unknown | undefined | 28 | 536.125–10983.112 |
| GB200 | dynamo-vllm | agentic-coding | 1 | 217 / 228 | 95.18% | 0 | unknown |
| GB200 | sglang | agentic-coding | 4 | 8006 / 8714 | 91.88% | 4 | 2230.997–19033.618 |
| GB300 | dynamo-sglang | fixed-sequence | 8 | unknown | undefined | 8 | 927.920–10546.266 |
| GB300 | sglang | agentic-coding | 5 | 21716 / 26681 | 81.39% | 5 | 804.843–9898.011 |
| H100 | sglang | agentic-coding | 1 | 129 / 216 | 59.72% | 1 | 97916.274–97916.274 |
| H200 | sglang | agentic-coding | 8 | 4661 / 5739 | 81.22% | 8 | 8502.815–56413.329 |
| H200 | sglang | fixed-sequence | 22 | 7620 / 7620 | 100.00% | 22 | 1447.250–11910.611 |
| H200 | trt | fixed-sequence | 4 | 3880 / 3880 | 100.00% | 4 | 1548.576–7690.718 |
| MI300X | sglang | fixed-sequence | 4 | 856 / 856 | 100.00% | 3 | 3314.774–12992.165 |
| MI355X | atom | agentic-coding | 6 | 3408 / 3662 | 93.06% | 6 | 4856.300–63177.950 |
| MI355X | atom | fixed-sequence | 3 | 2920 / 2920 | 100.00% | 3 | 2095.146–7567.514 |
| MI355X | atom-disagg | agentic-coding | 4 | 53928 / 63885 | 84.41% | 0 | unknown |
| MI355X | sglang | agentic-coding | 9 | 1875 / 2719 | 68.96% | 1 | 15984.888–15984.888 |
| MI355X | sglang | fixed-sequence | 25 | 10210 / 10210 | 100.00% | 25 | 1012.377–12614.105 |
| MI355X | sglang-disagg | agentic-coding | 1 | 795 / 1065 | 74.65% | 0 | unknown |
| MI355X | sglang-disagg | fixed-sequence | 2 | 160 / 160 | 100.00% | 0 | unknown |
| MI355X | vllm-disagg | fixed-sequence | 1 | 40 / 40 | 100.00% | 0 | unknown |

Comparable source rows: **0 / 198** against 45 retained campaign cells. Comparable metric observations: 0; ratios: 0. See imported/delta-2026-09-23.json for each observation's nearest-cell blockers.

History selection: MI300X/H100/H200, vllm/sglang, fixed sequence 2048/256 or 8192/512. Then require FP8, one physical GPU, matching concurrency and Qwen3-Coder-30B-A3B or Llama-3.3-70B identity/class. H200 supplies context only: our retained campaign has no measured H200 arm. A sglang match remains a runtime-different contextual comparison. Dataset, model/image pins and gates still need review.

Suggested bounded history command (not run here):

```text
python -B hot-aisle/campaign/backfill/fetch_history.py --max 100 --hardware MI300X --hardware H100 --hardware H200 --framework vllm --framework sglang --shape 2048/256 --shape 8192/512
```

Repeat the same command to resume; after completion use --restart to discover new arrivals. Filtering records matching row indices after download; it preserves whole artifacts and failures.

Empty artifact IDs: 10717288987, 10717688395, 10717942775, 10718232434, 10718540987, 10719421392, 10720248995, 10720859589, 10721329143, 10721465855, 10721633317, 10722125919, 10722396385, 10722495139, 10724898782, 10726580514, 10728650809, 10730419577, 10730434405, 10734721187, 10741496242, 10746598386, 10754397174, 10754869254, 10765160208, 10771249984, 10771878561, 10779085316.

Failure rows (artifact:row, successful/total): 10780222898:0 (0/19), 10780222898:1 (0/0), 10781810988:0 (0/27).

Model revisions remain UNVERIFIED unless supplied. Image digests are copied only when present; they were not independently fetched. No live GitHub calls or new benchmarks were run.
