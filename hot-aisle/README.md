# Hot Aisle workload report · 2.2.0

**Qualify a deployment. Keep the evidence.**

Live: https://bigbirdreturns.github.io/axm-tools/hot-aisle/

2.2 (22 September 2026) turns the page into an instrument over a connected runner.
The `report-engine` retains its 2.0 arithmetic; the integration standardizes source line endings and pins the resulting identity. Every measured finding projects from it.

- **Connected acquisition.** `runner/` reads the authorized Hot Aisle team, allocations,
  state, balance and retrieved on-demand prices through the public API, drives
  `vllm bench serve` on the allocation with the pinned export flags, and retains the
  exact result bytes. Same core behind a CLI, a localhost service (the page's connected
  mode) and an MCP server. See `RUNNER.md`.
- **Durable evaluations.** A plan is approved by hash. Trials are the unit of
  retention: cancel, a time or spend limit, or a crash keeps every completed trial; a
  reconnecting page, a new process or another interface finds the same job and resumes
  only what never completed.
- **One qualified record, every view a projection.** The record separates observed,
  declared, rule and scenario. The page recomputes it in the browser through the
  engine and checks its checksum before showing a number; the customer report,
  evidence packet, MCP result and CLI summary come from the same record. The shipped
  demonstration record is built by `runner/bin/build-demo.cjs` from the local
  integration environment and is marked synthetic in every projection.
- **Selective revalidation.** A price change recomputes economics from retained
  trials; new concurrency needs only the new cells; a changed request shape or runtime
  identity supersedes the record with a candidate plan; an evaluator correction
  re-adjudicates retained requests. The answer always names the minimal plan.
- **Source-driven finish.** `.github/workflows/hot-aisle-ci.yml` runs the engine suite,
  the runner suite, price arithmetic, browser journeys against the actual revision
  (static and connected) and a kit-consistency check. `scripts/build_kit.py` generates
  `MANIFEST.json` and `workload-report.zip` deterministically from source.

The import path below remains for offline and third-party evidence.

## Use

1. Drop one or more `vllm bench serve` result JSONs on Hot Aisle. Summary and detailed outputs work; appended JSON/JSONL and a single console summary are also accepted.
2. Confirm the number of **billable** GPUs and applicable rate. For the cost of a complete paid interval, enter its total charge instead of extrapolating a benchmark window.
3. Optionally add comparator results. Matching model, revision, representation, tokenizer, workload, cache and offered-load identities are required for a savings comparison. Missing metadata never prevents the individual result report.
4. Download the printable customer HTML and Evidence JSON. Optional latency gates require per-request samples; correctness requires a hash-bound evaluator sidecar. Completed responses are never relabeled as correct tasks.

The sample button loads deliberately tiny **synthetic** fixtures. The banner and exports preserve that status. No AMD/NVIDIA workload measurement was performed for this release: no MI300X or H100 has been measured with this tool yet, and the example record shipped in the page is a software fixture built from the fake benchmark (`runner/fixtures/fake-vllm.cjs`), stored with a portable command (`node runner/fixtures/fake-vllm.cjs`) so the record never carries a build machine's paths.

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
node --test runner/test/*.test.cjs
node scripts/verify_page.mjs            # needs playwright + chromium
python scripts/build_kit.py --check
node scripts/recompute.cjs workload-evidence.json
node scripts/recompute.cjs workload-evidence.json original-hot.json original-comparator.json
python -m unittest discover -s scripts -p 'test_price_math.py' -v
```

Node uses built-in modules only. The verifier loads the exact engine embedded in the page, validates the saved checksum, and recomputes its derived values. Providing all original benchmark files also checks exact hashes and normalization. Without originals it verifies the supplied calculation, not the raw producer evidence. Neither route independently reruns hardware or authenticates the source operator. Evaluator judgments remain supplied evidence.

## Source, scope and maintenance

`FORMATS.md` records the source-pinned format observations and refusal conditions. `FIRST_CAMPAIGN.md` remains the original proposed hardware campaign; v2 implements the file-to-report workflow, not that unexecuted GPU campaign. The initial `scripts/price_math.py` and its tests remain available for the price-only formulas.

`data/prices.json` and the matching embedded `prices-data` block are a **22 September 2026 snapshot**. October rates are announced future AI Cloud infrastructure prices, not Token Factory managed-endpoint quotes. Stock, instance sizes, tax, idle time, commitment terms and unentered costs are not inferred. Custom quotes can be entered directly.

All files are steward-owned. The shipped `index.html` requires no build. The page's `report-engine` script is the executable authority; tests and the CLI extract that exact source. Any edit must rerun the qualification and regenerate the offline ZIP and release manifest. Do not patch frozen releases. No scheduled fetch is activated here. The opt-in runner is the explicit execution adapter, separate from the static report viewer.

Independent, MIT-licensed original code by Second Run. Provider, model and runtime names retain their own rights. No provider endorsement, first customer, measured performance win or willingness to pay is asserted.

## Decision desk handoff

`Publish to connected desk` creates an immutable local `hot-aisle/publication@1` containing this record and its matching sealed packet. `/api/publications` exposes only those explicitly published snapshots. One catalogue is edited in `compute/data/catalog.json` and copied by `integration/build.py`; `node runner/bin/workload.cjs quote do-h100` retrieves the dated DigitalOcean quote. Tenant API prices and custom quotes remain separate evidence. See the combined source `integration/README.md`.
