# Shop evaluation manual

Turnkey instructions to evaluate one GPU compute shop against the reference operator, Hot
Aisle, and produce a report that says what the shop does wrong, right, and could do better.
Written so a stranger with a card and an SSH key can follow it in one day for roughly $10,
without asking anyone a question. If a step here conflicts with a script's own `--help` or
header comment, the script wins; file an issue against this manual instead of guessing.

This extends the pattern in `../README.md` (the three-arm Hot Aisle/DigitalOcean run sheet)
to any shop, one at a time, with a fixed reference instead of a live three-way comparison.

## What this measures

- **The workload bench**: throughput and tail latency serving `Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8`
  under `../arm.sh`'s pinned cells (concurrency 1/8/32/64, 3 repeats, 200 prompts each), scored
  by `../engine_table.cjs` against the same acceptance gates as the Hot Aisle campaign (p95 TTFT
  ≤ 1000 ms, p95 E2E ≤ 15000 ms, failure ≤ 1%): $/1k accepted requests, at the shop's own list
  rate.
- **The machine itself**: `probe/fingerprint.sh`'s snapshot of kernel, virtualization, CPU, RAM,
  storage, network, container runtime, GPU hardware/driver/topology, and a 60-second load sample
  — compared to the reference with `probe/diff.py`.
- **The buying experience** ("the counter"): sign-up friction, price transparency, time to SSH,
  API/CLI/TUI quality, billing granularity, tenant hygiene, network exposure on first boot,
  support responsiveness, and clean termination — recorded by hand per `counter/PROTOCOL.md` and
  scored by `counter/counter_record.py`.
- **All three together**, reconciled against the Hot Aisle reference, by
  `diagnose/diagnose.py`, into one `REPORT.md` per shop.

## What this does not measure

- Output quality or correctness of model responses (the bench scores latency and acceptance,
  not answer quality — see `../DISCLOSURES.md`'s "format, not capability" note from Run 3).
- Multi-GPU or multi-node behavior. Every arm here is a single GPU, tensor-parallel 1.
- Anything about a shop's larger fleet, support-tier SLAs, or negotiated/discounted pricing.
  This kit only ever pays and reports list price, one seat, self-serve.
- The shop's invoice-accuracy over a full billing cycle (only the one evaluation window).
- A statistically confident verdict. One shop, one day, one seat is a sample, not a census.
  Run it again a different week if a result looks surprising before trusting it.

## Prerequisites

- **A payment card and an account** at the shop under test, in your name or your
  organization's, per that shop's sign-up flow. Nobody else can do this step for you (see
  "What only the human does" below).
- **An SSH key pair.** Public half goes on the shop's console/account before you rent
  anything; the private half stays on your machine, and its path is passed to `evaluate.sh`
  as the fourth argument if it is not `~/.ssh/id_ed25519` or already loaded in `ssh-agent`.
  **Quote the key path** if it contains spaces (this happens: an operator's home directory
  can itself have a space in it, e.g. `"/mnt/c/Users/Jonathan Sandhu/.ssh/id_ed25519"`).
- **A Linux box or WSL** to run `evaluate.sh`, `collect.sh`, and the scoring/diagnose steps
  from. It needs `bash`, `ssh`, `scp`, `python3` (3.9+, standard library only — nothing here
  needs `pip install`), and `sha256sum`.
- **Node.js** (any recent LTS) on that same box, to run `../engine_table.cjs`.
- Roughly **$10** in card spend for the shop's compute, plus whatever the shop's own sign-up
  requires (some want a minimum card-load; that is the shop's money, not this kit's, and does
  not count against the $10 estimate).
- Fifteen minutes of your own attention at the start (sign-up, key upload, rent the seat) and
  the end (read the log, delete the machine); the middle 45–90 minutes is unattended.

## The one-day sequence

Run every command from `shop-eval/` (this directory) unless told otherwise. Each step names
its own time and money; totals are in the summary table at the end.

| # | step | who | time | money |
|---|---|---|---|---|
| 1 | Counter: sign up, note friction, price, quota gate | you | 15–30 min | $0 (before renting) |
| 2 | Rent one 1-GPU seat (self-serve, console or CLI) | you | 1–25 min | $0 (billing starts at create) |
| 3 | Fingerprint the machine | `evaluate.sh` over ssh | ~90 s | included in seat time |
| 4 | `arm.sh serve <kind>`: pull image, health, warm-up | `evaluate.sh` over ssh | 5–25 min (stop rule below) | included |
| 5 | `arm.sh bench <kind>`: 12 cells | `evaluate.sh` over ssh | up to 50 min (watchdog) | included |
| 6 | `collect.sh`: pull results back, verify manifest | `evaluate.sh`, local | 1–2 min | $0 |
| 7 | **Delete the machine** | you, in the shop's console | 1 min | stops the meter |
| 8 | Score: `engine_table.cjs` | `evaluate.sh`, local | seconds | $0 |
| 9 | Diagnose: `diagnose/diagnose.py` against the reference | `evaluate.sh`, local | seconds | $0 |
| 10 | Finish the counter record; file everything | you | 10–15 min | $0 |

Steps 3–6 run as one `evaluate.sh` invocation (see below); steps 8–9 run automatically at the
end of the same invocation if the scoring rate and the diagnose lane's files are in place.
Typical total: **~2.5 hours wall clock** (mostly steps 4–5, unattended), **~$5–9** at a
sub-tie-line rate (see `SHORTLIST.md`'s cost model — 2.5 h at the shop's rate, rounded to a
full billed hour if the shop has a 1-hour minimum). A same-silicon shop priced above Hot
Aisle can run higher; check `SHORTLIST.md`'s per-shop estimate before renting.

### Exact commands

```sh
# 0. From shop-eval/, confirm the shop and kind you're running (see SHORTLIST.md for the order).
shop=latitude            # short slug: lowercase, no spaces, matches providers.jsonl's provider_id
kind=nvidia               # amd or nvidia -- matches the GPU vendor of the seat you rented

# 1. Counter (before renting; see counter/PROTOCOL.md for the full walkthrough).
#    Sign up, note timestamps and answers as you go. You'll fill the record file after step 7.

# 2. Rent the seat yourself, in the shop's own console/CLI/TUI. Upload your SSH public key
#    first if the shop requires it uploaded before create. Note the request timestamp for
#    the counter record's provisioning.attempts. Wait for SSH to answer; note that timestamp
#    too (this is your time-to-SSH figure).

# 3-6. From your Linux box / WSL, once SSH answers:
bash evaluate.sh "$shop" "$kind" user@host.example.com [/path/to/key/with a space/id_ed25519]
#    This copies probe/fingerprint.sh, ../arm.sh, and ../cells.$kind.sh to the machine, runs
#    fingerprint -> serve -> bench there under nohup (survives a dropped connection), polls
#    until done, then runs ../collect.sh and copies results into runs/<shop>-<date>/.
#    It prints a log to runs/<shop>-<date>/evaluate.log as it goes.

# 7. STOP. Delete the machine now, in the shop's own console. evaluate.sh never does this.
#    Note the delete timestamp for the counter record's termination section, and check the
#    account balance/invoice a few minutes later to confirm billing actually stopped.

# 8-9. If you know the rate you were actually billed, re-run scoring/diagnose with it
#    (evaluate.sh already tried this if SHOP_RATE was set before you ran it):
SHOP_RATE=1.68 bash evaluate.sh "$shop" "$kind" user@host.example.com   # idempotent; re-scores in place

# 10. Fill counter/records/<shop>-<yyyy-mm>.json per counter/PROTOCOL.md, then:
python3 counter/counter_record.py validate counter/records/"$shop"-2026-09.json
python3 counter/counter_record.py score    counter/records/"$shop"-2026-09.json
```

`evaluate.sh` prints, at every stop (success or failure), exactly what you still have to do —
read that block before doing anything else. It is reproduced in outline in "What only the
human does" below.

## Stop rules

Carried directly from `../README.md`'s run sheet; they apply per shop, not per campaign.

- **Health not passed in 25 minutes → delete the machine and read the log.** `arm.sh serve`
  enforces this itself (it exits after 25 minutes with the last 40 log lines printed); if the
  shop's image pull or model load is simply slow through no fault of the shop, that is itself
  a finding, not a bug to route around. Do not raise the timeout to force a pass.
- **Bench watchdog:** `arm.sh bench` stops before starting a new cell once `MAX_BENCH_MINUTES`
  (default 50) has elapsed since the bench began; whatever cells completed stand, the rest are
  simply missing from the report, and the report says so.
- **Per-step spend cap:** if step 4 (serve) alone is approaching $5 of billed time with no
  health yet, stop it (`ssh host 'bash arm.sh stop'` if you can still reach it, otherwise just
  delete the machine) rather than let a stuck pull run out the clock.
- **Whole-shop spend cap:** if total spend for one shop's evaluation (steps 1–9) is
  approaching $15, stop wherever you are, delete the machine, and file the evaluation as
  partial. A retry of the compute steps alone is usually $5–10; do not compound a stuck run by
  restarting it repeatedly without changing anything.
- **Out-of-memory or a failed cell is a result, not a retry.** The cell fails, the manifest
  says which one, and the other cells still stand (see `../README.md`'s own retry-knob list
  for the difference between a real failure and a genuine retry case, e.g. a wrong runtime
  digest).

## What only the human does

`evaluate.sh` and the probe/counter/diagnose tools never touch a payment method, a console
button, or a deletion. Specifically, only you:

1. Create the account at the shop (email, card, any KYC) and record the friction for the
   counter score.
2. Upload your SSH public key to the shop's account/console.
3. Click (or CLI/TUI-invoke) "create" for the one-GPU seat, and record the request timestamp.
4. Note when SSH first answers (time-to-SSH), and hand `evaluate.sh` that `user@host`.
5. **Delete the machine** when `evaluate.sh` stops (whether it finished cleanly or not).
   Confirm the balance/invoice reflects the delete a few minutes later.
6. Answer the counter protocol's one real support question, by hand, and record the response
   time.
7. Enter the real invoice line once it posts (list-rate estimates in this kit's outputs are
   not the same as what you were actually charged; both are kept, per `../DISCLOSURES.md`'s
   convention of showing modeled and billed numbers side by side).
8. Decide whether the shop is added to the roster (`providers/providers.jsonl`) and whether
   to publish the report.

## Disclosure rules

Follow `../DISCLOSURES.md`'s existing convention; every `REPORT.md` and counter record carries
its own provenance line, not a footnote buried elsewhere.

- **State plainly who paid.** "Self-funded at list price" or "$X credit from the shop" — say
  which, in the counter record's `provenance.disclosure` field and in `REPORT.md`'s
  provenance line. A shop-provided credit is not disqualifying, but it is never silent.
- **Cost figures are list price unless marked otherwise.** If a credit or discount was used,
  the report still headlines the undiscounted list-price cost (as `../DISCLOSURES.md` does for
  the Hot Aisle arms), and separately notes what was actually billed to the card.
- **No exclusions, no ceremony, one line.** Per this kit's own house rule: state the funding
  relationship once, plainly, where the number appears. Do not add a disclaimer section that
  argues the relationship doesn't matter — say what it is and let the reader judge.
- **Relationship, not just money.** If the evaluator has any other relationship to the shop
  (an existing account, a prior conversation with their team, a referral), say so in the same
  line as the funding disclosure.
- **Never silently mix modeled and billed numbers.** Label every cost figure `modeled` (from
  `engine_table.cjs` at list rate) or `billed` (from the actual invoice) and never average
  them into one unlabeled number.

## How to name and file outputs

Everything from one evaluation lands under:

```
shop-eval/runs/<shop>-<yyyy-mm-dd>/
├── counter.json           # copy of counter/records/<shop>-<yyyy-mm>.json as of this run
├── fingerprint/
│   ├── fingerprint.json
│   ├── raw/                # fingerprint.sh's raw command output, one file per check
│   └── MANIFEST.sha256     # fingerprint.sh's own manifest (fingerprint.json + raw/*)
├── bench/                  # env.json, cell-*.json, cell-*.log from arm.sh + collect.sh
├── engine_table.json       # engine_table.cjs's per-cell scoring output
├── REPORT.md               # diagnose.py's output, or report_template.md filled by hand
├── evaluate.log            # evaluate.sh's own step-by-step log
└── MANIFEST.sha256         # sha256 of every file above, written last by evaluate.sh
```

`<shop>` is the same lowercase slug used as `provider_id` in `providers/providers.jsonl`
(e.g. `latitude`, `voltage-park`, `amd-devcloud`, `hotaisle`). `<yyyy-mm-dd>` is the UTC date
`evaluate.sh` started on. If you evaluate the same shop twice in one day, add a `-2` suffix
(`latitude-2026-10-01-2`) rather than overwrite the first run — both are evidence.

`evaluate.sh` builds this tree itself except for `counter.json`, which you copy in by hand
after filling out the counter record (step 10) — the counter protocol runs partly before the
machine exists, so it cannot be fully automated by a script that only runs after you have SSH.

Note that `../collect.sh` (called by `evaluate.sh`) also writes its own copy of the bench
results under `../results/<shop>/`, because that is where the shared campaign tooling always
looks. `evaluate.sh` copies that same data into `runs/<shop>-<date>/bench/` for you, but the
`../results/<shop>/` copy is not deleted — leave it there; other lanes' tools expect it.

## How to add the shop to providers.jsonl and the availability ledger

1. Open `../providers/providers.jsonl`. Each line is one JSON object; follow the field shape
   already used there (`provider_id`, `provider_name`, `offer_id`, `gpu`, `vendor`, `memoryGB`,
   `gpus`, `rate_usd_per_gpu_hour`, `rate_basis`, `kind`, `minimum_billing`, `regions`,
   `self_serve`, `availability_observed`, `availability_ts`, `source_url`, `source_quote`,
   `retrieved_at`, `campaign_role`, `notes`, `lane`, plus the modeled columns if you can compute
   them). Add one line per SKU actually evaluated, with `notes` pointing at
   `shop-eval/runs/<shop>-<date>/` as the evidence, not just the pricing page.
2. Update `../providers/PROVIDERS.md` and `../providers/TARGETS.md` by hand to match — these
   are generated summaries of `providers.jsonl` in this campaign's current build, not
   auto-regenerated; a mismatch between the JSONL and the Markdown is worse than no update.
3. Append one observation per provisioning attempt to the availability ledger, following
   `../availability/README.md`'s exact field list (`ts`, `provider`, `region`, `sku`, `gpus`,
   `method`, `layer`, `outcome`, `provisioned`, plus `attempt_id`, `evidence`,
   `real_create_attempt`, `ssh_reached`, and `time_to_ssh_s` for a delivered attempt). Use
   `method: console-create` or `tui-provision` (whichever you actually clicked), `layer:
   delivered`, and cite `runs/<shop>-<date>/evaluate.log` as the evidence reference. Do this
   whether or not the create succeeded — a failed or out-of-stock attempt is exactly the kind
   of evidence this ledger exists to hold.
4. Do not touch `../availability/observations.jsonl` with anything but the append-only helper
   described in `../availability/README.md`, if one is running on N01; if you are recording by
   hand, follow that README's field list exactly and never edit or reorder existing lines.

## How to compare across shops

- **One shop at a time, same reference.** Every `REPORT.md` is produced against the same
  `diagnose/reference/hotaisle-2026-09.json`, so any two `REPORT.md`s are directly comparable
  to each other through that shared reference — you do not need to re-run Hot Aisle for every
  new shop.
- **Line up the one table.** `report_template.md`'s single table (rate, $/1k accepted, ×Hot
  Aisle, TTFT p95, accepted %, time-to-SSH, counter score) is the same shape in every report;
  stack them to build a leaderboard. The `×Hot Aisle` column is the number that survives a
  price change on either side — prefer it over the raw `$/1k accepted` when ranking shops.
- **Never rank on modeled cost alone.** Fold in the counter score before calling a shop
  better than Hot Aisle; a cheap seat with a hard quota gate, no working delete, or previous-
  tenant residue on disk is disqualified regardless of its bench number (see
  `counter/counter_record.py`'s `DISQUALIFYING_CAP`).
- **Keep the fingerprint diffs.** `probe/diff.py reference.json candidate.json` surfaces
  hardware/driver differences that can explain a bench gap before you credit or blame the
  shop's operations for it (e.g. a different ROCm/CUDA point release, a throttled clock, fewer
  PCIe lanes).
- **Re-run before publishing a surprising result.** One seat, one day is a sample; if a shop's
  number is far better or far worse than expected, that is the case for a second run on a
  different day before anyone quotes it, not a reason to publish faster.
