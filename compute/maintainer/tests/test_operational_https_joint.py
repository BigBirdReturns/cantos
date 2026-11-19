"""Real replay of mocked same-socket TLS/HTTP capture plus adversarial receipts."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from compute.maintainer.operational_https_joint import (AuditInputError, audit, canonical,
    main, validate_endpoint, verify)
from compute.maintainer.operational_tls import certificate_validity
from compute.maintainer.tests.test_operational_tls import cert

BODY = b"cantos same socket response\n"
BODY_SHA = sha256(BODY).hexdigest()


class SocketFixture:
    def __init__(self, der):
        self.der = der

    def getpeercert(self, binary_form=False):
        if binary_form:
            return self.der
        end = certificate_validity(self.der)[1]
        return {"notAfter": end.strftime("%b %d %H:%M:%S %Y GMT")}


class ResponseFixture:
    def __init__(self, body=BODY, status=200, declared_length=None):
        self.status, self.body = status, body
        self.length = len(body) if declared_length is None else declared_length

    def getheader(self, name, default=None):
        return str(self.length) if name == "Content-Length" else default

    def read(self, n=-1):
        return self.body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ConnectionFixture:
    created = []

    def __init__(self, host, port, timeout, context, *, der, body=BODY, status=200,
                 declared_length=None, fail_connect=False):
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.sock = SocketFixture(der)
        self.response = ResponseFixture(body, status, declared_length)
        self.fail_connect = fail_connect
        self.requests = []
        ConnectionFixture.created.append(self)

    def connect(self):
        if self.fail_connect:
            raise ConnectionRefusedError("fixture")

    def request(self, method, path, headers):
        self.requests.append((method, path, headers))

    def getresponse(self):
        return self.response

    def close(self):
        pass


class JointHTTPSAuditTests(unittest.TestCase):
    url = "https://audit.example/health"
    host = "audit.example"

    def setUp(self):
        ConnectionFixture.created.clear()
        self.der = cert()

    def collect(self, *, body=BODY, status=200, declared_length=None, fail_connect=False,
                **kwargs):
        der = self.der
        def constructor(host, port, timeout, context):
            return ConnectionFixture(host, port, timeout, context, der=der,
                    body=body, status=status, declared_length=declared_length,
                    fail_connect=fail_connect)
        with patch("compute.maintainer.operational_https_joint.http_client.HTTPSConnection",
                   side_effect=constructor):
            return audit(self.url, allow_host=self.host, **kwargs)

    def check(self, receipt):
        raw = canonical(receipt)
        return verify(raw, sha256(raw).hexdigest())

    def test_bound_verified_peer_and_http_same_socket(self):
        receipt = self.collect(samples=2, expected_body_sha256=BODY_SHA)
        self.assertEqual(receipt["verdict"], "pass")
        self.assertEqual(receipt["summary"]["successes"], 2)
        self.assertEqual(len(ConnectionFixture.created), 2)
        self.assertTrue(all(c.requests[0][1] == "/health" for c in ConnectionFixture.created))
        self.assertEqual(receipt["observations"][0]["http"]["body_sha256"], BODY_SHA)
        self.assertEqual(self.check(receipt)["verdict"], "pass")

    def test_head_without_body_and_replay(self):
        receipt = self.collect(method="HEAD")
        self.assertIsNone(receipt["observations"][0]["http"]["body_bytes"])
        self.assertEqual(self.check(receipt)["verdict"], "pass")

    def test_invalid_exact_host_and_input(self):
        for url, host in [
            ("http://audit.example/health", "audit.example"),
            ("https://audit.example/health?token=1", "audit.example"),
            ("https://audit.example/health#fragment", "audit.example"),
            ("https://evil.example/health", "audit.example"),
            ("https://user:pass@audit.example/health", "audit.example"),
            ("https://audit.example:0/health", "audit.example"),
            ("https://audit.example//bad", "audit.example"),
        ]:
            with self.subTest(url=url), self.assertRaises(AuditInputError):
                validate_endpoint(url, host)
        with self.assertRaises(AuditInputError):
            self.collect(samples=0)
        with self.assertRaises(AuditInputError):
            self.collect(method="POST")

    def test_body_mismatch_cannot_pass_relaxed_threshold(self):
        receipt = self.collect(body=b"modified", expected_body_sha256=BODY_SHA,
                               min_success_fraction=0)
        self.assertEqual(receipt["verdict"], "fail")
        self.assertEqual(receipt["observations"][0]["outcome"], "http_body_mismatch")
        self.assertEqual(self.check(receipt)["verdict"], "fail")

    def test_truncated_and_oversized_body_hold(self):
        for size, limit, expected in [(len(BODY)+9, 65536, "http_body_incomplete"),
                                      (len(BODY), 2, "http_body_limit_exceeded")]:
            with self.subTest(expected=expected):
                receipt = self.collect(declared_length=size, max_body_bytes=limit)
                self.assertEqual(receipt["observations"][0]["outcome"], expected)
                self.assertEqual(self.check(receipt)["verdict"], "fail")

    def test_http_429_and_connection_refusal_are_not_success(self):
        receipt = self.collect(status=429)
        self.assertEqual(receipt["observations"][0]["outcome"], "http_throttled")
        self.assertEqual(self.check(receipt)["verdict"], "fail")
        receipt = self.collect(fail_connect=True)
        self.assertEqual(receipt["observations"][0]["outcome"], "tls_transport_error")
        self.assertEqual(self.check(receipt)["verdict"], "fail")

    def test_tls_leaf_pin_mismatch_prevents_request(self):
        receipt = self.collect(expected_leaf_sha256="0"*64, min_success_fraction=0)
        self.assertEqual(receipt["observations"][0]["outcome"], "tls_leaf_pin_mismatch")
        self.assertFalse(ConnectionFixture.created[-1].requests)
        self.assertEqual(self.check(receipt)["verdict"], "fail")

    def test_tampered_receipt_external_pin_rejected(self):
        receipt = self.collect()
        raw = canonical(receipt)
        receipt["verdict"] = "fail"
        with self.assertRaisesRegex(AuditInputError, "externally pinned"):
            verify(canonical(receipt), sha256(raw).hexdigest())
        with self.assertRaisesRegex(AuditInputError, "summary and verdict"):
            self.check(receipt)

    def test_relabelled_certificate_and_response_rejected_after_repin(self):
        for target, replacement in [("leaf_sha256", "0"*64),
                                    ("body_sha256", "0"*64)]:
            receipt = self.collect(expected_body_sha256=BODY_SHA)
            record = receipt["observations"][0]
            if target == "leaf_sha256":
                record["tls"][target] = replacement
            else:
                record["http"][target] = replacement
            receipt["observations_sha256"] = sha256(json.dumps(
                receipt["observations"], sort_keys=True,
                separators=(",", ":")).encode()).hexdigest()
            with self.assertRaises(AuditInputError):
                self.check(receipt)

    def test_replay_rejects_request_without_verified_tls(self):
        receipt = self.collect(fail_connect=True)
        receipt["observations"][0]["http"] = {"http_status": 200}
        receipt["observations_sha256"] = sha256(json.dumps(
            receipt["observations"], sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        with self.assertRaisesRegex(AuditInputError, "HTTP request after refused TLS"):
            self.check(receipt)

    def test_cli_verify_pinned_fixture_and_exclusive_output(self):
        receipt = self.collect()
        with TemporaryDirectory() as d:
            path = Path(d) / "receipt.json"
            out = Path(d) / "verified.json"
            raw = canonical(receipt)
            path.write_bytes(raw)
            args = ["verify", "--receipt", str(path), "--expected-receipt-sha256",
                    sha256(raw).hexdigest(), "--output", str(out)]
            self.assertEqual(main(args), 0)
            self.assertTrue(out.exists())
            self.assertEqual(main(args), 3)  # exclusive output, no overwrite


if __name__ == "__main__":
    unittest.main()
