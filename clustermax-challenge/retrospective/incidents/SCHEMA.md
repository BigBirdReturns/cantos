# Incidents schema: `secondrun.status-incidents.v1`

One file per provider, named `retrospective/incidents/<provider-slug>.json`. This is
the normalized, provider-neutral record that `scripts/retrospective.py` reads to
compute R1's outcome measures. It is produced by `scripts/collect_status.py` (or,
for status pages that resist automated parsing, hand-assembled and checked against
this schema) from a provider's own public status page.

## Fields

```
{
  "provider": "string, human-readable provider name as used on their status page",
  "status_page_url": "string, base URL of the status page",
  "retrieved_utc": "RFC3339 UTC timestamp, when this file's data was captured",
  "raw_files": [
    {"path": "retrospective/incidents/raw/<slug>/<file>", "sha256": "<64 hex>", "url": "source URL, if fetched"}
  ],
  "coverage_start": "YYYY-MM-DD, earliest date the history in this file demonstrably covers",
  "coverage_end": "YYYY-MM-DD, latest date the history in this file demonstrably covers",
  "severity_map": {
    "<provider's own impact/severity label, verbatim>": "critical|major|minor|none"
  },
  "incidents": [
    {
      "id": "string, stable identifier from the provider (their incident id/slug)",
      "title": "string",
      "impact_label": "string, the provider's own label before normalization (a key in severity_map)",
      "severity": "critical|major|minor|none, the normalized value (severity_map[impact_label])",
      "started_utc": "RFC3339 UTC timestamp",
      "resolved_utc": "RFC3339 UTC timestamp, or null if still open as of retrieved_utc",
      "is_maintenance": true or false,
      "url": "string, link to the incident's detail page"
    }
  ]
}
```

## Field notes

- **`coverage_start` / `coverage_end` are a claim, not a courtesy field.** R1's
  eligibility rule (`PLAN.md`) requires `coverage_start <= window_start` and
  `coverage_end >= window_end` for a provider to be included. Only set
  `coverage_start` to a date you can actually justify: either you paginated the
  provider's history all the way back to their platform's start (a 404/empty page,
  or an explicit "no incidents reported" month), or they published an explicit
  archive boundary. **If pagination stopped because the provider's API/UI only
  exposes a rolling recent window (see the Lambda smoke-test note below), leave
  `coverage_start` null rather than inferring it from the oldest incident found** —
  the oldest incident returned by a capped API is not evidence that nothing older
  exists. `retrospective.py` treats a missing `coverage_start` or `coverage_end` as
  "not eligible, pending manual verification," not as a crash.
- **`severity_map` records the normalization decision, not just a lookup table.**
  Keep every distinct raw label you observed for this provider, even ones that map
  to `"none"` (e.g. an informational or resolved-without-impact label), so an
  auditor can see exactly what was collapsed into what. `incidents[].severity` is
  always the already-normalized value; `retrospective.py` trusts it directly and
  does not re-derive it from `severity_map` at analysis time — `severity_map` is
  the audit trail for how `collect_status.py` (or a human) got there.
- **`is_maintenance`** covers scheduled/planned maintenance windows, however the
  provider marks them (a separate "scheduled maintenance" feed, a component type,
  or a title/label heuristic). PLAN.md excludes these from both outcome measures.
- **`resolved_utc: null`** means still open as of `retrieved_utc`. R1 counts these
  incidents' duration up to the window end and flags the result
  (`incident_hours_capped` in `R1-result.json`) rather than dropping them.
- **`raw_files`** must list every fetched artifact this normalization is built
  from, each with its own SHA-256, so the whole chain from "what the provider's
  page said" to "what R1 counted" is independently checkable.
- Provider **names in the ratings files do not have to match `<provider-slug>`
  exactly** — `retrospective/provider_map.json` (optional) maps a rating's display
  name to the incidents-file slug when they differ.
