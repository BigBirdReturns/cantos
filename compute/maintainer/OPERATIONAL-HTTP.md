# Observed HTTP endpoint operations

`python3 -m compute.maintainer.operational_http --url http://127.0.0.1:8000/health --samples 3 --output /tmp/health-observation.json`

For an explicitly authorized public HTTPS endpoint, name its exact host and the URL. The collector does not discover or enumerate targets:

`python3 -m compute.maintainer.operational_http --url https://bigbirdreturns.github.io/cantos/public/open-compute/ --allow-host bigbirdreturns.github.io --samples 3 --output /tmp/cantos-pages-observation.json`

The CLI executes bounded **HEAD** requests without redirects or environment-selected HTTP(S) proxies. Each request contacts the exact authorized host directly, so the receipt describes the direct client vantage rather than an ambient proxy.  It records each UTC start, monotonic client elapsed time, HTTP status, transport error type and outcome class, plus an exact SHA-256 of the canonical observation array. It reports attempted probes, successes, client-vantage p95 elapsed time, separately classified throttling, server errors, client errors and unfollowed redirects. Exit code 0 means the **declared sampled thresholds** passed; 1 means they failed; 2 means invalid input or output. The output path uses exclusive creation and never replaces a retained receipt. Commands execute at most 30 requests, cap each request at 10 seconds, disallow URL credentials and query secrets, require explicit exact-host authorization and standard TLS validation for public endpoints, and do not send model inference or cloud provisioning requests.

This is one executable network/availability observation from one specified client and interval. It does **not** measure bandwidth, cloud-provider availability promises, remote host security, storage durability, operator recovery, GPU throughput or lifecycle orchestration. External-source provenance records the probe target and captured response status, not authenticated provider-side instrumentation. Another observer can recompute all summary statistics from the recorded observations, but an unsigned local receipt does not prove a remote provider's historical conduct. Further operational categories require their own authorized acquisition and evidence.


## Optional exact-body service and distribution audit

A successful HEAD only observes the status response. A bounded GET can additionally compare the actual HTTP entity returned by an authorized service or distribution route against a separately sourced expected SHA-256:

```sh
python3 -m compute.maintainer.operational_http \
  --url http://127.0.0.1:8000/health.json \
  --method GET --expected-body-sha256 <64-hex-digest> \
  --samples 3 --max-body-bytes 65536 \
  --output /tmp/health-body-observation.json
```

Replace the example digest with the authentic expected digest from the application owner or published release manifest. The request uses no credentials, no body, no redirect, no environment proxy and no inference POST. The collector records the returned entity's byte count, SHA-256 and server-reported content length/encoding, without retaining the response body. It reads at most the configured limit plus one byte per attempt (maximum permitted limit 1 MiB); an oversized or incomplete body fails. A syntactically valid HTTP 200 with the wrong bytes becomes `http_body_mismatch`, independently of HTTP status. The existing sampled success and latency gates count body mismatches, truncated bodies and oversize bodies as failures. When an expected digest is supplied, any returned corrupt body fails the whole identity gate, even with a relaxed availability threshold; at least one matching response is required. A GET without an expected digest remains a body observation, **not** a content-integrity acceptance.

The digest covers the HTTP client's received entity bytes after transfer framing, without content decompression; the recorded encoding header is the server's claim, not a verified application decoder. Obtaining the expected digest from the same unauthenticated response would not independently validate origin or release provenance. This audit establishes bounded route behavior from its client vantage, not provider-side storage durability, remote security controls, inference correctness or a commercial SLA. For independently audited content, supply the digest from retained and separately verified source/release evidence.
