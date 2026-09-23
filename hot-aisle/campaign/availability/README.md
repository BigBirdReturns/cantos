# Availability ledger

One JSON line per observation of whether a provider would sell a given GPU SKU, in a given region, at a given moment. Every provisioning attempt the campaign makes writes here, including failures. This is the raw material for the availability heatmap: provider × SKU × region × hour. Nobody publishes this from the buyer's side.

Fields: `ts` (UTC), `provider`, `region`, `sku`, `gpus`, `method`, `layer`,
`outcome` (`available` | `out_of_capacity` | `out_of_stock` | `create_failed` |
`ssh_failed` | `unknown`), `provisioned`, and `synthetic`. Scheduled listings use
`method: api`, `layer: listed` and `reason`. Delivered rows use `layer: delivered`
and require `method` to be `api-create`, `console-create` or `tui-provision`, plus
`attempt_id`, `evidence`, `real_create_attempt` and `ssh_reached`;
`time_to_ssh_s` is required for success. Historical rows may omit newer fields,
use `console-plan-list`, `tui-provision-list` or `prior-session-note`, and include
optional `count` or `note`. Historical bytes are preserved.

Seeded 2026-09-23 from the first campaign. Times before 19:00 UTC are approximate to a few minutes. Probing on a schedule needs provider API tokens (DigitalOcean, Hot Aisle), which the operator holds. The admin TUI rate-limits repeated logins.

## Lane C kit (build only, 2026-09-24)

Python 3.9+ standard library only. No containers or model weights are used, so
model revisions and image digests do not apply. Nothing is installed or scheduled
by building this directory. The existing 15 ledger lines remain unchanged.

`probes.json` fixes 12 provider/SKU/region/GPU tuples from the campaign. These are
sampling targets, not assertions of currently rentable inventory. RunPod and bare
metal remain historical evidence; this lane implements only the two VM APIs.

### Public API sources and limits

Checked 2026-09-24, using four search queries plus direct public source reads:

- [DigitalOcean Sizes API](https://docs.digitalocean.com/reference/api/reference/sizes/):
  `GET https://api.digitalocean.com/v2/sizes`, `Authorization: Bearer <token>`.
  A GPU size has `gpu_info.count`; `available` and `regions` supply listing status.
  The adapter follows all pagination links, confined to that HTTPS origin/path,
  at most 20 pages and 20 seconds per request. A positive requires the exact SKU,
  matching GPU count, `available: true`, and membership in `regions`. A missing SKU
  is unknown, not a stockout. This does not establish quota or successful creation.
  These `available`/`regions` flags describe **configuration availability** and
  may not move with capacity. Their correspondence to rentable capacity is
  **UNVERIFIED until compared with console observations**. On 2026-09-23 the
  campaign's console observations showed H200 out of capacity in all regions;
  API listing flags must not override that evidence.
- [DigitalOcean sizes:read scope](https://docs.digitalocean.com/reference/api/scopes/sizes/read/)
  also requires `regions:read`. Supply a read-scoped `DIGITALOCEAN_TOKEN`.
- [Hot Aisle public API docs](https://admin.hotaisle.app/api/docs/) were reachable
  through web retrieval but exposed no readable schema. Direct local retrieval
  was refused. Full public-doc authentication verification is **UNVERIFIED**.
- [Hot Aisle's official client](https://raw.githubusercontent.com/hotaisle/hotaisle-cli/main/client/client.go)
  confirms base `https://admin.hotaisle.app/api` and the `Authorization` header
  (the client passes its supplied value unchanged). The existing campaign runner
  supplies `Token <token>`; that prefix is **UNVERIFIED in this build**. The
  [official v0.10.1 generated API types](https://pkg.go.dev/github.com/hotaisle/hotaisle-cli@v0.10.1/client)
  confirm team-scoped VM availability, `Quantity`, and `Specs.gpus`.
  The existing runner uses `/teams/{team}/virtual_machines/available/`; the brief's
  `/virtual_machines/available/` is its suffix, not a verified global endpoint.
  The full path is **UNVERIFIED against live API docs in this build**.

Hot Aisle responses have no regional coordinate in the documented VM type. The
kit therefore ships `team: null`, `auth_status: UNVERIFIED...`, and
`region_scope: null`. It performs no Hot Aisle request until the operator supplies
the team and sets `auth_status` to `verified` after checking the auth/path.
Set `region_scope` to `enc1` only after verifying that the team endpoint's returned
inventory is confined to ENC1. Otherwise leave it null: results remain unknown.
Do not map regionless inventory to every region. Tokens come exclusively from
the two environment variables; no credential files are read automatically.

### Run and test

From this directory (use `python3` on N01):

```sh
python -B probe.py --self-test
python -B heatmap.py --self-test
python -B test_availability.py
python -B probe.py --dry-run
python -B heatmap.py --now 2026-09-23T23:59:59Z
```

All three test commands run the same offline suite. Fixtures are synthetic;
`fixtures/observations.jsonl` intentionally exercises both evidence layers and
must never be copied into the operational ledger. `fixtures/delivered.json` is
marked synthetic and is deliberately rejected by the delivered helper.
`fixtures/digitalocean-page1.json` contains a synthetic `links.pages.next` link
to the second response (`digitalocean.json`); the suite verifies both pages'
contents, the requested URLs and authorization headers entirely offline.

`--dry-run` reads `fixtures/{digitalocean,hotaisle}.json`, never accesses the
network even when tokens exist, and prints JSONL without writing by default.
An explicit `--output demo.jsonl` appends only synthetic rows and refuses the
canonical campaign ledger. Heatmaps exclude rows marked synthetic. The default
Hot Aisle fixture results remain unknown because the regional mapping is unset;
the self-tests separately exercise positive and zero quantities with an explicit
fixture-only mapping.

After deployment authorization and token/config setup, one real read-only sample:

```sh
python3 -B probe.py --config probes.json --output /var/lib/second-run-availability/observations.jsonl
python3 -B heatmap.py --input /var/lib/second-run-availability/observations.jsonl --html /var/lib/second-run-availability/heatmap.html --summary /var/lib/second-run-availability/heatmap.txt
```

Each tuple appends `method: api`, `layer: listed`, `synthetic: false`, UTC `ts`,
`provisioned: false`, an outcome and reason. Missing tokens, HTTP failures,
timeouts, bad JSON, identity ambiguity and schema changes become unknown.
Response bodies and tokens are never logged. A completely unknown sample exits
1 *after* recording it; partial failures remain visible in the output/chart and
exit 0. Configuration or append failures exit 2.
Before tokens exist, every scheduled sample is all-unknown: exit 1 every 15
minutes can produce repeated unit-failure alerts. Configure credentials and
inspect the first sample before enabling the timer to avoid that alert noise.

### Record a delivered attempt

The helper records an actual create attempt already performed elsewhere; it
never provisions anything. Make a private receipt JSON using the fields in
`fixtures/delivered.json`, replace every fixture value, remove `synthetic` or set
it false, and attest `real_create_attempt: true`. Use a globally unique
`attempt_id` and an `evidence` reference to retained create/SSH records. Include
an offset-aware `ts` for the attempt's start. Keep secrets out of evidence refs.
Set `method` to the actual create channel: `api-create`, `console-create` or
`tui-provision`. The helper preserves that method and writes `layer: delivered`;
missing methods and listing methods are rejected.

```sh
python3 -B probe.py --delivered /path/to/actual-attempt.json --output /var/lib/second-run-availability/observations.jsonl
```

`available` means SSH was reached: `ssh_reached: true` and a finite nonnegative
`time_to_ssh_s` are required. Other outcomes (`out_of_capacity`, `out_of_stock`,
`create_failed`, `ssh_failed`, `unknown`) require `ssh_reached: false`. A VM that
was created but never reached SSH is `ssh_failed`, not delivered success.
Record each finalized attempt once; unresolved attempts can be recorded unknown.
Duplicate IDs are refused. This is operator-attested evidence, not automatic
verification of a receipt's authenticity. No edits or silent upserts occur.

Writers serialize through `<ledger>.lock`, validate existing JSONL, append and
fsync. A partial final line is refused without changing it. If a process is
killed, an orphan lock is possible: confirm no writer remains before removing
that lock. Keep the evidence bytes; investigate incomplete records separately.
Do not run manual writers during the timer's renderer if a fully consistent
snapshot is required. A concurrent partial read fails visibly on malformed JSON.

### Heatmap semantics

`heatmap.py` writes a standalone HTML document with inline SVG and CSS plus
`heatmap.txt`; no network requests, JavaScript, or external assets. Default time
is current UTC; `--now` makes builds reproducible. The supplied artifact uses
2026-09-23 23:59:59 UTC and only the unchanged campaign ledger.

There are 168 hourly columns: the current partial hour plus 167 preceding whole
hours. Each row is provider × SKU × region, labelled with GPU count. Colour is
available / valid **API** probes, where valid outcomes are available,
out_of_capacity and out_of_stock. Unknown probes never enter that denominator.
No valid probes means grey. Tooltips, row totals, an HTML table and the text
summary expose counts. Missed slots are elapsed quarter-hour slots with no API
observation, starting with each row's first API observation (including unknowns).
The first observed quarter-hour is included; earlier quarters in that hour and
all earlier hours are labelled **not sampled**. Rows with no API observations
have zero missed slots and remain entirely not sampled. An API observation
before the displayed week still establishes the sampling start. Synthetic,
future, manual and delivered observations do not start the API sampling clock.
Multiple probes in one slot all count, but fill only one slot for the missed-slot
calculation. This is a sampling fraction, not uptime.

Delivered dots use a separate successful-SSH / attempt denominator. The first
eight dots per hour are shown individually; additional attempts have an overflow
count and all outcomes remain in the table/text. A legacy `console-create`
success counts only when explicit provisioned and SSH-duration evidence exist.
The old TUI listing with `provisioned: true` is **not** promoted to a delivered
attempt. Historical manual listings and approximate notes are counted as
excluded, rather than mixed into scheduled API denominators. Thus the supplied
chart is grey for listed status and contains one historical delivered success;
it does not fabricate a week of API history.
A delivered tuple outside `probes.json` still gets its own row; it does not
acquire an API sampling history merely because an attempt exists.

### N01 deployment instructions — not executed

Resolve/contact N01 through Estate's canonical front door before activation;
the kit contains no peer address, login or SSH configuration. The operator must
authorize installation, supply the two tokens, verify the Hot Aisle configuration,
and choose ledger custody. These commands are for a coordinated N01 session,
from a staged copy of this directory. They do not transfer the campaign ledger.

```sh
sudo install -d -m 0755 /opt/second-run-availability
sudo install -m 0644 probe.py heatmap.py probes.json /opt/second-run-availability/
# First install only; never overwrite an existing env file containing tokens.
sudo test ! -e /etc/second-run-availability.env && sudo install -m 0600 availability.env.example /etc/second-run-availability.env
sudoedit /etc/second-run-availability.env
sudoedit /opt/second-run-availability/probes.json
sudo install -m 0644 availability.service availability.timer /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/availability.service /etc/systemd/system/availability.timer
sudo systemctl daemon-reload
sudo systemctl start availability.service
sudo systemctl status availability.service
sudo journalctl -u availability.service -n 30 --no-pager
# Enable after inspecting the first sample and generated outputs:
sudo systemctl enable --now availability.timer
sudo systemctl list-timers availability.timer
```

`DynamicUser` and `StateDirectory` manage `/var/lib/second-run-availability`; no
permanent account is required. Outputs are private (umask 0077). The service runs
the probe and renders in `ExecStopPost`, including after an all-unknown failure.
The timer fires at UTC :00/:15/:30/:45. `Persistent=true` gives one catch-up run
after downtime; it cannot recreate missed history. No concurrent service runs
are started. The unit retains a failure status for all-unknown samples; configure
the operator's existing unit-failure monitor after installation if alerts are
needed. No notification sender is bundled.

To stop sampling: `sudo systemctl disable --now availability.timer`; let an
in-flight one-shot finish. Keep the ledger. Neither installation nor rollback
instructions delete observations. Existing historical campaign data can be
seeded only as a separately authorized, byte-preserving custody operation.

### Ownership, maintenance and qualification limits

`observations.jsonl` is append-only evidence. `heatmap.html` and `heatmap.txt`
are disposable machine-generated projections. Scripts, fixtures, units, config,
README and BUILD-REPORT are steward-owned. API fields, GPU slugs, scopes,
pagination and Hot Aisle region mapping can rot; parser ambiguity is unknown.
Clock accuracy and missed timer runs affect sampling coverage. Python uses no
third-party packages; the systemd host needs Python 3.9+ and CA certificates.

Live credentials and systemd behavior remain UNVERIFIED: no provider API calls
with credentials, provisioning, installs, commits, pushes or branches were made.
See BUILD-REPORT.md for exact tests, the N01 contact failure and cleanup status.
