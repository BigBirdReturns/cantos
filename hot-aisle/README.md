# Hot Aisle workload report · 2.0.0

**Drop a vLLM result, enter the billable allocation, download a customer report.**

Live: https://bigbirdreturns.github.io/axm-tools/hot-aisle/

The page is self-contained. Open `index.html` from the offline kit or use the live page. There is no account, backend, model call, upload, telemetry or data persistence. Source files remain in browser memory and clear on reload.

## Use

1. Drop one or more `vllm bench serve` result JSONs on Hot Aisle. Summary and detailed outputs work; appended JSON/JSONL and a single console summary are also accepted.
2. Confirm the number of **billable** GPUs and applicable rate. For the cost of a complete paid interval, enter its total charge instead of extrapolating a benchmark window.
3. Optionally add comparator results. Matching model, revision, representation, tokenizer, workload, cache and offered-load identities are required for a savings comparison. Missing metadata never prevents the individual result report.
4. Download the printable customer HTML and Evidence JSON. Optional latency gates require per-request samples; correctness requires a hash-bound evaluator sidecar. Completed responses are never relabeled as correct tasks.

The sample button loads deliberately tiny **synthetic** fixtures. The banner and exports preserve that status. No AMD/NVIDIA workload measurement was performed for this release.

## What is implemented

- vLLM summary, detailed, array, appended/NDJSON and console import; transactional error handling; duplicate-trial rejection.
- Allocation-aware rental arithmetic, user-supplied total-charge override, current/announced price schedules and both break-even directions.
- Per-request TTFT/E2E gates, optional client queue, separately bound evaluator pass/fail, and joint request-level counting.
- Duration-weighted repeat aggregation. Successful-request percentiles are pooled only with complete raw samples; otherwise per-trial percentile ranges remain distinct.
- Customer HTML, normalized evidence JSON with SHA-256, source-file verification, and a command-line recomputation path. Original filenames, generated text, prompts, error bodies and unknown metadata are not exported.
- Summary mode retains unavailable fields instead of manufacturing per-request evidence. Legacy `request_goodput:` remains a source-reported latency observation, never task correctness.

## Verify

```sh
node scripts/test_workbench.cjs
node scripts/recompute.cjs workload-evidence.json
node scripts/recompute.cjs workload-evidence.json original-hot.json original-comparator.json
python -m unittest discover -s scripts -p 'test_price_math.py' -v
```

Node uses built-in modules only. The verifier loads the exact engine embedded in the page, validates the saved checksum, and recomputes its derived values. Providing all original benchmark files also checks exact hashes and normalization. Without originals it verifies the supplied calculation, not the raw producer evidence. Neither route independently reruns hardware or authenticates the source operator. Evaluator judgments remain supplied evidence.

## Source, scope and maintenance

`FORMATS.md` records the source-pinned format observations and refusal conditions. `FIRST_CAMPAIGN.md` remains the original proposed hardware campaign; v2 implements the file-to-report workflow, not that unexecuted GPU campaign. The initial `scripts/price_math.py` and its tests remain available for the price-only formulas.

`data/prices.json` and the matching embedded `prices-data` block are a **22 September 2026 snapshot**. October rates are announced future AI Cloud infrastructure prices, not Token Factory managed-endpoint quotes. Stock, instance sizes, tax, idle time, commitment terms and unentered costs are not inferred. Custom quotes can be entered directly.

All files are steward-owned. The shipped `index.html` requires no build. The page's `report-engine` script is the executable authority; tests and the CLI extract that exact source. Any edit must rerun the qualification and regenerate the offline ZIP and release manifest. Do not patch frozen releases. There are no scheduled fetches or external-effect adapters.

Independent, MIT-licensed original code by Second Run. Provider, model and runtime names retain their own rights. No provider endorsement, first customer, measured performance win or willingness to pay is asserted.
