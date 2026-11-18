#!/bin/bash
# Hy4 flash (publisher 3-bit build) on W03's two cards against Cantos's 32 fixed HumanEval+ tasks, three trials,
# graded by the pinned EvalPlus container. One chained run: claim, serve, capture, stop, release, grade.
R=/srv/w03/nvme-work/jobs/Cantos-Hy4-Local-First-20261118
S=/mnt/w03data/Incoming/DataArray/Projects/Products/Cantos/sessions/maintainer-empirical-20261118
O=$R/code-r01
UNIT=claude-hy4-server-20261118c
PORT=18400
IMAGE=sha256:803e956852925ff35f8d7a9f55a97fbcfad09a8dfa77a439f5b2ac537702563d
export XDG_RUNTIME_DIR=/run/user/$(id -u)
mkdir -p $O
cd $R/run

finish() {  # marker text
  systemctl --user stop $UNIT 2>/dev/null
  sleep 5
  python3 $R/run/claim.py release > $O/claim.release.json 2>&1
  echo "$2" > $O/$1
  exit 0
}

ss -ltn | grep -q ":$PORT " && { echo "port busy" > $O/CODE-FAILED; exit 0; }
python3 $R/run/claim.py claim 5400 > $O/claim.json 2>&1 || { echo "cards are claimed by another owner" > $O/CODE-FAILED; exit 0; }
FLAGS="-m $R/models/Hy4-flash-Q3_K-00001-of-00002.gguf -c 8192 -ngl 99 --jinja --host 127.0.0.1 --port $PORT --alias hy4-flash -np 1"
echo "$FLAGS" > $O/server-flags.txt
date -u +%FT%TZ > $O/server.started
systemd-run --user --unit $UNIT --collect -q -p RuntimeMaxSec=5000 -p WorkingDirectory=$O \
  -E LD_LIBRARY_PATH=$R/build/bin:/usr/local/cuda/lib64 bash -c "exec $R/build/bin/llama-server $FLAGS > $O/server.log 2>&1"
systemd-run --user --unit claude-hy4-guard-20261118c --collect -q python3 $R/run/guard2.py $UNIT $O/power.jsonl
for i in $(seq 1 120); do
  sleep 5
  [ "$(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/health)" = 200 ] && break
  [ "$(systemctl --user is-active $UNIT)" = active ] || finish CODE-FAILED "server stopped during load"
done
[ "$(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/health)" = 200 ] || finish CODE-FAILED "server not ready in time"
date -u +%FT%TZ > $O/server.ready

python3 $R/run/make_spec_code.py $O/spec > $O/make_spec.stdout 2>&1 || finish CODE-FAILED "spec could not be written"
cd $R/cantos
python3 -B compute/maintainer/maintainer.py prepare --spec $O/spec/spec.json --arm baseline > $O/prepare.json 2> $O/prepare.err || finish CODE-FAILED "prepare refused the spec"
python3 -B compute/maintainer/maintainer.py observe --spec $O/spec/spec.json --arm baseline --out $O/observe \
  --observation-id hy4-q3k-w03-humanevalplus32-20261118-r01 > $O/observe.stdout 2> $O/observe.stderr
echo "observe_exit=$?" > $O/observe.exit
systemctl --user stop $UNIT
date -u +%FT%TZ > $O/server.stopped
sleep 5
python3 $R/run/claim.py release > $O/claim.release.json 2>&1
[ -f $O/observe/run.json ] || { echo "capture produced no receipt" > $O/CODE-FAILED; exit 0; }

python3 -B compute/maintainer/evalplus_bridge.py prepare --run $O/observe/run.json --reference $S/humaneval-reference.jsonl \
  --normalizer compute/maintainer/normalize.py --out $O/prepared > $O/bridge.prepare.stdout 2> $O/bridge.prepare.stderr \
  || { echo "grading preparation failed" > $O/CODE-FAILED; exit 0; }
docker image inspect "$IMAGE" > $O/prepared/grader-image.json
timeout --signal=TERM --kill-after=30s 2h docker run --rm --name claude-hy4-evalplus-20261118 \
  --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 512 --memory 8g --cpus 4 --user "$(id -u):$(id -g)" \
  --tmpfs /tmp:rw,exec,size=2g -e HOME=/tmp -e XDG_CACHE_HOME=/tmp/cache \
  -e HUMANEVAL_OVERRIDE_PATH=/work/humaneval-reference.jsonl \
  -v "$O/prepared:/work" -w /work --entrypoint /bin/sh "$IMAGE" \
  -ec 'python -c '\''import importlib.metadata as m; assert m.version("evalplus")=="0.3.1"'\''; evalplus.evaluate --dataset humaneval --samples humaneval.jsonl --parallel 4 --min-time-limit 1 --gt-time-limit-factor 4' \
  > $O/prepared/evalplus.log 2>&1
echo "grader_exit=$?" > $O/grader.exit
python3 -B compute/maintainer/evalplus_bridge.py bind --run $O/observe/run.json --prepared $O/prepared \
  --results $O/prepared/humaneval_eval_results.json --log $O/prepared/evalplus.log --out $O/grades \
  > $O/bridge.bind.stdout 2> $O/bridge.bind.stderr
echo "bind_exit=$?" > $O/bind.exit
date -u +%FT%TZ > $O/CODE-DONE
