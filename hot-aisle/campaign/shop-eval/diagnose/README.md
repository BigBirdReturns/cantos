# Shop diagnosis

This standard-library Python tool summarizes observed compute-shop evidence against dated Hot Aisle observations. It does not identify hidden host or tenant causes from customer-side symptoms. Missing or unavailable fields are `UNKNOWN`, not failures. Heuristic readings appear as `SIGNAL` and cannot independently support a provider-quality verdict.

## Inputs

| Flag | Input |
|---|---|
| `--counter` | `second-run/counter-record@1` record |
| `--fingerprint` | `second-run/shop-fingerprint@1` customer-visible capture |
| `--bench` | scored `engine_table.cjs` JSON, or raw `cell-*.json` files |
| `--reference` | reference bundle (default: `reference/hotaisle-2026-09.json`) |
| `--scope` | JSON describing workload, acceptance, cost window, complete configuration, evidence, and SHA-256 of the scored table |
| `--reference-scope-id` | reference scope key from the bundle (`run1-cell-c64`, `run3-own-window`, or `run3-whole-seat`) |

All inputs can be omitted. Without verified candidate and reference scopes, the report explicitly refuses an economic ratio. Scope identity includes model and tokenizer revisions, precision, cache policy, workload/load profile, acceptance rule, cost scope, table gates/rate, and configuration identity. An unobserved field or mismatched acceptance/cost window fails closed. Different complete configurations may support a same-workload economic comparison, but do not establish operator causality.

```text
python diagnose.py --counter <file> --fingerprint <file> --bench <table.json> \
  --scope <scope.json> --reference-scope-id run3-own-window \
  --reference reference/hotaisle-2026-09.json --out REPORT.md --json
```

The shipped Run 1 table uses a latency-only acceptance rule with no correctness sidecar, while Run 3 uses EvalPlus grading and a different arrival trace. They are distinct scopes. Run 1's serving backend is not established. Run 3 explicitly disables prefix caching, but its broader cache warm/cold state is unobserved. Their price fields remain observations, while automatic comparison needs complete scope evidence. Never use a composite counter score as a quality verdict.

## Files

- `RUBRIC.md` documents evidence meanings, limits, and rule behavior.
- `reference/hotaisle-2026-09.json` keeps cost views distinct and cites source evidence for each scope.
- `diagnose.py` emits Markdown and optional structured JSON. Findings include cause-discriminating tests, bounded changes, acceptance, rollback, and access for WRONG results.
- `fixtures/` contains synthetic inputs only. It is not provider evidence.
- Run checks with `python -B test_diagnose.py` from this directory.
