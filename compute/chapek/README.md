# Cantos for Chapek

AI workflow software for continuing work across engineers, models and infrastructure. Cantos connects a job's inputs, decisions and results to reusable procedures. Second Run is its execution-and-reuse capability.

[Open the working example](https://bigbirdreturns.github.io/cantos/compute/chapek/) · [Download the runnable package](https://bigbirdreturns.github.io/cantos/compute/chapek/Cantos-Chapek-Seat-package.zip) · [Run instructions](START.md)

## Continue a customer operation

Carry requirements and configuration decisions from onboarding into deployment and support. A replacement engineer inherits the basis for the work. A model, workload or commercial change identifies the affected decisions and procedures. The customer keeps the working record and the runnable handover.

The Chapek example uses our own research, dated public pricing, historical compute results and a labelled synthetic workload. It contains five retained execution runs and eight current procedures. Price changes update calculations; a model change produces a revalidation plan; a runner change produces new bindings with the earlier history preserved.

## Use the example

The first screen shows the recommendation, changed inputs, completed work and remaining decisions. **Prospect** records a customer's requirements. **Server** evaluates capacity assumptions, with monthly and annual terms identified. **Work performed** exposes the procedures, results and execution history. **Keep & share** exports the current work for another operator.

The browser runs the record rules and capacity calculations locally. The downloaded package runs the retained procedures using Python and Node. [START.md](START.md) gives the reference code, qualified replay environment, commands and expected outcomes.

## Proposed Chapek integration

Connect the supported operations to existing provisioning, model endpoints and access controls. AI Studio retains model serving and tenant authentication; the customer retains its authoritative sources and decisions. One existing workflow supplies the initial integration case.

## Implementation

ResearchCore owns revisions, dependency checks, reviews and portable records. The Compute engine owns capacity arithmetic. The native runner owns procedure execution and checked reuse. Source formats and operation contracts are in [integration/WORK.md](../../integration/WORK.md).

For maintainers:

```sh
node compute/chapek/check.cjs
python -B compute/chapek/tests/package_check.py
python -B compute/chapek/tests/browser_check.py
```

The checks bind the page, package and supported browser journey to this source tree. Recorded evidence remains attached to its original inputs and conditions.

Jonathan Sandhu · Sandhu Consulting Group · bigbirdreturns@proton.me
