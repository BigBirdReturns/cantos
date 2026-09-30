# Observation corpus

These readers use a retained bundle in place. They do not mutate its payload and
do not create another index. The bundle's SQLite database remains the selection
index.

## The estate practices on itself

The estate's capture lanes already write observations in its own
`imported-observation@1` schema, each row carrying the producer's URL, revision,
retrieval time and hash, plus the producer's configuration. `estate_bundle.py`
turns those lanes into a Cantos collection without re-fetching anything:

```powershell
python -B -m corpus.estate_bundle --lane <session>\lanes\inferencex-history --lane <session>\lanes\mlperf --lane <session>\lanes\github-issues --out <new-collection>
```

The lane rows files are copied and hash-bound as the pinned raw inputs. The
importer projects them with the `imported-observation-jsonl` and
`github-issues-jsonl` adapters, `batch_owner.cjs` retains the rows as native
Research Desk packets through the same pinned ResearchCore owner used for
attempts, and `verification/VERIFY.json` records the checks: every lane line
retained, no duplicate identities, packets covering every row with ordered
identity ranges, an exact re-import of one row per origin, its history opening
through its packet with producer links exposed, and a full deterministic
re-import. `ESTATE.json` names the lanes, their manifests and reports by hash.
An existing output folder is never overwritten.

Estate JSONL ingestion streams the lane instead of loading its entire file.
A selected-row rebuild hashes all retained bytes while parsing and projecting
only that row. The history owner independently repeats that check before append.
Native packet production pulls the next input chunk only when the current batch
is ready, so packet verification cannot accumulate an unread queue of the lane.
These changes preserve the observations and native packet identities; they do
not require rebuilding an existing collection to use the faster replay path.

An opened observation from such a collection links to the producer record, the
producing commit and workflow run (InferenceX), the system and measurement
descriptions (MLPerf), or the issue or pull request itself. Producer issues and
pull requests are a separate kind, `producer_issue`, searchable by hardware
mention and engine. Packets written by `batch_owner.cjs` carry `first_row_id`
and `last_row_id`, so opening one observation verifies one packet rather than
loading an origin's every packet.

Open the collection interface from the repository root (Python 3.11+ and Node):

```powershell
python -B -m corpus.server --bundle <retained-bundle> --state <separate-attempt-directory>
```

Visit `http://127.0.0.1:8768/`. Search and page through observations, compare
their recorded conditions, open producing-source and implementation links,
inspect the initial and corrected projections, and rebuild an observation.
The default search shows benchmarks; traces, model metadata and prices remain
separate kinds. No performance/price join or automatic ranking is inferred.
The exact engine filter also applies to captured producer issues and PRs.

The September 29 delivery includes 70,725 observations in 74 native Research
Desk packets. Its retained correction gives latency its own field for 571
rows. The interface reads both versions by stable observation identity and
checks each opened row against its indexed native packet. It exposes the
correction procedure alongside the actual differences; producer rationale
is not supplied by this delivery.

Rebuild invokes the delivered importer against retained raw bytes. A second
verification of the receipt precedes appending source and claim records through
the existing ResearchCore owner embedded in `research-desk/app.html`. No reviews
or accepted-work measurements are invented. A subsequent attempt extends the
previous local packet; the original packet and source bundle stay unchanged.
Every completed attempt has an export link to a native Research Desk packet.
The state directory and source collection can be carried to another installation.
No account, central approval service, or online request is needed.

Incomplete attempt folders remain visible as unconfirmed. Completed summaries
are written atomically after their receipt and packet. A lost response triggers
a history refresh; it is not evidence that the operation failed. One server
process should own writes to a state directory at a time.

This is an executable normalization history. It does not yet connect full
producer decision histories or launch benchmark procedures. Recorded external
implementation links can be mutable; absent producing commits remain absent.
The existing calibration shapes have no bound hardware/model/acceptance contract
and are not calibration runs. The full Cantos product extends beyond this
collection interface.

The September 30 estate collection contains 293,172 benchmark observations and
25,300 producer issues/PRs in 718 packets. Issue records are captured metadata;
their state and links do not establish decision rationale or a verified fix.
The existing price lane needs an offer-specific projection preserving GPU-hour
versus instance-hour accounting, terms, location, availability and snapshot time.
The workload lane's small rows file contains summaries, while request events
live in the retained trace files. Neither lane is admitted by renaming its rows
as benchmarks. Their larger ingestion remains separate work.

Search with the existing filters and pagination:

```powershell
python corpus/query.py --db <bundle>\corpus\corpus.sqlite --kind benchmark --hardware H100 --model llama2-70b-99 --engine vLLM --scenario Offline --unit Tokens/s --limit 25 --offset 0
```

The same query is callable as `select_rows(db_path, *, kind, hardware, model, engine,
scenario, unit, limit, offset)`. Use `row_by_id(db_path, row_id)` to retrieve
the complete stored observation.

Replay one observation's existing source adapter against the pinned local bytes:

```powershell
python corpus/projection.py --bundle <bundle> --row-id <row-id> --actor "Local operator" --out <new-receipt.json>
```

The reimport receipt includes the stored and current normalized rows, source
identity, manifest/raw/native hash checks, procedure hash, and observation time.
Changed projection bytes are returned as a correction candidate. A missing or
altered source, changed source pins, or identity mismatch fails closed. Reimport
does not execute a benchmark, perform calibration, or assert accepted work.
Output must be a fresh path outside the read-only bundle.

Verification from the repository root:

```powershell
python -B -m unittest discover -s corpus/tests -p "test_*.py" -v
node --test corpus/tests/batch_stream.test.cjs
python -B corpus/tests/browser_collection.py --bundle <retained-bundle> --out <fresh-verification-directory>
```

The browser check uses the installed Playwright/Chromium dependency and actual
bundle rows. It checks search, pagination, a retained latency correction,
successive native journal extensions, Unicode preservation, export/reopen,
bookmarking, a lost response after commit, narrow layout and cross-origin write
rejection. These are software checks, not new measurements of the source work.
