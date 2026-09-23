# ClusterMAX medal table transcriptions — method and notes

Working directory: `retrospective/ratings/` (created for this task; not committed).
All retrieval timestamps are UTC, 2026-09-23, captured with `curl -w`.

## Sources located and pinned

| Release | Publication date | Date source | Medal-table image |
|---|---|---|---|
| 1.0 | 2025-03-26 (09:11:39 UTC) | `newsletter.semianalysis.com/p/the-gpu-cloud-clustermax-rating-system-how-to-rent-gpus`, JSON-LD `datePublished` | `clustermax.ai/img/neocloud-ranking-v1.webp` |
| 2.0 | 2025-11-06 (17:02:53 UTC) | `newsletter.semianalysis.com/p/clustermax-20-the-industry-standard`, JSON-LD `datePublished` | `clustermax.ai/img/neocloud-ranking-v2.jpg` (note: URL has no "0" — `v2.jpg`, not `v2.0.jpg`; probed `.jpg/.jpeg/.png/.webp` variants of `v2.0` and `v2`, only `v2.jpg` returned 200) |
| 2.1 | April 2026 (day not confirmed) | banner text inside the image itself: "SemiAnalysis GPU Cloud ClusterMAX™ Rating April 2026"; `clustermax.ai/v2.1` page has no explicit publish date in HTML, meta tags, or JSON-LD | `clustermax.ai/img/neocloud-ranking-v2.1.jpg` |

The 1.0 post URL was not guessable directly (`semianalysis.com/2025/03/26/clustermax-rating-system-for-ai-cloud-providers/` and similar 404'd); it was found by grepping the 2.0 newsletter HTML for internal links, which contained `https://semianalysis.com/2025/03/26/the-gpu-cloud-clustermax-rating-system-how-to-rent-gpus/` — the `/2025/03/26/` path segment corroborates the JSON-LD date.

`neocloud-ranking-v2.jpg` was confirmed to be the correct 2.0 table (not a stray/placeholder file) two ways: (1) its banner text reads "...Rating November 2025", matching the known 2.0 publish month; (2) the 2.0 newsletter's `og:image` meta tag points to a Substack-hosted image at 1742×874px, essentially identical in size to the 1738×873px `neocloud-ranking-v2.jpg` — both were downloaded and hashed (see `raw/SHA256SUMS.txt`).

**2.1 exact publish day:** not found. Checked the `clustermax.ai/v2.1` page source (no date field), tried three WebSearch queries, and queried the Wayback Machine CDX API for `clustermax.ai/v2.1` and its image — earliest crawl was **2026-05-15**, which postdates "April 2026" and is only a lower bound on when a crawler first visited, not a publication date. A CoreWeave press-release page referencing a ClusterMAX rating was fetched but its static HTML did not contain the relevant text (likely client-rendered) and gave no date. `published_date` in `clustermax-2.1.json` is therefore recorded as `"2026-04"` (month precision only) with a note explaining the gap. Used 3 of the 5 allowed WebSearch calls on this; stopped rather than spend more.

## Method

1. Downloaded every image and HTML page with `curl` into `raw/`, recording sha256 (`raw/SHA256SUMS.txt`) and retrieval time.
2. Viewed each full medal-table image with the Read tool (pass 1).
3. Used Python/PIL (stdlib pip-installed `Pillow` was already available; no install needed) to detect the table's horizontal divider lines programmatically (`numpy`, thresholding on near-black pixel rows) and crop each tier row individually at 1.6–2.6× upscale, splitting wide rows into overlapping left/right halves (pass 2, independent re-crop from the source file, not derived from the pass-1 screenshot).
4. Compared pass 1 and pass 2 transcriptions per tier. **Every tier in all three releases matched exactly between passes** — no unresolved disagreements. Two items were marked `confidence: "low"` in the JSON not because the two passes disagreed, but because the source logo itself is ambiguous even at 2.6× zoom:
   - **"STN"** (Bronze in 2.0 and 2.1): logo is a plain circular wordmark reading only "STN"; no fuller company name is rendered anywhere in the image.
   - **"Mistral AI"** (Unavailable in 2.0 and 2.1): logo reads "MISTRAL AI_" with a stylized trailing underscore, which may denote a specific compute/cloud division rather than the LLM lab itself; not otherwise disambiguated in the image.

## Row-label structure (2.0 and 2.1 only; 1.0 differs)

In 1.0, the bottom tier's Ranking-column label is simply **"Underperforming"**, containing one flat list of 10 providers.

In 2.0 and 2.1, the Ranking-column label for the entire bottom band is **"Not Recommended"**, and *within* that band the image itself prints two sub-headers as row labels: **"Underperforming"** and **"Unavailable"**. Per the task's schema (flat `tier` per provider), each provider was assigned the more specific sub-header value ("Underperforming" or "Unavailable") as its `tier`, with a `note` recording that the image's outer Ranking-column label for that row is "Not Recommended". No normalization of "Underperform" variants was needed — the images consistently print "Underperforming" in full.

## Cross-release changes observed (2.0 → 2.1)

Comparing the two images directly (not from any external source) surfaced:
- **Hot Aisle**: "Underperforming" in 1.0 (March 2025), then promoted to **Bronze in both 2.0 (Nov 2025) and 2.1 (Apr 2026)** — confirmed independently in all three images.
- **DataCrunch → Verda**: rebranded between 1.0 and 2.0; the 2.0 and 2.1 images both show "Verda" with a small "formerly DataCrunch" caption under the logo.
- **Core42, BitDeer, FPT Cloud/FPT AI Factory**: all three sat in the 2.0 "Unavailable" row; all three moved up to the 2.1 "Bronze" row (FPT's label also changed from "FPT CLOUD" to "FPT AI Factory"). This matches web-search commentary that 2.1 "moved four newly tested providers into the Bronze tier" (the fourth being new entrant **Radiant**, which does not appear anywhere in the 2.0 image at all).
- **evroc** and **greenai.cloud**: present in 2.0's "Unavailable" row, absent from the 2.1 image entirely. Not confirmed whether dropped, renamed, or merged — flagged in `clustermax-2.0.json` notes, not treated as "unresolved" since both passes agree the entries simply aren't in the 2.1 image.
- New entrants appearing only in 2.1's "Unavailable" row (not in 2.0): Tatra SuperCompute, Moonlite, BytePlus, SK telecom, VESSL AI, QumulusAI, boostrun.
- Platinum, Gold, and Silver tiers are byte-for-byte identical in composition across 2.0 and 2.1 (CoreWeave / Oracle+Nebius+Azure+Crusoe+FluidStack / the same 12 Silver logos). The "Underperforming" sub-tier is also identical across 2.0 and 2.1 (same 22 providers).

## Unresolved items

None outstanding after re-inspection. (Two low-confidence identifications are logged above and in the JSON `note` fields, but both passes agreed on the reading — the ambiguity is in the source logo, not in disagreement between transcription passes.)

## Files

- `raw/` — downloaded originals + `SHA256SUMS.txt` + wayback/GitHub lookups used while trying to pin the 2.1 date (inconclusive, kept for the record).
- `crops/` (removed before commit) — PIL-generated row/section crops used for the second transcription pass; regenerate from `raw/` if needed.
- `clustermax-1.0.json`, `clustermax-2.0.json`, `clustermax-2.1.json` — per schema `secondrun.clustermax-medals.v1`.
