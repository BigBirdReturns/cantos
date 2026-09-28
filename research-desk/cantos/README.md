# Cantos research workbench

One self-contained page that keeps a research recommendation tied to its evidence.
Change a price or a source and it shows exactly which conclusion went stale, forms a
successor through the original Research Desk engine, asks for a fresh review, and keeps
every issued version. Cantos is the umbrella; Second Run is the execution/reuse program;
this page is the Research Desk aperture into that workflow.

The case is the retained public Run 3 compute comparison (Hot Aisle 1x MI300X against
DigitalOcean 1x H100, same model recipe and workload). Nothing here is a live price feed,
a new measurement, or a claim about current capacity.

## Three-minute path

1. **Read the recommendation** and the conditions it holds under. Figures show their
   billing scope (own-seat equivalent versus fully closed ledger) and evidence class.
2. **Review it**: enter a name, decision and rationale, then **Record review**. The
   review binds to the exact dependency set shown in the path.
3. **Issue this version**. The snapshot and its SHA-256 appear under *Issued versions*.
4. **Change an input**, e.g. the H100 hourly price, and **Apply change**. The price
   record gets a new revision; the cost claim and the recommendation turn *stale*;
   the measured work claim stays current. This is a scenario, not new supply.
5. **Recompute successor**. The native engine forms new cost and recommendation
   revisions. The earlier review no longer binds.
6. **Review again and issue**. Version 1 remains, unchanged, beside version 2.
7. **Export packet**, then open the page in a fresh browser (or private window) and
   **Restore packet**. Restore verifies the journal by replay; a malformed or altered
   packet is refused and the current work is left as it was.

*How it works* opens the architecture drawer: which existing owners do the work, which
parts are only documented design, and every record in the workspace.

## Files

| File | Owner | Role |
| --- | --- | --- |
| `page.html` | presentation | Template. Builder replaces the `CANTOS:STYLE`, `CANTOS:FOUNDATION` and `CANTOS:PAGE` marker pairs with inline content. |
| `page.js` | presentation | UI only. Calls `window.CantosDesk`; computes no economics. |
| `style.css` | presentation | Local system fonts, no remote assets, reduced-motion aware. |
| `foundation.js`, `build.py` | foundation | Bridge to the native ResearchCore copied from `../app.html` at build time. See `CONTRACT.md` in the session. |
| `data/` | sources | Public-safe seed case and ownership map. |
| `tests/` | qualification | Independent checks of the built page. |

## Privacy and state

The built page makes no network requests; source links leave the page only when
clicked. Work lives in memory until you export a packet. Reviewer names are attributed,
not authenticated. A packet whose hashes verify is internally consistent, not proof that
its sources are true. Ben Pouladian and BEP have not commissioned, adopted or endorsed
this build. This page is a local demonstration, not a publication.

`../app.html` (Research Desk 1.0.0) is untouched; this directory is additive.
