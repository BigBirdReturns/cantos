# Owned Linux process-continuity audit

The native collector records bounded samples of an explicitly owned PID file and the running executable's kernel process identity (PID and Linux start ticks). It distinguishes stable observed process identity, observed replacement, missing process, unreadable state and executable mismatch. It never stops, restarts, signals, configures or modifies the observed service. A replacement seen in samples is evidence of lifecycle transition, not a measured restart guarantee or endpoint health result. Missing and unobserved intervals never become uptime.

Create a JSON plan using `cantos.process-continuity-plan/1` with exactly `schema`, `pidfile`, `executable`, `samples` and `interval_ms`. The PID file must be an explicitly owned, absolute, non-symlinked path containing only a numeric PID. Set `executable` to the exact `/proc/<pid>/exe` link target for the authorized service. Each plan supports 2 to 128 samples, intervals of 20 to 5000 ms and a 120-second maximum scheduled span. Collection requires Linux procfs. Windows and unowned PID files fail closed.

```sh
python3 -B compute/maintainer/operational_process.py collect \
  --plan owned-process-plan.json --receipt owned-process-receipt.json
sha256sum owned-process-receipt.json
python3 -B compute/maintainer/operational_process.py verify \
  --plan owned-process-plan.json --receipt owned-process-receipt.json \
  --expected-sha256 SHA256_OF_EXACT_RECEIPT_FILE
```

The collect command exits 0 for a fully observed stable identity, 2 for a reported transition or incomplete observation, and 3 for malformed or unsupported input. Verify checks exact canonical receipt bytes and externally pinned SHA-256, row identity, population, chronology, classifications, summary and plan binding. A valid replay establishes internal integrity and attribution to the declared plan; it cannot authenticate the observer or imply availability between samples. The independent recipient test launches only its own disposable Python subprocesses and demonstrates an actual PID transition, a missing-process interval, negative controls and offline receipt replay. No production process is altered.

This B-domain observation complements the existing HTTPS and storage receipts. Correlating process identity with application endpoint health and commercial-provider recovery requires independently captured, timestamped evidence from those surfaces; this module alone supplies no commercial SLA or production availability claim.
