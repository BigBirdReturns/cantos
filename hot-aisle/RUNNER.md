# Runner · connected qualification

The runner is the process behind the page's connected mode. It reads your Hot Aisle
account through the public API, freezes an evaluation plan you approve by hash,
drives `vllm bench serve` on the allocation, retains every trial's exact bytes,
writes a **qualified record**, and answers *what changed, what still stands, what is
the smallest check* when a price, a traffic profile or a runtime moves.

Three interfaces, one core, one engine (the `report-engine` script in `index.html`):

| Interface | Start | Use |
| --- | --- | --- |
| CLI | `node runner/bin/workload.cjs …` | scripts, CI, a VM shell |
| Localhost service | `node runner/bin/workload.cjs serve` | the page at `http://127.0.0.1:8787/` |
| MCP server | `node runner/bin/workload.cjs mcp` | Claude Code, Claude Desktop, any MCP host |

Node ≥ 20. No dependencies. State lives in `$WORKLOAD_HOME` (default `~/.workload-report`).

## Ten-minute path

```sh
# 1. token: HOTAISLE_API_TOKEN, or the official CLI's ~/.hotaisle/config.json
node runner/bin/workload.cjs inspect                 # teams, VMs, state, retrieved prices, balance

# 2. a plan runs nothing; it prints the hash you approve and the exact first command
node runner/bin/workload.cjs plan plan.json
node runner/bin/workload.cjs approve job-…           # binds approval to that hash
node runner/bin/workload.cjs start   job-…           # runs; survives Ctrl-C (resume with start)

# 3. result, receipts, what-if
node runner/bin/workload.cjs result  job-…
node runner/bin/workload.cjs revalidate rec-… --price 3.39
node runner/bin/workload.cjs revalidate rec-… --concurrency 1,8,32,64
node runner/bin/workload.cjs revalidate rec-… --runtime runtime_digest=rocm/vllm@sha256:next
node runner/bin/workload.cjs publish rec-…           # headline.json + evidence.json + report.html
```

No token, no GPU? `node runner/bin/workload.cjs demo --fast` runs the whole journey in the
local integration environment (fake API, fake benchmark). Everything it produces is
marked synthetic and can never be published as measured.

## Plan file

```json
{
  "target": { "adapter": "hotaisle", "exec": "ssh", "host": "vm.example", "ssh_user": "hotaisle",
              "name": "mi300x-dev-01", "deployment_id": "dep-…", "gpus": 1, "gpu_model": "AMD MI300X", "allocation_label": "1× MI300X VM" },
  "workload": { "model": "Qwen/Qwen3-Coder-30B-A3B-Instruct", "base_url": "http://127.0.0.1:8000",
                "dataset": "random", "input_len": 2048, "output_len": 256, "num_prompts": 200, "request_rate": "inf", "seed": 7 },
  "concurrency": [1, 8, 32], "repeats": 3,
  "identity": { "model_revision": "…", "precision": "FP8", "tokenizer_revision": "…", "cache_policy": "warm", "runtime_digest": "rocm/vllm@sha256:…" },
  "price": { "provider": "Hot Aisle", "gpus": 1, "rate": 2.99, "extra": 0, "source": "retrieved from API", "period": "retrieved" },
  "comparator": { "provider": "Nebius HGX H100", "gpus": 1, "rate": 3.85, "extra": 0, "source": "https://nebius.com/prices", "period": "2026-09-22 snapshot" },
  "limits": { "max_minutes": 90, "max_spend_usd": 25 },
  "gates": { "ttft": null, "e2e": null, "queue": false, "quality": false },
  "requirements": { "max_p95_ttft_ms": 1000, "max_p95_e2e_ms": 15000, "min_accepted_per_s": null, "max_failure_rate": 0.01 }
}
```

`exec: "ssh"` needs key-based SSH to the VM (BatchMode; no prompts) and a vLLM server
already listening at `base_url` on that VM. `exec: "local"` is for a runner living on the
VM itself. The runner never provisions, deletes, reboots or powers anything; it only
starts the benchmark for a plan whose hash you approved, within your limits.

## What a job guarantees

- **Approval binds the plan.** The hash covers target, workload, identity, prices,
  limits, gates and requirements. A changed plan is a new job.
- **Trials are the unit of retention.** Cancel, a limit, or a crash keeps every
  completed trial. A reconnecting client, a new process or another interface finds the
  same job; `start` on an interrupted job reruns only what never completed.
- **Evidence is admitted, not repaired.** Exact bytes are hashed and retained. Anything
  the engine refuses is a failed trial. A synthetic marker in a real run fails the trial.
- **Limits bound the run.** Time and modeled spend are checked before every trial.

## The qualified record

`observed` (retained trials, their source hashes), `declared` (identity, prices,
approval), `rule` (gates, requirements), `scenario` (allocation) and `derived`
(per-cell aggregate, cost, requirement check; primary cell; disposition). The record
carries a SHA-256 over everything but itself; `workload verify` and the page both
recompute `derived` from `observed + declared + rule` and refuse a record whose
conclusions do not follow from its evidence.

Every visible number is a projection of the record: the page's card, the customer
report, the evidence packet (`hot-aisle/sealed-report@1`, recomputable with
`scripts/recompute.cjs`), the MCP result and the CLI summary. `publish` writes them side
by side; it never edits the record.

## Revalidation

| Change | Economics | Performance / capacity | Qualification |
| --- | --- | --- | --- |
| price | recomputed, no GPU time | stands | re-applied |
| gates (with retained request samples) | recomputed | recomputed | re-applied |
| requirements | — | — | re-applied |
| traffic: new concurrency | — | stands for measured cells; new cells require measurement | — |
| traffic: request shape | — | all cells require measurement (new workload identity) | — |
| runtime / model identity | applied to the candidate | superseded; candidate plan for all cells | superseded |
| evaluator | — | — | re-adjudicate retained requests if acceptance was evaluator-gated |

The answer always includes the minimal plan (only the cells without valid evidence) and
keeps the prior record as history.

## MCP

```sh
claude mcp add hot-aisle-workload -- node /path/to/hot-aisle/runner/bin/workload.cjs mcp
```

Tools: `inspect_environment`, `prepare_evaluation`, `start_evaluation` (needs the plan
hash from prepare as its approval token), `evaluation_status`, `cancel_evaluation`,
`evaluation_result`, `list_records`, `revalidate`. Status and result tools carry an
MCP Apps UI resource (`ui://hot-aisle/evaluation`, `text/html;profile=mcp-app`).

## Security model

- Token from `HOTAISLE_API_TOKEN` or `~/.hotaisle/config.json`; never written by the runner.
- The service binds 127.0.0.1. State-changing calls need `X-Workload-Client: page` and a
  loopback or known page origin. The runner's own source is not served.
- API use is read-only. Benchmarks run over your SSH key, as your user, under a
  HUP/TERM trap so a dropped session kills the benchmark rather than leaving it billing.

## Not built

Provisioning VMs, installing vLLM, downloading models, comparator runs on other clouds
(import their result files instead), and any independent attestation of who produced a
result. The local environment proves the pipeline, not the hardware.
