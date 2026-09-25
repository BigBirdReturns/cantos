#!/usr/bin/env bash
# Fingerprint the machine a shop rented you: kernel, virtualization, CPU, RAM, storage,
# network, container runtime, GPU hardware/driver/topology, and a 60-second load sample.
# Run ON the rented machine as the normal user; sudo is used where it helps (dmidecode)
# but is never required. Every raw command's output lands in outdir/raw/<name>.txt so a
# human can check the parsing; outdir/fingerprint.json is the single structured record.
#
#   fingerprint.sh [amd|nvidia|auto] [outdir]
#
# A missing tool is recorded as "unavailable" in the JSON and its raw file; it never
# aborts the run. Nothing here provisions or deletes anything, and nothing is destructive.
set -uo pipefail

VENDOR_ARG="${1:-auto}"
OUTDIR="${2:-./shop-fingerprint}"
RAWDIR="$OUTDIR/raw"
SCRIPT_VERSION="1"

mkdir -p "$RAWDIR"

log() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; }

have() { command -v "$1" >/dev/null 2>&1; }

# JSON-escape a string for embedding inside a double-quoted JSON string.
esc() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="$(printf '%s' "$s" | tr -d '\r')"
  s="$(printf '%s' "$s" | awk 'BEGIN{ORS="\\n"} {print}')"
  # awk's ORS join leaves a trailing "\n" marker; strip it.
  s="${s%\\n}"
  printf '%s' "$s"
}

# run_raw <raw-file-basename> <cmd> [args...]
# Writes combined stdout+stderr to raw/<name>.txt and prints the same text to stdout.
# If the binary is missing or the command fails, writes/prints an "unavailable: ..." line
# instead of aborting the script.
run_raw() {
  local name="$1"; shift
  local outfile="$RAWDIR/${name}.txt"
  if [[ $# -eq 0 ]]; then
    printf 'unavailable: no command given\n' | tee "$outfile"
    return 0
  fi
  if ! have "$1"; then
    printf 'unavailable: %s not found\n' "$1" | tee "$outfile"
    return 0
  fi
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  if [[ $rc -ne 0 ]]; then
    printf '%s\n(exit %d)\n' "$out" "$rc" > "$outfile"
    printf 'unavailable: %s exited %d\n' "$1" "$rc"
    return 0
  fi
  printf '%s\n' "$out" > "$outfile"
  printf '%s' "$out"
}

# save_raw <name> <content...>  -- write pre-collected text to raw/<name>.txt verbatim.
save_raw() {
  local name="$1"; shift
  printf '%s\n' "$*" > "$RAWDIR/${name}.txt"
}

RECORDED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---------------------------------------------------------------------------
# GPU vendor
# ---------------------------------------------------------------------------
detect_vendor() {
  local req="$1"
  if [[ "$req" == "amd" || "$req" == "nvidia" ]]; then
    printf '%s' "$req"
    return
  fi
  if have nvidia-smi && nvidia-smi -L >/dev/null 2>&1; then
    printf 'nvidia'
    return
  fi
  if have rocm-smi && rocm-smi --showid >/dev/null 2>&1; then
    printf 'amd'
    return
  fi
  if [[ -d /sys/module/amdgpu ]]; then
    printf 'amd'
    return
  fi
  if [[ -d /sys/module/nvidia ]]; then
    printf 'nvidia'
    return
  fi
  printf 'unknown'
}
VENDOR="$(detect_vendor "$VENDOR_ARG")"
log "gpu vendor: $VENDOR (requested: $VENDOR_ARG)"

# ---------------------------------------------------------------------------
# System: kernel, distro, virtualization
# ---------------------------------------------------------------------------
KERNEL="$(uname -r 2>/dev/null || echo unavailable)"
HOSTNAME_VAL="$(hostname 2>/dev/null || echo unavailable)"
save_raw uname "$(uname -a 2>&1 || echo unavailable)"

DISTRO="unavailable"
if [[ -r /etc/os-release ]]; then
  DISTRO="$( (. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-unavailable}") || echo unavailable)"
  cp /etc/os-release "$RAWDIR/os-release.txt" 2>/dev/null || true
else
  save_raw os-release "unavailable: /etc/os-release not readable"
fi

VIRT="$(run_raw systemd-detect-virt systemd-detect-virt)"
CMDLINE="$(run_raw proc-cmdline cat /proc/cmdline)"
HUGEPAGES_TOTAL="$( { grep -m1 HugePages_Total /proc/meminfo 2>/dev/null | awk '{print $2}'; } || true)"
[[ -n "$HUGEPAGES_TOTAL" ]] || HUGEPAGES_TOTAL="unavailable"
save_raw proc-meminfo-hugepages "$(grep -i hugepages /proc/meminfo 2>&1 || echo unavailable)"
DMIDECODE_PRODUCT="$(run_raw dmidecode-system-product sudo -n dmidecode -s system-product-name)"

# ---------------------------------------------------------------------------
# CPU
# ---------------------------------------------------------------------------
LSCPU_RAW="$(run_raw lscpu lscpu)"
CPU_MODEL="unavailable"
CPU_CORES_LOGICAL="unavailable"
CPU_SOCKETS="unavailable"
NUMA_NODES="unavailable"
if [[ "$LSCPU_RAW" != unavailable* ]]; then
  CPU_MODEL="$(printf '%s\n' "$LSCPU_RAW" | sed -n 's/^Model name:[[:space:]]*//p' | head -1)"
  [[ -z "$CPU_MODEL" ]] && CPU_MODEL="unavailable"
  CPU_CORES_LOGICAL="$(printf '%s\n' "$LSCPU_RAW" | sed -n 's/^CPU(s):[[:space:]]*//p' | head -1)"
  [[ -z "$CPU_CORES_LOGICAL" ]] && CPU_CORES_LOGICAL="unavailable"
  CPU_SOCKETS="$(printf '%s\n' "$LSCPU_RAW" | sed -n 's/^Socket(s):[[:space:]]*//p' | head -1)"
  [[ -z "$CPU_SOCKETS" ]] && CPU_SOCKETS="unavailable"
  NUMA_NODES="$(printf '%s\n' "$LSCPU_RAW" | sed -n 's/^NUMA node(s):[[:space:]]*//p' | head -1)"
  [[ -z "$NUMA_NODES" ]] && NUMA_NODES="unavailable"
elif [[ -r /proc/cpuinfo ]]; then
  CPU_MODEL="$(sed -n 's/^model name[[:space:]]*:[[:space:]]*//p' /proc/cpuinfo | head -1)"
  [[ -z "$CPU_MODEL" ]] && CPU_MODEL="unavailable"
  CPU_CORES_LOGICAL="$(grep -c ^processor /proc/cpuinfo 2>/dev/null || echo unavailable)"
fi
CPU_JSON=$(printf '{"model":"%s","cores_logical":"%s","sockets":"%s","numa_nodes":"%s"}' \
  "$(esc "$CPU_MODEL")" "$(esc "$CPU_CORES_LOGICAL")" "$(esc "$CPU_SOCKETS")" "$(esc "$NUMA_NODES")")

# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------
FREE_RAW="$(run_raw free free -h)"
MEM_TOTAL="unavailable"
if [[ "$FREE_RAW" != unavailable* ]]; then
  MEM_TOTAL="$(printf '%s\n' "$FREE_RAW" | awk '/^Mem:/{print $2; exit}')"
  [[ -z "$MEM_TOTAL" ]] && MEM_TOTAL="unavailable"
fi
MEMORY_JSON=$(printf '{"total":"%s"}' "$(esc "$MEM_TOTAL")")

# ---------------------------------------------------------------------------
# Storage: block devices + NVMe SMART
# ---------------------------------------------------------------------------
LSBLK_RAW="$(run_raw lsblk lsblk -d -o NAME,SIZE,MODEL,ROTA,TYPE)"
NVME_SMART_JSON="[]"
if have nvme; then
  NVME_LIST_RAW="$(run_raw nvme-list sudo -n nvme list)"
  if [[ "$NVME_LIST_RAW" != unavailable* ]]; then
    smart_entries=()
    while IFS= read -r dev; do
      [[ -z "$dev" ]] && continue
      smart_name="nvme-smart-$(basename "$dev")"
      smart_out="$(run_raw "$smart_name" sudo -n nvme smart-log "$dev")"
      smart_entries+=("{\"device\":\"$(esc "$dev")\",\"smart_log\":\"$(esc "$smart_out")\"}")
    done < <(printf '%s\n' "$NVME_LIST_RAW" | awk '/^\/dev\/nvme/{print $1}')
    if [[ ${#smart_entries[@]} -gt 0 ]]; then
      NVME_SMART_JSON="[$(IFS=,; echo "${smart_entries[*]}")]"
    fi
  fi
else
  save_raw nvme-list "unavailable: nvme-cli not present"
fi
STORAGE_JSON=$(printf '{"devices":"%s","nvme_smart":%s}' "$(esc "$LSBLK_RAW")" "$NVME_SMART_JSON")

# ---------------------------------------------------------------------------
# Filesystems / free space
# ---------------------------------------------------------------------------
DF_RAW="$(run_raw df df -hT)"
FILESYSTEMS_JSON="\"$(esc "$DF_RAW")\""

# ---------------------------------------------------------------------------
# Network: interfaces, MTU, 30-second download throughput sample
# ---------------------------------------------------------------------------
IP_RAW="$(run_raw ip-link ip -o link show)"
IFACE_JSON="[]"
if [[ "$IP_RAW" != unavailable* ]]; then
  iface_entries=()
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    ifname="$(printf '%s' "$line" | awk -F': ' '{print $2}' | awk '{print $1}')"
    mtu="$(printf '%s' "$line" | grep -o 'mtu [0-9]*' | awk '{print $2}')"
    state="$(printf '%s' "$line" | grep -o 'state [A-Z]*' | awk '{print $2}')"
    [[ -z "$ifname" ]] && continue
    [[ -z "$mtu" ]] && mtu="unavailable"
    [[ -z "$state" ]] && state="unavailable"
    iface_entries+=("{\"name\":\"$(esc "$ifname")\",\"mtu\":\"$(esc "$mtu")\",\"state\":\"$(esc "$state")\"}")
  done <<< "$IP_RAW"
  if [[ ${#iface_entries[@]} -gt 0 ]]; then
    IFACE_JSON="[$(IFS=,; echo "${iface_entries[*]}")]"
  fi
fi

sample_download_throughput() {
  local outfile="$RAWDIR/network-throughput.txt"
  if ! have curl; then
    printf 'unavailable: curl not found\n' > "$outfile"
    printf 'unavailable: curl not found'
    return
  fi
  if ! curl -sSf --max-time 5 -o /dev/null 'https://speed.cloudflare.com/__down?bytes=1000' 2>>"$outfile"; then
    printf 'unavailable: no network reachability to speed.cloudflare.com\n' >> "$outfile"
    printf 'unavailable: no network'
    return
  fi
  local out speed_bytes http_code
  out="$(curl -sS --max-time 30 -o /dev/null \
    -w 'speed_download_bytes_per_s=%{speed_download}\ntime_total_s=%{time_total}\nhttp_code=%{http_code}\n' \
    'https://speed.cloudflare.com/__down?bytes=1073741824' 2>>"$outfile")"
  printf '%s\n' "$out" >> "$outfile"
  http_code="$(printf '%s\n' "$out" | sed -n 's/^http_code=//p')"
  speed_bytes="$(printf '%s\n' "$out" | sed -n 's/^speed_download_bytes_per_s=//p')"
  if [[ "$http_code" != 2* ]]; then
    printf 'unavailable: HTTP %s from speed.cloudflare.com' "${http_code:-unknown}"
    return
  fi
  if [[ -z "$speed_bytes" ]]; then
    printf 'unavailable: curl produced no throughput figure'
    return
  fi
  awk -v b="$speed_bytes" 'BEGIN{printf "%.2f", b/1000000}'
}
DOWNLOAD_MB_S="$(sample_download_throughput)"

NETWORK_JSON=$(printf '{"interfaces":%s,"download_throughput_mb_s":"%s"}' \
  "$IFACE_JSON" "$(esc "$DOWNLOAD_MB_S")")

# ---------------------------------------------------------------------------
# Container runtime
# ---------------------------------------------------------------------------
CONTAINER_RUNTIME="unavailable"
CONTAINER_VERSION="unavailable"
if have docker; then
  CONTAINER_RUNTIME="docker"
  CONTAINER_VERSION="$(run_raw docker-version docker --version)"
elif have podman; then
  CONTAINER_RUNTIME="podman"
  CONTAINER_VERSION="$(run_raw podman-version podman --version)"
else
  save_raw docker-version "unavailable: neither docker nor podman found"
fi
CONTAINER_JSON=$(printf '{"runtime":"%s","version":"%s"}' \
  "$(esc "$CONTAINER_RUNTIME")" "$(esc "$CONTAINER_VERSION")")

# ---------------------------------------------------------------------------
# GPU: count/model/vbios/firmware, driver, ROCm/CUDA version, per-device PCIe
# link (from sysfs, vendor-agnostic), topology, ECC/RAS, idle clocks/temp/power
# ---------------------------------------------------------------------------
gpu_pci_addrs() {
  local f cls
  for f in /sys/bus/pci/devices/*/class; do
    [[ -f "$f" ]] || continue
    cls="$(cat "$f" 2>/dev/null)"
    case "$cls" in
      0x030000*|0x030200*) basename "$(dirname "$f")" ;;
    esac
  done
}

pcie_link_for_addr() {
  local addr="$1" dir speed width
  dir="/sys/bus/pci/devices/$addr"
  speed="unavailable"; width="unavailable"
  [[ -r "$dir/current_link_speed" ]] && speed="$(cat "$dir/current_link_speed" 2>/dev/null || echo unavailable)"
  [[ -r "$dir/current_link_width" ]] && width="$(cat "$dir/current_link_width" 2>/dev/null || echo unavailable)"
  printf '%s|%s' "$speed" "$width"
}

GPU_COUNT="unavailable"
GPU_DRIVER_VERSION="unavailable"
GPU_STACK_VERSION="unavailable"
GPU_DEVICES_JSON="[]"

if [[ "$VENDOR" == "nvidia" ]]; then
  if have nvidia-smi; then
    NVSMI_L="$(run_raw nvidia-smi-L nvidia-smi -L)"
    if [[ "$NVSMI_L" != unavailable* ]]; then
      GPU_COUNT="$(printf '%s\n' "$NVSMI_L" | grep -c '^GPU ' || echo 0)"
    fi
    GPU_DRIVER_VERSION="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)"
    [[ -z "$GPU_DRIVER_VERSION" ]] && GPU_DRIVER_VERSION="unavailable"
    GPU_STACK_VERSION="$(nvidia-smi 2>/dev/null | grep -o 'CUDA Version: [0-9.]*' | awk '{print $3}')"
    [[ -z "$GPU_STACK_VERSION" ]] && GPU_STACK_VERSION="unavailable"
    run_raw nvidia-smi-q nvidia-smi -q >/dev/null
    QUERY="index,name,vbios_version,pcie.link.gen.current,pcie.link.width.current,ecc.errors.corrected.volatile.total,ecc.errors.uncorrected.volatile.total,clocks.sm,clocks.mem,temperature.gpu,power.draw,clocks_throttle_reasons.hw_slowdown"
    CSV_RAW="$(nvidia-smi --query-gpu="$QUERY" --format=csv,noheader,nounits 2>&1)"
    save_raw nvidia-smi-query-gpu "$CSV_RAW"
    if [[ -n "$CSV_RAW" ]]; then
      dev_entries=()
      while IFS=',' read -r idx name vbios pgen pwidth eccc eccu csm cmem temp power throttle; do
        [[ -z "${idx// /}" ]] && continue
        addr="$(gpu_pci_addrs | sed -n "$(( idx + 1 ))p")"
        [[ -z "$addr" ]] && addr="unavailable"
        dev_entries+=("{\"index\":\"$(esc "${idx// /}")\",\"model\":\"$(esc "${name# }")\",\"vbios\":\"$(esc "${vbios# }")\",\"firmware\":\"unavailable\",\"driver\":\"$(esc "$GPU_DRIVER_VERSION")\",\"pci_addr\":\"$(esc "$addr")\",\"pcie_link_gen_current\":\"$(esc "${pgen# }")\",\"pcie_link_width_current\":\"$(esc "${pwidth# }")\",\"ecc_corrected_total\":\"$(esc "${eccc# }")\",\"ecc_uncorrected_total\":\"$(esc "${eccu# }")\",\"clock_sm_mhz_idle\":\"$(esc "${csm# }")\",\"clock_mem_mhz_idle\":\"$(esc "${cmem# }")\",\"temp_c_idle\":\"$(esc "${temp# }")\",\"power_w_idle\":\"$(esc "${power# }")\",\"hw_slowdown_throttle\":\"$(esc "${throttle# }")\"}")
      done <<< "$CSV_RAW"
      if [[ ${#dev_entries[@]} -gt 0 ]]; then
        GPU_DEVICES_JSON="[$(IFS=,; echo "${dev_entries[*]}")]"
      fi
    fi
  else
    save_raw nvidia-smi-L "unavailable: nvidia-smi not found"
  fi
  TOPO_RAW="$(run_raw nvidia-smi-topo nvidia-smi topo -m)"
  ECC_RAW="$(run_raw nvidia-smi-ecc nvidia-smi --query-gpu=ecc.errors.corrected.aggregate.total,ecc.errors.uncorrected.aggregate.total --format=csv)"
  IDLE_RAW="$(run_raw nvidia-smi-idle nvidia-smi --query-gpu=index,clocks.sm,clocks.mem,temperature.gpu,power.draw --format=csv)"
elif [[ "$VENDOR" == "amd" ]]; then
  SMI_BIN=""
  if have rocm-smi; then SMI_BIN="rocm-smi"; elif have amd-smi; then SMI_BIN="amd-smi"; fi
  if [[ -n "$SMI_BIN" ]]; then
    SHOWID_RAW="$(run_raw "$SMI_BIN-showid" "$SMI_BIN" --showid)"
    if [[ "$SHOWID_RAW" != unavailable* ]]; then
      GPU_COUNT="$(printf '%s\n' "$SHOWID_RAW" | grep -c '^GPU\[' || echo 0)"
    fi
    PRODUCT_RAW="$(run_raw "$SMI_BIN-showproductname" "$SMI_BIN" --showproductname)"
    VBIOS_RAW="$(run_raw "$SMI_BIN-showvbios" "$SMI_BIN" --showvbios)"
    DRIVER_RAW="$(run_raw "$SMI_BIN-showdriverversion" "$SMI_BIN" --showdriverversion)"
    BUS_RAW="$(run_raw "$SMI_BIN-showbus" "$SMI_BIN" --showbus)"
    GPU_DRIVER_VERSION="$(printf '%s\n' "$DRIVER_RAW" | grep -m1 -oE '[0-9]+\.[0-9.]+' || echo unavailable)"
    [[ -z "$GPU_DRIVER_VERSION" ]] && GPU_DRIVER_VERSION="unavailable"
    if [[ -r /opt/rocm/.info/version ]]; then
      GPU_STACK_VERSION="$(cat /opt/rocm/.info/version 2>/dev/null || echo unavailable)"
    else
      GPU_STACK_VERSION="unavailable"
    fi
    save_raw rocm-version "${GPU_STACK_VERSION}"
    # Best-effort per-GPU device list: sysfs PCIe link is authoritative and vendor-agnostic;
    # product name / vbios come from the *-smi text dumps above (see raw/ for the full text,
    # since parsing per-index fields out of them varies by rocm-smi version).
    idx=0
    dev_entries=()
    while IFS= read -r addr; do
      [[ -z "$addr" ]] && continue
      link="$(pcie_link_for_addr "$addr")"
      speed="${link%%|*}"; width="${link##*|}"
      model_line="$(printf '%s\n' "$PRODUCT_RAW" | grep -m1 -i 'card series\|product name' | sed 's/.*:[[:space:]]*//')"
      [[ -z "$model_line" ]] && model_line="unavailable"
      dev_entries+=("{\"index\":\"$idx\",\"model\":\"$(esc "$model_line")\",\"vbios\":\"$(esc "$VBIOS_RAW")\",\"firmware\":\"unavailable\",\"driver\":\"$(esc "$GPU_DRIVER_VERSION")\",\"pci_addr\":\"$(esc "$addr")\",\"pcie_link_gen_current\":\"$(esc "$speed")\",\"pcie_link_width_current\":\"$(esc "$width")\",\"ecc_corrected_total\":\"unavailable\",\"ecc_uncorrected_total\":\"unavailable\",\"clock_sm_mhz_idle\":\"unavailable\",\"clock_mem_mhz_idle\":\"unavailable\",\"temp_c_idle\":\"unavailable\",\"power_w_idle\":\"unavailable\",\"hw_slowdown_throttle\":\"unavailable\"}")
      idx=$((idx + 1))
    done < <(gpu_pci_addrs)
    if [[ ${#dev_entries[@]} -gt 0 ]]; then
      GPU_DEVICES_JSON="[$(IFS=,; echo "${dev_entries[*]}")]"
    fi
  else
    save_raw rocm-smi-showid "unavailable: neither rocm-smi nor amd-smi found"
  fi
  TOPO_RAW="$(run_raw rocm-smi-showtopo "${SMI_BIN:-rocm-smi}" --showtopo)"
  ECC_RAW="$(run_raw rocm-smi-showrasinfo "${SMI_BIN:-rocm-smi}" --showrasinfo all)"
  IDLE_RAW="$(run_raw rocm-smi-idle "${SMI_BIN:-rocm-smi}" --showclocks --showtemp --showpower)"
else
  save_raw gpu-vendor "unavailable: no AMD or NVIDIA GPU detected"
  TOPO_RAW="unavailable: no GPU vendor detected"
  ECC_RAW="unavailable: no GPU vendor detected"
  IDLE_RAW="unavailable: no GPU vendor detected"
fi

GPU_JSON=$(printf '{"vendor":"%s","count":"%s","driver_version":"%s","rocm_or_cuda_version":"%s","devices":%s}' \
  "$(esc "$VENDOR")" "$(esc "$GPU_COUNT")" "$(esc "$GPU_DRIVER_VERSION")" "$(esc "$GPU_STACK_VERSION")" "$GPU_DEVICES_JSON")

# ---------------------------------------------------------------------------
# Sustained load sample (60 s), sampled every 5 s
# ---------------------------------------------------------------------------
run_load_sample() {
  local torch_ok=0 vllm_running=0
  if have python3 && python3 -c "import torch" >/dev/null 2>&1; then
    torch_ok=1
  fi
  if have docker && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx vllm; then
    vllm_running=1
  fi
  if [[ $torch_ok -eq 0 && $vllm_running -eq 0 ]]; then
    printf '"skipped: no torch"'
    return
  fi

  local matmul_py="$RAWDIR/load-sample-matmul.py"
  cat > "$matmul_py" <<'PYEOF'
import time
import torch
dev = "cuda" if torch.cuda.is_available() else "cpu"
a = torch.randn(4096, 4096, device=dev)
b = torch.randn(4096, 4096, device=dev)
t0 = time.time()
while time.time() - t0 < 60:
    c = a @ b
    if dev == "cuda":
        torch.cuda.synchronize()
PYEOF

  local matmul_pid="" method
  if [[ $torch_ok -eq 1 ]]; then
    python3 "$matmul_py" > "$RAWDIR/load-sample-matmul.log" 2>&1 &
    matmul_pid=$!
    method="local_torch"
  else
    docker cp "$matmul_py" vllm:/tmp/load-sample-matmul.py >/dev/null 2>&1
    docker exec vllm python3 /tmp/load-sample-matmul.py > "$RAWDIR/load-sample-matmul.log" 2>&1 &
    matmul_pid=$!
    method="vllm_container"
  fi

  local samples_file="$RAWDIR/load-sample-samples.txt"
  : > "$samples_file"
  local sample_entries=() i ts smi_out joined
  for i in 0 5 10 15 20 25 30 35 40 45 50 55; do
    sleep 5
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    if [[ "$VENDOR" == "amd" ]]; then
      smi_out="$( { "${SMI_BIN:-rocm-smi}" --showclocks --showtemp --showpower; } 2>&1 || echo unavailable)"
    elif [[ "$VENDOR" == "nvidia" ]]; then
      smi_out="$( { nvidia-smi --query-gpu=clocks.sm,clocks.mem,temperature.gpu,power.draw,clocks_throttle_reasons.hw_slowdown --format=csv,noheader; } 2>&1 || echo unavailable)"
    else
      smi_out="unavailable: no GPU vendor detected"
    fi
    printf '=== t+%ss (%s) ===\n%s\n' "$i" "$ts" "$smi_out" >> "$samples_file"
    sample_entries+=("{\"t_offset_s\":$i,\"recorded_at\":\"$(esc "$ts")\",\"sample\":\"$(esc "$smi_out")\"}")
  done
  wait "$matmul_pid" 2>/dev/null || true

  joined="[]"
  if [[ ${#sample_entries[@]} -gt 0 ]]; then
    joined="[$(IFS=,; echo "${sample_entries[*]}")]"
  fi
  printf '{"method":"%s","duration_s":60,"interval_s":5,"samples":%s}' "$method" "$joined"
}
LOAD_SAMPLE_JSON="$(run_load_sample)"

# ---------------------------------------------------------------------------
# Assemble fingerprint.json
# ---------------------------------------------------------------------------
cat > "$OUTDIR/fingerprint.json" <<EOF
{
  "schema": "second-run/shop-fingerprint@1",
  "schema_version": "$SCRIPT_VERSION",
  "recorded_at": "$RECORDED_AT",
  "hostname": "$(esc "$HOSTNAME_VAL")",
  "requested_gpu_vendor": "$(esc "$VENDOR_ARG")",
  "kernel": "$(esc "$KERNEL")",
  "distro": "$(esc "$DISTRO")",
  "virtualization": "$(esc "$VIRT")",
  "kernel_cmdline": "$(esc "$CMDLINE")",
  "hugepages_total": "$(esc "$HUGEPAGES_TOTAL")",
  "dmidecode_system_product": "$(esc "$DMIDECODE_PRODUCT")",
  "cpu": $CPU_JSON,
  "memory": $MEMORY_JSON,
  "storage": $STORAGE_JSON,
  "filesystems": $FILESYSTEMS_JSON,
  "network": $NETWORK_JSON,
  "container_runtime": $CONTAINER_JSON,
  "gpu": $GPU_JSON,
  "gpu_topology": "$(esc "$TOPO_RAW")",
  "ecc": "$(esc "$ECC_RAW")",
  "idle_power_state": "$(esc "$IDLE_RAW")",
  "load_sample": $LOAD_SAMPLE_JSON,
  "raw_dir": "raw/"
}
EOF

log "fingerprint.json written to $OUTDIR/fingerprint.json"

# ---------------------------------------------------------------------------
# MANIFEST.sha256 over fingerprint.json and every raw file
# ---------------------------------------------------------------------------
if have sha256sum; then
  (
    cd "$OUTDIR" || exit 0
    sha256sum fingerprint.json raw/*.txt 2>/dev/null > MANIFEST.sha256
  )
  log "MANIFEST.sha256 written to $OUTDIR/MANIFEST.sha256"
else
  log "sha256sum not found; MANIFEST.sha256 skipped"
fi

log "done: $OUTDIR"
