# Owned cross-host health-route gate

This CLI extension measures one explicitly authorized named TLS responder. A job
can require zero failed attempts and a maximum p95 latency before expressing a
deployment preference. Software fixtures cover this path; real cross-host
acquisition remains a separate acceptance step. There is no new UI acquisition
action. Existing requirement JSON and retained decision views carry the gates.

This does not qualify native model endpoint health, application success, uptime,
an SLA, provider security or general provider ratings. The native verdict remains
separate. Expected identities come from the selected requirement, never from a
receipt's self-description. Target/protocol changes alter decision identity and
invalidate mismatched evidence; they do not change native observations.

## Contract

Use the normal required operational requirement fields, with `operator: "lte"`,
`allowed_basis: ["observed"]`, an explicit `max_age_s`, plus these two objects:

- `network_protocol`: exactly `samples` (integer 1-20), `timeout_s` (0.1-3), and
  `interval_s` (0-1).
- `network_target`: exactly `id` (bounded route label), `url` (HTTPS literal
  unicast nonloopback IPv4, explicit port 1024-65535 and named path, no query/
  fragment/credentials), `collector_host_id_sha256`, `responder_host_id_sha256`,
  `responder_instance_id` (canonical UUID), `responder_source_sha256`,
  `tls_certificate_sha256` (DER SHA), `resource_identity_sha256`, and
  `scope: "owned_named_health_route"`.

Declare two requirements selecting the same target/protocol:

| Check | Meaning |
| --- | --- |
| `owned_network.failure_count` | Every failed attempt in the exact declared population; normally threshold 0 |
| `owned_network.latency_p95_ms` | Nearest-rank p95 local monotonic request duration, including TCP/TLS/body; unknown if **any** attempt fails |

Collector hostname hash (e.g. W01) is separate from responder hostname hash (e.g.
W03), and they must differ. Hashes are SHA256 of exact hostname UTF-8. The target's
resource hash must match the entire canonical native hardware identity, and that
hardware must already declare `audit_host_id_sha256` matching the responder host.
Missing or incompatible binding is unknown; no old identity is retrofitted.

The exact certificate pin authenticates designated key possession during
acquisition. Pinned self-signed certificates require no trust-store changes; no CA
or DNS hostname authentication is claimed. Host/instance/module labels and resource
origin remain operator declarations, not remote execution attestation or signed
retained receipts. Obtain expected pins/identities independently through trusted
operator setup. The supported responder module SHA must equal the installed pin.

## Explicit finite acquisition

`CONFIG.json` contains exactly `network_target` and `network_protocol`. Explicit
authorization `TARGET_SHA` is SHA256 of canonical target JSON: sorted keys, UTF-8,
separators `,` and `:`, no nonfinite values. Owner-provided certificate/key paths
are runtime-only; private keys never enter the acquisition evidence.

```text
python3 -B compute/maintainer/owner_ocl/network_health.py serve --config CONFIG.json --authorize-target TARGET_SHA --certificate CERT.pem --key KEY.pem --max-seconds 240 --max-requests 40 --ready-file NEW_READY.json
python3 -B compute/maintainer/job.py collect-network --manifest JOB.json --arm baseline --requirement REQUIREMENT_ID --authorize-target TARGET_SHA --out NEW_AUDIT
```

The separately authorized responder has a maximum configured lifetime 300s and
40 accepted connections, bounded TLS/header handling, and atomic exclusive
readiness after bind/listen/TLS setup. The normal/finally terminal receipt is
`NEW_READY.json.terminal.json`. The outer owner must retain exit/cleanup evidence
and a hard job bound for OS stalls. No responder is started by collection/import.

The job uses the existing pinned workbench collector and checks both collector
and network-module source hashes **before** contact. Its private CLI is
`instruments/collect.py network-health --config CONFIG.json --authorize-target
TARGET_SHA --out NEW_AUDIT`. There are no model/scan/service/firewall operations.
Direct numeric-address sockets use no proxies, DNS, redirects, ambient credentials
or cookies. One absolute timer covers TCP, TLS and response reading; registered
sockets close on expiry and cannot reconnect as plain HTTP. Each GET gets a fresh
256-bit nonce. Only exact 200, exact JSON content type and exact canonical
nonce/instance/host/source body pass. Bodies are bounded 4096B; duplicate JSON,
trailing data and nonfinite values fail. No failed attempts disappear.

`operation-template.json` embeds raw requests/responses/certificate, UTC/monotonic
timings, summary, original attempt journal and collector packet as bounded base64.
It emits both checks when their target/protocol match. Attach it to the arm's
`operations` before normal job run. A manifest can be copied/prepared before model
endpoints are live; native `prepare` only resolves declared files/configuration.
Both arms may reuse that explicit pre-run sample only when both targets/hardware
match. Normal run binds exact run hash, hardware and original raw UTC window.

Offline verification rechecks source pins, hashes/sizes, every attempt and nonce,
request/response identity, local-clock consistency, computed summary and freshness.
It never recollects. Price children preserve original bound evidence. To attach a
new acquisition, explicitly remove its stale bound attachment from the child
manifest; conflicting old/new inputs fail closed. Parents remain immutable.
Evidence must precede the native run within its declared age. Fresh probes cannot
retroactively qualify old runs. Required missing/stale/tampered/incomplete evidence
blocks preference. Empty requirements establish no operational qualification.

## Qualification and source custody

Run `python -B -m unittest compute.maintainer.tests.test_network_health` from the
source root. Transport is mocked; native integration uses authored loopback SSE
fixtures and the actual receipt validator. These are software tests, not model or
provider evidence. Live acceptance must retain exact source/artifact pins, declared
W01/W03 identities/certificate/instance, responder readiness/exit, all W01 attempts,
offline gate verification and an inapplicable old-run required-UNKNOWN child.
A positive joined gate needs a new applicable CPU run after the audit and declared
audit host; preserve that existing recipe's own 100% policy, two cases x three
trials x two arms=12 requests, max 16 tokens. The separate thermal 32-case 80% policy is
unchanged. Native incomparable evidence stays incomparable even with a passing gate.

The published ZIP predates this extension and must fail the new source precheck.
`SOURCES.json` identifies new private-owner source, separate from historical bundle
provenance. After review, root must sync the native mirror, build/qualify a distinct
workbench archive, update its outer archive pin, then build/qualify a separate
maintainer kit. Existing campaigns retain their approved old kit. No build,
install, live responder/probe, job, GPU/model work or publication occurred here.

The previously approved collector SHA
`348b194d7eda533541248c5210d015b210eacf46c424ab8175df2d6180404dc0`
is retained explicitly for historical recovery packets only, preserving their
unchanged raw/run/hardware/time checks and original decision identity. Unknown
pins remain refused; current acquisition and every new network packet require the
new exact collector/module pins. Set `CANTOS_RETAINED_RECOVERY_BUNDLE` to an
authorized original bundle to run the real retained-import regression; no fixture
is substituted when it is absent.
