# Cantos 0.5.0 decision workspace: build notes

Rebuild (from the repo root): `python -B app/source/build.py`  (writes app/Cantos.html and app/Cantos.manifest.json)
Install at site root: `cp app/Cantos.html index.html`

Source preview sha256 (unmodified 0.5.0): b7dda1c8fb088c43e8a1a0ee8674070f03d5e23be06a1c61c7a4da2ee8c26cb6 (rebuild in app/ was byte-identical)
Built page sha256 (with palette and nav additions): 56a4c84045c2c76cecb4adbf7655445cc0056178c0a1604baea992495a20ce18 (5,152,301 bytes); index.html is identical.

Change from 0.5.0 (presentation only; foundation.js and research-core.js untouched):
- app/source/app.js: two palette commands, "Distance to the floor" -> floor/index.html, "Circulation receipts" -> circulate/index.html
- app/source/index.template.html: an "ALSO ON THIS SITE" rail group with the same two links (hidden under 1000px like the other rail sections, because a bottom-row placement overflowed at 390 and 320; the palette still reaches both)

Gates on the built page (run from repo root):
- node --test app/source/foundation.test.cjs app/tests/regression.test.cjs: 34 tests, 33 pass, 0 fail, 1 skipped (needs hands/run3data, not in the preview)
- python app/tests/floor_regressions.py: 32/32, all_pass true
- python app/tests/real_regressions.py --packets app/packets: 32/32, all_pass true
- python app/tests/run_floor_gates.py app: native 34/33/0 PASS; browser 30 checks PASS; mobile 22 PASS; workspace 8 PASS; overflow 9 cases 0 failures PASS; STATUS PASS

Notes: run_floor_gates.py and floor_regressions.py read packets and controller scripts from the original build directory (council-review/astra, preview-v0.2.0/verification); these are not copied here. The first attempt, with the links in the bottom rail row, failed overflow at 390/320 and was fixed before the results above.

## Cold-visitor entry change (29 Sep 2026)

Built page sha256: d1f6bcdcd2535d2b49645cc2191603a38b523cec374539473786365f074c510a (5,155,501 bytes); index.html is identical. Supersedes the 56a4c840... page above.

Change (presentation and routing only; foundation.js and research-core.js untouched):
- app/source/app.js: with no saved state the page opens the verified Run 3 packet (Edition 01) from the embedded #run3-packet node, falling back to the invoice example only if that fails; saved state still restores whatever the person had. openEmbeddedRun3 became openWorkspace('run3'|'example'); palette keeps "Open the Run 3 decision (real, MI300X vs H100)" and gains "Open the worked example" (both go through the existing replace-workspace confirmation). composeRail() rewrites the rail after every prepareView: GPU inference first ("Real decision · Run 3, 24 Sep 2026"), Invoice extraction second ("Worked example · synthetic"); the non-current one is a switch button (data-open-workspace). The one-sentence orientation line is added under the Run 3 heading. The Evidence view link moved to the bottom rail row as "Evidence".
- app/source/index.template.html: rail markup for the example state, "Evidence" bottom-row link, example header now "Synthetic worked example" (with "Invoice extraction · 24 invoices. Two implementations. The same required fields.").
- app/source/style.css: .ws-eyebrow and .orientation rules only.

Test setup changes (intent unchanged; the checks now start by selecting the example through the rail and confirming replace): browser_regressions.py (boot and the reload check; all 30 checks), real_regressions.py (boot; the 32 checks start from the example, as before), floor_regressions.py (boot() selects the example unless select_example_first=False; a short settle in palette() for the dialog toggle event), run_floor_gates.py (the staged copies of the external mobile_check.py and visual_check_v2.py select the example after load; originals untouched). Six new checks in floor_regressions.py cover the cold entry (Run 3 opens with $0.74/$1.20, orientation line text, rail order and eyebrows, example header, palette pair, saved-state restore).

Gates on the built page (run from repo root):
- node --test app/source/foundation.test.cjs app/tests/regression.test.cjs: 34 tests, 33 pass, 0 fail, 1 skipped
- python app/tests/floor_regressions.py --page app/Cantos.html --out NEW_DIR: 38/38 (32 original + 6 cold-entry), all_pass true
- python app/tests/real_regressions.py --page app/Cantos.html --packets app/packets --out NEW_DIR: 32/32, all_pass true
- python app/tests/run_floor_gates.py app: native 34/33/0 PASS; browser 30 checks PASS; mobile 22 PASS; workspace 8 PASS; overflow 9 cases 0 failures PASS; STATUS PASS
Screenshots of the new cold load: app/verification/root-cold-1440.png, root-cold-390.png.


## 2026-09-30, orientation line places the decision in the record

ORIENTATION now reads: "One retained decision from the Second Run compute campaign: the same coding workload on two rented seats, cost per 1,000 accepted requests at list price, every figure stamped with its source. Cantos is the record it lives in." Rebuilt page sha256 57ee74039d9afb7f… (5,155,572 bytes); index.html at the root is identical. Gates: native 33/34, browser 30, mobile 22, workspace 8, overflow 0/9, floor regressions 38/38.
