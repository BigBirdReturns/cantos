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

`app/verification/` contains historical receipts and captures. New checks must
name the actual build they exercised; a previous green receipt is not acceptance
of later bytes. A successful local suite does not claim a hosted deployment.
