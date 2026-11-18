"""Tamper and join-integrity tests for retained coding-grade diagnosis."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from compute.maintainer.diagnose_grades import EvidenceError, diagnose, sha256


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True), encoding="utf-8")


class CodingDiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.receipt = {"schema": "cantos.empirical.vllm-application/1", "sources": {}}
        for arm in ("baseline", "candidate"):
            obs = [
                {"task_id": "HumanEval/0", "trial": 0, "repetition": 0, "warmup": False},
                {"task_id": "HumanEval/10", "trial": 0, "repetition": 0, "warmup": False},
            ]
            pairing = {"id": "fixture-paired-1", "schedule": "alternating AB/BA"}
            run_rel = f"vllm-capture/{arm}/run.json"
            grade_rel = f"grade-{arm}/grades.json"
            write_json(self.root / run_rel,
                       {"arm": arm, "pairing": pairing, "observations": obs})
            evals = {"HumanEval/0": [{"task_id": "HumanEval/0", "solution": "return True",
                                      "base_status": "pass", "plus_status": "pass"}],
                     "HumanEval/10": [{"task_id": "HumanEval/10", "solution": "return None",
                                       "base_status": "fail", "plus_status": "fail"}]}
            map_rows = []
            grade_rows = []
            for idx, o in enumerate(obs):
                task = o["task_id"]
                response_hash = hashlib.sha256((task + arm).encode()).hexdigest()
                obs[idx]["attempts"] = [{"response_text": task + arm, "response_sha256": response_hash}]
                map_rows.append({**{k: o[k] for k in ("task_id", "trial", "repetition")},
                                 "capture_eligible": True, "observation_index": idx,
                                 "task_solution_index": 0, "response_sha256": response_hash,
                                 "solution_sha256": hashlib.sha256(evals[task][0]["solution"].encode()).hexdigest()})
                grade_rows.append({**{k: o[k] for k in ("task_id", "trial", "repetition")},
                                   "response_sha256": response_hash, "accepted": idx == 0})
            write_json(self.root / run_rel, {"arm": arm, "pairing": pairing, "observations": obs})
            eval_rel = f"grade-{arm}/artifacts/humaneval_eval_results.json"
            map_rel = f"grade-{arm}/artifacts/mapping.json"
            write_json(self.root / eval_rel, {"eval": evals})
            write_json(self.root / map_rel, map_rows)
            grades = {"schema": "cantos.maintainer.grades/1",
                      "run_sha256": sha256(self.root / run_rel), "workload_sha256": "w" * 64,
                      "results": grade_rows,
                      "artifacts": [{"path": "artifacts/humaneval_eval_results.json",
                                     "sha256": sha256(self.root / eval_rel)},
                                    {"path": "artifacts/mapping.json", "sha256": sha256(self.root / map_rel)}]}
            write_json(self.root / grade_rel, grades)
            self.receipt["sources"][run_rel] = sha256(self.root / run_rel)
            self.receipt["sources"][grade_rel] = sha256(self.root / grade_rel)
        self.save_receipt()

    def save_receipt(self):
        write_json(self.root / "VLLM-EMPIRICAL-RECEIPT.json", self.receipt)

    def mutate(self, arm, rel_suffix, mutation):
        path = self.root / (f"grade-{arm}/" + rel_suffix)
        obj = json.loads(path.read_text())
        mutation(obj)
        write_json(path, obj)
        grade_path = self.root / f"grade-{arm}/grades.json"
        grades = json.loads(grade_path.read_text())
        for artifact in grades["artifacts"]:
            if artifact["path"] == rel_suffix:
                artifact["sha256"] = sha256(path)
        write_json(grade_path, grades)
        self.receipt["sources"][f"grade-{arm}/grades.json"] = sha256(grade_path)
        self.save_receipt()

    def test_source_bound_outcome(self):
        result = diagnose(self.root)
        self.assertEqual(result["total_per_arm"], 2)
        self.assertEqual(result["accepted"], {"baseline": 1, "candidate": 1})
        self.assertEqual(result["cross_arm_acceptance_disagreements"], 0)
        self.assertEqual(result["grading_categories"]["baseline"]["base_fail_plus_fail"], 1)
        self.assertNotIn("return True", json.dumps(result))
        self.assertNotIn("return None", json.dumps(result))

    def test_grade_promotion_rejected_after_receipt_updated(self):
        self.mutate("baseline", "grades.json",
                    lambda g: g["results"][1].__setitem__("accepted", True))
        with self.assertRaisesRegex(EvidenceError, "contradicts"):
            diagnose(self.root)

    def test_mapping_relabel_rejected_even_with_updated_hash(self):
        self.mutate("candidate", "artifacts/mapping.json",
                    lambda m: m[0].__setitem__("task_id", "HumanEval/10"))
        with self.assertRaises(EvidenceError):
            diagnose(self.root)

    def test_response_relabel_rejected_even_with_updated_hash(self):
        self.mutate("candidate", "artifacts/mapping.json",
                    lambda m: m[0].__setitem__("response_sha256", "0" * 64))
        with self.assertRaisesRegex(EvidenceError, "raw capture bytes"):
            diagnose(self.root)

    def test_unaccounted_grade_change_rejected(self):
        p = self.root / "grade-baseline/grades.json"
        obj = json.loads(p.read_text())
        obj["results"][0]["accepted"] = False
        write_json(p, obj)
        with self.assertRaisesRegex(EvidenceError, "receipt/source"):
            diagnose(self.root)

    def test_raw_capture_rewrite_rejected_even_with_updated_manifest(self):
        arm = "baseline"
        run_path = self.root / "vllm-capture/baseline/run.json"
        run = json.loads(run_path.read_text())
        run["observations"][0]["attempts"][0]["response_text"] += " tampered"
        write_json(run_path, run)
        grade_path = self.root / "grade-baseline/grades.json"
        grades = json.loads(grade_path.read_text())
        grades["run_sha256"] = sha256(run_path)
        write_json(grade_path, grades)
        self.receipt["sources"]["vllm-capture/baseline/run.json"] = sha256(run_path)
        self.receipt["sources"]["grade-baseline/grades.json"] = sha256(grade_path)
        self.save_receipt()
        with self.assertRaisesRegex(EvidenceError, "raw capture bytes"):
            diagnose(self.root)

    def test_mismatched_workload_rejected(self):
        self.mutate("candidate", "grades.json",
                    lambda g: g.__setitem__("workload_sha256", "z" * 64))
        with self.assertRaisesRegex(EvidenceError, "mismatched graded task"):
            diagnose(self.root)


if __name__ == "__main__":
    unittest.main()
