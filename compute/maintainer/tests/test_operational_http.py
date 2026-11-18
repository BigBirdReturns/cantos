"""Live loopback checks for the bounded operational HTTP collector."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import tempfile
from unittest.mock import patch
import unittest

from compute.maintainer.operational_http import (
    AuditInputError, audit, main, validate_target,
)


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        statuses = {"/ok": 200, "/throttle": 429, "/failure": 503, "/redirect": 302}
        code = statuses.get(self.path, 404)
        self.send_response(code)
        if code == 302:
            self.send_header("Location", "/ok")
        self.end_headers()

    def log_message(self, *args):
        pass


class ObservedHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_real_head_samples_bound_to_endpoint(self):
        r = audit(self.base + "/ok", samples=3)
        self.assertEqual(r["verdict"], "pass")
        self.assertEqual((r["summary"]["successes"], r["summary"]["attempts"]), (3, 3))
        self.assertEqual(r["evidence_class"], "observed_client_vantage")
        self.assertEqual(r["method"], "HEAD")
        self.assertEqual([x["http_status"] for x in r["observations"]], [200] * 3)
        raw = json.dumps(r["observations"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        self.assertEqual(r["observations_sha256"], hashlib.sha256(raw).hexdigest())

    def test_proxy_environment_cannot_redirect_authorized_loopback_probe(self):
        # Explicit, local probe must not silently honor an ambient proxy route.
        with patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:1",
                                     "HTTP_PROXY": "http://127.0.0.1:1",
                                     "no_proxy": "", "NO_PROXY": ""}):
            result = audit(self.base + "/ok", samples=1, timeout_seconds=0.5)
        self.assertEqual(result["summary"]["outcome_counts"], {"http_success": 1})
        self.assertEqual(result["verdict"], "pass")

    def test_5xx_fails_without_losing_observation(self):
        r = audit(self.base + "/failure", samples=2)
        self.assertEqual(r["verdict"], "fail")
        self.assertEqual(r["summary"]["outcome_counts"], {"http_server_failure": 2})
        self.assertEqual([x["http_status"] for x in r["observations"]], [503, 503])

    def test_throttling_is_distinct_from_server_failure(self):
        r = audit(self.base + "/throttle", samples=1)
        self.assertEqual(r["summary"]["outcome_counts"], {"http_throttled": 1})

    def test_redirect_is_not_followed_or_counted_as_success(self):
        r = audit(self.base + "/redirect", samples=1)
        self.assertEqual(r["observations"][0]["http_status"], 302)
        self.assertEqual(r["summary"]["outcome_counts"], {"http_redirect_not_followed": 1})
        self.assertEqual(r["verdict"], "fail")

    def test_actual_404_is_retained(self):
        r = audit(self.base + "/not-found", samples=1)
        self.assertEqual(r["summary"]["outcome_counts"], {"http_client_failure": 1})

    def test_remote_requires_exact_authorized_tls_hostname(self):
        with self.assertRaises(AuditInputError):
            validate_target("https://example.org/a")
        with self.assertRaises(AuditInputError):
            validate_target("http://example.org/a", allow_host="example.org")
        with self.assertRaises(AuditInputError):
            validate_target("https://evil.example.org/a", allow_host="example.org")
        self.assertEqual(validate_target("https://example.org/a", allow_host="EXAMPLE.ORG"),
                         "https://example.org/a")

    def test_credential_and_query_bearing_urls_rejected(self):
        for url in ("http://name:pass@127.0.0.1/a", "http://127.0.0.1/?token=secret",
                    "http://127.0.0.1/a#fragment", "file:///etc/passwd"):
            with self.subTest(url=url), self.assertRaises(AuditInputError):
                validate_target(url)

    def test_invalid_thresholds_rejected_without_network(self):
        for kw in ({"samples": 31}, {"samples": 0}, {"timeout_seconds": 20.0},
                   {"min_success_fraction": -0.1}, {"max_p95_ms": float("nan")}):
            with self.subTest(kw=kw), self.assertRaises(AuditInputError):
                audit(self.base + "/ok", **kw)

    def test_cli_writes_single_non_overwriting_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "observation.json"
            argv = ["--url", self.base + "/ok", "--samples", "1", "--output", str(target)]
            self.assertEqual(main(argv), 0)
            self.assertEqual(json.loads(target.read_text())["verdict"], "pass")
            self.assertEqual(main(argv), 2)

    def test_cli_failure_status_has_nonzero_exit(self):
        self.assertEqual(main(["--url", self.base + "/failure", "--samples", "1",
                               "--min-success-fraction", "1"]), 1)


if __name__ == "__main__":
    unittest.main()
