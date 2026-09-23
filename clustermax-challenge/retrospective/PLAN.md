# Retrospective study R1: do ClusterMAX medals track providers' own public incident records?

Status: **frozen before any incident data was collected** (git commit on branch
`agent/clustermax-standing-challenge`, 2026-09-23). The plan hash in `plan.json`
covers this file. Anything changed after collection is reported as a deviation.

This is a look back at public records, not the prospective customer-outcome test.
It asks a narrow question about one of ClusterMAX's ten criteria (reliability),
using the only outcome data that is public and free: each provider's own status page.

## Question

Among providers rated in a ClusterMAX release, do higher medals go with fewer
self-reported service incidents in the 180 days after that release?

## Inputs

* **Ratings.** ClusterMAX 2.0 (published 2025-11-06) is the primary release.
  ClusterMAX 1.0 (published 2025-03, date pinned in `ratings/`) is secondary.
  Medals are taken from the official published tables/images, with source URL and
  file SHA-256 recorded. Ordinal: Platinum 5, Gold 4, Silver 3, Bronze 2,
  Underperforming 1. "Unavailable"/unrated providers are excluded.
* **Outcomes.** Each provider's public status page incident history, captured with
  retrieval time, URL and raw-file SHA-256.
* **Window.** Primary: [2.0 publication date, +180 days). Secondary: [1.0 publication
  date, +180 days).

## Eligibility (decided before looking at counts)

A rated provider is included if its public status history is retrievable and
covers the entire window (the earliest retrievable record, or an explicit
"no incidents" archive month, predates the window start). Otherwise it is listed
as excluded with the reason. **Hot Aisle is excluded from the primary analysis**
because the author has a working relationship with it; its numbers are reported
separately and labelled.

## Outcome measures

* **Primary:** count of incidents whose provider-assigned impact is major or
  critical (or the provider's equivalent top two severities), started inside the window.
* **Secondary:** count of all incidents of any impact; sum of incident durations
  in hours (start to resolved).

Scheduled maintenance is excluded. Incidents are not filtered by component
(component naming differs too much across providers to filter without judgement);
this is a limitation, not a choice made after seeing results.

## Analysis

* Spearman rank correlation (average ranks for ties) between medal ordinal and
  each outcome measure, across included providers.
* Uncertainty: 5000 provider-level bootstrap resamples, seed 20260923, 95%
  percentile interval. Exact two-sided permutation p-value (or 20000 random
  permutations if the provider count makes exact enumeration impractical).
* Reading rule for the primary measure:
  * interval entirely below 0: **consistent** with medals tracking reported incidents;
  * interval entirely above 0: **inconsistent** (higher medals, more incidents);
  * otherwise: **inconclusive**.
* Minimum: fewer than 8 included providers means the result is reported as
  **insufficient** and no reading is given.

## Known limits, stated in advance

1. Status pages are self-reported. A provider that reports honestly and in detail
   looks worse than one that reports nothing. This transparency effect can reverse
   the sign of any correlation and cannot be removed with public data.
2. Status pages cover whole companies; ClusterMAX rates GPU cloud offerings.
3. Reliability is one of ClusterMAX's ten criteria. A null or inverse result here
   does not show the medals are wrong overall.
4. Retrospective and observational. Nothing here is causal or prospective.

Every excluded provider, every raw file and every deviation from this plan is published
alongside the result.
