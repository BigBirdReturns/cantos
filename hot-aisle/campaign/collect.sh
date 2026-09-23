#!/usr/bin/env bash
# Pull one manual arm's results back and verify them against the machine's own manifest.
#   collect.sh do-h100 root@203.0.113.10 [port]
# Lands in campaign/results/<arm>/ with env.json, cell-*.json, cell-*.log and MANIFEST.sha256.
# Verification here is byte identity with what the machine wrote; the page's import path
# hashes the same bytes again when you drop them in.
set -euo pipefail
arm="${1:?arm name, e.g. do-h100}"; host="${2:?user@host}"; port="${3:-22}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dest="$here/results/$arm"
mkdir -p "$dest"
scp -o BatchMode=yes -o StrictHostKeyChecking=accept-new -P "$port" "$host":/tmp/workload-report/'*' "$dest"/
( cd "$dest" && sha256sum -c MANIFEST.sha256 )
n=$(ls "$dest"/cell-*.json 2>/dev/null | wc -l)
echo "$arm: $n result files verified in $dest"
python3 - "$dest" <<'PY' 2>/dev/null || true
import json,sys,glob,os
d=sys.argv[1]
for f in sorted(glob.glob(os.path.join(d,'cell-*.json'))):
    try:
        j=json.load(open(f))
        print(f"  {os.path.basename(f)}: completed={j.get('completed')} duration={j.get('duration'):.1f}s req/s={j.get('request_throughput'):.3f} p95_ttft={j.get('p95_ttft_ms'):.0f}ms p95_e2el={j.get('p95_e2el_ms'):.0f}ms")
    except Exception as e:
        print(f"  {os.path.basename(f)}: unreadable ({e})")
PY
