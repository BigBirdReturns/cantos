# Shop-eval probe

Fingerprint any rented GPU box (1-GPU VM or bare metal, AMD MI300X-class or NVIDIA
H100-class, Ubuntu) and diff it against Hot Aisle, the reference operator. Inventory
is read-only by default. Active GPU load is opt-in and bounded. Three files do the
work; everything else here supports them.

- `fingerprint.sh` -- runs ON the rented machine, writes `fingerprint.json` + `raw/`
- `diff.py` -- runs anywhere with Python 3.9+, compares two `fingerprint.json` files
- `fingerprint.schema.json` -- the shape both of the above agree on

## What it collects

Kernel, distro, virtualization (`systemd-detect-virt`, `dmidecode` if sudo allows
it), CPU model/cores/NUMA, RAM, block devices + NVMe SMART, mounted filesystems and
free space, network interfaces + MTU, container runtime, vendor-filtered GPU count/model/VBIOS where mapping is verified, driver and
ROCm-or-CUDA version, per-GPU PCIe link gen/width (read live from sysfs
`current_link_speed`/`current_link_width`, plus vendor-specific management output), GPU
topology, ECC/RAS counters, and ambient clocks/temp/power. The probe sets
`idle_verified: false` because it does not establish workload isolation. Fields with
legacy `*_idle` names are ambient samples and must not be interpreted as idle values;
unknown device-to-SMI mappings remain unknown with raw evidence retained. The default run performs no
external network request and no active load. It records network interfaces only;
throughput is not measured by this inventory probe.

Every raw command's output lands in `raw/<name>.txt`, byte-for-byte, whether it
succeeded or not. `fingerprint.json` is the parsed, structured summary of the same
run. `MANIFEST.sha256` covers `fingerprint.json` and every file under `raw/`.

## Running it on a fresh VM

```sh
scp fingerprint.sh candidate-host:~/
ssh candidate-host
bash fingerprint.sh amd ./fp-out        # inventory only; output path must not already exist
bash fingerprint.sh amd ./fp-load --gpu-load   # explicit 30 s GPU load, fresh output path
```

`auto` tries bounded `nvidia-smi`, `rocm-smi`, `amd-smi list`, then `/sys/module` checks; pass
`amd` or `nvidia` explicitly if you already know, or if both are present and you want
one side of a mixed box. No arguments defaults to `auto ./shop-fingerprint`.

**Sudo:** used, not required. `dmidecode -s system-product-name` and
`nvme smart-log` run under `sudo -n` (non-interactive -- never prompts, never
blocks) and fall back to "unavailable" if that fails or sudo isn't set up. Every
other collector runs as the normal user. Existing output paths are refused with exit
code 3; choose a new run-specific directory so evidence is never overwritten.

**What gets skipped:**
- `network.download_throughput_mb_s` is `not_measured: active network test not requested`;
  no external test payload is fetched.
- `load_sample` is `not_requested` unless `--gpu-load` is supplied. That option requires
  GNU `timeout`, host Python with a matching CUDA/HIP PyTorch build and an actual visible GPU. It runs a
  30 s tensor matmul on GPU 0, samples telemetry on a nominal 5 s cadence, records measured
  elapsed seconds for each sample (command overhead can lengthen the interval), the selected
  device/backend and iteration completion, and never falls back to CPU. Missing PyTorch,
  wrong backend, missing device, or workload failure leaves status `unknown`, retains the
  fingerprint/raw logs, and exits 4. The PyTorch import and GPU process have hard
  timeouts; vendor management samples are also bounded. Without GNU `timeout`, active
  load is refused.
- Any other missing tool (`lscpu`, `nvme`, `docker`, `rocm-smi`, `amd-smi`, `ip`, ...): its
  field(s) read `"unavailable: <tool> not found"` and its `raw/*.txt` says so too.
  The script never aborts on a missing tool -- `set -uo pipefail`, no `-e`, and
  every external command goes through a `run_raw`/`have` guard.

The inventory only writes its new output tree; it does not modify machine settings or files
outside `outdir`. For another capture, choose a fresh output path because existing paths are
refused rather than overwritten.

## Diffing

```sh
python diff.py fixtures/hotaisle-2026-09.fingerprint.json path/to/candidate/fingerprint.json
python diff.py reference.json candidate.json --json | jq .flags
```

Prints every field that differs (a plain two-column-ish table), then screening signals
that can motivate matched, workload-specific follow-up checks. They are not a provider
score or proof that a shop fails service requirements:

| Signal | Observed condition (screening only) |
| --- | --- |
| `pcie_below_gen5_x16` | any GPU's current link is below gen 5 or width 16 |
| `vm_not_bare_metal` | `virtualization` names a hypervisor (not `none`/unknown) |
| `driver_rocm_major_mismatch` | candidate's driver or ROCm/CUDA major version != reference's |
| `thermal_throttle_under_load` | a load-sample reading shows an active throttle reason |
| `ecc_errors_nonzero` | corrected or uncorrected ECC count > 0 on any GPU |
| `download_throughput_low` | download sample < 200 MB/s |
| `mtu_low` | a non-loopback interface's MTU < 1500 |
| `free_disk_low` | free space on `/` < 200 GB |

The default inventory records no network-throughput observation, so the related diff flag
remains unknown/absent; it does not treat an unmeasured path as slow. AMD collection selects
either `rocm-smi` or `amd-smi` and uses that utility's own command family. Unsupported fields
stay unavailable with raw command output retained.

Each signal prints a one-line reason to investigate it. `diff.py` exits `0` on a
normal comparison; only a bad path or unparseable JSON exits nonzero. Treat every
threshold as a triage heuristic and verify its effect under the selected workload.

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
