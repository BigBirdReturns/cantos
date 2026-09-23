"""Offline real-schema and mocked history tests; python -B test_history.py."""
import copy
import io
import json
import shutil
import unittest
import uuid
import zipfile
from unittest.mock import patch
import importer as I
import fetch_history as F


class RealSchemaTests(unittest.TestCase):
    def setUp(self):
        self.manifest = I.BASE / "fixtures/manifest.json"
        self.rows = I.import_manifest(self.manifest, True)

    def test_original_bytes_and_identity(self):
        m = json.loads(self.manifest.read_bytes())
        self.assertEqual(5, len(m["files"]))
        for e in m["files"]:
            self.assertEqual(e["sha256"], I.digest((self.manifest.parent / e["path"]).read_bytes()))
        self.assertEqual(self.rows, I.import_manifest(self.manifest, True))
        self.assertTrue(all(r["fixture"] and r["tier"] == "imported" for r in self.rows))
        self.assertTrue(all(r["provenance"]["artifact_id"] for r in self.rows))

    def test_nested_metrics_and_shapes(self):
        r = next(r for r in self.rows if r["provenance"]["artifact_id"] == 10716032664 and r["metric"]["name"] == "p95_ttft_ms")
        self.assertAlmostEqual(29189.37, r["metric"]["value"])
        self.assertIsNone(r["workload"]["input_tokens"])
        self.assertEqual(4, r["gpus"])
        self.assertEqual(1615, r["num_requests_total"])
        self.assertEqual(1438, r["num_requests_successful"])
        self.assertAlmostEqual(1438/1615, r["success_rate"])
        self.assertEqual(4062.984375, r["joules_per_successful_query"])
        self.assertEqual(1, r["power_valid"])

    def test_failed_rows_survive(self):
        failed = [r for r in self.rows if r["outcome"] == "failure"]
        self.assertEqual(2, len(failed))
        for r in failed:
            self.assertEqual(0, r["metric"]["value"])
            self.assertEqual(0 if r["num_requests_total"] else None, r["success_rate"])
            self.assertEqual("successful_requests", r["metric"]["name"])
            self.assertTrue(r["comparison_hold"])
            self.assertIsNone(r["joules_per_successful_query"])

    def test_fixed_counts_and_topology(self):
        r = next(r for r in self.rows if r["provenance"]["artifact_id"] == 10716378525)
        self.assertEqual(640, r["num_requests_successful"])
        self.assertEqual(1, r["success_rate"])
        self.assertEqual(8, r["gpus"])
        self.assertEqual(I.UNKNOWN, r["image_digest"])
        self.assertNotIn("comparison_hold", r)
        r = next(r for r in self.rows if r["provenance"]["artifact_id"] == 10718795856)
        self.assertEqual(8, r["gpus"])
        self.assertEqual("num_prefill_gpu + num_decode_gpu", r["gpu_count_rule"])
        r = next(r for r in self.rows if r["provenance"]["artifact_id"] == 10721648398)
        self.assertEqual(1, r["gpus"])

    def test_gpu_rule_not_ep_or_dcp(self):
        self.assertEqual(16, I.gpu_count(dict(tp=4, pp=2, pcp_size=2, ep=4, dcp_size=4))[0])
        self.assertIsNone(I.gpu_count(dict(tp=8, pp=1, is_multinode=True))[0])
        self.assertEqual(4, I.gpu_count(dict(num_gpus=4, tp=8, pp=1))[0])
        with self.assertRaises(ValueError):
            I.gpu_count(dict(num_gpus=1.5))

    def test_empty_and_invalid_schema(self):
        self.assertEqual([], I.inferencemax({}, b"[]", "test", True))
        with self.assertRaises(ValueError):
            I.inferencemax({}, b"{}", "test", True)
        for gpu in ("gb200", "gb300", "b300", "mi355x"):
            self.assertEqual(gpu.upper(), I.hardware("cluster:" + gpu + "-vendor"))

    def test_summary_counts_source_rows_not_metrics(self):
        from summarize import summarize
        manifest = json.loads(self.manifest.read_bytes())
        report = {"comparable_source_rows": 0, "measured_cells": 45, "comparable_observations": 0, "gaps": []}
        summary = summarize(self.rows, manifest, report)
        count = sum(len(json.loads((self.manifest.parent / e["path"]).read_bytes())) for e in manifest["files"])
        self.assertIn(f"{count} source rows", summary)
        self.assertIn("2 zero-success/failure rows retained", summary)
        self.assertIn("10780222898:1 (0/0)", summary)

    def test_raw_manifest_binds_receipts_and_preserves_unknown_run(self):
        # The real fixture manifest includes no invented workflow run IDs.
        manifest = json.loads(self.manifest.read_bytes())
        self.assertTrue(all(e.get("workflow_run_id") is None for e in manifest["files"] if e["artifact_id"] != 10780222898))
        row = next(r for r in self.rows if r["provenance"]["artifact_id"] == 10716378525)
        self.assertEqual(row["provenance"]["head_sha"], row["provenance"]["revision"])
        self.assertIsNone(row["observed_at"])


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.root = I.BASE / ("test-history-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.filters = {k: [] for k in ("hardware", "model", "framework", "shape")}
        self.fixture = (I.BASE / "fixtures/inferencex-10716032664.json").read_bytes()
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            z.writestr("agg_bmk.json", self.fixture)
        self.archive = out.getvalue()

    def tearDown(self):
        # Unique test directory is resolved and checked before recursive cleanup.
        resolved = self.root.resolve()
        assert resolved.parent == I.BASE.resolve() and resolved.name.startswith("test-history-")
        shutil.rmtree(resolved)

    def artifact(self, ident, expired=False):
        return {"id": ident, "name": "results_bmk", "expired": expired, "created_at": "2026-09-23T00:00:00Z",
                "workflow_run": {"id": 123, "head_sha": "a" * 40}}

    def api(self, artifacts):
        def request(url):
            if "/zip" in url:
                return 200, {}, self.archive
            return 200, {}, json.dumps({"artifacts": artifacts if "&page=1" in url else []}).encode()
        return request

    def test_cap_resume_skip_expired_and_existing(self):
        a = [self.artifact(1), self.artifact(2, True), self.artifact(3)]
        request = self.api(a)
        first = F.fetch(self.root, F.Client(2, request), self.filters)
        self.assertEqual("request-cap", first["status"])
        self.assertEqual([1], first["fetched"])
        self.assertEqual([2], first["skipped_expired"])
        self.assertEqual(2, first["requests"])
        second = F.fetch(self.root, F.Client(2, request), self.filters)
        self.assertEqual("complete", second["status"])
        self.assertEqual([3], second["fetched"])
        third = F.fetch(self.root, F.Client(2, request), self.filters, restart=True)
        self.assertEqual([], third["fetched"])
        self.assertEqual([1, 3], third["skipped_downloaded"])
        self.assertEqual(3, len(list(self.root.glob("fetch-receipt-*.json"))))
        m = I.raw_manifest(self.root, "2026-09-23T00:00:00Z")
        self.assertEqual(123, m["files"][0]["workflow_run_id"])

    def test_rate_limits_and_retry_budget(self):
        responses = iter([(403, {"Retry-After": "2", "X-RateLimit-Reset": "105"}, b""),
                          (429, {"retry-after": "3"}, b""), (200, {}, b"ok")])
        sleeps = []
        client = F.Client(3, lambda url: next(responses), sleeps.append, lambda: 100)
        self.assertEqual(b"ok", client.get(F.API))
        self.assertEqual(3, client.used)
        self.assertIn(6, sleeps)
        self.assertIn(3, sleeps)
        with self.assertRaises(F.BudgetDone):
            client.get(F.API)

    def test_rate_limit_saved_at_cap(self):
        sleeps = []
        client = F.Client(1, lambda url: (429, {"retry-after": "30"}, b""), sleeps.append, lambda: 100)
        r = F.fetch(self.root, client, self.filters)
        self.assertEqual("request-cap", r["status"])
        self.assertEqual([30], sleeps)
        self.assertEqual(130, json.loads((self.root / "history-state.json").read_bytes())["cooldown_until"])

    def test_filters_preserve_whole_raw_file(self):
        filters = dict(self.filters, hardware=["H100"])
        F.fetch(self.root, F.Client(3, self.api([self.artifact(1)])), filters)
        self.assertEqual(self.fixture, (self.root / "results_bmk_1/agg_bmk.json").read_bytes())
        index = json.loads((self.root / "history-index.json").read_bytes())
        self.assertEqual([], index["1"]["matching_row_indices"])
        self.assertTrue(F.matches({"hw": "cluster:mi300x-amd", "framework": "vllm", "isl": 2048, "osl": 256},
                                  dict(self.filters, hardware=["MI300X"], framework=["vllm"], shape=["2048/256"])))

    def test_error_receipt_and_retry_after_interruption(self):
        def broken(url):
            if "/zip" in url:
                raise OSError("mock interruption")
            return self.api([self.artifact(1)])(url)
        with self.assertRaises(OSError):
            F.fetch(self.root, F.Client(3, broken), self.filters)
        receipt = json.loads(next(self.root.glob("fetch-receipt-*.json")).read_bytes())
        self.assertEqual("error", receipt["status"])
        result = F.fetch(self.root, F.Client(2, self.api([self.artifact(1)])), self.filters)
        self.assertEqual([1], result["fetched"])

    def test_zip_paths_never_extracted(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            z.writestr("../escaped.json", self.fixture)
        self.archive = out.getvalue()
        with self.assertRaises(ValueError):
            F.fetch(self.root, F.Client(3, self.api([self.artifact(1)])), self.filters)
        self.assertFalse((self.root / "results_bmk_1/agg_bmk.json").exists())

    def test_gh_headers(self):
        from types import SimpleNamespace
        result = SimpleNamespace(stdout=b"HTTP/2.0 429 Too Many Requests\r\nRetry-After: 2\r\n\r\n{}", returncode=1)
        with patch("shutil.which", return_value="gh"), patch("subprocess.run", return_value=result):
            status, headers, body = F.transport(F.API)
        self.assertEqual(429, status)
        self.assertEqual("2", headers["retry-after"])

    def test_urllib_fallback_is_mocked_and_drops_redirect_auth(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = response
        response.status, response.headers = 200, {}
        response.read.return_value = b"{}"
        opener = MagicMock()
        opener.open.return_value = response
        with patch("shutil.which", return_value=None), patch.dict("os.environ", {"GH_TOKEN": "test-only"}), \
                patch("urllib.request.build_opener", return_value=opener) as build:
            self.assertEqual(200, F.transport(F.API)[0])
            request = opener.open.call_args.args[0]
            self.assertEqual("Bearer test-only", request.get_header("Authorization"))
            redirect = build.call_args.args[0]
            redirected = redirect.redirect_request(request, None, 302, "Found", {}, "https://example.test/blob")
            self.assertIsNone(redirected.get_header("Authorization"))

    def test_expired_after_listing_is_recorded(self):
        api = self.api([self.artifact(1)])
        request = lambda url: (410, {}, b"") if "/zip" in url else api(url)
        result = F.fetch(self.root, F.Client(3, request), self.filters)
        self.assertEqual([1], result["skipped_expired"])
        self.assertEqual("complete", result["status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
