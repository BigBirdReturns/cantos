#!/usr/bin/env bash
# One arm of the first qualified workload, run ON the GPU machine.
#
#   arm.sh serve amd|nvidia        pull the pinned image, start vLLM on :8000, wait for health,
#                                  record the environment, run one unrecorded warm-up pass
#   arm.sh bench amd|nvidia        run every cell in cells.<kind>.sh (manual arms only; the Hot
#                                  Aisle arm's cells are driven by the runner over ssh instead)
#   arm.sh stop                    stop the container (the VM keeps billing until you delete it)
#
# Everything the comparison engine needs to match sides is pinned here and in cells.sh:
# model revision, precision, tokenizer revision, workload id, cache policy, runtime digest.
# Results land in /tmp/workload-report with a sha256 manifest. Nothing here provisions or
# deletes machines; that is your hand, on the provider's console.
set -euo pipefail

MODEL="Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8"
REVISION="dcaee4d4dfc5ee71ad501f01f530e5652438fde0"
AMD_IMAGE="rocm/vllm@sha256:30761c2125ce150d556bef46406a0158446421886bf83a2e60154c6e4ca17a13"
NVIDIA_IMAGE="vllm/vllm-openai@sha256:8a69ffad015f138d7170c4ddc429e230a3bc1c1719f67e14324749df200a4b90"
PORT=8000
RESULT_DIR=/tmp/workload-report
HF_CACHE="${HF_CACHE:-$HOME/hf-cache}"
MAX_MODEL_LEN=4096            # 2048 in + 256 out with margin; keeps the KV budget honest across arms
MAX_BENCH_MINUTES="${MAX_BENCH_MINUTES:-50}"   # watchdog for the manual bench loop
TP="${TP:-1}"                  # tensor parallel; set TP=2 on a 2-GPU allocation so the whole billed allocation serves

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
log() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*"; }

need_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    log "docker missing; installing docker.io"
    sudo apt-get update -qq && sudo apt-get install -y -qq docker.io >/dev/null
    sudo systemctl enable --now docker
  fi
  if ! docker info >/dev/null 2>&1; then sudo usermod -aG docker "$USER" || true; log "re-login may be needed for docker group; trying sudo"; fi
}

dk() { if docker info >/dev/null 2>&1; then docker "$@"; else sudo docker "$@"; fi; }

serve() {
  local kind="${1:?serve amd|nvidia}"
  need_docker
  mkdir -p "$RESULT_DIR" "$HF_CACHE"
  local image devices
  case "$kind" in
    amd)    image="$AMD_IMAGE";    devices=(--device=/dev/kfd --device=/dev/dri --group-add video --ipc=host --security-opt seccomp=unconfined --cap-add=SYS_PTRACE) ;;
    nvidia) image="$NVIDIA_IMAGE"; devices=(--gpus all --ipc=host) ;;
    *) echo "serve amd|nvidia" >&2; exit 2 ;;
  esac
  log "pulling $image (pinned by digest)"
  dk pull "$image" >/dev/null
  dk rm -f vllm >/dev/null 2>&1 || true
  log "starting vllm serve $MODEL@$REVISION on :$PORT"
  # The result dir is bind-mounted so `docker exec vllm vllm bench serve` writes where the host
  # (and the runner's scp) can read it. The HF cache persists across container restarts.
  dk run -d --name vllm --network host "${devices[@]}" \
    -v "$HF_CACHE:/root/.cache/huggingface" -v "$RESULT_DIR:$RESULT_DIR" \
    -e HF_HUB_ENABLE_HF_TRANSFER=0 ${HF_TOKEN:+-e HF_TOKEN="$HF_TOKEN"} \
    --entrypoint vllm "$image" serve "$MODEL" --revision "$REVISION" --tokenizer-revision "$REVISION" \
    --served-model-name "$MODEL" --port "$PORT" --max-model-len "$MAX_MODEL_LEN" \
    --tensor-parallel-size "${TP:-1}" --gpu-memory-utilization 0.90 >/dev/null   # request logging is off by default in vLLM >= 0.10; 0.30.0 rejects --disable-log-requests
  log "waiting for /v1/models (model download + load; typically 5-15 min on a datacenter link)"
  local t0=$SECONDS
  until curl -sf "http://127.0.0.1:$PORT/v1/models" >/dev/null; do
    if ! dk ps --format '{{.Names}}' | grep -qx vllm; then log "container exited:"; dk logs --tail 40 vllm; exit 1; fi
    if (( SECONDS - t0 > 1500 )); then log "no health after 25 min; last log lines:"; dk logs --tail 40 vllm; exit 1; fi
    sleep 10
  done
  log "healthy after $((SECONDS - t0)) s"
  env_record "$kind"
  warm_up
}

env_record() {
  local kind="$1" gpu="" driver=""
  if [[ $kind == amd ]]; then
    gpu="$( (rocm-smi --showproductname 2>/dev/null || dk exec vllm rocm-smi --showproductname 2>/dev/null) | grep -i -m1 'card series\|product name' | sed 's/.*: *//' || true)"
    driver="$( (cat /opt/rocm/.info/version 2>/dev/null || dk exec vllm cat /opt/rocm/.info/version 2>/dev/null) || true)"
  else
    gpu="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || true)"
    driver="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1 || true)"
  fi
  local vllm_version; vllm_version="$(dk exec vllm vllm --version 2>/dev/null | tail -1 || echo unknown)"
  local image_id; image_id="$(dk image inspect --format "{{index .RepoDigests 0}}" "$(dk inspect --format "{{.Config.Image}}" vllm)" 2>/dev/null || true)"
  cat > "$RESULT_DIR/env.json" <<EOF
{
  "schema": "second-run/arm-environment@1",
  "recorded_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "kind": "$kind",
  "host": "$(hostname)",
  "gpu": "$gpu",
  "driver_or_rocm": "$driver",
  "image": "$image_id",
  "vllm_version": "$vllm_version",
  "model": "$MODEL",
  "revision": "$REVISION",
  "max_model_len": $MAX_MODEL_LEN,
  "kernel": "$(uname -r)"
}
EOF
  log "environment: gpu='$gpu' vllm='$vllm_version' image='$image_id'"
}

warm_up() {
  log "warm-up pass (unrecorded): 32 prompts at concurrency 8"
  dk exec vllm vllm bench serve --backend openai --base-url "http://127.0.0.1:$PORT" --model "$MODEL" \
    --dataset-name random --random-input-len 2048 --random-output-len 256 --num-prompts 32 \
    --max-concurrency 8 --request-rate inf --seed 1 >/dev/null 2>&1 || { log "warm-up failed; benchmark CLI unavailable in image?"; dk exec vllm vllm bench serve --help | head -5; exit 1; }
  log "warm-up done"
}

bench() {
  local kind="${1:?bench amd|nvidia}"
  local cells="$here/cells.$kind.sh"
  [[ -f "$cells" ]] || { echo "$cells missing; generate it with node campaign/gen-cells.cjs and copy it next to arm.sh" >&2; exit 2; }
  mkdir -p "$RESULT_DIR"
  log "running cells from $(basename "$cells") with a $MAX_BENCH_MINUTES-minute watchdog"
  local t0=$SECONDS
  # Each line of cells.sh is one complete `docker exec vllm vllm bench serve …` command.
  while IFS= read -r line; do
    [[ -z "$line" || "$line" == \#* ]] && continue
    local cell; cell="$(sed -n 's/.*--result-filename \([^ ]*\).*/\1/p' <<<"$line")"
    if [[ -s "$RESULT_DIR/$cell" ]]; then log "skip $cell (exists)"; continue; fi
    if (( (SECONDS - t0) / 60 >= MAX_BENCH_MINUTES )); then log "watchdog: stopping before $cell"; break; fi
    log "cell $cell"
    if ! timeout "$(( (MAX_BENCH_MINUTES*60) - (SECONDS - t0) ))" bash -c "$line" > "$RESULT_DIR/${cell%.json}.log" 2>&1; then
      log "cell $cell FAILED (kept log, no result); continuing"
      rm -f "$RESULT_DIR/$cell"
    fi
  done < "$cells"
  ( cd "$RESULT_DIR" && sha256sum cell-*.json env.json > MANIFEST.sha256 ) 2>/dev/null || true
  log "done in $(( (SECONDS - t0) / 60 )) min; $(ls "$RESULT_DIR"/cell-*.json 2>/dev/null | wc -l) result files in $RESULT_DIR"
  cat "$RESULT_DIR/MANIFEST.sha256" 2>/dev/null || true
}

stop() { dk rm -f vllm >/dev/null 2>&1 && log "vllm container removed (the machine itself is still billing)"; }

case "${1:-}" in
  serve) serve "${2:-}" ;;
  bench) bench "${2:-}" ;;
  stop)  stop ;;
  *) sed -n '2,12p' "$0"; exit 2 ;;
esac
