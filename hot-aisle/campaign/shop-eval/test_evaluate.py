#!/usr/bin/env python3
"""Offline integration checks for evaluate.sh using only a local fake SSH seat."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parent
if os.name == "nt":
    BASH = Path(r"C:\Program Files\Git\bin\bash.exe")
    SCRATCH = Path(r"S:\Scratch\Runs\ha-combined-reference-20260925")
else:
    BASH = Path(shutil.which("bash") or "/bin/bash")
    SCRATCH = Path(tempfile.gettempdir()) / "ha-combined-reference-20260925"


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.assertTrue(BASH.is_file(), "a Bash executable is required")
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="shop-eval-", dir=SCRATCH)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.se = self.root / "project/hot-aisle/campaign/shop-eval"
        self.campaign = self.root / "project/hot-aisle/campaign"
        self.runs = self.root / "private-runs"
        (self.se / "probe").mkdir(parents=True)
        (self.se / "diagnose/reference").mkdir(parents=True)
        (self.se / "counter/records").mkdir(parents=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.remote = self.root / "remote"
        self.remote.mkdir()
        self.log = self.root / "ssh.log"
        self.trace = self.root / "trace"
        shutil.copy2(SOURCE / "evaluate.sh", self.se / "evaluate.sh")
        (self.campaign / "cells.amd.sh").write_text("# fixture\n")
        (self.se / "diagnose/reference/hotaisle-2026-09.json").write_text("{}\n")
        self._write("ssh", r'''#!/usr/bin/env bash
set -euo pipefail
while (($#)); do case "$1" in -o|-i|-P) shift 2;; --) shift; break;; *) break;; esac; done
shift
cmd="$1"
printf '%s\n' "$cmd" >> "$FAKE_SSH_LOG"
if [[ "${FAKE_HIDE_RUN_EXIT:-0}" == 1 && "$cmd" == test\ -f\ *run.exit* ]]; then exit 1; fi
cd "$FAKE_REMOTE_HOME"
bash -c "$cmd"
''')
        self._write("scp", r'''#!/usr/bin/env bash
set -euo pipefail
while (($#)); do case "$1" in -o|-i|-P) shift 2;; -r) shift;; --) shift; break;; *) break;; esac; done
args=("$@"); dest="${args[-1]}"; sources=("${args[@]:0:${#args[@]}-1}")
if [[ "$dest" == *:* ]]; then
  d="${dest#*:}"; mkdir -p "$FAKE_REMOTE_HOME/${d%/}"
  for s in "${sources[@]}"; do cp -r "$s" "$FAKE_REMOTE_HOME/${d%/}/"; done
else
  mkdir -p "$dest"
  for s in "${sources[@]}"; do
    [[ "${FAKE_SCP_FAIL_PULL:-0}" != 1 ]] || { echo 'scripted pull failure' >&2; exit 19; }
    r="${s#*:}"
    if [[ "$r" == */. ]]; then cp -r "$FAKE_REMOTE_HOME/${r%/.}/." "$dest/"; else cp -r "$FAKE_REMOTE_HOME/$r" "$dest/"; fi
  done
fi
''')
        self._write("python3", '#!/usr/bin/env bash\nexec "$TEST_PYTHON" "$@"\n')
        self._write("fingerprint.sh", r'''#!/usr/bin/env bash
set -euo pipefail
[[ "${EVAL_FAIL_STAGE:-}" != fingerprint ]] || exit 21
o="$2"; mkdir -p "$o/raw"; echo '{}' > "$o/fingerprint.json"; echo raw > "$o/raw/item.txt"
(cd "$o" && sha256sum fingerprint.json raw/item.txt > MANIFEST.sha256)
echo fingerprint >> "$FAKE_TRACE"
''')
        (self.se / "probe/fingerprint.sh").write_text((self.bin / "fingerprint.sh").read_text())
        (self.campaign / "arm.sh").write_text(r'''#!/usr/bin/env bash
set -euo pipefail
RESULT_DIR=/tmp/workload-report
if [[ "$1" == serve ]]; then
  echo serve >> "$FAKE_TRACE"; [[ "${EVAL_FAIL_STAGE:-}" != serve ]] || exit 22
  mkdir -p "$RESULT_DIR"; echo '{}' > "$RESULT_DIR/env.json"
elif [[ "$1" == bench ]]; then
  echo bench >> "$FAKE_TRACE"; [[ "${EVAL_FAIL_STAGE:-}" != bench ]] || exit 23
  echo '{}' > "$RESULT_DIR/cell-1.json"
  (cd "$RESULT_DIR" && sha256sum env.json cell-1.json > MANIFEST.sha256)
else exit 2; fi
''')
        (self.campaign / "engine_table.cjs").write_text("const a=process.argv.slice(2); process.stdout.write(JSON.stringify({fixture:true,rate:a[1]})+'\\n');\n")
        (self.se / "diagnose/diagnose.py").write_text(r'''import argparse,json,pathlib,sys
p=argparse.ArgumentParser(); [p.add_argument(x) for x in ('--fingerprint','--bench','--reference','--out')]; p.add_argument('--counter'); a=p.parse_args()
b=pathlib.Path(a.bench)
if not b.is_file() or not json.loads(b.read_text()).get('fixture'): raise SystemExit(5)
pathlib.Path(a.out).write_text('table='+b.name+'\n')
''')

    def _write(self, name, body):
        p = self.bin / name
        p.write_text(body)
        p.chmod(0o755)

    def env(self, **extra):
        runs = Path(extra.pop("SHOP_EVAL_RUNS_DIR", self.runs))
        def unix(path):
            if os.name != "nt":
                return str(path)
            return subprocess.check_output([str(BASH), "-lc", "cygpath -u \"$1\"", "fixture", str(path)], text=True).strip()
        remote, fake_bin, ssh_log, trace = map(unix, (self.remote, self.bin, self.log, self.trace))
        return {**os.environ, "FAKE_BIN": fake_bin, "TEST_PYTHON": unix(Path(sys.executable)),
                "SHOP_EVAL_RUNS_DIR": unix(runs),
                "FAKE_REMOTE_HOME": remote, "FAKE_SSH_LOG": ssh_log, "FAKE_TRACE": trace,
                "EVALUATE_POLL_INTERVAL_SECONDS": "1", **extra}

    def run_eval(self, *args, env=None):
        command = 'export PATH="$FAKE_BIN:$PATH"; exec bash "$@"'
        return subprocess.run([str(BASH), "-c", command, "fixture", str(self.se / "evaluate.sh"), *map(str, args)], cwd=self.se,
                              env=env or self.env(), text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=30)

    def run_path(self, tag):
        day = subprocess.check_output([str(BASH), "-lc", "date -u +%Y-%m-%d"], text=True).strip()
        return self.runs / f"latitude-{day}-{tag}"

    def test_launch_pid_failfast_collect_table_and_final_manifest(self):
        result = self.run_eval("latitude", "amd", "tester@fixture.invalid",
                               env=self.env(SHOP_RATE="0.75", EVALUATE_RUN_TAG="ok"))
        self.assertEqual(result.returncode, 0, result.stdout)
        run = self.run_path("ok")
        self.assertEqual(self.trace.read_text().splitlines(), ["fingerprint", "serve", "bench"])
        self.assertTrue((self.remote / f"shop-eval-latitude-{run.name.split('-', 1)[1]}" / "run.pid").is_file())
        self.assertTrue((run / "bench/cell-1.json").is_file())
        self.assertIn("table=engine_table.json", (run / "REPORT.md").read_text())
        checked = subprocess.run([str(BASH), "-lc", "cd \"$1\" && sha256sum -c MANIFEST.sha256", "fixture", str(run)], capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_serve_failure_stops_before_bench_or_scoring(self):
        result = self.run_eval("latitude", "amd", "tester@fixture.invalid",
                               env=self.env(EVAL_FAIL_STAGE="serve", EVALUATE_RUN_TAG="fail"))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.trace.read_text().splitlines(), ["fingerprint", "serve"])
        run = self.run_path("fail")
        self.assertFalse((run / "engine_table.json").exists())
        self.assertIn("remote job failed with exit 22", result.stdout)

    def test_collection_failure_stops_before_scoring(self):
        result = self.run_eval("latitude", "amd", "tester@fixture.invalid",
                               env=self.env(FAKE_SCP_FAIL_PULL="1", EVALUATE_RUN_TAG="pull-fail"))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.run_path("pull-fail") / "engine_table.json").exists())
        self.assertIn("scripted pull failure", result.stdout)

    def test_host_injection_rejected_and_rescore_is_local(self):
        bad = self.run_eval("latitude", "amd", "tester@host;touch${IFS}/tmp/pwned")
        self.assertNotEqual(bad.returncode, 0)
        self.assertFalse(self.log.exists())
        good = self.run_eval("latitude", "amd", "tester@fixture.invalid",
                             env=self.env(SHOP_RATE="0.75", EVALUATE_RUN_TAG="local"))
        self.assertEqual(good.returncode, 0, good.stdout)
        before = self.log.read_text()
        run = self.run_path("local")
        source_manifest_before = hashlib.sha256((run / "MANIFEST.sha256").read_bytes()).hexdigest()
        source_report_before = (run / "REPORT.md").read_bytes()
        rescored_env = self.env(EVALUATE_RESCORE_TAG="check")
        rescored = self.run_eval("--rescore", run, "1.25", env=rescored_env)
        self.assertEqual(rescored.returncode, 0, rescored.stdout)
        self.assertEqual(self.log.read_text(), before)
        derived = run.with_name(run.name + "-rescore-check")
        self.assertIn('"rate":"1.25"', (derived / "engine_table.json").read_text())
        self.assertEqual(hashlib.sha256((run / "MANIFEST.sha256").read_bytes()).hexdigest(), source_manifest_before)
        self.assertEqual((run / "REPORT.md").read_bytes(), source_report_before)
        checked = subprocess.run([str(BASH), "-lc", "cd \"$1\" && sha256sum -c MANIFEST.sha256", "fixture", str(derived)], capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_duplicate_run_identity_refuses_overwrite(self):
        env = self.env(EVALUATE_RUN_TAG="duplicate")
        first = self.run_eval("latitude", "amd", "tester@fixture.invalid", env=env)
        self.assertEqual(first.returncode, 0, first.stdout)
        run = self.run_path("duplicate")
        before = hashlib.sha256((run / "MANIFEST.sha256").read_bytes()).hexdigest()
        again = self.run_eval("latitude", "amd", "tester@fixture.invalid", env=env)
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("refusing to overwrite existing run", again.stdout)
        self.assertEqual(before, hashlib.sha256((run / "MANIFEST.sha256").read_bytes()).hexdigest())

    def test_rejects_any_runs_directory_inside_checkout(self):
        inside_checkout = self.root / "project/other-private-data"
        inside_checkout.mkdir()
        live = self.run_eval("latitude", "amd", "tester@fixture.invalid",
                             env=self.env(SHOP_EVAL_RUNS_DIR=inside_checkout))
        self.assertNotEqual(live.returncode, 0)
        self.assertIn("outside the checked-out project", live.stdout)
        self.assertFalse(self.log.exists())

        source = self.root / "private-source"
        source.mkdir()
        rescore = self.run_eval("--rescore", source, "1.00",
                                env=self.env(SHOP_EVAL_RUNS_DIR=inside_checkout))
        self.assertNotEqual(rescore.returncode, 0)
        self.assertIn("outside the checked-out project", rescore.stdout)

    def test_missing_remote_exit_status_times_out_as_unresolved(self):
        result = self.run_eval("latitude", "amd", "tester@fixture.invalid",
                               env=self.env(FAKE_HIDE_RUN_EXIT="1", EVALUATE_POLL_TIMEOUT_SECONDS="2",
                                            EVALUATE_POLL_INTERVAL_SECONDS="1", EVALUATE_RUN_TAG="timeout"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("timed out waiting for remote exit status", result.stdout)
        self.assertIn("Remote status is unresolved", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
