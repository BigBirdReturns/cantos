"""Offline regressions at cancellation, stale-observation and ownership boundaries."""
import concurrent.futures
from contextlib import redirect_stdout
import datetime as dt
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import supervision as s


class SupervisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get("TEST_TMPDIR"))
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.prompt = self.state / "EXECUTOR.md"
        self.prompt.write_text("Bounded fixture executor instructions.", encoding="utf-8")
        self.cfg = {
            "state_dir": str(self.state), "runtime_dir": str(self.state),
            "project_home": str(self.state), "project_checkout": str(self.state),
            "start_file": str(self.state / "START.md"), "estate_root": str(self.state),
            "watch_config": str(self.state / "watch.json"),
            "expires_utc": "2099-01-01T00:00:00+00:00",
            "executor_session_id": "00000000-0000-0000-0000-000000000001",
            "preparation_session_id": "00000000-0000-0000-0000-000000000002",
            "source_commit": "a" * 40, "provider_charge_cap_usd": 50,
            "first_allocation_cap_usd": 8, "executor_timeout_seconds": 7200,
            "executor_prompt": str(self.prompt), "claude_executable": "MUST-NOT-RUN",
            "model": "fixture-only",
        }
        self.config_path = self.state / "supervision.json"

    def candidate(self, age_seconds=0):
        return {"classification": "candidate", "started_utc":
                (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=age_seconds)).isoformat(),
                "capture": {"raw_path": "fixture-private.raw", "raw_sha256": "0" * 64},
                "provisioned": False, "synthetic": False}

    def response(self, body, code=0):
        return subprocess.CompletedProcess(["fixture-monitor"], code, json.dumps(body), "")

    def test_stale_latest_candidate_cannot_wake_after_interval_hold(self):
        (self.state / "latest.json").write_text(json.dumps(self.candidate(age_seconds=7200)))
        with patch.object(s.subprocess, "run", return_value=self.response({"classification": "interval_hold"})), \
             patch.object(s, "launch_task", side_effect=AssertionError("must not wake executor")):
            result = s.tick(self.cfg, self.config_path)
        self.assertEqual(result["status"], "interval_hold")
        self.assertFalse((self.state / "acquisition-claim.json").exists())

    def test_stop_arriving_during_sample_blocks_acquisition(self):
        def complete_sample(*args, **kwargs):
            (self.state / "STOP").touch()
            return self.response(self.candidate())
        with patch.object(s.subprocess, "run", side_effect=complete_sample), \
             patch.object(s, "launch_task", side_effect=AssertionError("must not wake executor")):
            result = s.tick(self.cfg, self.config_path)
        self.assertEqual(result["status"], "stopped_or_expired_before_claim")
        self.assertFalse((self.state / "acquisition-claim.json").exists())

    def test_crashed_wrapper_after_expiry_launches_only_one_release_recovery(self):
        self.cfg["expires_utc"] = "2000-01-01T00:00:00+00:00"
        (self.state / "STOP").touch()
        (self.state / "acquisition-claim.json").write_text(json.dumps({"created_utc": "2000-01-01T00:00:00+00:00"}))
        (self.state / "executor-process.json").write_text(json.dumps({"status": "running", "heartbeat_utc": "2000-01-01T00:00:00+00:00"}))
        (self.state / "allocation.json").write_text(json.dumps({"phase": "acquired", "allocation_id": "fixture-owned-vm"}))
        with patch.object(s.subprocess, "run", side_effect=AssertionError("no new capacity sample")), \
             patch.object(s, "launch_task", return_value={"task": "fixture-recovery"}) as launch:
            first = s.tick(self.cfg, self.config_path)
            second = s.tick(self.cfg, self.config_path)
        self.assertEqual(first["status"], "recovery_started")
        self.assertEqual(second["status"], "acquisition_claimed")
        self.assertEqual(launch.call_count, 1)
        launch.assert_called_once_with(self.cfg, "recovery")

    def test_unreadable_allocation_routes_finished_worker_to_recovery(self):
        (self.state / "allocation.json").write_text('{"phase": "acqui')
        self.assertEqual(s.read_state(self.state / "allocation.json"), {})
        child = Mock(pid=999)
        child.poll.return_value = 0
        child.wait.return_value = 0
        with patch.object(s.subprocess, "Popen", return_value=child), \
             patch.object(s, "recover", return_value={"status": "fixture-recovery"}) as recover:
            result = s.worker(self.cfg)
        self.assertEqual(result, 0)
        recover.assert_called_once_with(self.cfg)
        self.assertEqual(json.loads((self.state / "executor-process.json").read_text())["recovery"]["status"], "fixture-recovery")

    def test_simultaneous_candidates_launch_one_executor(self):
        gate = threading.Barrier(2)
        def sample(*args, **kwargs):
            gate.wait(timeout=3)
            return self.response(self.candidate())
        with patch.object(s.subprocess, "run", side_effect=sample), \
             patch.object(s, "launch_task", return_value={"task": "fixture-executor"}) as launch:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(s.tick, self.cfg, self.config_path) for _ in range(2)]
                results = [future.result(timeout=5) for future in futures]
        self.assertEqual(sorted(result["status"] for result in results), ["acquisition_claimed", "executor_started"])
        self.assertEqual(launch.call_count, 1)
        launch.assert_called_once_with(self.cfg, "executor")
        claim = json.loads((self.state / "acquisition-claim.json").read_text())
        self.assertEqual(claim["executor_session_id"], self.cfg["executor_session_id"])

    def test_stale_or_synthetic_current_candidate_cannot_acquire(self):
        cases = [self.candidate(age_seconds=121), dict(self.candidate(), synthetic=True),
                 dict(self.candidate(), provisioned=True), dict(self.candidate(), capture=None)]
        for candidate in cases:
            with self.subTest(candidate=candidate), \
                 patch.object(s.subprocess, "run", return_value=self.response(candidate)), \
                 patch.object(s, "launch_task", side_effect=AssertionError("must not wake executor")):
                self.assertEqual(s.tick(self.cfg, self.config_path)["status"], "candidate_monitor_hold")
        self.assertFalse((self.state / "acquisition-claim.json").exists())

    def test_scheduler_launch_failure_retains_claim_and_does_not_retry_acquisition(self):
        with patch.object(s.subprocess, "run", return_value=self.response(self.candidate())) as sample, \
             patch.object(s, "launch_task", side_effect=RuntimeError("Task Scheduler refused fixture")) as launch:
            with self.assertRaisesRegex(RuntimeError, "Task Scheduler refused"):
                s.tick(self.cfg, self.config_path)
            second = s.tick(self.cfg, self.config_path)
        self.assertEqual(second["status"], "acquisition_claimed")
        self.assertTrue((self.state / "acquisition-claim.json").exists())
        self.assertEqual(sample.call_count, 1)
        launch.assert_called_once_with(self.cfg, "executor")

    def test_stopped_worker_never_starts_acquisition_model(self):
        (self.state / "STOP").touch()
        with patch.object(s.subprocess, "Popen", side_effect=AssertionError("acquisition model started")), \
             patch.object(s, "recover", return_value={"status": "fixture-release-only"}) as recover:
            self.assertEqual(s.worker(self.cfg), 0)
        recover.assert_called_once_with(self.cfg)

    def test_recovery_scheduler_refusal_is_durable_visible_and_not_retried(self):
        self.cfg["expires_utc"] = "2000-01-01T00:00:00+00:00"
        (self.state / "acquisition-claim.json").write_text(json.dumps({"created_utc": "2000-01-01T00:00:00+00:00"}))
        (self.state / "allocation.json").write_text(json.dumps({"phase": "acquired", "allocation_id": "fixture-owned-vm"}))
        with patch.object(s.subprocess, "run", side_effect=AssertionError("no provider/model calls")), \
             patch.object(s, "launch_task", side_effect=RuntimeError("Task Scheduler refused recovery fixture")) as launch:
            first = s.tick(self.cfg, self.config_path)
            second = s.tick(self.cfg, self.config_path)
        self.assertEqual(first["status"], "release_unconfirmed")
        self.assertEqual(second, first)
        self.assertIn("Task Scheduler refused", first["reason"])
        self.assertEqual(json.loads((self.state / "recovery-launch-failure.json").read_text()), first)
        launch.assert_called_once_with(self.cfg, "recovery")
        self.assertEqual(json.loads((self.state / "allocation.json").read_text())["phase"], "acquired")

    def test_recovery_launch_without_execution_claim_times_out_visibly(self):
        self.cfg["expires_utc"] = "2000-01-01T00:00:00+00:00"
        (self.state / "acquisition-claim.json").write_text(json.dumps({"created_utc": "2000-01-01T00:00:00+00:00"}))
        started = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=61)).isoformat()
        (self.state / "recovery-launch.json").write_text(json.dumps({"started_utc": started}))
        with patch.object(s.subprocess, "run", side_effect=AssertionError("no provider/model calls")), \
             patch.object(s, "launch_task", side_effect=AssertionError("must not duplicate recovery task")):
            result = s.tick(self.cfg, self.config_path)
        self.assertEqual(result["status"], "release_unconfirmed")
        self.assertIn("did not claim execution", result["reason"])
        self.assertTrue((self.state / "acquisition-claim.json").exists())

    def test_partial_claim_gets_startup_grace_but_aged_corruption_recovers(self):
        claim = self.state / "acquisition-claim.json"
        claim.write_text('{"created_utc":')
        with patch.object(s.subprocess, "run", side_effect=AssertionError("no new sample")), \
             patch.object(s, "launch_task", return_value={"task": "fixture-recovery"}) as launch:
            fresh = s.tick(self.cfg, self.config_path)
            self.assertEqual(fresh["status"], "acquisition_claimed")
            launch.assert_not_called()
            self.assertFalse((self.state / "recovery-launch.json").exists())
            old = time.time() - 181
            os.utime(claim, (old, old))
            aged = s.tick(self.cfg, self.config_path)
        self.assertEqual(aged["status"], "recovery_started")
        self.assertGreater(aged["heartbeat_age_s"], 180)
        launch.assert_called_once_with(self.cfg, "recovery")

    def test_unreadable_allocation_recovery_prompt_preserves_ownership_boundary(self):
        (self.state / "allocation.json").write_text("{")
        with patch.object(s.subprocess, "run", return_value=self.response({}, code=1)) as model:
            result = s.recover(self.cfg)
            second = s.recover(self.cfg)
        self.assertEqual(model.call_count, 1)
        prompt = model.call_args.args[0][-1]
        self.assertIn("RELEASE-ONLY RECOVERY", prompt)
        self.assertIn("Do not rent or run any workload", prompt)
        self.assertIn("uncertain ownership", prompt)
        self.assertFalse(result["closure_confirmed_by_executor"])
        self.assertEqual(second["recovery_status"], "already_claimed")

    def test_operational_failures_are_nonzero_and_remain_parseable(self):
        self.cfg['runtime_sha256'] = {}
        self.config_path.write_text(json.dumps(self.cfg))
        for status, monitor_code in [('unknown', 1), ('monitor_failed', 2),
                                     ('release_unconfirmed', None), ('candidate_monitor_hold', None),
                                     ('configuration_error', 2)]:
            with self.subTest(status=status):
                result = {'status': status}
                if monitor_code is not None:
                    result['returncode'] = monitor_code
                output = io.StringIO()
                with patch.object(s.sys, 'argv', ['supervision.py', '--config', str(self.config_path)]), \
                     patch.object(s, 'tick', return_value=result), redirect_stdout(output):
                    self.assertEqual(s.main(), 1)
                self.assertEqual(json.loads(output.getvalue())['status'], status)
                self.assertEqual(json.loads((self.state/'supervision-latest.json').read_text())['status'], status)

    def test_success_status_does_not_hide_nonzero_monitor_exit(self):
        self.cfg['runtime_sha256'] = {}
        self.config_path.write_text(json.dumps(self.cfg))
        with patch.object(s.sys, 'argv', ['supervision.py', '--config', str(self.config_path)]), \
             patch.object(s, 'tick', return_value={'status': 'waiting_capacity', 'returncode': 1}), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(s.main(), 1)

    def test_normal_capacity_wait_returns_zero(self):
        self.cfg['runtime_sha256'] = {}
        self.config_path.write_text(json.dumps(self.cfg))
        with patch.object(s.sys, 'argv', ['supervision.py', '--config', str(self.config_path)]), \
             patch.object(s, 'tick', return_value={'status': 'waiting_capacity', 'returncode': 0}), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(s.main(), 0)


if __name__ == "__main__":
    unittest.main()
