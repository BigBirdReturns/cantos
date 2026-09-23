#!/usr/bin/env bash
# On an authorized CPU seat; see README for image preparation.
# Usage: grade.sh TASKS REPLAY_DIR DETAILED_JSON NEW_GRADING_DIR
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ${1:-} == --self-test ]]; then
  exec python3 -B "$HERE/selftest.py" GradeTests
fi
if [[ ${1:-} == --build-image ]]; then
  : "${BASE_IMAGE:?Supply a reviewed digest-pinned Python 3.11 CPU image}"
  [[ $BASE_IMAGE =~ @sha256:[0-9a-f]{64}$ ]] || exit 2
  # Dependencies are installed only inside the CPU-seat container image.
  exec docker build --build-arg "BASE_IMAGE=$BASE_IMAGE" -f "$HERE/grader.Dockerfile" -t run3-evalplus:0.3.1 "$HERE"
fi
: "${EVALPLUS_IMAGE:?Supply a reviewed digest-pinned EvalPlus 0.3.1 image (see README)}"
[[ $EVALPLUS_IMAGE =~ (^sha256:|@sha256:)[0-9a-f]{64}$ ]] || { echo 'Unpinned grader image' >&2; exit 2; }
[[ $# == 4 ]] || exit 2
TASKS=$(realpath "$1"); REPLAY=$(realpath "$2"); DETAIL=$(realpath "$3")
python3 -B "$HERE/grade.py" prepare "$TASKS" "$REPLAY/requests.jsonl" "$DETAIL" "$4"
GRADE=$(realpath "$4")
docker image inspect "$EVALPLUS_IMAGE" > "$GRADE/grader-image.json"
GRADE_CONTAINER="run3-grader-$$"
trap 'docker stop -t 5 "$GRADE_CONTAINER" >/dev/null 2>&1 || true' EXIT
for DATASET in humaneval mbpp; do
  timeout --signal=TERM --kill-after=30s 2h docker run --rm --name "$GRADE_CONTAINER" --network none \
    --read-only --cap-drop ALL --security-opt no-new-privileges \
    --pids-limit 512 --memory 8g --cpus 4 --user "$(id -u):$(id -g)" \
    --tmpfs /tmp:rw,exec,size=2g -e HOME=/tmp -e XDG_CACHE_HOME=/tmp/cache \
    -e HUMANEVAL_OVERRIDE_PATH=/work/humaneval-reference.jsonl \
    -e MBPP_OVERRIDE_PATH=/work/mbpp-reference.jsonl \
    -v "$GRADE:/work" -w /work --entrypoint /bin/sh "$EVALPLUS_IMAGE" -ec \
    "python -c 'import importlib.metadata as m; assert m.version(\"evalplus\") == \"0.3.1\"'; evalplus.evaluate --dataset $DATASET --samples $DATASET.jsonl --parallel 4 --min-time-limit 1 --gt-time-limit-factor 4" \
    > "$GRADE/$DATASET.log" 2>&1
done
python3 -B "$HERE/grade.py" join "$TASKS" "$REPLAY/requests.jsonl" "$DETAIL" "$GRADE" "$GRADE/evaluation.json"
python3 -B "$HERE/grade.py" summary "$REPLAY" "$GRADE/evaluation.json" "$DETAIL" "$GRADE/quality-buckets.json"
