# What the next operator inherits: the Chapek seat record

`index.html` is a working page prepared for Chapek.io by Jonathan Sandhu. It runs entirely in the reader's browser. It makes no requests, needs no account, and keeps what the reader enters in that browser unless they save or send a copy.

The page continues one record across editions. Edition 3 put one idea to a GPU-capacity seller: customers buy a seat, the place where their AI work runs and stays their own, more than they buy a node, and let the reader test it on one prospect. Edition 5 opens on what the next operator inherits from that record:

- **What you inherit.** The recommendation in use and its state (flagged by the record's own dependency check when an input it was built on has a later version), what changed since it was written, the native work already performed, what is still open, and what to do next.
- **Prospect.** The questions that decide fit, plus the recommendation and the reader's own conclusion.
- **Server.** The full dedicated-capacity economics, with the quick test (a prospect's monthly volume priced on the server in use).
- **Work performed.** Four native runs of the Cantos operation runner, their receipts, and eight retained procedures, each with its exact native task and computation key. The page shows these; it never executes them.
- **Evidence.** Dated sources, each kept within its own scope.

The changed server numbers in the record are the monthly equivalent under Chapek's annual term, not a reduced price for a monthly commitment; the record says so wherever they appear.

## Owners and checks

The page embeds, unchanged:

- `app/source/research-core.js`, for decisions, revisions, sign-offs and portable records;
- `compute/capacity/index.html`, for server economics, with only its saved-input slot filled.

Every price it shows comes from `compute/capacity/capacity.cjs` and the Compute engine. The retained procedures were run by `integration/work.py` outside this page; their keys bind to results in the working record's store, which travels in the delivered package, not in this repository.

```sh
node compute/chapek/check.cjs                      # published bytes against the owners in this tree
python -B compute/chapek/tests/browser_check.py    # reader journey over HTTP and an offline saved copy
```

If either embedded owner changes, `check.cjs` fails until the page is rebuilt against it. The page is built outside this repository, from the Cantos working record that also holds its fuller qualification. Neither check establishes customer fit, measured H200 NVL or B300 throughput, a quote, legal jurisdiction or execution location.
