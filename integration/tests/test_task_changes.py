"""Native change-owner checks over committed, explicitly synthetic evidence."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import task_changes


ROOT = task_changes.ROOT
DEMO = ROOT / "hot-aisle/data/demo/record.json"
HISTORY = ROOT / "research-desk/examples/worked-history.json"

# No benchmark is started. Native owners bind an explicitly synthetic pass mask
# to the retained synthetic rows, then build and verify a quality-gated record.
QUALITY_FIXTURE = r"""
const fs = require('node:fs');
const path = require('node:path');
const [root, source, output] = process.argv.slice(1);
const engine = require(path.join(root, 'hot-aisle/runner/lib/engine.cjs'));
const record = require(path.join(root, 'hot-aisle/runner/lib/record.cjs'));
const { Jobs } = require(path.join(root, 'hot-aisle/runner/lib/jobs.cjs'));
const { Store } = require(path.join(root, 'hot-aisle/runner/lib/store.cjs'));
const original = JSON.parse(fs.readFileSync(source, 'utf8'));
if (!original.synthetic) throw Error('This test accepts only synthetic fixture rows');
const HA = engine.load();
const jobs = new Jobs(new Store(path.join(path.dirname(output), 'native-plan-state')));
const job = jobs.plan({ ...original.declared.plan,
  gates: { ...original.declared.plan.gates, quality: true } });
job.trials = original.observed.trials.map(trial => {
  const run = HA.restoreRun(trial.normalized);
  const sidecar = { schema: 'hot-aisle/request-evaluation@1',
    source_sha256: run.source.sha256, record_index: run.source.record_index,
    passed: run.rows.map((row, index) => row.success && index % 2 === 0),
    evaluator: 'synthetic-change-routing-fixture',
    criterion_id: 'synthetic-alternating-success-mask-v1' };
  return { ...trial, status: 'completed', normalized: HA.attachQuality(run, sidecar) };
});
job.disposition = original.observed.disposition;
const result = record.build(job);
const verification = record.verify(result);
if (!verification.verified || !result.synthetic) throw Error(JSON.stringify(verification));
fs.writeFileSync(output, JSON.stringify(result) + '\n');
process.stdout.write(JSON.stringify({ verified: verification.verified,
  synthetic: result.synthetic, quality_gate: result.declared.plan.gates.quality,
  approval: result.declared.approval, benchmark_started: false }) + '\n');
"""


class ChangeTasks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = Path("S:/Scratch/Runs") if os.name == "nt" else Path(tempfile.gettempdir())
        scratch.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix="change-owner-tests-", dir=scratch)
        cls.base = Path(cls.temporary.name)
        cls.demo_bytes = DEMO.read_bytes()
        cls.demo = json.loads(cls.demo_bytes)
        cls.history_bytes = HISTORY.read_bytes()
        cls.history = json.loads(cls.history_bytes)
        cls.quality = cls.base / "synthetic-quality-record.json"
        built = subprocess.run(["node", "-e", QUALITY_FIXTURE, str(ROOT), str(DEMO), str(cls.quality)],
                               capture_output=True, text=True, encoding="utf-8", check=True)
        cls.quality_build = json.loads(built.stdout)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def record_task(self, change, source=DEMO):
        return {"id": "change-test", "task_class": "record-change",
                "source": str(source), "change": change}

    def execute(self, task):
        return task_changes.prepare(task, ROOT)["execute"]()

    def test_price_reuses_performance_without_execution(self):
        task = self.record_task({"price": {"rate": 1.68}})
        output = self.execute(task)
        result = output["result"]
        self.assertTrue(output["synthetic"])
        self.assertEqual(0, result["summary"]["requires_measurement"])
        self.assertIsNone(result["minimal_plan"])
        self.assertFalse(result["reevaluate"])
        self.assertIn(("performance", "stands"),
                      [(c["subject"], c["status"]) for c in result["conclusions"]])
        original = {c["concurrency"]: c for c in self.demo["derived"]["cells"]}
        for cell in result["scenario"]["cells"]:
            retained = original[cell["concurrency"]]
            self.assertEqual(retained["aggregate"]["rate"], cell["accepted_per_s"])
            self.assertAlmostEqual(retained["cost"]["costPer1000"] * 1.68 /
                                   self.demo["declared"]["price"]["rate"], cell["cost_per_1000"])
        self.assertEqual(output, self.execute(task), "same retained evidence gives identical output")
        self.assertEqual(self.demo_bytes, DEMO.read_bytes())

    def test_runtime_change_proposes_only_required_full_identity_rerun(self):
        result = self.execute(self.record_task({"runtime": {"runtime_digest": "synthetic:corrected-runtime"}}))["result"]
        plan = self.demo["declared"]["plan"]
        self.assertTrue(result["summary"]["superseded"])
        self.assertEqual(plan["concurrency"], result["minimal_plan"]["concurrency"])
        self.assertEqual(plan["repeats"], result["minimal_plan"]["repeats"])
        self.assertEqual(len(plan["concurrency"]) * plan["repeats"], result["summary"]["requires_measurement"])
        self.assertEqual("synthetic:corrected-runtime", result["minimal_plan"]["identity"]["runtime_digest"])
        self.assertIn(self.demo["id"], result["minimal_plan"]["note"])
        self.assertEqual(self.demo_bytes, DEMO.read_bytes())

    def test_gate_change_recomputes_retained_request_rows(self):
        result = self.execute(self.record_task({"gates": {"ttft": 150}}))["result"]
        self.assertEqual(0, result["summary"]["requires_measurement"])
        self.assertIsNone(result["minimal_plan"])
        self.assertIn(("acceptance", "recomputed"),
                      [(c["subject"], c["status"]) for c in result["conclusions"]])
        old_rates = {c["concurrency"]: c["aggregate"]["rate"] for c in self.demo["derived"]["cells"]}
        self.assertTrue(any(c["accepted_per_s"] < old_rates[c["concurrency"]]
                            for c in result["scenario"]["cells"]))
        self.assertTrue(all(c["unit"] == "latency-qualified requests" for c in result["scenario"]["cells"]))
        self.assertEqual(self.demo_bytes, DEMO.read_bytes())

    def test_quality_gated_evaluator_correction_requests_reassessment_not_inference(self):
        self.assertEqual({"verified": True, "synthetic": True, "quality_gate": True,
                          "approval": None, "benchmark_started": False}, self.quality_build)
        original = self.quality.read_bytes()
        output = self.execute(self.record_task({"evaluator": {"criterion_id": "corrected-synthetic-rule"}}, self.quality))
        result = output["result"]
        self.assertTrue(output["synthetic"])
        self.assertTrue(result["reevaluate"])
        self.assertEqual(0, result["summary"]["requires_measurement"])
        self.assertIsNone(result["minimal_plan"])
        self.assertIn(("acceptance", "requires_reevaluation"),
                      [(c["subject"], c["status"]) for c in result["conclusions"]])
        self.assertEqual(original, self.quality.read_bytes())

    def test_evaluator_change_leaves_ungated_acceptance_alone(self):
        self.assertFalse(self.demo["declared"]["plan"]["gates"]["quality"])
        result = self.execute(self.record_task({"evaluator": {"criterion_id": "corrected-synthetic-rule"}}))["result"]
        self.assertFalse(result["reevaluate"])
        self.assertEqual([("acceptance", "stands")],
                         [(c["subject"], c["status"]) for c in result["conclusions"]])

    def test_source_correction_preserves_history_and_invalidates_dependents(self):
        task = {"task_class": "source-correction", "source": str(HISTORY),
                "change": {"record_id": "public-index", "patch": {
                    "summary": "Corrected supplied observation; dependent conclusions need renewed review."}}}
        output = self.execute(task)
        self.assertTrue(output["historical_reports_preserved"])
        self.assertEqual(output["before_revision"] + 1, output["after_revision"])
        self.assertTrue(output["affected"])
        for affected in output["affected"]:
            self.assertFalse(affected["after"]["dependency"]["current"])
            self.assertFalse(affected["after"]["review"]["ready"])
            self.assertTrue(any("public-index" in b for b in affected["after"]["dependency"]["blockers"]))
        original_events = self.history["workspace"]["events"]
        successor_events = output["packet"]["workspace"]["events"]
        self.assertEqual(original_events, successor_events[:-1])
        self.assertEqual("record", successor_events[-1]["type"], "no review or freeze was invented")
        self.assertEqual(original_events[-1]["at"], output["event_timestamp"])
        self.assertIn("not a fresh observation time", output["timestamp_basis"])
        self.assertEqual(output, self.execute(task))
        self.assertEqual(self.history_bytes, HISTORY.read_bytes())

    def test_unknown_classes_fields_and_typos_fail_closed(self):
        tasks = [
            {**self.record_task({"price": {"rate": 1.68}}), "task_class": "unknown-change"},
            {**self.record_task({"price": {"rate": 1.68}}), "customer": "invented-dispatch-key"},
            self.record_task({"source_correction": {"reason": "unsupported class"}}),
            self.record_task({"runtime": {"runtime_digset": "typo"}}),
            self.record_task({"price": {"raet": 1.68}}),
            {"task_class": "source-correction", "source": str(HISTORY),
             "change": {"record_id": "public-index", "patch": {"revision": 99}}},
        ]
        for task in tasks:
            with self.subTest(task=task):
                with self.assertRaisesRegex(ValueError, "[Uu]nsupported"):
                    task_changes.prepare(task, ROOT)

    def test_caller_metadata_does_not_change_the_native_operation(self):
        task = self.record_task({"price": {"rate": 1.68}})
        prepared = task_changes.prepare(task, ROOT)
        other = copy.deepcopy(task)
        other.update(id="different-request", actor="different-caller")
        repeated = task_changes.prepare(other, ROOT)
        self.assertEqual(prepared["parameters"], repeated["parameters"])
        self.assertEqual(prepared["inputs"], repeated["inputs"])
        self.assertEqual(prepared["execute"](), repeated["execute"]())


if __name__ == "__main__":
    unittest.main(verbosity=2)
