# Run a maintainer comparison

This kit contains Cantos's streamed baseline/candidate instrument and the SecondRun adapters that execute and retain its observations and analysis. It uses Python 3.10 or later and the standard library. Start in the extracted `cantos` directory.

Read [the instrument guide](compute/maintainer/README.md) to configure your explicit serving endpoints, model and implementation identities, workload, intended change and comparison policy. Existing serving processes remain under their operator's control. The example specification is a template; replace its configuration with the actual tested systems.

```sh
python -B compute/maintainer/maintainer.py --help
python -B compute/maintainer/maintainer.py run --spec YOUR_SPEC.json --out new-comparison
```

The kit includes the existing `grade.sh --build-image` branch and `grader.Dockerfile` used by the [EvalPlus bridge](compute/maintainer/EVALPLUS-BRIDGE.md). That construction step requires Docker and a pinned Python 3.11 CPU base image; other historical Run3 grading commands require the full source checkout.

The result retains raw observations, a readable report and a machine verdict. The guide defines supported workload evaluators, external grading, streaming metrics and pass/regression/incomparable/error conditions. Use one [explicit grading contract](compute/maintainer/EVALPLUS-BRIDGE.md#regrade-an-unchanged-capture-with-a-new-pinned-grader) to analyze revised grades for both retained arms. SecondRun reuses the captures and records the new analysis alongside the original result.

Use [SecondRun's maintainer workflow](integration/WORK.md) to retain each observation separately, reuse unchanged evidence, update analysis after a price or policy change, and obtain fresh observations when serving inputs change. Configure the example request to reference your specification and policy.

```sh
python -B integration/work.py --catalog
python -B integration/work.py --request integration/examples/maintainer-work.json --store results --require-maintainer-pass
```

An explicit `--fresh` invocation requests new observations. Retained observations keep their original timestamps and raw evidence. Other SecondRun operations described by the full guide require the complete Cantos source checkout; the compact kit includes the maintainer operations and their dependencies.

`MAINTAINER-MANIFEST.json` records every included file and its hash. The public download's SHA-256 receipt identifies the ZIP. [DELIVERY.md](DELIVERY.md) and [DELIVERY.json](DELIVERY.json) preserve the complete product goal and current scope. Automated fixture tests qualify software behavior; representative live measurements retain their separately stated workload, hardware and observation conditions.

## Retain the comparison as a deployment decision

After collection and any independent grading, run the documented `analyze` command. It exports validated native OCL receipts alongside the verdict. Then export workbench packets using the exact decision engine included in this kit:

```sh
python -B compute/maintainer/maintainer.py export-packets --analysis YOUR_ANALYSIS --bundle public/open-compute/open-compute-workbench.zip --out new-packets
```

The export verifies both imports in the existing workbench, records a decision under the retained acceptance requirement and saves its history. Open that exact retained store from the same kit directory:

```sh
python -B new-packets/workbench-owner/cantos/open-compute-ledger/run.py --store new-packets/workbench-verification-store --open
```

Open **History** to inspect the preserved decision, original requirement, source observations and outcome. This command uses the verified owner already extracted by the packet export.

For a separate operator workspace, `new-packets/baseline/packet.json` and `candidate/packet.json` can also be opened under **Collect & import**. That imports evidence; explicitly choose requirements for the new decision. Keep each exported packet together with its evidence directory.

Unspecified costs remain unknown. `--policy-prices-usd` explicitly declares that policy hourly assumptions are modeled USD amounts; the underlying measured acceptance remains unchanged. A price change leaves a failed quality requirement unresolved.

## Inspect the retained live application evidence

The included [qualification and raw archive](compute/maintainer/QUALIFICATION.md) record 192 actual vLLM streaming requests, independent application grades, failed qualification, scoped energy and an unavailable-endpoint attempt. Reproduce the evidence-to-decision path without inference:

```sh
python -B app/tests/check_maintainer_evidence.py
```

The expected application verdict is `incomparable`: each arm accepted 21 of 96 observations against its original 80% requirement. Successful verification means those observations, grades, unknown costs and refusal survive the entire delivered workflow.

### Offline AWS CUR resource-cost attribution

The extracted recipient can run the AWS legacy Cost and Usage Report audit with:
    python -m compute.maintainer.provider_cur --cur PATH --cur-sha256 SHA256 --sessions PATH --sessions-sha256 SHA256 --receipt NEW_PATH

Use an operator-supplied UTF-8 legacy CUR CSV with resource IDs enabled and externally retained SHA-256. The session JSON schema is cantos.aws-cur-resource-sessions/1 with 1 to 64 entries containing session_id, 12-digit account_id, resource_id, UTC start_utc/end_utc and observation_sha256 for separately held resource-session evidence. The executable attributes only USD Usage line items wholly inside one session. It retains unmatched rows, fee/discount types and incomplete intervals without prorating charges or inventing a provider rate. The exclusive receipt contains source digests, exact decimal arithmetic and allocation holds. Source pins establish file identity, not AWS provenance, complete billing, application acceptance or whole-system costs. No AWS account connection or charges are required.

### Source-bound provider spend per accepted attempt (qualified subset)

Run `python -m compute.maintainer.provider_cost_join --cur CUR.csv --cur-sha256 SHA256 --sessions resource-sessions.json --sessions-sha256 SHA256 --bindings arm-bindings.json --bindings-sha256 SHA256 --campaign EXTRACTED_PINNED_CAMPAIGN --receipt new-receipt.json`. Bindings must use `cantos.aws-cur-accepted-work-bindings/1`, with the exact SHA-256 of the campaign's `VLLM-EMPIRICAL-RECEIPT.json` and exactly one distinct resource session per baseline/candidate arm. Each declared resource session must pin that same campaign receipt. The auditor independently replays external grader mapping and source-bound GPU telemetry, recomputes CUR attribution, and issues an exclusive durable receipt. It reports only the attributed unblended Usage *subset* per independently accepted attempt; operator resource ownership, export authenticity, invoice completeness, fees, credits and whole-system economics remain unverified.
