# shop-eval / diagnose

Diagnoses a GPU compute shop against Hot Aisle as the reference operator: what it's
doing wrong, right, and could do better, across nine layers (counter score, site/power,
hardware lifecycle, known-good stack, fleet automation, health/availability, tenant
hygiene, pricing/capacity, public proof).

## Inputs (all optional)

| Flag | Shape | Produced by |
|---|---|---|
| `--counter` | `second-run/counter-record@1` | `../counter/counter_record.py score` |
| `--fingerprint` | `second-run/shop-fingerprint@1` | a shop-fingerprint collector |
| `--bench` | `engine_table.cjs` JSON table, or a dir of raw `cell-*.json` (or a `table.json` inside one) | `node ../engine_table.cjs ...` |
| `--reference` | reference bundle (default: shipped `reference/hotaisle-2026-09.json`) | this kit |

Every input is optional. A missing input produces, per layer, a note explaining what to
run to get it, instead of a crash. Full field lists and the reasoning behind every rule
are in `RUBRIC.md`.

## Run it

```
python diagnose.py --counter <file> --fingerprint <file> --bench <table.json or cells dir> \
    --reference reference/hotaisle-2026-09.json --out REPORT.md --json
```

`REPORT.md` gets a one-line verdict (×Hot Aisle on $/1k accepted, if `--bench` and
`--reference` both resolve), then per-layer WRONG / RIGHT / COULD-DO-BETTER findings
with the observation that triggered each one, a ranked "first three things to change"
with expected effect, and a provenance block. `--json` additionally writes
`REPORT.json` (same stem) with the same data structured for programmatic use.

## Files

- `RUBRIC.md` — the full rubric: every rule id, its layer, the observation it reads,
  what WRONG/RIGHT/COULD-DO-BETTER look like, and the impact-ranking weights.
- `reference/hotaisle-2026-09.json` — Hot Aisle's own numbers, assembled only from
  what's actually in this repo's results files; every field cites its source, and
  anything not present in those files is the literal string `"unobserved"`.
- `diagnose.py` — the tool. Python 3.9+, standard library only.
- `fixtures/` — a synthetic bad-shop (counter record, fingerprint, bench cells)
  built to fail every rule at least once. See `fixtures/SYNTHETIC.md`.
- `test_diagnose.py` — `python -B test_diagnose.py`. Runs the fixtures through
  `diagnose.py` and checks every rule id fires; runs with all inputs missing and
  checks the report is still usable; re-reads the reference bundle's cited source
  files and checks the numbers still match.

## Path/shape contract with the other lanes

This lane was built without waiting for `../counter/` or the fingerprint collector to
exist. The shapes above are what this lane agrees to read; if the counter or
fingerprint lanes land with a different shape, update the loaders in `diagnose.py`
(`load_counter`, `load_fingerprint`) and the field references in `RUBRIC.md` rather
than changing the on-disk paths.
