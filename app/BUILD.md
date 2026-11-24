# Building and checking Cantos

From the repository root:

```sh
python -B app/source/build.py
```

This rebuilds `app/Cantos.html` and its manifest from the source template,
styles and scripts, checking the versioned ResearchCore owner first. Copy
`app/Cantos.html` to `index.html` to update the published root entry. Both pages
must contain identical bytes; do not edit either generated HTML file directly.

```sh
python -B app/tests/check_build.py
node --test app/source/foundation.test.cjs app/tests/regression.test.cjs
python -B -m unittest discover -s integration/tests -p test_task_research_handoff.py -v
python -B -m unittest discover -s integration/tests -p test_release_gate.py -v
```

The build check generates a temporary candidate and compares it with both
shipped pages and the build manifest. The native decision suites preserve original packets, dependency
checks and analytical behavior. The handoff suite checks the separate existing
procedure owner, not a newly added browser executor.

## Native browser checks

Use the installed Playwright test dependency and Chromium. Each output directory
must be new and outside the source checkout; CI uses temporary directories.

```sh
python -B app/tests/overview_regressions.py --page index.html --out <new-overview-output>
python -B app/tests/browser_regressions.py --page index.html --out <new-workspace-output>
python -B app/tests/floor_regressions.py --page index.html --out <new-interaction-output>
python -B app/tests/real_regressions.py --page index.html --packets app/packets --out <new-run3-output>
```

These exercise local pages: the overview and its real entry paths, current work
preservation, malformed imports, corrections, reviews, retained successors,
Run 3 scenarios, keyboard interaction and narrow layouts. No live provider or
hosted site is required. The older `run_floor_gates.py` also depends on historical
controller scripts outside this extracted repository; the self-contained suites
above are the current CI entry points.

## Publication

The existing `.github/workflows/hot-aisle-ci.yml` now qualifies the Cantos app
alongside the execution instruments. The filename is retained for release-gate
continuity. Changes to `README.md`, `app/`, `index.html`, `assets/`, either relevant workflow,
or the existing compute/integration source require matching qualification.
`pages.yml` stages and deploys only after the release gate passes.
The staging size filter retains `compute/community-kit.zip` as an intentional
public download and compares its staged bytes with the qualified source kit.
The community results page links to that independently runnable collection.

`app/verification/` contains historical receipts and captures. New checks must
name the actual build they exercised; a previous green receipt is not acceptance
of later bytes. A successful local suite does not claim a hosted deployment.

## Guided Open Compute entry

`public/open-compute/` embeds the same built app at `app/Cantos.html?workspace=run3&presentation=1`. The direct `workspace=run3` route verifies the embedded packet before presenting a decision. Presentation mode changes navigation and layout; ResearchCore and the native change, recompute, review, retain, export and restore transactions remain the owners of the result.

The guided workspace uses a scoped IndexedDB database, `cantos.open-compute.presentation`, with record key `cantos.open-compute.presentation.v1` for explicit local saves. Its transaction completes before the UI acknowledges a save. Ordinary Cantos localStorage behavior remains unchanged. A verified legacy guided localStorage packet migrates into this database while the earlier copy remains untouched. Reload restores a verified guided save. `fresh=1` opens the original packet in memory without deleting either saved copy. Opening an exported packet follows the existing verification and replacement-confirmation path.

The guide accepts only same-origin messages from its own frame, and the app accepts navigation commands only from its same-origin parent. Those commands inspect or focus existing controls; they do not change assumptions, calculate outcomes or manufacture retained editions.

Run the focused public-flow gate in a fresh output directory:

```sh
python -B app/tests/public_flow_regressions.py --out <new-public-flow-output>
```

It checks the live page, acceptance and request inspection, price revision and stale gating, explicit recomputation, preserved predecessor, native export and offline replay, isolated local-save recovery, the fresh route, and the mobile scenario drawer. `--browser-executable` selects an installed Chromium-compatible browser; `--base-url` can target a served checkout during native estate QA. The receipt records the app bytes actually exercised.

Portable workspace exports use compact JSON with the same native packet identity. Export checks the existing 12 MB import boundary before offering a file; oversized packets preserve current work and report the limit explicitly. The two-edition Run 3 packet remains below that boundary.

If browser storage is unavailable, the guided entry opens the verified starting packet in memory and reports that saved work could not be read. Corrupt saved packets still fail native verification and remain untouched. Startup failures reach the outer guide instead of leaving an indefinite verification message.
