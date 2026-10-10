# Dedicated capacity: an inspectable reservation decision

A single offline page for anyone weighing a fixed GPU commitment: a reserved node, a monthly allocation, a dedicated cluster. Open `index.html` in a browser. The page makes no network requests; nothing you type leaves it.

## What it does

- **Charges the whole commitment.** The full allocation fee counts whether the hardware is busy or idle. Productive hours never shorten the bill.
- **Keeps unknowns unknown.** Accepted throughput starts unmeasured and produces no estimate. Seven route costs (preparation, validation, operations, recovery, coordination, capture, upkeep) stay unknown until entered; an explicit zero is a different statement from a blank.
- **Shows what utilization does.** Cost per 1,000 accepted results at 25 %, 50 %, 75 % and 100 % productive use of the same commitment.
- **Separates price changes from configuration changes.** A new price recomputes the economics from the same assumed output. A new model, runtime, hardware or acceptance rule needs new evidence; the earlier result stays historical.
- **Reprices one published result without stretching it.** The Run 3 MI300X summary (4,336 accepted of 8,622 scheduled requests, 24 September 2026) can be repriced at any hourly rate. Its count, date, acceptance rule and caveats are preserved, and it says nothing about other hardware.
- **Retains the decision.** Download the decision as a JSON packet with a SHA-256 checksum, or save a copy of the page with your inputs embedded. Reopening either verifies the checksum and recomputes every value.

The starting $10,000 / 720-hour / 8-GPU values are illustrative, not a quotation. Once a saved decision or page is reopened, including a page whose saved-input slot is filled by an embedding view, the note names that scenario instead of describing the starting example.

## Check a decision offline

```sh
node verify.cjs example-decision.json        # full recomputation through the Compute engine
python check_math.py example-decision.json   # independent Python arithmetic
```

Neither checker verifies a signature, an author, a provider quote, measured performance, hardware location or legal jurisdiction. A packet whose inputs are changed consistently and rehashed is simply a different valid scenario.

## Sources and ownership

The page embeds the Compute calculation owner, `compute/engine.cjs`, and the retained summary `hot-aisle/campaign/results/RUN3-RESULTS.md`, both pinned by Git blob identity (`21956dbc…`, `95289238…`). `capacity.cjs` adds the full-commitment scenario projection and calls the engine's `quote` for the charge; caller inputs are labelled as scenarios and never as provider quotes. If either embedded owner changes, `build.py` stops until this view is reviewed and its pins are updated.

## Build and checks

```sh
python -B compute/capacity/build.py
node --test compute/capacity/tests/capacity.test.cjs
python -B compute/capacity/tests/check_reference.py
python -B compute/capacity/tests/browser_check.py <output-directory>
```

The browser journey drives real HTTP and file navigation with Playwright. It runs in the repository's CI workflow, and the Pages release gate holds publication until that workflow passes for the exact sources. Set `CHROMIUM_EXECUTABLE` to use a specific local Chromium.

`QUALIFICATION.json` records where this view came from and what has been checked.
