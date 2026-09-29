# circulate — contract (2026-09-29)

One driver runs the whole path on real public sources every cycle, leaves a receipt, and probes try to break every joint. Nothing in this folder invents a value, every row records its producer and conditions, and the sponsor disclosure travels with anything published. Those are the only rules.

## Layout

```
circulate/
  CONTRACT.md            this file
  README.md              how to run, read a receipt, add a stage or probe
  circulate.py           the driver (stdlib + existing repo tools; node for the page engine)
  stages/<name>.py       one module per stage, function run(ctx) -> StageResult
  probes/run_probes.py   runs every probe, writes PROBES.json
  probes/p??_<name>.py   one probe per file, function run(ctx) -> ProbeResult
  receipts/<YYYY-MM-DD>/RECEIPT.json, RECEIPT.md, PROBES.json, stage logs
  LATEST.md              copy of the newest RECEIPT.md (committed)
  index.html             static receipt viewer: reads receipts/index.json
  receipts/index.json    list of receipts (date, overall, per-stage status)
  retained/              bulk outputs that are NOT committed (.gitignore); in CI they are uploaded as workflow artifacts
```

## Stages (run in this order; a failing stage records FAIL and the driver continues)

| Stage | Source | Writes (committed) | Writes (retained/artifact) |
|---|---|---|---|
| inferencex | gh api `SemiAnalysisAI/InferenceX` actions/artifacts?name=results_bmk, newest since backfill/imported/history-index.json | history-index.json update; imported/daily/<date>.jsonl.gz (new rows only, imported-observation@1); IMPORT-SUMMARY standing table | raw artifacts |
| prices | gh api release `thatkavish/OpenComputePrices` latest-data asset digests; download only if a digest changed | data/price-history/INDEX.json (new days appended, sha256 per day); data/market.json | per-day snapshot files |
| status | scripts/collect_status.py for every provider in retrospective/status-pages.json with a supported platform (atlassian-history, atlassian, betterstack, instatus, sorryapp — the last three are new modes to add, matching what incidents/COLLECTION-LOG-2026-09-29.md describes) | incidents/<slug>-standing.json (never overwrite files R1/R2 read); COLLECTION-LOG-standing.md | raw pages |
| economics | page engine (hot-aisle/campaign/market/economics_by_date.cjs) over Run 3 record × dated Hot Aisle + comparator snapshots | campaign/market/RUN3-ECONOMICS-BY-DATE.jsonl, MARKET.md refreshed | — |
| delta | backfill/delta.py over all imported files vs ../results cells | backfill/DELTA-standing.md | full delta json.gz |
| r2-standing | retrospective/run_r2.py functions, rolling 180-day window ending today, 3.0 ordinal, seed = YYYYMMDD; labelled STANDING, unfrozen; frozen plan-R2/R2-result untouched (hash-asserted) | retrospective/results/R2-standing-<date>.{json,md} | — |
| newsletter | newsletter.semianalysis.com sitemap; only slugs not already in research-desk/packets/sources | packets/newsletter-standing.jsonl (append) | raw HTML |
| packet | research-desk/packets/build_packet.js over current claim files + standing newsletter rows; validate_packet.js | packets/PUBLIC-TAIL-standing.research-packet.json (+ .sha256) | — |
| frontdoor | hot-aisle/data/run3/build-run3.cjs --embed if data/market.json changed; scripts/build_kit.py | index.html, MANIFEST.json, workload-report.zip | — |
| tests | fast suites: hot-aisle runner node tests, clustermax-challenge unittest, backfill importer --self-test, integration pytest, research-desk validate_packet | — | logs |

## StageResult / ProbeResult (JSON)

```
{"name": "...", "status": "OK" | "HOLD" | "FAIL" | "SKIP", "started_utc": ..., "finished_utc": ..., "seconds": ...,
 "counts": {...}, "sources": [{"url": ..., "sha256": ..., "retrieved_utc": ...}], "outputs": [{"path": ..., "sha256": ...}],
 "notes": "...", "error": null | "..."}
```
HOLD = the stage ran and correctly refused to produce a number (gated source, rate-limit, comparison hold). FAIL = the stage broke. SKIP = disabled by flag or nothing new. The receipt's `overall` is OK only if no stage is FAIL and every probe is PASS.

## Driver flags

`python circulate/circulate.py [--stage NAME ...] [--offline] [--resume DATE] [--retained DIR]`
`--offline` runs every stage against fixtures under circulate/fixtures/ with no network (this is what tests use). `--resume` re-runs only stages whose StageResult in that receipt is missing or FAIL; completed stages are reused by hash. Exit code 0 when overall OK, 2 when any FAIL, 1 on driver error.

## Probes (each restores what it touched; each asserts frozen-file hashes before and after)

| Probe | Break | Must observe |
|---|---|---|
| p01_packet_tamper | flip one byte in a copy of the standing packet | validate_packet.js exits nonzero naming the failed check |
| p02_evidence_tamper | flip one byte in a copy of data/run3/evidence.json | page engine checksum mismatch; card would not render a number |
| p03_price_shift | +10% Hot Aisle price in a copy of one snapshot | economics recompute changes cost per 1k by exactly the ratio; comparator unchanged |
| p04_bad_artifact | truncated JSON, empty list, tp:0 artifact | importer refuses loudly / emits null count with rule; never a fabricated count |
| p05_gated_source | fetch a gated HF dataset shard | HTTP 401 recorded as HOLD; no retry with credentials |
| p06_stale_kit | edit a kit source in a temp copy | build_kit --check fails; rebuild passes |
| p07_r2_perturb | double one provider's incidents in a copy | rho changes, classification recorded; frozen R2 files hash-identical |
| p08_platform_mislabel | status-pages.json copy with wrong platform | collect_status auto mode either detects the real platform or records UNSUPPORTED; never a silent zero-incident file |
| p09_kill_resume | start driver --offline with an injected sleep stage, kill it, rerun --resume | completed stages reused by hash, killed stage re-run, receipt complete |
| p10_dup_artifact | same bytes under two artifact ids | two provenance rows, source rows deduped by (artifact_id, sha256, row_index) only |
| p11_secret_scan | grep every committed output for credential patterns and the Better Stack webhook placeholder | zero hits (push protection would refuse otherwise) |

## What commits, what does not

Committed: receipts, LATEST.md, index.json, summaries, indexes, standing JSONL under ~30 MB, refreshed page/kit. Not committed: anything under retained/ (raw artifacts, per-day price files, raw HTML, full delta). In CI those go to `actions/upload-artifact` with 30-day retention and the receipt records the artifact name.

## Schedule

`.github/workflows/circulate.yml`: nightly cron + workflow_dispatch + on push to main for this folder; permissions contents: write; runs driver then probes; commits with message `circulate: <date> <overall>`; uploads retained/ as an artifact. Local: `circulate/run_local.cmd` and a Task Scheduler registration script (register only with `--register`), same precedent as sessions/field-niches-20260927/TASK-LAUNCH.json.
