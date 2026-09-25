# The shelf

Claims about compute, filed side by side so that someone who was not there can see what
each one supports and what it does not. This directory is the format, the checker, and
the rule for pulling other people's shelves into yours. It is not a ranking, a rating, a
registry of trust, or a service. Nothing here bills, expires, or phones home.

Live page: https://bigbirdreturns.github.io/axm-tools/shelf/

## What is here

```
shelf/
├── README.md              this file
├── SPEC.md                the card format, filing version 2 (normative)
├── index.html             the whole interface; embeds the browser engine in <script id="shelf-engine">
├── card.skeleton.json     a passing empty card to start from
├── scripts/
│   ├── shelf.py           validate · compose · which · pull · sync  (stdlib only)
│   └── check_staging.py   staged imports carry provenance; promotions are complete, cite a real capture, and match bytes
├── data/
│   ├── cards.jsonl        this hub's shelf: five cards filed 2026-09-24 (byte-checked copy, see below)
│   ├── hubs.json          hubs the page reads (human-owned)
│   ├── promotions.jsonl   recorded decisions to move a staged card onto the shelf (human-owned; absent until the first one)
│   └── staging/           what `pull` wrote: exact bytes, hash, time, filing errors, standing imported/candidate
└── tests/
    ├── cases.json         one fixture both engines must satisfy
    ├── test_shelf.py      CLI regressions (python -m unittest)
    ├── test_engine.cjs    browser-engine regressions and byte-for-byte parity with the CLI (node --test)
    └── fixtures/          the two model-stranger filings, unedited
```

## Run it

```
cd shelf/scripts
python shelf.py validate ../data/cards.jsonl
python shelf.py which --unit "USD / 1000 accepted requests" --period 2026-09 --measured
python shelf.py compose a.json b.json --for same_period
python shelf.py pull https://example.org/their/cards.jsonl --hub their-name
python shelf.py sync --check
python -m unittest discover -s ../tests -p 'test_shelf.py' -v
node --test ../tests/test_engine.cjs
```

Python 3.8 or later, standard library only. Exit codes: `validate` returns the number of
failing filings; `compose` returns 2 on a refusal; `sync --check` returns 1 on drift.

## What each command establishes, and what it does not

- **validate** checks that a card carries the five answers, the four flags, the three
  checks, a publication-date basis, an observer-benefit record and explicit hourly units.
  It cannot establish that a cited source warrants a value, that a populated disclosure
  is complete, or that a claim is true.
- **compose** refuses five compositions the format does not license and names the rule
  for each. Finding no refusal is not admission.
- **which** says which cards have a result in the asked unit, are measurements when one
  is required, and have a known observation date inside the asked period; for each it
  reports the results, the card's own limits, and who inspected, recomputed or repeated
  it. This is the check a stranger performed by hand on 2026-09-24, made mechanical.
  Nothing ranks.
- **pull** copies another hub's cards into `data/staging/` with their exact bytes, hash,
  retrieval time and filing errors. Standing is `imported/candidate` and stays so until a
  local admission decision names the exact captured input. An authorized person or
  procedure may make that decision. Pulling never writes to `data/cards.jsonl`.
- **sync --check** confirms `data/cards.jsonl` is byte-identical to the retained campaign
  record in `hot-aisle/campaign/shelf/cards.jsonl`, where the first five cards were filed
  and where the Run 3 recomputation, propagation and narrowing checks still run against
  the campaign bytes they need.

## The first hub

The five cards are one measured run of ours, narrowed to what it supports; one good
outside benchmark artifact; one provider rating with a partly withheld derivation; one
price index with a published method and withheld weights; and one provider's statement
about itself. Two model strangers filed a sixth and a seventh card from public pricing
pages with none of our context; their filings are retained unedited in `tests/fixtures/`
and, for the second, pulled into `data/staging/second-stranger/` through the tool itself.
The first stranger's unchanged card originally exposed three filing errors. Enforcing
the already-documented version field now also identifies its missing `filing_version`:
four current errors, with the original three retained. Human filing and usability remain
separate, untested properties; they do not block mechanical qualification.

## Generated engine and custody regressions

The independent streaming corpus in `tests/generated.py` starts from the five retained
archetypes. Its full profile drives 10,000 valid variations, 100,000 faults in 32
families, 10,000 controlled changes and 1,000,000 distinct ordered pairs through the
native Python and embedded browser engines. Each pair exercises one of the five
declared purposes; it does not claim every purpose on every pair. Seeded rule cases
check the expected result as well as parity, including the named refusal rule.

From the repository root:

```powershell
python -B shelf/tests/generated.py --profile full --seed 20260924 --out S:/Scratch/Runs/shelf-generated-full
python -B -m unittest discover -s shelf/tests -p "test_generated_*.py" -v
python -B -m unittest discover -s shelf/tests -p test_federation_properties.py -v
```

Use a new output directory for each run. Only the report and up to twenty failure
witnesses are retained. Reports bind generator, engines, source cards and catalog
hashes; a source change during the run fails qualification. A differential failure
receives bounded structural reduction and can be replayed with
`python -B shelf/tests/generated.py --replay <failure.json>`. Single-fault and
transition witnesses retain their hypotheses; removing a required field must not
manufacture a different failure. `GENERATED-VERIFICATION.json` records the full local
run. CI runs a smaller population and uploads its report and any counterexamples.

The federation suite additionally performs 425 local captures across 376 generated
scenarios: repeated bytes across hubs, changed metadata, tampering, admission records,
duplicate IDs and successor captures. Historical bytes survive; imports retain
candidate status; admission records name an exact capture, hash and filing. Those
records do not authenticate an actor or prove source truth.

Diagnostic consistency currently uses the installed validator. A capture made under
older validation behavior can therefore be held for review even when its bytes are
unchanged; the checker cannot yet distinguish rule drift from edited diagnostics.
It preserves the capture instead of rewriting its history.

This is a stratified test population, not an observed usage distribution or a claim
of three-sigma coverage. The query API checks unit, observation period, measured
status and valid filing. Configuration compatibility, general claim entailment and
institutional standing require their own contracts; a million scoped checks do not
silently add them. Evidence flags remain separate dimensions, not a trust ladder.

## Adding your hub, or a card

- A hub is any URL that serves a `cards.jsonl` or a single card. Open a pull request
  adding it to `data/hubs.json`. Listing grants nothing: the page renders your cards with
  your hub's name on the row, and `pull` imports them as candidates.
- A card on this shelf is one line in `data/cards.jsonl` that passes `validate`. Review
  checks the cited sources. Filing and machine validation do not grant standing.

## Ownership (CONTINUITY §4)

Human-owned: `data/hubs.json`, `data/promotions.jsonl`, `data/staging/**`, `data/cards.jsonl`
(which must also match the retained campaign record). Nothing here is machine-owned; there
is no scheduled workflow. `.github/workflows/shelf-ci.yml` only verifies.

## Disclosure

On the run card, Hot Aisle's credit paid for the AMD arm and Hot Aisle is a sales prospect
of the shelf's author. The H100 arm was paid in cash. One run per arm, no repeats. The card
says so on its spine.
