"""Pinned multi-receipt HTTP audit ledger, with a local HTTP fixture only."""
from datetime import timedelta, datetime
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import threading
import unittest

from compute.maintainer.operational_http import AuditInputError, audit
from compute.maintainer.operational_http_ledger import reconcile, main


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status = 503 if self.path == "/bad" else 200
        payload = b"public temporal audit fixture"
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def encode(doc):
    return (json.dumps(doc, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def digest(raw):
    return sha256(raw).hexdigest()


def make(root, docs, *, endpoint=None, method="GET"):
    entries = []
    for i, doc in enumerate(docs):
        raw = encode(doc)
        name = "capture-%02d.json" % (i + 1)
        (root / name).write_bytes(raw)
        entries.append({"file": name, "sha256": digest(raw)})
    manifest = {
        "schema": "cantos.operational-http-ledger-manifest/1",
        "endpoint": docs[0]["endpoint"] if endpoint is None else endpoint,
        "method": method, "receipts": entries,
    }
    raw = encode(manifest)
    return raw, digest(raw), manifest


class TemporalLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:%d" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def good(self):
        return audit(self.url + "/ok", method="GET", samples=2)

    def test_two_custodied_successes_report_sparse_observed_gaps(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            docs = [self.good(), self.good()]
            raw, pin, _ = make(root, docs)
            result = reconcile(raw, pin, root)
            self.assertEqual(result["verdict"], "pass")
            self.assertEqual(result["samples"]["attempts"], 4)
            self.assertEqual(result["samples"]["successes"], 4)
            self.assertEqual(result["receipt_count"], 2)
            self.assertGreaterEqual(result["window"]["unobserved_gap_seconds"], 0)
            self.assertIn("Unobserved gaps", result["limits"][1])
            self.assertEqual(result["custody"], "externally_pinned_inventory_and_each_original_receipt")

    def test_failed_receipt_is_not_smoothed_by_other_successes(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            good = audit(self.url + "/bad", method="GET", samples=1)
            raw, pin, _ = make(root, [good])
            result = reconcile(raw, pin, root)
            self.assertEqual(result["verdict"], "fail")
            self.assertEqual(result["samples"]["outcome_counts"]["http_server_failure"], 1)
            self.assertEqual(result["samples"]["longest_consecutive_failure_samples"], 1)

    def test_tampered_original_receipt_rejected(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            raw, pin, manifest = make(root, [self.good()])
            file = root / manifest["receipts"][0]["file"]
            file.write_bytes(file.read_bytes() + b" ")
            with self.assertRaisesRegex(AuditInputError, "external receipt SHA-256"):
                reconcile(raw, pin, root)

    def test_removed_failure_cannot_keep_externally_pinned_inventory(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            raw, pin, manifest = make(root, [self.good(), self.good()])
            manifest["receipts"].pop()
            with self.assertRaisesRegex(AuditInputError, "external manifest SHA-256"):
                reconcile(encode(manifest), pin, root)

    def test_duplicate_receipt_pin_is_not_independent_observation(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            raw, _, manifest = make(root, [self.good()])
            manifest["receipts"].append(dict(manifest["receipts"][0]))
            replaced = encode(manifest)
            with self.assertRaisesRegex(AuditInputError, "duplicate"):
                reconcile(replaced, digest(replaced), root)

    def test_reordered_receipts_rejected_even_with_recalculated_manifest_pin(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            raw, _, manifest = make(root, [self.good(), self.good()])
            manifest["receipts"].reverse()
            replaced = encode(manifest)
            with self.assertRaisesRegex(AuditInputError, "out-of-order"):
                reconcile(replaced, digest(replaced), root)

    def test_mixed_endpoint_refused(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            raw, _, manifest = make(root, [self.good()])
            manifest["endpoint"] = self.url + "/bad"
            replaced = encode(manifest)
            with self.assertRaisesRegex(AuditInputError, "mixed endpoint"):
                reconcile(replaced, digest(replaced), root)

    def test_mixed_method_refused(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            raw, _, manifest = make(root, [self.good()])
            manifest["method"] = "HEAD"
            replaced = encode(manifest)
            with self.assertRaisesRegex(AuditInputError, "mixed endpoint or method"):
                reconcile(replaced, digest(replaced), root)

    def test_path_traversal_refused_before_file_read(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            raw, _, manifest = make(root, [self.good()])
            manifest["receipts"][0]["file"] = "../outside.json"
            replaced = encode(manifest)
            with self.assertRaisesRegex(AuditInputError, "filename"):
                reconcile(replaced, digest(replaced), root)

    def test_symlink_to_other_file_refused(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            raw, _, manifest = make(root, [self.good()])
            file = root / manifest["receipts"][0]["file"]
            original = root / "hidden.json"
            file.rename(original)
            file.symlink_to(original)
            with self.assertRaisesRegex(AuditInputError, "unsafe receipt path"):
                reconcile(raw, digest(raw), root)

    def test_repinning_rewritten_original_verdict_still_fails(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            source = audit(self.url + "/bad", method="GET", samples=1)
            source["verdict"] = "pass"
            raw, pin, _ = make(root, [source])
            with self.assertRaisesRegex(AuditInputError, "verdict disagrees"):
                reconcile(raw, pin, root)

    def test_collector_clock_overlap_rejected_with_valid_repin(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            a, b = self.good(), self.good()
            b["observations"][0]["utc_start"] = a["observations"][0]["utc_start"]
            b["observations_sha256"] = digest(json.dumps(
                b["observations"], sort_keys=True, separators=(",", ":")).encode())
            raw, pin, _ = make(root, [a, b])
            with self.assertRaisesRegex(AuditInputError, "out-of-order"):
                reconcile(raw, pin, root)

    def test_cli_exit_and_exclusive_output(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            raw, pin, _ = make(root, [self.good()])
            manifest = root / "manifest.json"
            manifest.write_bytes(raw)
            output = root / "result.json"
            args = ["--manifest", str(manifest), "--expected-manifest-sha256", pin,
                    "--evidence-directory", str(root), "--output", str(output)]
            self.assertEqual(main(args), 0)
            self.assertEqual(json.loads(output.read_text())["verdict"], "pass")
            self.assertEqual(main(args), 2)
            self.assertEqual(main(args[:-1] + [str(root / "unused.json"),
                                             "--expected-manifest-sha256", "0" * 64]), 2)

    def test_cli_failed_receipt_returns_one(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            raw, pin, _ = make(root, [audit(self.url + "/bad", method="GET", samples=1)])
            manifest = root / "manifest.json"
            manifest.write_bytes(raw)
            self.assertEqual(main(["--manifest", str(manifest),
                                   "--expected-manifest-sha256", pin,
                                   "--evidence-directory", str(root),
                                   "--output", str(root / "fail.json")]), 1)


if __name__ == "__main__":
    unittest.main()
