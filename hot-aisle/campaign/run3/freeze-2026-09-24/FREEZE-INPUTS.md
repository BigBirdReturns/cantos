# Run 3 inputs, fetched 2026-09-24 ~00:00 UTC (raw files kept locally, not committed)

| File | URL | SHA-256 |
|---|---|---|
| HumanEvalPlus.jsonl.gz | https://github.com/evalplus/humanevalplus_release/releases/download/v0.1.10/HumanEvalPlus.jsonl.gz | 272720b90ac375502c8ed23cd791c2a93dfb22a911641a494da74a426c09f101 |
| MbppPlus.jsonl.gz | https://github.com/evalplus/mbppplus_release/releases/download/v0.2.0/MbppPlus.jsonl.gz | af43697e8791c4c149bdfd6b489d8b5412507551ac20e28a439f650b8225db63 |
| AzureLLMInferenceTrace_code.csv | https://raw.githubusercontent.com/Azure/AzurePublicDataset/master/data/AzureLLMInferenceTrace_code.csv | 54e9a6d2a4bd06ba1e060304b900abbc74cbea53de96506e60fe5bb4f2277fb6 |

- **Counts:** HumanEval+ 164, MBPP+ 378, trace 8,818 arrivals, from 2023-11-16 18:17:03.98 to 19:14:19.93 (57.3 min).
- **Trace shape:** very bursty. For example, 531 arrivals in the minute from 18:20 after a 144 s gap. The largest gap is 217 s.
- **Frozen task file:** `tasks.json` (542 tasks), built by `workload.py` at this commit, sha256 `6c508237082261ac927b96825e2f097782389b1cebc3f78360f0665a8db3501f`.
  - Grading references are the upstream release lines, verbatim (`record_raw`). EvalPlus inputs contain IEEE Infinity, which strict JSON re-encoding rejected.
- **Grader image:** `run3-evalplus:0.3.1`, built on OCTO-N01 from `python@sha256:da047cb8f9d1d98e5c070f5300ba9f7274e33b8fc0e5be5ed88740aed1b95ba9`. Image id `sha256:c7c75a7fbc8aa215ddd39930ca0adb2cd4df87de19d4792db8c9f2a7853d7b93`.
  - Smoke on canonical solutions: HumanEval+ pass@1 0.994 (base 0.994), MBPP+ 0.995 (base 1.000). The few canonical failures are grader-uninformative task ids to declare before scoring.
- **Trace start:** the prereg's "first full hour boundary" rule would leave 14 minutes of source. Amended pre-data: start `2023-11-16T18:17:04Z` (the source's first arrival is 18:17:03.98), and rate factor ≤ 0.95 (3,420 s of source spread over 3,600 s).
