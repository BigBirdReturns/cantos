# Shortlist · first ten shops to evaluate

Source: `../providers/providers.jsonl` and `../providers/TARGETS.md`, staged 2026-09-24 (list
prices as published that day, not yet human-approved into `compute/data/catalog.json`).

## The rule

A shop makes this list only if, as published:

1. **Self-serve** — no sales call required to reach the SKU under test.
2. **1-GPU seat rentable** — a single accelerator can be rented on its own, not only in an 8-GPU
   block.
3. **Price or silicon** — list price at or below the tie line (**$2.72/GPU-h for H100**, the rate
   that ties Hot Aisle's $0.74/1k on Run 3's workload; **$2.99/GPU-h for MI300X**, Hot Aisle's own
   rate) **or** the same silicon as Hot Aisle (MI300X), at any price, because a same-silicon shop
   answers a different question (operator quality, not hardware economics).
4. **Not a hyperscaler** — no AWS, Azure, GCP, Oracle.
5. **Not a pure marketplace of third-party hosts** — excludes Lium, Spheron, TensorDock, RunPod,
   Vast.ai, io.net, Akash, Shadeform. Those resell inventory from hosts this kit cannot identify or
   hold accountable; a bad result there names the marketplace, not the operator responsible for it.

This leaves two kinds of comparator: a **cheap H100** (tests whether price alone beats Hot Aisle)
and a **second MI300X shop** (tests whether Hot Aisle's number is the silicon or the shop —
`TARGETS.md`'s own next-run recommendation).

**Cost model, both tiers.** Every shop's own run (fingerprint + `arm.sh serve` + `arm.sh bench` +
collect) takes about 2.5 hours wall clock, the whole-seat figure Run 3 actually measured for one
arm on Hot Aisle (2.73 h, request to delete). Shops billing per minute or per second are charged
for that 2.5 h. Shops with a 1-hour minimum, billed hourly, are charged for 3 h (2.5 h rounded up).
This does **not** include the counter evaluation's own small provisioning spend (up to $3, see
`MANUAL.md`), which is separate and roughly the same for every shop.

## Tier 1 · evaluate first

| # | shop | GPU | $/GPU-h | min. billing | kind | full-eval cost | what it answers | biggest risk |
|---|---|---|---|---|---|---|---|---|
| 1 | AMD Developer Cloud (on DigitalOcean) | MI300X | 1.99 | unknown | VM | ~$5.00 | Same silicon as Hot Aisle: is Hot Aisle's number the silicon or the shop? | Price and availability came from one JS-rendered page the lane could not re-fetch; minimum billing and true self-serve depth are unverified. |
| 2 | Latitude.sh (g3.h100.small) | H100 | 1.68 | 1 hour | bare metal | ~$5.05 | Cheapest self-serve H100 under the tie line: does price alone beat Hot Aisle here? | Different silicon (NVIDIA), so a win here argues price/operator, not hardware; 1-hour billing rounds a short run up. |
| 3 | Voltage Park | H100 | 1.99 | 1 hour | VM | ~$6.00 | Self-serve H100 at list, Ethernet-fabric cluster. | Ethernet (not InfiniBand) fabric can hurt the tail at concurrency 64, which would confound a price story with a network story. |
| 4 | Verda (DataCrunch), spot | H100 | 1.73 | 1 hour | VM | ~$5.20 | Cheapest H100 found anywhere in the pool. | Spot: the instance can be preempted mid-bench, losing the money already spent and forcing a retry. |
| 5 | Crusoe (Cloud) | MI300X | 3.45 | 1 minute | VM | ~$8.65 | Third-cheapest same-silicon shop; priced *above* Hot Aisle, so it only wins by beating Hot Aisle on quality, not price. | Costs more than the reference operator itself; qualifies only under the same-silicon rule, not the price rule. |

**Total to evaluate all five: about $30** (fingerprint + bench runs only; add the small,
roughly-equal counter-evaluation spend per shop from `MANUAL.md`, and each provider's own real
invoice once it posts, which is very likely to be lower — these are worst-case, minimum-billing
estimates).

## Tier 2 · evaluate next

| # | shop | GPU | $/GPU-h | min. billing | kind | full-eval cost | what it answers | biggest risk |
|---|---|---|---|---|---|---|---|---|
| 6 | Vultr | MI300X | 3.99 | unknown | VM | ~$10.00 | A third same-silicon operator, to see whether tiers 1's same-silicon results (AMD Dev Cloud, Crusoe) are shop-specific or silicon-specific. | Minimum billing unit and true single-GPU rentability are unconfirmed beyond the price list. |
| 7 | Massed Compute | H100 | 2.73 | unknown | VM | ~$6.85 | Misses the H100 tie line by one cent; included as the next-cheapest self-serve H100 if 1–5 are unavailable. | A one-cent miss on the tie line is a judgment call, not a clean pass; minimum billing unverified. |
| 8 | DigitalOcean | MI300X | 2.59 | 5 min (page) / 60 s (docs) | VM | ~$6.50 (or $0 if it cannot be rented) | Second-cheapest same-silicon offer; also the shop `arm.sh`/`collect.sh` were originally built against. | `self_serve: quota` and observed `out_of_stock` in every region as of 2026-09-24 — this seat may simply not be rentable this month. |
| 9 | TensorWave | MI300X | 1.71 ("starting at") | unknown | VM/metal, unconfirmed | ~$4.30 (if reachable at all) | Cheapest MI300X price found anywhere, if it is real. | `self_serve: sales` — a sales conversation is required, which breaks the "any operator, no phone call" promise this kit is built on. |
| 10 | Lambda | H100 | 3.99 | 1 hour | VM | ~$12.00 | Well-known, well-documented neocloud baseline: what does a reputable-but-not-cheap H100 shop look like? | 47% above the H100 tie line; earns its place on documentation/reputation, not on price — least likely of the ten to be worth the money on cost alone. |

## Notes for whoever runs this next

- Re-check each shop's price and availability the day of the run — this list is a snapshot from
  `providers.jsonl` (2026-09-24) and prices, quotas, and stock move. `SHORTLIST.md` is a starting
  order, not a guarantee any given shop is rentable today.
- "Same-silicon" shops (rows 1, 5, 6, 8, 9) qualify at any price under rule 3; don't read their
  higher-than-Hot-Aisle rate as a disqualifier — the question they answer is quality, not price.
- If a tier-1 shop turns out unreachable (quota, out of stock, sales gate discovered on contact),
  pull the next tier-2 row in order rather than picking a new shop ad hoc, so the shortlist itself
  stays the record of what was tried and why.
