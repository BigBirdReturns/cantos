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

## Count retries and accepted work

The [real-model retry qualification](compute/maintainer/RETRY-QUALIFICATION.md) retains 22 actual requests, complete grades and 978 board power samples in an offline-verifiable archive.

[Retry campaigns](compute/maintainer/RETRY.md) run bounded solution attempts with durable dispatch journals, source-bound acceptance, first-pass success, and complete retry and elapsed-time accounting. [Resource accounting](compute/maintainer/RETRY-RESOURCES.md) joins the exact campaign to measured power evidence and separately sourced cost assumptions. Configure the declared retry policy before collecting a new campaign.

```sh
python -B compute/maintainer/retry.py --help
python -B compute/maintainer/retry_resources.py --help
```

These commands produce their own campaign and resource receipts. The baseline/candidate comparison, SecondRun operations, and workbench packet export below retain their existing contracts.

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
