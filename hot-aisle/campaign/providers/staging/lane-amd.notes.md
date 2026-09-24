# AMD Instinct GPU Provider Pricing - Collection Notes

**Collection Date:** 2026-09-24  
**Total WebSearch Calls Used:** 5 of 12 allowed  
**Total WebFetch Calls Used:** 10  

## Provider Status Summary

### Priced Providers (with public rates)

**TensorWave** — MI300X $1.71/GPU-hr (on-demand), MI355X $2.95/GPU-hr; quote-driven; not self-serve

**Vultr** — MI300X $3.99/GPU-hr on-demand / $1.85/GPU-hr preemptible; MI325X $4.62/GPU-hr; MI355X preemptible ~$2.29/GPU-hr; website blocks WebFetch (403) but pricing available via search; self-serve

**Oracle Cloud** — MI300X (8-GPU) $6.00/GPU-hr bare metal; MI355X $8.60/GPU-hr; pricing inferred from aggregator blogs (site returns 403); quota/sales access model

**Microsoft Azure** — ND MI300X v5 $6.00/GPU-hr on-demand / $1.11/GPU-hr spot in eastus2 and westus3; pricing from search aggregation; self-serve

**Crusoe Cloud** — MI300X $3.45/GPU-hr on-demand, spot contact sales; MI355X $7.40/hr for self-serve endpoints (not per-GPU); self-serve pricing page accessible

**AMD Developer Cloud** (DigitalOcean-backed) — MI300X $1.99/GPU-hr (single or 8-GPU cluster); free tier: $100 credits + AMD AI Developer Program membership + 100k hours for Indian researchers/startups; self-serve via devcloud.amd.com

**Hot Aisle** — MI300X VMs $2.99/GPU-hr (new customers, $1.99 grandfathered) billed by minute; bare metal $3.39/GPU-hr with 1-month minimum; Michigan facility; self-serve in <60 seconds via terminal/CLI/API

### Unpaid/Sales-Only Providers

**RunPod** — No MI300X offering; only NVIDIA GPUs in pricing table; pricing page does not list AMD models

**Nscale** — Dropped AMD entirely; no current AMD GPU offerings

**Shadeform** — Aggregator platform (30+ GPU cloud support); website content is navigation only; actual pricing requires visiting instance directory pages; not accessible via WebFetch

### Data Access Issues

**Oracle Cloud** — Website returns HTTP 403 Forbidden; pricing inferred from third-party aggregator blogs (Spheron, GPU Finder, etc.)

**Vultr** — Website returns HTTP 403 Forbidden for direct access; pricing retrieved via web search results and aggregator blogs

**Nscale** — URL https://www.nscale.com/pricing returns 404; confirmed via search that provider dropped AMD

**AMD Developer Cloud** — Initial direct URL timed out; pricing confirmed via web search and official AMD blog/announcement pages

## Notes on Data Quality

- **TensorWave, Oracle, Vultr prices** sourced from third-party aggregators (Spheron blog) for oracle/vultr; TensorWave from own product page
- **Spot/Preemptible pricing** available for Azure (spot), Vultr (preemptible), Crusoe (contact sales)
- **Regional info** limited; most providers don't publish region list on pricing pages (common for AMD GPU scarcity)
- **Minimum billing** varies: Hot Aisle by-minute VMs vs. 1-month bare metal; others typically per-minute or hourly
- **Self-serve availability**: Hot Aisle claims <60s deployment; AMD Dev Cloud via web portal; TensorWave, Oracle, Crusoe vary (quote-driven vs. web-based)
- **Free tier**: Only AMD Developer Cloud ($100 credits + research exemptions)

## Aggregator Sources Consulted

1. Spheron Network blog (2026-09): AMD MI300X & MI355X Pricing benchmark
2. Thunder Compute blog (Sept 2026): Cheapest MI300X rentals
3. GPU Finder: MI300X cloud pricing 2026
4. GetDeploying: Provider comparison tables

All pricing current as of September 2026 per sources.
