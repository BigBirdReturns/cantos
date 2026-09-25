# Evaluate a compute shop

This procedure assesses a provider against a buyer's stated workload and operating needs, records how its service performs, and identifies what to adopt, repair, or investigate. Hot Aisle (HA) is a dated reference observation, not a universal grade or gold standard. The kit has not yet been qualified on a new Linux/GPU shop; scripted tests use a local synthetic SSH fixture and do not establish real provider performance.

## 1. Set the decision and evidence boundary

Write the decision in buyer terms: “For workload W, can service S deliver acceptable output Q by deadline D at total cost C, with recovery R and operator effort E?” Name the smallest unit observed: public offer, one account, one allocation, one SKU in one region, or an agreed fleet sample. Capture date/time, region, SKU, GPU count/partition, CPU/RAM, storage, virtualization, image, driver/runtime, network/client location, workload/evaluator revisions, prices, billing minimums, and account tier. Unknown facts stay unknown. A single allocation does not characterize a fleet.

Choose the access mode and write its limits:

| Mode | Can establish | Remains outside the evidence |
|---|---|---|
| Public desk review | Dated offers, docs, public support/terms/status claims | Actual delivery, capacity, billing, customer experience, host condition |
| Customer rental | Account and SKU acquisition, assigned config, workload, own billing/support, release | Hidden topology, other tenants, physical conditions or unexposed policy |
| Cooperative host | Explicitly approved configuration, telemetry, fleet sample, incident/recovery records | Unobserved hosts, other tenants, or untested causal claims |

Label each claim with the kit's evidence class: **published_claim**, **operator_report**, **measured**, **derived**, or **hypothesis**. A provider page is a published claim until measured; an operator's report remains self-reported; a ticket acknowledgement is not a resolution; a hash preserves identity but does not prove source truth. Keep these evidence classes visible in the report.

## 2. Freeze scope, budget, and stop/release plan

Complete the workload and access worksheet before acquisition. Freeze accepted-output rules, offered-load schedule, timeout/retry policy, precision, image digest, software versions, input identity, warm/cold state, repetition count, cost basis, measurement window, and planned interventions. Declare one comparison label: **matched**, **different complete configuration**, **historical**, or **not comparable**. Different GPUs can still be compared for buyer-level economics when the accepted work and cost window match; that does not isolate operator quality. Tail latency is an outcome being measured, so a tail difference alone does not invalidate comparison. Differences in workload, traffic, acceptance rules or cost window must be disclosed and can limit the claim.

For the current combined Hot Aisle campaign, the authorized provider-charge ceiling is **$50**, including failed attempts, setup/drain time, storage, egress and billing minimums; record deposits or prepaid balance separately from actual spend. CPU-side wall time and energy are recorded separately and are not included in that provider-charge cap; if unknown, say so. Every other assessment must declare its own authorized cap. Estimate the provider bill before starting and monitor it during the run. `evaluate.sh` cannot enforce the account's spend limit. If the forecast approaches the applicable cap, a resource is unsafe, cost cannot be monitored, or access/release becomes uncertain, stop workload activity and use the provider's documented control plane to release the allocation. The evaluator must identify a human release owner and confirm billing cessation later. This tool never rents, changes the account, contacts the provider, or deletes the machine.

Only run approved synthetic or buyer-cleared data. Do not touch other tenants or test isolation by accessing their data. Process termination on a disposable job is an acceptable controlled failure when pre-authorized and recoverable. Host resets, firmware/power changes, network disruption, reimage and physical faults require the host operator's explicit authority. If a failure test is not safe, record recovery as unobserved.

## 3. Intake and run the bounded campaign

Before rental, record public price and terms, region/SKU availability, account/KYC/card/quota/sales gates, image support, access method, support path and release steps. For an actual rental, record submitted-create, allocation, SSH-ready, workload-ready, first-accepted-work, delete and billing-confirmation times separately. Distinguish listed, attempted, allocated, access-ready, workload-ready and released capacity.

Prepare the CPU-side evaluator, pinned inputs, SSH key, evidence destination and release plan first. The operator creates the account and machine, installs the public key, checks the assigned configuration, then runs from the `shop-eval` directory:

```sh
SHOP_EVAL_RUNS_DIR="$HOME/.local/share/axm-tools/shop-eval/runs" \
SHOP_RATE=1.25 EVALUATE_RUN_TAG=trial-01 bash evaluate.sh <shop-slug> <amd|nvidia> <user@host> [ssh-key]
```

Use a unique lowercase shop slug and run tag. The target must be a plain `user@DNS-name`, IPv4 address or safe SSH config alias. The script copies the fingerprint probe and pinned workload arm, records the remote PID/exit state, waits for completion with a 120-minute default poll limit, retrieves the fingerprint and workload output, verifies each manifest, writes an engine table, and passes that table file to diagnosis. Run data stays outside the checkout in `$HOME/.local/share/axm-tools/shop-eval/runs/` by default; `SHOP_EVAL_RUNS_DIR` can point to another private directory outside the checkout. Existing run identities are never overwritten. A nonzero exit means collection/scoring is incomplete; preserve the run and read its final log block before taking the next action. A timeout leaves remote status unresolved; inspect the remote log/exit file and control plane, then release the allocation by the documented action. It never provisions or releases a provider resource.

If collection finished but the billed or chosen modeled rate becomes known later, rescore from local retained data only:

```sh
bash evaluate.sh --rescore "$HOME/.local/share/axm-tools/shop-eval/runs/<shop>-<UTC-date>-<tag>" 1.25
```

This mode makes no SSH call. It verifies the source run's sealed manifest and writes a new sibling `<source-run>-rescore-<tag>/` with `RESCORE.json`, the derived score table/report and its own manifest. The source evidence, report and manifest remain byte-for-byte unchanged. Do not edit original observations to “fix” them; correct a source in a new record or explain the correction alongside the retained evidence.

The `evaluate.sh` workload is Run 1's pinned single-GPU synthetic LLM serving configuration with random inputs and latency/acceptance gates. It is distinct from the quality-graded workload in [the combined campaign notes](COMBINED-CAMPAIGN.md). The fingerprint does not run an active GPU-load sample by default; the probe's explicit `--gpu-load` option runs a bounded 30-second sample. Snapshot and short-load results are diagnostic evidence, not proof of sustained performance or physical root cause. Neither workload measures multi-GPU scaling, multi-node behavior, fleet reliability, negotiated pricing or full-cycle invoice accuracy.

## 4. Preserve the Hot Aisle baseline and cost bases

The retained Run 3 HA A/T0 reference is one configuration/run: 4,336 accepted out of 8,622 scheduled; TTFT p50/p95/p99 53/155/571 ms. The retained DO H100 observation is 4,280 accepted out of 8,622; TTFT p50/p95/p99 35/76/2,254 ms. These counts/tails describe those observed windows only. Keep the source run IDs, gate, load and completion deadline beside them. The figures are prior observations, not proof of universal HA performance or fleet capability. Record the comparison label as **matched**, **different complete configuration**, **historical**, or **not comparable**. Different hardware can still inform buyer-level performance-per-dollar for the same accepted work and cost window, but does not isolate operator quality. Tail latency differences remain valid measured outcomes.

Keep the HA cost bases separate: **$0.74** is a modeled dedicated-equivalent arm window of about 64.7 minutes, not an actual cold invoice; **about $0.90 per 1,000 accepted requests** is a mixed-window shared-seat ratio over 9,086 mixed-arm accepted requests, including smoke, setup and gaps, with invoice unreconciled, so it is not a steady-state figure; **$1.0845** is an old per-arm ledger lower bound from SSH to work-end and covers a different setup window. These are different windows; do not combine or average them. For every candidate report separately: (a) steady-state cost per accepted unit with the window and included work named; (b) modeled allocation cost at the stated rate plus billing minimum; (c) actual provider invoice, credits and any reconciliation gap; and (d) customer total, including provider charges, transfer/storage and customer-side operator time or labor cost when known. Mark each unknown explicitly. Provider operator economics—such as margin, utilization, capital cost and support labor—remain unknown without internal provider data and must not be inferred from customer prices or benchmark results.

The counter records account, pricing, provisioning, availability, interface, billing, tenant, network, support and termination evidence. Treat its fields as operational observations with explicit evidence and denominator. Any weighted total from older records is a chosen convention, not a provider-quality claim, purchase gate or leaderboard. Preserve raw observations and decide buyer requirements using the report status rules below. A failure row and an unknown row must never collapse into the same result.

## 5. Record results and make the report reviewable

Keep every attempt, failed cell, partial result, manual intervention and stop reason. Report all denominators and repetitions, median/range where repeats permit, plus the exact configuration and time window. Thousands of requests from one warm process are not thousands of independent provider trials. Separate exploration from frozen confirmation, and validate a proposed improvement on fresh repeats or held-out inputs. A faster result after changing quality, precision, input, arrival rate or evaluator is a new comparison scope.

Use one row per buyer requirement with **PASS** (measured threshold met), **FAIL** (measured miss), **UNKNOWN** (not established) or **N/A** (reason required). Add evidence class/source, measured value and denominator, threshold, configuration/date, interpretation, caveat, owner, next action and retest condition. Report four findings plainly: what the provider does well and the buyer should adopt; where it misses this workload; what could improve and the discriminating test; and what remains unknown. Include operator effort, support interventions, recovery time/data loss, cost bases, scope and sample limits. Generated diagnosis is an aid for review, not verified causality or an automatic prescription.

For recovery, stop only a disposable test process with a documented supervisor, then record detection, acknowledgement, repair, readiness, resumed useful work, rework, output identity and operator minutes. A reboot or successful SSH does not prove workload recovery. For handoff, give a second operator the sanitized procedure, pinned inputs/configuration, expected outputs, release steps and support path without coaching. Record their elapsed time, questions and deviations. If they cannot reproduce the result, fix the nearest instruction gap and retest before calling the procedure reusable.

## 6. Release and share safely

After the run, inspect the provider console and release the exact allocation; record confirmation and later invoice/balance evidence. Revoke temporary keys/tokens and retain results only in approved custody. Never claim billing stopped solely because a VM disappeared from SSH. The run manifest covers captured files; verify it after any authorized local rescore or report update.

An open, vendor-neutral procedure may share commands, schemas, synthetic fixtures and sanitized outcomes when rights permit. Remove keys/tokens, private IPs, account IDs, customer data, private topology, ticket contents and unpublished host details. Keep source evidence separately and retain provenance. Mark local scripted fixtures and sample records **synthetic**; never present them as a successful provider run. Independent replication on another operator's eligible machine is a separate validation step. No outbound outreach is part of the default assessment procedure.
