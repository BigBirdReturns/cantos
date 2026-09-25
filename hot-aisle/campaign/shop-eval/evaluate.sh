#!/usr/bin/env bash
# evaluate.sh <shop> <amd|nvidia> <user@host> [ssh-key]
#
# Thin orchestrator for one shop-eval run, driven from the operator's Linux box (or WSL).
# It copies probe/fingerprint.sh and the campaign's arm.sh + cells.<kind>.sh to the rented
# machine, runs fingerprint -> serve -> bench there over one ssh session under nohup, pulls
# the results back with the campaign's own collect.sh, scores them with engine_table.cjs,
# and runs diagnose.py against the Hot Aisle reference -- all into
# shop-eval/runs/<shop>-<date>/.
#
# It never rents, provisions, or deletes a machine. Every stop -- success or failure --
# ends by printing exactly what you, the human, still have to do (see on_exit below and
# MANUAL.md's stop rules).
set -euo pipefail

usage() {
  echo "usage: evaluate.sh <shop> <amd|nvidia> <user@host> [ssh-key]" >&2
  echo "  shop      short slug, e.g. latitude, voltage-park, amd-devcloud" >&2
  echo "  amd|nvidia which GPU vendor's cells and runtime image to use" >&2
  echo "  user@host  ssh target for the already-rented, already-running machine" >&2
  echo "  ssh-key    optional path to a private key (quote it if it has spaces)" >&2
  exit 2
}

[[ $# -ge 3 ]] || usage
shop="$1"
kind="$2"
host="$3"
key="${4:-}"
[[ "$kind" == "amd" || "$kind" == "nvidia" ]] || usage

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
campaign_dir="$(cd "$here/.." && pwd)"
date_tag="$(date -u +%Y-%m-%d)"
rundir="$here/runs/${shop}-${date_tag}"
fp_dir="$rundir/fingerprint"
bench_dir="$rundir/bench"
log_file="$rundir/evaluate.log"
remote_dir='shop-eval-run'   # relative to the ssh login's $HOME on the rented machine

mkdir -p "$fp_dir" "$bench_dir"

ssh_opts=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new)
scp_opts=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new)
if [[ -n "$key" ]]; then
  ssh_opts+=(-i "$key")
  scp_opts+=(-i "$key")
fi

log_line() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*" | tee -a "$log_file"; }

STAGE="start"
on_exit() {
  local ec=$?
  {
    echo
    echo "================================================================="
    echo "evaluate.sh stopped after stage '$STAGE' (exit code $ec) for $shop on $host"
    case "$STAGE" in
      start|copy)
        echo "Nothing ran on $host yet beyond copying files there."
        ;;
      running)
        echo "The remote fingerprint/serve/bench job may still be running on $host."
        echo "Check progress:"
        echo "  ssh ${key:+-i \"$key\" }\"$host\" \"tail -n 40 $remote_dir/run.log\""
        ;;
      collected)
        echo "Results were pulled back but scoring/diagnose did not finish."
        ;;
      scored)
        echo "Scored, but diagnose.py did not finish; fill report_template.md by hand."
        ;;
      diagnosed|done)
        echo "All local steps finished."
        ;;
    esac
    echo
    echo "You must still do this by hand -- evaluate.sh never provisions or deletes machines:"
    echo "  1. Delete the $shop machine ($host) in its own console now. It keeps billing"
    echo "     until you do, regardless of what this script did."
    echo "  2. Open $rundir/REPORT.md if it exists; otherwise copy report_template.md into"
    echo "     $rundir/REPORT.md and fill it from $fp_dir, $bench_dir, and the engine table."
    echo "  3. Fill in the counter record for $shop this month if you have not already:"
    echo "     $here/counter/records/${shop}-$(date -u +%Y-%m).json  (see counter/PROTOCOL.md)"
    echo "     then: python3 \"$here/counter/counter_record.py\" score \"$here/counter/records/${shop}-$(date -u +%Y-%m).json\""
    echo "  4. When the real invoice posts, add it to $rundir/REPORT.md's provenance line."
    echo "  5. If $shop should join the roster: add it to providers/providers.jsonl and an"
    echo "     observation to availability/README.md's ledger (see MANUAL.md)."
    echo "================================================================="
  } | tee -a "$log_file"
}
trap on_exit EXIT

log_line "shop-eval: $shop ($kind) on $host -> $rundir"

# 1. Copy the probe, the workload arm, and its cells to the remote machine.
probe_script="$here/probe/fingerprint.sh"
[[ -f "$probe_script" ]] || { echo "missing $probe_script" >&2; exit 1; }
arm_script="$campaign_dir/arm.sh"
[[ -f "$arm_script" ]] || { echo "missing $arm_script" >&2; exit 1; }
cells_file="$campaign_dir/cells.$kind.sh"
[[ -f "$cells_file" ]] || {
  echo "missing $cells_file; generate it first with:" >&2
  echo "  node \"$campaign_dir/gen-cells.cjs\"" >&2
  exit 1
}

runner_local="$rundir/remote-run.sh"
cat > "$runner_local" <<REMOTE
#!/usr/bin/env bash
set -uo pipefail
cd "\$(dirname "\$0")"
bash fingerprint.sh "$kind" .
bash arm.sh serve "$kind"
bash arm.sh bench "$kind"
REMOTE
chmod +x "$runner_local"

ssh "${ssh_opts[@]}" "$host" "mkdir -p $remote_dir"
scp "${scp_opts[@]}" "$probe_script" "$arm_script" "$cells_file" "$runner_local" "$host:$remote_dir/"
STAGE="copy"
log_line "copied fingerprint.sh, arm.sh, cells.$kind.sh, remote-run.sh to $host:$remote_dir/"

# 2. Fingerprint, serve, and bench over one ssh session, under nohup so a dropped
#    connection does not kill the run. Everything after this point bills the seat;
#    the 25-minute health cap in arm.sh and the bench watchdog are the only automatic
#    stops (see MANUAL.md's stop rules). This step normally takes 45-90 minutes.
ssh "${ssh_opts[@]}" "$host" \
  "cd $remote_dir && chmod +x remote-run.sh fingerprint.sh arm.sh && nohup bash remote-run.sh > run.log 2>&1 & echo \$! > run.pid; disown"
STAGE="running"
log_line "started fingerprint + serve + bench on $host under nohup; polling run.log"

while ssh "${ssh_opts[@]}" "$host" "kill -0 \$(cat $remote_dir/run.pid 2>/dev/null) 2>/dev/null"; do
  sleep 30
  ssh "${ssh_opts[@]}" "$host" "tail -n 3 $remote_dir/run.log" 2>/dev/null | tee -a "$log_file" || true
done
log_line "remote run finished; last lines of run.log:"
ssh "${ssh_opts[@]}" "$host" "tail -n 30 $remote_dir/run.log" 2>&1 | tee -a "$log_file" || true

# 3. Pull back fingerprint.json (with its raw/ and MANIFEST.sha256) and the bench cells.
scp "${scp_opts[@]}" -r "$host:$remote_dir/raw" "$host:$remote_dir/fingerprint.json" "$host:$remote_dir/MANIFEST.sha256" "$fp_dir/" 2>>"$log_file" \
  || log_line "warning: could not collect the full fingerprint set; check $host:$remote_dir manually"

if [[ -n "$key" ]]; then export SSH_KEY="$key"; fi
bash "$campaign_dir/collect.sh" "$shop" "$host" >>"$log_file" 2>&1 \
  || log_line "warning: collect.sh reported a problem; see $log_file"
if [[ -d "$campaign_dir/results/$shop" ]]; then
  cp -a "$campaign_dir/results/$shop/." "$bench_dir/"
  log_line "bench results copied into $bench_dir (also left in $campaign_dir/results/$shop by collect.sh)"
fi
STAGE="collected"

# 4. Score locally with the existing engine. Needs the rate this seat was actually billed
#    at -- pass it as SHOP_RATE=<dollars-per-gpu-hour> in the environment, since evaluate.sh
#    does not know your invoice.
if [[ -n "${SHOP_RATE:-}" ]]; then
  if command -v node >/dev/null 2>&1; then
    node "$campaign_dir/engine_table.cjs" "$bench_dir" "$SHOP_RATE" 1000 15000 > "$rundir/engine_table.json" \
      && log_line "engine table written to $rundir/engine_table.json (gates: p95 TTFT 1000ms, p95 E2E 15000ms)" \
      || log_line "warning: engine_table.cjs failed; score manually"
  else
    log_line "warning: node not found; cannot run engine_table.cjs (see MANUAL.md prerequisites)"
  fi
else
  log_line "SHOP_RATE not set; skipping engine_table.cjs. Run it yourself once you know the billed rate:"
  log_line "  node \"$campaign_dir/engine_table.cjs\" \"$bench_dir\" <rate> 1000 15000 > \"$rundir/engine_table.json\""
fi
STAGE="scored"

# 5. Diagnose against the Hot Aisle reference.
diag="$here/diagnose/diagnose.py"
ref="$here/diagnose/reference/hotaisle-2026-09.json"
counter_rec="$here/counter/records/${shop}-$(date -u +%Y-%m).json"
if [[ -f "$diag" && -f "$ref" ]]; then
  python3 "$diag" --counter "$counter_rec" --fingerprint "$fp_dir/fingerprint.json" \
    --bench "$bench_dir" --reference "$ref" --out "$rundir/REPORT.md" \
    && log_line "REPORT.md written to $rundir/REPORT.md" \
    || log_line "warning: diagnose.py failed; fill report_template.md by hand"
else
  log_line "warning: diagnose.py or the reference file is not in place yet; fill report_template.md by hand"
fi
STAGE="diagnosed"

# 6. Manifest everything this run produced locally.
( cd "$rundir" && find . -type f ! -name MANIFEST.sha256 -exec sha256sum {} \; | sort -k2 > MANIFEST.sha256 )
log_line "MANIFEST.sha256 written for $rundir"
STAGE="done"
