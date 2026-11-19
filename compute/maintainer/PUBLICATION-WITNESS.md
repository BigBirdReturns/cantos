# Source-bound public release witness

Run the read-only public witness with the exact commit and independently qualified recipient-kit digest and byte count. It observes the current GitHub main ref, qualifying CI for that exact head, the associated GitHub Pages workflow, and the exact served archive at the fixed Cantos Pages URL. It fails closed on changed main, later failed/pending jobs, missing jobs, redirects, or mismatched bytes.

    python -m compute.maintainer.publication_witness observe \
      --commit EXACT_40_HEX --kit-sha256 EXACT_64_HEX --kit-bytes INTEGER \
      --receipt public-witness.json

Record the SHA-256 reported beside the receipt separately, then independently replay without network:

    python -m compute.maintainer.publication_witness verify \
      --receipt public-witness.json --sha256 EXTERNALLY_PINNED_64_HEX

PASS means the observed endpoint and GitHub API responses matched those bindings from this client vantage. WAIT means an exact-head publication gate was missing or incomplete. HOLD means an exact-head gate failed or a source/byte identity contradicted the expected release. Neither PASS nor a pinned client receipt establishes provider-wide availability, authenticated GitHub attestation, or completion of empirical A/B/C acceptance. This operation performs only HTTPS GET requests, never creates a release, changes a workflow, or contacts a recipient.
