# Shop-eval probe

Fingerprint any rented GPU box (1-GPU VM or bare metal, AMD MI300X-class or NVIDIA
H100-class, Ubuntu) and diff it against Hot Aisle, the reference operator. Three
files do the work; everything else here supports them.

- `fingerprint.sh` -- runs ON the rented machine, writes `fingerprint.json` + `raw/`
- `diff.py` -- runs anywhere with Python 3.9+, compares two `fingerprint.json` files
- `fingerprint.schema.json` -- the shape both of the above agree on

## What it collects

Kernel, distro, virtualization (`systemd-detect-virt`, `dmidecode` if sudo allows
it), CPU model/cores/NUMA, RAM, block devices + NVMe SMART, mounted filesystems and
free space, network interfaces + MTU, a 30 s download-throughput sample against
`speed.cloudflare.com`, container runtime, GPU count/model/VBIOS, driver and
ROCm-or-CUDA version, per-GPU PCIe link gen/width (read live from sysfs
`current_link_speed`/`current_link_width`, plus `rocm-smi`/`nvidia-smi`), GPU
topology, ECC/RAS counters, idle clocks/temp/power, and a 60 s sustained-load
sample (12 readings, one every 5 s) if it can find something to load the GPU with.

Every raw command's output lands in `raw/<name>.txt`, byte-for-byte, whether it
succeeded or not. `fingerprint.json` is the parsed, structured summary of the same
run. `MANIFEST.sha256` covers both, same convention as `campaign/collect.sh` and
`campaign/results/*/MANIFEST.sha256` one level up.

## Running it on a fresh VM

```sh
scp fingerprint.sh candidate-host:~/
ssh candidate-host
bash fingerprint.sh amd ./fp-out        # or: nvidia | auto
```

`auto` tries `nvidia-smi` then `rocm-smi` then a couple of `/sys/module` checks; pass
`amd` or `nvidia` explicitly if you already know, or if both are present and you want
one side of a mixed box. No arguments defaults to `auto ./shop-fingerprint`.

**Sudo:** used, not required. `dmidecode -s system-product-name` and
`nvme smart-log` run under `sudo -n` (non-interactive -- never prompts, never
blocks) and fall back to "unavailable" if that fails or sudo isn't set up. Every
other collector runs as the normal user.

**What gets skipped:**
- No network reachability (or a non-2xx from the speed-test endpoint): the download
  sample records `"unavailable: no network"` / `"unavailable: HTTP <code> ..."`
  instead of a bogus near-zero throughput number.
- No `torch` importable by `python3` on the host, and no running container named
  `vllm`: `load_sample` is the literal string `"skipped: no torch"`, no 60 s wait.
- Any other missing tool (`lscpu`, `nvme`, `docker`, `rocm-smi`, `ip`, ...): its
  field(s) read `"unavailable: <tool> not found"` and its `raw/*.txt` says so too.
  The script never aborts on a missing tool -- `set -uo pipefail`, no `-e`, and
  every external command goes through a `run_raw`/`have` guard.

Exit and rerun freely; it doesn't touch anything outside `outdir`.

## Diffing

```sh
python diff.py fixtures/hotaisle-2026-09.fingerprint.json path/to/candidate/fingerprint.json
python diff.py reference.json candidate.json --json | jq .flags
```

Prints every field that differs (a plain two-column-ish table), then a short flag
list for the differences that move serving throughput or correctness:

| Flag | Trips when |
| --- | --- |
| `pcie_below_gen5_x16` | any GPU's current link is below gen 5 or width 16 |
| `vm_not_bare_metal` | `virtualization` names a hypervisor (not `none`/unknown) |
| `driver_rocm_major_mismatch` | candidate's driver or ROCm/CUDA major version != reference's |
| `thermal_throttle_under_load` | a load-sample reading shows an active throttle reason |
| `ecc_errors_nonzero` | corrected or uncorrected ECC count > 0 on any GPU |
| `download_throughput_low` | download sample < 200 MB/s |
| `mtu_low` | a non-loopback interface's MTU < 1500 |
| `free_disk_low` | free space on `/` < 200 GB |

Each flag prints a one-line "why it matters". `diff.py` always exits `0` on a
normal run -- a shop failing every flag is the point of running it, not a tool
failure. Only a bad path or unparseable JSON exits nonzero.

## Fixtures

- `fixtures/hotaisle-2026-09.fingerprint.json` -- built ONLY from facts already on
  record in `campaign/results/hotaisle-mi300x/env.json` /
  `env.normalized.json` (host, kernel, GPU model/count, ROCm version, recorded_at).
  Every other field is the literal string `"unobserved"`, not a guess. The next
  real Hot Aisle rental runs `fingerprint.sh` on the VM and this file gets replaced
  with actual output.
- `fixtures/synthetic-bad-shop.fingerprint.json` -- hand-built, marked
  `"_synthetic": true`, not a real machine or vendor's numbers. Exists purely to
  trip all eight flags above for `test_probe.py`.

## Testing

```sh
python -B test_probe.py
bash -n fingerprint.sh
```

`test_probe.py` is stdlib `unittest`: a minimal required-field walker reads
`fingerprint.schema.json`'s own `"required"` lists and checks both fixtures against
it (no `jsonschema` dependency), runs `diff.py` as a subprocess against the two
fixtures and asserts all eight flag tags fire with non-trivial why-it-matters text,
and shells out to `bash -n fingerprint.sh`.
