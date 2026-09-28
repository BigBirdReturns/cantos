"""output-contract: substring candidates only, retained grade untouched, grader input pinned."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "hot-aisle" / "campaign" / "run3"))
import task_contract
import work

FIXTURE = ROOT / "hot-aisle" / "campaign" / "results" / "run3-scored-a-t0"
PROMPT = 'def f(x):\n    """Return x plus one.\n    >>> f(1)\n    2\n    """\n'
F = "`" * 3


class ContractRules(unittest.TestCase):
    """Mechanical rules on synthetic outputs; no retained bytes involved."""

    def test_valid_raw_output_is_never_touched(self):
        self.assertIsNone(task_contract.propose(PROMPT, "    return x + 1\n", "stop"))
        self.assertIsNone(task_contract.propose(PROMPT, "    return x + 1\nprint(f(1))\n", "length"))

    def test_closing_fence_without_opening_cuts_from_the_fence(self):
        out = "    return x + 1\n\n# Test\nprint(f(1))\n" + F + "\n\nThis returns x plus one.\n"
        rule, start, end = task_contract.propose(PROMPT, out, "stop")
        self.assertEqual(rule, "closing_fence_cut")
        self.assertEqual(out[start:end], "    return x + 1\n\n# Test\nprint(f(1))\n")

    def test_opened_fence_extracts_only_the_first_block(self):
        out = ("Here is the code:\n" + F + "python\n    return x + 1\n" + F + "\n\nAnd tests:\n"
               + F + "python\nassert f(1) == 2\n" + F + "\n")
        rule, start, end = task_contract.propose(PROMPT, out, "stop")
        self.assertEqual(rule, "fence_block_extract")
        self.assertEqual(out[start:end], "    return x + 1\n")

    def test_length_limited_output_backs_off_to_a_parsing_line_prefix(self):
        out = "    return x + 1\n\ndef g(y):\n    return y * (2 +"
        rule, start, end = task_contract.propose(PROMPT, out, "length")
        self.assertEqual(rule, "length_backoff")
        self.assertEqual(out[start:end], "    return x + 1\n\n")
        # The same bytes finished by stop are not a length case: no rule applies, raw stands.
        self.assertIsNone(task_contract.propose(PROMPT, out, "stop"))

    def test_candidates_never_insert_and_refuse_empty_or_prose_only(self):
        self.assertIsNone(task_contract.propose(PROMPT, F + "\nprose only\n", "stop"))  # empty before fence
        self.assertIsNone(task_contract.propose(PROMPT, "I cannot help with that request.", "stop"))
        comment_body = "    # only a comment\n    # another\n"
        self.assertIsNone(task_contract.propose(PROMPT, comment_body, "length"))  # never parses; raw kept
        for out in ("    return x + 1\n" + F + "\nmore\n", "    x = (1,\n    2\n" + F + "\n"):
            proposal = task_contract.propose(PROMPT, out, "stop")
            if proposal is not None:
                _, start, end = proposal
                self.assertIn(out[start:end], out)
        self.assertTrue(task_contract.comment_only("# a\n\n   # b\n"))
        self.assertFalse(task_contract.comment_only("# a\nreturn 1\n"))


class ContractHandoff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = Path("S:/Scratch/Temp") if os.name == "nt" else Path(tempfile.gettempdir())
        scratch.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix="work-contract-", dir=scratch)
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        cls.store = cls.directory / "shared"
        cls.base = HERE / "examples"
        cls.request = json.loads((cls.base / "contract.json").read_bytes())
        cls.cold = work.run(cls.request, cls.base, cls.store)
        if cls.cold["summary"] != {"executed": 1, "reused": 0, "held": 0}:
            raise AssertionError(cls.cold)
        cls.result_path = Path(cls.cold["tasks"][0]["result"])
        cls.value = json.loads(cls.result_path.read_bytes())["value"]

    def test_retained_grade_and_deadlines_are_unchanged_and_candidates_account_for_invalid_raw(self):
        v = self.value
        self.assertEqual((v["scheduled"], v["completed"], v["accepted"], v["correct"]), (8622, 8622, 4336, 4371))
        t = v["totals"]
        self.assertEqual(t["samples"], t["placeholders"] + t["raw_valid"] + t["raw_invalid"])
        self.assertEqual(t["raw_invalid"], t["candidate_valid"] + t["candidate_still_invalid"] + t["unresolved_raw_kept"])
        self.assertEqual(sum(r["applied"] for r in t["by_rule"].values()), len(v["candidates"]))
        self.assertEqual(sum(r["valid"] for r in t["by_rule"].values()), t["candidate_valid"])
        self.assertEqual(t["raw_invalid_retained_correct"], 0)
        self.assertGreater(t["candidate_valid"], 0)
        self.assertGreater(t["unresolved_raw_kept"], 0)  # comment-only bodies stay raw
        for c in v["candidates"]:
            self.assertFalse(c["retained_passed"])
            self.assertLessEqual(0, c["span"][0])
            self.assertLessEqual(c["span"][0], c["span"][1])
            self.assertLessEqual(c["span"][1], c["raw_chars"])
            self.assertEqual(c["candidate_chars"], c["span"][1] - c["span"][0])
        for flag in ("graded", "executed_generated_code", "fresh_evalplus_execution", "new_gpu_run", "authority_promoted"):
            self.assertIs(v[flag], False)
        self.assertTrue(v["retained_grade_unchanged"])
        for meta in v["grading_input"].values():
            self.assertNotEqual(meta["samples_sha256"], meta["retained_samples_sha256"])

    def test_materialized_candidates_match_the_pinned_grader_input_and_prepare_layout(self):
        import common
        import grade
        out = self.directory / "candidate-grade"
        new_map = task_contract.materialize(self.result_path, FIXTURE, out)
        retained = json.loads((FIXTURE / "grade" / "mapping.json").read_bytes())
        self.assertEqual(new_map["schema"], "second-run/grading-map@1")
        self.assertEqual({k: new_map[k] for k in ("source_sha256", "requests_sha256", "tasks_sha256")},
                         {k: retained[k] for k in ("source_sha256", "requests_sha256", "tasks_sha256")})
        by_index = {c["request_index"]: c for c in self.value["candidates"]}
        tasks, rows, _ = grade.bound_inputs(FIXTURE / "tasks.json", FIXTURE / "replay" / "requests.jsonl",
                                            FIXTURE / "detailed.json")
        by_id = {t["task_id"]: t for t in tasks["tasks"]}
        for dataset, meta in new_map["datasets"].items():
            self.assertEqual(meta["request_indices"], retained["datasets"][dataset]["request_indices"])
            self.assertEqual(common.sha(out / (dataset + ".jsonl")), meta["samples_sha256"])
            self.assertEqual(meta["samples_sha256"], self.value["grading_input"][dataset]["samples_sha256"])
            self.assertEqual(hashlib.md5((out / (dataset + "-reference.jsonl")).read_bytes()).hexdigest(),
                             meta["reference_md5"])
            retained_samples = common.jsonl(FIXTURE / "grade" / (dataset + ".jsonl"))
            samples = common.jsonl(out / (dataset + ".jsonl"))
            self.assertEqual(len(samples), len(retained_samples))
            for sample, original, n in zip(samples, retained_samples, meta["request_indices"]):
                self.assertEqual(sample["task_id"], original["task_id"])
                if n in by_index:
                    prompt = by_id[rows[n]["task_id"]]["prompt"]
                    self.assertTrue(sample["solution"].startswith(prompt))
                    self.assertIn(sample["solution"][len(prompt):], rows[n]["output_text"])
                else:
                    self.assertEqual(sample["solution"], original["solution"])
        lineage = json.loads((out / "contract-map.json").read_bytes())
        self.assertEqual(len(lineage["candidates"]), len(self.value["candidates"]))
        self.assertIs(lineage["graded"], False)
        with self.assertRaises(FileExistsError):
            task_contract.materialize(self.result_path, FIXTURE, out)

    def test_second_process_reuses_and_unknown_argument_is_refused(self):
        again = work.run(self.request, self.base, self.store)
        self.assertEqual(again["summary"], {"executed": 0, "reused": 1, "held": 0})
        self.assertEqual(again["tasks"][0]["key"], self.cold["tasks"][0]["key"])
        with self.assertRaises(ValueError):
            task_contract.prepare({"id": "x", "task_class": "output-contract", "source": str(FIXTURE),
                                   "sanitize": True}, HERE)
        with self.assertRaises(ValueError):
            task_contract.prepare({"id": "x", "task_class": "output-contract",
                                   "source": str(self.directory / "absent")}, HERE)


if __name__ == "__main__":
    unittest.main()
