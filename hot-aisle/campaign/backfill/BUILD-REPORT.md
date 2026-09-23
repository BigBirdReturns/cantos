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
