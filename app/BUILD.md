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
