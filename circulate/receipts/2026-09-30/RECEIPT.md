# Circulation receipt 2026-09-30

**Overall: OK**  |  mode: online  |  2026-09-30T17:23:35Z to 2026-09-30T17:47:02Z (1406.8 s of stage time)  |  git 9aebbff64328  |  python 3.13.15, node 24.19.0

## Stages

| Stage | Status | Seconds | Counts | Notes |
|---|---|---:|---|---|
| inferencex | OK | 75.65 | index_before 4168, listing_pages 2, new_artifacts_found 79, downloaded 79, imported 79, empty 33, refused 0, source_rows 172 | 79 artifacts imported (172 source rows, 3488 metric observations, 33 empty), 0 refused. |
| prices | SKIP | 0.35 | assets 8, days_before 2201, changed_assets 0, removed_assets 0 | release unchanged: all 8 asset digests equal the recorded set (GPU Pricing Data — 2026-07-29 14:36 UTC). |
| status | OK | 744.93 | providers_in_file 63, collected 23, hold 0, unsupported 0, failed 0, no_collector 40, incidents 1548 | 23 providers collected (1548 incident records); 0 unreachable (HOLD), 0 unsupported, 40 without a collector. |
| economics | OK | 1.6 | index_days 120, days_with_verified_files 120, committed_rows 121, rows_computed 121, dated_priced 120 | recomputed 121 rows through the page engine; byte-identical to the committed file. |
| delta | OK | 10.33 | inputs 4, observations 11915, source_rows 1868, chunks 1, measured_cells 45, comparable_observations 0, gaps 0, ranked 11915 | 11915 observations vs 45 measured cells: 0 comparable, 11915 ranked. |
| r2-standing | OK | 230.67 | window_start 2026-04-03, window_end 2026-09-30, included_primary 16, included_secondary 22, reading inconclusive, seed 20260930, spearman_rho 0.41480895520125544 | STANDING: window 2026-04-03..2026-09-30, 16 providers, Spearman rho 0.41480895520125544 on major_or_critical_incident_count, bootstrap 95% interval [-0.060615444347344644, 0.7728006354170801], permutation p 0.1109; reading inconclusive. |
| newsletter | SKIP | 0.22 | sitemap_posts 343, known 343, new_found 0, fetched 0, appended 0, paywalled 0, no_body 0, failed 0 | no post in the sitemap (343) is missing from the packet or the standing rows (343 known). |
| packet | SKIP | 0.71 | base_rebuild_identical True, base_rebuild_matches_build_notes True, standing_rows 0 | no standing newsletter rows; the committed packet stands (rebuilt from the lane inputs: identical=True). |
| frontdoor | SKIP | 0.46 | market_embed_in_sync True, record_embed_in_sync True, record_verified True, record_sha256 57e21870e378259d, kit kit matches source: 42 files, 1864029 bytes | nothing to rebuild: embeds equal data/market.json and data/run3/record.json, Run 3 record verified, kit matches source. |
| tests | OK | 341.91 | suites 7, passed 7, failed 0, skipped 0 | 7 suites passed. |

## Frozen files

8 frozen files hashed before and after the run and compared with circulate/frozen-hashes.json. Moved: none.

## Probes

PROBES.json: overall PASS, counts {"PASS": 11}.

## Outputs

| Stage | Path | Committed | SHA-256 |
|---|---|---|---|
| inferencex | hot-aisle/campaign/backfill/imported/daily/2026-09-30.jsonl.gz | yes | 67f37f6dd4372591... |
| inferencex | hot-aisle/campaign/backfill/imported/history-index.json | yes | 558cd2dd0b5eb01d... |
| inferencex | hot-aisle/campaign/backfill/IMPORT-SUMMARY.md | yes | d8ee659d1a7111d6... |
| status | clustermax-challenge/retrospective/incidents/nebius-standing.json | yes | ecbd32b4b1a29dd4... |
| status | clustermax-challenge/retrospective/incidents/crusoe-r2-standing.json | yes | 8fd8bf8048b129eb... |
| status | clustermax-challenge/retrospective/incidents/fluidstack-standing.json | yes | 29768467778e8305... |
| status | clustermax-challenge/retrospective/incidents/together-ai-standing.json | yes | 62468757d7ba595e... |
| status | clustermax-challenge/retrospective/incidents/lambda-standing.json | yes | 966fafe17228bf42... |
| status | clustermax-challenge/retrospective/incidents/scaleway-standing.json | yes | bdf6a56ca1fcaafc... |
| status | clustermax-challenge/retrospective/incidents/cirrascale-standing.json | yes | a3d270150af02a98... |
| status | clustermax-challenge/retrospective/incidents/gcore-standing.json | yes | 05c118bd9b2304f1... |
| status | clustermax-challenge/retrospective/incidents/hyperstack-standing.json | yes | dfcaca5f86fb3295... |
| status | clustermax-challenge/retrospective/incidents/runpod-standing.json | yes | c6c41e8783e68407... |
| status | clustermax-challenge/retrospective/incidents/atlas-cloud-standing.json | yes | 4a6711b5206cfbdb... |
| status | clustermax-challenge/retrospective/incidents/prime-intellect-standing.json | yes | f76fee3bc8d9f701... |
| status | clustermax-challenge/retrospective/incidents/cudo-compute-standing.json | yes | 48e6367d2c8a28ef... |
| status | clustermax-challenge/retrospective/incidents/latitude-sh-standing.json | yes | 3d600bf72b9826c3... |
| status | clustermax-challenge/retrospective/incidents/lightning-ai-standing.json | yes | 76f71e86f984e70f... |
| status | clustermax-challenge/retrospective/incidents/verda-standing.json | yes | b78a762408b6467e... |
| status | clustermax-challenge/retrospective/incidents/digitalocean-standing.json | yes | b6a93b3b294e326b... |
| status | clustermax-challenge/retrospective/incidents/sharon-ai-standing.json | yes | d802c3081825de20... |
| status | clustermax-challenge/retrospective/incidents/hydra-standing.json | yes | 991e6155860423f6... |
| status | clustermax-challenge/retrospective/incidents/gpu-net-standing.json | yes | b3dabb7bfbaf97f9... |
| status | clustermax-challenge/retrospective/incidents/akamai-standing.json | yes | c8dbe74920337480... |
| status | clustermax-challenge/retrospective/incidents/mithril-standing.json | yes | 7623ed09432b0d4d... |
| status | clustermax-challenge/retrospective/incidents/radiant-standing.json | yes | 2249a571856b681a... |
| status | clustermax-challenge/retrospective/incidents/COLLECTION-LOG-standing.md | yes | d3477995892be8ca... |
| economics | hot-aisle/campaign/market/MARKET.md | yes | 7036d787a2c9e9ab... |
| delta | circulate/retained/delta/delta-standing.json.gz | no (retained) | b879f1af97c00ab5... |
| delta | hot-aisle/campaign/backfill/DELTA-standing.md | yes | cbfb230715f85022... |
| r2-standing | clustermax-challenge/retrospective/results/R2-standing-2026-09-30.json | yes | 8608bf29c3f29594... |
| r2-standing | clustermax-challenge/retrospective/results/R2-standing-2026-09-30.md | yes | 0eeb7aa2487c0e0f... |

## Disclosure

Hot Aisle arm run on a provider credit; costed at undiscounted list price. See hot-aisle/campaign/DISCLOSURES.md. Imported external observations (InferenceX, MLPerf, OpenComputePrices, provider status pages, SemiAnalysis newsletter) are third-party data, not our measurements. Nothing in this receipt invents a value: a gated or unreachable source is HOLD with its HTTP code.

Bulk outputs (raw artifacts, raw pages, per-day price files, full delta) are not committed; in CI they are uploaded as the workflow artifact `circulate-retained-2026-09-30`.
