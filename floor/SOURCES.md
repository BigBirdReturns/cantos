# Sources

Built 2026-09-29. Root: `D:/Projects/Organs/AXM/axm-tools/`. Every path cited in `FLOOR.md`, `PRESCRIPTIONS.md`, `floor.json` and `prescriptions.json` is below with sha256 and size at build time. Nothing here was modified. Numbers not read directly from a file were computed by the build script from the files listed (window minutes, per-hour and per-1,000 figures, percentiles, medians, nearest-rank percentiles, uplift ratios).

## Files

| id | path | sha256 | bytes | used for |
|---|---|---|---:|---|
| MANUAL | `main/hot-aisle/campaign/shop-eval/MANUAL.md` | `7bd72312ec44df1633eaf9ae93f79442566b50a2880a31b0731a0ace23f10f01` | 12,879 | thesis, evidence classes, cost bases, claim limits |
| SHORTLIST | `main/hot-aisle/campaign/shop-eval/SHORTLIST.md` | `81633c21830dbdcb84bd6c5a4b95c49138aa01f7c77e68c5bfe76caf376ef9c4` | 6,238 | tie lines $2.72/$2.99, rules |
| RUBRIC | `main/hot-aisle/campaign/shop-eval/diagnose/RUBRIC.md` | `97a38fa138686a11f4e4e8dc174da5969153fed689bf1b662688ad730ce08549` | 7,376 | PRICE-01/02/03, FLEET-01, HW/STK rules, scope ids |
| PROTOCOL | `main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md` | `fef63ec1e4cf8a7590a5d4c45df7f495b393637c8a2a803efd1546dbecd22bdc` | 10,801 | counter steps 1-10, Hot Aisle-grade definitions |
| CREC_HA | `main/hot-aisle/campaign/shop-eval/counter/records/hotaisle-2026-09.json` | `826bd56abf6309d5ad79e116254e4a0fa85df900b65f751a6ccd77abba760680` | 6,857 | Hot Aisle counter record |
| CREC_DO | `main/hot-aisle/campaign/shop-eval/counter/records/digitalocean-2026-09.json` | `a7d4a246815e8549583500f7c1e69f6662c3865cb513a2be1b982fb12922b274` | 8,064 | DigitalOcean counter record |
| DISC | `main/hot-aisle/campaign/DISCLOSURES.md` | `327114957bbeda4b24eb79af60fcd0a32f8fdf21a64fc5bd9d30af717866714f` | 5,496 | funding, Run 1/2 caveats, Run 2 uplift |
| IDENT | `main/hot-aisle/campaign/identity.json` | `1af0d1546c03a24d284bdc56449e79dcc79c4f8a4c290ad8ac26dab8ecab899d` | 3,067 | registered Run 1 gates, list rates |
| R3README | `main/hot-aisle/campaign/run3/README.md` | `0eaa7dbc38320aaf4eff9b283eb6d8f814efb8c7bd9a66c2e6e66913eb8918e2` | 15,142 | Run 3 kit contract |
| R3PREREG | `main/hot-aisle/campaign/run3/PREREG.md` | `37ee1dbb205d6185168db5d3c7d7cfa5b903268065defbcb669154f6417b4c7f` | 12,736 | Run 3 gates, budgets, stop rules |
| R3FREEZE | `main/hot-aisle/campaign/run3/freeze-2026-09-24/FREEZE.md` | `8cfb30e68a5118a27eb890096f80ce6beef4d2775a0e8e167b7bf9a2db04eb28` | 1,856 | trace start, factor 0.95, calibration outcome |
| R3RES | `main/hot-aisle/data/run3/source/RUN3-RESULTS.md` | `2f29c31a56c72100395af280efc04a682188e74bd760be554f5c0916868b5de2` | 3,995 | Run 3 headline table |
| R3SUM | `main/hot-aisle/campaign/results/RUN3-HOTAISLE-SUMMARY.md` | `0796d8e840a59cea8096f4a0e2e583db7a1ba1d3647f6a3888c59d7a6c5f1d77` | 1,943 | whole-seat correction $0.90 |
| R3HEAD | `main/hot-aisle/data/run3/headline.json` | `33e43f9a89aeeac666646e008c78f767d3c3d00d953ff8da246efa70183595bd` | 1,288 | A/T0 headline p95 E2E and window cost |
| R3ENV | `main/hot-aisle/data/run3/source/env.json` | `4749075dbf594555d76a66af6e3b0db655d95739158f0b963001d7965a3bc0b0` | 1,285 | A/T0 selected backends |
| R3INV | `main/hot-aisle/data/run3/source/invocation.json` | `34e65448616090eb10b4cdcf67bc63ea1b56dff16c05cf8e3a2112e9543b8467` | 1,099 | A/T0 serve invocation |
| A_DET | `main/hot-aisle/campaign/results/run3-scored-a-t0/detailed.json` | `ef907e4cbe45832890109c4ca0d37851ad8e4f087beb70421506af897e6a67ab` | 605,631 | A/T0 per-request latencies (percentiles recomputed) |
| A_LT | `main/hot-aisle/data/run3/source/ledger-times.json` | `bda7da5d7c7a9fae395da7212299450df3c8a16f6352ebe7653d63c93ab89307` | 313 | A/T0 timestamps |
| A_QB | `main/hot-aisle/campaign/results/run3-scored-a-t0/grade/quality-buckets.json` | `694d5a1df8bb27d010e329af092d27349821e0aaf9f55d4f25334a4697fa1ea5` | 2,030 | A/T0 bucket accepted |
| T1_DET | `main/hot-aisle/campaign/results/run3-scored-a-t1/detailed.json` | `d20a5440675b122209a586b1e0353fe3ae957f0179183f66f85636370980a82a` | 605,203 | A/T1 latencies |
| T1_QB | `main/hot-aisle/campaign/results/run3-scored-a-t1/grade/quality-buckets.json` | `c6bed37dee50264b1d0f6697b67cbcfd2de539fb99c66cab48a46c3b15b5864b` | 2,043 | A/T1 buckets |
| N_DET | `main/hot-aisle/campaign/results/run3-scored-n-t0/detailed.json` | `f1a435b029675ffd2a7c6bb96fc0526c5294bb8acdda9ac76bbe764f9fb99b77` | 612,180 | N/T0 latencies |
| N_LT | `main/hot-aisle/campaign/results/run3-scored-n-t0/ledger-times.json` | `1f0e902669b80c882b2d8f72d599d5a89a1fb5c93d256eae5a4a61557c8ecf0a` | 313 | N/T0 timestamps |
| N_CLOSE | `main/hot-aisle/campaign/results/run3-scored-n-t0/closure.json` | `7444670e9652d05a0eeca004f49d8b3009ebec6378f03a790123bffa7411e867` | 603 | N/T0 request and release times |
| N_QB | `main/hot-aisle/campaign/results/run3-scored-n-t0/grade/quality-buckets.json` | `54a2411eb4d3904e3f26567ff605c23c61477ebb21aed45fb63b1c400d11d9a3` | 2,030 | N/T0 buckets |
| EXPLORE | `main/hot-aisle/campaign/run2/EXPLORE.md` | `27b485fb67810b46db9da11f66745b3e64bb1944148c5210e418360cd849ae82` | 885 | Run 2 exploration note |
| X_BASE | `main/hot-aisle/campaign/results/run2-hotaisle-mi300x/` | (directory) | | Run 2 registered cells |
| X_EXPL | `main/hot-aisle/campaign/results/run2-explore-hotaisle-mi300x/` | (directory) | | Run 2 forced-backend cells |
| AVAIL | `main/hot-aisle/campaign/availability/observations.jsonl` | `70b94218de435bbb0ae850975a632f9c7d6ef13de021b2d2ea0f86e50e5eee5a` | 6,868 | availability ledger |
| RERUN | `main/hot-aisle/campaign/backfill/RERUN-POLICY.md` | `3141cd133c46cb751e6bb2b49314e1f881821c1c775a0053cdb4fbaed3d7f876` | 4,939 | carry-lessons, rerun triggers |
| IMPSUM | `main/hot-aisle/campaign/backfill/IMPORT-SUMMARY.md` | `e6a9da729a0dbf8e09a629048f619cf2804e73f2640683c4eba86d50aa20546b` | 18,673 | InferenceX and MLPerf import summary |
| MARKET | `main/hot-aisle/campaign/market/MARKET.md` | `6df6c87a2004dd631538ab464b7fe5ab70b100353a941c60788af041a94431ef` | 4,559 | price context and tie by date |
| MSTATS | `main/hot-aisle/campaign/market/market-stats.json` | `4bec273e18f70a3ddb8c50ec1829ec4bd8f588c0d16594133988face166c00c9` | 16,459 | per-provider July medians |
| ECON | `main/hot-aisle/campaign/market/RUN3-ECONOMICS-BY-DATE.jsonl` | `eecd0ae642f194269446c01e070be7a28b49510503e9e0e14e6288fffeaf733d` | 185,112 | Run 3 economics by date |
| CLAIMS | `sessions/clustermax-cloudreview-20260929/claims.all.jsonl` | `2c61f975a28dd7793f4900517e342a82d6d648c00a8ff670717cf6d75eac016f` | 763,248 | 1,273 review sentences |
| CAPMAN | `sessions/clustermax-cloudreview-20260929/capture-manifest.json` | `98536fc3e0de267cd51d2ab6d856ae6ed7cab243e12d754b767086b8439ef13f` | 57,622 | sha256 and retrieval times of clustermax.ai pages |
| CRREAD | `sessions/clustermax-cloudreview-20260929/README.md` | `64b363eefec093b96a780ed71599dd7049e54846496f56c500d487416b60e67a` | 6,564 | capture findings |
| TCO | `sessions/clustermax-cloudreview-20260929/tco-model.json` | `273bcd0a8434554de8cb0c535a1211c394d279e29a04adb8344f4d4edd8cbdc1` | 21,707 | MTBF presets, goodput assumptions |
| TIERS | `sessions/clustermax-cloudreview-20260929/page-tier-vs-3.0.json` | `38090cef7a4d60d3e21973fb91c50aa5cb846235f6802dc514329f35f95f5375` | 20,440 | 2.0 page tier vs 3.0 tier |
| REP_A | `sessions/clustermax-cloudreview-20260929/reports/batch-A.md` | `38219e4c763d3d141ac9b534f66440009ccb3f71833bf82b17f1238c2fb2ceb4` | 10,270 | provider surface outcomes |
| REP_B | `sessions/clustermax-cloudreview-20260929/reports/batch-B.md` | `a1e598ec25705516757b7036b3ad17ce0811b3890a8b4b23ecfbdb8fe28e31f9` | 13,346 | provider surface outcomes |
| REP_C | `sessions/clustermax-cloudreview-20260929/reports/batch-C.md` | `2d5e19ae37066e0d21371b80486bf9c9318998ae8d0d2b197f8cdebda1ac6a0c` | 24,773 | provider surface outcomes |
| REP_D | `sessions/clustermax-cloudreview-20260929/reports/batch-D.md` | `83992a570a9f99d5a271a2383b2ba24a3fc7e51af5ccd1c7bf85ae71ddadcf85` | 21,908 | provider surface outcomes |
| HA_PROV | `sessions/clustermax-cloudreview-20260929/providers/hotaisle/` | (directory) | | Hot Aisle pricing/trust/status fetch (directory) |
| EXP_SLURM | `sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html` | `3942ce69c6d476549ff5a6780f3b4b4cacee8180fa5180c34cfa537d3a4ccf41` | 126,486 | SemiAnalysis Slurm expectations |
| EXP_K8S | `sessions/clustermax-cloudreview-20260929/raw/expectations_kubernetes.html` | `ee6fc684d8d7eb994a58840b2b5c7fb4d0c4acb2ebdea6e944bb175e440e4e30` | 92,038 | Kubernetes expectations |
| EXP_STAND | `sessions/clustermax-cloudreview-20260929/raw/expectations_standalone.html` | `f94da567a4e2b48ae02b01f410677a12f03b8f1780be4532cc043dd03a46055c` | 90,541 | Standalone expectations |
| EXP_MON | `sessions/clustermax-cloudreview-20260929/raw/expectations_monitoring.html` | `b285009fc4a6743c07da26b41bd7ba03c8efa004ff4d43904d42e37c3d1c47f0` | 102,332 | Monitoring expectations |
| EXP_HC | `sessions/clustermax-cloudreview-20260929/raw/expectations_health-checks.html` | `c1329c39850634fd962159ca6147fdd40892f908fb505a8182d9a2e9267a242e` | 87,105 | Health-check expectations |
| CR_AVAIL | `sessions/clustermax-cloudreview-20260929/raw/criteria_availability.html` | `58e04c5f7bd041b0eea5e6921ab73adb773900a5210d15fa8834786d54274c5d` | 54,386 | criteria: availability |
| CR_LIFE | `sessions/clustermax-cloudreview-20260929/raw/criteria_lifecycle.html` | `406757db1d0d3a7df1168980d219c705b600dcf29cfa76256708dd29a15c0bb2` | 56,559 | criteria: lifecycle |
| CR_MON | `sessions/clustermax-cloudreview-20260929/raw/criteria_monitoring.html` | `4d03e7c9c13940b4e6bcce7c68df60fd3e836ca0b22683ee7bfe2ef109eceddc` | 58,630 | criteria: monitoring |
| CR_NET | `sessions/clustermax-cloudreview-20260929/raw/criteria_networking.html` | `0aff08d945e8d968829922dabccec698ef49eaf32d3f767f6d29f1d432e0c48d` | 55,427 | criteria: networking |
| CR_ORCH | `sessions/clustermax-cloudreview-20260929/raw/criteria_orchestration.html` | `786b7a7c47236c3ae2d0f50072c6e5b2588208bf408613a402dc5d279924a84c` | 58,059 | criteria: orchestration |
| CR_PRICE | `sessions/clustermax-cloudreview-20260929/raw/criteria_pricing.html` | `f319859a53b68b527325c8443fa07516aa1ca4e446e975bb111071f5579e6382` | 53,788 | criteria: pricing |
| CR_REL | `sessions/clustermax-cloudreview-20260929/raw/criteria_reliability.html` | `7cef18d9776c4d3c92881a89701a5cdc022e85cfb073dd21b5c2db5611c0f1a7` | 58,503 | criteria: reliability |
| CR_SEC | `sessions/clustermax-cloudreview-20260929/raw/criteria_security.html` | `a54ec4bc293d8082657c4846ecec22cc9546828d0bbc0f8835baf8c6396bf566` | 74,283 | criteria: security |
| CR_STOR | `sessions/clustermax-cloudreview-20260929/raw/criteria_storage.html` | `004d9955bdbdfa20fb46d83050b448cccb4d704707d0c58de9ea3c00e6f0cb92` | 57,638 | criteria: storage |
| AUDIT_INV | `sessions/public-tail-20260929/lanes/cmax-audit/checks-inventory.json` | `ed07cbfa2304137dc2bfe3f50b6e800b20c9307d0e27eab81413b4cc190a3c3a` | 112,818 | 59 audit checks |
| AUDIT_COV | `sessions/public-tail-20260929/lanes/cmax-audit/rows/criteria-coverage.jsonl` | `8c16adfb01e0e1f58c7445f018656bb9e2e28df181513c2f5741b362342a066d` | 48,045 | 73 catalog rows and graded ids |
| AUDIT_REP | `sessions/public-tail-20260929/lanes/cmax-audit/REPORT.md` | `f9959a8ec32dbc38733a1eaad0f0f2f63ef89874c64a6e821572b0bd28d993e6` | 4,193 | audit lane report |
| MINVER | `sessions/public-tail-20260929/lanes/cmax-audit/repo/cmax/scripts/1-audit/minimum-versions.json` | `4a71c6933b982957a6a2ed99a020744dcef699d52bf6805a7ff5c231c4b4ede4` | 33,051 | minimum-versions.json (copied HEAD 97865af) |
| MINVER_UP | `sessions/public-tail-20260929/lanes/cmax-audit/raw/upstream-minimum-versions.json` | `9af5750dd7bc420e6e80efb6b05a34bd0065808efc033955b2e6f60da7108119` | 66,104 | upstream minimum table, generated 2026-09-25 (UTF-16) |
| MLP_COV | `sessions/public-tail-20260929/lanes/mlperf/summary/coverage.md` | `3e1f3f15def68541539b7cc388ce6be722a98325aea467f762c9c75c3c2ce7e2` | 40,588 | MLPerf derived per-accelerator table |
| MLP_REP | `sessions/public-tail-20260929/lanes/mlperf/REPORT.md` | `d3242354771e025c199ce9896a9d41c79ad71ae8b03ebf88bbe30924f9142e4d` | 4,696 | MLPerf lane report |
| IX_REP | `sessions/public-tail-20260929/lanes/inferencex-history/REPORT.md` | `fee05e468f44577df2fa5374695115f7fa4da426033a9c909063b300be93418d` | 4,517 | InferenceX lane report |
| IX_ROWS | `sessions/public-tail-20260929/lanes/inferencex-history/rows/inferencex.jsonl` | `317626fea556ef9db55d3c9a298a6c0ca483139eea858fa8b7c222e16dcc32f4` | 1,269,005,412 | InferenceX rows (H100/MI300X groups recomputed) |
| GHI_COV | `sessions/public-tail-20260929/lanes/github-issues-deep/summary/coverage.md` | `c5c4f465605d194f1d485723a43cc5c427c60517853b8609d57636389f80efbe` | 10,054 | vLLM issue volume context |
| OCP_REP | `sessions/public-tail-20260929/lanes/opencomputeprices/REPORT.md` | `c88b2afbbb5c3bc1a6e77fba12012ac93f2c62ee173c5069f55db94436786ff8` | 3,312 | OpenComputePrices lane report |
| R2 | `main/clustermax-challenge/retrospective/results/R2-result.md` | `e3c257f437fc73d2f99e90b8fc7b85192107f835d02834a03e2f9f23f583569c` | 40,818 | incident counts |
| R2PLAN | `main/clustermax-challenge/retrospective/PLAN-R2.md` | `a8c93b65041ca8144a21cf4890d2f2724b58a9d91df260e364ec2d3ffc163bdd` | 7,996 | window, eligibility, limits |
| INC | `main/clustermax-challenge/retrospective/incidents/` | (directory) | | incident JSON files (directory) |
| INCSCHEMA | `main/clustermax-challenge/retrospective/incidents/SCHEMA.md` | `b0e5eecc9e84df4dd955716e7611a4d736367f74eaa255004a6a0fdbaf1d00df` | 4,114 | incident schema |
| COLLECT | `main/clustermax-challenge/scripts/collect_status.py` | `fa821dc8894a74d28ac09a3e3d2f0d834e7a98d9df04efccd3f9691fa2ffccec` | 49,196 | status collection script |
| RUN_R2 | `main/clustermax-challenge/retrospective/run_r2.py` | `5520aee90e2d675abf73c654aa5d78d2ab757f109cb8bcfd238031d5c8e182bd` | 19,603 | R2 pipeline |
| EVAL_SH | `main/hot-aisle/campaign/shop-eval/evaluate.sh` | `e6f253ba40ce8c18facd412ed6ddc4e6235e91c2da57eec412286b98e0bd7eca` | 13,305 | kit entry point: fingerprint + pinned arm + score |
| ARM_SH | `main/hot-aisle/campaign/arm.sh` | `99d1bb6a073d308eafa77ed651568b31346cc98bc5d5ec86191d364de9a067f8` | 7,459 | pinned workload arm used by evaluate.sh (installs docker.io if absent) |
| ARM3_SH | `main/hot-aisle/campaign/run3/arm3.sh` | `7e891338b6334dfa543297c99b790962c490e29cc60e631837a5d21811b80683` | 333 | Run 3 arm (invocation.json, env.json, ledger-times.json) |
| FINGERPRINT | `main/hot-aisle/campaign/shop-eval/probe/fingerprint.sh` | `79f4796d7310b69e817dc84e02c5717a461bab10f201c6effbdca6898ab63bb1` | 27,838 | hardware/driver/PCIe/RAS fingerprint probe |
| DELTA | `main/hot-aisle/campaign/backfill/DELTA-2026-09-29.md` | `8bfe40352059929dffe9a805a4c618d876ae3a10b82ef637bd189c34b5923044` | 26,778 | InferenceX/MLPerf vs retained cells: 0 comparable (cited via report, not re-read) |

## SemiAnalysis pages: capture manifest

The expectations and criteria pages were read from `sessions/clustermax-cloudreview-20260929/raw/` and their sha256 match `capture-manifest.json` (retrieved 2026-09-29T18:29 to 18:31Z). The older copies under `sessions/clustermax-delta-20260923/criteria/live/` differ in raw bytes but extract to identical text (checked for all 16 pages read).

| url | file | sha256 (manifest) | sha256 (recomputed) | retrieved_utc |
|---|---|---|---|---|
| https://www.clustermax.ai/criteria/security | `sessions/clustermax-cloudreview-20260929/raw/criteria_security.html` | `a54ec4bc293d8082657c4846ecec22cc9546828d0bbc0f8835baf8c6396bf566` | `a54ec4bc293d8082657c4846ecec22cc9546828d0bbc0f8835baf8c6396bf566` (match) | 2026-09-29T18:30:57Z |
| https://www.clustermax.ai/criteria/lifecycle | `sessions/clustermax-cloudreview-20260929/raw/criteria_lifecycle.html` | `406757db1d0d3a7df1168980d219c705b600dcf29cfa76256708dd29a15c0bb2` | `406757db1d0d3a7df1168980d219c705b600dcf29cfa76256708dd29a15c0bb2` (match) | 2026-09-29T18:30:58Z |
| https://www.clustermax.ai/criteria/orchestration | `sessions/clustermax-cloudreview-20260929/raw/criteria_orchestration.html` | `786b7a7c47236c3ae2d0f50072c6e5b2588208bf408613a402dc5d279924a84c` | `786b7a7c47236c3ae2d0f50072c6e5b2588208bf408613a402dc5d279924a84c` (match) | 2026-09-29T18:30:59Z |
| https://www.clustermax.ai/criteria/storage | `sessions/clustermax-cloudreview-20260929/raw/criteria_storage.html` | `004d9955bdbdfa20fb46d83050b448cccb4d704707d0c58de9ea3c00e6f0cb92` | `004d9955bdbdfa20fb46d83050b448cccb4d704707d0c58de9ea3c00e6f0cb92` (match) | 2026-09-29T18:30:59Z |
| https://www.clustermax.ai/criteria/networking | `sessions/clustermax-cloudreview-20260929/raw/criteria_networking.html` | `0aff08d945e8d968829922dabccec698ef49eaf32d3f767f6d29f1d432e0c48d` | `0aff08d945e8d968829922dabccec698ef49eaf32d3f767f6d29f1d432e0c48d` (match) | 2026-09-29T18:31:00Z |
| https://www.clustermax.ai/criteria/reliability | `sessions/clustermax-cloudreview-20260929/raw/criteria_reliability.html` | `7cef18d9776c4d3c92881a89701a5cdc022e85cfb073dd21b5c2db5611c0f1a7` | `7cef18d9776c4d3c92881a89701a5cdc022e85cfb073dd21b5c2db5611c0f1a7` (match) | 2026-09-29T18:31:01Z |
| https://www.clustermax.ai/criteria/monitoring | `sessions/clustermax-cloudreview-20260929/raw/criteria_monitoring.html` | `4d03e7c9c13940b4e6bcce7c68df60fd3e836ca0b22683ee7bfe2ef109eceddc` | `4d03e7c9c13940b4e6bcce7c68df60fd3e836ca0b22683ee7bfe2ef109eceddc` (match) | 2026-09-29T18:31:02Z |
| https://www.clustermax.ai/criteria/pricing | `sessions/clustermax-cloudreview-20260929/raw/criteria_pricing.html` | `f319859a53b68b527325c8443fa07516aa1ca4e446e975bb111071f5579e6382` | `f319859a53b68b527325c8443fa07516aa1ca4e446e975bb111071f5579e6382` (match) | 2026-09-29T18:31:03Z |
| https://www.clustermax.ai/criteria/availability | `sessions/clustermax-cloudreview-20260929/raw/criteria_availability.html` | `58e04c5f7bd041b0eea5e6921ab73adb773900a5210d15fa8834786d54274c5d` | `58e04c5f7bd041b0eea5e6921ab73adb773900a5210d15fa8834786d54274c5d` (match) | 2026-09-29T18:31:05Z |
| https://www.clustermax.ai/expectations/slurm | `sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html` | `3942ce69c6d476549ff5a6780f3b4b4cacee8180fa5180c34cfa537d3a4ccf41` | `3942ce69c6d476549ff5a6780f3b4b4cacee8180fa5180c34cfa537d3a4ccf41` (match) | 2026-09-29T18:31:05Z |
| https://www.clustermax.ai/expectations/kubernetes | `sessions/clustermax-cloudreview-20260929/raw/expectations_kubernetes.html` | `ee6fc684d8d7eb994a58840b2b5c7fb4d0c4acb2ebdea6e944bb175e440e4e30` | `ee6fc684d8d7eb994a58840b2b5c7fb4d0c4acb2ebdea6e944bb175e440e4e30` (match) | 2026-09-29T18:31:06Z |
| https://www.clustermax.ai/expectations/standalone | `sessions/clustermax-cloudreview-20260929/raw/expectations_standalone.html` | `f94da567a4e2b48ae02b01f410677a12f03b8f1780be4532cc043dd03a46055c` | `f94da567a4e2b48ae02b01f410677a12f03b8f1780be4532cc043dd03a46055c` (match) | 2026-09-29T18:31:08Z |
| https://www.clustermax.ai/expectations/monitoring | `sessions/clustermax-cloudreview-20260929/raw/expectations_monitoring.html` | `b285009fc4a6743c07da26b41bd7ba03c8efa004ff4d43904d42e37c3d1c47f0` | `b285009fc4a6743c07da26b41bd7ba03c8efa004ff4d43904d42e37c3d1c47f0` (match) | 2026-09-29T18:31:09Z |
| https://www.clustermax.ai/expectations/health-checks | `sessions/clustermax-cloudreview-20260929/raw/expectations_health-checks.html` | `c1329c39850634fd962159ca6147fdd40892f908fb505a8182d9a2e9267a242e` | `c1329c39850634fd962159ca6147fdd40892f908fb505a8182d9a2e9267a242e` (match) | 2026-09-29T18:31:10Z |

## External vendor documents

URLs that appear as links on the SemiAnalysis expectations pages and are cited by name in the prescriptions. They were not fetched here; they are cited as the expectations page cites them.

- https://slurm.schedmd.com/topology.yaml.html
- https://slurm.schedmd.com/prolog_epilog.html
- https://slurm.schedmd.com/accounting.html
- https://docs.nvidia.com/cuda/gpudirect-rdma/
- https://developer.nvidia.com/networking/hpc-x
- https://github.com/NVIDIA/pyxis
- https://github.com/NVIDIA/enroot
- https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
- https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/dcgm-diagnostics.html
- https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/getting-started.html
- https://kubernetes.io/docs/concepts/storage/persistent-volumes/#access-modes
- https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- https://github.com/kubernetes/node-problem-detector
- https://github.com/NVIDIA/NVSentinel
- https://github.com/leptonai/gpud
- https://github.com/planetlabs/draino
- https://github.com/NVIDIA/dcgm-exporter
- https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack
- https://github.com/NVIDIA/nccl-tests
- https://www.kernel.org/doc/html/latest/admin-guide/perf-security.html
- https://nvidia.custhelp.com/app/answers/detail/a_id/5582 (CVE-2024-0132)
- https://rocm.docs.amd.com/projects/install-on-linux/en/latest/install/quick-start.html

## Read but used only for context, or not used

- `sessions/public-tail-20260929/lanes/github-issues-deep/summary/coverage.md`: used once (vLLM issue volume, P-06), heuristic regex counts of issues only.
- `main/hot-aisle/campaign/backfill/DELTA-2026-09-29.md`: hashed above, cited only through the InferenceX report and IMPORT-SUMMARY.md for "0 comparable observations"; not re-read.
- Wayback diffs, Together/CoreWeave narrative claims, business and financing claims: not used.
- Files in `sessions/clustermax-delta-20260923/` were used only to confirm the text of the SemiAnalysis pages matches the 2026-09-29 capture.