# Operating inputs: useful work before provider promotion

This release connects reviewed operating materials to the existing compute desk's read-only MCP surface. It does not provision, dispatch, install, change client settings or grant data-transfer permission. No new runtime dependencies, database or scheduler are introduced.

## Concrete route candidates

| User request | Existing material | Outcome to qualify |
|---|---|---|
| Finish coding work | OpenCode private endpoint recipes, vLLM, EvalPlus, native dstack Hot Aisle backend | Accepted tasks per complete allocation cost and deadline, with cancellation and cleanup |
| Search a document folder | Local Docling parsing, BEIR relevance tests, optional qualified remote embedding/reranking | Correct fields, retrieved evidence and supported answers; skip GPU work that local parsing already resolves |
| Reuse long context | vLLM prefix reuse, AMD-specific LMCache builds, SGLang locality routing | Cold/warm/evicted/changed-context performance under tenant and runtime boundaries |
| Finish a numerical simulation | FluidX3D/OpenCL and addressable high-memory capacity | Numerical acceptance and full wall time; commercial rights require a separate check |

The registry contains 25 primary sources, seven operator shapes and four authored qualification recipes. Source references, proposed acceptance metrics and limitations are machine readable in `registry.json`. Existing Run 3 supports a bounded coding-batch observation, not an interactive coding-agent or managed-cluster qualification. Public software claims remain attributed upstream capabilities until tested here.

## Architecture consequence

Use the existing runner as the execution owner. A future lifecycle adapter should call an existing provider implementation such as dstack's native Hot Aisle backend instead of inventing a second provisioning system. Its backend documentation requires a tenant availability read and warns about full minimum reservations on some instances. Its runtime API excludes provisioning and image pull from max_duration. Neither a listed hourly price nor that timeout establishes a complete billing cap. Keep tenant inventory and prices outside this public-source collector.

Prefer prepared, pinned images and familiar clients. LMCache's AMD wheels require matching ROCm/PyTorch/Python/image identities. Cache history is not proof of answer correctness. A changed release tag requests qualification; it never installs a new version or promotes a route. Local execution remains a candidate when transfer, startup, rights or privacy make it preferable. FluidX3D's commercial-use rights remain a gate rather than being inferred from public source availability.

## Read and refresh

Run `node compute/scripts/materials.cjs coding-burst`, or call `compute_materials` with `{"recipe":"coding-burst"}` in the existing MCP connection. `recipe` and `layer` are optional filters; the caller cannot choose filesystem paths or URLs. Nothing is fetched during a tool call.

Explicit refresh: `python compute/scripts/material_feeds.py --previous compute/materials/observations.json --output /new/path/material-observations.json`. The collector uses four bounded public GET workers, refuses redirects, limits bytes/time and preserves the original age of last-good data on failure. Documentation bytes are hashed, not republished or parsed into prices; release metadata is separate from immutable artefact identity. A maintainer reviews a snapshot before copying it to `observations.json` and rebuilding the kit. No background schedule was activated.

Sources blocking automation use the explicit `--observed manifest.json` route: `{ "source-id": { "path": "capture.html", "sha256": "exact-file-digest", "url": "registered-url", "observed_at": "actual-capture-time" } }`. Captures must stay inside the manifest directory and preserve their original timestamp. Missing, stale, mismatched and inaccessible observations remain visible. The initial capture observed 23 sources; the SGLang gateway and SkyPilot job references refused redirects and remain unavailable in the feed.
