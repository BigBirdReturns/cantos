# Astra review — Lane B

Reviewed against lane-B.brief, COMMON-BUILD and SYNTHESIS, including Correction/North star. Paths below are relative to `hot-aisle/campaign/`; findings concern Lane B, with Lane A inspected only at the interface.

1. **Blocking defects**

   - **Availability becomes unsupported success probability.** `ledger/waterline.py:73–85` counts creates as listing probes and substitutes delivery probability 1 when there are no attempts. Reproduction: ten positive API listings, zero creates → probability 1.0, `thin=False`. One failed create also changes the listing fraction to 10/11. Keep denominators separate; delivery probability must remain unknown without attempts, with independent thinness and time-window checks.
   - **Estate schedule does not bound its watchdog.** `ledger/ESTATE-ARM-PREREG.md:25,35–40,61` allows 1,024 output tokens but calls a 300-token estimate “worst case.” At the cited 12.44 tok/s, depth 1 alone needs approximately 225 minutes for capped outputs, before prompt processing. Depths 4/16 have no measured upper bound; “stop after the current cell” cannot enforce 4.5 hours. Specify bounded cell/request deadlines and interruption retention before freezing.
   - **Reassignment prevents release accounting.** `ledger/knot_lifecycle.py:54,60` makes REASSIGNED terminal. After interrupting a paid seat and moving unfinished IDs, recording its confirmed RELEASED event is rejected. Permit resource release independently of work reassignment; retain the original seat’s final billing clock.
   - **Validation admits unqualified correctness.** `ledger/ledger_validate.py:171–178` checks evaluator presence, not frozen identity, and does not recompute traversal ratios. In-memory mutations of `valid-estate-full.json` setting evaluator `frozen=False` or closures/traversal to 999 both validate. Reject these before using records as qualification evidence.

2. **Honesty defects**

   `ledger/ledger_validate.py:196–201` and `ledger/ledger_build_run1.py:276–281` define wall-clock/accepted using only work time. This omits acquisition/setup/release despite the buyer-clock contract. Preserve work throughput separately; total wall-clock must use request→release or remain unknown.

   `ledger/ESTATE-ARM-PREREG.md:48` puts allocated MoE model-buffer bytes into bytes/traversal. Its caveat is good, but footprint is not traversed bytes; retain a separate footprint field and leave active bytes unknown. The planner likewise uses footprint and assumes one prefill traversal (`waterline.py:218–223`), while the ledger correctly leaves unmeasured MoE traversal bytes null.

   Recomputed Run 1: H100 $2.2222/2,267 × 1,000 = **$0.98024**; MI300X $2.2195/2,400 × 1,000 = **$0.92479**, approximately **5.7% lower**. Arithmetic is correct under declared request→work-end modeling. Present beside 53% as a different aggregation: all cells plus setup versus selected qualifying cells. Neither is an invoice or correctness result; release time is missing and acceptance is latency-only.

3. **Fit**

   Cloud Run 3’s declared 6,300-second work schedule plus 300-second cleanup fits 6,600 seconds arithmetically; Lane B’s estate schedule does not. `run3/arm.py:192` emits a flat `second-run/run-ledger@1`; Lane B requires nested groups. Its builder accepts only Run 1 cell files. Add a tested adapter joining clocks, acquisition, grades and receipts. Detailed results have a separate page-engine path; the ledger itself is not directly importable. Planner and ledger also use different wall-clock boundaries and traversal estimates.

4. **Non-blocking improvements**

   Rank unmeasured plans separately; validate malformed inputs without tracebacks; verify existing event chains before append; make `test_all.py` rebuild exclusively in temporary storage; add source-hash verification.

5. **Verdict: NOT READY.** Resolve the blockers and schema/units mismatches. Validator (17 checks), planner self-tests and seat checks passed; both real Run 1 records rebuilt in memory and validated. Lifecycle/builder self-tests were blocked by sandbox temporary-directory permissions. The aggregate runner was not run because it overwrites examples. No reviewed code changed.
