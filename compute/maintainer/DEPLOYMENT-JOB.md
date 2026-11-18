# Recipient-owned deployment job

This driver joins the existing paired endpoint capture and native application verdict with explicitly bound operational and economic evidence. It does not install or start serving systems. Configure both endpoints, workload, policy and declared identities in a copy of `examples/spec.json`; create `deployment-job.json` from the template and point `comparison.spec` at that file. The native spec remains authoritative for endpoints, workload, inference protocol, identities and acceptance policy.

Run the paired comparison once:

```text
python -B compute/maintainer/job.py run --manifest deployment-job.json --out deployment-run
```

The output directory retains copied data inputs, both raw endpoint receipts, native analysis, deployment decision and input hashes. Validate first without probing endpoints or executing a grader:

```text
python -B compute/maintainer/job.py validate --manifest deployment-job.json
```

Validation reports missing requirements as unknown and never calls a manifest ready for a decision. For workloads with external-grader tasks, attach receipt-bound grades or provide `external_grading` with `execute: true`, a pinned reference/normalizer/contract and limits. Only `run` honors that explicit execution flag, through the shipped bounded Docker grader. Completed jobs preserve the original authorization in `execution-plan.json` and disable future execution in `job.json`; decide/import never execute a grader. An ungraded tool-call trace is not useful-work success.

For `run`, `decide` and `import`, exit codes follow the decision state: 0 selects candidate, 1 keeps baseline, 2 means no eligible arm, incomparable or undetermined, and 3 means incomplete or execution error. Exit 0 is a decision result, not a generic claim that the product is qualified. `export` returns 0 when the bundle is written.

## Operational and resource records

Attach operation JSON paths in each arm's `operations` array and a resource template or binding in `resources`. The job accepts only supported `cantos.operation-binding/1` check ids, binds them to the exact run hash and declared hardware identity, and uses the shipped raw-evidence verifier. Unknown or unsupported checks remain unknown. The binding records operator-declared custody; it is not provider attestation. The pinned local acquisition runs only on an explicitly authorized local host; it does not inspect or control remote endpoints. Declare `audit_host_label` and `audit_host_id_sha256` in the native hardware identity, then collect:

```text
python -B compute/maintainer/job.py collect --manifest deployment-job.json --arm baseline --authorize-local-host HOST_LABEL --out baseline-ops
```

Repeat for candidate, point each arm's `collection` at its `acquisition.json`, then run the paired job. Raw packet, summary and original collection packet are retained and bound to the captured run; unsupported checks remain unknown.

Before capture, resource files may use `cantos.resource-template/1` with declared hardware hash, measured-trials accounting, source-bound scenario assumptions and explicit verification/retry/operator/idle allocations. See [`examples/deployment-resources.json`](examples/deployment-resources.json) and [`examples/deployment-assumptions.txt`](examples/deployment-assumptions.txt); these are hypothetical placeholders, not current provider prices. Replace every value, basis, source and hash with recipient evidence, and replace the hardware hash with SHA-256 of the canonical hardware identity object. The run creates `cantos.resource-binding/1` records bound to exact run hashes and native trial windows. Missing cost categories, allocations, energy scope or source records remain unknown; zero must be an explicit sourced value. Ranges propagate conservatively. Board-only energy cannot establish whole-system energy.

An optional separately labeled retry layer uses top-level `retry: {"required": true, "economics": false}` and per-arm `retry` paths: `campaign` is the retained `retry-campaign.json`, with optional `telemetry`, `scenario` and `allocations`. Campaigns are read-only evidence and never cause replay. Retry identity, acceptance controls, timing and campaign artifacts are checked against the native captured experiment. Retry economics, when explicitly enabled, uses the complete retry campaign window and its accepted-task denominator; native measured-trial costs are not added. A telemetry receipt uses `cantos.retry.telemetry/1`; its `samples` journal and the allocations file are retained and hash checked even when stored outside the campaign directory. The scenario uses `cantos.retry.cost-scenario/1`. The allocations file uses `cantos.retry.allocations/1`, binds the exact `campaign_sha256`, and contains `additional_costs` records with `category` (`verification`, `retry`, `operator`, `idle` or `other`), `unit: "USD"`, `basis`, `source`, `source_sha256`, exactly one of `value` or `range`, and a rationale. Each record sets `includes_in_scenario`; if true, `scenario_fields` must identify already-priced scenario fields and the amount is not added again. Missing allocation categories remain unknown. This layer does not replace the native verdict or issue new inference requests.

Changing policy or source-bound prices can produce a child analysis without new inference, provided each retained arm's observation key still matches. Stage a changed job manifest and all referenced inputs inside the retained job directory, then run:

```text
python -B compute/maintainer/job.py decide --job deployment-run --manifest deployment-run/inputs/reprice/deployment-job.json --out deployment-repriced
```

This creates a new retained child with an explicit parent decision. A changed endpoint, implementation, model, workload or inference protocol fails with `capture_required`; collect a fresh paired run instead. Each child remains separately exportable:

```text
python -B compute/maintainer/job.py export --job deployment-repriced --out deployment-repriced-bundle
python -B compute/maintainer/job.py import --bundle deployment-repriced-bundle --out deployment-import-check
```

Bundles contain data only. Import verifies transport and hashes, revalidates receipts, reruns the native analyzer and deployment join from installed trusted code, and checks the claimed decision identity. It never executes an imported script or grader. Imported post-hoc decisions require their retained parent record.

The frozen vLLM example has 192 captured requests, with 21 of 96 accepted by each arm against an 80% requirement. Its authoritative native verdict is incomparable; no deployment winner or prefix-cache benefit can be inferred. Full-system operational coverage, general-purpose workflow evaluation and complete measured economics remain open until recipient-owned evidence covers them.
