# circulate

One driver runs the whole public-data path on real sources, leaves a receipt, and the probes try to break every joint. Rules are in [CONTRACT.md](CONTRACT.md); this file is how to run it, read a receipt, and add a stage or a probe.

Stdlib Python 3.10+, `node` (page engine, Research Desk packet), `gh` (GitHub reads, authenticated). No packages.

## Run it

```text
python circulate/circulate.py                      # online, all ten stages, writes committed outputs
python circulate/circulate.py --offline            # every stage on circulate/fixtures/, no network, writes only under circulate/
python circulate/circulate.py --stage prices status
python circulate/circulate.py --resume 2026-09-29  # re-run only stages that are missing or FAIL in that receipt
python circulate/circulate.py --retained D:\scratch\circ
python circulate/circulate.py --finalize 2026-09-29   # recompute overall/index after PROBES.json was written
python circulate/probes/run_probes.py              # writes receipts/<today>/PROBES.json (then run --finalize)
python -m unittest circulate.tests.test_offline    # from the repo root: the offline end-to-end assertion
```

Exit codes: `0` overall OK, `2` a stage FAILed / a frozen file moved / a probe FAILed, `1` driver error.

Flags: `--stage` (repeatable) runs only those stages and keeps earlier results for the rest; `--resume DATE` reuses a completed stage only if every output it recorded still has the recorded SHA-256 (stage result files are written the moment a stage finishes, so a killed run resumes cleanly); `--retained DIR` is where bulk outputs go; `--date` overrides the receipt date (tests use it).

Environment: `CIRCULATE_INJECT_SLEEP_STAGE=<name>:<seconds>` appends one extra final stage that sleeps (probe p09 kills the driver during it). `CIRCULATE_SESSIONS` points at the folder that holds the local research session lanes (default `<repo>/../sessions`); they are used only to verify a baseline or reproduce the base packet, never as the source of a number. `CIRCULATE_RATE_SLEEP_CAP` (seconds, default 900) is the longest the driver will sleep for a GitHub rate-limit reset before recording HOLD.

## Offline mode

`--offline` uses `circulate/fixtures/` only (three InferenceX artifacts and their listing, a 50-row price slice and the release response, one Atlassian history page with its incidents, one Better Stack quarter, three Instatus months, one SorryApp month, three newsletter posts and a sitemap, the Run 3 record, 40 imported rows). It pretends the day is 2026-09-29 so those windows line up, and every write that would land on a committed path goes to `retained/offline/sandbox/<same path>` instead. The receipt goes to `receipts/<date>/` (or `<date>-offline/` if a real receipt for that date exists; those folders are gitignored). `index.json` and `LATEST.md` are not touched offline. Two stages are reduced so a fixture run takes about half a minute: `r2-standing` re-evaluates the frozen R2 data at low draw counts and labels the output OFFLINE SMOKE, and `tests` runs a subset of the suites. Counts in an offline receipt describe the fixtures, not the live sources.

## Reading a receipt

`receipts/<date>/RECEIPT.md` is for people, `RECEIPT.json` (schema `circulate/receipt@1`, validated by `circulate.validate_receipt`) for machines, `stages/<name>.json` is each stage's StageResult as written when it finished, `logs/<name>.log` its log, `PROBES.json` the probes.

| Status | Meaning |
|---|---|
| OK | the stage ran and produced or verified its outputs |
| HOLD | the stage ran and correctly refused to produce a number: gated source, rate limit, source not reachable (the HTTP code is in the note), or a comparison that cannot be made. Never a failure. |
| FAIL | the stage broke (exception, schema problem, test failure, a committed row that no longer matches its source). Overall becomes FAIL. |
| SKIP | nothing new, or disabled by flag |

`overall` is OK only if no stage is FAIL, no frozen file moved, and no probe FAILed (a probe HOLD or SKIP does not fail it). Every StageResult has `counts`, `sources` (url, sha256, retrieved_utc), `outputs` (path, sha256, whether committed) and `notes`. The sponsor disclosure (from `hot-aisle/campaign/DISCLOSURES.md`) is in every receipt.

Frozen files (`retrospective/plan-R2.json`, `PLAN-R2.md`, `plan.json`, `results/R2-result.*`, `results/R1-*`) are hashed before and after each run and against `circulate/frozen-hashes.json` (created on the first run; update it only when a frozen file is deliberately superseded, which by definition it should not be).

## What each stage writes

Committed: `hot-aisle/campaign/backfill/imported/daily/<date>.jsonl.gz`, `imported/history-index.json`, `IMPORT-SUMMARY.md` (a marked block), `DELTA-standing.md`; `hot-aisle/data/price-history/INDEX.json`; `clustermax-challenge/retrospective/incidents/<slug>-standing.json` and `COLLECTION-LOG-standing.md`; `retrospective/results/R2-standing-<date>.{json,md}`; `hot-aisle/campaign/market/RUN3-ECONOMICS-BY-DATE.jsonl` and a marked block in `MARKET.md`; `research-desk/packets/newsletter-standing.jsonl`, `PUBLIC-TAIL-standing.research-packet.json` (+ `.sha256`); the front door and kit when they were stale. Not committed (`retained/`, uploaded as the `circulate-retained-<date>` workflow artifact): raw InferenceX artifacts, raw status pages, raw newsletter HTML, per-day price files, the full delta.

The commit step in CI should `git add` the paths listed in `RECEIPT.json` `committed_paths` plus `circulate/receipts`, `circulate/LATEST.md` and `circulate/frozen-hashes.json` (see `.github/workflows/pta-fetch.yml` for the nightly-commit pattern: configure the bot identity, `git diff --cached --quiet ||` commit, push).

## Things a stage will not do

It will not invent a value. A source that is gated, unreachable or unparseable is HOLD with the HTTP code (or UNSUPPORTED for a platform mismatch in `status`); an artifact the importer refuses is kept in the index with the importer's message. It will not overwrite a recorded price day, a frozen file, or a file R1/R2 read. It does not retry a refused request with other credentials. GitHub calls check `X-RateLimit-Remaining` and sleep to the reset (or HOLD if that is farther than the cap); `inferencex` imports at most 500 new artifacts per run and `newsletter` at most 50 new posts.

Known limits: the `prices` stage can detect that the OpenComputePrices release changed but cannot turn the release CSVs into normalized rows; a changed digest online is a HOLD naming the changed assets. `status` collects only providers whose platform has a collector. `economics` recomputes only where the price day files are available (retained/, the committed tree, or the local research lane); elsewhere it verifies the committed rows against `INDEX.json` and the Run 3 sources. `delta` uses the full 2026-09-29 import only where its retained copy is present and matches its pointer; otherwise it says so and uses the 100-artifact sample.

## Add a stage

1. `stages/<name>.py` with `run(ctx) -> StageResult` (a dict with `name, status, started_utc, finished_utc, seconds, counts, sources, outputs, notes, error`). `stages/_common.py` has `Stage` (builds the dict), `Ctx` (paths, `ctx.out()` for committed outputs, `ctx.gh()` / `ctx.http()` for the network, `ctx.run()` for subprocesses) and `Hold` (raise it to end as HOLD).
2. Write committed outputs through `ctx.out(rel)` so `--offline` sandboxes them; record them with `s.output(path)`.
3. Add the name to `STAGES` in `circulate.py`, add fixtures under `fixtures/<name>/`, and make the offline path exercise the same code.
4. Extend `tests/test_offline.py` if the stage adds an assertion worth making.

## Add a probe

`probes/p??_<name>.py` exposing `run(ctx) -> ProbeResult`; see `probes/_common.py`. Each probe restores what it touched and asserts the frozen-file hashes before and after.
