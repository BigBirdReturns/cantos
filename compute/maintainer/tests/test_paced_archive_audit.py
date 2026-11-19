"""Data-only paced archive replay: independent positive and negative controls."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

from compute.maintainer.paced_archive_audit import AuditError, audit_archive, _open_archive


def packed(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def hashof(raw):
    return hashlib.sha256(raw).hexdigest()


def fixture(path, *, false_acceptance=False, unsafe=False, duplicate=False, bad_manifest=False):
    src = {}
    source_text = "def solve(x): return x + 1"
    sha = hashof(source_text.encode())
    workload = packed({"schema": "cantos.maintainer.workload/1", "cases": [{"id": "HumanEval/0"}]})
    inputs = {}
    for arm in ("baseline", "candidate"):
        prefix = arm + "/"
        gp = arm + "_grades/"
        row = {"task_id": "HumanEval/0", "trial": 0, "repetition": 0,
               "warmup": False,
               "attempts": [{"response_text": source_text, "response_sha256": sha}]}
        run = {"schema": "cantos.maintainer.run/1", "arm": arm,
               "pairing": {"id": "pinned-pair"}, "observations": [row],
               "artifacts": [{"path": "workload.json", "bytes": len(workload),
                              "sha256": hashof(workload)}]}
        src[prefix + "workload.json"] = workload
        src[prefix + "run.json"] = packed(run)
        mapping = packed([{"task_id": "HumanEval/0", "trial": 0, "repetition": 0,
                           "observation_index": 0, "capture_eligible": True,
                           "response_sha256": sha, "solution_sha256": sha,
                           "task_solution_index": 0}])
        evaluations = packed({"eval": {"HumanEval/0": [
            {"task_id": "HumanEval/0", "solution": source_text,
             "base_status": "pass", "plus_status": "pass"}]}})
        src[gp + "artifacts/mapping.json"] = mapping
        src[gp + "artifacts/humaneval_eval_results.json"] = evaluations
        src[gp + "grades.json"] = packed({
            "schema": "cantos.maintainer.grades/1",
            "run_sha256": hashof(src[prefix + "run.json"]),
            "workload_sha256": hashof(workload),
            "artifacts": [{"path": "artifacts/mapping.json",
                            "bytes": len(mapping), "sha256": hashof(mapping)},
                           {"path": "artifacts/humaneval_eval_results.json",
                            "bytes": len(evaluations), "sha256": hashof(evaluations)}],
            "results": [{"task_id": "HumanEval/0", "trial": 0, "repetition": 0,
                         "response_sha256": sha,
                         "accepted": not false_acceptance or arm == "baseline"}],
        })
        inputs[arm] = prefix + "run.json"
        inputs[arm + "_grades"] = gp + "grades.json"
    src["original-analysis.json"] = packed({
        "schema": "cantos.maintainer.verdict/1", "exit_code": 0,
        "verdict": "pass",
        "baseline": {"accepted_tasks": 1, "attempts": 1},
        "candidate": {"accepted_tasks": 1, "attempts": 1}})
    src["notices/ANALYSIS.json"] = packed({
        "schema": "cantos.private-paced-analysis/1", "native_verdict": "pass",
        "board_energy": {
            "baseline": {"accepted_tasks": 1, "status": "aligned",
                         "joules": 5, "measured_duration_s": 10,
                         "joules_per_accepted": 5},
            "candidate": {"accepted_tasks": 1, "status": "aligned",
                          "joules": 6, "measured_duration_s": 12,
                          "joules_per_accepted": 6}}})
    src["comparison.json"] = packed({
        "schema": "cantos.comparison-bundle/1",
        "inputs": inputs, "original_analysis": "original-analysis.json",
        "files": [{"path": n, "bytes": len(v),
                   "sha256": ("0" * 64 if bad_manifest and n == "baseline/run.json"
                              else hashof(v))} for n, v in sorted(src.items())]})
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for n, v in sorted(src.items()):
            z.writestr(n, v)
        if unsafe:
            z.writestr("../outside", b"unsafe")
        if duplicate:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                z.writestr("baseline/run.json", src["baseline/run.json"])
    return hashof(Path(path).read_bytes())


class PacedArchiveAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "paced.zip"

    def tearDown(self):
        self.temp.cleanup()

    def test_fixture_positive_and_energy_denominator(self):
        sha = fixture(self.path)
        r = audit_archive(self.path, sha)
        self.assertEqual(r["contingency"]["both_accepted"], 1)
        self.assertEqual(r["paired_attempts"], 1)
        self.assertEqual(r["candidate_minus_baseline_gpu_board_joules"], 1)
        self.assertEqual(r["arms"]["candidate"]["joules_per_accepted"], 6)

    def test_pinned_archive_tampering(self):
        sha = fixture(self.path)
        with self.assertRaisesRegex(AuditError, "SHA-256"):
            audit_archive(self.path, "0" * 64)
        self.assertEqual(len(sha), 64)

    def test_manifest_mismatch(self):
        sha = fixture(self.path, bad_manifest=True)
        with self.assertRaisesRegex(AuditError, "artifact mismatch"):
            audit_archive(self.path, sha)

    def test_evaluator_acceptance_contradiction(self):
        sha = fixture(self.path, false_acceptance=True)
        with self.assertRaisesRegex(AuditError, "evaluator verdict contradiction"):
            audit_archive(self.path, sha)

    def test_reject_traversal_and_extras(self):
        sha = fixture(self.path, unsafe=True)
        with self.assertRaisesRegex(AuditError, "unsafe ZIP member"):
            audit_archive(self.path, sha)

    def test_duplicate_members_refused(self):
        sha = fixture(self.path, duplicate=True)
        with self.assertRaisesRegex(AuditError, "duplicate"):
            audit_archive(self.path, sha)


if __name__ == "__main__":
    unittest.main()
