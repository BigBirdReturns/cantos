# Second Run Compute · 0.2 integration candidate

**Compare rental allocations, model ownership, price reusable work, and connect the evidence you already produce.**

Open `index.html`. The public application works without an account, installation or application network requests. It includes four provider price snapshots, three economic models, saved decisions, source inspection and a private-workspace connection path. All core calculations run locally. This is a compute decision desk, not a broker or scheduler.

## Start

Unzip the kit. For the offline calculator, open `compute/index.html` in a browser. To consume explicitly published qualification records, start the instrument and connect the desk:

```sh
node hot-aisle/runner/bin/workload.cjs serve --port 8787
node compute/scripts/connect.cjs --port 8765 --runner http://127.0.0.1:8787
```

Open the **private localhost link printed by the helper**. It serves this same page and automatically discovers immutable records published by that instrument. Refresh to observe newer results. An explicit stable port preserves the browser origin used for saved decisions across restarts; omit `--port` for an ephemeral port. Stop the helper with Ctrl+C.

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

**Compare compute** filters advertised per-GPU memory, allocation size, provider and reserved hours. The chart plots actual catalog price/memory values, not invented throughput. Every row exposes its source, date, allocation basis and terms. Shortlist up to four options and save a decision. In that saved decision, repricing creates a new version linked to the old checksum.

**Own vs rent** includes purchase cost, residual value, horizon, whole-system load and idle energy, and ongoing costs. Without measured rates it compares reserved time, not equal output. Supplying both rates scales the rental hours needed for the same declared work. Capacity and quality still require qualification. Cash payback uses purchase price against monthly rental-cost avoidance after operating cost; it is not a resale or investment-return forecast.

**The second run** models reusable procedures, smaller-model work and retained premium work. The calculation counts failed first attempts, premium fallback, per-request verification and initial qualification cost. It distinguishes requests moved from premium GPU time saved. Model inputs are scenarios, and saved routes remain proposals. It does not infer that a whole physical GPU becomes available.

**My workspace** discovers authorized results through the local helper or exposes them to an agent through MCP. Supported benchmark files are normalized using the exact retained v2 workload-report engine. Imports are a fallback for disconnected use. Synthetic examples are marked everywhere. Saved decisions persist locally only after a save; raw benchmark inputs remain in memory. Original approved files remain the durable source on disk.

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

`engine.cjs` is the economic authority. `adapters/workload-engine.cjs` is a pinned, credited copy of the existing workload-normalization engine. The page inlines both. Sources, tests and bridge remain inside this tool directory; it imports no sibling tool at runtime. `scripts/build.py` generates the single page, manifest and offline ZIP from current source. Do not edit the generated page as the source of truth.

Install `ci/compute-ci.yml` under `.github/workflows/` in a repository with this `compute/` directory. It runs source, API/MCP and **native-navigation browser tests**, then builds a fresh artifact. The optional price-review workflow is a maintainer template, not an activated schedule in this kit. Publishing the `compute/` directory to any static host is sufficient for the public page; private connections continue to run locally.

## Price upkeep

`data/catalog.json` owns provider observations and effective-date schedules. The current snapshot was reviewed on 22 September 2026. The UI flags it after 30 days. Check `scripts/review_prices.py --help` for a bounded public-source drift review. It produces source hashes and token-level discrepancy receipts and fails when it cannot establish the expected tokens. **It never upgrades token presence to a verified quote or renews the review date automatically.** A maintainer approves changed prices, availability assumptions and effective dates. The live source parsers have not been qualified against every provider delivery environment.

## Privacy and security

The public page sends no application telemetry. Explicit saves use browser storage. Shareable decision exports contain the supplied scenario and dated catalog; they grant no authority. Normalized run exports omit generated text, prompts, original filenames, raw error bodies and unrecognized metadata. Selected model names and timestamps can still identify work.

The helper binds loopback, checks the Host and Origin, rejects writes, requires a per-process bearer token for data, excludes symlinks and limits directory/file sizes. Tokens travel in a local URL fragment and are removed from the address after connection. Use a trusted local machine: these controls are not tenant authentication for an internet-exposed service. No provider key is bundled. A checksum supports exact recomputation, not source authenticity.

See `METHOD.md`, `PROVENANCE.json` and `QUALIFICATION.json` for the calculation boundary, donor identities and test scope. All source files are steward-owned; no workflow silently overwrites customer records. The wider execution fabric, public contribution registry, billing settlement and automated policy promotion remain separate development work.

## Integrated qualification records

The instrument owns measured-result arithmetic and qualification. The desk consumes its qualified record and sealed packet through a generated verifier, preserving the exact original object in saved decisions. `integration/README.md` in the combined source explains ownership, local publication, one catalogue and native browser qualification. Scenario arithmetic remains in the desk; source-bound workload findings remain in the instrument.
