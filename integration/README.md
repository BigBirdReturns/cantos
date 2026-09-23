# Compute desk / qualification instrument integration

`compute/` is the provider-neutral decision desk. `hot-aisle/` is the independently deployable qualification instrument. The desk links to the instrument and reads its explicitly published records. It neither imports the runner at runtime nor creates jobs, approvals, dispatchers or an alternate scheduler.

## Start both, then complete the handoff

```sh
node hot-aisle/runner/bin/workload.cjs serve --port 8787
node compute/scripts/connect.cjs --port 8765 --runner http://127.0.0.1:8787
```

Open the instrument at the printed localhost address and the private desk URL printed by `connect.cjs`. Prepare an evaluation on an already authorized allocation, review its limits and approve its exact plan. When a record exists, choose **Publish to connected desk**, then **Refresh observations** in the desk. Publication creates a local immutable snapshot; it does not send data to the public site. The desk lists the record, recomputes it and its matching sealed packet, permits saving a decision, and creates a linked price scenario without new inference.

For a complete software demonstration use `serve --demo` instead. Every generated result retains its synthetic status. Nothing in the demo needs an API token, GPU or model download.

The read-only MCP connection uses the same service:

```sh
node compute/scripts/connect.cjs --mcp --runner http://127.0.0.1:8787
```

`compute_list_publications` discovers explicit local snapshots; `compute_get_publication` verifies one. The instrument's separate MCP server remains the execution owner.

## One editing authority per domain

| Domain | Authoritative source | Generated copies |
|---|---|---|
| Public price catalogue | `compute/data/catalog.json` | `hot-aisle/data/catalog.json`, legacy prices block and file |
| Measured-result arithmetic | `hot-aisle/index.html` script `report-engine` | `compute/adapters/workload-engine.cjs` |
| Record qualification and revalidation | `hot-aisle/runner/lib/record.cjs`, `revalidate.cjs`, `publication.cjs` | `compute/adapters/qualified-engine.cjs`, embedded browser verifier |
| Ownership, shortlist and reuse scenarios | `compute/engine.cjs` | desk browser copy |
| Job execution and authority | `hot-aisle/runner/` | none in the desk |

`python integration/build.py` regenerates authority copies. `--check` detects drift. Copying the pinned functions is deliberate so each downloadable component operates independently; the generated files are not a second editing authority. `AUTHORITIES.json` records exact source hashes. The API-provided tenant price and a custom quote remain separate from the dated public catalogue.

## The publication contract

`hot-aisle/publication@1` contains a `hot-aisle/qualified-record@1` and the matching `hot-aisle/sealed-report@1`. The verifier checks the record checksum, recomputes its derived findings, checks declared/rule mirrors and approval binding, requires the expected report engine identity, recomputes the packet and verifies that it is the projection of this record's primary cell. A file hash authenticates neither a producer nor a historical execution.

The local publication ID combines the record ID with its checksum. Repeated publication of the same object is idempotent. A later version of a mutable runner record creates a different publication directory. Incomplete campaigns retain their completed/planned-trial count and cannot be presented as a complete campaign merely because a primary cell met its stated requirements.

The runner exposes `GET /api/publications`, `GET /api/publications/:id` and `GET /api/catalog`. The desk is configured with one explicit loopback origin and proxies these read-only resources. It accepts no arbitrary remote URL or browser-supplied path. A corrupt publication is held visibly. No published record appears until the operator performs the publication handoff.

`second-run/qualified-decision@1` retains that exact pair. Price-only revisions point to the earlier decision checksum and preserve the original measured record. Changing GPU count requires new performance qualification; it is not a price revision. Raw vLLM imports remain the separate fallback and never silently acquire qualified-record status.

## Qualification

```sh
python integration/build.py --check
node hot-aisle/scripts/test_workbench.cjs
node --test hot-aisle/runner/test/*.test.cjs compute/tests/test_core.cjs compute/tests/test_bridge.cjs integration/tests/seam.test.cjs
python -m unittest discover -s hot-aisle/scripts -p 'test_price_math.py' -v
python -m unittest discover -s compute/tests -p 'test_prices.py' -v
python compute/scripts/build.py
python hot-aisle/scripts/build_kit.py --check
```

The source-driven workflow `.github/workflows/hot-aisle-ci.yml` also runs the instrument's native file/HTTP/SSE journeys, the desk's native localhost journeys (`--require-navigation`), and the actual two-service browser handoff. A blocked browser is a failed qualification, not permission to substitute `set_content`. Generated manifests and archives contain their own source identities rather than hashes hard-coded in CI.

## Preserved boundaries

This integration does not run or fund a customer hardware campaign, authenticate a provider result, provision resources, transfer a repository to another organization or publish customer evidence on the internet. Real Hot Aisle authentication, native vLLM/ROCm compatibility and a matched comparator campaign remain unqualified. The runner's modeled time/spend checks apply between trials and are not a provider billing cap; that boundary must be addressed before describing a native campaign as hard-budgeted. Existing job schemas without the current plan-body identity may be retained as history but are not silently re-approved.

The public catalogue retains its actual review date. Rebuilding, copying, repricing and reconnecting do not renew it. The integration uses the supplied September 22 snapshot; no source-price refresh is implied.

## Native Windows recheck

`QUALIFICATION.json` records the exact tested source hashes and fresh native browser counts. The recheck caught and repaired same-document private-link activation, corrected presentation-sensitive test assertions, and distinguishes unconfigured observations from failed reads. Both services were driven through actual localhost URLs; the desk saved and repriced a published record, reloaded it, held corrupt input, and retained saved decisions after the runner stopped. The campaign backend remained explicitly synthetic.

## Publication acceptance

Every current workflow uploading the full Pages site runs `integration/release_gate.py` before upload. It requires a successful native-CI run for the exact product and release-workflow source identities. A newer matching failed run holds release; unrelated data-only commits can reuse an identical passing source set. Uncommitted product changes, missing proof and timeouts hold publication. Data-refresh commits remain separate from whether their site artifact may deploy.

Qualification JSON files describe the contract; workflow outcomes and captured source hashes establish results. The historical integration receipt applies only to its recorded bytes. Verify the gate with `python -m unittest discover -s integration/tests -p test_release_gate.py -v`.
