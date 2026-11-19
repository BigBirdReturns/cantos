# Retry campaign resource accounting

The resource adapter joins complete, validated retry campaigns to timestamped GPU board power samples. It uses the unchanged Open Compute Ledger trapezoidal integration and cost functions pinned in `retry_resources.SOURCES.json`. The campaign denominator includes all offered work, including failed attempts and exhausted tasks.

## Capture and join

Start the read-only sampler before running the campaign. Supply exact NVIDIA GPU UUIDs from the machine under test, a fresh journal path, a fresh stop marker, and the sampling tolerance declared before capture. The sampler retains raw sensor output and flushes every record. It changes no GPU settings.

~~~sh
python -B compute/maintainer/retry_resources.py record \
  --out /absolute/power.jsonl --device GPU-EXACT-UUID \
  --stop-file /absolute/STOP-POWER --interval-s 0.25 \
  --max-gap-s 2.5 --max-seconds 1800
~~~

Run the campaign in a second process after the first power sample exists. Create the stop marker after the campaign reaches its terminal state. Wait for the sampler to exit, then seal and analyze:

~~~sh
python -B compute/maintainer/retry_resources.py seal \
  --campaign /absolute/campaign/retry-campaign.json \
  --journal /absolute/power.jsonl --out /absolute/telemetry.json
python -B compute/maintainer/retry_resources.py analyze \
  --campaign /absolute/campaign/retry-campaign.json \
  --telemetry /absolute/telemetry.json --out /absolute/resources.json
~~~

The telemetry manifest binds the exact campaign SHA, observation identity, OS clock identity, selected device list, predeclared maximum sample gap, producer hash and raw journal hash. Sealing records these bindings; analysis validates them. Samples must bracket the complete campaign window and increase in time. Missing brackets, oversized gaps and sensor failures inside that window keep energy unknown. A process-interrupted campaign remains incomplete and cannot supply a complete useful-work denominator.

`gross_board_joules` integrates the named boards over the full campaign, including queuing, failed attempts, retry backoff and grading windows. `gross_board_joules_per_accepted_task` divides that total by eventual accepted tasks and remains null when none succeed. Gross board energy includes resident-model idle and any other load on those boards. CPU grading, other hardware, server startup and facility overhead fall outside the measurement. Driver power reports remain uncalibrated sensor estimates.

Linux joins use the observed host and boot ID with the monotonic clock. A different boot or clock identity is rejected. On systems with only a process-local clock identity, independent collectors require an established shared timebase before the join can qualify.

## Declared cost scenarios

Pass `--scenario /absolute/scenario.json` to analyze under explicit assumptions. The scenario schema is `cantos.retry.cost-scenario/1`, currency is `USD`, and each non-null value requires a corresponding source or stated assumption under `field_sources`. Supported values are capex, residual, life_hours, utilization, financing_usd_per_hour, hosting_usd_per_hour, operations_usd_per_hour, maintenance_usd_per_hour, network_usd_per_hour, electricity_usd_per_kwh, pue, intervention_seconds, intervention_usd_per_hour and average_it_power_w. Capex and residual use the exact keys `capex_usd` and `residual_usd`.

The model applies the entire campaign duration, including failed work, to declared time-based charges. Missing components preserve an unknown full total; an explicit zero needs an assumption or source like every other value. GPU-only electricity remains scoped to those boards and cannot supply facility energy through PUE. An independently declared whole-IT power scenario can model that different boundary. Scenario arithmetic establishes modeled cost under the inputs. `actual_total_cost_usd` remains null because this instrument does not collect bills or metered financial transactions.

## Acceptance evidence

The focused resource tests include an independent piecewise-linear 50-joule oracle, all-failure denominator handling, exact clock and observation binding, multi-device accounting, missing samples, failed sensor reads, raw tampering and missing economic assumptions. Synthetic fixtures are labeled and establish accounting behavior. Actual model efficiency requires a separately retained native model campaign and observed telemetry.
