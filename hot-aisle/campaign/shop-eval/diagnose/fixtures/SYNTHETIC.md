# Synthetic fixtures

Everything under `fixtures/` is fabricated for `test_diagnose.py`. None of it is a real
shop, a real run, or a real Hot Aisle result. Each file says so in a `_synthetic` /
`"synthetic-badshop-..."` field or value so it can never be mistaken for real evidence
if it leaks out of this directory.

- `counter-record.json` -- a `second-run/counter-record@1` record for a shop that fails
  CNT-01 (low overall score), CNT-02 (dimension imbalance), PRICE-01 (hourly-only
  billing), PROOF-01 (no manifest/disclosure/pinned commit) and PROOF-02 (no
  whole-window cost disclosure).
- `fingerprint.json` -- a `second-run/shop-fingerprint@1` record for the same shop,
  failing PWR-01 (throttles under sustained load), HW-01 (degraded PCIe link), HW-02
  (stale/unreported firmware), HW-03 (uncorrectable RAS errors), STK-01 (ROCm behind
  the qualified reference), STK-02 (no observed-backend visibility), FLEET-01 (15-minute
  provisioning), HEALTH-02 ("idle" sample started far above its own idle baseline),
  TEN-01 (VM without ACS/hugepages), TEN-02 (no NUMA pinning on a 2-node host), and
  PRICE-03 (listed available, did not actually provision).
- `bench-cells/table.json` -- an `engine_table.cjs`-shaped table for the same shop,
  failing HEALTH-01 (nonzero failed requests) and PRICE-02 (cost_per_1k far above the
  Hot Aisle reference at low accepted_pct). `diagnose.py` prefers `table.json` when a
  directory contains one.
- `bench-cells/cell-c8-r0.json`, `cell-c32-r0.json` -- small (3-request) but
  structurally real raw bench cell files, same shape as
  `../../results/hotaisle-mi300x/cell-*.json`, kept alongside `table.json` to show the
  real cell shape a shop's raw bench output takes.
- `bench-cells-rawonly/` -- the same two cell files with no `table.json`, so
  `diagnose.py`'s raw-cell aggregation path (no correctness/cost grading available,
  only completed/failed/TTFT percentiles) gets exercised directly.
