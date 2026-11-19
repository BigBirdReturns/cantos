# Source-bound coding failure diagnosis

The native `diagnose_grades.py` command joins two retained HTTP capture journals, external application grades, grader mappings and exact EvalPlus solution status records. It rejects changed source hashes, broken run/workload bindings, relabeled capture or task identities, response hashes that do not match captured response bytes, and grade promotions unsupported by the external evaluator.

Run from a Cantos checkout with a complete retained campaign directory:

```sh
python3 -m compute.maintainer.diagnose_grades /path/to/retained-campaign --output /path/to/coding-diagnosis.json
python3 -m unittest compute.maintainer.tests.test_diagnose_grades
```

The campaign must contain `VLLM-EMPIRICAL-RECEIPT.json`, `vllm-capture/{baseline,candidate}/run.json`, `grade-{baseline,candidate}/grades.json` and the retained grader artifacts referenced by each grade manifest. Its receipt pins the run and grade files; each grade file pins its subordinate mapping and evaluator artifacts. Rewriting all evidence and manifests together is outside the tool's authenticity claims; independent custody of the original receipt remains necessary.

The output records base-test/plus-test failure categories, per-task trial consistency, cross-arm response identity, source SHA-256 values and acceptance differences. It deliberately excludes solutions, prompts and raw response text. The audit analyzes already captured real model outputs and **does not** create new inference, prove a general agentic benchmark, verify provider SLAs or infer whole-system operating costs. A matching pairing declaration is recorded, while the separate native comparator still owns full acceptance and CI comparability checks.


## Paired useful-work accounting

The diagnosis also reports a source-bound 2-by-2 acceptance contingency over identical task/trial/repetition keys: both accepted, baseline-only accepted, candidate-only accepted, and neither accepted. The directional counts expose task swaps even when aggregate acceptance is identical. A separate task-level sign diagnostic groups all repeated trials under their task ID, counts which arm accepted more per task, and reports a two-sided exact conditional sign probability over non-tied tasks. The probability describes a symmetry null under independent, exchangeable task units; it is not a generalization bound, model ranking, randomized intervention effect, or evidence that trial repetitions are independent. The original receipts, grader decisions, and workload hashes remain authoritative; no new inference or grades are generated.
