# Lane C build report · 2026-09-24

Built the availability probe, separate delivered-attempt helper, seven-day
heatmap and uninstalled N01 deployment kit. All implementation changes are
inside `hot-aisle/campaign/availability/`. No commits, branches, pushes,
provider provisioning, credentialed API calls or installations were performed.

## Files built

| File | Purpose |
|---|---|
| `probe.py` | Standard-library GET adapters, fixture dry-run, append-only listed observations, operator-attested delivered helper and self-test entry point |
| `probes.json` | Twelve fixed provider/SKU/region/GPU targets; explicit Hot Aisle verification holds |
| `heatmap.py` | 168 UTC hourly columns, separate listed and delivered denominators, inline SVG HTML and plain-text summary |
| `heatmap.html`, `heatmap.txt` | Reproducible projection of the existing 15-line ledger through 2026-09-23 23:59:59 UTC |
| `fixtures/digitalocean.json`, `fixtures/hotaisle.json` | Synthetic provider API response fixtures |
| `fixtures/observations.jsonl` | Synthetic arithmetic fixture exercising available, unavailable, unknown and delivered attempts |
| `fixtures/delivered.json` | Receipt-field example, marked synthetic and rejected by the real append helper |
| `test_availability.py` | Nineteen offline tests, including actual CLI subprocesses |
| `availability.service`, `availability.timer` | Read-only one-shot, post-run rendering even on probe failure, UTC quarter-hour cadence |
| `availability.env.example` | Blank token environment-file template |
| `README.md` | Extended run, evidence, public-source, install and maintenance instructions |
| `BUILD-REPORT.md` | This handoff |

The existing `observations.jsonl` was not appended, rewritten or normalized.
Before/after SHA-256:

```text
79c66c657b5a9bbd3b74dece8306fe843a11e763fe9b8f407bc3129d3e6861f7
```

## Run

From `hot-aisle/campaign/availability/`:

```sh
python -B probe.py --self-test
python -B heatmap.py --self-test
python -B test_availability.py
python -B probe.py --dry-run
python -B heatmap.py --now 2026-09-23T23:59:59Z
```

The first three commands run the same suite. Dry-run uses only fixtures, prints
synthetic JSONL and does not append to the campaign ledger. See README for the
live sampling command, receipt helper and staged N01 install commands.

## Test output and checks

Final run on Windows / Python 3.13:

```text
probe.py --self-test:   Ran 19 tests in 0.478s — OK
heatmap.py --self-test: Ran 19 tests in 0.492s — OK
heatmap.py --now 2026-09-23T23:59:59Z:
  Wrote heatmap.html and heatmap.txt; 15 source records
```

Verified missing-token unknowns without network use; all-unknown CLI exit 1
after appending; dry-run isolation; exact DigitalOcean GPU count and region
matching; available/unavailable Hot Aisle fixture quantities under an explicit
test mapping; unverified regional holds; pagination; redirect/cross-origin
credential protections; 401/403/429/500, timeout and malformed responses;
credential omission from observation output; real-create and SSH receipt
validation; duplicate refusal; append-prefix preservation; incomplete-tail
refusal; writer locking; UTC hour boundaries; synthetic/old/future/manual
exclusion; legacy create evidence; HTML escaping; parseable SVG with 168 cells
per row; and independent listed and delivered denominators.

The arithmetic fixture yields listed **1/2**, unknown **1**, missed **1/4**
quarter-hour slots and delivered **1/2** in its observed hour. The campaign
projection has **0 valid API probes**, **one historical confirmed-SSH attempt**,
and **14 excluded manual listings/notes**. Grey cells accurately show the absence
of API history. No new availability result is asserted.

Not run: real provider credentials, API quota behavior, native Linux/systemd
activation, screen-reader qualification or rendered light/dark browser review.
The browser skill was used to attempt local visual QA, but Browser URL policy
blocked the local file URL and prohibited workarounds. Automated HTML/SVG checks
passed; both colour schemes are implemented in CSS, not visually qualified.

## Open questions and operator inputs

1. Supply `DIGITALOCEAN_TOKEN` with `sizes:read` and its required `regions:read`
   scope. Bearer auth and size response fields were verified against public docs.
2. Supply `HOTAISLE_API_TOKEN` and the intended team. Confirm the `Token` auth
   prefix and full team endpoint, then set `hotaisle.auth_status` to `verified`.
   The official client confirms the base URL and Authorization header, but the
   public docs did not expose readable auth details during this build. These
   remaining facts are explicitly **UNVERIFIED**, not silently assumed live.
3. Verify whether that Hot Aisle endpoint's inventory is confined to ENC1 before
   setting `hotaisle.region_scope` to `enc1`. Its documented availability objects
   have no region field. Leaving this unset deliberately yields unknown.
4. Authorize and coordinate N01 installation, token custody and the ledger
   location. The install kit starts a new operational ledger; copying historical
   evidence is a separate custody decision. Native `systemd-analyze verify` and
   a first-sample inspection are in the instructions. No model/image pins apply.
5. Real creates remain separately authorized work. Their operator must supply a
   unique attempt ID, retained evidence reference, timestamp, outcome and actual
   SSH evidence to the helper. Listing probes never write delivered observations.

Sources and verification limits are linked in README; four public search queries
were used, within the lane's eight-search cap. No provider was contacted with
credentials and nobody was messaged.

## Front-door and local environment limitations

The supplied root instructions require the Estate front door. Estate resolved
through `python D:\Projects\where.py estate`; the canonical policy was read.
`estate_peer.py probe OCTO-N01` failed before connecting because its configured
runtime could not write `S:\Scratch\Runs\Estate-Peer\known_hosts`
(`PermissionError`). N01 contact therefore remains unestablished. No alternate
peer, direct SSH or Estate recovery action was attempted. The explicitly
authorized local lane build proceeded; this is not an N01 deployment receipt.

The initial test run failed because Python 3.13's mode-0700 temporary directories
on Windows excluded the sandbox token. Tests now create UUID-named directories
with inherited lane ACLs and clean them successfully. The initial run left 18
empty temporary directories which the sandbox could neither inspect nor remove
even with nonrecursive deletion. These are local cleanup residue, not kit files;
no test successfully wrote into them. An authorized owner session must remove
these exact empty directories from this lane (no recursive deletion is needed):

```text
tmp13irw4gz  tmp3hqoel01  tmp7hvitken  tmp9htnl1y8  tmp9rqq2alk  tmpaat3maux
tmpde_ki9rg  tmpgl89kane  tmpiiblti61  tmpkt5_wfle  tmpmxyvi_br  tmpo2ze9e41
tmpoemdmywy  tmpov89a2k3  tmps8ljtmdg  tmpv6jlozc8  tmpwdq52sbb  tmp__k9pn_t
```

Git read-only checks used a per-command `safe.directory` option after Git
reported repository ownership mismatch; no global Git configuration was changed.

## Fix round 1

Completed only Lane C from `build-2026-09-24/fix-A-C.brief`. All edits are
inside this availability directory; no commits, branches, pushes, provider API
calls, provisioning or installation occurred.

Files changed:

- `probe.py`: delivered receipts require and preserve `api-create`,
  `console-create` or `tui-provision`, and emit `layer: delivered`.
- `fixtures/delivered.json`, `fixtures/observations.jsonl`: use the concrete
  create methods; the example receipt includes the delivered layer.
- `heatmap.py`: missed slots begin at each tuple's earliest real API
  observation, including unknown observations and observations before the
  visible week. Earlier hours/quarters are labelled not sampled. Rows without
  API history have no missed slots. Duplicate probes still fill only one slot.
- `fixtures/digitalocean-page1.json`: added a synthetic pagination response
  with `links.pages.next`; the second page is `digitalocean.json`.
- `test_availability.py`: verifies concrete receipt methods and rejections,
  pagination contents/URLs/auth, separate tuple sampling starts, mid-hour starts,
  older history, exclusions, and delivered tuples outside the configured list.
- `README.md`: updated field contract, sampling semantics, DigitalOcean
  configuration-versus-capacity limitation (UNVERIFIED until compared with
  console observations), September 23 H200 console observations, and expected
  quarter-hour alert noise before tokens exist.
- `heatmap.html`, `heatmap.txt`: regenerated from the original campaign ledger.

Run from this directory:

```sh
python -B test_availability.py
python -B probe.py --self-test
python -B heatmap.py --self-test
python -B heatmap.py --now 2026-09-23T23:59:59Z
```

Test results on Windows / Python 3.13: **23 tests passed** in each of the three
entry points. Both self-test entry points include CLI tests, offline pagination,
receipt validation, denominator checks and HTML/SVG parsing. Reproduction wrote
both heatmap files from 15 source records: every configured row now has missed
0 and not sampled 672 slots, retaining one historical SSH success and 14
excluded manual records. The operational ledger SHA-256 remains
`79c66c657b5a9bbd3b74dece8306fe843a11e763fe9b8f407bc3129d3e6861f7`.
Lane-scoped `git diff --check` passes. No native browser or systemd/live-provider
qualification was performed in this fix round.

Cleanup status supersedes the earlier residue note: directory inspection before
and after this round found only `fixtures/`; none of the old `tmp*` directories
were present, and tests left no `tmp*`, `.selftest-*` or `test-tmp-*` directories.

Open questions and operator inputs remain the deployment items above: provider
tokens, verified Hot Aisle auth/path and regional scope, console/API capacity
comparison, and coordinated installation authorization/custody. Real delivered
receipts additionally need the actual create method; no method is inferred.

The required canonical N01 probe was attempted again and failed before connecting
with PermissionError writing `S:\Scratch\Runs\Estate-Peer\known_hosts`.
N01 contact remains unestablished; no alternate route or recovery was attempted.
Only the explicitly requested local lane fixes proceeded.
