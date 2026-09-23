#!/usr/bin/env bash
# Run 2 · one arm, run ON the GPU machine. Pre-registered in PREREG.md; do not edit after the prereg commit.
#   arm2.sh all amd|nvidia     serve -> env -> smoke -> bench (both shapes) -> manifest
set -uo pipefail
MODEL="RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic"
REVISION="f50dbad2c84590ca17dc51e207c34321b65ff14b"
AMD_IMAGE="vllm/vllm-openai-rocm@sha256:2e7da1ad1c66836802072588adea75f9f4991da5f9545b4318e91d422c22ce6a"   # v0.30.0
NVIDIA_IMAGE="vllm/vllm-openai@sha256:8a69ffad015f138d7170c4ddc429e230a3bc1c1719f67e14324749df200a4b90"    # v0.30.0 (Run 1 image)
PORT=8000; OUT=/tmp/run2; HF_CACHE="${HF_CACHE:-$HOME/hf-cache}"
SERVE_FLAGS=(--max-model-len 16384 --max-num-seqs 256 --gpu-memory-utilization 0.90 --no-enable-prefix-caching)
WATCHDOG_MIN="${WATCHDOG_MIN:-150}"
log() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*"; }
dk() { if docker info >/dev/null 2>&1; then docker "$@"; else sudo docker "$@"; fi; }

serve() {
  local kind=$1 image env=() devices=()
  case $kind in
    amd)    image=$AMD_IMAGE; devices=(--device=/dev/kfd --device=/dev/dri --group-add video --ipc=host --security-opt seccomp=unconfined --cap-add=SYS_PTRACE); env=(-e VLLM_ROCM_USE_AITER=1) ;;
    nvidia) image=$NVIDIA_IMAGE; devices=(--gpus all --ipc=host) ;;
    *) echo "amd|nvidia" >&2; return 2 ;;
  esac
  mkdir -p "$OUT" "$HF_CACHE"
  log "pull $image"; dk pull "$image" >/dev/null || return 1
  dk rm -f vllm >/dev/null 2>&1
  log "serve $MODEL@$REVISION ${SERVE_FLAGS[*]} ${env[*]}"
  dk run -d --name vllm --network host "${devices[@]}" "${env[@]}" \
    -v "$HF_CACHE:/root/.cache/huggingface" -v "$OUT:$OUT" -e HF_HUB_ENABLE_HF_TRANSFER=0 \
    --entrypoint vllm "$image" serve "$MODEL" --revision "$REVISION" --tokenizer-revision "$REVISION" \
    --served-model-name "$MODEL" --port $PORT "${SERVE_FLAGS[@]}" >/dev/null || return 1
  local t0=$SECONDS
  until curl -sf "http://127.0.0.1:$PORT/v1/models" >/dev/null; do
    if ! dk ps --format '{{.Names}}' | grep -qx vllm; then
      log "container exited"; dk logs --tail 80 vllm > "$OUT/serve-failure.log" 2>&1; tail -30 "$OUT/serve-failure.log"
      ( cd "$OUT" && sha256sum serve-failure.log > MANIFEST.sha256 ); return 1
    fi
    if (( SECONDS - t0 > 2400 )); then log "no health in 40 min"; dk logs --tail 80 vllm > "$OUT/serve-failure.log" 2>&1; return 1; fi
    sleep 10
  done
  log "healthy after $((SECONDS - t0)) s"
  local gpu drv ver
  if [[ $kind == amd ]]; then
    gpu=$(dk exec vllm rocm-smi --showproductname 2>/dev/null | grep -m1 -i 'card series' | sed 's/.*: *//' | tr -d '\t')
    drv=$(dk exec vllm cat /opt/rocm/.info/version 2>/dev/null)
  else
    gpu=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
    drv=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
  fi
  ver=$(dk exec vllm python3 -c 'import vllm;print(vllm.__version__)' 2>/dev/null)
  printf '{"schema":"second-run/arm-environment@1","run":"run2","recorded_at":"%s","kind":"%s","host":"%s","gpu":"%s","driver_or_rocm":"%s","image":"%s","vllm_version":"%s","model":"%s","revision":"%s","serve_flags":"%s","env":"%s","kernel":"%s"}\n' \
    "$(date -u +%FT%TZ)" "$kind" "$(hostname)" "$gpu" "$drv" "$image" "$ver" "$MODEL" "$REVISION" "${SERVE_FLAGS[*]}" "${env[*]}" "$(uname -r)" > "$OUT/env.json"
  log "env: $(cat "$OUT/env.json")"
}

smoke() {  # equivalence smoke check: 3 fixed prompts, greedy, 64 tokens
  local i=0 p
  for p in "Explain what a mutex is in one paragraph." "Write a Python function that returns the nth Fibonacci number iteratively." "What is 17 * 23? Answer with the number only."; do
    curl -s "http://127.0.0.1:$PORT/v1/completions" -H 'content-type: application/json' \
      -d "{\"model\":\"$MODEL\",\"prompt\":\"$p\",\"max_tokens\":64,\"temperature\":0,\"seed\":0}" > "$OUT/smoke-$i.json"
    i=$((i+1))
  done
  log "smoke done"
}

cell() {  # cell <shape> <in> <out> <conc> <n> <rep>
  local shape=$1 in=$2 out=$3 c=$4 n=$5 r=$6
  local f="cell-$shape-c$c-r$r.json"
  [[ -s "$OUT/$f" ]] && return 0
  log "cell $f"
  dk exec vllm vllm bench serve --backend openai --base-url "http://127.0.0.1:$PORT" --model "$MODEL" \
    --dataset-name random --random-input-len "$in" --random-output-len "$out" --ignore-eos \
    --num-prompts "$n" --max-concurrency "$c" --request-rate inf --seed $((7 + r)) \
    --save-result --save-detailed --percentile-metrics ttft,tpot,itl,e2el --metric-percentiles 50,95,99 \
    --result-dir "$OUT" --result-filename "$f" \
    --metadata run=run2 shape="$shape" model_revision=$REVISION precision=FP8-dynamic workload_id="run2-$shape-v1" cache_policy=no-prefix-cache cell="$shape-c$c-r$r" \
    > "$OUT/${f%.json}.log" 2>&1 || { log "cell $f FAILED"; rm -f "$OUT/$f"; }
}

bench() {
  local t0=$SECONDS r row
  local plan=( "long 8192 512 1 16" "long 8192 512 8 64" "long 8192 512 32 128" "long 8192 512 64 256" "long 8192 512 128 256"
               "short 2048 256 1 16" "short 2048 256 8 64" "short 2048 256 32 128" "short 2048 256 64 256" )
  log "warm-up (unrecorded)"
  dk exec vllm vllm bench serve --backend openai --base-url "http://127.0.0.1:$PORT" --model "$MODEL" \
    --dataset-name random --random-input-len 2048 --random-output-len 128 --ignore-eos \
    --num-prompts 32 --max-concurrency 16 --request-rate inf --seed 1 >/dev/null 2>&1
  for r in 0 1 2; do
    for row in "${plan[@]}"; do
      if (( (SECONDS - t0) / 60 >= WATCHDOG_MIN )); then log "watchdog stop"; break 2; fi
      # shellcheck disable=SC2086
      cell $row "$r"
    done
  done
  dk logs vllm > "$OUT/serve.log" 2>&1
  ( cd "$OUT" && sha256sum *.json > MANIFEST.sha256 )
  log "bench done in $(( (SECONDS - t0) / 60 )) min; $(ls "$OUT"/cell-*.json 2>/dev/null | wc -l) cells"
}

case "${1:-}" in
  all)  serve "${2:-}" && smoke && bench; echo "ARM_EXIT=$?" ;;
  stop) dk rm -f vllm ;;
  *)    sed -n 2,3p "$0" ;;
esac
