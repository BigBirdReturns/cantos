# Market context for the Run 3 economics (built 2026-09-29)

Source: OpenComputePrices, release `latest-data` (updated 2026-07-29), `rows/prices.jsonl`, 1,689,060 rows, sha256 `390b25b1b25d59631166dae6273ba7b04c4a8645191002eafafe865afaa73bd0` (lane `sessions/public-tail-20260929/lanes/opencomputeprices/`). Imported, third-party listings (aggregator feeds such as getdeploying, shadeform, skypilot), not provider quotes and not measured by us. The series ends 2026-07-29, so it does not cover Run 3 (2026-09-24) or DigitalOcean's 2026-08-01 price change.

Method: on-demand `hourly_price_usd` (per GPU-hour). Per provider, the median of its rows in the month; then the median across providers. Row-weighted medians are not used (marketplaces with many shapes dominate). Reproduced with `build_price_history.py`; per-provider numbers are in `market-stats.json`.

## Per-provider median on-demand $/GPU-hr, July 2026 vs April 2026

| GPU | Jul 2026 | providers | Apr 2026 | providers | Apr to Jul |
|---|---|---|---|---|---|
| MI300X | $3.04 | 7 | $2.72 | 6 | +11.8% |
| H100 | $2.99 | 42 | $2.59 | 41 | +15.4% |
| H200 | $4.29 | 33 | $3.49 | 36 | +22.9% |
| B200 | $6.49 | 23 | $5.20 | 18 | +24.9% |

The provider set changed between the two months. For MI300X the same six providers give $2.72 (April) to $2.82 (July), +3.7%; the rest of the +11.8% is Cyfuture AI joining in June at $3.04. RunPod's MI300X median moved $1.99 to $2.19. Hot Aisle, DigitalOcean, Crusoe, Oracle and Azure did not move in the monthly median.

## Where Hot Aisle sits in the MI300X distribution

July 2026 provider medians, other providers only (n = 6): DigitalOcean $1.99, RunPod $2.19, Cyfuture AI $3.04, Crusoe $3.45, Oracle $6.00, Azure $7.86.

| Hot Aisle price | providers at or below it | percentile (n = 6 others) | with Hot Aisle's own July median included (n = 7) |
|---|---|---|---|
| $2.99 VM (1, 2, 4 GPU) | 2 of 6 | 33rd | 3 of 7, 43rd |
| $3.39 bare metal (8 GPU) | 3 of 6 | 50th | 4 of 7, 57th |

On the last snapshot day (2026-07-29) the set is the same with RunPod at $2.39 and the ranks are unchanged (2 of 6 and 3 of 6). The $3.39 is a per-GPU figure for the 8-GPU node (a one-month minimum per `data/prices.json`); the series lists it as `reserved`, and the comparison here is to on-demand medians, so it is the less like-for-like of the two.

The series itself has Hot Aisle's 1x/2x/4x VM at $1.99 from 2026-03-22 to 2026-07-26 and at $2.99 from 2026-07-27 or 2026-07-28 (both values appear on 07-27). Hot Aisle's July monthly median is therefore $1.99, and the $2.99 figure above is the price as of the end of the series and as used in Run 3. The 8x on-demand listing at $1.99 disappears on 2026-05-21; the 8x $3.39 reserved listing runs 2026-05 to 2026-07.

## Run 3 economics by date

`RUN3-ECONOMICS-BY-DATE.jsonl` recomputes the retained Run 3 arms at each dated public price with no GPU rerun (`economics_by_date.cjs`, calling the page engine's `costing` on the retained, engine-accepted counts: Hot Aisle A/T0 4,336 accepted, DigitalOcean N/T0 4,280 accepted). Intervals are those behind the published $0.74 and $1.20: 64.68 min for A/T0 (seat request to SSH plus arm window) and 69.82 min for N/T0 (request to release). No billing minimum binds; Hot Aisle's arm was paid from credit and is costed at list.

| Hot Aisle 1x MI300X | DigitalOcean 1x H100 (public series) | Hot Aisle $/1k accepted | DigitalOcean $/1k accepted |
|---|---|---|---|
| $1.99 (2026-03-22 to 2026-07-26) | $3.39 | $0.49 | $0.92 |
| $2.99 (2026-07-27 to 2026-07-29) | $3.39 | $0.74 | $0.92 |
| $2.99 as run (2026-09-24) | $4.41 as run | $0.74 | $1.20 |

At the listed public prices Hot Aisle is 46% cheaper per accepted request at $1.99 and 19% cheaper at $2.99. The as-run comparison (38% cheaper) used DigitalOcean's $4.41, which is not in this series; the series carries $3.39 for the DigitalOcean H100 to its last day.

## Limits

- Public series: one snapshot source per row; different aggregators disagree for the same provider (DigitalOcean H100 x1: getdeploying $3.39 and skypilot $6.74 on every Hot Aisle snapshot day; shadeform lists $3.34 on other days). The comparator price uses the source priority getdeploying, shadeform, skypilot and every value is retained in the by-date rows.
- Days the series lacks have no file in `data/price-history/`; nothing is interpolated. TensorWave and DataCrunch are not in the series; Verda is the DataCrunch successor and is present.
- MI355X has one provider and MI300X seven, so the MI300X percentile rests on six comparators.
