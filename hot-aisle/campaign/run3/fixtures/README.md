# Synthetic offline fixtures

The five tiny tasks are authored test fixtures, not copied EvalPlus tasks.
The CODE-shaped slice is synthetic and tests timestamp parsing, ties, boundaries and scaling; it is not an observed Azure slice. Production must use the source file and verified SHA in SOURCES.md. Fixture task IDs are deliberately isolated by synthetic=true. serve-amd.log is a synthetic selection/override parser case. No fixture establishes model quality, GPU performance or upstream dataset-byte verification.
