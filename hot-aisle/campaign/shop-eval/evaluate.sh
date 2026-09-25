#!/usr/bin/env bash
# evaluate.sh <shop> <amd|nvidia> <user@host> [ssh-key]
# evaluate.sh --rescore <run-directory> <gpu-hour-rate>
#
# Live mode runs only on the already-rented, already-running machine supplied by
# the operator. Rescore mode reads one retained local run and makes no SSH call.
set -Eeuo pipefail

usage() {
  cat >&2 <<'USAGE'
usage: evaluate.sh <shop> <amd|nvidia> <user@host> [ssh-key]
       evaluate.sh --rescore <run-directory> <gpu-hour-rate>
  shop       lowercase provider slug [a-z0-9][a-z0-9-]*
  user@host  SSH user plus DNS name, IPv4, or SSH-config alias; no options/paths
  ssh-key    optional private key path
  --rescore  local-only: rescore retained bench data at a new rate, no SSH
USAGE
  exit 2
}

is_rate() { [[ "$1" =~ ^[0-9]+([.][0-9]+)?$ ]] && awk -v n="$1" 'BEGIN { exit !(n > 0) }'; }
run_python() {
  if command -v python3 >/dev/null 2>&1; then python3 "$@";
  elif command -v python >/dev/null 2>&1; then python "$@";
  else echo "Python 3 is required for local scoring/rescore" >&2; return 127; fi
}

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
campaign_dir="$(cd "$here/.." && pwd -P)"
project_root="$(cd "$here/../../.." && pwd -P)"
diag="$here/diagnose/diagnose.py"
ref="$here/diagnose/reference/hotaisle-2026-09.json"
default_runs_root="${XDG_DATA_HOME:-$HOME/.local/share}/axm-tools/shop-eval/runs"
runs_root="${SHOP_EVAL_RUNS_DIR:-$default_runs_root}"

run_local_reports() {
  local source="$1" rate="$2" outdir="$3" table="$3/engine_table.json" counter_rec="$here/counter/records/${shop:-local}-$(date -u +%Y-%m).json"
  [[ -d "$source" ]] || { echo "source run directory does not exist: $source" >&2; return 1; }
  [[ -d "$source/bench" ]] || { echo "source run has no bench/ data: $source" >&2; return 1; }
  [[ -f "$source/fingerprint/fingerprint.json" ]] || { echo "source run has no fingerprint/fingerprint.json" >&2; return 1; }
  mkdir -p "$outdir"
  is_rate "$rate" || { echo "rate must be a positive decimal GPU-hour price" >&2; return 2; }
  command -v node >/dev/null 2>&1 || { echo "node is required for local scoring" >&2; return 1; }
  [[ -f "$campaign_dir/engine_table.cjs" && -f "$diag" && -f "$ref" ]] || { echo "scorer, diagnosis, or reference file is missing" >&2; return 1; }

  local tmp_table="$outdir/.engine_table.$$.tmp" tmp_report="$outdir/.REPORT.$$.tmp"
  node "$campaign_dir/engine_table.cjs" "$source/bench" "$rate" 1000 15000 > "$tmp_table"
  [[ -s "$tmp_table" ]] || { rm -f "$tmp_table"; echo "engine table is empty" >&2; return 1; }
  mv "$tmp_table" "$table"
  local args=(--fingerprint "$source/fingerprint/fingerprint.json" --bench "$table" --reference "$ref" --out "$tmp_report")
  if [[ -f "$counter_rec" ]]; then args+=(--counter "$counter_rec"); fi
  if ! run_python "$diag" "${args[@]}"; then rm -f "$tmp_report"; echo "diagnosis failed; retained score table is $table" >&2; return 1; fi
  [[ -s "$tmp_report" ]] || { rm -f "$tmp_report"; echo "diagnosis produced no report" >&2; return 1; }
  mv "$tmp_report" "$outdir/REPORT.md"
  echo "Local score table and report written to $outdir"
}

if [[ "${1:-}" == "--rescore" ]]; then
  [[ $# -eq 3 ]] || usage
  run_dir="$(cd "$2" 2>/dev/null && pwd -P)" || { echo "run directory not found: $2" >&2; exit 1; }
  runs_root="$(cd "$runs_root" 2>/dev/null && pwd -P)" || { echo "private runs directory does not exist: ${SHOP_EVAL_RUNS_DIR:-$default_runs_root}" >&2; exit 1; }
  case "$runs_root/" in "$project_root/"*) echo "SHOP_EVAL_RUNS_DIR must be outside the checked-out project to keep run data private" >&2; exit 2 ;; esac
  case "$run_dir/" in "$runs_root"/*/) ;; *) echo "rescore accepts only a run directory beneath $runs_root" >&2; exit 2 ;; esac
  run_name="${run_dir##*/}"
  if [[ "$run_name" =~ ^(.+)-[0-9]{4}-[0-9]{2}-[0-9]{2}- ]]; then shop="${BASH_REMATCH[1]}"; fi
  [[ -s "$run_dir/MANIFEST.sha256" ]] || { echo "source run has no sealed MANIFEST.sha256" >&2; exit 1; }
  ( cd "$run_dir" && sha256sum -c MANIFEST.sha256 ) || { echo "source run manifest does not verify; refusing rescore" >&2; exit 1; }
  is_rate "$3" || { echo "rate must be a positive decimal GPU-hour price" >&2; exit 2; }
  rescore_tag="${EVALUATE_RESCORE_TAG:-$(date -u +%H%M%S)-$$}"
  [[ "$rescore_tag" =~ ^[a-zA-Z0-9][a-zA-Z0-9-]*$ ]] || { echo "invalid EVALUATE_RESCORE_TAG" >&2; exit 2; }
  derived="$runs_root/${run_name}-rescore-${rescore_tag}"
  [[ ! -e "$derived" ]] || { echo "refusing to overwrite existing rescore: $derived" >&2; exit 1; }
  mkdir "$derived"
  source_manifest_sha256="$(sha256sum "$run_dir/MANIFEST.sha256" | awk '{print $1}')"
  run_python - "$derived/RESCORE.json" "$run_dir" "$source_manifest_sha256" "$3" <<'PY'
import datetime,json,sys
out,source,manifest,rate=sys.argv[1:]
with open(out,"w",encoding="utf-8") as f:
    json.dump({"kind":"local-rescore","source_run":source,"source_manifest_sha256":manifest,"modeled_gpu_hour_rate_usd":float(rate),"created_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()},f,indent=2)
    f.write("\n")
PY
  run_local_reports "$run_dir" "$3" "$derived"
  tmp_manifest="$derived/.MANIFEST.$$.tmp"
  ( cd "$derived" && find . -type f ! -name MANIFEST.sha256 ! -name '.MANIFEST.*.tmp' -exec sha256sum {} \; | LC_ALL=C sort -k2 > "$tmp_manifest" )
  mv "$tmp_manifest" "$derived/MANIFEST.sha256"
  echo "Source run remains unchanged; derived rescore: $derived"
  exit 0
fi

[[ $# -ge 3 && $# -le 4 ]] || usage
shop="$1"; kind="$2"; host="$3"; key="${4:-}"
[[ "$shop" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "invalid shop slug: use lowercase letters, digits, and hyphens" >&2; exit 2; }
[[ "$kind" == amd || "$kind" == nvidia ]] || usage
# SSH and SCP each parse the destination themselves. Restrict it to a plain
# user@host token so shell metacharacters, options and scp path syntax cannot
# be smuggled through either command. Use an SSH config alias for IPv6 hosts.
[[ "$host" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9][A-Za-z0-9.-]*$ ]] || {
  echo "invalid SSH target; use user@DNS-name, user@IPv4, or a safe SSH-config alias" >&2; exit 2;
}

date_tag="$(date -u +%Y-%m-%d)"
run_tag="${EVALUATE_RUN_TAG:-$(date -u +%H%M%S)-$$}"
[[ "$run_tag" =~ ^[a-zA-Z0-9][a-zA-Z0-9-]*$ ]] || { echo "invalid EVALUATE_RUN_TAG" >&2; exit 2; }
mkdir -p "$runs_root"
runs_root="$(cd "$runs_root" && pwd -P)"
case "$runs_root/" in "$project_root/"*) echo "SHOP_EVAL_RUNS_DIR must be outside the checked-out project to keep run data private" >&2; exit 2 ;; esac
rundir="$runs_root/${shop}-${date_tag}-${run_tag}"
[[ ! -e "$rundir" ]] || { echo "refusing to overwrite existing run: $rundir" >&2; exit 1; }
mkdir "$rundir" || { echo "could not reserve unique run directory: $rundir" >&2; exit 1; }
fp_dir="$rundir/fingerprint"; bench_dir="$rundir/bench"; log_file="$rundir/evaluate.log"
mkdir "$fp_dir" "$bench_dir"

# Use a unique remote workspace and output directory for this run. The arm's
# only local customization is its result path; workload cells remain pinned.
remote_dir="shop-eval-${shop}-${date_tag}-${run_tag}"
ssh_opts=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new)
scp_opts=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new)
if [[ -n "$key" ]]; then ssh_opts+=(-i "$key"); scp_opts+=(-i "$key"); fi

log_line() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*" | tee -a "$log_file"; }
STAGE="start"
seal_manifest() {
  local tmp="$rundir/.MANIFEST.$$.tmp"
  ( cd "$rundir" && find . -type f ! -name MANIFEST.sha256 ! -name '.MANIFEST.*.tmp' -exec sha256sum {} \; | LC_ALL=C sort -k2 > "$tmp" )
  mv "$tmp" "$rundir/MANIFEST.sha256"
}
on_exit() {
  local ec=$?
  trap - EXIT
  {
    echo
    echo "================================================================="
    echo "evaluate.sh stopped after stage '$STAGE' (exit code $ec) for $shop on $host"
    case "$STAGE" in
      start|copy) echo "No remote workload was started." ;;
      running) echo "Remote status is unresolved. Inspect $remote_dir/run.log and run.exit before retrying." ;;
      collected) echo "Evidence was collected; local scoring/reporting did not finish." ;;
      scored) echo "Scored, but the report step did not finish." ;;
      diagnosed|done) echo "Local scoring, diagnosis and collection finished." ;;
    esac
    echo "This tool does not create or delete provider resources."
    echo "Check the provider console now and release this test allocation by its documented control-plane action."
    echo "Inspect $rundir and verify $rundir/MANIFEST.sha256 before handoff."
    echo "================================================================="
  } | tee -a "$log_file"
  seal_manifest || echo "WARNING: could not seal final manifest for $rundir" >&2
  if (( ec != 0 )); then echo "Run retained at $rundir (exit $ec)." >&2; fi
}
trap on_exit EXIT
log_line "shop-eval: $shop ($kind) on $host -> $rundir"

probe_script="$here/probe/fingerprint.sh"; arm_script="$campaign_dir/arm.sh"; cells_file="$campaign_dir/cells.$kind.sh"
[[ -f "$probe_script" ]] || { echo "missing $probe_script" >&2; exit 1; }
[[ -f "$arm_script" ]] || { echo "missing $arm_script" >&2; exit 1; }
[[ -f "$cells_file" ]] || { echo "missing $cells_file; generate it first with node $campaign_dir/gen-cells.cjs" >&2; exit 1; }

runner_local="$rundir/remote-run.sh"
cat > "$runner_local" <<REMOTE
#!/usr/bin/env bash
set -Eeuo pipefail
status=0
finish() { status=\$?; printf '%s\\n' "\$status" > run.exit; exit "\$status"; }
trap finish EXIT
cd "\$(dirname "\$0")"
# Keep arm.sh's pinned workload intact while isolating output to this run.
sed "s|^RESULT_DIR=/tmp/workload-report\$|RESULT_DIR=\$PWD/workload-report|" arm.sh > arm-run.sh
bash fingerprint.sh "$kind" fingerprint
bash arm-run.sh serve "$kind"
bash arm-run.sh bench "$kind"
[[ -s workload-report/MANIFEST.sha256 ]]
REMOTE
chmod +x "$runner_local"

STAGE="copy"
ssh "${ssh_opts[@]}" -- "$host" "umask 077 && mkdir '$remote_dir'" || { echo "could not create unique remote workspace" >&2; exit 1; }
scp "${scp_opts[@]}" -- "$probe_script" "$arm_script" "$cells_file" "$runner_local" "$host:$remote_dir/"
log_line "copied pinned runner inputs into $remote_dir"

# PID and exit status are written by the same remote shell that backgrounds
# the job. A polling transport error is a failure, never a false completion.
launch_cmd="cd '$remote_dir' && chmod +x remote-run.sh fingerprint.sh arm.sh && (nohup ./remote-run.sh >run.log 2>&1 < /dev/null & echo \$! >run.pid)"
ssh "${ssh_opts[@]}" -- "$host" "$launch_cmd"
STAGE="running"
log_line "started remote workload; waiting for run.exit"
poll_timeout="${EVALUATE_POLL_TIMEOUT_SECONDS:-7200}"
poll_interval="${EVALUATE_POLL_INTERVAL_SECONDS:-10}"
[[ "$poll_timeout" =~ ^[0-9]+$ && "$poll_timeout" -gt 0 ]] || { echo "EVALUATE_POLL_TIMEOUT_SECONDS must be a positive integer" >&2; exit 2; }
[[ "$poll_interval" =~ ^[0-9]+$ && "$poll_interval" -gt 0 ]] || { echo "EVALUATE_POLL_INTERVAL_SECONDS must be a positive integer" >&2; exit 2; }
poll_started=$SECONDS
while true; do
  poll_elapsed=$((SECONDS - poll_started))
  (( poll_elapsed < poll_timeout )) || { echo "timed out waiting for remote exit status after ${poll_elapsed}s; remote job may still be running" >&2; exit 1; }
  if ssh "${ssh_opts[@]}" -- "$host" "test -f '$remote_dir/run.exit'"; then break; else
    rc=$?
    (( rc == 1 )) || { echo "SSH failed while polling remote job (status $rc); stop and inspect manually" >&2; exit 1; }
  fi
  sleep "$poll_interval"
  ssh "${ssh_opts[@]}" -- "$host" "tail -n 3 '$remote_dir/run.log'" 2>&1 | tee -a "$log_file"
done
remote_status="$(ssh "${ssh_opts[@]}" -- "$host" "cat '$remote_dir/run.exit'")"
[[ "$remote_status" =~ ^[0-9]+$ ]] || { echo "invalid remote exit status: $remote_status" >&2; exit 1; }
if (( remote_status != 0 )); then
  ssh "${ssh_opts[@]}" -- "$host" "tail -n 60 '$remote_dir/run.log'" 2>&1 | tee -a "$log_file" || true
  echo "remote job failed with exit $remote_status; refusing to score partial collection as complete" >&2
  exit 1
fi

log_line "remote job exited successfully; collecting into unique local run"
scp "${scp_opts[@]}" -r -- "$host:$remote_dir/fingerprint/fingerprint.json" "$host:$remote_dir/fingerprint/raw" "$host:$remote_dir/fingerprint/MANIFEST.sha256" "$fp_dir/"
( cd "$fp_dir" && sha256sum -c MANIFEST.sha256 ) >> "$log_file" 2>&1
scp "${scp_opts[@]}" -r -- "$host:$remote_dir/workload-report/." "$bench_dir/"
[[ -s "$bench_dir/MANIFEST.sha256" ]] || { echo "collected workload manifest is missing" >&2; exit 1; }
( cd "$bench_dir" && sha256sum -c MANIFEST.sha256 ) >> "$log_file" 2>&1
STAGE="collected"

# Cost remains an explicit operator input. Scores are modeled at this rate;
# invoice and promotional-credit values belong in separate report fields.
if [[ -n "${SHOP_RATE:-}" ]]; then rate="$SHOP_RATE"; else rate=""; fi
if [[ -n "$rate" ]]; then
  run_local_reports "$rundir" "$rate" "$rundir"
  STAGE="scored"
else
  log_line "SHOP_RATE not set; local evidence collected, scoring deferred."
  log_line "Rescore offline later: bash '$here/evaluate.sh' --rescore '$rundir' <modeled-GPU-hour-rate>"
fi

# A counter score is only a disclosed, chosen convention. Its missing fields,
# weights and capability scope must be reviewed; it is not a provider grade.
STAGE="diagnosed"
log_line "run complete; review REPORT.md and evidence classes before drawing conclusions"
STAGE="done"
