# Run a maintainer comparison

This kit contains Cantos's streamed baseline/candidate instrument and the SecondRun adapters that execute and retain its observations and analysis. It uses Python 3.10 or later and the standard library. Start in the extracted `cantos` directory.

Read [the instrument guide](compute/maintainer/README.md) to configure your explicit serving endpoints, model and implementation identities, workload, intended change and comparison policy. Existing serving processes remain under their operator's control. The example specification is a template; replace its configuration with the actual tested systems.

```sh
python -B compute/maintainer/maintainer.py --help
python -B compute/maintainer/maintainer.py run --spec YOUR_SPEC.json --out new-comparison
```

The result retains raw observations, a readable report and a machine verdict. The guide defines supported workload evaluators, external grading, streaming metrics and pass/regression/incomparable/error conditions.

Use [SecondRun's maintainer workflow](integration/WORK.md) to retain each observation separately, reuse unchanged evidence, update analysis after a price or policy change, and obtain fresh observations when serving inputs change. Configure the example request to reference your specification and policy.

```sh
python -B integration/work.py --catalog
python -B integration/work.py --request integration/examples/maintainer-work.json --store results --require-maintainer-pass
```

An explicit `--fresh` invocation requests new observations. Retained observations keep their original timestamps and raw evidence. Other SecondRun operations described by the full guide require the complete Cantos source checkout; the compact kit includes the maintainer operations and their dependencies.

`MAINTAINER-MANIFEST.json` records every included file and its hash. The public download's SHA-256 receipt identifies the ZIP. [DELIVERY.md](DELIVERY.md) and [DELIVERY.json](DELIVERY.json) preserve the complete product goal and current scope. Automated fixture tests qualify software behavior; representative live measurements retain their separately stated workload, hardware and observation conditions.
