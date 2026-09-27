"""run-diagnose through the actual owners, with all mutations confined to scratch copies."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import task_diagnose
import work

FIXTURE = ROOT / "hot-aisle" / "campaign" / "results" / "run3-scored-a-t0"
CLASSES = ("correct", "syntax_valid_grade_failed", "syntax_invalid",
           "never_sent_placeholder", "not_requested_placeholder")


class DiagnoseHandoff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = Path("S:/Scratch/Temp") if os.name == "nt" else Path(tempfile.gettempdir())
        cls.temporary = tempfile.TemporaryDirectory(prefix="work-diagnose-", dir=scratch)
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        cls.store = cls.directory / "shared"
        cls.base = HERE / "examples"
        cls.request = json.loads((cls.base / "diagnose.json").read_bytes())
        cls.cold = work.run(cls.request, cls.base, cls.store)
        if cls.cold["summary"] != {"executed": 1, "reused": 0, "held": 0}:
            raise AssertionError(cls.cold)
        cls.value = json.loads(Path(cls.cold["tasks"][0]["result"]).read_bytes())["value"]

    def test_diagnosis_accounts_for_the_retained_recomputation(self):
        value = self.value
        self.assertEqual((value["scheduled"], value["completed"], value["accepted"]), (8622, 8622, 4336))
        late = value["late_partition"]
        self.assertEqual(value["correct"] - value["accepted"],
                         late["correct_first_token_late"] + late["correct_completion_late_only"])
        self.assertEqual(sum(late["categories"].values()) + late["unmeasurable_send_ts"],
                         late["correct_first_token_late"])
        self.assertEqual(sum(b["late"] for b in late["bins"]), late["correct_first_token_late"])
        self.assertEqual(len(late["bins"]), 12)
        totals = value["solutions"]["totals"]
        self.assertEqual(totals["samples"], sum(totals[name] for name in CLASSES))
        self.assertEqual(totals["samples"], value["scheduled"])
        self.assertEqual(totals["correct"], value["correct"])
        self.assertEqual(sum(value["solutions"]["syntax_error_families"].values()), totals["syntax_invalid"])
        for family in value["solutions"]["syntax_error_families"]:
            self.assertNotRegex(family, r" on line \d+$")
        self.assertTrue(value["solutions"]["all_solutions_equal_frozen_prompt_plus_raw_output"])
        self.assertEqual(value["solutions"]["anomalies"], [])
        self.assertFalse(value["synthetic"])
        for flag in ("executed_generated_code", "sanitized_or_repaired", "fresh_evalplus_execution",
                     "new_gpu_run", "authority_promoted"):
            self.assertIs(value[flag], False)
        self.assertEqual(value["acceptance_contract"]["criterion_id"],
                         json.loads((FIXTURE / "grade" / "evaluation.json").read_bytes())["criterion_id"])

    def test_relocated_copy_reuses_and_altered_output_is_held(self):
        copy = self.directory / "relocated"
        shutil.copytree(FIXTURE, copy, ignore=shutil.ignore_patterns("posthoc-sanitized", "ledger"))
        request = {"tasks": [{"id": "elsewhere", "actor": "another-operator",
                              "task_class": "run-diagnose", "source": str(copy)}]}
        moved = work.run(request, self.base, self.store)
        self.assertEqual(moved["summary"], {"executed": 0, "reused": 1, "held": 0})
        self.assertEqual(moved["tasks"][0]["key"], self.cold["tasks"][0]["key"])
        # Appending a comment to one delivered output changes only requests.jsonl. The
        # retained detailed.json still names the original request bytes, so the campaign
        # owner refuses before any classification; nothing is diagnosed from altered evidence.
        requests = copy / "replay" / "requests.jsonl"
        lines = requests.read_bytes().splitlines(keepends=True)
        row = json.loads(lines[0])
        row["output_text"] += "\n# altered after the run\n"
        lines[0] = (json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
        requests.write_bytes(b"".join(lines))
        altered = work.run(request, self.base, self.store)
        self.assertEqual(altered["summary"], {"executed": 0, "reused": 0, "held": 1})
        self.assertEqual(altered["tasks"][0]["status"], "held")

    def test_unknown_argument_is_refused_before_reading_evidence(self):
        with self.assertRaises(ValueError):
            task_diagnose.prepare({"id": "x", "task_class": "run-diagnose", "source": str(FIXTURE),
                                   "repair": True}, HERE)
        with self.assertRaises(ValueError):
            task_diagnose.prepare({"id": "x", "task_class": "run-diagnose",
                                   "source": str(self.directory / "absent")}, HERE)


if __name__ == "__main__":
    unittest.main()
