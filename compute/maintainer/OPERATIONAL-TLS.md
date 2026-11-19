# Source-bound TLS endpoint certificate audit

Use `operational_tls.py` only for an explicitly authorized HTTPS **origin**.
The collector makes direct TLS handshakes to an exact `--allow-host`, passes that
hostname as SNI, and uses Python's default CA verification and hostname checks.
It sends no HTTP request, follows no redirect and uses no proxy configuration.
A success records the observed leaf certificate DER, SHA-256, notBefore/notAfter,
handshake latency, observation timestamp and certificate-expiry policy. An
untrusted peer, pin mismatch or certificate approaching expiry yields failure.

From the extracted maintainer kit's `cantos` directory, for an endpoint you
are authorized to assess:

```sh
python -B compute/maintainer/operational_tls.py collect \
  --url https://EXACT-HOST/ --allow-host EXACT-HOST \
  --samples 2 --min-remaining-days 14 --output tls-observations.json
sha256sum tls-observations.json
python -B compute/maintainer/operational_tls.py verify \
  --receipt tls-observations.json \
  --expected-receipt-sha256 INDEPENDENTLY-RETAINED-SHA256 \
  --output tls-verification.json
```

Retain the SHA-256 **outside** the collected receipt before running the offline
verifier. The verifier rejects changed original bytes, decodes the embedded DER,
rederives the certificate fingerprint and ASN.1 validity times, replays per-sample
expiry and optional certificate pin rules, and recomputes aggregate status. Both
commands return exit 0 for pass, 1 for an observed failing policy and 2 for
invalid input or a broken custody/verification boundary.

An optional `--expected-leaf-sha256` establishes a separate leaf-certificate
identity invariant. A legitimate leaf rotation can trip this policy and needs an
explicit revised pin, not a silent bypass. Without a pin, the audit still
requires default CA-chain and exact-hostname verification during live collection.
The certificate is public TLS handshake data, but the receipt should retain its
normal evidence access controls.

The offline verifier validates the retained DER's syntax, fingerprint, expiry
and policy, not the original CA trust path, DNS destination, issuer authority or
server possession of the private key. Those depend on the live collector and
independently retained evidence custody. One short client-vantage sample is
neither a provider-wide uptime/security assessment nor an application-inference,
network capacity, lifecycle, or commercial-SLA measurement. Document the
observed origin, vantage, sample times and policy when citing a result.
