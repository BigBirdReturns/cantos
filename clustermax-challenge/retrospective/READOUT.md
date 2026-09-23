# R1: what the first collection establishes

The original R1 plan, input records and generated results are retained unchanged. This interpretation note was added after the ClusterMAX 3.0 release.

The collection obtained nine eligible histories from 59 rated providers. Some exclusions reflect shallow API windows, failed route discovery or client-rendered pages beyond the collector's implementation. They do not establish that only nine providers publish usable history. The original exclusion ledger records the collection process and includes stronger absence statements that this note does not adopt.

The reported association between the 2.0 medal rank and self-reported major/critical incident counts is rho = +0.6378, with a provider-bootstrap interval [0.00, 0.94] and two-sided permutation p = 0.07525. R1 classified it as inconclusive. Incident reporting, fleet exposure, service scope and severity conventions differ; counts are not a normalized customer failure rate. This is not the incremental customer-job prediction test.

The 3.0 rating concerns managed clusters. Provider-wide status records may include other services. A managed-cluster reliability claim requires service-matched evidence and an exposure denominator. No broad validation or refutation of the medals follows from R1.

[Original immutable output](results/R1-result.md) · [Collection and exclusion log](incidents/INELIGIBLE.md) · [Prospective submission protocol](../SUBMITTING.md)

## Post-hoc sensitivity (not part of the frozen analysis)

Everything below was computed after the frozen R1 run, by reusing
`scripts/retrospective.py`'s own functions (`spearman`, `bootstrap_ci`,
`permutation_p`) against the same nine eligible primary-release providers and
the same `major_or_critical_incident_count` measure -- without modifying that
script or its frozen output. None of this changes the pre-registered reading
below; it is reported because it shows the result is fragile, and a reader
deciding how much weight to put on "inconclusive" should see exactly how
fragile.

**(a) The bootstrap lower bound is a seed knife-edge.** Under the plan's
frozen seed (`20260923`, 5,000 draws), the 95% provider-bootstrap interval is
`[0.00, 0.9366]` -- the lower bound lands at exactly `0.0`, an artifact of a
resample that happens to draw a set of providers with zero rank variance
sitting right at the 2.5th percentile. Rerunning the identical procedure
across 200 other seeds (1 through 200, same 5,000 draws each): the lower
bound is exactly `0.0` in 141/200 runs, and in the other 59/200 runs
(29.5%) the lower bound is strictly positive, which under R1's own reading
rule (interval entirely above 0) flips the classification from
**inconclusive** to **inconsistent** (higher medals, more reported
incidents). The lower bound never exceeds about `0.09` across these 200
seeds. The frozen seed was fixed before collection and was not chosen to
produce either reading -- but the reading is not robust to the seed choice.

**(b) Exact permutation p over all 9! assignments.** With 9 eligible
providers, exact enumeration is 9! = 362,880 permutations -- practical to run
exhaustively on this cohort. The frozen implementation instead used
`PERMUTATION_CAP = 20000` random draws whenever `n!` exceeds that cap (the
plan itself allows random draws "if the provider count makes exact
enumeration impractical," but 362,880 permutations run in well under a
second; the 20,000-assignment threshold in the code, not the actual cost of
exact enumeration, is what triggered the random-draw path here). The
frozen, random-20000 result is p = 0.07525. The exact p, over the full
362,880 permutations, is **0.0717** (0.07169...) -- close to, and on the same
side of conventional thresholds as, the reported figure, but not identical
to it. `retrospective/results/R1-result.md`'s "Deviations from the frozen
plan: None" is accurate to what the code actually ran; it is not a claim
that the random-draw p exactly equals the exact p.

**(c) Cirrascale's only counted major/critical incident is a mislabeled
maintenance notice.** In the primary window, Cirrascale's sole incident
counted toward `major_or_critical_incident_count` is titled "Post-Planned
Maintenance Notification -- Cogent Work Order" (started 2026-02-17). It was
filed by Cirrascale as an ordinary incident (`is_maintenance: false`,
`severity: "major"`) -- R1's `is_maintenance` exclusion rule, applied exactly
as specified, correctly does not drop it, and this note is not proposing that
the frozen result be recomputed with it dropped. As a sensitivity check only:
excluding that one incident (Cirrascale's `major_or_critical_incident_count`
1 -> 0, all eight other providers unchanged) changes rho from **0.6378 to
0.5093** (~0.51), widens the bootstrap interval to `[-0.2657, 0.9340]` (now
straddling zero more asymmetrically), and raises the exact permutation p from
0.0717 to **0.1802** (~0.18).

**(d) Leave-one-provider-out rho range.** Dropping each of the nine eligible
providers in turn and recomputing rho on the remaining eight:

| Provider dropped | rho | exact permutation p |
|---|---|---|
| Nebius | 0.5076 | 0.2286 |
| Scaleway | 0.5622 | 0.1631 |
| Sharon AI | 0.5331 | 0.1774 |
| Akamai | 0.6359 | 0.0988 |
| DigitalOcean | 0.6565 | 0.0810 |
| Hyperstack | 0.6565 | 0.0810 |
| latitude.sh | 0.6565 | 0.0810 |
| Lightning AI | 0.6836 | 0.0690 |
| Cirrascale | 0.7965 | 0.0179 |

The leave-one-out rho ranges from **0.51** (dropping Nebius, the
highest-ordinal provider) to **0.80** (dropping Cirrascale, exact p 0.018).
No single provider's removal flips the reading from inconclusive to either
consistent or inconsistent under the frozen bootstrap rule, but the point
estimate itself moves by nearly 0.3 depending on which one provider is left
out of a nine-provider cohort.

**None of (a)-(d) changes the pre-registered reading above: inconclusive.**
Taken together, though, they show that reading sits on a small, sensitive
base -- a different (still legitimate, still pre-specifiable) seed, exact
instead of capped-random permutation enumeration, one relabeled incident, or
the removal of any single one of nine providers each move the numbers by
enough to matter. Treat "inconclusive" as a genuinely unstable read of thin
data, not as a near-miss that a slightly different but equally reasonable
procedure would have called otherwise.
