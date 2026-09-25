# The counter · evaluation protocol

The customer-facing side of a shop evaluation: everything observable from
signing up through releasing the machine, without touching the GPU. Any
operator can use this checklist with a declared time and spending cap.
Two hours and $10 are planning estimates, not field-qualified bounds. The
historical Hot Aisle record (`records/hotaisle-2026-09.json`) was compiled from
retained campaign evidence; it was not produced by an end-to-end run of this
protocol. Its unknown fields remain work for a fresh evaluation.

Fill `counter_record.schema.json` as you go (`second-run/counter-record@1`).
**Every field you did not actually observe stays the literal string
`"unobserved"`. Never guess, never carry a value in from a pricing page you
didn't personally read this session, never assume "self-serve" implies "no
quota gate."** `counter_record.py validate` will accept `"unobserved"`
anywhere a real value is expected but will reject a missing field.

Budget: **$20 sign-up minimum (if one exists) + up to $3 for three timed
provisioning attempts + incidentals** should comfortably stay under $10 net
spend once the machine is deleted (prepaid credit balances are not spend).
Keep every receipt/invoice screenshot; `provenance.money_spent_usd` is the
actual dollars charged, or `"unobserved"` until reconciled. Put modeled
estimates in `provenance.modeled_cost_usd`, with their scope in the disclosure.
Disclosure does not turn an estimate into an observed charge.

The numeric checklist score is uncalibrated and cannot rank providers. Missing
observations are not evidence that an operator meets the floor. The historical
"Hot Aisle-grade" examples below identify particular observed behaviors, not
a validated universal standard or a fleet guarantee.

Each step below: what to do, what to record, what "Hot Aisle-grade" looks
like, what disqualifies the shop outright (append the observation's own text
to `disqualifying_observations`; that field's mere non-emptiness caps the
whole record at 40/100 in `counter_record.py score`, regardless of every
other number).

## 1. Account creation friction

**Do:** Start sign-up with a fresh email. Note every screen before you can
attempt a create: KYC/ID upload, card entry, a quota that starts at zero, a
"contact sales" wall.

**Record:** `account_creation.kyc_required`, `card_required`, `quota_gate`
(`none` / `soft` / `hard` / `sales`), `sales_gate`,
`signup_to_active_account_s` (stopwatch from first sign-up screen to first
successful create attempt, whether or not it succeeds).

**Hot Aisle-grade:** self-serve, no sales team, no KYC beyond a card;
prepaid Stripe credit, $20 minimum. `quota_gate: none`, `sales_gate: false`.

**Disqualifying:** a sales conversation is required before you can attempt
any create on the SKU under test (`sales_gate: true` and no workaround).

## 2. Price transparency

**Do:** Find the SKU's price without logging in. Read the pricing page and,
separately, the billing/docs page; note if they disagree (Hot Aisle and
DigitalOcean both have known page-vs-docs mismatches worth specifically
checking for).

**Record:** `price_transparency.published`, `per_gpu_hour_usd`,
`minimum_billing`, `egress_rate`, `storage_rate`.

**Hot Aisle-grade:** public pricing page, no login; $/GPU-hr stated per SKU;
minimum billing window stated in one place consistently ("1 minute" for the
1x MI300X VM).

**Disqualifying:** the price for the SKU under test is not published
anywhere without a sales conversation.

## 3. Provisioning: time to SSH

**Do:** Time from the moment you submit "create" to the moment `ssh` first
succeeds. Do this **3 times** if 3 × the SKU's hourly rate stays under $3
(true for any SKU at or below ~$1/GPU-hr-equivalent given a few minutes each
— for a $2.99/GPU-hr MI300X VM, three ~2-minute attempts costs well under
$1 total at 1-minute-minimum billing). Delete the machine the moment SSH is
confirmed each time.

**Record:** `provisioning.attempts[]` (`request_ts`, `ssh_ready_ts`,
`time_to_ssh_s` per attempt), `measured_3x`, `total_cost_usd`.

**Hot Aisle-grade:** under 3 minutes request-to-SSH (Run 3: 122s, 00:08:55Z
to 00:10:57Z).

**Disqualifying:** a create that reports success but never reaches SSH
(record it as its own attempt with `ssh_ready_ts: "unobserved"`; if this
happens on more than one of three attempts, add it to
`disqualifying_observations`).

## 4. Availability honesty

**Do:** For the SKU under test (and 2-3 adjacent SKUs/regions if cheap to
check), compare what the listing/console/API says is available against
whether a real create actually succeeds. Do this at more than one time of
day if the schedule allows — Hot Aisle's own listing visibly changes hour to
hour and day to day.

**Record:** every attempt, in the shape the campaign's own
`availability/observations.jsonl` ledger uses (`ts`, `provider`, `region`,
`sku`, `gpus`, `method`, `layer`, `outcome`, `provisioned`; see
`../../availability/README.md` for the full field rules), mirrored into
`availability_honesty.ledger_attempts[]` here so this record is
self-contained. **Write the same rows to the real ledger too** if you are
running this against a shop the campaign already tracks — this protocol
does not replace that ledger, it feeds it.

Keep listing observations separate from actual create attempts. A listing that
was not requested is not a failed create. Report delivery counts per SKU and
region, with the observation times; do not pool unrelated plans or regions into
an availability percentage. The legacy `availability_honesty` field name does
not establish a provider's intent or truthfulness.

**Hot Aisle-grade:** a SKU shown as available in the TUI provisions when you
actually request it (Run 3: listed 00:02:15Z, delivered 00:10:45Z, same SKU,
same region).

**Disqualifying:** the listing/console consistently shows a SKU as available
while every real create attempt against it fails (`out_of_capacity` /
`create_failed`) — a systematically fake-available listing.

## 5. API / CLI / TUI quality

**Do:** Issue an API token (or confirm none exists / it's manual). Run
list, create, and delete through whatever programmatic surface exists
(API, CLI, or TUI — Hot Aisle's admin TUI and DigitalOcean's `doctl` both
count). Deliberately repeat one create call and one delete call to check
idempotency.

**Record:** `api_cli_tui_quality.token_issuance`, `list_op`, `create_op`,
`delete_op`, `idempotent_create`, `idempotent_delete`.

**Hot Aisle-grade:** self-serve token issuance; list/create/delete all work
without a support ticket; a registered SSH key logs into the TUI directly.

**Disqualifying:** create or delete cannot be done programmatically at all
(sales- or ticket-mediated only) for a shop otherwise marketed self-serve.

## 6. Billing granularity and stop-on-delete

**Do:** Note the account balance or an invoice line immediately before and
immediately after deleting the machine. Confirm the delta matches the
billed duration at the stated per-second/per-minute rate and minimum.

**Record:** `billing_granularity.billing_quantum`,
`stop_on_delete_verified` (true only if you actually diffed
balance/invoice around the delete), `invoice_matches_balance`.

**Hot Aisle-grade:** billing stops at delete, confirmed against the account
balance, not just claimed on a docs page (Hot Aisle: VM deleted from the
TUI, billing stops at delete).

**Disqualifying:** billing continues to accrue after a confirmed delete.
This is the single most direct trust breach the counter can catch — treat
any confirmed instance as a disqualifying observation even if the amount is
small.

## 7. Tenant hygiene

**Do:** The instant you have SSH, before touching anything: check
`/home`, `/root`, `/tmp`, shell history files, and `~/.ssh/authorized_keys`
for anything you didn't put there.

**Record:** `tenant_hygiene.fresh_disk`, `previous_tenant_residue`,
`default_users_keys_present`.

**Hot Aisle-grade:** empty home directories, empty shell history, only the
SSH key(s) you registered.

**Disqualifying:** any file, credential, key, or shell history from a
previous tenant. This is a hard fail regardless of anything else measured
(`score_tenant_hygiene` in `counter_record.py` already scores this 0/100 on
its own; also add it to `disqualifying_observations`).

## 8. Network path

**Do:** Note whether the box gets a public IP by default. Run a port scan
(or `ss -tlnp` / `netstat` from inside, plus an external scan if you have
one handy) immediately after first boot, before opening anything yourself.

**Record:** `network_path.public_ip_assigned`, `firewall_default`
(`open` / `closed` / `unknown`), `open_ports_first_boot` (list of ports, or
`[]` if a scan ran and found none — only use `"unobserved"` if no scan ran
at all).

**Hot Aisle-grade:** public IP assigned; only SSH open by default, or a
clearly documented default-deny firewall.

**Disqualifying:** a database, management interface, or other sensitive
service is reachable from the public internet on first boot with no
warning.

## 9. Support path

**Do:** Ask one real, answerable question through whatever support channel
exists (chat, email, ticket, community). Time the first human (not bot)
response.

**Record:** `support_path.channel`, `first_response_time_s`,
`sales_required`.

**Hot Aisle-grade:** a channel exists and does not route through sales.

**Disqualifying:** no support channel can be found at all, or the only path
found is a sales contact form, for an issue unrelated to purchasing.

## 10. Termination

**Do:** Delete the machine through the same surface you created it with (or
whichever surfaces are available). Time how long until it disappears from
the active-resources list.

**Record:** `termination.method`, `billing_stopped_confirmed` (cross-check
against step 6), `time_to_confirm_s`.

**Hot Aisle-grade:** self-serve delete (console/TUI/API), reflected quickly
in the active list, billing stopped (Hot Aisle: TUI delete).

**Disqualifying:** deletion requires a support ticket, or billing does not
stop (same disqualifying condition as step 6 — record it once, it caps the
score either way).

## After the run

```sh
python -B counter_record.py validate records/<provider>-<yyyy-mm>.json
python -B counter_record.py score    records/<provider>-<yyyy-mm>.json
python -B counter_record.py compare  records/hotaisle-2026-09.json records/<provider>-<yyyy-mm>.json
```

Fill `provenance` last, honestly: who ran it, when, which account, how much
was actually spent net of any credit, and the one-line disclosure this
campaign's `DISCLOSURES.md` convention expects (funding relationship, or
"none"). Leave `disqualifying_observations` empty unless something in steps
1-10 above actually triggered it — do not pre-fill it defensively.
