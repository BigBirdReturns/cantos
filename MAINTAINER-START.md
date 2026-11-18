# Review a retained serving change

Start the local workbench from the extracted `cantos` directory:

```sh
python -B open-compute-ledger/run.py --open
```

Choose **Review a serving change → Open the real vLLM experiment**. This frozen example makes zero inference requests. Its native verdict is **incomparable**: baseline and candidate each accepted 21 of 96 requests; the 80% requirement needs at least 77. The instrument correctly refuses to call this a passing change or rank a winner.

To package an analyzed comparison for the workbench, run this from the extracted `cantos` directory:

```sh
python -B compute/maintainer/maintainer.py export-comparison --analysis YOUR_ANALYSIS --out comparison.zip
```

In the workbench, choose **Review a serving change → Import comparison** and select `comparison.zip`. The displayed native verdict, exact policy, observations and evidence identity travel with the analysis. The workbench does not rerun the model or replace the instrument verdict.

The original evidence ZIP remains the source record. Editing policy in the workbench creates a visibly labeled **post-hoc analysis** linked to its parent and original. It reuses the captured responses and existing application grades with zero new inference requests. A changed acceptance rule can change which tasks qualify, but it cannot alter captured responses or their grades. Export the revised decision as **Analysis JSON**; the **Original evidence ZIP** remains unchanged. Keep both with the retained history.

The Catalog comparison tab is a separate, scoped screening workflow for retained workloads or published model/price cohorts. It does not create a universal model ranking. The older packet exporter below remains available when a recipient needs the legacy catalog-decision path.

## Run a new maintainer comparison

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
