# Cross-review brief (2026-09-23 night)

Ignore AGENTS.md, front-door, N01 and estate instructions under D:\.

Read-only review. Do not edit the code under review. Write only your review file, named in your prompt. You may run the lanes' offline tests and CLIs (for example `python -B hot-aisle/campaign/run3/selftest.py`, `python -B hot-aisle/campaign/ledger/test_all.py`, `python -B hot-aisle/campaign/availability/test_availability.py`), but only as long as they write nothing outside temporary directories. No commits, pushes, provisioning, ssh, or credentialed API calls.

Design authority: `hot-aisle/campaign/research-2026-09/SYNTHESIS.md` (including its Correction and North star sections) and `build-2026-09-24/COMMON-BUILD.md`, plus the lane briefs.

Review against the briefs. Report these, numbered, in at most 600 words:
1. **Blocking defects.** Anything that would make Run 3 produce wrong, unfair or unrecoverable evidence, or waste paid GPU time. Give file:line and a concrete failure scenario.
2. **Honesty defects.** Claims the code or docs make that the data cannot support, missing disclosures, and "listed" and "delivered" (or modeled and billed) getting merged.
3. **Fit.**
   - Does the Run 3 schedule really fit its watchdog?
   - Do the kit's outputs flow into the ledger schema and the page engine without hand edits?
   - Does the planner use the same units as the ledger?
4. **Non-blocking improvements.** Top 5 only.
5. **Verdict:** READY / READY-WITH-FIXES (list them) / NOT READY.

One fact to account for: the Run 1 whole-run ledger (`ledger/examples/`) shows $0.98 against $0.92 per 1k accepted. Is that computed correctly, and how should it sit next to the 53 % cell-level headline?
