# Incident collection log, 2026-09-29 (R2 widening)

Continuation of `COLLECTION-LOG.md` (2026-09-23), which is unchanged. This pass widens the incident record for the R2 study (`../PLAN-R2.md`).
Providers covered: every provider rated (not Unavailable) in ClusterMAX 3.0 or 2.0. Sources: the provider surfaces saved under
`sessions/clustermax-cloudreview-20260929/providers/<slug>/` (read-only inputs) plus live fetches, paced at <=2 requests/second, saved with SHA-256 under `raw/<slug>/`.

## Method by platform

* **Atlassian Statuspage:** `scripts/collect_status.py --mode atlassian-history` (Crusoe only; the other Atlassian providers already had files).
* **Better Stack** (Verda, Prime Intellect, together.ai, FluidStack, RunPod, Cudo, Hydra): `collect_status.py` has no mode for it, and its `--manual-json` path expects a hand-written document. Instead a one-off parser (scratch, not committed) read `/incidents/<YYYY-MM>/<YYYY-MM>` quarter pages and each `/incident/<id>` page; every page is saved under `raw/<slug>/` with its hash. The Better Stack list page shows only the resolution time and no impact; start time and the worst affected-service state (Downtime / Degraded performance / Maintenance) come from the detail page. Incidents with no affected component recorded get severity `none`.
* **Instatus** (Gcore, Mithril, Atlas Cloud): the paged JSON that the status page itself calls, `https://api.instatus.com/public/<page>/notices/monthly/<monthKey>?page_no=N`, for Jan-Sep 2026.
* **status.io** (CoreWeave, OVHcloud): no reachable history; audit files only.
* **Custom / other:** Google Cloud `incidents.json` (saved capture), Radiant (SorryApp) monthly history pages.

Coverage claims: `coverage_start` is the first day of the oldest month/quarter actually fetched, never inferred from the oldest incident.
Severity mappings are those fixed in PLAN-R2.md. Files marked EXCLUDED below still exist so the exclusion is checkable.

## Per-provider outcome

| Provider | 3.0 tier | 2.0 tier | Outcome | File | In R2 primary | In R2 secondary | Notes |
|---|---|---|---|---|---|---|---|
| CoreWeave | Platinum | Platinum | NEW 2026-09-29 | coreweave.json | - | - | status.io. History page ignores the date parameter (identical bytes for date=2026-04/2026-09); RSS holds 10 items, oldest 2026-09-11; API 403/404. File written from the RSS for audit; coverage_start null; EXCLUDED from R2 (no route to the window). |
| Nebius | Platinum | Gold | existing file (2026-09-23 R1 collection, not re-collected) | nebius.json | yes | yes | Atlassian-compatible; coverage 2025-01-01..2026-09-23. |
| Oracle | Gold | Gold | NO FILE |  | - | - | ocistatus.oraclecloud.com root is a 2,459-byte JS shell; status/incident/history/summary endpoints return 10-byte 404s; only components.json (current state). No history. |
| Google Cloud | Gold | Silver | NEW 2026-09-29 | google-cloud.json | yes | yes | Custom incidents.json, hand-parsed from the file saved in the 2026-09-29 capture (sha256 201d34fc0af9..., byte-identical to a live refetch). 6 incidents, oldest 2026-02-27. coverage_start null; accepted in R2 only through the capped-feed rule. |
| Azure | Silver | Gold | NO FILE |  | - | - | azure.status.microsoft history page is a client-rendered list of post-incident reviews with no static payload; RSS held one current item. Not parseable from disk; not attempted live. |
| Firmus | Silver | Silver | NO FILE |  | - | - | No status page (status.firmus.co / status.smc.co DNS fail). |
| Lambda | Silver | Silver | existing file (2026-09-23 R1 collection, not re-collected) | lambda.json | yes | yes | incident.io (Atlassian-compatible API), 25 most recent incidents, coverage_start null. Accepted in R2 only through the capped-feed rule (oldest 2026-02-13 predates the window). |
| GMI | Silver | Bronze | NO FILE |  | - | - | No status page (trust centre only). |
| TensorWave | Silver | Silver | NO FILE |  | - | - | No status page found (status host DNS fails; security host 403). |
| AWS | Bronze | Silver | NO FILE |  | - | - | health.aws.amazon.com is a JS shell; status.aws.amazon.com currentevents and all.rss hold recent event updates (38 items), not an archive. No incident history. |
| GCore | Bronze | Silver | NEW 2026-09-29 | gcore.json | yes | yes | Instatus (status-pages.json said Atlassian). Hand-parsed from https://api.instatus.com/public/status.gcore.com/notices/monthly/<monthKey>?page_no=N, Jan-Sep 2026, following isLastPage. The status page HTML shows only 5 notices per month, so the paged endpoint was required. 323 notices, 118 non-maintenance. |
| Verda | Bronze | Bronze | NEW 2026-09-29 | verda.json | yes | yes | Better Stack. No collect_status.py mode. Hand-parsed: fetched /incidents/<quarter> for 2026-01/03, 04/06, 07/09 and every /incident/<id> detail page (the on-disk copy held only the Jul-Sep 2026 quarter). Severity from the per-update affected-service state colour. |
| moonlite | Bronze |  | NOT PROBED |  | - | - | No surface for this provider in the 2026-09-29 capture and no collection attempted in this pass. status-pages.json lists: no status page. |
| Prime Intellect | Bronze | Bronze | NEW 2026-09-29 | prime-intellect.json | yes | yes | Better Stack, same method as Verda. |
| together.ai | Bronze |  | NEW 2026-09-29 | together-ai.json | yes | yes | Better Stack, same method. All three quarters show "No incidents reported"; zero-incident file, coverage 2026-01-01..2026-09-29. Zero is the page's own record. |
| Crusoe | Bronze | Gold | NEW 2026-09-29 | crusoe-r2.json | yes | yes | File renamed from crusoe.json after the first R2 run: R1 reads incidents/crusoe.json by that name and would have changed its frozen numbers (see plan-R2.json post_freeze_amendments). collect_status.py --mode atlassian-history against https://status.crusoecloud.com (live). 186 incidents, coverage 2025-01-01..2026-09-29. status-pages.json had only the Vanta trust centre. |
| DigitalOcean | Bronze | Bronze | existing file (2026-09-23 R1 collection, not re-collected) | digitalocean.json | yes | yes | Atlassian. |
| GMO GPU Cloud | Bronze | Silver | NO FILE |  | - | - | No status page (NXDOMAIN, none linked). |
| Hyperstack | Bronze | Bronze | existing file (2026-09-23 R1 collection, not re-collected) | hyperstack.json | yes | yes | Atlassian. |
| Vultr | Participation Ribbon | Silver | NO FILE |  | - | - | status.vultr.com and the site are Cloudflare-blocked to curl (403). |
| neysa | Participation Ribbon |  | NO FILE |  | - | - | trust.neysa.ai is a trust centre, not an incident page. |
| VESSL AI | Participation Ribbon |  | NOT PROBED |  | - | - | No surface for this provider in the 2026-09-29 capture and no collection attempted in this pass. status-pages.json lists: no status page. |
| Shadeform | Participation Ribbon | Bronze | NO FILE |  | - | - | trust.shadeform.com is a Vanta trust centre; status host does not resolve. |
| RunPod | Participation Ribbon | Bronze | NEW 2026-09-29 | runpod.json | yes | yes | Better Stack (uptime.runpod.io), same method. 51 incidents. |
| Radiant | Participation Ribbon |  | NEW 2026-09-29 | radiant.json | yes | - | SorryApp (status.radiant.co). Hand-parsed /history/2026/<month>, Jan-Sep; June-August return 404 (no notices listed). 4 notices, all maintenance; zero non-maintenance incidents. SorryApp exposes no severity. |
| FPT AI Factory | Participation Ribbon |  | NO FILE |  | - | - | status.fptcloud.com dead. |
| Core42 | Participation Ribbon | Unavailable | NO FILE |  | - | - | status.core42.ai dead. |
| latitude.sh | Participation Ribbon | Bronze | existing file (2026-09-23 R1 collection, not re-collected) | latitude-sh.json | yes | yes | Atlassian. |
| IBM Cloud | Participation Ribbon | Bronze | NO FILE |  | - | - | cloud.ibm.com/status is a 4.9 KB JS shell. |
| Buzz HPC | Participation Ribbon | Bronze | NO FILE |  | - | - | status.buzzhpc.ai dead. |
| Vast.ai | Participation Ribbon | Bronze | NO FILE |  | - | - | status.vast.ai is a 1.7 KB template shell ($title/$status placeholders), no API. |
| BitDeer | Participation Ribbon | Unavailable | NO FILE |  | - | - | status.bitdeer.ai dead. |
| Hyperbolic | Participation Ribbon | Underperforming | NO FILE |  | - | - | status.hyperbolic.ai is an UptimeRobot page that showed "There was an error while fetching the data"; no incident archive (platform corrected in status-pages.json). |
| STN | Participation Ribbon | Bronze | NO FILE |  | - | - | status.stninc.com redirects to google.com; no status page. |
| Sharon AI | Underperforming | Underperforming | existing file (2026-09-23 R1 collection, not re-collected) | sharon-ai.json | yes | yes | Atlassian, coverage from 2025-10-10. |
| IREN | Underperforming | Underperforming | NO FILE |  | - | - | status.iren.com does not resolve. |
| Hydra | Underperforming | Underperforming | NEW 2026-09-29 | hydra.json | yes | yes | Better Stack (status.hydrahost.com), same method. Every month Jan-Sep 2026 shows "No incidents reported". |
| FarmGPU | Underperforming | Underperforming | NO FILE |  | - | - | status host does not resolve. |
| Whitefiber | Underperforming | Underperforming | NO FILE |  | - | - | status host does not resolve. |
| PaleBlueDot.AI | Underperforming | Underperforming | NO FILE |  | - | - | palebluedot.instatus.com serves the Instatus marketing home page, not a PaleBlueDot status page (batch-D reported it as live; re-read and live-fetched, it is not). No status page found. |
| Akamai | Underperforming | Underperforming | existing file (2026-09-23 R1 collection, not re-collected) | akamai.json | yes | yes | Atlassian, coverage 2025-01-01..2026-09-23. |
| Hetzner | Underperforming | Underperforming | NO FILE |  | - | - | status.hetzner.com lists current reports only (custom); /history and /api/v2/incidents.json return the same 15 KB page; no archive found. |
| Mithril | Underperforming | Underperforming | NEW 2026-09-29 | mithril.json | yes | yes | Instatus (status-pages.json said Atlassian; /api/v2/incidents.json 404). Same paged endpoint as Gcore, host status.mithril.ai. 14 notices. |
| OVHcloud | Underperforming | Underperforming | NEW 2026-09-29 | ovhcloud.json | - | - | status.io (status.us.ovhcloud.com). Same limits as CoreWeave; RSS holds 10 items, oldest 2026-09-25. File written for audit; EXCLUDED from R2. Global status.ovhcloud.com is a JS-only shell. |
| Massed Compute | Underperforming | Underperforming | NO FILE |  | - | - | status.massedcompute.com returns a StatusIQ "No status page found with this domain mapping" error: dead. |
| FluidStack | Unavailable | Gold | NEW 2026-09-29 | fluidstack.json | - | yes | Better Stack, same method. Every month Jan-Sep 2026 shows "No incidents reported". |
| Cirrascale | Unavailable | Silver | existing file (2026-09-23 R1 collection, not re-collected) | cirrascale.json | - | yes | Atlassian. Unavailable in 3.0; 2.0 comparison only. |
| Lightning AI | Unavailable | Bronze | existing file (2026-09-23 R1 collection, not re-collected) | lightning-ai.json | - | yes | Atlassian. Unavailable in 3.0; 2.0 comparison only. |
| Scaleway | Unavailable | Silver | existing file (2026-09-23 R1 collection, not re-collected) | scaleway.json | - | yes | Atlassian. Unavailable in 3.0; enters only the 2.0 comparison. |
| Cudo Compute | Unavailable | Bronze | NEW 2026-09-29 | cudo-compute.json | - | yes | Better Stack, same method. Every month Jan-Sep 2026 shows "No incidents reported". |
| DENVR Dataworks | Unavailable | Bronze | NO FILE |  | - | - | No status page (status.denvr.com dead). |
| Atlas Cloud | Unavailable | Bronze | NEW 2026-09-29 | atlas-cloud.json | - | yes | Instatus page atlascloud.instatus.com; API key is "atlascloud" (host form 404s). 41 notices, every one labelled MAJOROUTAGE by the provider. |
| Sesterce | Unavailable | Underperforming | NO FILE |  | - | - | status.sesterce.com dead. |
| Together.ai | Not present | Silver | NEW 2026-09-29 | together-ai.json | yes | yes | Better Stack, same method. All three quarters show "No incidents reported"; zero-incident file, coverage 2026-01-01..2026-09-29. Zero is the page's own record. |
| Voltage Park | Not present | Silver | NO FILE |  | - | - | status host NXDOMAIN; trust centre only (folded into Lightning AI in 3.0). |
| Neysa | Not present | Bronze | NO FILE |  | - | - | trust.neysa.ai is a trust centre, not an incident page. |
| Qubrid | Not present | Bronze | NOT PROBED |  | - | - | No surface for this provider in the 2026-09-29 capture and no collection attempted in this pass. status-pages.json lists: no status page. |
| Hot Aisle | Not present | Bronze | EXCLUDED BY DESIGN |  | - | - | Author working relationship (plan-R2 excluded_by_design). Also no public status page (status.hotaisle.xyz NXDOMAIN). Not in the 3.0 table. |
| deepinfra | Not present | Underperforming | NOT PROBED |  | - | - | No surface for this provider in the 2026-09-29 capture and no collection attempted in this pass. status-pages.json lists: https://status.deepinfra.com (custom). |
| dstack | Not present | Underperforming | NOT PROBED |  | - | - | No surface for this provider in the 2026-09-29 capture and no collection attempted in this pass. status-pages.json lists: no status page. |
| GPU.NET | Not present | Underperforming | NOT PROBED |  | - | - | No surface for this provider in the 2026-09-29 capture and no collection attempted in this pass. status-pages.json lists: https://status.gpu.net (betteruptime). |
| Clore.ai | Not present | Underperforming | NOT PROBED |  | - | - | No surface for this provider in the 2026-09-29 capture and no collection attempted in this pass. status-pages.json lists: no status page. |
| Exabits | Not present | Underperforming | NOT PROBED |  | - | - | No surface for this provider in the 2026-09-29 capture and no collection attempted in this pass. status-pages.json lists: no status page. |
| E2E Cloud | Not present | Underperforming | NOT PROBED |  | - | - | No surface for this provider in the 2026-09-29 capture and no collection attempted in this pass. status-pages.json lists: https://status.e2enetworks.com (custom). |
| Aethir | Not present | Underperforming | NOT PROBED |  | - | - | No surface for this provider in the 2026-09-29 capture and no collection attempted in this pass. status-pages.json lists: no status page. |
| Akash | Not present | Underperforming | NOT PROBED |  | - | - | No surface for this provider in the 2026-09-29 capture and no collection attempted in this pass. status-pages.json lists: no status page. |
| Salad | Not present | Underperforming | NOT PROBED |  | - | - | No surface for this provider in the 2026-09-29 capture and no collection attempted in this pass. status-pages.json lists: https://status.salad.com (custom). |

Providers listed twice under different spellings (for example `together.ai` / `Together.ai`, `GCore` / `GCore`) are one provider; the R2 runner resolves them through `provider_map.json` + `provider_map_R2.json`.

## Notes on things that did not work as briefed

* **PaleBlueDot:** the brief and the batch-D report suggest `palebluedot.instatus.com` is a live Instatus page. It is not: it serves the Instatus marketing home page. `status-pages.json` records the URL with platform text saying so; no incident file exists.
* **status.io:** the history page ignores `?date=`; RSS holds 10 items. Neither CoreWeave nor OVHcloud can reach the window.
* **Better Stack and Instatus pages saved on disk were partial** (latest quarter, 5 notices per month). The complete records above needed live paged fetches.
* **Azure, AWS, Oracle, IBM, Vultr, Hetzner, Vast.ai:** no static route to a history was found; none were forced.
* **Lambda** and **Google Cloud** have `coverage_start: null`; R2 admits them only through its declared capped-feed rule and reports a strict-rule sensitivity (S5).
* **Better Stack zero-incident pages** (together.ai, FluidStack, Cudo, Hydra) are included as zero-count providers because their pages state "No incidents reported" for every month; a status page that is simply never used looks the same, which is the transparency limit stated in PLAN-R2.md.
