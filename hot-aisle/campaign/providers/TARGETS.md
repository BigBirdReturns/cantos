# Targets · what the provider compile says to measure next (2026-09-24)

Source: `PROVIDERS.md` / `providers.jsonl` (135 staged offers, 27 providers, 104 with a published
price), gathered 2026-09-24 by four lanes plus two live API/TUI observations. Prices are list,
per GPU-hour, as published that day. Targets are modeled from Run 3 and are not measurements.

## The tie line

Run 3 whole-run: Hot Aisle MI300X $2.99/h → $0.74 per 1k accepted; DigitalOcean H100 $4.41/h → $1.20.
Both seats did the same accepted work (4,336 vs 4,280), so cost scales with the hourly rate:

| seat | rate that ties Hot Aisle at $0.74 |
|---|---|
| 1x H100 doing N/T0's work | **$2.72/h** |
| 1x MI300X doing A/T0's work | $2.99/h (Hot Aisle itself) |
| any 1x seat at rate r | must deliver r / 0.00074 accepted per hour (Hot Aisle delivered ~4,040) |

## Where the list price already crosses the line

Self-serve 1x H100 below $2.72, as published 2026-09-24:

| provider | $/GPU-h | kind | modeled $/1k | verified by |
|---|---|---|---|---|
| Latitude.sh g3.h100.small | 1.68 | on-demand metal | 0.46 | Fable re-fetched pricing page |
| Verda (DataCrunch) | 1.73 | spot | 0.47 | lane only |
| Voltage Park | 1.99 | on-demand, Ethernet | 0.54 | Fable re-fetched FAQ ("starting at $1.99") |
| Spheron | 2.21 | spot marketplace | 0.60 | lane only |
| TensorDock | 2.25 | marketplace | 0.61 | lane only |
| Lium | 1.11–2.24 | marketplace, variable | 0.30–0.61 | lane only, ranges |
| Massed Compute | 2.73 | on-demand | 0.74 | Fable re-fetched pricing page |

MI300X 1x below Hot Aisle's $2.99:

| provider | $/GPU-h | self-serve | verified by |
|---|---|---|---|
| AMD Developer Cloud (runs on DigitalOcean) | 1.99 | yes | lane only; devcloud.amd.com is JS-rendered, re-fetch failed |
| TensorWave | 1.71 "starting at" | sales | Fable re-fetched product page |
| DigitalOcean gpu-mi300x1-192gb | 2.59 | quota | live API; no capacity in any region 09-23/24 |

## What this means for the argument

The H100 does flip on price. At $1.68–1.99 self-serve list rates the modeled H100 cost per accepted
closure is 25–40 % below Hot Aisle, if those seats do N/T0's work. That "if" is the measurement:
cheap H100 seats are often PCIe or shared hosts, arrival-burst tails were the H100's weak point
in Run 3 (p99 TTFT 2,254 ms), and none of these providers has a ledgered run yet.

The AMD side has the same shape: AMD Developer Cloud at $1.99 would put MI300X at ~$0.49/1k if it
does A/T0's work, and it is DigitalOcean hardware, which was Run 3's H100 comparator.

## Runs this compile points at (each ~$3–6 at list, one hour)

1. **N on a sub-tie H100**: Latitude.sh $1.68 or Voltage Park $1.99, same freeze as Run 3.
   Question: does a cheap H100 deliver N/T0's 4,280 accepted with the same tail?
2. **A on AMD Developer Cloud MI300X $1.99**: the neutral-provider MI300X arm C that DigitalOcean's
   own SKU could not supply. Question: is Hot Aisle's number the silicon or the shop?
3. **Repeat A/T0 on Hot Aisle** when a 1x VM is listed (weekends, per their TUI). Turns one run into two.
4. **H200 at $2.27–3.62** (Verda spot, Massed Compute) as the first nvidia-next point: needs
   ≥3,100–4,900 accepted/h to tie, i.e. 0.8–1.2× MI300X's throughput on this workload.

## Rows to verify before anyone quotes them

- Vultr MI300X 1x $3.99 and MI325X 1x $4.62: lane hit 403 on vultr.com, priced from a secondary page.
- TensorWave MI355X $2.95: sourced from a TensorWave blog post, not a price list.
- AMD Developer Cloud $1.99: lane source is the JS app shell; confirm on the AMD page or by sign-in.
- Oracle and Azure 8x rows: lanes used the printed global PDF / calculator text; regional prices differ.
- All marketplace rows (Lium, Spheron, TensorDock, RunPod): displayed low end at retrieval time.
- Duplicates across lanes (Crusoe MI300X ×2, Oracle MI300X ×2, Hot Aisle) are kept in staging on purpose; dedup happens at catalog approval.

Not priced publicly: Vast.ai (dynamic), io.net, Akash, Shadeform (aggregator table empty), SF Compute
(login), Prime Intellect, FluidStack, Cudo, Hyperbolic, OVHcloud, Google Cloud (page timeouts),
AWS and Azure on-demand (calculators; AWS Capacity Blocks printed $5.19 H100 / $6.87 H200), IBM.
