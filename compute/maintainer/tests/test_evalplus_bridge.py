"""Test the public grading join, using synthetic grader output, never executing code."""
import argparse
import contextlib
import hashlib
import io
import json
import unittest
from pathlib import Path

import test_instrument as fixtures
import evalplus_bridge as bridge
import maintainer
from common import load, sha256_file


class EvalPlusBinding(unittest.TestCase):
    setUp = fixtures.Instrument.setUp
    tearDown = fixtures.Instrument.tearDown
    save = fixtures.Instrument.save
    run_pair = fixtures.Instrument.run_pair

    def prepared(self):
        reference = self.root / "reference.jsonl"
        reference.write_text(json.dumps({"task_id": "case", "prompt": "def f():\n", "canonical_solution": "    return 2\n"}) + "\n")
        normalizer = Path(maintainer.__file__).parent / "normalize.py"
        self.work["cases"][0]["expect"] = {
            "kind": "external", "grader": {"name": "EvalPlus", "revision": "0.3.1",
            "artifact_sha256": "a" * 64, "reference_sha256": sha256_file(reference),
            "normalizer_sha256": sha256_file(normalizer),
            "criterion": "humanevalplus-v0.1.10-base-and-plus-chat-complete-code-v1"}}
        self.a.mode = self.b.mode = "external"
        self.run_pair()
        run = self.root / "pair/baseline/run.json"
        prepared = self.root / "prepared"
        args = argparse.Namespace(run=str(run), reference=str(reference), normalizer=str(normalizer),
                                  instrument=str(Path(maintainer.__file__).parent), out=str(prepared))
        with contextlib.redirect_stdout(io.StringIO()):
            bridge.prepare(args)
        samples = [json.loads(x) for x in (prepared / "humaneval.jsonl").read_text().splitlines()]
        results = {"hash": hashlib.md5(reference.read_bytes()).hexdigest(), "eval": {"case": [
            {"task_id": x["task_id"], "solution": x["solution"], "base_status": "pass", "plus_status": "pass"} for x in samples]}}
        path = self.root / "fixture-evalplus-results.json"
        path.write_text(json.dumps(results))
        log = self.root / "fixture-evalplus.log"
        log.write_text("Synthetic join test. No code was executed and this is not a benchmark result.\n")
        return argparse.Namespace(run=str(run), prepared=str(prepared), results=str(path), log=str(log),
                                  instrument=str(Path(maintainer.__file__).parent), out=str(self.root / "bound"))

    def test_complete_public_prepare_bind_join(self):
        args = self.prepared()
        with contextlib.redirect_stdout(io.StringIO()):
            bridge.bind(args)
        grade = maintainer.validate_grades(self.root / "bound/grades.json", args.run)
        self.assertEqual(sum(x["accepted"] for x in grade["results"]), 2)
        self.assertEqual(grade["grader"]["artifact_sha256"], "a" * 64)

    def test_changed_normalized_solution_fails_even_with_updated_intermediate_hashes(self):
        args = self.prepared()
        prepared = Path(args.prepared)
        rows = [json.loads(x) for x in (prepared / "humaneval.jsonl").read_text().splitlines()]
        rows[0]["solution"] = "def f():\n    return 999\n"
        (prepared / "humaneval.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))
        mapping = load(prepared / "mapping.json")
        mapping[0]["solution_sha256"] = hashlib.sha256(rows[0]["solution"].encode()).hexdigest()
        (prepared / "mapping.json").write_text(json.dumps(mapping))
        meta = load(prepared / "prepared.json")
        meta["samples_sha256"] = sha256_file(prepared / "humaneval.jsonl")
        meta["mapping_sha256"] = sha256_file(prepared / "mapping.json")
        (prepared / "prepared.json").write_text(json.dumps(meta))
        result = load(args.results)
        result["eval"]["case"][0]["solution"] = rows[0]["solution"]
        Path(args.results).write_text(json.dumps(result))
        with self.assertRaisesRegex(ValueError, "normalized raw response"):
            bridge.bind(args)

    def test_missing_evalplus_observation_fails_closed(self):
        args = self.prepared()
        result = load(args.results)
        result["eval"]["case"].pop()
        Path(args.results).write_text(json.dumps(result))
        with self.assertRaisesRegex(ValueError, "coverage"):
            bridge.bind(args)

    def test_observed_grader_image_mismatch_fails_closed(self):
        args = self.prepared()
        (Path(args.prepared) / "grader-image.json").write_text(json.dumps([{"Id": "sha256:" + "b" * 64}]))
        with self.assertRaisesRegex(ValueError, "observed grader image"):
            bridge.bind(args)


if __name__ == "__main__":
    unittest.main()
