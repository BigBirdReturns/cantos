# evidence/

The minimal retained inputs the product reads, copied from the axm-tools session folders with relative layout preserved. Resolved through `tools/evidence_root.py` (env `CANTOS_EVIDENCE` overrides this folder; the old absolute session paths are used only when a file is missing here).

- `clustermax-cloudreview-20260929/` : `claims.all.jsonl`, `headers.all.json`, `page-tier-vs-3.0.json`, `review-headers.json`, `capture-manifest.json`, `SHA256SUMS.txt`, and `providers/<slug>/manifest.json` (manifests only; the fetched provider pages are not shipped). Used by `floor/rate`.
- `public-tail-20260929/lanes/chat-corpora-meta/` : the lmsys-chat-1m parquet listing and the lane `manifest.json` (records the HTTP 401s). Used by circulate probe p05.
- `public-tail-20260929/lanes/clustermax-r2-raw/` : Crusoe's Atlassian history + incident files and CoreWeave's status.io history page, used by probe p08. `MANIFEST.json` lists the original sha256 of each file. Any webhook URL is replaced by `REDACTED-WEBHOOK-PLACEHOLDER` (none were present in these files).

Not shipped (bulk): the 954 MB OpenComputePrices feed, the other public-tail lanes, the provider page captures. Scripts that need them report `SKIP` with the path they looked for; committed outputs (`findings.jsonl`, `RATINGS.*`, price cache) are static and unaffected.
