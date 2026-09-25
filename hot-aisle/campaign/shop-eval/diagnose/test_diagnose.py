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
import adapt  # noqa: E402

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

    def test_rules_distinguish_failures_from_signals_and_unknowns(self):
        statuses = {}
        for layer in self.report_json["layers"].values():
            for rid, res in layer["rules"].items():
                statuses[rid] = res["status"]
        missing_ids = [rid for rid in diagnose.ALL_RULE_IDS if rid not in statuses]
        self.assertEqual(missing_ids, [], f"rule ids absent from JSON report: {missing_ids}")
        self.assertEqual(statuses["CNT-01"], "SIGNAL")
        self.assertEqual(statuses["PRICE-02"], "UNKNOWN")  # no scope-bound table hash
        self.assertEqual(statuses["PWR-01"], "SIGNAL")
        self.assertEqual(statuses["HW-01"], "SIGNAL")
        self.assertEqual(statuses["HW-03"], "SIGNAL")
        self.assertEqual(statuses["STK-01"], "SIGNAL")
        self.assertEqual(statuses["STK-02"], "UNKNOWN")
        self.assertEqual(statuses["TEN-01"], "SIGNAL")
        self.assertEqual(statuses["TEN-02"], "SIGNAL")
        self.assertTrue(any(st == "WRONG" for st in statuses.values()))

    def test_verdict_refuses_ratio_without_scope_identity(self):
        self.assertIn("Hot Aisle", self.report_json["verdict"])
        self.assertIn("Not comparable", self.report_json["verdict"])
        self.assertNotIn("0.10x", self.report_json["verdict"])

    def test_top_three_ranked_by_weight_and_nonempty(self):
        top3 = self.report_json["top_three"]
        self.assertEqual(len(top3), 3)
        weights = [diagnose.RULE_WEIGHT[t["rule_id"]] for t in top3]
        self.assertEqual(weights, sorted(weights, reverse=True))
        self.assertNotEqual(top3[0]["rule_id"], "PRICE-02")
        for finding in top3:
            self.assertIn("competing_causes", finding["diagnostic"])
            self.assertIn("discriminating_test", finding["diagnostic"])
            self.assertIn("rollback", finding["diagnostic"])

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
                self.assertEqual(res["status"], "UNKNOWN")
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
        self.assertEqual(data["gates"]["ttft_ms"], r["gate_ttft_ms"])

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
        self.assertIn("counter composite score", md)
        self.assertEqual(self._status(js, "CNT-01"), "signal")
        self.assertEqual(self._status(js, "PRICE-01"), "right")   # per-minute from billing_quantum text
        self.assertEqual(self._status(js, "FLEET-01"), "right")   # 122 s to SSH, carried from the counter
        self.assertEqual(self._status(js, "PRICE-03"), "unknown") # listing/create pairing is not explicitly linked

    def test_probe_fingerprint_triggers_node_rules(self):
        md, js = self._run(self.BAD_PROBE)
        for rule_id in ("HW-01", "HW-03", "PWR-01"):
            self.assertEqual(self._status(js, rule_id), "signal", rule_id)
        self.assertEqual(self._status(js, "STK-01"), "not_comparable")  # NVIDIA vs AMD version labels
        self.assertEqual(self._status(js, "TEN-02"), "right")     # single NUMA node; pinning not applicable
        self.assertEqual(self._status(js, "HW-02"), "unknown")    # firmware age is not node-observable
        self.assertEqual(self._status(js, "STK-02"), "unknown")   # backend not captured by the probe yet
        self.assertEqual(self._status(js, "HEALTH-02"), "unknown") # ambient reading is not a verified idle baseline

    def test_all_unobserved_probe_fixture_does_not_crash(self):
        md, js = self._run(self.HA_PROBE)
        self.assertIn("counter composite score", md)
        for rule_id in ("HW-01", "HW-03", "PWR-01", "TEN-01", "TEN-02"):
            self.assertEqual(self._status(js, rule_id), "unknown", rule_id)
        self.assertEqual(self._status(js, "STK-01"), "right")  # ROCm version on same-vendor MI300X

    def test_ambient_power_never_counts_as_idle_evidence(self):
        fp = {"gpus": [{"idle_power_w": 237, "idle_verified": False,
                        "sample_context": "ambient", "sustained_60s": {"power_w_start": 290}}]}
        self.assertEqual(diagnose.rule_health_02(None, fp, None, {})["status"], "UNKNOWN")

    def test_probe_v3_unobserved_load_stays_unknown(self):
        with open(self.HA_PROBE, encoding="utf-8") as f:
            raw = json.load(f)
        adapted = diagnose.adapt_fingerprint(raw)
        self.assertIn(adapted["_adapted_from"], adapt.PROBE_SCHEMAS)
        self.assertTrue(adapted["gpus"])
        self.assertIsNone(adapted["gpus"][0]["sustained_load"])
        self.assertEqual(diagnose.rule_pwr_01(None, adapted, None, {})["status"], "UNKNOWN")

    def test_power_signal_reports_verified_sample_duration(self):
        sample = adapt._sustained({"status": "pass", "duration_s": 30, "samples": [
            {"sample": "2000, 1000, 60, 250 W, Not Active"},
            {"sample": "1500, 1000, 70, 250 W, Not Active"},
        ]}, "nvidia")
        result = diagnose.rule_pwr_01(None, {"gpus": [{"sustained_load": sample}]}, None, {})
        self.assertEqual(result["status"], "SIGNAL")
        self.assertIn("over 30s", result["observation"])
        self.assertNotIn("60s", result["observation"])

    def test_mixed_sku_listing_and_create_cannot_prove_availability_agreement(self):
        with open(self.COUNTER, encoding="utf-8") as f:
            record = json.load(f)
        record["availability_honesty"]["ledger_attempts"] = [
            {"ts": "2026-09-25T10:00:00Z", "sku": "sku-a", "region": "region-a",
             "method": "tui-provision-list", "outcome": "available", "provisioned": False,
             "snapshot_id": "listing-a"},
            {"ts": "2026-09-25T10:01:00Z", "sku": "sku-b", "region": "region-a",
             "method": "tui-provision", "outcome": "available", "provisioned": True,
             "listing_snapshot_id": "listing-a"},
        ]
        counter = diagnose.adapt_counter(record)
        self.assertIsNone(counter["provisioning"]["listed_available"])
        self.assertIsNone(counter["provisioning"]["provisioned"])
        self.assertEqual(diagnose.rule_price_03(None, {"provisioning": counter["provisioning"]}, None, {})["status"], "UNKNOWN")
        record["availability_honesty"]["ledger_attempts"][1].update({"sku": "sku-a", "listing_snapshot_id": "listing-a"})
        paired = diagnose.adapt_counter(record)
        self.assertEqual(paired["provisioning"]["matched_availability_attempts"], 1)
        self.assertEqual(diagnose.rule_price_03(None, {"provisioning": paired["provisioning"]}, None, {})["status"], "RIGHT")


class TestComparisonGate(unittest.TestCase):
    def test_retained_run1_table_cannot_be_compared_to_run3_or_auto_scored(self):
        retained = os.path.join(CAMPAIGN_ROOT, "results", "run1-engine", "hotaisle-mi300x.ttft1000.json")
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        report = os.path.join(td.name, "REPORT.md")
        self.assertEqual(diagnose.main(["--bench", retained, "--out", report, "--json"]), 0)
        with open(os.path.splitext(report)[0] + ".json", encoding="utf-8") as f:
            emitted = json.load(f)
        self.assertIn("Not comparable", emitted["verdict"])
        self.assertNotIn("0.10x", emitted["verdict"])
        bench, err = diagnose.load_bench(retained)
        self.assertIsNone(err)
        ref, err = diagnose.load_reference(REFERENCE)
        self.assertIsNone(err)
        verdict = diagnose.verdict_line(bench, ref)
        self.assertIn("Not comparable", verdict)
        self.assertNotIn("0.10x", verdict)
        candidate = dict(ref["comparison_scopes"]["run1-cell-c64"])
        candidate["bench_sha256"] = diagnose.sha256_file(retained)
        candidate["evidence"] = "retained Run 1 source table and identity.json"
        compared = diagnose.assess_comparison(bench, ref, candidate, "run3-own-window")
        self.assertEqual(compared["economic_comparison"], "unavailable")
        self.assertTrue(any("workload_id" in reason or "acceptance" in reason or "cost_scope" in reason
                            for reason in compared["reasons"]))
        scope = ref["comparison_scopes"]["run3-own-window"]
        # Run 1 is latency-only random prompts; Run 3 is trace-replayed EvalPlus.
        self.assertNotEqual(scope["workload_id"], "random-seed7-in2048-out256-n200-v1")

    def test_scope_hash_and_acceptance_are_required_and_configuration_label_checked(self):
        with open(os.path.join(FIXTURES, "bench-cells", "table.json"), "rb") as f:
            payload = f.read()
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        table_path = os.path.join(td.name, "table.json")
        with open(table_path, "wb") as f:
            f.write(payload)
        bench, err = diagnose.load_bench(table_path)
        self.assertIsNone(err)
        config = {"gpu_model": "Test GPU", "gpu_count": 1, "runtime_digest": "sha256:test",
                  "server_version": "v1", "backend": "backend-a", "kernel": "kernel-a", "tensor_parallel": 1}
        scope = {
            "workload_id": "work-v1", "model_revision": "modelrev", "tokenizer_revision": "tokenrev",
            "precision": "FP8", "cache_policy": "warm", "load_profile_id": "fixed-c1",
            "cost_scope": "cell_execution_window", "observation_date": "2026-09-25",
            "configuration_id": "config-a", "configuration": config, "rate": bench["rate"],
            "acceptance": {"rule_id": "latency-only", "quality_rule": "completed under gates",
                           "ttft_ms": 1000, "e2e_ms": None, "evidence": "test scope evidence"},
            "evidence": "fixture scope", "bench_sha256": diagnose.sha256_file(table_path),
        }
        ref = {"comparison_scopes": {"test": dict(scope)}}
        matched = diagnose.assess_comparison(bench, ref, dict(scope), "test", "matched")
        self.assertEqual(matched["label"], "matched")
        self.assertIn("not established", matched["operator_causality"])
        other = dict(scope)
        other["configuration_id"] = "config-b"
        other["configuration"] = {**config, "gpu_model": "Other GPU"}
        different = diagnose.assess_comparison(bench, ref, other, "test", "different complete configuration")
        self.assertEqual(different["label"], "different complete configuration")
        self.assertIn("allowed", different["economic_comparison"])
        other["acceptance"] = {**scope["acceptance"], "quality_rule": "correctness graded"}
        rejected = diagnose.assess_comparison(bench, ref, other, "test")
        self.assertEqual(rejected["economic_comparison"], "unavailable")
        self.assertTrue(any("acceptance mismatch" in x for x in rejected["reasons"]))
        other["acceptance"] = scope["acceptance"]
        other["bench_sha256"] = "0" * 64
        rejected_hash = diagnose.assess_comparison(bench, ref, other, "test")
        self.assertTrue(any("sha256" in x.lower() for x in rejected_hash["reasons"]))

    def test_reference_cost_scopes_remain_distinct_and_run3_cache_is_unknown(self):
        ref, err = diagnose.load_reference(REFERENCE)
        self.assertIsNone(err)
        scopes = ref["comparison_scopes"]
        self.assertNotEqual(scopes["run3-own-window"]["cost_scope"], scopes["run3-whole-seat"]["cost_scope"])
        self.assertIn("unobserved", scopes["run3-own-window"]["cache_policy"])
        self.assertTrue(diagnose.is_unknown_value(scopes["run3-own-window"]["cache_policy"]))


if __name__ == "__main__":
    unittest.main()
