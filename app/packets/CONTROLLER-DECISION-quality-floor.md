# Controller decision: quality_floor for the Run 3 hardware policy · 2026-09-29 06:30 UTC

Clause 3 of BRIEF.md carried `quality_floor: .5`, copied from the invoice fixture. Opus and Sol both found that N/T0 accepts 4,280 / 8,622 = 0.4964, so at .5 the H100 arm is ineligible under the owner's existing rule (core 1.0.1 L79) and the $2.49/h rate change cannot flip the decision. Run 3's PREREG.md (lines 95-115) has no acceptance-rate floor; its gates are a complete hour, no holds, failed transport <= 1%.

Decision: the Run 3 policy uses `quality_floor: 0`, and its summary says so in one line: "No acceptance-rate floor; Run 3 preregistered gates were a complete hour, no holds, transport failures under 1% (PREREG.md L95-115)." The owner's eligibility rule is left unchanged. No packet or page claims a floor that the run did not have. The flip at $2.49/h then follows from the retained measurements: N/T0 $0.677 vs A/T0 $0.744 per 1,000 accepted.

Applies to: Sol's packets (rebuild with floor 0 if built at .5), Astra's regressions (assert the flip), Fable's integration.
