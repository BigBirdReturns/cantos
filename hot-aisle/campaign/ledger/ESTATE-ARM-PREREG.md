# Estate arm of Run 3 · pre-registration (draft for freezing, r2)

Status: **DRAFT, not frozen.** Freeze = commit this file with every UNVERIFIED item resolved, before the 3090 is touched. Runs after about **2026-09-28**, when the W01 RTX 3090 frees up from SeedVR2. Nothing here asserts a result.

r2 (fix round 1, 2026-09-24): cells are **time-boxed**, so the schedule bounds its own watchdog by construction; per-request deadline and output cap set; interruption retention specified; footprint bytes separated from traversed bytes.

**Question.** On an estate seat whose VRAM cannot hold the model, how many accepted closures does one weight traversal buy, and what does one accepted closure cost in wall clock and metered watts, as batch depth increases?

This is the measurement the SYNTHESIS Correction calls missing: "one model that does not fit, streamed end to end, running a graded task batch at increasing depth. Report traversals, seconds and bytes per traversal, accepted closures per traversal, and cost including metered watts."

## Which path this measures (read this first)

**Path A (primary): llama.cpp partial offload, `split-vram-ram`.** `-ngl 22` puts 22 of 36 layers in the 3090's VRAM; the other 14 stay in host RAM and are computed by the CPU. Nothing streams across PCIe per decode step except activations (kilobytes). A "traversal" here is one decode step over both memory domains: GPU layers from GDDR6X, CPU layers from DDR.

**This is not the doctrine's streaming path** (checkpoint → RAM → hot aperture → fused kernel), for which no code exists (SYNTHESIS: "Not yet shown: ... hot-aperture or fused-kernel code"). Path A is registered because it is the only end-to-end token path on the estate with a receipt, on this exact seat and model.

**Path B (secondary, no closures): true link streaming at slice scale.** The existing Kimi-K3 expert-slice worker reads packed expert bytes from disk/RAM to the GPU per layer (receipts: 2.88 GB in 19.8 s cold, 3.52 s warm on the 4060). Path B reports bytes per traversal and seconds per traversal over the link only; it produces no tokens and therefore no accepted closures. It is included so the record holds one measured streamed-link number beside the split-path number, and is labelled as such.

## Pinned (resolve UNVERIFIED before freezing)

- **Seat:** `estate-w01-3090` (seats.json): RTX 3090, PCI `00000000:25:00.0`, UUID `GPU-0b31e56a-…`, host OCTO-W01, i5-13500T, 31.77 GiB RAM. UNVERIFIED: the card's negotiated PCIe link; record `nvidia-smi -q | grep -A2 "Link"` at start.
- **Model:** `S:\Models\EST-FABRIC-NET-TETHER-1\gpt-oss-120b-Q2_0.gguf`, 33,745,206,528 B, 116.8 B params (MoE, ~5.1 B active). Does not fit 24 GB. UNVERIFIED: file sha256 and the upstream quantization source; record both.
  - *Why this model:* it is the only over-VRAM model with a token-rate receipt on this seat (B1: 12.44 ± 1.20 tok/s generation, 94.92 ± 9.87 tok/s prompt at `-ngl 22`, 2026-09-09). Sizing below comes from those numbers.
  - *Continuity variant, optional:* `Qwen3-Coder-30B-A3B-Instruct` Q8_0 GGUF (~32 GB, UNVERIFIED size/revision, not on disk) continues Run 3's model. It runs only if Path A finishes inside the watchdog, as a separate labelled cell set, never in place of the primary.
- **Engine:** llama.cpp `b10665` prebuilt Windows x64 CUDA 12.4 (RUNLOG binding, commit `ca3d5a3e1`), `llama-server`. UNVERIFIED: whether `b10665` `llama-server` exposes `llamacpp:n_decode_total` on `/metrics`; if not, traversals come from the per-request `timings.predicted_n` and slot counts, and the record says which.
- **Serve flags, identical for every cell:** `-ngl 22 -c <4096 × depth> -np <depth> --flash-attn auto -t 14 --metrics` (default mmap). KV cache dtype default. `-ngl 22` is fixed at every depth (it is the measured configuration).
- **Sampling:** temperature 0, **`max_tokens 512`**, chat template on, reasoning effort **low** via the chat-template kwargs (gpt-oss emits an analysis channel; UNVERIFIED flag name in `b10665`). Outputs that hit the cap are completed-not-correct unless EvalPlus passes them anyway.
- **Per-request deadline: 75 s** from send (streaming; the client closes the socket, like `run3/replay.py` does at 60 s). A request that hits it is `lost` (sent, unanswered). At the measured 12.44 tok/s a full 512-token output takes ~41 s plus ~2 s prompt, so the deadline binds only slowdowns at depth, not normal completions.
- **Evaluator:** EvalPlus **HumanEval+** (164 tasks), frozen: pin the `evalplus` version and dataset hash here before freezing (UNVERIFIED now). Grading on `estate-w01-cpu` in a container/venv, never on the serving process.
- **Meter:** a wall-socket plug meter on OCTO-W01 sampled at ≥ 1 Hz with a machine-readable log (**operator must supply**; no metered-watts receipt exists in the estate). Also `nvidia-smi --query-gpu=power.draw,memory.used --format=csv -lms 1000` for the whole run as a labelled GPU-only proxy. If no plug meter exists at freeze, `money.energy.*` stays null with the reason "no wall meter" and the GPU proxy is reported separately, never as the cost.
- **Tariff:** operator supplies $/kWh; otherwise `tariff_usd_per_kwh` null.

## Cells: time-boxed, not count-boxed

One depth per cell. Each cell is a **70-minute box**: tasks are issued in fixed order (task id ascending) until the **65-minute issue cutoff**, then the box drains until 70:00 and the server is stopped. Whatever finished is the cell. This is what bounds the watchdog: **3 cells × 70 min + load (≤ 5 min each, from the 98 s llama-bench wall including load) + Path B (10-minute box) = 3 h 55 min ≤ the 4.5 h watchdog**, regardless of how slow decode turns out.

| cell | depth (`-np`) | context total | issued up to | estimate from B1 (mean ~300 out tokens) | bound |
|---|---|---|---|---|---|
| d1 | 1 | 4096 | 164 tasks or the 65-min cutoff | 164 × (~200 in / 94.9 + ~300 out / 12.44) ≈ 164 × 26 s ≈ **71 min** → expect ~150 of 164 in the box | 70 min |
| d4 | 4 | 16384 | same | ≤ d1's rate if depth buys nothing; more closures if it does | 70 min |
| d16 | 16 | 65536 | same | may OOM at `-ngl 22` (see stop rules) | 70 min |

The "71 min" is an **estimate**; the worst case (every request hitting the 75 s deadline) is bounded by the box, not by the estimate: at depth 1 that is ≥ 52 tasks issued and finished per box. The registered outputs are per box, so a slower-than-estimated seat yields fewer closures, not a blown watchdog.

Order: d1, d4, d16, then Path B, then the optional continuity variant (only if ≥ 75 min of watchdog remain, in its own boxes).

### Interruption retention

- Tasks not issued before the cutoff are **unsent**: recorded with `error: unsent_at_cutoff`, counted in `attempted` only if the ledger line says so (it does not: `attempted` = issued), and listed by id so a later cell or seat can pick them up (Knot `INTERRUPTED → REASSIGNED`).
- Tasks issued and not finished by 70:00 are **lost** (`error: lost_at_box_end`), counted in `attempted` and `lost`, never in `completed`.
- The journal is append-only per request (`journal.jsonl`, fsync per line, as `run3/replay.py` does); an interrupted box is recovered from the journal and retained as incomplete, never promoted.

## What each cell records (the ledger's traversal group)

- **traversals** = `llamacpp:n_decode_total` delta over the box (or the declared fallback).
- **seconds_per_traversal** = decode wall clock ÷ traversals; also the per-request `timings` from llama-server.
- **footprint_bytes** = VRAM-resident model bytes + RAM-resident model bytes as printed by llama.cpp at load (`CUDA0 model buffer size`, `CPU model buffer size`). This is what is **allocated**.
- **bytes_per_traversal** = **null** unless measured: gpt-oss-120B is MoE, only the active experts are read per step, and nothing in this protocol measures that. Footprint is not traversed bytes and is never written into this field.
- **accepted_closures_per_traversal** = EvalPlus passes (base + plus tests) ÷ traversals. Also accepted ÷ box-second and accepted ÷ kWh.
- **work**: attempted (= issued), completed, correct (EvalPlus pass), accepted (= correct; no latency gate in this arm, declared), lost, unsent (listed), restarts.
- **money.energy**: `watts_mean` from the plug meter over the box, `kwh`, `usd` if a tariff exists; idle baseline watts for 5 min before d1 and after the last cell.
- **clocks**: `t_request` = the operator's lease note; `t_ready` = first `/health` OK; `t_work_start` / `t_work_end` per box and overall; `t_released` = server stopped **and** GPU memory freed (`nvidia-smi` shows the baseline). On an owned seat release is the operator's act; it is still recorded.

Every cell writes its ledger line with `ledger_validate.py`, and the Knot walks `ISSUED → PROVISIONED → RUNNING → DELIVERED → KNOT_VERIFIED → SETTLED(authority: energy | none) → RELEASED` in `events.jsonl`.

## Gates and stop rules

- No gate decides a winner; there is no comparator arm. The registered outputs are the traversal numbers per box.
- **OOM at d16 with `-ngl 22` is a result**, recorded as a failed cell (its box still counts against the watchdog only for the time it used). A labelled fallback `-ngl 18` d16 may run in a fresh 70-minute box afterwards if the watchdog allows; it never replaces the registered cell.
- Server not healthy within 15 min of start: stop, keep the log.
- Watchdog **4.5 h from `t_ready`**, enforced by an outer `timeout` on the whole script (as `run3/arm3.sh` does): TERM at 4:30, KILL at 4:31; the finally-block stops the server and seals the manifest. By construction the schedule above ends at ≤ 3 h 55 min.
- Any box whose grader cannot run all issued tasks is recorded as incomplete, not dropped.
- Host must be otherwise idle (no SeedVR2, no other GPU or CPU jobs); record `nvidia-smi` and top-5 CPU processes at start.

## Equivalence smoke

Three fixed prompts, greedy, 64 tokens, saved as `smoke-*.json` (same three as `run2/arm2.sh`), to show the served model answers, not to judge quality.

## What this arm does NOT claim

- Nothing about the doctrine's hot-aperture path; Path A is a CPU/GPU split, and the record says so on every line.
- Nothing about a dense 70B or 405B: this model is a 120B MoE at 2-bit, chosen because it is the only over-VRAM model with a receipt on this seat.
- Nothing about bytes traversed per step (unmeasured for MoE); only footprint is recorded.
- No cost comparison with Hot Aisle or DigitalOcean unless the same graded batch has run there under Run 3; then `$/accepted` and `accepted closures per traversal` sit side by side with the Run 3 seats' numbers.

## Waterline check

`python waterline.py plan fixtures/knots/knot-estate-arm-120b.json --start-at 2026-09-29T10:00:00Z` plans this Knot on `estate-w01-3090` over the measured B1 curve at depth 1 (164 × 301 traversals × 0.0804 s ≈ 66 min of work, inside one box) and marks every plan UNMEASURED (setup unknown; depths 4 and 16 extrapolated): exactly the numbers this arm exists to measure. Before 09-28 it refuses with "declared busy".
