#!/usr/bin/env bash
# Runs only ON an already authorized GPU seat. Full command in README.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ${1:-} == --self-test ]]; then
  exec python3 -B "$HERE/selftest.py" ArmTests
fi
exec timeout --signal=TERM --kill-after=30s 110m python3 -B "$HERE/arm.py" "$@"
