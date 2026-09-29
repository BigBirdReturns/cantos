# Retrospective study R2: do ClusterMAX 3.0 medals track providers' own public incident records?

Status: **frozen before any correlation was computed** (2026-09-29). The hash of this file is
in `plan-R2.json`; `run_r2.py` refuses to run if this file or the runner changes. Anything
changed after the run is reported as a deviation.

R2 repeats the design of R1 (`PLAN.md`, `results/R1-result.md`, unchanged) on a wider provider
set and the six-tier ClusterMAX 3.0 table. It is a look back at public records, not the
prospective customer-outcome test.

## Disclosure about ordering

R1 froze its plan before any incident data was collected. R2 cannot say that. The R2 incident
files were collected on 2026-09-29 before this plan was written, and the collector printed
per-provider incident counts as it ran, so some counts were seen (the largest were RunPod and
Gcore; several Better Stack pages had none). No rank correlation, interval or p-value was
computed until after this file was hashed. The design below repeats R1's and adds only rules
that the wider collection made necessary (severity mapping for platforms Atlassian's `impact`
field does not cover, the capped-feed coverage rule, six ordinals, the permutation rule).
The provider set is whatever could be collected; it was not chosen by how it would correlate.

## Question

Among providers rated in ClusterMAX 3.0, do higher medals go with fewer self-reported service
incidents in the 180 days before the 3.0 release? The same window is applied to ClusterMAX 2.0
medals as a secondary comparison.

## Inputs

* **Ratings, primary.** ClusterMAX 3.0 (published 2026-09-23), from
  `launch/release-3.0/clustermax-3.0.json` (transcribed from the newsletter's medal image; its
  recorded sources and hashes are in that file). Ordinal: Platinum 6, Gold 5, Silver 4,
  Bronze 3, Participation Ribbon 2, Underperforming 1. **Unavailable** and providers **not
  present** in the release are excluded.
* **Ratings, secondary.** ClusterMAX 2.0 (published 2025-11-06), from
  `retrospective/ratings/clustermax-2.0.json`, same ordinal table (2.0 has no Ribbon tier).
  Unavailable excluded.
* **Outcomes.** Each provider's public status-page incident history under
  `retrospective/incidents/<slug>.json` (schema `secondrun.status-incidents.v1`), with raw file
  hashes, collected 2026-09-29 (some files are the 2026-09-23 R1 collection, unchanged). Name to slug:
  `provider_map.json` plus `provider_map_R2.json`, else a slugified name.
* **Window.** 180 days ending on the 3.0 release date: [2026-03-27, 2026-09-23), start
  inclusive, end exclusive, in UTC. The same window is used for both rating sets.

## Eligibility (decided before looking at correlations)

A rated provider is included if its incident file exists and either:

1. `coverage_start <= 2026-03-27` and `coverage_end >= 2026-09-23` (R1's rule); or
2. **capped-feed rule:** `coverage_start` is null (the collector could not prove where the
   history starts), the feed is an ordered recent-incident feed, the oldest non-maintenance record
   started before 2026-03-27, and `coverage_end >= 2026-09-23`. A feed that reaches back past the
   window start has not dropped in-window records by age. This rule admits only existing
   files whose `coverage_start` is null; it is reported per provider and switched off in
   sensitivity S5.

Otherwise the provider is listed as excluded with the reason (no file, coverage too short,
etc.). **Hot Aisle is excluded by design** (author working relationship); it has no public status
page and is not in the 3.0 table.

## Severity mapping (fixed now)

Primary measure counts incidents with severity `major` or `critical`. Where a platform has no
Atlassian-style `impact`, its own vocabulary is mapped by semantic tier: full outage/downtime ->
`critical`; partial outage/service disruption -> `major`; degraded performance/informational ->
`minor`; nothing recorded -> `none`.

| Platform | Provider label | Severity |
|---|---|---|
| Atlassian Statuspage | critical / major / minor / none | as given |
| Instatus | MAJOROUTAGE / PARTIALOUTAGE / DEGRADEDPERFORMANCE, MINOROUTAGE | critical / major / minor |
| Better Stack | worst affected-service state: Downtime / Degraded performance | critical / minor |
| Better Stack | no affected component recorded | none |
| Google Cloud | SERVICE_OUTAGE / SERVICE_DISRUPTION / SERVICE_INFORMATION | critical / major / minor |
| SorryApp, status.io RSS | no severity exposed | none |

Scheduled maintenance is excluded (`is_maintenance`), including Instatus `UNDERMAINTENANCE` and
Better Stack blue (maintenance) states. Incidents are not filtered by component.
For Better Stack, only incidents where a component is marked Downtime count toward the primary
measure; Degraded performance and unlabelled incidents count toward the all-incident count only.

## Outcome measures

Same as R1: **primary** count of major/critical non-maintenance incidents started in the window;
**secondary** count of all non-maintenance incidents; sum of incident hours (unresolved capped at
the window end).

## Analysis

* Spearman rank correlation (average ranks for ties) between medal ordinal and each measure
  (`scripts/retrospective.py` functions, unchanged).
* 5000 provider-level bootstrap resamples, seed 20260929, 95% percentile interval.
* Two-sided permutation p-value: **exact when n! <= 500,000**, otherwise 20,000 random draws with
  the same seed.
* Reading rule for the primary measure (same as R1):
  * interval entirely below 0: **consistent** with medals tracking reported incidents;
  * interval entirely above 0: **inconsistent** (higher medals, more incidents);
  * otherwise: **inconclusive**.
* Fewer than 8 included providers: **insufficient**, no reading.

## Pre-declared sensitivities

Reported alongside, never replacing, the primary result:

* **S1 leave-one-out:** drop each included provider in turn; report the range of rho and how many
  runs read consistent / inconclusive / inconsistent.
* **S2 permutation exactness:** if n! <= 500,000 the main p is exact (stated); otherwise recompute
  with 200,000 random draws (seed 20260930) to show stability.
* **S3 maintenance mislabel check:** drop counted major/critical incidents whose title matches
  `\b(maintenance|planned|scheduled|upgrade)\b` (case-insensitive) and recompute.
* **S4 bootstrap seed robustness:** repeat the bootstrap with seeds 1..200; report the range of
  the lower and upper bounds and how many seeds give each reading. (R1's interval had a
  knife-edge lower bound at 0.)
* **S5 strict coverage:** drop providers admitted only by the capped-feed rule and recompute.
* **S6 critical only:** count only `critical` incidents as the primary measure and recompute.

## Known limits, stated in advance

1. Status pages are self-reported. A provider that reports in detail looks worse than one that
   reports nothing; several included pages record no incidents at all. This transparency effect can
   reverse the sign of the correlation and cannot be removed with public data.
2. Status pages cover whole companies; ClusterMAX 3.0 rates managed GPU clusters. Scope, fleet
   exposure and severity conventions differ across providers; counts are not a customer failure rate.
3. The 3.0 medals are dated at the end of the window, so any link between them and the preceding
   record is concurrent, not predictive, and could run either way (reviewers see the same pages).
   The 2.0 comparison uses medals ten months older than the window.
4. Severity vocabularies were mapped by the table above; Better Stack and SorryApp expose little or
   no severity, so results for those providers rest on that mapping.
5. Reliability is one of ClusterMAX's ten criteria. A null or inverse result does not show the medals
   are wrong overall. Retrospective and observational; nothing here is causal or prospective.

Every excluded provider, every raw file and every deviation from this plan is published alongside
the result.
