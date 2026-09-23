# Estate arm of Run 3 · pre-registration (draft for freezing)

Status: **DRAFT, not frozen.** Freeze = commit this file with every UNVERIFIED item resolved, before the 3090 is touched. Runs after about **2026-09-28**, when the W01 RTX 3090 frees up from SeedVR2. Nothing here asserts a result.

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
- **Serve flags, identical for every cell:** `-ngl 22 -c <4096 × depth> -np <depth> --flash-attn auto --no-mmap off (default mmap) -t 14 --metrics`. KV cache dtype default. `-ngl 22` is fixed at every depth (it is the measured configuration).
- **Sampling:** temperature 0, `max_tokens 1024`, chat template on, reasoning effort **low** via the chat-template kwargs (gpt-oss emits an analysis channel; UNVERIFIED flag name in `b10665`). Truncated outputs count as completed-not-correct.
- **Evaluator:** EvalPlus **HumanEval+** (164 tasks), frozen: pin the `evalplus` version and dataset hash here before freezing (UNVERIFIED now). Grading on `estate-w01-cpu` in a container/venv, never on the serving process.
- **Meter:** a wall-socket plug meter on OCTO-W01 sampled at ≥ 1 Hz with a machine-readable log (**operator must supply**; no metered-watts receipt exists in the estate). Also `nvidia-smi --query-gpu=power.draw,memory.used --format=csv -lms 1000` for the whole run as a labelled GPU-only proxy. If no plug meter exists at freeze, `money.energy.*` stays null with the reason "no wall meter" and the GPU proxy is reported separately, never as the cost.
- **Tariff:** operator supplies $/kWh; otherwise `tariff_usd_per_kwh` null.

## Cells

One depth per cell; the full 164-task batch per cell; tasks in fixed order (task id ascending); one repeat.

| cell | depth (`-np`) | context total | prompts | expected work (sized from B1) |
|---|---|---|---|---|
| d1 | 1 | 4096 | 164 | 164 × (~200 in / 94.9 + ~300 out / 12.44) ≈ 164 × 26 s ≈ **71 min** |
| d4 | 4 | 16384 | 164 | ≤ 71 min if depth buys nothing; less if it does |
| d16 | 16 | 65536 | 164 | ≤ 71 min worst case; may OOM at `-ngl 22` (see stop rules) |

Total worst case ≈ 3.6 h of work plus one load (~2 min per the 98 s llama-bench wall including load). **Watchdog: 4.5 h**, which the schedule fits (Run 2's did not). Path B is one extra ~10-minute cell on the 4060 or 3090 (two layers, cold and warm), run after Path A or skipped if the watchdog is near.

Order: d1, d4, d16, then Path B, then the optional continuity variant.

## What each cell records (the ledger's traversal group)

- **traversals** = `llamacpp:n_decode_total` delta over the cell (or the declared fallback).
- **seconds_per_traversal** = decode wall clock ÷ traversals; also the per-request `timings` from llama-server.
- **bytes_per_traversal** = VRAM-resident model bytes + RAM-resident model bytes as printed by llama.cpp at load (`CUDA0 model buffer size`, `CPU model buffer size`). MoE note: only the active experts are read per step; the nominal resident bytes are reported with that caveat, not an active-bytes claim.
- **accepted_closures_per_traversal** = EvalPlus passes (base + plus tests) ÷ traversals. Also accepted ÷ wall-second and accepted ÷ kWh.
- **work**: attempted 164, completed, correct (EvalPlus pass), accepted (= correct; no latency gate in this arm, declared), lost, restarts.
- **money.energy**: `watts_mean` from the plug meter over the cell, `kwh`, `usd` if a tariff exists; idle baseline watts for 5 min before d1 and after the last cell.
- **clocks**: `t_request` = the operator's lease note; `t_ready` = first `/health` OK; `t_work_start` / `t_work_end` per cell and overall; `t_released` = server stopped and GPU memory freed.

Every cell writes its ledger line with `ledger_validate.py`, and the Knot walks `ISSUED → PROVISIONED → RUNNING → DELIVERED → KNOT_VERIFIED → SETTLED(authority: energy | none) → RELEASED` in `events.jsonl`.

## Gates and stop rules

- No gate decides a winner; there is no comparator arm. The registered outputs are the four traversal numbers per cell.
- **OOM at d16 with `-ngl 22` is a result**, recorded as a failed cell. A labelled fallback `-ngl 18` d16 may run afterwards; it never replaces the registered cell.
- Server not healthy within 15 min of start: stop, keep the log.
- Watchdog 4.5 h from `t_ready`: stop after the current cell.
- Any cell where the grader cannot run all 164 tasks is recorded as incomplete, not dropped.
- Host must be otherwise idle (no SeedVR2, no other GPU or CPU jobs); record `nvidia-smi` and top-5 CPU processes at start.

## Equivalence smoke

Three fixed prompts, greedy, 64 tokens, saved as `smoke-*.json` (same three as `run2/arm2.sh`), to show the served model answers, not to judge quality.

## What this arm does NOT claim

- Nothing about the doctrine's hot-aperture path; Path A is a CPU/GPU split, and the record says so on every line.
- Nothing about a dense 70B or 405B: this model is a 120B MoE at 2-bit, chosen because it is the only over-VRAM model with a receipt on this seat.
- No cost comparison with Hot Aisle or DigitalOcean unless the same graded batch has run there under Run 3; then `$/accepted` and `accepted closures per traversal` sit side by side with the Run 3 seats' numbers.

## Waterline check

`python waterline.py plan fixtures/knots/knot-estate-arm-120b.json --start-at 2026-09-29T10:00:00Z` plans this Knot on `estate-w01-3090` over the measured B1 curve at depth 1 (164 × 301 traversals × 0.0804 s ≈ 66 min) and flags depths 4 and 16 as extrapolated: exactly the numbers this arm exists to measure. Before 09-28 it refuses with "declared busy".
