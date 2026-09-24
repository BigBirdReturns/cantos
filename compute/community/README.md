# Second Run Compute: the community loop

One board for retained execution paths, supported by the existing workload-report arithmetic. Public browsing, claim checks and saved decisions require no account. The optional Node helper manages a local admission queue, immutable result objects and append-only review events. This release is a community beta, not a certification or an operating compute exchange.

## A complete first visit

Open `results.html`, select a workload and two relevant records, then choose **Check a claim**. Keep scope at the selected observations unless you deliberately want to test a broader marketing statement. Save or export the resulting decision. Its records and exact calculation travel with it. Each result also has a self-contained HTML report that recomputes offline.

The board does not automatically read a pasted URL or interpret arbitrary marketing text. The visitor selects the measurable statement; unknown or incompatible evidence produces a gap, and a universal claim produces a scope limit even when the selected observations agree. Token prices, hardware memory and task success remain different measurements. Uptime, live capacity, autonomy, interventions and energy remain unmeasured unless a later admitted record schema supplies them.

## Authority and evidence

`core.cjs` calls the retained `workload-engine.cjs` for all source-bound workload outcomes, latency gates and costs. It does not replace the execution instrument's arithmetic. Historical TierBench rows are imported as source-reported historical summaries and keep their cost basis. Historical narrative findings are not upgraded into native trial evidence. They may be compared only as the observations in their exact study, with the study's limitations attached.

A result packet is `second-run/result-packet@1`: SHA-256 over canonical payload JSON, metadata plus one supported evidence body. Native normalized report evidence can be recomputed without original files; the original input hashes remain commitments, not producer authentication. Source authenticity, invoice authentication, statistical representativeness and contributor independence remain separate questions. Two usernames or two copies of one trial never establish replication.

Source snapshots are fixed at full commits. An unavailable source or missing field stays unavailable. No new model calls or GPUs are required to build the board. Seed disclosures preserve sponsorship and unresolved billing. Costs labeled modeled, source-reported, shadow-estimated and upper-bound must not be presented as reconciled invoices.

## Private contribution, then explicit publication

Read a publication already released by the existing instrument:

```
node community/cli.cjs capture --runner http://127.0.0.1:8787 --publication PUBLISHED_RECORD_ID --out candidate.json
```

The helper checks the original publication and its matching report. It writes a private candidate and never starts a job. Open the candidate in **Contribute**, review public labels, declare funding and relationship, inspect the preview and download the approved packet. Original prompts, outputs, raw filenames and unconstrained metadata are not carried into the workload projection. Exact model identity and timestamps can still reveal work. The screen requires explicit consent; its credential/path/email checks are guardrails, not a privacy certification.

Optional public submission through your own authorized `gh` installation:

```
node community/cli.cjs submit contribution.json --repository OWNER/REPO --approve-public FULL_PACKET_SHA256
```

This command alone makes external writes: a public gist containing the exact reviewed packet, followed by a review issue. It needs permission to create both. A gist-success/issue-failure response retains the gist URL so you can finish the submission without duplicating it. It never admits a result or opens a pull request automatically. Repository maintainers still review the source and scope. No submission was performed merely by building or testing this release.

## Independent hub

```
node community/cli.cjs init ./my-hub --name "Our compute desk"
node community/cli.cjs serve ./my-hub --port 8770
```

Initialization refuses existing directories. The packaged seed retains its upstream attribution and limitations; `--empty` starts with no admitted records. The new hub contains its own application, objects, review history and generated site. Every command can subsequently be run with `node my-hub/app/cli.cjs ...`; it does not need the original kit directory or the public origin.

```
node my-hub/app/cli.cjs stage contribution.json --hub ./my-hub
node my-hub/app/cli.cjs review PACKET_SHA --hub ./my-hub --decision accept --reviewer "Maintainer" --reason "Reviewed scope and disclosures"
node my-hub/app/cli.cjs build ./my-hub
node my-hub/app/cli.cjs verify-feed ./my-hub/site/feed.json
node my-hub/app/cli.cjs ingest other-feed.json --hub ./my-hub
```

A feed import stages data without inheriting another hub's approval. Review decisions are hash-linked immutable events. Rejection or withdrawal creates a later event while preserving original objects. A correction names the earlier packet; it does not overwrite it. Duplication of underlying evidence is held unless it is explicitly a correction. Synthetic data is reserved for software tests and refused by normal public admission.

The local server binds only 127.0.0.1, checks its Host header, permits GET/HEAD on a fixed set of static paths and has no write API. It does not provision, invoke a model, open a shell or fetch sources. Serve `site/` on any static host to publish your hub. The generated record pages operate when downloaded and disconnected.

## Verify

```
node --test community/tests/test_core.cjs
python community/tests/browser.py --out /tmp/second-run-community-qa
node community/cli.cjs verify result.json
node community/cli.cjs verify-decision decision.json
```

Python Playwright/Chromium is test-only; application and CLI use built-in Node modules. Browser qualification uses real HTTP navigation, two independent directories and two loopback origins. The second hub is exercised after the first server is stopped; all outside network requests are rejected. A separate Node process recomputes an exported decision. This demonstrates software portability in the test environment, not actual independent community adoption or native GPU replication.

## Maintenance and ownership

Steward-owned: source files, `data/release.json`, contribution policy and the pinned source import recipe. Machine-generated: `data/records/`, `feed.json`, `../results.html`, `r/`, `../community-kit.zip`, `MANIFEST.json`. The import recipe writes only new content-addressed seed records; correcting a source requires a new packet and relation. Original campaign records are never edited.

Hub `objects/`, `inbox/` and `reviews/` are operator-owned durable custody; `site/` is a rebuildable projection. Never run two maintainers' review commands against one directory. A stale `.review-lock` must be investigated before removal. Keep review history and packet objects during migration; regenerate the site from those records. Review code changes before upgrading executable recipes; ingesting a result never executes code from its body or source URL.

Current native qualification, external contribution and source coverage are recorded in the release receipt. A populated board is not evidence of a self-sustaining community. That next acceptance test requires real outside operators.

## Shipped measurement boundary

The native rows are reprojected through the retained workload engine. Its documented quantile interpolation can differ slightly from a prose percentile in the original write-up. Raw source identities and acceptance masks remain intact. The list-rate Hot Aisle baseline is a dedicated-equivalent scenario; the tuned row is its own shared-seat script window; DigitalOcean uses the recorded request-to-release interval. Comparing unlike cost windows is a stated scenario, not an invoice comparison. The source collection includes every retained TierBench ledger row, grouped by exact task/model/effort/support/cost basis; none is upgraded from historical reporting to independently executed evidence.

Original code in this directory is MIT licensed (LICENSE). Provider and benchmark-source rights remain with their owners. Source snapshots and their original repositories identify the relevant material.
