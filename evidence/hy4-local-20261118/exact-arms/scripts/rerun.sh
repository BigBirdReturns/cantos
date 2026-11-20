#!/bin/bash
# Second capture of both W02 processor arms, with one server version string on both, then the pinned analysis.
# One arm at a time: load, the same single readiness request, Cantos prepare and observe, stop.
J=/mnt/w03data/Incoming/DataArray/Scratch/hy4-exact-arms-20261118
V=/home/jonathan/hy4-exact-arms-20261118
R=$J/run2
mkdir -p $R
REQUEST='{"model":"hy4-flash","messages":[{"role":"user","content":"Say OK."}],"temperature":0,"seed":1729,"max_tokens":8,"stream":true,"stream_options":{"include_usage":true},"chat_template_kwargs":{"reasoning_effort":"no_think"},"top_p":1}'

fail() {
  echo "$1" > $R/RERUN-FAILED
  exit 1
}

arm() {  # name side port [server flags]
  local ARM=$1 SIDE=$2 PORT=$3
  shift 3
  date -u +%FT%TZ > $R/$ARM.server.started
  numactl --interleave=all $V/venv/bin/python $J/serve_hy4.py --model /dev/shm/hy4/$ARM --port $PORT --threads 56 "$@" \
    --status $R/$ARM.status.json > $R/$ARM.server.log 2>&1 &
  local PID=$!
  while kill -0 $PID 2>/dev/null; do
    [ "$(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/health)" = 200 ] && break
    sleep 5
  done
  kill -0 $PID 2>/dev/null || fail "$ARM server exited during load"
  date -u +%FT%TZ > $R/$ARM.server.ready
  curl -sN -m 1700 http://127.0.0.1:$PORT/v1/chat/completions -H 'Content-Type: application/json' -d "$REQUEST" > $R/$ARM.readiness.sse.txt
  cd $J/cantos
  python3 -B compute/maintainer/maintainer.py prepare --spec $R/spec/spec.json --arm $SIDE > $R/$ARM.prepare.json 2> $R/$ARM.prepare.err
  echo "prepare_exit=$?" > $R/$ARM.observe.exit
  python3 -B compute/maintainer/maintainer.py observe --spec $R/spec/spec.json --arm $SIDE --out $R/observe-$ARM \
    --observation-id hy4-$ARM-w02-processors-20261118-r02 > $R/$ARM.observe.stdout 2> $R/$ARM.observe.stderr
  echo "observe_exit=$?" >> $R/$ARM.observe.exit
  kill $PID
  wait $PID 2>/dev/null
  date -u +%FT%TZ > $R/$ARM.server.stopped
  grep -q 'observe_exit=0' $R/$ARM.observe.exit || fail "$ARM capture did not complete"
  sleep 60
}

python3 $J/make_spec_w02.py $R/spec > $R/make_spec.stdout 2>&1 || fail "spec could not be written"
arm bf16 baseline 18510
arm fp8 candidate 18511 --fp8 --skeleton /dev/shm/hy4/bf16
cd $J/cantos
python3 -B compute/maintainer/maintainer.py analyze --baseline $R/observe-bf16/run.json --candidate $R/observe-fp8/run.json \
  --policy $R/spec/policy.precision.json --out $R/analysis > $R/analyze.stdout 2> $R/analyze.stderr
echo "analyze_exit=$?" > $R/analyze.exit
date -u +%FT%TZ > $R/RERUN-DONE
