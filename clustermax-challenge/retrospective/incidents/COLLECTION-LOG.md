# R1 incident collection log

Progress notes for the incident-collection pass over `retrospective/status-pages.json`
(providers rated in ClusterMAX 1.0 and/or 2.0). Does not touch `PLAN.md` or
`plan.json` (frozen).

## 1. Atlassian `history.json` collector (task 1)

Added `collect_atlassian_history()` to `scripts/collect_status.py`: pages
`<status_url>/history.json?page=N` (3 months/page, newest first, including
zero-incident months) until a page's oldest month predates 2025-03-01 or
pages run out, then fetches `<status_url>/incidents/<code>.json` for each
incident found (exact `created_at`/`resolved_at`/`impact`, maintenance
detection via `impact == "maintenance"` or `scheduled_for`). Severity map:
critical/major/minor identity, `none`/`maintenance` -> `none`.
`coverage_start` is only set when paging reached a month older than
2025-03-26 or ran out of pages (reached the page's own creation), and is the
later (max) of the page's `created_at` date and the oldest returned month's
first day. Rate limiting: `default_fetch_paced` enforces <=2 req/s;
`fetch_with_retry` retries 429/5xx/network errors up to 3 attempts with
linear backoff. Every `history.json` page and every `incidents/<code>.json`
response is saved under `retrospective/incidents/raw/<slug>/` with its
SHA-256 in `raw_files`.

Verified live against `status.digitalocean.com` before writing the
collector: `history.json?page=1` returns real JSON (not the HTML page some
discovery notes assumed), `?page=7` reaches January 2025, and per-incident
`/incidents/<code>.json` gives exact ISO timestamps and a literal
`impact: "maintenance"` for scheduled work. This confirms the standing
discovery note ("Atlassian history is capped") was wrong: `/api/v2/incidents.json`
is capped (~25-50 recent), but `history.json` is not.

Fixture tests added to `tests/test_collect_status.py`
(`AtlassianHistoryCollectorTests`, `RetryAndRateLimitTests`): pagination
stop-before-2025-03 + coverage_start, "reached page creation before
threshold" branch, "neither threshold reached -> null" branch, maintenance
detection/severity, detail-fetch-failure fallback to the coarse summary, raw
file hashing, safety-cap note, and retry/no-retry behavior for
transient vs. non-transient HTTP errors. No network in tests.

## 2. status.io (task 2)

Investigated CoreWeave and OVHcloud (both status.io). `api.status.io/1.0/status/<id>`
only returns current status; its `/incidents` sub-resource 403s. The HTML
history page (`/pages/history/<id>?date=YYYY-MM`) **ignores the `date`
query param** -- verified byte-identical responses for `date=2024-01` and
`date=2026-08` -- and always renders only the current rolling window
(~20 recent events). Not implemented: no way found to reach full
2025-03..2026-05 history. See `INELIGIBLE.md`.

## 3. betteruptime / custom pages (task 3)

Probed 7 betteruptime pages (FluidStack, Together.ai, RunPod, Prime
Intellect, Cudo Compute, Hydra, GPU.NET): only `/index.json` returns
real per-page JSON, and it holds at most the single currently-active
report, not a history; every other guessed route serves an identical
client-rendered SPA shell across all pages on the platform; the
authenticated API 401s without a token. Not implemented for this platform.

Probed the "custom" pages individually (Vultr, Vast.ai, Hetzner,
Hyperbolic, deepinfra, Salad, Massed Compute, E2E Cloud, Neysa): none
exposes a full history with start/end times and a severity back to
2025-03. Salad's `/history` JSON is real but a fixed ~7-day rolling window
with no per-incident severity (query params to widen it are silently
ignored). Vast.ai is a 30-day computed-uptime-color widget, not
provider-assigned severity. Full per-provider reasons in `INELIGIBLE.md`.
No severity was invented for any of these -- they're just not collected.

## 4. Collection run + eligibility judgment call (task 4)

Ran the new `atlassian-history` collector for every provider whose
`status-pages.json` platform is `atlassian-statuspage` **and** actually
answers `history.json` on live recheck: Nebius, Scaleway, Cirrascale,
Hyperstack, latitude.sh, Lightning AI, DigitalOcean, Akamai, Sharon AI (9
providers). Two providers flagged `atlassian-statuspage` at discovery time
(GCore, Mithril) no longer answer `/api/v2/*` or `/history.json` on live
recheck -- see `INELIGIBLE.md`; this is a live-state finding, not a
disagreement with the discovery run. Lambda (incident.io-hosted, not real
Atlassian Statuspage; `/history.json` 404s) keeps its existing
`lambda.json` from the earlier smoke test -- not superseded, since the
`history.json` route genuinely doesn't exist for that platform.

Per the coordinator's correction: hyperscaler status pages (AWS, Azure,
Google Cloud, Oracle, IBM Cloud) are **not** blanket-excluded. Each was
checked individually (see `INELIGIBLE.md`); each turned out ineligible for
a stated technical reason (shallow rolling data or a client-rendered page
with no static content), not a hyperscaler-blanket judgment.

`provider_map.json` updated to map every ClusterMAX 1.0/2.0 rated-tier
provider name to its incidents-file slug, keeping the GMI/GMI Cloud and
Verda/DataCrunch merges (and adding IREN/Iris Energy as a third same-company
merge, since both point at the same `iren.com` homepage and neither has a
status page anyway).

`retrospective/incidents/lambda.json` (the old smoke-test file) is kept, not
deleted -- see above, it is not superseded.

## 5-6. Results and test runs

Collection run completed 2026-09-23: 9 providers via `atlassian-history`
(nebius, scaleway, cirrascale, hyperstack, latitude-sh, lightning-ai,
digitalocean, akamai, sharon-ai), all with `coverage_start: 2025-01-01`
(sharon-ai: `2025-10-10`, its page's own creation date) and
`coverage_end: 2026-09-23`, plus the pre-existing `lambda.json`
(coverage_start null, excluded).

`python scripts/retrospective.py` ran clean and wrote
`retrospective/results/R1-result.json` + `.md`. Primary release (ClusterMAX
2.0): 9 eligible providers (nebius, scaleway, cirrascale, hyperstack,
latitude-sh, lightning-ai, digitalocean, sharon-ai, akamai) >= minimum 8 ->
sufficient, reading **inconclusive** (major/critical bootstrap 95% CI
crosses 0). Secondary release (ClusterMAX 1.0): only 2 eligible (nebius,
scaleway -- the only two of the nine collected providers actually rated in
1.0) < minimum 8 -> **insufficient**, no reading given. Exact numbers in
the final handback message and in `retrospective/results/R1-result.json`.

`python -m unittest discover -s tests -p "test_*.py"`: 76 tests, all pass.
`PYTHON=<python> node tests/test_engine.cjs`: 26 checks passed. Both exact
outputs pasted in the final handback message.

## Packaging (2026-09-23)

The loose raw responses (2,311 files, ~147 MB, mostly repeated page metadata)
are stored byte-for-byte in `raw-2026-09-23.zip` at their original relative
paths (`incidents/raw/<slug>/...`). Every `raw_files[].sha256` in the
per-provider JSON refers to a member of that archive. The rating-image crops
used for transcription were deleted (they are derivable from `ratings/raw/`).

## Packaging and re-collection (2026-09-23, coordinator)

The first run's loose raw responses were deleted by a packaging-script error
before they were archived. All ten providers were re-collected the same day
with the same collector. Against the first run's normalized files: identical
incident sets for every provider (0 added, 0 removed); one Scaleway incident's
fields changed (live page updated); coverage dates identical; every R1 statistic
identical to full precision. The first-run normalized files are not published;
the raw responses behind the published files are the second run's.

Raw responses (2,311 files, ~147 MB uncompressed, mostly repeated page
metadata) are stored byte-for-byte in `raw-2026-09-23.zip` at their original
relative paths (`incidents/raw/<slug>/...`); every `raw_files[].sha256` in the
per-provider JSON refers to a member of that archive. The rating-image crops
used for transcription were removed; they are derivable from `ratings/raw/`.
