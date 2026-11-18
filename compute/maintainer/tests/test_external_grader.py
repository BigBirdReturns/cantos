"""Generic grading custody/sandbox contracts; fixtures are not model results."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_instrument as fixtures
import external_grader as bridge
import maintainer
from common import canonical, load, sha256_file


class ExternalGraderTests(unittest.TestCase):
    setUp = fixtures.Instrument.setUp
    tearDown = fixtures.Instrument.tearDown
    save = fixtures.Instrument.save
    run_pair = fixtures.Instrument.run_pair

    def prepared(self, multi_step=False, normalizer=False, mode="external"):
        reference = self.root / "application-reference.json"
        reference.write_text('{"source":"unit fixture acceptance oracle"}\n')
        grader = {"name": "FixtureApplication", "revision": "fixture-v1", "criterion": "full-captured-conversation-v1",
                  "artifact_sha256": "a" * 64, "reference_sha256": sha256_file(reference)}
        normalizer_path = None
        if normalizer:
            normalizer_path = self.root / "normalizer.py"
            normalizer_path.write_text('raise AssertionError("This must never execute on the host")\n')
            grader["normalizer_sha256"] = sha256_file(normalizer_path)
        expect = {"kind": "external", "grader": grader}
        if multi_step:
            self.work["cases"][0] = {"id": "case", "steps": [
                {"messages": [{"role": "user", "content": "first step"}],
                 "expect": {"kind": "text_exact", "value": "def f():\n    return 2\n"}},
                {"messages": [{"role": "user", "content": "use the preceding answer"}], "expect": expect}]}
        else:
            self.work["cases"][0]["expect"] = expect
        self.a.mode = self.b.mode = mode
        self.run_pair()
        self.run_path = self.root / "pair/baseline/run.json"
        self.prepared_dir = self.root / "prepared"
        bridge.prepare(self.run_path, reference, self.prepared_dir, normalizer_path)
        return load(self.prepared_dir / "input/transcript.json")

    def result(self, transcript=None, accepted=None):
        transcript = transcript or load(self.prepared_dir / "input/transcript.json")
        results = {"schema": "cantos.external-results/1", "grader": transcript["grader"],
                   "transcript_sha256": sha256_file(self.prepared_dir / "input/transcript.json"),
                   "results": [{"task_id": row["task_id"], "trial": row["trial"], "repetition": row["repetition"],
                                "response_sha256": row["response_sha256"], "trajectory_sha256": row["trajectory_sha256"],
                                "accepted": row["trajectory"]["capture_eligible"] if accepted is None else accepted}
                               for row in transcript["observations"]]}
        path = self.root / "application-results.json"
        path.write_text(json.dumps(results))
        return path

    def test_multistep_trajectory_is_hash_bound_and_native_grades_validate(self):
        transcript = self.prepared(multi_step=True, normalizer=True)
        row = transcript["observations"][0]
        self.assertEqual(len(row["trajectory"]["steps"]), 2)
        messages = row["trajectory"]["steps"][1]["request"]["messages"]
        self.assertEqual([m["role"] for m in messages], ["user", "assistant", "user"])
        self.assertEqual(messages[1]["content"], "def f():\n    return 2\n")
        self.assertEqual(row["trajectory_sha256"], bridge._sha(canonical(row["trajectory"])))
        grade = bridge.bind(self.run_path, self.prepared_dir, self.result(transcript), self.root / "grades")
        self.assertEqual(grade["execution_basis"], "operator_supplied_result_no_execution_attested")
        checked = maintainer.validate_grades(self.root / "grades/grades.json", self.run_path)
        self.assertEqual(sum(r["accepted"] for r in checked["results"]), 2)

    def test_missing_or_duplicate_results_fail_closed(self):
        self.prepared()
        path = self.result()
        results = load(path)
        results["results"].pop()
        path.write_text(json.dumps(results))
        with self.assertRaisesRegex(ValueError, "coverage"):
            bridge.bind(self.run_path, self.prepared_dir, path, self.root / "bad-missing")
        results["results"].append(copy.deepcopy(results["results"][0]))
        path.write_text(json.dumps(results))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            bridge.bind(self.run_path, self.prepared_dir, path, self.root / "bad-duplicate")

    def test_changed_grader_reference_and_full_conversation_are_rejected(self):
        self.prepared(multi_step=True)
        path = self.result()
        results = load(path)
        results["grader"]["artifact_sha256"] = "b" * 64
        path.write_text(json.dumps(results))
        with self.assertRaisesRegex(ValueError, "Grader identity"):
            bridge.bind(self.run_path, self.prepared_dir, path, self.root / "bad-image")
        path = self.result()
        results = load(path)
        results["results"][0]["trajectory_sha256"] = "c" * 64
        path.write_text(json.dumps(results))
        with self.assertRaisesRegex(ValueError, "full trajectory"):
            bridge.bind(self.run_path, self.prepared_dir, path, self.root / "bad-conversation")
        (self.prepared_dir / "input/reference.bin").write_bytes(b"changed reference")
        with self.assertRaises(ValueError):
            bridge.bind(self.run_path, self.prepared_dir, path, self.root / "bad-reference")

    def test_incomplete_stream_cannot_be_upgraded_to_accepted(self):
        transcript = self.prepared(mode="missing_done")
        self.assertTrue(all(not r["trajectory"]["capture_eligible"] for r in transcript["observations"]))
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            bridge.bind(self.run_path, self.prepared_dir, self.result(accepted=True), self.root / "false-success")
        grade = bridge.bind(self.run_path, self.prepared_dir, self.result(accepted=False), self.root / "true-failure")
        self.assertTrue(all(not r["accepted"] for r in grade["results"]))

    def test_transcript_tamper_cannot_be_hidden_by_updating_preparation_hashes(self):
        transcript = self.prepared(multi_step=True)
        path = self.result(transcript)
        changed = copy.deepcopy(transcript)
        changed["observations"][0]["trajectory"]["steps"][0]["response_text"] = "forged earlier answer"
        transcript_path = self.prepared_dir / "input/transcript.json"
        transcript_path.write_text(json.dumps(changed))
        meta_path = self.prepared_dir / "prepared.json"
        meta = load(meta_path)
        meta["transcript_sha256"] = sha256_file(transcript_path)
        for artifact in meta["artifacts"]:
            if artifact["path"] == "input/transcript.json":
                artifact.update(sha256=sha256_file(transcript_path), bytes=transcript_path.stat().st_size)
        meta_path.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, "exact captured conversation"):
            bridge.bind(self.run_path, self.prepared_dir, path, self.root / "bad-tamper")

    def test_sandbox_argument_contract_and_mocked_receipt(self):
        transcript = self.prepared()
        output = self.result(transcript).read_bytes()
        calls = []
        def process(argv, timeout_s, stdout_limit=bridge.MAX_OUTPUT, stderr_limit=bridge.MAX_LOG):
            calls.append(argv)
            if argv[1:3] == ["context", "inspect"]:
                return 0, json.dumps([{"Endpoints": {"docker": {"Host": "unix:///fixture/docker.sock"}}}]).encode(), b""
            if argv[1:3] == ["image", "inspect"]:
                return 0, json.dumps([{"Id": "sha256:" + "a" * 64}]).encode(), b""
            if argv[1] == "run":
                return 0, output, b"Synthetic Docker invocation test; no container ran."
            return 0, b"", b""
        with patch.object(bridge, "_bounded_process", side_effect=process):
            receipt = bridge.run(self.prepared_dir, self.root / "execution")
        args = next(argv for argv in calls if argv[1] == "run")
        for flag, value in (("--network", "none"), ("--pull", "never"), ("--user", "65534:65534"), ("--cap-drop", "ALL")):
            self.assertEqual(args[args.index(flag) + 1], value)
        self.assertIn("--read-only", args)
        self.assertEqual(args.count("--mount"), 1)
        self.assertIn("target=/input,readonly", args[args.index("--mount") + 1])
        self.assertNotIn("--privileged", args)
        self.assertNotIn("--volume", args)
        self.assertTrue(any(argv[1:3] == ["rm", "--force"] for argv in calls))
        grade = bridge.bind(self.run_path, self.prepared_dir, self.root / "execution/results.json", self.root / "docker-grades",
                            execution_receipt=self.root / "execution/execution.json")
        self.assertEqual(grade["execution_basis"], "retained_bounded_docker_receipt")
        self.assertEqual(receipt["results_sha256"], bridge._sha(output))

    def test_missing_local_image_never_pulls_or_runs(self):
        self.prepared()
        calls = []
        def missing(argv, *args):
            calls.append(argv)
            if argv[1:3] == ["context", "inspect"]:
                return 0, json.dumps([{"Endpoints": {"docker": {"Host": "unix:///fixture/docker.sock"}}}]).encode(), b""
            return 1, b"", b"not found"
        with patch.object(bridge, "_bounded_process", side_effect=missing), self.assertRaisesRegex(ValueError, "no pull"):
            bridge.run(self.prepared_dir, self.root / "missing-image")
        self.assertFalse(any(argv[1] in ("pull", "run") for argv in calls))
        self.assertIn("error", load(self.root / "missing-image/execution.json"))

    def test_explicit_pair_grading_connects_both_native_receipts(self):
        self.prepared(multi_step=True)
        calls = []
        def process(argv, *args):
            calls.append(argv)
            if argv[1:3] == ["context", "inspect"]:
                return 0, json.dumps([{"Endpoints": {"docker": {"Host": "unix:///fixture/docker.sock"}}}]).encode(), b""
            if argv[1:3] == ["image", "inspect"]:
                return 0, json.dumps([{"Id": "sha256:" + "a" * 64}]).encode(), b""
            if argv[1] == "run":
                mounted = argv[argv.index("--mount") + 1].split("source=", 1)[1].split(",target=", 1)[0]
                transcript_path = Path(mounted) / "transcript.json"
                transcript = load(transcript_path)
                result = {"schema": "cantos.external-results/1", "grader": transcript["grader"],
                          "transcript_sha256": sha256_file(transcript_path),
                          "results": [{**{key: row[key] for key in ("task_id", "trial", "repetition", "response_sha256", "trajectory_sha256")},
                                       "accepted": row["trajectory"]["capture_eligible"]} for row in transcript["observations"]]}
                return 0, json.dumps(result).encode(), b"Fixture only; no Docker process executed."
            return 0, b"", b""
        runs = {side: self.root / "pair" / side / "run.json" for side in ("baseline", "candidate")}
        config = {"execute": True, "reference": "application-reference.json", "limits": {"timeout_s": 30}}
        with patch.object(bridge, "_bounded_process", side_effect=process):
            grades = bridge.grade_pair(runs, config, self.root, self.root / "pair-grades")
        for side in ("baseline", "candidate"):
            maintainer.validate_grades(grades[side], runs[side])
            maintainer.validate_closure(grades[side].parent / "artifacts/execution/execution.json")
        self.assertEqual(grades["execution"], {"inference_requests": 0, "grader_executions": 2})
        self.assertEqual(sum(argv[1] == "run" for argv in calls), 2)
        with patch.object(bridge, "_bounded_process", side_effect=AssertionError("must not execute")):
            with self.assertRaisesRegex(ValueError, "execute=true"):
                bridge.grade_pair(runs, {"execute": False, "reference": "application-reference.json"}, self.root, self.root / "forbidden-execution")


if __name__ == "__main__":
    unittest.main()
