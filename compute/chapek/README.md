# A seat for every Chapek customer

`index.html` is a working page prepared for Chapek.io by Jonathan Sandhu. It runs entirely in the reader's browser. It makes no requests, needs no account, and keeps what the reader enters in that browser unless they save or send a copy.

The page puts one idea to a GPU-capacity seller: customers buy a seat, the place where their AI work runs and stays their own, more than they buy a node. The page lets the reader test that on one prospect:

- **Quick test.** On the first screen, a prospect and their monthly volume of checked results give a price per result on one H200 NVL server at Chapek's public monthly list price. The page also shows what happens to that price as more of the prospect's work runs on the same server.
- **Prospect.** The questions that decide fit, plus a draft recommendation that is flagged whenever an answer it depended on changes.
- **Server.** The full dedicated-capacity economics.
- **Evidence.** Dated sources, each kept within its own scope.

## Owners and checks

The page embeds, unchanged:

- `app/source/research-core.js`, for decisions, revisions, sign-offs and portable records;
- `compute/capacity/index.html`, for server economics, with only its saved-input slot filled.

Every price it shows comes from `compute/capacity/capacity.cjs` and the Compute engine.

```sh
node compute/chapek/check.cjs                      # published bytes against the owners in this tree
python -B compute/chapek/tests/browser_check.py    # reader journey over HTTP and an offline saved copy
```

If either embedded owner changes, `check.cjs` fails until the page is rebuilt against it. The page is built outside this repository, from the Cantos working record that also holds its fuller qualification. Neither check establishes customer fit, measured H200 NVL or B300 throughput, a quote, legal jurisdiction or execution location.
