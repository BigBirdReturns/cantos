#!/usr/bin/env python3
"""Stdlib unittest suite for diagnose.py. Run with: python -B test_diagnose.py"""
import json
import os
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import diagnose  # noqa: E402

FIXTURES = os.path.join(SCRIPT_DIR, "fixtures")
REFERENCE = os.path.join(SCRIPT_DIR, "reference", "hotaisle-2026-09.json")
# campaign/ root, two levels above shop-eval/diagnose/
CAMPAIGN_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))


def read_text(*parts):
    with open(os.path.join(CAMPAIGN_ROOT, *parts), "r", encoding="utf-8") as f:
        return f.read()


def read_json(*parts):
    with open(os.path.join(CAMPAIGN_ROOT, *parts), "r", encoding="utf-8") as f:
        return json.load(f)


class TestFixturesTriggerEveryRule(unittest.TestCase):
    """The bad-shop fixture set is built to fail every rule at least once."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        out_path = os.path.join(cls.tmpdir.name, "REPORT.md")
        argv = [
            "--counter", os.path.join(FIXTURES, "counter-record.json"),
            "--fingerprint", os.path.join(FIXTURES, "fingerprint.json"),
            "--bench", os.path.join(FIXTURES, "bench-cells"),
            "--reference", REFERENCE,
            "--out", out_path,
            "--json",
        ]
        rc = diagnose.main(argv)
        assert rc == 0
        cls.out_path = out_path
        cls.json_path = os.path.splitext(out_path)[0] + ".json"
        with open(out_path, "r", encoding="utf-8") as f:
            cls.report_md = f.read()
        with open(cls.json_path, "r", encoding="utf-8") as f:
            cls.report_json = json.load(f)

    def test_report_files_written(self):
        self.assertTrue(os.path.isfile(self.out_path))
        self.assertTrue(os.path.isfile(self.json_path))
        self.assertGreater(len(self.report_md), 0)

    def test_every_rule_id_present_in_report(self):
        for rid in diagnose.ALL_RULE_IDS:
            with self.subTest(rule=rid):
                self.assertIn(f"[{rid}]", self.report_md)

    def test_every_rule_triggers_wrong(self):
        statuses = {}
        for layer in self.report_json["layers"].values():
            for rid, res in layer["rules"].items():
                statuses[rid] = res["status"]
        missing_ids = [rid for rid in diagnose.ALL_RULE_IDS if rid not in statuses]
        self.assertEqual(missing_ids, [], f"rule ids absent from JSON report: {missing_ids}")
        not_wrong = {rid: st for rid, st in statuses.items() if st != "WRONG"}
        self.assertEqual(
            not_wrong, {},
            f"fixtures were built to fail every rule; these did not evaluate to WRONG: {not_wrong}",
        )

    def test_verdict_is_a_ratio_against_hot_aisle(self):
        self.assertIn("Hot Aisle", self.report_json["verdict"])
        self.assertIn("x Hot Aisle", self.report_json["verdict"])

    def test_top_three_ranked_by_weight_and_nonempty(self):
        top3 = self.report_json["top_three"]
        self.assertEqual(len(top3), 3)
        weights = [diagnose.RULE_WEIGHT[t["rule_id"]] for t in top3]
        self.assertEqual(weights, sorted(weights, reverse=True))
        # PRICE-02 has the highest weight and is triggered by the fixtures -> must lead.
        self.assertEqual(top3[0]["rule_id"], "PRICE-02")

    def test_provenance_block_present(self):
        self.assertIn("## Provenance", self.report_md)
        prov = self.report_json["provenance"]
        self.assertIn("counter-record.json", prov["counter_input"])
        self.assertIn("fingerprint.json", prov["fingerprint_input"])
        self.assertIn("bench-cells", prov["bench_input"])
        self.assertIn("hotaisle-2026-09.json", prov["reference_input"])


class TestAllInputsMissing(unittest.TestCase):
    """Every input is optional; a fully-empty run must still produce a usable report."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        out_path = os.path.join(cls.tmpdir.name, "REPORT.md")
        # No --counter, --fingerprint, --bench. --reference left at its shipped default.
        rc = diagnose.main(["--out", out_path, "--json"])
        assert rc == 0
        cls.out_path = out_path
        cls.json_path = os.path.splitext(out_path)[0] + ".json"
        with open(out_path, "r", encoding="utf-8") as f:
            cls.report_md = f.read()
        with open(cls.json_path, "r", encoding="utf-8") as f:
            cls.report_json = json.load(f)

    def test_report_written_without_crashing(self):
        self.assertTrue(os.path.isfile(self.out_path))
        self.assertGreater(len(self.report_md), 0)

    def test_verdict_says_insufficient_data(self):
        self.assertIn("Insufficient data", self.report_json["verdict"])

    def test_every_layer_explains_what_to_run(self):
        for layer in self.report_json["layers"].values():
            for res in layer["rules"].values():
                self.assertEqual(res["status"], "MISSING")
        # every layer's "not evaluated" note must name a concrete command to run
        self.assertIn("counter_record.py validate", self.report_md)
        self.assertIn("fingerprint.sh", self.report_md)
        self.assertIn("engine_table.cjs", self.report_md)

    def test_no_top_three_when_nothing_evaluated(self):
        self.assertEqual(self.report_json["top_three"], [])

    def test_default_reference_still_used(self):
        self.assertIn("hotaisle-2026-09.json", self.report_json["provenance"]["reference_input"])
        self.assertIn("assembled_at", self.report_json["provenance"]["reference_input"])


class TestRawCellsAggregation(unittest.TestCase):
    """The raw cell-*.json path (no engine table) is exercised directly."""

    def test_raw_cells_dir_parses_and_has_no_grading(self):
        bench, err = diagnose.load_bench(os.path.join(FIXTURES, "bench-cells-rawonly"))
        self.assertIsNone(err)
        self.assertEqual(bench["kind"], "raw_cells")
        by_cell = {c["cell"]: c for c in bench["cells"]}
        self.assertIn("cell-c8", by_cell)
        self.assertIn("cell-c32", by_cell)
        self.assertEqual(by_cell["cell-c8"]["completed"], 2)
        self.assertEqual(by_cell["cell-c8"]["failed"], 1)
        self.assertEqual(by_cell["cell-c8"]["attempted"], 3)
        self.assertEqual(by_cell["cell-c32"]["completed"], 3)
        self.assertEqual(by_cell["cell-c32"]["failed"], 0)
        # Raw cells carry no correctness grading.
        self.assertIsNone(by_cell["cell-c8"]["accepted_pct"])
        self.assertIsNone(by_cell["cell-c8"]["cost_per_1k"])
        # TTFT percentiles are directly present in each raw cell and get averaged.
        self.assertAlmostEqual(by_cell["cell-c8"]["ttft_p50_ms"], 1000.0)

    def test_table_json_takes_precedence_when_present(self):
        bench, err = diagnose.load_bench(os.path.join(FIXTURES, "bench-cells"))
        self.assertIsNone(err)
        self.assertEqual(bench["kind"], "engine_table")
        cells_names = {c["cell"] for c in bench["cells"]}
        self.assertEqual(cells_names, {"cell-c8", "cell-c32"})


class TestReferenceBundleMatchesSourceFiles(unittest.TestCase):
    """Every re-readable number in the reference bundle is checked against the exact
    repo file it cites, so the bundle cannot silently drift from the results it quotes.
    """

    @classmethod
    def setUpClass(cls):
        with open(REFERENCE, "r", encoding="utf-8") as f:
            cls.ref = json.load(f)

    def test_run3_a_t0_ttft_and_accepted_present_in_summary(self):
        text = read_text("results", "RUN3-HOTAISLE-SUMMARY.md")
        r = self.ref["run3_a_t0"]
        self.assertIn("53 / 155 / 571", text)
        self.assertEqual(r["ttft_p50_ms"], 53)
        self.assertEqual(r["ttft_p95_ms"], 155)
        self.assertEqual(r["ttft_p99_ms"], 571)
        self.assertIn("4,336 (50.3 %)", text)
        self.assertEqual(r["accepted"], 4336)
        self.assertEqual(r["accepted_pct"], 50.3)
        self.assertIn("**$0.72**", text)
        self.assertEqual(r["cost_per_1k_accepted_own_window_usd"], 0.72)

    def test_run3_whole_seat_present_in_summary(self):
        text = read_text("results", "RUN3-HOTAISLE-SUMMARY.md")
        r = self.ref["run3_whole_seat"]
        self.assertIn("2.73 h, $8.15, 9,086 accepted", text)
        self.assertEqual(r["duration_hours"], 2.73)
        self.assertEqual(r["cost_usd"], 8.15)
        self.assertEqual(r["accepted"], 9086)
        self.assertIn("$0.90 per 1k accepted", text)
        self.assertEqual(r["cost_per_1k_accepted_usd"], 0.90)

    def test_run3_do_h100_present_in_results(self):
        text = read_text("results", "RUN3-RESULTS.md")
        r = self.ref["run3_do_h100"]
        self.assertIn("**$1.20**", text)
        self.assertEqual(r["cost_per_1k_accepted_whole_run_usd"], 1.20)
        self.assertIn("35 / 76", text)
        self.assertEqual(r["ttft_p50_ms"], 35)
        self.assertEqual(r["ttft_p95_ms"], 76)

    def test_run1_best_cell_matches_engine_table_exactly(self):
        data = read_json("results", "run1-engine", "hotaisle-mi300x.ttft1000.json")
        c64 = next(c for c in data["cells"] if c["cell"] == "cell-c64")
        r = self.ref["run1_best_cell"]
        self.assertEqual(c64["cost_per_1k"], r["cost_per_1k_usd"])
        self.assertEqual(c64["accepted_pct"], r["accepted_pct"])
        self.assertEqual(data["gates"]["ttft_ms"], r["gate_ttft_p95_ms"])

    def test_stack_matches_env_normalized(self):
        data = read_json("results", "hotaisle-mi300x", "env.normalized.json")
        r = self.ref["stack"]
        self.assertEqual(data["driver_or_rocm"], r["driver_or_rocm_version"])
        self.assertEqual(data["kernel"], r["kernel"])
        self.assertEqual(data["gpu"], r["gpu_model"])
        self.assertEqual(data["vllm_version"], r["vllm_version"])

    def test_billing_matches_identity_json(self):
        data = read_json("identity.json")
        r = self.ref["billing"]
        self.assertEqual(data["arms"]["hotaisle-mi300x"]["billing"], r["granularity"])
        self.assertEqual(data["arms"]["hotaisle-mi300x"]["list_rate"], r["list_rate_usd_per_gpu_hour"])

    def test_proof_manifest_and_disclosure_files_exist(self):
        self.assertTrue(os.path.isfile(os.path.join(CAMPAIGN_ROOT, "results", "hotaisle-mi300x", "MANIFEST.sha256")))
        self.assertTrue(os.path.isfile(os.path.join(CAMPAIGN_ROOT, "DISCLOSURES.md")))

    def test_unobserved_fields_are_literally_unobserved(self):
        hw = self.ref["hardware_lifecycle"]
        for key in ("pcie_gen", "pcie_width", "vbios", "firmware", "ras_errors_correctable",
                    "ras_errors_uncorrectable", "idle_power_w", "sustained_60s_throttle"):
            self.assertEqual(hw[key], "unobserved")
        tenant = self.ref["tenant_hygiene"]
        for key in ("acs_enabled", "hugepages_enabled", "numa_pinning"):
            self.assertEqual(tenant[key], "unobserved")




class TestSeamWithRealCounterAndProbeShapes(unittest.TestCase):
    """The counter lane's raw record and the probe lane's fingerprint are what a real run
    produces; diagnose.py must consume them through adapt.py without the rule-facing fixtures."""

    SHOP_EVAL = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
    COUNTER = os.path.join(SHOP_EVAL, "counter", "records", "hotaisle-2026-09.json")
    BAD_PROBE = os.path.join(SHOP_EVAL, "probe", "fixtures", "synthetic-bad-shop.fingerprint.json")
    HA_PROBE = os.path.join(SHOP_EVAL, "probe", "fixtures", "hotaisle-2026-09.fingerprint.json")

    def _run(self, fingerprint):
        tmp = tempfile.mkdtemp()
        out = os.path.join(tmp, "REPORT.md")
        rc = diagnose.main(["--counter", self.COUNTER, "--fingerprint", fingerprint,
                            "--reference", REFERENCE, "--out", out, "--json"])
        self.assertEqual(rc, 0)
        with open(out, encoding="utf-8") as f:
            md = f.read()
        with open(os.path.splitext(out)[0] + ".json", encoding="utf-8") as f:
            js = json.load(f)
        return md, js

    def _status(self, js, rule_id):
        layers = js.get("layers") or []
        if isinstance(layers, dict):
            layers = list(layers.values())
        for layer in layers:
            rules = layer.get("rules") if isinstance(layer, dict) else None
            if isinstance(rules, dict) and rule_id in rules:
                return str(rules[rule_id].get("status", "")).lower()
            if isinstance(rules, list):
                for r in rules:
                    if r.get("rule_id") == rule_id or r.get("id") == rule_id:
                        return str(r.get("status", "")).lower()
        return None

    def test_raw_counter_record_is_scored_and_read(self):
        md, js = self._run(self.BAD_PROBE)
        self.assertIn("counter score 80", md)
        self.assertEqual(self._status(js, "CNT-01"), "right")
        self.assertEqual(self._status(js, "PRICE-01"), "right")   # per-minute from billing_quantum text
        self.assertEqual(self._status(js, "FLEET-01"), "right")   # 122 s to SSH, carried from the counter
        self.assertEqual(self._status(js, "PRICE-03"), "right")   # listed available and provisioned agree

    def test_probe_fingerprint_triggers_node_rules(self):
        md, js = self._run(self.BAD_PROBE)
        for rule_id in ("HW-01", "HW-03", "PWR-01", "STK-01"):
            self.assertEqual(self._status(js, rule_id), "wrong", rule_id)
        self.assertEqual(self._status(js, "TEN-02"), "right")     # numa_nodes "1" coerced to 1
        self.assertEqual(self._status(js, "HW-02"), "missing")    # firmware age is not node-observable
        self.assertEqual(self._status(js, "STK-02"), "missing")   # backend not captured by the probe yet
        self.assertEqual(self._status(js, "HEALTH-02"), "right")  # idle 45 W vs loaded ~291 W

    def test_all_unobserved_probe_fixture_does_not_crash(self):
        md, js = self._run(self.HA_PROBE)
        self.assertIn("counter score 80", md)
        for rule_id in ("HW-01", "HW-03", "PWR-01", "TEN-01", "TEN-02"):
            self.assertEqual(self._status(js, rule_id), "missing", rule_id)
        self.assertEqual(self._status(js, "STK-01"), "right")  # ROCm 7.2.4 is the reference stack


if __name__ == "__main__":
    unittest.main()
