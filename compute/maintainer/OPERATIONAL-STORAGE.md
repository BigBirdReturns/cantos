# B: bounded local storage readback audit

The `operational_storage.py` CLI collects actual, read-only byte counts, SHA-256 identities, error classes and monotonic read times for explicitly listed files beneath one owned directory. It tests the current local file-read path without writing, repairing or fault-injecting the audited storage. A pinned plan declares each expected SHA-256 and exact byte length, with at most 32 files, three samples per file, 16 MiB per file and 64 MiB aggregate read budget. Receipt bytes contain no file contents.

```sh
python3 compute/maintainer/operational_storage.py collect --root /absolute/owned/root --plan /path/pinned-plan.json --output /separate/receipt.json
python3 compute/maintainer/operational_storage.py verify --plan /path/pinned-plan.json --receipt /separate/receipt.json
```

The plan has schema `cantos.storage-readback-plan/1`, a `samples` integer from 1 to 3, and an `entries` array of `{"path":"relative/file","bytes":123,"sha256":"<64 lowercase hex>"}`. Use a separately pinned source manifest to create the plan, rather than deriving expected digests from the same read under audit. The collector uses relative descriptor traversal with `O_NOFOLLOW`, rejects symlinks and nonregular files, checks file identity before, after and on a fresh open, and records missing or changed files as failed observations. It accepts only an absolute owned root and writes its receipt outside that root.

Exit 0 means all observed samples matched the declared source identity; exit 2 means a completed audit observed mismatches or read errors; exit 3 means invalid input, an unsafe path, or collection failure. The offline verifier independently recomputes the plan binding and sample-level classifications and detects a falsified successful readback. Its verdict demonstrates internal receipt consistency, not independent collector authentication.

**Evidence boundary:** These measurements support only authorized local file readback at one client vantage and observation time. They establish neither disk failure endurance nor cloud-provider durability, restoration, isolation, service availability or contractual SLA. OS cache, background I/O, filesystem snapshots and read scheduling can affect elapsed time. The collector makes no new model calls, writes no data into the audited root, and has no authority to run destructive recovery tests. Real provider coverage requires scoped provider resources and appropriately attributable observations.
