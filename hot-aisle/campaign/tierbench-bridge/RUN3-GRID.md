# RUN3-GRID · Run 3's EvalPlus workload as a Tier-Bench task class, across model tiers and seats

Status: **a plan and a budget, not a result.** Run 3 (`../run3/PREREG.md`) has not run; no open-weight tier has a Tier-Bench Call row.
Prices are dated list prices from `models.json` (reviewed 2026-07-26), the Race 6 operator diagnostic (Codex tiers, subscription-derived)
and `../ledger/seats.json` (cloud seats). Nothing here is a claim about which tier or seat wins.

## 1. The workload becomes a task class

Run 3 freezes 164 HumanEval+ and 378 MBPP+ prompts (542 tasks, cycled; seed 700000 + request index; temperature 0.2; raw completion,
no chat wrapper, no repair) and grades each raw completion with EvalPlus base **and** plus tests on a CPU seat. In Tier-Bench terms:

| Tier-Bench concept | Run 3 value |
|---|---|
| `task_id` | `evalplus:HumanEval/<n>`, `evalplus:Mbpp/<n>` |
| `task_class` | `evalplus-humaneval-plus`, `evalplus-mbpp-plus` (importer rule in place); the Knot pools them as `graded-coding` |
| grader | EvalPlus 0.3.1, frozen by dataset sha256 (`../run3/workload.py`). **Not hidden**: the plus tests are public, so Tier-Bench would mark this `public-graded`, not `hidden-graded`; contamination is a caveat on every tier, strongest for the open-weight models trained on the web |
| `outcome` | pass = base AND plus; fail = completed but a test failed; error = transport failure, sample timeout, or client-limit rejection (never a pass, PREREG); partial = grading hold |
| `trial` | cycle index (each pass over the 542 tasks is one trial; K = 3 cycles gives K decisive receipts per task) |
| `tokens` | exact, from the vLLM usage field / Ollama counts / provider usage |
| `cost_usd` | API tiers: the provider bill per call. Fabric seats: run cost allocated per request (`allocated-from-seat-lease`), with the run ledger holding the real number |
| `phase` | `run3-A/T0`, `run3-A/T1`, `run3-N/T0`, `estate-arm`, `api-<tier>` |
| `effort` | none for open weights (sampling frozen in the prereg); Codex/Claude effort as routed |

The Knot (`fixtures/knots/knot-run3-evalplus-tierbench.json`) declares `tierbench.task_classes = ["tierbench-T1"]` as the prior
analogy (implement-from-docstring). Once Run 3 rows exist the Knot should point at `evalplus-*` and the analogy retires.

## 2. The grid

Rows are model tiers on the Tier-Bench axis; columns are seats on the fabric axis. A cell is one run: (pass rate on base+plus, $/accepted
closure from request to release, wall per accepted closure, and the **residue**: the task ids this tier fails that a dearer tier passes).

| Model tier | Seat(s) | Provider price | Seat price | Evidence today |
|---|---|---|---|---|
| `qwen3.5:9b-q4_K_M@none` (Ollama) | `estate-w01-3090`, `estate-w01-4060`, `estate-n01-3090-egpu` (after ~09-28) | $0 | energy: 3090 nameplate 350 W, tariff to be supplied (assumed $0.30/kWh) | routing-evidence.md: structured floor only, **excluded from the coding route** (SyntaxError on the coding canary). Expected residue: large. This row is the cheap floor the broker must try first |
| `claude-haiku-4-5@harness` (API) | none for inference; grader on `estate-w01-cpu` / `estate-n01-cpu` | $1 / $5 per 1M | $0 | Tier-Bench: sufficient (K/K) on T0..T4 and 5/5 breadth tasks; 3/5 unstable on the task02 residue; Race 6: 6/6 at $0.106. `tier_waterline` picks it for `graded-coding` on today's evidence |
| `gpt-5.6-luna@low` (Codex) | none; grader as above | $1 / $6 per 1M (race6, subscription-derived) | $0 | Race 6: 6/6 solves at $0.116, 2/2 authoring at $0.060; policy.json's normal cloud coding floor. No Claude-ledger rows |
| `qwen3-coder-30b-a3b-fp8@vllm` (Run 3's model) | `hotaisle-mi300x-1x-enc1` (A/T0, A/T1), `do-h100-nyc2` (N/T0) | $0 | $2.99 / $4.41 per GPU-hr, 2 h reserved per invocation (PREREG watchdog) | Run 1 priors on a random workload only (accept 1.0 / 0.945 at the TTFT gate); **no correctness evidence**. This is the row Run 3 creates |
| `qwen3-coder-30b-a3b-awq@vllm` or `gguf-q4@llama.cpp` (estate arm) | `estate-w01-3090` (after ~09-28) | $0 | energy, metered (plug meter required, `../ledger/ESTATE-ARM-PREREG.md`) | bytes UNVERIFIED (~16 / ~18.6 GB); different quantisation = separate identity, no equivalence claim (PREREG L) |
| `gpt-5.6-terra@medium`, `gpt-5.6-sol@high`, `claude-sonnet-5@low`, `claude-fable-5@*` | none | $2.5/$15, $5/$30, $3/$15, $10/$50 per 1M | $0 | residue tiers: run only on the task ids the floor fails (residue-broker: next rung after 0/K), never on the full 542 |

## 3. Budget

Per closure the Knot assumes 400 input + 300 output tokens (the cycled EvalPlus prompts are short; the actual Run 3 mean will replace
this). Per 1,000 closures at list:

| Tier | $/1k closures (list) | Basis |
|---|---:|---|
| haiku-4-5 | 1.90 | (400 x $1 + 300 x $5) / 1e6 x 1000 |
| luna@low | 2.20 | race6 pricing [1, 6] |
| spark@low | 4.90 | race6 [1.75, 14]; latency lane, weekly budget gate |
| terra@medium | 5.50 | race6 [2.5, 15] |
| sonnet-5@low | 5.70 | models.json |
| opus-5 | 9.50 | models.json |
| sol@high | 11.00 | race6 [5, 30] |
| fable-5 | 19.00 | models.json |
| qwen 9B / 30B on the estate | energy only | 350 W x hours x tariff = ~$0.10/h at $0.30/kWh; per closure depends on throughput, **unmeasured for this class** |
| 30B on Hot Aisle MI300X | 2 h lease $5.98 per arm invocation | per 1k accepted = $5.98 / (accepted / 1000); Run 1 measured $0.072/1k accepted on the random workload at saturation (SYNTHESIS), which Run 3's 0.10 rate factor will not reach ("price and correctness, not capacity") |
| 30B on DO H100 | 2 h lease $8.82 | Run 1: $0.153/1k accepted at saturation |

Grid cost for the first pass, one cycle (542 tasks) per tier, K = 3 cycles where the tier is a candidate floor:

| Cell | Cost | Note |
|---|---:|---|
| Cloud open-weight arms (as pre-registered): A/T0 + A/T1 + N/T0 | $20.78 + $4.22 reserve = **$25.00** | already approved scope; produces the 30B rows for three seats and the hour-long sustained window |
| haiku-4-5, 3 cycles x 542 | ~$3.09 at list; $61 if the Tier-Bench trial mean ($0.0378, subagent-estimated, long prompts) held | the Tier-Bench figure is for harness trials with 20k-token contexts, not raw completions; the list figure is the honest estimate for this workload |
| luna@low, 3 cycles x 542 | ~$3.58 list (subscription window, not cash) | Codex weekly limits gate it; `spark_budget_ok` logic in route.py shows the pattern |
| qwen3.5:9b, 3 cycles on the estate 3090 | ~$0.30 energy at nameplate; 0 cash | needs the 3090 free (~09-28) and a plug meter |
| residue tiers (terra, sol, sonnet, fable) on the failed task ids only | bounded by residue size x $/closure; at a 20 % residue (~108 tasks x 3) ~$1.8 (terra) to ~$6.2 (fable) | never run the full set at a dear tier; that maps a ceiling, not the frontier (burden-discipline) |
| **Total first grid** | **~$32-38 cash + ~$4 subscription-window** | within the $50 allowance; the $25 cloud part is the existing Run 3 approval |

Wall clock is the other budget. `tier_waterline` shows the serial API plan for 542 closures at the Tier-Bench trial median latency
exceeds the 90-minute Knot deadline at concurrency 1 (needs ~4 in flight); the cloud seats finish the same count in ~12-17 minutes of
work after a 11-16 minute setup, but bill a 2 h reserved lease under the Run 3 watchdog.

## 4. What the grid answers

**Frontier residue x hardware cost.** For one graded coding class:

1. **Residue size per tier.** Which EvalPlus task ids the $0-provider tiers (qwen 9B on the estate; the 30B on a rented seat) fail that
   haiku / luna pass, and which of those only a frontier tier passes. That is the "frontier residue" in Tier-Bench's sense, measured with
   K = 3 cycles per task rather than inferred from a benchmark score.
2. **Cost per accepted closure with the seat included.** The fabric ledger prices the open-weight rows honestly: lease from request to
   release (including the 2 h reservation and failed acquisitions), energy on the estate, and the accepted count after the latency gate.
   The API rows are priced per call. The comparison is then on one unit: $/accepted closure, and wall per accepted closure.
3. **The break-even.** At list, haiku costs ~$1.90 per 1k closures flat; a Hot Aisle lease costs $5.98 per invocation regardless of
   volume. The open-weight seat only wins per closure above roughly 3,100 accepted closures per 2 h lease (about 0.44 accepted/s), and
   only if its residue is small enough that the escalations it forces do not cost more than the API floor would have. Run 3's rate
   factor 0.10 is well below that, so the first grid measures **price and correctness**, and the break-even is computed, not claimed.
4. **Priors for WATERLINE.** `seats.json.priors["graded-coding"]` is null on every seat today ("no graded batch has run"). Each cell
   fills one prior: accept rate, n, receipt. `tier_waterline` then stops saying "assumed 1.0".
5. **Whether the estate row is real.** The Correction in SYNTHESIS asks for accepted closures per weight traversal on a streamed seat.
   The qwen 9B row is resident on a 3090 and does not test that; the 30B AWQ/GGUF estate arm does, and it needs the plug meter and the
   3090 after ~09-28.

## 5. What is not measured by the grid

Hidden-graded sufficiency (EvalPlus is public); provider rate limits and API latency under 4-way concurrency; the Codex subscription's
marginal cost (list-priced for comparison only); the 30B AWQ/GGUF identity (UNVERIFIED bytes); anything about Run 1 or Run 2's claims.

## 6. Steps (after the operator approves Run 3)

1. Run the three cloud arms as pre-registered; build ledgers with `../ledger/ledger_build_run3.py`.
2. Emit the sidecar `tierbench-calls.jsonl` per arm (BRIDGE.md 2e) from `detailed.json` + `grade/evaluation.json`; import with
   `import_tierbench.py --receipts` once the sidecar reader lands (open question in BUILD-REPORT.md).
3. Run haiku and luna on the same frozen prompts through a route.py-style validator-backed runner, three cycles, keeping the receipts;
   import them as route receipts (cost DERIVED from list) and reconcile against the provider dashboard (Tier-Bench `reconcile()`).
4. Run qwen3.5:9b on the estate 3090 after ~09-28 with the plug meter; record the seat lease in the run ledger.
5. Re-run `tier_waterline.py plan` with the new evidence: the chosen tier and the seat plans are then measured, and the residue list is
   the deliverable for the residue tiers.
