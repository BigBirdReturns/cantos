"""Adversarial temporal replay of independently pinned joint HTTPS receipts."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from compute.maintainer.operational_https_ledger import AuditInputError, reconcile, main
from compute.maintainer.operational_https_joint import canonical
from compute.maintainer.tests import test_operational_https_joint as _joint_fixture


class JointTemporalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.fixture = _joint_fixture.JointHTTPSAuditTests()
        self.fixture.setUp()

    def prepare(self, records=None):
        if records is None:
            records = [self.fixture.collect(), self.fixture.collect()]
        entries = []
        for idx, record in enumerate(records):
            name = f"receipt-{idx+1}.json"
            raw = canonical(record)
            (self.path / name).write_bytes(raw)
            entries.append({"file": name, "sha256": sha256(raw).hexdigest()})
        manifest = {
            "schema": "cantos.operational-https-ledger-manifest/1",
            "endpoint": self.fixture.url,
            "authorized_host": self.fixture.host,
            "method": "GET",
            "receipts": entries,
        }
        raw = canonical(manifest)
        return manifest, sha256(raw).hexdigest(), raw

    def check(self, records=None):
        _, digest, raw = self.prepare(records)
        return reconcile(raw, digest, self.path)

    def test_pinned_live_capture_replay_and_sample_only_scope(self):
        result = self.check()
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["samples"]["attempts"], 2)
        self.assertEqual(result["samples"]["successes"], 2)
        self.assertEqual(result["receipt_count"], 2)
        self.assertEqual(len(result["samples"]["observed_distinct_TLS_leaf_sha256"]), 1)
        self.assertGreaterEqual(result["window"]["unobserved_gap_seconds"], 0)
        self.assertIn("not a provider-wide SLA", result["limits"][0])

    def test_pinned_manifest_tamper_rejected(self):
        manifest, digest, raw = self.prepare()
        with self.assertRaisesRegex(AuditInputError, "external manifest digest mismatch"):
            reconcile(raw + b" ", digest, self.path)

    def test_independently_pinned_receipt_tamper_rejected(self):
        _, digest, raw = self.prepare()
        file = self.path / "receipt-2.json"
        file.write_bytes(file.read_bytes() + b" ")
        with self.assertRaises(AuditInputError):
            reconcile(raw, digest, self.path)

    def test_duplicate_capture_rejected_even_under_new_filename(self):
        record = self.fixture.collect()
        with self.assertRaisesRegex(AuditInputError, "duplicate receipt"):
            self.check([record, record])

    def test_mixed_authorized_host_and_endpoint_rejected(self):
        manifest, _, _ = self.prepare()
        for field, value in [("endpoint", "https://other.example/health"),
                             ("authorized_host", "other.example")]:
            wrong = dict(manifest, **{field: value})
            raw = canonical(wrong)
            with self.subTest(field=field), self.assertRaises(AuditInputError):
                reconcile(raw, sha256(raw).hexdigest(), self.path)

    def test_mixed_response_policy_rejected(self):
        first = self.fixture.collect()
        other = self.fixture.collect(max_p95_ms=2000)
        with self.assertRaisesRegex(AuditInputError, "mixed audit policy"):
            self.check([first, other])

    def test_reversed_captures_rejected(self):
        first = self.fixture.collect()
        second = self.fixture.collect()
        with self.assertRaisesRegex(AuditInputError, "overlapping or out-of-order"):
            self.check([second, first])

    def test_path_escape_and_symlink_rejected(self):
        manifest, _, _ = self.prepare()
        manifest["receipts"][0]["file"] = "../receipt-1.json"
        raw = canonical(manifest)
        with self.assertRaisesRegex(AuditInputError, "safe filename"):
            reconcile(raw, sha256(raw).hexdigest(), self.path)

        # The external manifest remains unchanged while a receipt path turns into a link.
        valid_manifest = dict(manifest, receipts=[dict(v) for v in manifest["receipts"]])
        valid_manifest["receipts"][0]["file"] = "receipt-1.json"
        raw = canonical(valid_manifest)
        digest = sha256(raw).hexdigest()
        (self.path / "receipt-1.json").unlink()
        (self.path / "receipt-1.json").symlink_to(self.path / "receipt-2.json")
        with self.assertRaisesRegex(AuditInputError, "custody path"):
            reconcile(raw, digest, self.path)

    def test_http_failure_stays_failed_and_counted(self):
        first = self.fixture.collect()
        bad = self.fixture.collect(status=500)
        result = self.check([first, bad])
        self.assertEqual(result["verdict"], "fail")
        self.assertEqual(result["samples"]["attempts"], 2)
        self.assertEqual(result["samples"]["successes"], 1)
        self.assertEqual(result["samples"]["sampled_failure_incidents"], 1)

    def test_tls_verification_time_must_belong_to_sample_interval(self):
        receipt = self.fixture.collect()
        receipt["observations"][0]["started_at_utc"] = "2020-01-01T00:00:00+00:00"
        observations = receipt["observations"]
        receipt["observations_sha256"] = sha256(json.dumps(
            observations, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        with self.assertRaisesRegex(AuditInputError, "TLS verification timestamp"):
            self.check([receipt])

    def test_direct_cli_on_pinned_receipt_inventory(self):
        _, digest, _ = self.prepare()
        manifest_file = self.path / "manifest.json"
        manifest_file.write_bytes(canonical({
            "schema": "cantos.operational-https-ledger-manifest/1",
            "endpoint": self.fixture.url, "authorized_host": self.fixture.host,
            "method": "GET",
            "receipts": [
                {"file": f"receipt-{i}.json",
                 "sha256": sha256((self.path / f"receipt-{i}.json").read_bytes()).hexdigest()}
                for i in (1, 2)],
        }))
        self.assertEqual(main(["--manifest", str(manifest_file),
                               "--expected-manifest-sha256", digest,
                               "--evidence-directory", str(self.path),
                               "--output", str(self.path / "report.json")]), 0)
        report = json.loads((self.path / "report.json").read_text())
        self.assertEqual(report["samples"]["attempts"], 2)


if __name__ == "__main__":
    unittest.main()
