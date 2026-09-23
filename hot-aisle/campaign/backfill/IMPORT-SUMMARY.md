# InferenceX import summary

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
