# Observed HTTP endpoint operations

`python3 -m compute.maintainer.operational_http --url http://127.0.0.1:8000/health --samples 3 --output /tmp/health-observation.json`

For an explicitly authorized public HTTPS endpoint, name its exact host and the URL. The collector does not discover or enumerate targets:

`python3 -m compute.maintainer.operational_http --url https://bigbirdreturns.github.io/cantos/public/open-compute/ --allow-host bigbirdreturns.github.io --samples 3 --output /tmp/cantos-pages-observation.json`

The CLI executes bounded **HEAD** requests without redirects. It records each UTC start, monotonic client elapsed time, HTTP status, transport error type and outcome class, plus an exact SHA-256 of the canonical observation array. It reports attempted probes, successes, client-vantage p95 elapsed time, separately classified throttling, server errors, client errors and unfollowed redirects. Exit code 0 means the **declared sampled thresholds** passed; 1 means they failed; 2 means invalid input or output. The output path uses exclusive creation and never replaces a retained receipt. Commands execute at most 30 requests, cap each request at 10 seconds, disallow URL credentials and query secrets, require explicit exact-host authorization and standard TLS validation for public endpoints, and do not send model inference or cloud provisioning requests.

This is one executable network/availability observation from one specified client and interval. It does **not** measure bandwidth, cloud-provider availability promises, remote host security, storage durability, operator recovery, GPU throughput or lifecycle orchestration. External-source provenance records the probe target and captured response status, not authenticated provider-side instrumentation. Another observer can recompute all summary statistics from the recorded observations, but an unsigned local receipt does not prove a remote provider's historical conduct. Further operational categories require their own authorized acquisition and evidence.
