# Cantos / Second Run: run the Chapek example

This example continues an existing piece of work: a customer-fit recommendation, its capacity assumptions, the results behind it, and the next executable steps. Cantos keeps the working record; Second Run runs the supported procedures.

## Read and change the work

Open the [working example](https://bigbirdreturns.github.io/cantos/compute/chapek/) or open `Cantos-Chapek-Seat.html` from the extracted package. The first screen shows the recommendation, changed inputs, completed work and open decisions. Use **Prospect** to enter an example of your own, **Server** to change the allocation assumptions, and **Save a copy** to keep your work in an offline file.

**Work performed** connects each result to its inputs, procedure and execution history. The case uses dated Chapek list prices, historical compute results and a labelled synthetic workload for the model-change demonstration. The proposed Chapek connection belongs alongside AI Studio, through the customer's existing provisioning, endpoints and access controls.

## Run the package

[Download the package](https://bigbirdreturns.github.io/cantos/compute/chapek/Cantos-Chapek-Seat-package.zip), extract it and open a terminal in the extracted `package` directory. For replay of the shipped bindings, use **Python 3.13.15 and Node 24.19.0**. These runtime versions participate in the computation identities.

Acquire the reference code in a new sibling directory:

```sh
git -c core.autocrlf=false clone https://github.com/BigBirdReturns/cantos ../cantos-code
git -C ../cantos-code checkout 34803a104a9e1025cf3a89c632617c2966d19c3f
python next.py --checkout ../cantos-code --store store
```

The next action contains four tasks. With the delivered result store, all four reuse checked results. To repeat the same work from an empty result store:

```sh
python next.py --checkout ../cantos-code --store fresh-results
```

Three computations execute; the record-bound reprice reuses the calculation just produced. To run all eight procedures through their records:

```sh
python next.py --checkout ../cantos-code --request requests/09-verify-all-procedures.json
```

Each run prints its outcome and the location of the new receipt. The package includes the working record, its inputs, requests, results and earlier receipts. The reference checkout supplies the procedures and the retained Run 3 source.

## Reading a result

**Executed** means the procedure ran. **Reused** means a verified result matched the declared computation. **Held** names the condition that needs attention, such as missing input, changed code or an outdated record revision. Direct tasks can recompute under changed conditions; record-bound tasks require a matching recorded basis. The procedure's result separately states any outstanding business decision or proposed measurement.

## Explore the general runner

From any supported Cantos checkout with Python 3.12+ and Node 22+:

```sh
python -B integration/work.py --request integration/examples/work.json --store .cantos-example-results
```

An empty store executes six tasks; a repeat reuses six results. This establishes results for that local environment. The [operation reference](../../integration/WORK.md) gives the task classes, input formats and change handling.

Jonathan Sandhu · Sandhu Consulting Group · bigbirdreturns@proton.me
