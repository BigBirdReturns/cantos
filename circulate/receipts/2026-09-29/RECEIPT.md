# Circulation receipt 2026-09-29

**Overall: OK**  |  mode: online  |  2026-09-29T23:21:04Z to 2026-09-29T23:39:25Z (1079.1 s of stage time)  |  git 6d818de74ea7  |  python 3.13.15, node 24.19.0

## Stages

| Stage | Status | Seconds | Counts | Notes |
|---|---|---:|---|---|
| inferencex | OK | 14.07 | index_before 4161, listing_pages 2, new_artifacts_found 7, downloaded 7, imported 7, empty 3, refused 0, source_rows 28 | 7 artifacts imported (28 source rows, 526 metric observations, 3 empty), 0 refused. |
| prices | OK | 0.29 | assets 8, days_before 2201 | baseline asset digests recorded; release unchanged since the INDEX build (GPU Pricing Data — 2026-07-29 14:36 UTC). |
| status | OK | 721.13 | providers_in_file 63, collected 23, hold 0, unsupported 0, failed 0, no_collector 40, incidents 1542 | 23 providers collected (1542 incident records); 0 unreachable (HOLD), 0 unsupported, 40 without a collector. |
| economics | OK | 0.85 | index_days 120, days_with_verified_files 120, committed_rows 121, rows_computed 121, dated_priced 120 | recomputed 121 rows through the page engine; byte-identical to the committed file. |
| delta | OK | 78.86 | inputs 3, observations 293698, source_rows 18040, chunks 20, measured_cells 45, comparable_observations 0, gaps 0, ranked 293698 | 293698 observations vs 45 measured cells: 0 comparable, 293698 ranked. |
| r2-standing | OK | 93.3 | window_start 2026-04-02, window_end 2026-09-29, included_primary 16, included_secondary 22, reading inconclusive, seed 20260929, spearman_rho 0.41480895520125544 | STANDING: window 2026-04-02..2026-09-29, 16 providers, Spearman rho 0.41480895520125544 on major_or_critical_incident_count, bootstrap 95% interval [-0.05983845468247857, 0.7685678408488934], permutation p 0.113; reading inconclusive. |
| newsletter | SKIP | 0.16 | sitemap_posts 343, known 343, new_found 0, fetched 0, appended 0, paywalled 0, no_body 0, failed 0 | no post in the sitemap (343) is missing from the packet or the standing rows (343 known). |
| packet | SKIP | 0.31 | base_rebuild_identical True, base_rebuild_matches_build_notes True, standing_rows 0 | no standing newsletter rows; the committed packet stands (rebuilt from the lane inputs: identical=True). |
| frontdoor | SKIP | 0.25 | market_embed_in_sync True, record_embed_in_sync True, record_verified True, record_sha256 57e21870e378259d, kit kit matches source: 42 files, 1864073 bytes | nothing to rebuild: embeds equal data/market.json and data/run3/record.json, Run 3 record verified, kit matches source. |
| tests | OK | 169.9 | suites 7, passed 7, failed 0, skipped 0 | 7 suites passed. |

## Frozen files

8 frozen files hashed before and after the run and compared with circulate/frozen-hashes.json. Moved: none.

## Probes

PROBES.json: overall PASS, counts {"PASS": 11}.

## Outputs

| Stage | Path | Committed | SHA-256 |
|---|---|---|---|
| inferencex | hot-aisle/campaign/backfill/imported/daily/2026-09-29.jsonl.gz | yes | a978efa4882f7478... |
| inferencex | hot-aisle/campaign/backfill/imported/history-index.json | yes | 04a00905136dfe52... |
| inferencex | hot-aisle/campaign/backfill/IMPORT-SUMMARY.md | yes | efeee7dc0eebec2a... |
| prices | hot-aisle/data/price-history/INDEX.json | yes | 86f7b9aa5a0a1874... |
| status | clustermax-challenge/retrospective/incidents/nebius-standing.json | yes | cf3e4b3b30a7206a... |
| status | clustermax-challenge/retrospective/incidents/crusoe-r2-standing.json | yes | 5c6602b381f59a74... |
| status | clustermax-challenge/retrospective/incidents/fluidstack-standing.json | yes | 0bfeeaad2d846f4d... |
| status | clustermax-challenge/retrospective/incidents/together-ai-standing.json | yes | 4e7c9c312f8cc3d6... |
| status | clustermax-challenge/retrospective/incidents/lambda-standing.json | yes | b3fe6f82919a446e... |
| status | clustermax-challenge/retrospective/incidents/scaleway-standing.json | yes | 89c857e88a0055c7... |
| status | clustermax-challenge/retrospective/incidents/cirrascale-standing.json | yes | c1e2cbb308f79629... |
| status | clustermax-challenge/retrospective/incidents/gcore-standing.json | yes | dd3325a51d7d0b1c... |
| status | clustermax-challenge/retrospective/incidents/hyperstack-standing.json | yes | 35f2952feb31f1ec... |
| status | clustermax-challenge/retrospective/incidents/runpod-standing.json | yes | 6facf2e7297fecd4... |
| status | clustermax-challenge/retrospective/incidents/atlas-cloud-standing.json | yes | b8165d0187149c3e... |
| status | clustermax-challenge/retrospective/incidents/prime-intellect-standing.json | yes | ce6db610a38c058a... |
| status | clustermax-challenge/retrospective/incidents/cudo-compute-standing.json | yes | e82fb2c4444e8115... |
| status | clustermax-challenge/retrospective/incidents/latitude-sh-standing.json | yes | ab8ab147190c1240... |
| status | clustermax-challenge/retrospective/incidents/lightning-ai-standing.json | yes | 9fd7a62e85896827... |
| status | clustermax-challenge/retrospective/incidents/verda-standing.json | yes | 6e175fe5dac4281e... |
| status | clustermax-challenge/retrospective/incidents/digitalocean-standing.json | yes | 0cc06ff5cc933ceb... |
| status | clustermax-challenge/retrospective/incidents/sharon-ai-standing.json | yes | 46fb1afca195af7f... |
| status | clustermax-challenge/retrospective/incidents/hydra-standing.json | yes | a66cfd9392fe67c1... |
| status | clustermax-challenge/retrospective/incidents/gpu-net-standing.json | yes | 17492e0e35427d26... |
| status | clustermax-challenge/retrospective/incidents/akamai-standing.json | yes | 9cd614df13939fb3... |
| status | clustermax-challenge/retrospective/incidents/mithril-standing.json | yes | 28e61e0b07569048... |
| status | clustermax-challenge/retrospective/incidents/radiant-standing.json | yes | af1bd934d16addf6... |
| status | clustermax-challenge/retrospective/incidents/COLLECTION-LOG-standing.md | yes | ed5d6c4f3793cab0... |
| economics | hot-aisle/campaign/market/MARKET.md | yes | a746d8694b654d37... |
| delta | circulate/retained/delta/delta-standing.json.gz | no (retained) | dc44c6a053ac8694... |
| delta | hot-aisle/campaign/backfill/DELTA-standing.md | yes | 1dbc52158aacb581... |
| r2-standing | clustermax-challenge/retrospective/results/R2-standing-2026-09-29.json | yes | 45dcdbe8f95dd244... |
| r2-standing | clustermax-challenge/retrospective/results/R2-standing-2026-09-29.md | yes | 1ec9b94ce55b39bf... |

## Disclosure

The Hot Aisle arms ran on a **$200 credit given by Hot Aisle** to the Second Run team. Second Run is pitching Hot Aisle a paid engagement. Costs are computed at **undiscounted list price** ($2.99/GPU-hr), not at the credit. The DigitalOcean arm was self-funded at list price ($4.41/GPU-hr). Imported external observations (InferenceX, MLPerf, OpenComputePrices, provider status pages, SemiAnalysis newsletter) are third-party data, not our measurements. Nothing in this receipt invents a value: a gated or unreachable source is HOLD with its HTTP code.

Bulk outputs (raw artifacts, raw pages, per-day price files, full delta) are not committed; in CI they are uploaded as the workflow artifact `circulate-retained-2026-09-29`.
