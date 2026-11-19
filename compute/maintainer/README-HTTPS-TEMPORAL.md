# Same-socket HTTPS temporal ledger

The collector `operational_https_joint.py collect` acquires bounded, direct HTTPS observations, verifying the TLS peer with the default CA trust store, hostname validation and SNI, then binding the HTTP response to that same connection. Each write is exclusive and yields a SHA-256-pinnable receipt.

The `operational_https_ledger.py` recipient CLI consumes an externally SHA-256-pinned manifest and a directory of individually pinned original joint receipts. It independently replays each TLS DER and HTTP observation, enforces identical URL/host/method and non-sample policy, refuses duplicate, reordered, overlapping, altered or symlinked evidence, then reports observed successes, failures, latency, TLS leaf identities and gaps. A failing sample or receipt stays visible. Exit codes are 0 (accepted), 1 (observed threshold failure), and 2 (invalid evidence).

Example offline replay of the bundled measured evidence, after extracting `evidence/https-temporal-20261119.zip` into `/tmp/https-temporal`:

```bash
python3 compute/maintainer/operational_https_ledger.py \
  --manifest /tmp/https-temporal/manifest.json \
  --expected-manifest-sha256 "$(cat /tmp/https-temporal/manifest.sha256)" \
  --evidence-directory /tmp/https-temporal
```

Evidence collected on 2026-11-19 from `https://bigbirdreturns.github.io/cantos/public/open-compute/` consists of two independent receipts, four same-socket TLS/HTTP GET observations, and externally pinned manifest/receipt hashes. All four were HTTP successes in the capture. These samples establish only the stated client-vantage observations, not provider-wide uptime, a commercial SLA, authenticated host custody, or application-level model correctness. The archive is immutable source evidence after Git commitment. Its own SHA-256 and source-tree identity must be verified through the recipient kit manifest, not inferred from the embedded `manifest.sha256` alone.
