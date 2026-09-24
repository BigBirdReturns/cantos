# Invariants · what the market is already saying about what we measure (2026-09-24)

Sources, all read today: X (live search in the operator's browser plus a Codex lane, 7 dated
posts retained), Reddit (Codex lane, 21 dated posts from 10 threads), Hacker News (Algolia API),
Hot Aisle's own blog, ClusterMAX 3.0's public page (published 2026-09-23), and two judges
(Fable and Astra) reading Run 3 and the provider compile. The raw ledgers live in the internal
research folder; this file keeps what survives across independent sources.

An invariant here is a claim that recurs across independent posters AND that our ledger can
test or must encode. "Suggested" means one source or one organisation.

## Established across independent sources

1. **The GPU-hour is not a unit.** The same H100 rents from $1.11 to $6.16 on the day we compiled
   (Lium low end to CoreWeave list; RAX Finance on X, Sep 22: "$1.99 to $5.99 for the same H100",
   881 reposts). The CFTC letter on the first H100/B200 rental futures (CME + Silicon Data, listing
   Oct 5) calls the underlying market "fragmented and opaque". Jim Liu (Mar 2026) corrects a
   reserved-vs-on-demand and 8-GPU-vs-1-GPU comparison. Our unit is the accepted closure, priced
   from capacity request to release. Encode: purchase basis, timestamp, minimum rentable unit,
   commitment, on every price.

2. **Availability is priced separately from compute.** Hot Aisle raised MI300X from $1.99 to
   $2.99 in July at 100 % utilisation with "a queue of customers waiting" and says customers
   "cannot get DigitalOcean capacity when they need it"; our API log shows DigitalOcean's $2.59
   MI300X with no capacity in any region for two days. @nodiligence (Aug 19): the market puts
   "very different prices on the compute itself and on the certainty of actually having that
   compute". Reddit r/RunPod (Dec 2025): no H100 all week in the region holding the user's
   volume. Encode: every allocation attempt, success or not, with wait time and substitute SKU;
   a listed price with no capacity is a price of infinity for that hour.

3. **A provider rating is screening evidence, not a seat guarantee.** ClusterMAX 3.0 scopes
   itself to "managed clusters", not "who can build the best powered shell", and its authors
   defend that scope. The buyer-side reaction is the same in two places: @flatkey101 (Sep 24),
   "useful as a public reference, still a bad substitute for your own bakeoff on code and cluster
   behavior"; Jim Liu (Sep 23) on Vast.ai's tier: "Some of these GPUs are literally hosted in
   people's basements." Both sides agree the rating does not tell one account what one GPU beside
   its data will deliver. Encode: rating edition, rated product, and whether the rated thing is
   the thing being rented.

4. **Cost per correct answer, not per token.** r/LLMDevs (Sep 2026) converges on cost per good
   completion with fixed prompts, deterministic structural checks and pass rate kept beside
   speed; Reddit's own summary: "report accepted count and fraction next to cost per accepted
   request so low coverage cannot hide behind the ratio". Run 3 already does this. Encode:
   parse verdict, correctness verdict and deadline verdict retained separately.

5. **Startup, storage and retries belong on the bill.** r/StableDiffusion and r/RunPod: ten-minute
   setups, storage billed while stopped, negative balances, hours lost waiting on support.
   Backblaze markets "the storage problem neoclouds don't talk about". Our ledger clocks
   request to release; it does not yet carry storage after release, egress, or failed starts.
   Encode: line items for disk, transfer, failed provisioning and credits, separate from GPU time.

6. **Performance is a property of the configuration, not the chip.** vLLM maintainers on
   Blackwell, an 8x MI300X operator on r/LocalLLaMA (cache state and prompt length flip the
   number), our own Run 2 vs Run 3 (forced AITER attention +46 % on 70B long context, worse
   tail on 30B short MoE). Encode: image digest, engine version, attention and MoE backend,
   cache state, arrival trace, concurrency, on every row. Run 3 already records these from serve.log.

## Suggested (one source or one organisation)

7. Cheap H100 seats differ in form factor and host: PCIe vs SXM vs NVL, shared hosts,
   marketplace hosts in "Vietnam, Taiwan, Nebraska, and Estonia". Nobody in the sample has
   measured whether that changes accepted work on a coding workload. This is the next run.
8. Index prices are not rentable prices. Mercatus AI's weekly index (Sep 21) shows MI300X $4.98
   above H100 $3.89; our compile shows self-serve MI300X at $1.99–3.99 and H100 at $1.68–3.99.
   Index composition, not silicon, explains the inversion. Encode: never cite an index without
   the basket.
9. Kernel changes need correctness checks, not just speed. One X account attributes accuracy
   loss to AMD kernels, undated. Run 3 grades every request, so this is already covered; keep it.
10. Interruptions cost lost work, not discounted runtime. One r/deeplearning report of 12 hours
    lost without checkpoints. For inference, count late and failed requests during an eviction.
11. Quota friction is account-class specific. Azure rejections and a 24-hour approval in the
    same thread; DigitalOcean gave us limit 1 within a day. Encode: account class and the
    quota timeline, not a yes/no.

## Corrections to our own documents

- The tie is $2.72/h for a 1x H100, not $2.99. RUN3-RESULTS.md said "below ~$2.99/h the
  ranking flips" while its own table shows $2.99 → $0.81, still above $0.74. Fixed today (Astra).
- A/T0's $0.74 is an own-seat-equivalent; the actual shared seat was $0.90/1k across three arms.
  Both numbers appear in the results; the summary should always print both.

## Fields the catalogue is missing (SCHEMA v2 candidates)

From both lanes and Astra, grouped by how a cheap lane could fill them from public pages:

| group | fields | source page |
|---|---|---|
| GPU identity | form_factor (PCIe/SXM/NVL/OAM), power_limit, interconnect | SKU spec page |
| Host | tenancy (dedicated/shared/VM/container/bare metal), vcpu, ram, cpu_sharing | instance docs |
| Purchase basis | quote_ts, commitment, minimum_gpus, prepay, price_valid_until | pricing page |
| Bill boundary | billing_quantum, minimum_charge, stopped_storage_rate, storage_after_release, egress_rate, failed_start_billed | billing FAQ |
| Access | account_class, quota_default, quota_wait_observed, kyc_required | onboarding docs |
| Interruption | spot_notice, eviction_policy, disk_survival | spot terms |
| Software freedom | custom_image, root, driver_choice, api_provision, api_delete | deploy docs |
| Support | channel, hours, first_response_commitment, credit_policy | support page |
| Rating provenance | rating_edition, rated_product, rated_scope_matches_offer | ClusterMAX page |

Per-run measurements (time_to_ready, model_download_time, observed eviction, support first
response) stay in the ledger, not the catalogue.

## What to ask the crowd (Astra's five, kept)

1. Invoice-backed effective H100 cost including startup, storage, egress and idle, with SKU, region, date.
2. Which PCIe or shared-host H100s show repeatable burst-tail regressions; share config and traces.
3. Over a month, how often did eviction or quota block a deployment, and how long to recover.
4. Which provider restrictions blocked custom vLLM images, driver changes or automated teardown.
5. On real coding workloads, what fraction of failures disappears after sanitisation while keeping deadlines.

## Fable's reading

The market has arrived at our unit from the other direction. Financial actors are trying to make
the GPU-hour a commodity (CME futures, RAX's "1 cT = 1 GPU-hour", Sail Research's $80M
buy-any-chip arbitrage) while every practitioner post says the GPU-hour does not carry the
information a buyer needs. That gap is the product. The instrument's job is to be the thing the
futures market cannot be: a receipt for delivered accepted work under a named configuration,
with availability and the bill boundary on it.

Two things the discourse does not contain and we can supply cheaply: a measured answer to
whether a $1.68 H100 does a $4.41 H100's work (nobody has posted one), and an availability log
with denominators (everyone complains, nobody counts). Run order stands as in TARGETS.md.
