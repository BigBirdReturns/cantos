# R1 ineligible / not-collected providers

For every provider rated in ClusterMAX 1.0 or 2.0 (excluding the "Unavailable"
tier, which `scripts/retrospective.py` excludes before ever looking at
incident data) that does **not** have a `retrospective/incidents/<slug>.json`
file, this records why, so the exclusion is checkable. All findings below are
from direct `urllib`/`curl` probes run 2026-09-23 (no WebSearch), separate
from and in some cases correcting `retrospective/status-pages.json`'s
discovery notes (that discovery run pre-dates the fixed Atlassian
`history.json` collector and, for a few platforms, the live surface has
changed since discovery ran).

No severity is ever invented for a provider whose platform has none; where a
provider is listed here as "no severity field," that's a statement about the
platform, not a decision to guess one.

## Collected but not fully eligible (has a `<slug>.json`, may still be
excluded by `retrospective.py`'s coverage-window rule)

- **Lambda** (`lambda.json`, incident.io-hosted, not real Atlassian
  Statuspage): `/history.json` 404s -- this platform does not expose it.
  Only `/api/v2/incidents.json` is available, which caps at the ~25 most
  recent incidents with no confirmed pagination to the start of history, so
  `coverage_start` is correctly left `null` per SCHEMA.md. Not superseded by
  the new history.json collector (that collector simply doesn't apply to
  this platform); the file is kept as-is.

## Hyperscaler status pages (checked individually -- no blanket exclusion)

- **AWS**: `status.aws.amazon.com/data.json` is real JSON but is a
  current/active-events feed (2 events at check time, oldest ~hours old),
  not an archive; no history endpoint found. `health.aws.amazon.com/health/status`
  requires an AWS console login.
- **Azure**: `azure.status.microsoft/en-us/status/history/` is a
  client-rendered React app; the fetched HTML contains no incident dates,
  severities, or `__NEXT_DATA__`/JSON payload to parse statically.
- **Google Cloud**: `status.cloud.google.com/incidents.json` is real JSON
  with `severity` (`low`/`medium`/`high`) and `begin`/`end` timestamps, but
  it only returned 6 incidents, earliest `2026-02-27` -- short of both the
  primary window start (2025-11-06) and the secondary window
  (2025-03-26..2025-09-22) by a wide margin. No further-back archive
  endpoint found (`/2025.json`, `/history.json`, `/incidents/2025.json` all
  404). Rolling/short window, not a full archive.
- **Oracle** (`ocistatus.oraclecloud.com`): client-rendered SPA shell (2459
  bytes of HTML, no incident content); no JSON API found.
- **IBM Cloud** (`cloud.ibm.com/status`): client-rendered SPA shell (4925
  bytes of HTML, no incident content); no JSON API found.

## status.io (CoreWeave, OVHcloud)

Both are on status.io. `api.status.io/1.0/status/<page_id>` gives only
current status (its `/incidents` and `/history` sub-resources return
HTTP 403). The HTML history page
(`<status_url>/pages/history/<page_id>?date=YYYY-MM`) **ignores the `date`
query parameter entirely** -- verified by requesting `date=2024-01` and
`date=2026-08` and getting byte-identical output each time, always showing
only the current rolling window (for OVHcloud: a single "September 2026"
`timelineMajor` block with ~20 recent events; for CoreWeave: a "No incidents
in the last day" empty state). `status-pages.json`'s discovery notes
("reachable-content-present" for 6 sampled months) reflect this same
always-current page, not real per-month filtering -- a false positive in
that discovery pass. A path-segment variant
(`/pages/history/<id>/2025-03`) 404s. No way found to reach 2025-03 depth.

## betteruptime / Better Stack (FluidStack, Together.ai, RunPod, Prime
Intellect, Cudo Compute, Hydra, GPU.NET)

Confirmed on 7 representative pages (status.fluidstack.io,
status.together.ai, uptime.runpod.io, status.primeintellect.ai,
status.cudocompute.com, status.hydrahost.com, status.gpu.net): the only
static endpoint that returns real, page-specific JSON is `/index.json`
(a JSON:API document), and its `included` array holds at most the single
currently-active `status_report` -- not a history. Every other guessed route
(`/history`, `/history.json`, `/incidents.json`, `/feed`, `/reports.json`,
`/api/v2/status.json`, `/status_reports.json`) serves the same
byte-identical client-rendered SPA shell for every page on the same
platform (the route is handled client-side after JS loads). The
authenticated API (`uptime.betterstack.com/api/v2/...`) returns
`401 Unauthorized` without a bearer token we don't have. No static path to
a full incident history was found for this platform.

## Trust-center pages (Vanta), not incident status pages by design

**Crusoe**, **Voltage Park**, **Shadeform**, **GMI** (trust.gmicloud.ai):
each resolves to a Vanta-style security/compliance trust center, which
publishes controls and audit attestations, not an incident timeline. No
incident data exists on these pages to collect.

## Custom platforms (each independently probed; none reaches 2025-03 with a
severity or equivalent)

- **Vultr**: root page loads; `/history`, `/feed` return 403; `/index.json`,
  `/api/v2/status.json`, `/history.json` all 404. No endpoint found.
- **Vast.ai**: hand-rolled JS widget (`index.js`) that renders `maxDays = 30`
  of daily uptime squares from `logs/<component>_report.log`, colored by a
  computed uptime threshold (`success`/`partial`/`failure`), not a
  provider-assigned severity. Even if scraped, the window is 30 days, far
  short of the 180-day study window, let alone back to 2025-03. Too shallow
  and no real severity field.
- **Hetzner**: `/history`, `/feed`, `/index.json`, `/api/v2/status.json`,
  `/history.json` all 404. No endpoint found.
- **deepinfra**: same -- all guessed endpoints 404.
- **Salad**: `/history` returns real JSON, but it is a fixed rolling
  ~7-day window (`period_start`/`period_end` unix timestamps spanning ~7
  days); `period_start`/`period_end` query parameters are accepted but
  silently ignored (verified: a request for a much wider range returned the
  same byte-identical 7-day payload). No per-incident severity field either
  (only aggregate `outages`/`downtime_secs` counters). Too shallow, no
  severity.
- **Massed Compute**: tiny homepage (1300 bytes); no history/feed/json
  endpoint found.
- **Hyperbolic**: `/history` returns HTML but it is an empty client-rendered
  SPA shell -- zero occurrences of any date, incident, or severity string in
  the fetched markup.
- **E2E Cloud**: `/history` returns substantive HTML (mentions of
  "incident"/"Resolved") but zero occurrences of any 2025 date and only 8 of
  "2026-" (likely component/version strings, not incident dates); no
  discernible per-incident start/end timestamps or severity labels found in
  the static markup. Would need JS execution to confirm; not implemented
  here without that evidence.
- **Neysa** (trust.neysa.ai): despite the "custom" platform label, this is
  effectively another trust-center-style page; `/history`, `/feed`,
  `/index.json`, `/history.json` all 404.
- **Mithril** (flagged `atlassian-statuspage` by the original discovery,
  `api_summary_ok: true`): on live recheck, `/api/v2/status.json`,
  `/api/v2/incidents.json`, and `/history.json` all now 404, though the
  homepage itself loads (200KB). Whatever backed the `/api/v2` surface at
  discovery time is no longer reachable; no working incident API found.
- **GCore** (also flagged `atlassian-statuspage` with `api_summary_ok: true`
  at discovery, "0 incidents"): same story as Mithril -- `/api/v2/*` and
  `/history.json` now all 404 despite a large (2.2MB) homepage. No working
  incident API found.

## No public status/incident page located at all

(status-pages.json already establishes this per-provider via candidate-URL
probing; verified for Hot Aisle below since it's explicitly in scope.)

TensorWave, Firmus, GMO GPU Cloud, STN, Atlas Cloud, Qubrid, Verda/DataCrunch,
DENVR Dataworks, Buzz HPC, IREN/Iris Energy, FarmGPU, Whitefiber, dstack,
PaleBlueDot.AI, Clore.ai, Exabits, Sesterce, Aethir, Akash, Lepton AI, SMC
(the `smc.statuspage.io` slug resolves but is an unconfigured demo tenant --
its only "incident" is literally titled "This is an example incident",
created 2022-03-18 -- treated as no real status page).

**Hot Aisle**: re-checked directly (not just via status-pages.json's
candidate list). `hotaisle.xyz` (homepage) has no status/uptime link
anywhere in its markup. `hotaisle.statuspage.io` resolves but to Atlassian's
generic unclaimed-slug marketing page (`<title>Real-Time Incident
Communication with Statuspage | Atlassian</title>`), confirmed by fetching
`/api/v2/status.json`, `/history.json`, and `/api/v2/incidents.json` on that
host and getting the identical marketing-page bytes back for all three.
`status.hotaisle.xyz` and `trust.hotaisle.xyz` do not resolve (DNS
failure). No public status page exists for Hot Aisle; it is excluded from
collection (and, per PLAN.md, was already excluded from the primary
correlation by design regardless).

## Judgment call flagged explicitly

Per the coordinator's correction, hyperscaler status pages are **not**
blanket-excluded as "not comparable" -- each was checked individually above
on the same retrievability/coverage terms as every other provider, and each
is ineligible for a stated technical reason (shallow/rolling data or a
client-rendered page with no static incident content), not because it is a
hyperscaler.
