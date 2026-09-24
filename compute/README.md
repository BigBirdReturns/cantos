# Second Run Compute · release 0.2

**Compare rental allocations, model ownership, price reusable work, and keep the evidence you already produce.**

Open `index.html`. The public application works without an account, installation or application network requests. It includes four provider price snapshots, three economic models, saved decisions, source inspection and a private local-runner connection path. All core calculations run locally. This is a compute decision desk, not a broker or scheduler.

Versions: this release is **0.2.0** (`MANIFEST.json`). The calculation engine `engine.cjs` carries its own version, `Compute.VERSION` (currently 0.1.0); it is stamped into every saved decision and changes only when the arithmetic changes, so bumping it invalidates earlier saved decisions.

## Start

Unzip the kit (`compute-kit.zip`, this desk only). For the offline calculator, open `compute/index.html` in a browser.

To read records published by the **Hot Aisle runner**, which is a separate download (`../hot-aisle/workload-report.zip` next to this desk, or the `hot-aisle/` directory of the combined source), start the runner from its extracted folder, then start this desk's local helper and point it at the runner:

```sh
# from the extracted runner kit
node runner/bin/workload.cjs serve --port 8787
# from the extracted desk kit
node compute/scripts/connect.cjs --port 8765 --runner http://127.0.0.1:8787
```

Open the **private localhost link printed by the helper**. It serves this same page and automatically discovers immutable records published by that runner. Refresh to observe newer results. An explicit stable port preserves the browser origin used for saved decisions across restarts; omit `--port` for an ephemeral port. Stop the helper with Ctrl+C.

The helper requires Node 22 or newer and built-in modules only. It does not install software, run shell commands, call a model, scan hardware, start a benchmark, provision a GPU, pay a bill or change an existing job queue.

Optional configuration:

```sh
node compute/scripts/connect.cjs --port 8765 \
  --results /path/to/approved-results \
  --aperture /path/to/aperture-support.json \
  --endpoint http://127.0.0.1:8000
```

`--aperture` reads an existing `aperture-support/1` receipt. Obtain it separately through Aperture's permissioned scan. `--endpoint` reads `/v1/models` and selected `/metrics` counters from one explicitly configured endpoint. Remote endpoints require HTTPS. `--api-key-env VARIABLE_NAME` uses an existing environment variable; credentials never enter the public page. Prefer an existing SSH tunnel for a remote private runtime rather than exposing it publicly.

## Use from an MCP client

Add a local stdio server in a client that supports the negotiated protocol versions:

```json
{
  "mcpServers": {
    "second-run-compute": {
      "command": "node",
      "args": ["/absolute/path/compute/scripts/connect.cjs", "--mcp", "--results", "/path/to/approved-results"]
    }
  }
}
```

The server implements initialization, tool discovery and calls over newline-delimited JSON-RPC. It negotiates MCP 2025-11-25 or 2025-06-18. The ten read-only tools include `compute_list_publications`, `compute_get_publication`, `compute_list_offers`, `compute_ownership`, `compute_route_scenario`, `compute_plan`, `compute_list_runs`, `compute_get_run`, `compute_hardware`, and `compute_endpoint`. They invoke the same calculations used by the page. This release is **stdio MCP**, not a remote HTTP MCP service or an MCP App iframe.

A client can ask: “Compare one-GPU allocations with at least 80 GB for 160 hours, then prepare a shortlist.” Or: “Read my existing run and model its cost.” Tool calls cannot rent or run compute. Starting new evaluations and enforcing a production route belong to the existing execution owner and require a separately qualified adapter.

## The four views

**Compare compute** filters advertised per-GPU memory, allocation size, provider and reserved hours. The chart plots actual catalog price/memory values, not invented throughput. Every row exposes its source, date, allocation basis, listed tier where a provider has several, and terms. Shortlist up to four options and save a decision. In that saved decision, repricing creates a new version linked to the old checksum. Filters and the shortlist are remembered in this browser so a return visit starts where the last one ended. Arriving from the workload report with `?from=hot-aisle&memory=192` presets the memory floor and shortlists the MI300X and H100 comparison.

**Own vs rent** includes purchase cost, residual value, horizon, whole-system load and idle energy, and ongoing costs. Without measured rates it compares reserved time, not equal output. Supplying both rates scales the rental hours needed for the same declared work. Capacity and quality still require qualification. Cash payback uses purchase price against monthly rental-cost avoidance after operating cost; it is not a resale or investment-return forecast.

**Reuse routine work** models reusable procedures, smaller-model work and retained premium work. The calculation counts failed first attempts, premium fallback, per-request verification and initial qualification cost. It distinguishes requests moved from premium GPU time saved. Model inputs are scenarios, and saved routes remain proposals. It does not infer that a whole physical GPU becomes available.

**Your results** shows runs and records read from the local Hot Aisle runner through the helper, or exposes them to an agent through MCP. Until a runner is connected, a synthetic sample (marked everywhere) shows what an observed run looks like. Supported benchmark files are normalized using the exact retained v2 workload-report engine. Imports are a fallback for disconnected use. Saved decisions persist locally only after a save, up to 12; an entry that no longer verifies is kept and marked "needs re-verification" rather than dropped, and the stored list is never overwritten with fewer entries than were read unless you clear it. Raw benchmark inputs remain in memory. Original approved files remain the durable source on disk.

The mature vLLM comparison utility is preserved byte-for-byte in `adapters/workload-report-v2.html` as an advanced fallback. Its historical source/kit links retain their original scope. Its same-model comparison and joint acceptance gates are not replaced by a priceboard or a weaker-model routing scenario.

## Verify and maintain

```sh
node --test compute/tests/test_core.cjs compute/tests/test_bridge.cjs
python -m unittest discover -s compute/tests -p 'test_prices.py' -v
python compute/scripts/build.py
# Test-only dependency; the shipped app and helper have no package dependencies.
python -m pip install playwright==1.57.0
python -m playwright install chromium
python compute/tests/test_browser.py --require-navigation
node compute/scripts/recompute.cjs compute-decision.json
```

`engine.cjs` is the economic authority. `adapters/workload-engine.cjs` and `adapters/qualified-engine.cjs` are generated copies of the Hot Aisle engine and runner libraries (`integration/build.py` in the combined source); edit the originals, not the copies. The page inlines all of them. Sources, tests and bridge remain inside this tool directory; it imports no sibling tool at runtime. `scripts/build.py` generates the single page, manifest and offline ZIP from current source, including the review date and price-schedule options shown in the page, which come from `data/catalog.json`. Do not edit the generated page as the source of truth.

Continuous integration for this directory runs from `.github/workflows/hot-aisle-ci.yml` in the combined repository (source, API/MCP and native-navigation browser tests, then a fresh build that must match the committed artifacts). Publishing the `compute/` directory to any static host is sufficient for the public page; private connections continue to run locally.

## Price upkeep

`data/catalog.json` owns provider observations and effective-date schedules. The current snapshot was reviewed on 22 September 2026. The UI flags it after 30 days. Runpod rows carry `tier: "Secure Cloud"`; the same source page lists Community Cloud rates roughly 30-45% lower, which this catalog does not model. Check `scripts/review_prices.py --help` for a bounded public-source drift review. It produces source hashes and token-level discrepancy receipts and fails when it cannot establish the expected tokens. **It never upgrades token presence to a verified quote or renews the review date automatically.** A maintainer approves changed prices, availability assumptions and effective dates. The live source parsers have not been qualified against every provider delivery environment.

## Privacy and security

The public page sends no application telemetry. Explicit saves, remembered filters and the theme choice use browser storage on this origin only. Shareable decision exports contain the supplied scenario and dated catalog; they grant no authority. Normalized run exports omit generated text, prompts, original filenames, raw error bodies and unrecognized metadata. Selected model names and timestamps can still identify work.

The helper binds loopback, checks the Host and Origin, rejects writes, requires a per-process bearer token for data, excludes symlinks and limits directory/file sizes. Tokens travel in a local URL fragment and are removed from the address after connection. Use a trusted local machine: these controls are not tenant authentication for an internet-exposed service. No provider key is bundled. A checksum supports exact recomputation, not source authenticity.

See `METHOD.md`, `PROVENANCE.json` and `QUALIFICATION.json` for the calculation boundary, donor identities and test scope. All source files are steward-owned; no workflow silently overwrites customer records. The wider execution fabric, public contribution registry, billing settlement and automated policy promotion remain separate development work.

## Integrated qualification records

The Hot Aisle runner owns measured-result arithmetic and qualification. The desk consumes its qualified record and sealed packet through a generated verifier, preserving the exact original object in saved decisions. `integration/README.md` in the combined source explains ownership, local publication, one catalogue and native browser qualification. Scenario arithmetic remains in the desk; source-bound workload findings remain in the runner.

## Community beta, 24 September 2026

Open [the results board](results.html) to search the source-bound campaign results and retained TierBench observations, compare a structured claim, and export a decision carrying its evidence. The board is a view of this product, not a new execution owner. Its historical summaries preserve source-reported, estimated and upper-bound cost bases; the three native campaign paths delegate outcomes and economics to the existing report engine. No summary becomes an independently reproduced run.

[community/README.md](community/README.md) explains the safe contribution preview, explicit public submission, reviewed local admission and independently operable hubs. [community-kit.zip](community-kit.zip) includes the board, source, verifier, records and current calculator page. The older compute-kit.zip continues to package the calculator and private read-only helper; use the community kit for the board. Runtime execution remains with the existing approved runner.

Native qualification: node compute/community/tests/browser.cjs (pinned Playwright is a test-only dependency). It exercises actual localhost services, exported evidence and decisions in another process, public-preview consent invalidation, and a second-generation hub after its first origin is stopped. Those isolated test operators are software fixtures, not evidence of outside adoption. Public sharing never occurs automatically.
