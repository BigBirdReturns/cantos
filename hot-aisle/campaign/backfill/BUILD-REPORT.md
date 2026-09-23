# Lane D build report

2026-09-23. Built entirely inside `hot-aisle/campaign/backfill/`. No commit, branch, push, provision, rental, SSH, provider API, credentials or messages. The lane's explicit COMMON-BUILD scope was followed. No measured campaign files were changed.

## Files built

- `SOURCES.md`: eight source families, including all requested candidates; URLs, formats, coverage, fields, cadence, evidence type and terms boundaries. Twelve search queries, below the fifteen-query cap. Artificial Analysis excluded from scraping under its published terms.
- `importer.py`: stdlib adapters for InferenceMAX/InferenceX fixed-sequence aggregate JSON and MLPerf LoadGen summaries. Pinned manifest, raw hash verification, local drop-box, optional public raw-file download/cache with actual retrieval receipt, strict offline mode, separate imported tier and persistent fixture marker.
- `delta.py`: raw-metric comparison against all four campaign result directories; each repeat retained. Shape/precision/GPU/metric compatibility, contextual caveats, source hashes, observed ROCm backend parsing, ranked unreproduced observations and explicit blockers.
- `RERUN-POLICY.md`: framework/backend, hardware/firmware, 20% gap and 90-day triggers; minimal confirmation protocols; architectural lessons carried forward without asserting cross-model speedups.
- `README.md`, `SCHEMA.md`: runnable commands, manifest/record contracts, interpretation and limits.
- `test_backfill.py`, `fixtures/manifest.json`, `fixtures/inferencemax.json`, `fixtures/mlperf_log_summary.txt`, and three files under `fixtures/results/run2-explore-hotaisle-mi300x/`: small, explicitly synthetic raw-format/parser fixtures. `.gitattributes` preserves fixture bytes.
- This report.

## Run and validation

From the repository root:

```text
python -B hot-aisle/campaign/backfill/importer.py --self-test
python -B hot-aisle/campaign/backfill/delta.py --self-test
python -B hot-aisle/campaign/backfill/test_backfill.py
```

These entry points run the same offline suite. Final test run: **23 tests, OK**, Python 3.13 on Windows. Tested hashing/tampering, cache misses without network, path containment, mocked full-file retrieval and timestamp receipt, units/seconds conversion, invalid MLPerf logs, finite metrics, class caveats, hardware/count/precision/shape mismatch rejection, zero denominators, fixture separation, ranking/age and backend parsing. An initial test failed because Python's restrictive TemporaryDirectory ACL was inaccessible to this sandbox; tests now use ordinary uniquely named directories under the lane and clean them successfully.

CLI smoke: offline manifest → 9 imported fixture observations → 1 measured-format fixture cell → 4 contextual fixture ratios and 9 ranked unreproduced observations. Temporary output JSON/JSONL files were removed. An invalid JSONL input was also checked to fail nonzero.

Read-only real-results integration: **45 cells**, all four expected arms, with `ROCM_ATTN`, `ROCM_AITER_FA`, and unavailable Run 1 backends distinguished. Nine synthetic imports produced 18 fixture-labelled comparisons and nine unreproduced entries. **These are test counts, not performance results.** No fixture ratios are published as findings, and no real historical checkpoint is asserted reproduced.

Complete import/delta commands and a deliberately unpinned production-manifest template are in [README.md](README.md). All scripts have an offline self-test entry and documented invocation.

## Verification limits / open questions

1. **Live downloads NOT VERIFIED.** The shell's public GitHub HTTPS attempts failed with WinError 10061. Primary web documentation was readable. Mocked download/cache tests pass, but no actual full historical dataset was fetched in this build. Fixture files are authored examples of documented raw formats, not copies of real published runs. First deployment must validate a real pinned file from each source.
2. **Source/model/image pins UNVERIFIED.** No source commit, model revision or image digest was invented. Non-fixture imports require a source commit/tag and expected raw hash; missing model/runtime identity remains UNVERIFIED. The production manifest example intentionally refuses execution until filled.
3. MLPerf system/model/precision metadata is curator-supplied and bound by manifest hash; companion-file references must be reviewed. Accuracy/compliance certification and automatic system-metadata joins are not implemented. Its variable shapes/concurrency are not comparable to the current random-token cells, so they remain rerun candidates without misleading ratios.
4. InferenceX AgentX nested traces and explicit benchmark-outcome validity interpretation need separate adapters; outcome-bearing fixed-sequence records are retained with a ratio hold. Current adapter targets the documented fixed-sequence aggregate contract, not every historical schema generation.
5. MLPerf release-specific result terms and vendor table redistribution rights need review before outward publication. Price/availability sources are inventory only; no pricing importer or allocation evidence is claimed.
6. One empty directory from the initial failed ACL test, `tmpo0ahfmnc`, could not be removed because Windows denies access. It contains no successfully written test data and is not a versioned artifact. Ordinary permissioned cleanup is needed outside this restricted sandbox. Later tests leave no temporary files/directories.

## Operator inputs

No token or approval is needed for offline tests, supplied public files, or the scripts' supported public raw GitHub downloads. Supply actual source files, their original URLs, source commits/tags, retrieval times and hashes; MLPerf companion metadata/evidence; and verified model/runtime pins where available. For CI artifacts requiring account access, supply an already authorised downloaded artifact, not a credential in the manifest.

Actual checkpoint reruns require a separately frozen workload protocol, model access if gated, compute/spend authorization and available hardware. Publication remains a separate operator decision. This kit requests none of those actions and establishes no new benchmark result.


## Fix round 1

Completed against the locally supplied 100 artifacts on 2026-09-23 (campaign date). This section supersedes the original InferenceX fixture-only and unsupported-agentic limitations above. All writes stayed inside backfill/. No commit, branch, push, SSH, provider calls, live GitHub calls, credentials or messages. Network-restricted execution used the supplied drop-box only.

### Files built or updated

- `importer.py`: real flat fixed-sequence and nested agentic-coding adapters, request counts/accounting/rates, failures, power fields, documented physical GPU-count precedence, and artifact provenance. Adds `--raw-dir` to build and import a hash-bound source manifest.
- `fetch_history.py`: stdlib GitHub history kit using gh or urllib/GH_TOKEN, bounded page/archive/retry requests, 403/429 waits, resumable pending-page state, downloaded/expired skips, whole-file post-download filters, index and per-invocation receipts. ZIP paths are never extracted.
- `fixtures/inferencex-{10716032664,10716378525,10718795856,10721648398,10780222898}.json`: five byte-identical real copies, covering both scenarios, split allocations, valid/invalid power and two zero-success rows. `fixtures/manifest.json` binds original hashes/provenance. One InferenceX authored file is retained as `authored-inferencemax.json` via `authored-manifest.json` solely for known-ratio regression tests. Existing authored MLPerf/campaign-reader fixtures remain labelled.
- `test_history.py`, `test_backfill.py`: real-schema tests and mocked history transport/resumption/rate-limit tests, plus retained comparison regressions.
- `delta.py`: source-row and comparable-row counts distinguish metric expansion from observations of runs.
- `summarize.py`: reproducible source-row aggregation and energy/success summary; offline self-test.
- `data-raw/import-manifest.json`: all 100 aggregate hashes, artifact IDs, head SHAs, creation times and three available workflow IDs. This is inside the existing ignored raw cache; retain it with that cache for future reproduction.
- `imported/inferencex-2026-09-23.jsonl`: **198 real source rows / 3,620 imported metric observations**, fixture=false. No new measured benchmark claim.
- `imported/delta-2026-09-23.json`: real comparison against **45** retained campaign cells, **0 comparable source rows**, **0 ratios**.
- `IMPORT-SUMMARY.md`: hardware x framework x scenario counts, weighted request-success rates, valid J/query ranges, failure/empty-file inventories and recommended history selection.
- `README.md`, `SCHEMA.md`, `SOURCES.md`, `.gitattributes`: run instructions, actual schema/GPU rule, current evidence limits, and raw byte preservation.

### How to run

Exact commands are in README.md, section "Fix round 1: real artifacts and resumable history". The completed pipeline was importer `--raw-dir .../data-raw --retrieved-at 2026-09-23T23:40:00Z --output .../imported/inferencex-2026-09-23.jsonl`, delta with that JSONL and `--as-of 2026-09-23`, then `summarize.py`. All run from the repository root. Test with each script's `--self-test`; test modules also run directly with Python -B.

History filter: MI300X/H100/H200 + vllm/sglang + 2048/256 or 8192/512; then check model/class, FP8, one GPU and matching concurrency. H200 has no retained measured campaign arm; sglang remains runtime-different context. The complete fetch command is in IMPORT-SUMMARY.md. Repeat to resume; use --restart after completion or changed filters to scan from page 1 while retaining downloaded IDs.

### Test output summary

**PASS: 40 distinct offline tests** on Python 3.13/Windows. Final importer, delta and summarizer `--self-test` each ran 40/40; fetcher self-test and direct test_history.py ran 17/17; direct test_backfill.py ran 23/23. Covered actual nested latency conversion, count/energy retention, zero-success and 0/0 cases, GPU topology, identity/hash stability, summary deduplication, cap/resume, existing/expired skips (including HTTP 410), 403/429 delays and persisted cooldown, filters preserving bytes, interrupted fetch receipts, unsafe ZIP member rejection, gh header parsing, and mocked urllib authentication/redirect stripping. No live transport was tested.

Initial new-test failures were test assumptions: the mock's page=1 check accidentally matched per_page=100, and one zero-success fixture has total=0 (its rate is undefined, not zero). Both assertions/fixtures were corrected; final runs all pass. Original 23 comparison tests passed throughout.

The real import processed every local aggregate: 28 empty lists recorded in the manifest/summary, 149 fixed-sequence and 49 agentic source rows, and all three zero-success rows retained (0/19, 0/0, 0/27). Raw supplied files were not rewritten. Missing/invalid power is never silently zero; rates include agentic warmup-drop accounting and are not correctness/error rates.

### Open questions and operator inputs

- Live gh/urllib reads and roughly 11k-artifact completeness remain **UNVERIFIED**. This session needed no tokens. To run history later, supply authenticated gh or GH_TOKEN with access to the public Actions artifacts, in a network-permitted environment. Tokens never belong in manifests or reports.
- GitHub offset pagination can shift as artifacts arrive/expire; after a long scan, restart once to catch shifted/new IDs. Expired bytes cannot be recovered by this kit. Do not run concurrent writers on one cache. Filters annotate matching row indices after download; all raw rows remain retained.
- The initial retrieval timestamp is approximate per the operator brief; 97 workflow run IDs are unavailable, and measurement timestamps/model revisions remain UNVERIFIED. Image digests/head SHAs are retained as supplied, not independently checked upstream.
- Thirty-six fixed-sequence rows have no request counts; their success rates remain unknown. Some energy readings are invalid/missing. Empty artifact files contain no observations and are listed separately.
- No comparable performance claim can be drawn from this latest-100 snapshot. History retrieval and a newly frozen rerun protocol are needed to find/reproduce suitable checkpoints. Publication, compute spending and live benchmarks were not performed and still require their own operator direction.
