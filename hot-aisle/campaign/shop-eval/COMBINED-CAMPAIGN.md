# Combined Hot Aisle reference campaign

Status: **prepared, not executed here**. This is a bounded plan for the owner-operated Hot Aisle account and the retained Run 3 kit. It does not rent or provision a VM. Execution depends on a matching one-GPU MI300X allocation becoming available, the frozen task/trace artifacts passing identity checks, and the already-authorized CPU grading path remaining usable. No larger-seat or fleet-quality claim follows from this campaign.

## Question and acceptance

First establish a repeatable waterline for the existing Run 3 MI300X condition. The retained result is one observation: **4,336 / 8,622 accepted requests**, with acceptance requiring the per-request correctness label and both the 1 s TTFT and 60 s completion limits. It is not a fleet estimate or uncertainty interval. Keep the exact Run 3 task set, pinned serving image/model, seed and T0 configuration. The production EvalPlus label is `correct` only when both base and plus tests pass; a transport error, missing result, or deadline miss cannot pass. Keep all scheduled arrivals in the denominator.

Use the frozen trace and its checked hash, not a generated schedule. The retained calibration ceiling is rate factor 0.95. Root verified the existing replay CLI against the frozen trace: duration 3600 s at factor 0.95, 1800 s at 1.9, and 900 s at 3.8 each schedule the same 8,622 arrivals, with matching normalized arrival times. The compressed cases are separate duration/load conditions and do not count as full-hour Run 3 repeats. Preserve each actual request drain and allocation-to-release time in the cost record.

## Spend and sequence

The campaign's current compute ceiling is **$50 at the observed public Hot Aisle rate of $2.99/GPU-hour**. This is a spend cap, not an assumed invoice or guaranteed allocation duration. Five one-hour workload windows represent 5 GPU-hours / **$14.95 of workload-window price**; boot, serve, profiling, final drain and release time add billable duration. Record actual billable time and list-rate cost. CPU grading runs on the already-authorized CPU path; record its wall time and energy/cost as separate fields, never as free or included in the GPU estimate. Unknown costs remain unknown.

1. **Five full-hour Run 3 repeats:** if three separate allocations are available, run 2 / 2 / 1 repeats across them. These are repeated observations, not independent fleet evidence. Capture the read-only hardware/software fingerprint on every boot, before serving; preserve all raw logs and sealed outputs. Reuse the authorized pinned grader image, and verify its source/task/trace identities before the first GPU call. Run the exact retained condition in each repeat. Pass `--funding credit:hotaisle` to `arm3.sh`: that records declared Hot Aisle credit funding, not a reconciled invoice. Do not discard failed, slow, incorrect or deadline-missing arrivals.
2. **Separate compressed-load envelope:** run two 30-minute trials (factor 1.9) and two 15-minute trials (factor 3.8), with the same source arrivals and acceptance rule. On allocation 1, alternate 1.9 / 3.8 / 3.8 / 1.9 between full-hour repeats 1 and 2 so those load trials share one allocation. Report each as a diagnostic condition, including accepted rate, tail latency, errors and drain cost; do not pool them with the full-hour repeats.
3. **One runtime change control:** on allocation 2, bracket one bounded T1 runtime-variable trial between full-hour repeats 3 and 4, restoring T0 afterward. Keep hardware, tasks, trace, seed, precision and acceptance fixed. Write the single changed variable and expected observable into the run record before execution. Do not tune repeatedly and select the best result. The T0 reversion is a repeat, not an extra sixth baseline.
4. **One application failure/recovery check:** after full-hour repeat 5 on allocation 3, run a separately labeled short replay. Stop only this campaign's serving container mid-run, restart the same pinned service, then replay future arrivals. Time fresh health and replay resumption. The journal must retain completed, failed and uncertain requests; missed deadlines stay failures, and later retries cannot retroactively count as accepted in the original window. No host reset or unrelated container is part of this drill. It checks application recovery/accounting, not transparent resume or hardware fault tolerance, and remains NOT RUN until a seat is available.

At $2.99/GPU-hour, use this planning ceiling (not a runtime guarantee or invoice): setup/profile across three boots, 3 h ($8.97); five full-hour baselines, 5 h ($14.95); compressed load, 2 h including 1.5 h scheduled trials and drain ($5.98); one bounded T1 trial plus restore, 2 h ($5.98); recovery drill, 1 h ($2.99). That is a conceptual 13 h / **$38.87**, leaving **$11.13** below the $50 ceiling for overruns or a necessary clean repeat. CPU grading time and energy/cost are separate and currently unknown. Bound and record actual allocation-to-release duration before continuing; do not spend merely to use the cap. A future **$16 reserve for two control trials** is separate, funded only from later remaining credit, and never charged to this $50 envelope.

## What to report

For every repeat retain task/trace/image/grader hashes, config and seed, fingerprint per boot, request-level correctness/TTFT/completion labels, errors, missingness, start/readiness/work/drain/release times, and modeled list cost. Report all five outcomes plus median and range; with five repeats, describe observed variation without claiming universal statistical significance. Also show accepted-count ratio to the single retained 4,336/8,622 observation, clearly marked as an exploratory comparison against one historical run. Report compressed-load, runtime-change, and recovery outcomes in separate rows.

Record current create attempts only for the exact GPU SKU and region actually requested; an offer listing or a different region/SKU is not delivered capacity evidence. Keep capacity unknown until a real create attempt supports it. Keep invoice amounts distinct from estimated/list-price cost and from account credit. Do not derive a provider ranking from missing availability denominators or a composite score whose flag is uncalibrated.

Use Run 3's `arm3.sh`/replay path for these runs, for example `bash "$KIT/arm3.sh" amd T0 --approved-run --funding credit:hotaisle ...` with the frozen task/trace arguments from `run3/README.md`. The older Run 1 `arm.sh` AMD image is vLLM 0.27.1-dev and is not a substitute for this pinned Run 3 configuration. Record trial order and warm-up context; compare the five retained T0 repeat outputs separately from compressed-load, T1 and recovery rows. Keep per-boot fingerprints and provider/account profile material in private campaign custody until reviewed; do not copy it into public report output by default.

## One seat, then scale

Start with one VM and one GPU to establish the workload and accepted-work unit. Expand only when a specific question needs the next topology:

| Configuration | Question answered | Comparison boundary |
|---|---|---|
| 1 VM / 1 GPU | Can this shop repeat the accepted-work baseline? | Primary Hot Aisle waterline |
| 1 VM / 4 GPUs, sharded | Does one job sharded across four local GPUs improve accepted work per cost and deadline? | Same model/workload; record tensor parallelism and whole-allocation cost |
| 1 VM / 4 GPUs, independent replicas | Does one four-GPU VM serve four independent jobs more effectively than one-GPU seats? | Independent jobs; include replica scheduling, per-job acceptance, aggregate accepted work and whole-allocation cost |
| 4 single-GPU VMs | Does independent-job throughput scale across allocations? | Separate jobs; include scheduler, staging and aggregate capacity limits |
| Multi-node fabric | Does network topology support distributed serving/training, including recovery? | A distinct network and fault-recovery track |
| Repeated allocations over time | Are availability and delivered configuration stable? | Multiple create attempts across dated windows; not inferred from one VM |

Larger hardware is not automatically a better reference. Each added topology is a new condition with its own measured accepted-work, cost, variation and recovery evidence. Profile each fresh boot. Keep Run 1's latency-only result separate from this Run 3 correctness-and-deadline acceptance.

## Holds and authority

The campaign is not all-tracks-ready. No provider rental, external network test, or machine change is part of this preparation. The owner retains Hot Aisle account access, the exact allocation/create action, and Run 3 execution. Do not proceed with a GPU run if the selected image, task/trace hashes, application health, grader identity or output destination fails its preflight. Preserve that failure as a hold. A passing local replay or probe test is preparation evidence, not a completed Hot Aisle campaign.
