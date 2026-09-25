#!/usr/bin/env bash
# Fingerprint the machine a shop rented you: kernel, virtualization, CPU, RAM, storage,
# network inventory, container runtime, and GPU hardware/driver/topology. Inventory is
# read-only by default; a bounded GPU-only load sample requires the explicit --gpu-load flag.
# Run ON the rented machine as the normal user; sudo is used where it helps (dmidecode)
# but is never required. Every raw command's output lands in outdir/raw/<name>.txt so a
# human can check the parsing; outdir/fingerprint.json is the single structured record.
#
#   fingerprint.sh [amd|nvidia|auto] [outdir] [--gpu-load]
#
# A missing tool is recorded as "unavailable" in the JSON and its raw file. A requested,
# unverified GPU load remains unknown and exits nonzero after preserving the fingerprint.
# Existing output paths are refused; nothing provisions or deletes anything.
set -uo pipefail

VENDOR_ARG="auto"
OUTDIR="./shop-fingerprint"
GPU_LOAD_REQUESTED=0
POSITIONAL=()
for arg in "$@"; do
  case "$arg" in
    --gpu-load) GPU_LOAD_REQUESTED=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      printf '\nUsage: %s [amd|nvidia|auto] [outdir] [--gpu-load]\n' "$0"
      exit 0
      ;;
    --*) printf 'unknown option: %s\n' "$arg" >&2; exit 2 ;;
    *) POSITIONAL+=("$arg") ;;
  esac
done
if ((${#POSITIONAL[@]} > 2)); then
  printf 'usage: %s [amd|nvidia|auto] [outdir] [--gpu-load]\n' "$0" >&2
  exit 2
fi
if ((${#POSITIONAL[@]} >= 1)); then VENDOR_ARG="${POSITIONAL[0]}"; fi
if ((${#POSITIONAL[@]} >= 2)); then OUTDIR="${POSITIONAL[1]}"; fi
case "$VENDOR_ARG" in amd|nvidia|auto) ;; *) printf 'invalid GPU vendor: %s\n' "$VENDOR_ARG" >&2; exit 2 ;; esac
OUT_PARENT="$(dirname "$OUTDIR")"
mkdir -p "$OUT_PARENT"
if ! mkdir "$OUTDIR" 2>/dev/null; then
  printf 'refusing to overwrite existing output path: %s\n' "$OUTDIR" >&2
  exit 3
fi
RAWDIR="$OUTDIR/raw"
SCRIPT_VERSION="3"

mkdir "$RAWDIR"

log() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; }

have() { command -v "$1" >/dev/null 2>&1; }

# JSON-escape a string for embedding inside a double-quoted JSON string.
esc() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\t'/\\t}"
  # Device tools sometimes emit ANSI controls and other non-JSON control bytes.
  # Raw command output remains byte-for-byte in raw/; sanitize only this summary copy.
  s="$(printf '%s' "$s" | tr -d '\r\000-\010\013\014\016-\037\177')"
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

# GPU management utilities can hang when the driver/provider stack is unhealthy.
# Give each one a short ceiling; preserve timeout/error output rather than blocking
# the inventory indefinitely.
run_bounded_raw() {
  local name="$1" seconds="$2"; shift 2
  if ! have timeout; then
    printf 'unavailable: GNU timeout is required to bound GPU telemetry\n' | tee "$RAWDIR/${name}.txt"
    return 0
  fi
  run_raw "$name" timeout --signal=TERM --kill-after=2s "${seconds}s" "$@"
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
  if have timeout && have nvidia-smi && timeout --signal=TERM --kill-after=1s 5s nvidia-smi -L >/dev/null 2>&1; then
    printf 'nvidia'
    return
  fi
  if have timeout && have rocm-smi && timeout --signal=TERM --kill-after=1s 5s rocm-smi --showid >/dev/null 2>&1; then
    printf 'amd'
    return
  fi
  if have timeout && have amd-smi && timeout --signal=TERM --kill-after=1s 5s amd-smi list >/dev/null 2>&1; then
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
# Network: inventory only. Active network tests require a separate, explicit campaign.
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

DOWNLOAD_MB_S="not_measured: active network test not requested"
save_raw network-throughput "$DOWNLOAD_MB_S"
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
# link (from vendor-filtered sysfs), topology, ECC/RAS and ambient clocks/temp/power
# ---------------------------------------------------------------------------
gpu_pci_addrs() {
  local f cls vendor expected root
  root="${SHOP_PROBE_PCI_SYSFS_ROOT:-/sys/bus/pci/devices}"
  case "$VENDOR" in
    amd) expected="0x1002" ;;
    nvidia) expected="0x10de" ;;
    *) return 0 ;;
  esac
  for f in "$root"/*/class; do
    [[ -f "$f" ]] || continue
    cls="$(cat "$f" 2>/dev/null)"
    case "$cls" in 0x030000*|0x030200*) ;; *) continue ;; esac
    vendor="$(cat "$(dirname "$f")/vendor" 2>/dev/null || true)"
    [[ "$vendor" == "$expected" ]] && basename "$(dirname "$f")"
  done
}

nvidia_bdf_to_sysfs() {
  local bdf="$1"
  if [[ "$bdf" =~ ^0000([[:xdigit:]]{4}):([[:xdigit:]]{2}):([[:xdigit:]]{2}\.[[:xdigit:]])$ ]]; then
    printf '%s:%s:%s' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}"
  elif [[ "$bdf" =~ ^([[:xdigit:]]{4}):([[:xdigit:]]{2}):([[:xdigit:]]{2}\.[[:xdigit:]])$ ]]; then
    printf '%s:%s:%s' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}"
  else
    return 1
  fi
}

pcie_link_for_addr() {
  local addr="$1" dir speed width
  dir="${SHOP_PROBE_PCI_SYSFS_ROOT:-/sys/bus/pci/devices}/$addr"
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
    NVSMI_L="$(run_bounded_raw nvidia-smi-L 5 nvidia-smi -L)"
    if [[ "$NVSMI_L" != unavailable* ]]; then
      matched_count="$(gpu_pci_addrs | wc -l | tr -d ' ')"
      if [[ "$matched_count" == 0 ]] && grep -q '^GPU ' <<< "$NVSMI_L"; then
        GPU_COUNT="unavailable: nvidia-smi devices had no NVIDIA sysfs match"
      else
        GPU_COUNT="$matched_count"
      fi
    fi
    GPU_DRIVER_VERSION="$(run_bounded_raw nvidia-smi-driver 5 nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)"
    [[ -z "$GPU_DRIVER_VERSION" ]] && GPU_DRIVER_VERSION="unavailable"
    GPU_STACK_VERSION="$(run_bounded_raw nvidia-smi-banner 5 nvidia-smi | grep -o 'CUDA Version: [0-9.]*' | awk '{print $3}')"
    [[ -z "$GPU_STACK_VERSION" ]] && GPU_STACK_VERSION="unavailable"
    if have timeout; then
      timeout --signal=TERM --kill-after=2s 5s nvidia-smi -q > "$RAWDIR/nvidia-smi-q.txt" 2>&1 || true
    else
      save_raw nvidia-smi-q "unavailable: GNU timeout is required to bound vendor telemetry"
    fi
    QUERY="index,pci.bus_id,name,vbios_version,pcie.link.gen.current,pcie.link.width.current,ecc.errors.corrected.volatile.total,ecc.errors.uncorrected.volatile.total,clocks.sm,clocks.mem,temperature.gpu,power.draw,clocks_throttle_reasons.hw_slowdown"
    CSV_RAW="$(run_bounded_raw nvidia-smi-query-gpu 10 nvidia-smi --query-gpu="$QUERY" --format=csv,noheader,nounits)"
    if [[ -n "$CSV_RAW" ]]; then
      dev_entries=()
      while IFS=',' read -r idx bus_id name vbios pgen pwidth eccc eccu csm cmem temp power throttle; do
        [[ -z "${idx// /}" ]] && continue
        bus_id="${bus_id// /}"
        if addr="$(nvidia_bdf_to_sysfs "$bus_id")" && [[ -r "${SHOP_PROBE_PCI_SYSFS_ROOT:-/sys/bus/pci/devices}/$addr/vendor" ]] && [[ "$(cat "${SHOP_PROBE_PCI_SYSFS_ROOT:-/sys/bus/pci/devices}/$addr/vendor" 2>/dev/null)" == 0x10de ]]; then
          :
        else
          addr="unavailable: no NVIDIA sysfs match for $bus_id"
        fi
        dev_entries+=("{\"index\":\"$(esc "${idx// /}")\",\"model\":\"$(esc "${name# }")\",\"vbios\":\"$(esc "${vbios# }")\",\"firmware\":\"unavailable\",\"driver\":\"$(esc "$GPU_DRIVER_VERSION")\",\"pci_addr\":\"$(esc "$addr")\",\"pcie_link_gen_current\":\"$(esc "${pgen# }")\",\"pcie_link_width_current\":\"$(esc "${pwidth# }")\",\"ecc_corrected_total\":\"$(esc "${eccc# }")\",\"ecc_uncorrected_total\":\"$(esc "${eccu# }")\",\"clock_sm_mhz_idle\":\"$(esc "${csm# }")\",\"clock_mem_mhz_idle\":\"$(esc "${cmem# }")\",\"temp_c_idle\":\"$(esc "${temp# }")\",\"power_w_idle\":\"$(esc "${power# }")\",\"hw_slowdown_throttle\":\"$(esc "${throttle# }")\"}")
      done <<< "$CSV_RAW"
      if [[ ${#dev_entries[@]} -gt 0 ]]; then
        GPU_DEVICES_JSON="[$(IFS=,; echo "${dev_entries[*]}")]"
      fi
    fi
  else
    save_raw nvidia-smi-L "unavailable: nvidia-smi not found"
  fi
  TOPO_RAW="$(run_bounded_raw nvidia-smi-topo 10 nvidia-smi topo -m)"
  ECC_RAW="$(run_bounded_raw nvidia-smi-ecc 10 nvidia-smi --query-gpu=ecc.errors.corrected.aggregate.total,ecc.errors.uncorrected.aggregate.total --format=csv)"
  IDLE_RAW="ambient observation; workload isolation not verified. $(run_bounded_raw nvidia-smi-ambient 10 nvidia-smi --query-gpu=index,clocks.sm,clocks.mem,temperature.gpu,power.draw --format=csv)"
elif [[ "$VENDOR" == "amd" ]]; then
  if have timeout && have rocm-smi && timeout --signal=TERM --kill-after=1s 5s rocm-smi --showid >/dev/null 2>&1; then
    AMD_TOOL="rocm-smi"
    SHOWID_RAW="$(run_bounded_raw rocm-smi-showid 10 rocm-smi --showid)"
    PRODUCT_RAW="$(run_bounded_raw rocm-smi-showproductname 10 rocm-smi --showproductname)"
    VBIOS_RAW="$(run_bounded_raw rocm-smi-showvbios 10 rocm-smi --showvbios)"
    DRIVER_RAW="$(run_bounded_raw rocm-smi-showdriverversion 10 rocm-smi --showdriverversion)"
    TOPO_RAW="$(run_bounded_raw rocm-smi-showtopo 10 rocm-smi --showtopo)"
    ECC_RAW="$(run_bounded_raw rocm-smi-showrasinfo 10 rocm-smi --showrasinfo all)"
    IDLE_RAW="ambient observation; workload isolation not verified. $(run_bounded_raw rocm-smi-idle 10 rocm-smi --showclocks --showtemp --showpower)"
    GPU_COUNT="$(gpu_pci_addrs | wc -l | tr -d ' ')"
    GPU_DRIVER_VERSION="$(printf '%s\n' "$DRIVER_RAW" | grep -m1 -oE '[0-9]+\.[0-9.]+' || echo unavailable)"
    model_source="$PRODUCT_RAW"
    vbios_source="$VBIOS_RAW"
    amd_model_ref="raw/rocm-smi-showproductname.txt"
    amd_vbios_ref="raw/rocm-smi-showvbios.txt"
  elif have timeout && have amd-smi && timeout --signal=TERM --kill-after=1s 5s amd-smi list >/dev/null 2>&1; then
    AMD_TOOL="amd-smi"
    SHOWID_RAW="$(run_bounded_raw amd-smi-list 10 amd-smi list)"
    PRODUCT_RAW="$(run_bounded_raw amd-smi-static 10 amd-smi static)"
    DRIVER_RAW="$(run_bounded_raw amd-smi-version 10 amd-smi version)"
    TOPO_RAW="$(run_bounded_raw amd-smi-topology 10 amd-smi topology)"
    ECC_RAW="$(run_bounded_raw amd-smi-bad-pages 10 amd-smi bad-pages)"
    IDLE_RAW="ambient observation; workload isolation not verified. $(run_bounded_raw amd-smi-metric-idle 10 amd-smi metric)"
    GPU_COUNT="$(printf '%s\n' "$(gpu_pci_addrs | wc -l)" | tr -d ' ')"
    GPU_DRIVER_VERSION="unavailable: see raw/amd-smi-version.txt"
    model_source="$PRODUCT_RAW"
    vbios_source="unavailable: amd-smi static output retained in raw/amd-smi-static.txt"
    amd_model_ref="raw/amd-smi-static.txt"
    amd_vbios_ref="raw/amd-smi-static.txt"
  else
    AMD_TOOL="unavailable"
    SHOWID_RAW="unavailable: neither supported AMD SMI command succeeded"
    save_raw amd-smi-list "$SHOWID_RAW"
    PRODUCT_RAW="$SHOWID_RAW"; model_source="$SHOWID_RAW"; vbios_source="$SHOWID_RAW"
    amd_model_ref="raw/amd-smi-list.txt"
    amd_vbios_ref="raw/amd-smi-list.txt"
    TOPO_RAW="$SHOWID_RAW"; ECC_RAW="$SHOWID_RAW"; IDLE_RAW="$SHOWID_RAW"
  fi
  save_raw amd-smi-selected "$AMD_TOOL"
  if [[ "$SHOWID_RAW" == unavailable* ]]; then GPU_COUNT="unavailable"; fi
  if [[ -r /opt/rocm/.info/version ]]; then
    GPU_STACK_VERSION="$(cat /opt/rocm/.info/version 2>/dev/null || echo unavailable)"
  else
    GPU_STACK_VERSION="unavailable"
  fi
  save_raw rocm-version "$GPU_STACK_VERSION"
  idx=0
  dev_entries=()
  while IFS= read -r addr; do
    [[ -z "$addr" ]] && continue
    link="$(pcie_link_for_addr "$addr")"
    speed="${link%%|*}"; width="${link##*|}"
    # SMI output formats vary; do not copy one device's first value onto every BDF.
    model_line="unavailable: per-device mapping not established; see $amd_model_ref"
    vbios_line="unavailable: per-device mapping not established; see $amd_vbios_ref"
    dev_entries+=("{\"index\":\"$idx\",\"model\":\"$(esc "$model_line")\",\"vbios\":\"$(esc "$vbios_line")\",\"firmware\":\"unavailable\",\"driver\":\"$(esc "$GPU_DRIVER_VERSION")\",\"pci_addr\":\"$(esc "$addr")\",\"pcie_link_gen_current\":\"$(esc "$speed")\",\"pcie_link_width_current\":\"$(esc "$width")\",\"ecc_corrected_total\":\"unavailable: see raw AMD SMI output\",\"ecc_uncorrected_total\":\"unavailable: see raw AMD SMI output\",\"clock_sm_mhz_idle\":\"unavailable: ambient telemetry retained in raw AMD SMI files\",\"clock_mem_mhz_idle\":\"unavailable: ambient telemetry retained in raw AMD SMI files\",\"temp_c_idle\":\"unavailable: ambient telemetry retained in raw AMD SMI files\",\"power_w_idle\":\"unavailable: ambient telemetry retained in raw AMD SMI files\",\"hw_slowdown_throttle\":\"unavailable: see raw AMD SMI output\"}")
    idx=$((idx + 1))
  done < <(gpu_pci_addrs)
  if [[ ${#dev_entries[@]} -gt 0 ]]; then GPU_DEVICES_JSON="[$(IFS=,; echo "${dev_entries[*]}")]"; fi
else
  save_raw gpu-vendor "unavailable: no AMD or NVIDIA GPU detected"
  TOPO_RAW="unavailable: no GPU vendor detected"
  ECC_RAW="unavailable: no GPU vendor detected"
  IDLE_RAW="unavailable: no GPU vendor detected"
fi

GPU_JSON=$(printf '{"vendor":"%s","count":"%s","driver_version":"%s","rocm_or_cuda_version":"%s","devices":%s}' \
  "$(esc "$VENDOR")" "$(esc "$GPU_COUNT")" "$(esc "$GPU_DRIVER_VERSION")" "$(esc "$GPU_STACK_VERSION")" "$GPU_DEVICES_JSON")

# ---------------------------------------------------------------------------
# Optional bounded GPU load sample (30 s), sampled every 5 s. GNU timeout is
# mandatory; telemetry commands and the PyTorch process each have hard bounds.
# ---------------------------------------------------------------------------
run_load_sample() {
  if [[ $GPU_LOAD_REQUESTED -eq 0 ]]; then
    printf '"not_requested"'
    return 0
  fi
  local duration=30 matmul_py="$RAWDIR/gpu-load.py" load_log="$RAWDIR/gpu-load.log"
  if [[ "$VENDOR" != amd && "$VENDOR" != nvidia ]]; then
    save_raw gpu-load "unknown: GPU vendor not detected; explicit GPU workload not run"
    printf '{"status":"unknown","reason":"GPU vendor not detected","method":"torch_gpu_matmul","duration_s":%d,"nominal_interval_s":5,"samples":[]}' "$duration"
    LOAD_FAILURE=1
    return 0
  fi
  if ! have timeout; then
    save_raw gpu-load "unknown: GNU timeout unavailable; bounded GPU load refused"
    printf '{"status":"unknown","reason":"GNU timeout unavailable; bounded GPU load refused","method":"torch_gpu_matmul","duration_s":%d,"nominal_interval_s":5,"samples":[]}' "$duration"
    LOAD_FAILURE=1
    return 0
  fi
  if ! have python3 || ! timeout --signal=TERM --kill-after=2s 10s python3 -c 'import torch' >/dev/null 2>&1; then
    save_raw gpu-load "unknown: host Python PyTorch unavailable; no CPU fallback"
    printf '{"status":"unknown","reason":"host Python PyTorch unavailable; no CPU fallback","method":"torch_gpu_matmul","duration_s":%d,"nominal_interval_s":5,"samples":[]}' "$duration"
    LOAD_FAILURE=1
    return 0
  fi
  cat > "$matmul_py" <<'PYEOF'
import sys, time
import torch
vendor, duration = sys.argv[1], int(sys.argv[2])
if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
    raise SystemExit("no CUDA/HIP GPU device visible to PyTorch")
if vendor == "amd" and not torch.version.hip:
    raise SystemExit("AMD requested but PyTorch is not a HIP build")
if vendor == "nvidia" and not torch.version.cuda:
    raise SystemExit("NVIDIA requested but PyTorch is not a CUDA build")
device = torch.device("cuda:0")
name = torch.cuda.get_device_name(0)
a = torch.randn((1024, 1024), device=device)
b = torch.randn((1024, 1024), device=device)
torch.cuda.synchronize()
print(f"gpu={name} backend={'hip' if torch.version.hip else 'cuda'}", flush=True)
until = time.monotonic() + duration
iterations = 0
while time.monotonic() < until:
    c = a @ b
    torch.cuda.synchronize()
    iterations += 1
print(f"status=pass gpu_iterations={iterations}", flush=True)
PYEOF
  local load_start=$SECONDS
  timeout --signal=TERM --kill-after=5s 45s python3 "$matmul_py" "$VENDOR" "$duration" > "$load_log" 2>&1 &
  local load_pid=$! sample_entries=() i ts smi_out joined load_rc=0 elapsed_s
  for i in 0 5 10 15 20 25; do
    sleep 5
    elapsed_s=$((SECONDS - load_start))
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    if [[ "$VENDOR" == amd ]]; then
      if [[ "$AMD_TOOL" == rocm-smi ]]; then
        smi_out="$(timeout --signal=TERM --kill-after=1s 5s rocm-smi --showclocks --showtemp --showpower 2>&1 || echo unavailable: rocm-smi metric command failed or timed out)"
      elif [[ "$AMD_TOOL" == amd-smi ]]; then
        smi_out="$(timeout --signal=TERM --kill-after=1s 5s amd-smi metric --gpu all --usage --temperature --power --clock 2>&1 || echo unavailable: amd-smi metric command failed or timed out)"
      else smi_out="unavailable: no supported AMD SMI utility"; fi
    else
      smi_out="$(timeout --signal=TERM --kill-after=1s 5s nvidia-smi --query-gpu=clocks.sm,clocks.mem,temperature.gpu,power.draw,clocks_throttle_reasons.hw_slowdown --format=csv,noheader 2>&1 || echo unavailable: nvidia-smi metric command failed or timed out)"
    fi
    printf '=== t+%ss (%s) ===\n%s\n' "$i" "$ts" "$smi_out" >> "$RAWDIR/gpu-load-samples.txt"
    sample_entries+=("{\"t_offset_s\":$elapsed_s,\"recorded_at\":\"$(esc "$ts")\",\"sample\":\"$(esc "$smi_out")\"}")
  done
  wait "$load_pid" || load_rc=$?
  joined="[]"
  if [[ ${#sample_entries[@]} -gt 0 ]]; then joined="[$(IFS=,; echo "${sample_entries[*]}")]"; fi
  if [[ $load_rc -eq 0 ]] && grep -q '^status=pass gpu_iterations=[1-9][0-9]*$' "$load_log"; then
    printf '{"status":"pass","method":"torch_gpu_matmul","duration_s":%d,"nominal_interval_s":5,"samples":%s}' "$duration" "$joined"
  else
    LOAD_FAILURE=1
    save_raw gpu-load "unknown: GPU workload failed; see raw/gpu-load.log"
    printf '{"status":"unknown","reason":"GPU workload failed; inspect raw/gpu-load.log","method":"torch_gpu_matmul","duration_s":%d,"nominal_interval_s":5,"samples":%s}' "$duration" "$joined"
  fi
}
LOAD_FAILURE=0
LOAD_SAMPLE_JSON=""
run_load_sample > "$RAWDIR/load-sample.json"
LOAD_SAMPLE_JSON="$(cat "$RAWDIR/load-sample.json")"

# ---------------------------------------------------------------------------
# Assemble fingerprint.json
# ---------------------------------------------------------------------------
cat > "$OUTDIR/fingerprint.json" <<EOF
{
  "schema": "second-run/shop-fingerprint@3",
  "schema_version": "$SCRIPT_VERSION",
  "recorded_at": "$RECORDED_AT",
  "idle_verified": false,
  "sample_context": "ambient; workload isolation and idle state were not verified",
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
    sha256sum fingerprint.json raw/* 2>/dev/null > MANIFEST.sha256
  )
  log "MANIFEST.sha256 written to $OUTDIR/MANIFEST.sha256"
else
  log "sha256sum not found; MANIFEST.sha256 skipped"
fi

log "done: $OUTDIR"
if [[ $LOAD_FAILURE -ne 0 ]]; then
  log "requested GPU load was not verified; fingerprint retained with load_sample unknown"
  exit 4
fi
