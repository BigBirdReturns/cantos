# Shop diagnosis rubric

Evaluates any GPU compute shop against Hot Aisle as the reference operator. Nine layers,
each fed by one or more of the three canonical inputs:

- **counter** — `../counter/records/<shop>.json`, schema `second-run/counter-record@1`, produced
  by `../counter/counter_record.py score`. Shape agreed here (counter lane not yet built):
  `{schema, shop, generated_at, score: 0-100, billing_granularity, dimensions: {pricing, proof,
  hygiene, availability, stack, hardware} -> {score: 0-100, weight, notes, ...flags}}`.
  `dimensions.proof` additionally carries the booleans `has_manifest_hash`, `has_disclosure`,
  `has_pinned_commit`, `publishes_whole_window_cost`.
- **fingerprint** — `<outdir>/fingerprint.json`, schema `second-run/shop-fingerprint@1`. Shape
  agreed here (fingerprint lane not yet built): kernel, virtualization, acs_enabled,
  hugepages_enabled, iommu, cpu{numa_nodes,...}, ram, storage, network, container_runtime
  {cpu_pinning, numa_pinning}, provisioning{requested_at, ssh_ready_at, seconds_to_ssh,
  listed_available, provisioned}, gpus[]{model, vbios, firmware, firmware_age_days,
  driver_or_rocm_version, pcie_gen, pcie_gen_max, pcie_width, pcie_width_max, topology,
  ecc_enabled, ras_errors_correctable, ras_errors_uncorrectable, idle_temp_c, idle_clock_mhz,
  idle_power_w, sustained_60s{clock_mhz_start, clock_mhz_end, temp_c_start, temp_c_end,
  power_w_start, power_w_end, throttled}}.
- **bench** — the existing workload engine. Either the JSON table `engine_table.cjs` prints
  (`{dir, rate, gates, engine, cells:[{cell, runs, completed, attempted, accepted,
  accepted_pct, accepted_per_s, holds, cost_per_1k}]}`), or a directory of raw
  `cell-<name>-r<n>.json` files in the vLLM-bench shape used under
  `results/hotaisle-mi300x/` (per-cell `backend`, `completed`, `failed`,
  `p50/p95/p99_ttft_ms`, `p50/p95/p99_tpot_ms`, `std_itl_ms`, `request_throughput`,
  `total_token_throughput`, ...). `diagnose.py` accepts either.

Hot Aisle reference numbers below are cited from the repo (see `reference/hotaisle-2026-09.json`
for the full bundle with per-field sources): Run 3 A/T0 — $0.72/1k accepted (own window),
$0.90/1k whole seat, TTFT p50/p95/p99 53/155/571 ms, 50.3% accepted; Run 1 best cell c64 —
$0.072/1k at 100% accepted under TTFT p95 <= 1000 ms; DO H100 whole run — $1.20/1k.

Each rule below has a stable **rule id** used by `diagnose.py` and `REPORT.md`.

---

## 1. Counter (external trust/reputation score)

Feeds from: **counter** (`score`, `dimensions.*`).

- **CNT-01 — overall score.**
  WRONG: `score < 70`. Symptom: shop is likely to fail one or more of the harder layers below
  (hardware lifecycle, known-good stack) since the counter score aggregates them.
  RIGHT: `score >= 70`.
  COULD DO BETTER: fix the single lowest-scoring dimension first (see CNT-02), then re-run
  `counter_record.py score` and confirm the overall score moved. Expected effect: overall
  counter score rises; indirectly, whichever bench metric that dimension covers improves.

- **CNT-02 — dimension imbalance.**
  WRONG: `(average dimension score) - (minimum dimension score) > 30`, i.e. one blind spot is
  dragging an otherwise-fine shop down.
  RIGHT: spread <= 30 points.
  COULD DO BETTER: put engineering effort into the lagging dimension specifically rather than
  broad polish; re-score and confirm the spread narrowed. Expected effect: overall counter
  score rises faster per unit effort than an across-the-board pass.

## 2. Site / power (inferred from the fingerprint's sustained-load sample)

Feeds from: **fingerprint** (`gpus[].sustained_60s`, `idle_*`).

- **PWR-01 — thermal/power throttle under sustained load.**
  WRONG: any GPU's `sustained_60s.throttled == true`, or its clock drops more than 15% from
  `clock_mhz_start` to `clock_mhz_end` over the 60 s sample. Symptom in bench: TTFT p99 and
  `accepted_pct` degrade specifically on the higher-concurrency cells (throughput starts
  fine, then decays as the sample runs long enough to heat-soak) — the failure mode that
  produced Hot Aisle's own 155/571 ms p95/p99 gap under burst load, but worse and sustained
  rather than momentary.
  RIGHT: sustained clocks hold within ~5% of the idle/boost clock across the 60 s sample,
  power draw stable, `throttled == false` (Hot Aisle-grade).
  COULD DO BETTER: fix airflow/PSU headroom or raise the BIOS power/thermal limit; re-run the
  60 s sustained sample and confirm clocks stay flat. Expected effect: bench TTFT p99 and
  accepted_pct at high concurrency both improve; $/1k accepted falls because fewer requests
  blow the latency gate.

## 3. Hardware lifecycle

Feeds from: **fingerprint** (`gpus[].pcie_*`, `firmware_age_days`, `ras_errors_*`).

- **HW-01 — degraded PCIe link.**
  WRONG: `pcie_gen < pcie_gen_max` or `pcie_width < pcie_width_max` for any GPU (classic
  case: a gen5 card negotiated at gen4 x8 because of a bad riser, wrong slot, or stale
  motherboard BIOS). Symptom: `total_token_throughput`/`output_throughput` hits a hard
  ceiling regardless of concurrency, and `accepted_per_s` plateaus far below what the GPU's
  compute would otherwise support.
  RIGHT: every GPU negotiated at its full rated generation and width.
  COULD DO BETTER: reseat the card, update the host BIOS, check slot bifurcation; re-read
  `pcie_gen`/`pcie_width` from a fresh fingerprint and re-run the plateaued bench cell.
  Expected effect: throughput ceiling and accepted_per_s rise at the same concurrency.

- **HW-02 — stale firmware/VBIOS.**
  WRONG: `firmware_age_days > 270` (about 9 months un-refreshed against vendor releases) or
  the field is absent/unknown (shop cannot report its own firmware state = opacity). Symptom:
  intermittent tail-latency spikes or ECC events with no other explanation.
  RIGHT: `firmware_age_days <= 180`, reported explicitly.
  COULD DO BETTER: update to the vendor-qualified VBIOS/firmware matching the driver/ROCm
  branch in use; re-read the fingerprint and soak-test. Expected effect: RAS error counters
  and TTFT p99 drop; firmware age resets to near zero.

- **HW-03 — rising/uncorrected RAS errors.**
  WRONG: `ras_errors_uncorrectable > 0` for any GPU, or `ras_errors_correctable > 100`.
  Symptom: sporadic `failed` requests in bench cells that should otherwise be clean (compare
  Hot Aisle A/T0: 8,622/0 failed).
  RIGHT: zero uncorrectable errors, correctable count low/flat between samples.
  COULD DO BETTER: RMA or reseat the card; re-sample RAS counters over a repeat 60 s window
  and confirm flat. Expected effect: bench `failed` count converges to 0; accepted_pct rises
  because fewer runs are lost to hardware faults rather than latency gates.

## 4. Known-good stack

Feeds from: **fingerprint** (`gpus[].driver_or_rocm_version`, `observed_backend.*`) vs
**reference** (`stack.driver_or_rocm_version` = `7.2.4`).

- **STK-01 — driver/ROCm/CUDA behind the qualified version.**
  WRONG: `driver_or_rocm_version != reference.stack.driver_or_rocm_version` (e.g. ROCm 6.x
  where the qualified reference is 7.2.4). Symptom: the MoE/attention kernel falls back to a
  generic, untuned code path, so `output_throughput` at a given concurrency sits well below
  what the same silicon does on the qualified stack.
  RIGHT: pinned to the qualified version (or a newer version on the same qualified branch,
  recorded the way `env.json`/`env.normalized.json` record it here).
  COULD DO BETTER: upgrade to the qualified ROCm/CUDA + matching serving-image digest; re-read
  the fingerprint driver version and re-run the same bench cell. Expected effect:
  output_throughput/accepted_per_s rise, `cost_per_1k` falls.

- **STK-02 — opaque backend selection.**
  WRONG: fingerprint's `observed_backend.attention_backend` is missing, null, or `"unknown"` —
  the shop gives the tenant no way to see which attention/MoE kernel actually served a
  request (this must come from the fingerprint's own snapshot of the serving process/logs;
  the bench cell JSON's `backend` field is the *benchmark client's* transport, e.g.
  `"openai"`, and is not evidence either way).
  Symptom: unexplained throughput/latency swings between otherwise-identical runs with no way
  to root-cause them, mirroring what Run 3 had to reconstruct by hand from `serve.log`
  (`ROCM_ATTN` vs `ROCM_AITER_FA`).
  RIGHT: backend/runtime identity is recorded per run (own `env.json`-equivalent), the way
  Hot Aisle's `env.json`/`env.normalized.json` capture it, surfaced in the fingerprint as
  `observed_backend.attention_backend` / `.moe_kernel`.
  COULD DO BETTER: have the shop expose backend/runtime in a per-session capture; diff it
  across runs. Expected effect: reproducible TTFT tail; regressions become attributable
  instead of mysterious.

## 5. Fleet automation (inferred from provisioning behavior)

Feeds from: **fingerprint** (`provisioning.seconds_to_ssh`) vs **reference**
(`provisioning.seconds_to_ssh` = 122 s).

- **FLEET-01 — slow/manual provisioning.**
  WRONG: `seconds_to_ssh > 300` (5 minutes from request to SSH-ready; Hot Aisle's own seat
  took 122 s). Symptom: the gap between an arm's own-window `$/1k` and its whole-seat `$/1k`
  widens, because idle/setup time is billed but produces no accepted work — the same effect
  that separates Hot Aisle's own $0.72 (own window) from $0.90 (whole seat).
  RIGHT: `seconds_to_ssh` in the same range as the reference (roughly under 3 minutes).
  COULD DO BETTER: pre-warm golden images / automate the fleet provisioner instead of manual
  console steps; re-time request-to-SSH-ready on a fresh seat. Expected effect: whole-window
  `$/1k accepted` moves toward the own-window figure.

## 6. Health and availability

Feeds from: **bench** (`failed`/`attempted-completed`), **fingerprint**
(`idle_power_w` vs `sustained_60s.power_w_start`, `provisioning.listed_available`/`provisioned`).

- **HEALTH-01 — nonzero failures with no hardware cause identified.**
  WRONG: summed `failed` (raw cells) or `attempted - completed` (engine table) `> 0` across
  bench cells. Symptom: `accepted_pct` depressed independent of the latency gate.
  RIGHT: `failed == 0` (Hot Aisle A/T0: 8,622/0).
  COULD DO BETTER: pull serve logs for the failing cell, fix the OOM/timeout/config cause,
  re-run. Expected effect: `completed/attempted` and `accepted_pct` converge upward.

- **HEALTH-02 — GPU wasn't actually idle when "idle" was sampled.**
  WRONG: `sustained_60s.power_w_start > 1.5 * idle_power_w`, i.e. the load sample started from
  a GPU already drawing well above its own quoted idle baseline — a signal of a noisy
  neighbor or an oversold/shared card. Symptom: elevated TTFT variance even at low
  concurrency (c1-class cells), where a truly idle-start GPU should be closest to its best
  case.
  RIGHT: sample starts within ~1.5x of the GPU's own idle baseline.
  COULD DO BETTER: get the shop to confirm exclusive single-tenant allocation; re-sample idle
  power after confirming nothing else is scheduled. Expected effect: `std_ttft_ms` on
  low-concurrency cells shrinks.

- **PRICE-03 — capacity listed as available but not actually provisionable.** (kept here since
  it is an availability check, numbered in the pricing/capacity id space to match
  `diagnose.py`)
  WRONG: `provisioning.listed_available == true` and `provisioning.provisioned == false` —
  the dashboard said a seat existed and the attempt to take it failed (compare Run 3:
  DigitalOcean MI300X/H200 listed `regions=[]` all night while marketed as orderable).
  Symptom: bench simply has no data for that shop/SKU — you cannot get to a bench at all.
  RIGHT: listed availability and actual provisioning success agree.
  COULD DO BETTER: shop should reconcile its capacity dashboard against real inventory in
  real time; re-check the listing after the fix and confirm a provisioning attempt succeeds.
  Expected effect: uptime/availability rate on provisioning attempts rises; this is the
  precondition for every other bench number existing at all.

## 7. Tenant hygiene and isolation

Feeds from: **fingerprint** (`virtualization`, `acs_enabled`, `hugepages_enabled`,
`container_runtime.numa_pinning`, `cpu.numa_nodes`).

- **TEN-01 — VM without ACS override or hugepages.**
  WRONG: `virtualization == "vm"` and (`acs_enabled == false` or `hugepages_enabled ==
  false`). Symptom: elevated inter-token jitter (`std_itl_ms`, `std_tpot_ms`) from PCIe
  peer-to-peer interference or memory fragmentation that bare metal or a properly configured
  VM wouldn't show.
  RIGHT: bare metal, or a VM with the ACS override patch and reserved hugepages both on
  (Hot Aisle's own seat is a VM — `enc1-gpuvm004` — so "VM" alone is not the failure; missing
  ACS/hugepages under virtualization is).
  COULD DO BETTER: enable the ACS override patch and reserve hugepages at boot; re-read the
  fingerprint flags. Expected effect: `std_itl_ms`/`std_tpot_ms` drop.

- **TEN-02 — no CPU/NUMA pinning on a multi-socket host.**
  WRONG: `cpu.numa_nodes > 1` and `container_runtime.numa_pinning == false`. Symptom:
  cross-NUMA memory access inflates the TPOT/TTFT tail specifically (not the median).
  RIGHT: serving process pinned to the NUMA node local to its GPU, or single-NUMA host.
  COULD DO BETTER: pin the serving process/container to the local NUMA node and enable cgroup
  limits; re-read `container_runtime.numa_pinning`. Expected effect: p95/p99 TTFT and TPOT
  tail tighten.

## 8. Pricing and capacity

Feeds from: **counter** (`billing_granularity`), **bench** (`cost_per_1k`) vs **reference**
(`run3_a_t0.cost_per_1k_accepted_own_window_usd` = 0.72).

- **PRICE-01 — no sub-hour billing.**
  WRONG: `billing_granularity in {"per-hour", "unknown"}`. Symptom: whole-window `$/1k`
  inflated relative to own-window `$/1k` because any partial hour is rounded up and billed in
  full (Hot Aisle bills per minute; DigitalOcean bills per second with a 5-minute minimum —
  both are finer than per-hour).
  RIGHT: `billing_granularity` is per-minute, per-second, or per-second-with-short-minimum.
  COULD DO BETTER: negotiate or enable sub-hour billing; check invoice line-item granularity
  after the change. Expected effect: whole-window `$/1k accepted` moves toward own-window
  `$/1k accepted`.

- **PRICE-02 — worse `$/1k accepted` than the reference at comparable acceptance.**
  WRONG: the shop's best-qualifying bench cell's `cost_per_1k` exceeds
  `reference.run3_a_t0.cost_per_1k_accepted_own_window_usd` (0.72) by more than 5%, at a
  comparable accepted_pct.
  RIGHT: at or under the reference figure.
  COULD DO BETTER: the highest-leverage single number in this whole report — attack it via
  the other WRONG findings ranked above it (rate, STK-01/STK-02 tuning, FLEET-01
  provisioning waste), not by re-negotiating price alone; re-run `engine_table.cjs` after each
  fix. Expected effect: `cost_per_1k` falls directly and proportionally.

## 9. Public proof

Feeds from: **counter** (`dimensions.proof.has_manifest_hash`, `.has_disclosure`,
`.has_pinned_commit`, `.publishes_whole_window_cost`).

- **PROOF-01 — no reproducible/public benchmark trail.**
  WRONG: any of `has_manifest_hash`, `has_disclosure`, `has_pinned_commit` is false. Symptom:
  none in the bench itself — this is a trust-layer gap, not a latency/throughput one; it shows
  up as depressed conversion/counter score, not as a bench number.
  RIGHT: all three true — a per-result SHA-256 manifest (as in
  `results/hotaisle-mi300x/MANIFEST.sha256`), a published disclosure of funding/relationship
  and methodology caveats (as in `DISCLOSURES.md`), and a pinned commit/build identity for the
  numbers being published.
  COULD DO BETTER: publish a manifest + disclosure page alongside every result set; re-check
  the counter proof dimension. Expected effect: counter proof-dimension score rises; does not
  move bench throughput/latency/$-per-1k, and the report says so explicitly.

- **PROOF-02 — cost claims that hide idle/setup time.**
  WRONG: `dimensions.proof.publishes_whole_window_cost == false`, i.e. the shop only ever
  publishes a best-case cell number (like Hot Aisle's own $0.072/1k at c64) without also
  publishing the whole-window equivalent that includes provisioning/idle overhead (like Hot
  Aisle's own $0.72 own-window vs $0.90 whole-seat pair).
  RIGHT: both figures published side by side, labelled.
  COULD DO BETTER: publish both the best-qualifying-cell number and the whole-window number
  every time either is quoted. Expected effect: no bench number moves; this is a disclosure
  fix, and the report says so.

---

## Ranking used for "first three things to change"

`diagnose.py` assigns each rule id a fixed impact weight (higher = more leverage on
`$/1k accepted`, throughput, or uptime) and reports the top three WRONG findings by that
weight: PRICE-02 (100) > STK-01 (90) > HW-01 (85) > PWR-01 (80) > HEALTH-01 (75) >
FLEET-01 (70) > STK-02 (65) > HW-03 (60) > TEN-01 (55) > PRICE-01 (50) > HW-02 (45) >
PRICE-03 (40) > TEN-02 (35) > HEALTH-02 (30) > CNT-01 (25) > CNT-02 (20) > PROOF-01 (15) >
PROOF-02 (10).
