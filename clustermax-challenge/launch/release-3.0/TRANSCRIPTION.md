# ClusterMAX 3.0 medal table transcription — method and notes

Working directory: `launch/release-3.0/` (created for this task; not committed).
All retrieval timestamps are UTC, 2026-09-23, captured with `curl -w`.
Follows the same method as `retrospective/ratings/TRANSCRIPTION.md` (1.0/2.0/2.1).

## Release identification

ClusterMAX 3.0 was announced by Jordan Nanos at
https://x.com/JordanNanos/status/2102871532267847699 (~2026-09-23 21:23 UTC),
with an attached table image (`raw/tweet-image-orig.jpg`, 1432x880).

`clustermax.ai` had **not** been updated with a v3.0/v3 page as of retrieval
(`/v3.0` and `/v3` both 404; `sitemap.xml` still lists only `/v1`, `/v2`,
`/v2.1`; site `lastmod` predates the tweet). The `/img/neocloud-ranking-v3*`
image path variants listed in the task (`.jpg`/`.jpeg`/`.png`/`.webp`, with
and without the trailing `.0`) all 404'd too. So unlike 2.0/2.1, the
official source for 3.0 is the **SemiAnalysis newsletter post**, not the
clustermax.ai site.

The newsletter post was not in the top-10 `/api/v1/archive?sort=new&limit=10`
listing at the moment of the first fetch (top entry was 2026-09-21), so the
slug was found by guessing from the 2.1 post's slug pattern
(`clustermax-21-...` → `clustermax-30-the-industry-standard`), which
returned HTTP 200. Its JSON-LD `datePublished` is
`2026-09-23T21:20:29+00:00` — three minutes before the tweet, consistent
with the tweet linking to/announcing this post. `published_date` in
`clustermax-3.0.json` is recorded as `"2026-09-23"`.

The medal-table image itself was extracted from the post body (not the
`og:image`, which is a separate 1448x1086 cropped/re-encoded preview used
for social-card unfurling) by grepping the HTML for
`substack-post-media.s3.amazonaws.com` image URLs and picking the one whose
embedded dimensions (`1432x880`) match the tweet image's dimensions exactly:
`raw/neocloud-ranking-v3.0-newsletter-source.png`, fetched directly from
the S3 origin (353,995 bytes, matching the `data-attrs` byte count in the
post HTML) rather than through the Substack CDN's downscaled/webp
renditions. This PNG is the primary transcription source; the tweet JPEG
(same 1432x880 dimensions) was used only as a cross-check, not re-read
independently pixel-by-pixel.

## Method

1. Downloaded every page and image with `curl` into `raw/`, recording
   sha256 (`raw/SHA256SUMS.txt`) and retrieval time.
2. Viewed the full medal-table image with the Read tool (pass 1).
3. Used Python/PIL (`numpy` thresholding on near-black pixel rows, same
   approach as the 1.0/2.0/2.1 transcription) to detect the table's
   horizontal divider lines programmatically and crop each tier row
   individually at 3x upscale, split into overlapping left/right halves
   (pass 2, independent re-crop from the source file). Dense rows (Bronze,
   Participation Ribbon, Unavailable) were further re-cropped at 6-14x zoom
   on specific logo clusters to resolve small/crowded logos.
4. Compared pass 1 and pass 2 transcriptions per tier/row. **Every tier
   matched exactly between passes** — no disagreements between the two
   independent reads.
5. Cross-checked the full transcription against the newsletter article's
   own body text (not just the table image), which independently confirms:
   - The exact tier-count/movement summary: *"Google Cloud joins Oracle in
     the Gold tier. Azure moves to Silver, Fluidstack moves to Unavailable,
     and Crusoe drops to Bronze. Lambda, Firmus and TensorWave remain in
     Silver, while GMI moves up to Silver from Bronze."* — matches the
     transcribed table exactly.
   - A prose enumeration of the Unavailable tier's sub-groups (previously
     tested and now uncooperative; yet-to-launch/tested; big but
     geographically untestable; too-small-to-be-rated), which resolved
     several low-confidence logo reads (see below).

## Row-label structure

Same convention as 2.0/2.1: the Ranking-column label for the whole bottom
band is **"Not Recommended"**, and within it the image prints two
sub-headers, **"Underperforming"** and **"Unavailable"**, which were used
as the `tier` value per provider (per-provider `note` records the outer
"Not Recommended" label).

## New tier: Participation Ribbon

3.0 introduces a new tier between Bronze and Underperforming. Its badge
graphic is a blue ribbon/rosette (not a circular medal like the other
tiers): the medallion reads "ClusterMAX 3.0" and the ribbon tail reads
"PARTICIPATION" (vertical text). **The literal word "Ribbon" never appears
in the image** — the tier is conveyed by the ribbon-shaped badge graphic
plus the word "PARTICIPATION". Recorded as `"Participation Ribbon"` per
the task instruction to record it "exactly as labelled"; this is the
closest literal rendering of what the image shows (shape + word), and
matches how SemiAnalysis's own site is expected to refer to it. Contains
exactly 15 providers.

## Logo ambiguities resolved via the article's own text

- **"PIC"**: bare square logo reading only "PIC". Article text confirms
  full name **"Poolside Infrastructure Company"**.
- **Bare "A" + 4-square checkerboard logomark** (between Corvex and
  Volta in the Unavailable row): no company name renders near this logo at
  any zoom tried (up to 14x). Article text lists, in the same left-to-right
  order as the image, "...Corvex, **Andromeda**, Volta, Firebird..." —
  identified as **Andromeda**.
- **"Mistral AI"** (stylized "MISTRAL AI_"): ambiguous in 2.0/2.1 (unclear
  if a compute division vs. the LLM lab). Article text plainly says
  "Mistral" is one of the yet-to-launch/tested providers doing bare metal
  — resolved as the LLM lab itself, confidence raised to high.
- **"GLOBAL AI"** and **"Argentum"**: both confirmed verbatim in the
  article's prose enumeration ("...GlobalAI, Argentum and Qumulus").
- **"Volta"** vs. **"Voltage Park"**: these are two different things. The
  article has a dedicated section titled *"Lightning (merged with Voltage
  Park)"*, describing Lightning AI and Voltage Park (Silver in 2.1) as
  having merged into one company, now listed only as **"Lightning AI"** in
  the Unavailable tier (Voltage Park no longer appears as a standalone
  logo). Separately, the same article text lists **"Volta"** as an
  unrelated, distinct yet-to-launch company in the same tier. Both facts
  are recorded in `clustermax-3.0.json` and in `transitions.json`.

## Remaining low-confidence item

- **STN** (Participation Ribbon; Bronze in 2.0/2.1): same ambiguity as
  every prior release — plain circular "STN" wordmark, no fuller name
  rendered anywhere in the image. Left at `confidence: "low"`, listed in
  `unresolved`.

## Providers confirmed absent from ClusterMAX 3.0 entirely

Three providers that were rated in 2.1 do not appear anywhere in the 3.0
image (all tier rows checked at zoom, full width) **and are not mentioned
anywhere in the newsletter article body text either**:

- **Hot Aisle** (Bronze in 2.1, Bronze in 2.0, Underperforming in 1.0) —
  zero mentions of "Hot Aisle" anywhere in the 3.0 newsletter HTML.
- **Qubrid** (Bronze in 2.1)
- **RunSun Cloud** (Unavailable in 2.1) — note: the article text's prose
  does mention a bare "RunSun" once, in the "big and important but
  untestable for geographic/regulatory reasons" group, but no "RunSun"
  logo appears in the image itself and the table's total count (77)
  excludes it; treated as absent from the rated table specifically.

A further 16 smaller 2.1 Underperforming/Unavailable providers (deepinfra,
dstack, GPU.NET, Clore.ai, Exabits, E2E Cloud, Aethir, Akash, Salad,
BluSky AI, Arc Compute, Telus, Telenor, backend AI, Sakura, neevcloud) are
also absent from both the 3.0 image and the article text. This is
consistent with the article's own statement that a bucket of smaller
providers is *"still covered in our market view, but not part of the
rating system"* — i.e. 3.0 appears to have deliberately pruned the
long tail of inactive/tiny Unavailable-tier entrants rather than just
re-tiering them. All of this is recorded per-row in `transitions.json`.

## Cross-check against the task's stated tweet facts

All match exactly, both from the image and independently from the
article's own summary sentence quoted above:

| Fact | Match |
|---|---|
| Nebius + CoreWeave Platinum | yes |
| Google Cloud + Oracle Gold | yes |
| Azure Silver | yes |
| Fluidstack Unavailable | yes |
| Crusoe Bronze | yes |
| Lambda, Firmus, TensorWave Silver | yes |
| GMI Silver | yes |
| 19 medallion (Platinum..Bronze) total | yes (2+2+5+10=19) |
| 15 Participation Ribbon | yes |
| 77 providers covered | yes (2+2+5+10+15+11+32=77) |

**No mismatches found.**

## Unresolved items

Only the STN logo-ambiguity above (consistent across every release to
date). No transcription-pass disagreements.

## Files

- `raw/` — downloaded originals + `SHA256SUMS.txt` (kept).
- `crops/` (removed before commit) — PIL-generated row/section/zoom crops used for the second
  transcription pass and logo disambiguation; **deleted after use** per
  task instructions (regenerate from `raw/neocloud-ranking-v3.0-newsletter-source.png`
  with the same divider-detection approach if needed again).
- `clustermax-3.0.json` — per schema `secondrun.clustermax-medals.v1`.
- `transitions.json` — per-provider 2.1 → 3.0 tier comparison, schema
  `secondrun.clustermax-transitions.v1`.
