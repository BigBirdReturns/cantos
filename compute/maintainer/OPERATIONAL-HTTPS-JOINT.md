# Bound TLS and HTTP operational evidence

The independent operational HTTP and TLS collectors establish endpoint delivery and certificate behavior through separate connections. `operational_https_joint.py` measures the **same verified TLS connection** that carries each authorized HEAD/GET request. It records the leaf DER identity, CA/hostname-verified handshake classification, exact HTTP status, bounded response digest, total elapsed time, full failures and explicit policy. Each receipt can be replayed offline against an independently retained SHA-256 digest. It performs no inference, POST, provider account operations or paid resource provisioning.

Run from the checked-out source or extracted recipient kit root:

```sh
python -m compute.maintainer.operational_https_joint collect \
  --url https://bigbirdreturns.github.io/cantos/public/open-compute/ \
  --allow-host bigbirdreturns.github.io --samples 2 --method GET \
  --max-body-bytes 16384 --expected-body-sha256 DIGEST_FROM_SEPARATELY_PINNED_SOURCE \
  --output owned-observation.json
sha256sum owned-observation.json
python -m compute.maintainer.operational_https_joint verify \
  --receipt owned-observation.json --expected-receipt-sha256 OBSERVED_EXTERNAL_PIN \
  --output verified-observation.json
```

Exit codes: 0 accepted observations, 2 failed acceptance, 3 invalid evidence/command/permission. Outputs are created exclusively and never overwrite previous evidence. The collector uses a direct socket and a default verifying TLS context with SNI. It rejects query strings, credentials, redirects, non-HTTPS targets, unapproved DNS hosts and oversized response bodies. Leaf pins, body digests and minimum certificate lifetime are explicit invariants. An invalid TLS identity prevents the HTTP request. An observed response does not certify the origin operator or imply continuous availability, provider-wide security, network capacity, useful-work quality, or a commercial SLA. Offline replay validates the externally pinned receipt and recomputes DER, outcome classifications and verdict. It does not independently repeat CA verification; the observation's original trust boundary remains explicit.
