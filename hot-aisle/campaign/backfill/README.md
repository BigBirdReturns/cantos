# Lane D: historical backfill kit

Stdlib Python 3.10+. Imports historical files into a separate `imported-observation@1` JSONL stream, compares raw metrics to retained campaign cells, and ranks unreproduced checkpoints. No new performance results are asserted. All files are steward-owned; CLI outputs and optional raw caches are machine-generated. No dependencies, deployment, schedules or provider access.

## Run offline

From the repository root (PowerShell or a shell):

```text
python -B hot-aisle/campaign/backfill/importer.py --self-test
python -B hot-aisle/campaign/backfill/delta.py --self-test
python -B hot-aisle/campaign/backfill/test_backfill.py
python -B hot-aisle/campaign/backfill/importer.py --manifest hot-aisle/campaign/backfill/fixtures/manifest.json --offline --output hot-aisle/campaign/backfill/fixture-imports.jsonl
python -B hot-aisle/campaign/backfill/delta.py --imports hot-aisle/campaign/backfill/fixture-imports.jsonl --results hot-aisle/campaign/backfill/fixtures/results --allow-fixtures --as-of 2026-09-23 --output hot-aisle/campaign/backfill/fixture-delta.json
```

All three self-test entry points run the same offline suite. Tests include a mocked public download; they never contact the network. `-B` avoids bytecode files. Fixtures are hand-authored raw-format examples, **not fetched historical measurements**. Their manifest has `fixture: true`; outputs preserve it. Delta refuses them unless `--allow-fixtures` is explicit. The sample URL identifies the schema owner, not a purported origin of the invented numbers. Exact fixture bytes are SHA-256 bound and exempted from line-ending conversion.

To check the real measured-cell reader, omit `--results` in the final command; it defaults to `../results`. This reads Run 1 H100/MI300X, Run 2 MI300X and the exploration, preserving each repeat rather than averaging percentiles. Such a run against synthetic imports remains a **software integration test**, not a historical gap finding. All malformed cells fail loudly. Source result files remain unchanged.

## Import full historical files, online or through the drop-box

1. Select actual files from the two sources in [SOURCES.md](SOURCES.md). For InferenceX use fixed-sequence `agg_bmk.json` or a single `agg_*.json`; unpack an authorised artifact locally. Preserve source run ID/attempt, original artifact URL and producing commit, especially for reused CI sweeps. For MLPerf choose a `mlperf_log_summary.txt` and retain matching systems JSON, measurement/config, accuracy and compliance references at the same commit.
2. Create a manifest under this directory with the contract below and `fixture: false`. Record actual retrieval timestamp and SHA-256 of original bytes. Prefer full commit SHAs; release tags are accepted but bytes are still hash-checked. Model revisions and image digests must be full pins or `UNVERIFIED`; never infer an image digest from a tag. `observed_at` is the measurement timestamp if known, otherwise null.
3. Put original raw files at manifest-relative `path` locations. This is the local drop-box path for blocked downloads or GitHub Actions artifacts. Nothing executes imported scripts. Metadata and reference URLs remain declarations to review; a manifest hash is not evidence that those declarations are true.
4. Run the importer with `--offline`. For a missing public file hosted at `https://raw.githubusercontent.com/<owner>/<repo>/<pinned-revision>/<path>`, omit `--offline` to download the full file (64 MiB maximum). URL revision must match the declared pin. Pre-existing cached bytes are always verified; no silent overwrite or fallback. All files must validate before any JSONL output is written. Successfully verified cache files can remain after a later input fails.

```text
python -B hot-aisle/campaign/backfill/importer.py --manifest hot-aisle/campaign/backfill/observed.json --output hot-aisle/campaign/backfill/imported.jsonl
python -B hot-aisle/campaign/backfill/importer.py --manifest hot-aisle/campaign/backfill/observed.json --offline --output hot-aisle/campaign/backfill/imported.jsonl
python -B hot-aisle/campaign/backfill/delta.py --imports hot-aisle/campaign/backfill/imported.jsonl --as-of 2026-09-23 --output hot-aisle/campaign/backfill/delta-report.json
```

No tokens required by either script. Direct fetching only supports public raw GitHub HTTPS files and excludes ambient proxies/auth. It does not fetch ZIPs, call provider APIs, browse arbitrary URLs, scrape dashboards, or authenticate to Actions. An operator may supply an already downloaded permitted artifact; no credential should be put in a manifest. Live download execution is **UNVERIFIED** in this environment. A successful live fetch writes a `*.retrieval.json` sidecar with the actual UTC retrieval time, URL, revision and raw hash; subsequent offline reads verify and reuse it. Local drop-box files without that sidecar use the curator's declared original retrieval time.

## Manifest contract

```json
{
  "schema": "backfill-manifest@1",
  "fixture": false,
  "files": [{
    "source": "mlperf",
    "path": "raw/checkpoint/mlperf_log_summary.txt",
    "url": "https://raw.githubusercontent.com/mlcommons/inference_results_v5.0/UNVERIFIED/UNVERIFIED",
    "revision": "UNVERIFIED",
    "retrieved_at": "2026-09-23T00:00:00Z",
    "observed_at": null,
    "sha256": "UNVERIFIED",
    "metadata": {
      "hardware": "UNVERIFIED", "gpus": null, "model": "UNVERIFIED",
      "precision": "UNVERIFIED", "framework": "UNVERIFIED",
      "framework_version": "UNVERIFIED", "model_revision": "UNVERIFIED",
      "image_digest": "UNVERIFIED", "backend": "UNVERIFIED"
    },
    "metadata_evidence": []
  }]
}
```

This deliberately non-runnable example requires real pins/hashes. `source` is `inferencemax` or `mlperf`. InferenceX identity/config comes from each raw row; MLPerf identity is curator-supplied `metadata`, with `metadata_evidence` holding URLs, commit, hashes and field mappings for companion files. No automatic metadata truth/accuracy validation is claimed. Unknown values remain unknown. `path` cannot escape the manifest directory. Use multiple file entries for full historical checkpoint sets, not only the fixtures.

## Output and comparison contract

Each JSONL observation contains schema/tier/fixture, immutable content ID, source, URL/revision/retrieved_at/raw SHA-256, manifest SHA-256, row index, optional measurement time, hardware/count, model/class/revision, precision/detail, framework/version, image/backend, original config, workload shape, gates, metric name/value/units and warnings. [SCHEMA.md](SCHEMA.md) defines missing-value and metric semantics. The importer refuses unsupported layouts, invalid MLPerf logs, empty data and non-finite/negative metrics. Explicit InferenceX outcome metadata is retained with a comparison hold pending a dedicated validity adapter.

`delta.py` requires hardware, GPU count, precision family, input/output tokens, scenario and concurrency to agree. Exact model or the explicit narrow class mapping must agree. Class-only matches are labelled. Framework/version, precision detail, backend, config/flags, model/image pins, dataset/load and gates are all checked for differences/unknowns and emitted beside every ratio. No unknown shape is treated as a wildcard. Per-GPU throughput compares only equal GPU allocations. MLPerf samples/s and inferred token rates are not converted into requests/s.

Ratios use raw metrics, not page-engine gated accepted rates. `engine_table.cjs` remains the authority for those gated results. The absent AMD per-request E2E samples in Run 1 cannot be repaired from summary numbers. Exploration stays post-hoc. The output includes each matching repeat, source hashes and a stable ranked unreproduced list with blockers; no close ratio certifies reproduction. See [RERUN-POLICY.md](RERUN-POLICY.md) for threshold and score definitions.

## What can rot / open limits

Artifact layout, retention, model spelling, precision labels, latency units and LoadGen summary labels can change. Unknown formats fail rather than guess. Fixture-backed parser contracts were checked against current producer documentation, but a real pinned export must be validated before relying on live imports. No historical checkpoint commit/image/model identity was verified here. vLLM versions are copied only if supplied, not extracted speculatively from image tags. MLPerf metadata joining remains curator-driven; this adapter does not certify MLPerf results. Price/availability sources are inventoried only. Schema fixtures do not support performance claims.
