# ClusterMAX 3.0 launch evidence

ClusterMAX 3.0 has been released. Open [the reader view](index.html) or [the source-bound ledger](claims-3.0.observed.json). The ledger covers 17 selected provider assignments; it does not claim complete review of all 77 providers. Exact retrieval hashes are in [source observations](source-observations-20260923.json).

## Observation and scoring are separate

Schema `secondrun.launch-claims.v2` records SUPPLIED, PARTIAL, NOT_IN_REVIEWED_SOURCES and NOT_REVIEWED findings. Partial and unreviewed findings carry explicit limitations and sources. These are limits of this review, not assertions that evidence does not exist. The v1 template and validator remain supported for historical records.

The ledger accepts Participation Ribbon and Unavailable as observations. The unchanged five-tier scorer refuses Participation Ribbon; Unavailable is never converted into Underperforming or a failed job. A new mapping requires a separately identified plan and post-release disclosure. No six-tier probability is invented here.

## Use

```sh
python scripts/launch_ledger.py launch/claims-3.0.observed.json
python scripts/launch_ledger.py launch/claims-3.0.observed.json --plan path/to/plan.json --output binding-draft.json
```

A binding draft requires compatible tiers, sources and rating version. It does not register a study or authenticate external timestamps. Validate the complete submission before relying on a result.

## Chronology

The original instrument was published earlier on release day at `ee650e3`. Consolidated v1.3 (`448e003`) was created locally at 21:16 UTC (self-reported commit time, not an independent clock) and first reached GitHub at 21:27:08 UTC -- after the cited 3.0 article's own recorded `datePublished` of 21:20:29 UTC. Neither code publication establishes a preregistered real customer cohort. This ledger is post-release work. Plans can still prospectively predict future jobs; freeze their design, predictions and mapping before observing those outcomes.

The complete [77-provider transcription](release-3.0/clustermax-3.0.json) and [transition record](release-3.0/transitions.json) remain separate. The inspected article is recorded as methodology_source. The exact 3.0 rubric remains unverified, so this observation ledger cannot emit a real binding yet.
