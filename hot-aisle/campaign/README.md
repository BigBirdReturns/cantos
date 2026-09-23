# First qualified workload · run sheet

Three arms, one model, one request set, one acceptance rule. Budget $20, ceiling $35.
Every identity the comparison engine demands is pinned in `identity.json` before anything
is rented. What this run does not cover is listed there too, and stays on the page.

| Arm | Machine | Rate | Path | Est. cost |
| --- | --- | --- | --- | --- |
| A · Hot Aisle MI300X | 1× MI300X VM, self-serve | $2.99/GPU-hr, per minute | runner, API-authenticated, ssh exec | ~$2.75 |
| B · DigitalOcean H100 | `gpu-h100x1-base` droplet | $4.41/GPU-hr, per second, 5-min min | `arm.sh` on the droplet, files imported | ~$4.05 |
| C · DigitalOcean MI300X | `gpu-amd-base` droplet | $2.59/GPU-hr, per second, 5-min min | `arm.sh` on the droplet, files imported | ~$2.40 |

Each arm is ~55 minutes wall clock: 15 to 20 minutes of pull and load, one unrecorded
warm-up, then 12 cells (concurrency 1, 8, 32, 64 × 3 repeats × 200 prompts). Stop rule:
if an arm has not passed health in 25 minutes, delete the machine and read the log. A
retry of any arm is about $4.

## What only you can do (this is when the card is needed)

1. **DigitalOcean.** Create the account, add the card, and create one GPU Droplet to see
   whether the account is allowed to (new accounts are sometimes limited; the console says
   so at create time). Add your SSH public key to the account. Arms B and C.
2. **Hot Aisle.** Reserve the ID at hotaisle.cloud, add the card, upload the same SSH
   public key, create an API token, and put it in `HOTAISLE_API_TOKEN` on the machine that
   runs the runner. Create one Small VM (1× MI300X). Arm A.
3. Tell me the two droplet IPs and the Hot Aisle VM's ssh host and user. Everything below
   is mechanical from there.

Order that spends least if something breaks: **A first** (it exercises the API adapter and
is the buyer's own machine), then B, then C. Delete each machine as soon as its files are
collected. Nothing keeps billing except the machine itself.

## Arm A · Hot Aisle, through the runner

On the VM (ssh in, copy `campaign/arm.sh` there):

```sh
bash arm.sh serve amd          # pull rocm/vllm by digest, serve the pinned model, health, env.json, warm-up
```

On your machine, from the kit root (`hot-aisle/`):

```sh
export HOTAISLE_API_TOKEN=…
node runner/bin/workload.cjs inspect                       # team, VM, state, retrieved $/GPU-hr, balance
# fill the four __VM_*__ placeholders in campaign/plan.hotaisle.json from inspect
# (or open http://localhost:8787 with `workload serve`; the connected page fills them)
node runner/bin/workload.cjs plan campaign/plan.hotaisle.json    # prints the hash and the exact first command; runs nothing
node runner/bin/workload.cjs approve job-…
node runner/bin/workload.cjs start   job-…                 # 12 cells over ssh; Ctrl-C keeps completed trials; `start` resumes
node runner/bin/workload.cjs result  job-…
node runner/bin/workload.cjs publish rec-…                 # headline.json, evidence.json, report.html
```

The plan's `price.rate` must be replaced by the figure `inspect` retrieved so the record
says "retrieved", not "snapshot". Limits are 75 minutes and $8; the runner stops before
any trial that would cross them. Then on the VM: `bash arm.sh stop`, and delete the VM in
the Hot Aisle console.

## Arms B and C · DigitalOcean, manual flags, imported as evidence

On the droplet (as root, `gpu-h100x1-base` for B, `gpu-amd-base` for C; copy `arm.sh` and the
matching `cells.<kind>.sh` next to each other):

```sh
bash arm.sh serve nvidia && bash arm.sh bench nvidia   # B: the same 12 cells, same arguments, 50-minute watchdog
bash arm.sh serve amd    && bash arm.sh bench amd      # C
bash arm.sh stop
```

On your machine:

```sh
bash campaign/collect.sh do-h100  root@<ip-B>
bash campaign/collect.sh do-mi300x root@<ip-C>
```

Then delete both droplets. `cells.amd.sh` and `cells.nvidia.sh` are generated from
`plan.hotaisle.json` by the runner's own argument builder (`node campaign/gen-cells.cjs`), so the
manual arms run byte-identical arguments to the runner-driven arm. They differ from each other
only in the declared runtime digest, and from the runner's cells only by the absent `plan_sha256`.

## Assembling the row on the page

1. **The qualified record** is arm A's, from `publish`. It carries the retrieved price, the
   approved plan hash, and the DigitalOcean H100 list price as a price-only comparator.
2. **The measured comparison** is a workbench packet: drop arm A's retained cell files
   (`$WORKLOAD_HOME/jobs/<job>/…/cell-*.json`) on the Hot Aisle side and arm B's
   `results/do-h100/cell-*.json` on the comparator side with the DigitalOcean H100 preset.
   Model, revision, precision, tokenizer, workload id, cache policy and load all match by
   construction; the engine shows the savings figure only if they do.
3. **Same silicon, two prices** is a second packet: arm A against arm C with the
   DigitalOcean MI300X preset. If the AMD arms measure alike, this packet says DigitalOcean is
   cheaper per accepted request at list. That is the honest reading and the argument for
   the correctness arm, where the buyer's service, not his list price, is what's measured.
4. **Invoices.** When the three bills post, enter each machine's real charge as the
   whole-bill override on a copy of the packet and keep both. The difference between modeled
   window cost and billed cost, per provider, is a number nobody else publishes.
5. Ship: replace the fixture record with arm A's record in `data/`, flip
   `QUALIFICATION.json` to name exactly which arms ran, add the two packets and the three
   `env.json` files under `campaign/results/`, and let CI and the gate publish it.

## Retry knobs, in the order to try them

- Health never arrives on AMD: `docker logs vllm`. If it is a kernel or attention error, add
  `-e VLLM_USE_TRITON_FLASH_ATTN=0` to the `docker run` line in `arm.sh serve` and rerun.
- Out of memory at concurrency 64: it is a real result, not a retry. The cell fails, the
  other cells stand, and the record says which cell did not meet requirements.
- `vllm bench` missing in an image: the image is not the one pinned; check the digest.
- DigitalOcean refuses a GPU Droplet: try Spheron for the H100 arm ($3.59/hr, 20-min
  minimum, self-serve) and record it as a custom comparator. Do not substitute the MI300X
  arm; the buyer's arm is arm A.
