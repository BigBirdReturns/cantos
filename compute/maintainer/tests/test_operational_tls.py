"""TLS operational audit tests: certificate DER, replay and native transport policy."""
import base64
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from operational_tls import (AuditInputError, audit, certificate_validity, validate_origin,
                             verify, _fetch_leaf)


def tlv(tag, payload):
    if len(payload) < 128:
        prefix = bytes([len(payload)])
    else:
        digits = len(payload).to_bytes((len(payload).bit_length() + 7) // 8, "big")
        prefix = bytes([0x80 | len(digits)]) + digits
    return bytes([tag]) + prefix + payload


def cert(after_days=300):
    now = datetime.now(timezone.utc)
    before = now - timedelta(days=10)
    after = now + timedelta(days=after_days)
    def when(dt):
        return tlv(0x18, dt.strftime("%Y%m%d%H%M%SZ").encode())
    validity = tlv(0x30, when(before) + when(after))
    tbs = tlv(0x30, tlv(0xa0, tlv(0x02, b"\x02")) +
              tlv(0x02, b"\x01") + tlv(0x30, b"") +
              tlv(0x30, b"") + validity)
    return tlv(0x30, tbs + tlv(0x30, b"") + tlv(0x03, b"\x00"))


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


class CertificateAudit(unittest.TestCase):
    def setUp(self):
        self.der = cert()
        self.url = "https://audit.example/"
        self.host = "audit.example"

    def sample(self, **changes):
        with patch("operational_tls._fetch_leaf", return_value=self.der) as fetch:
            document = audit(self.url, allow_host=self.host, samples=2, **changes)
            self.assertEqual(fetch.call_count, 2)
            return document

    def test_der_dates_and_no_trailing_payload(self):
        start, end = certificate_validity(self.der)
        self.assertLess(start, datetime.now(timezone.utc))
        self.assertGreater(end, datetime.now(timezone.utc))
        with self.assertRaises(AuditInputError):
            certificate_validity(self.der + b"X")

    def test_observed_pinned_replay(self):
        receipt = self.sample()
        self.assertEqual(receipt["verdict"], "pass")
        self.assertEqual(receipt["summary"]["successes"], 2)
        raw = canonical(receipt)
        self.assertEqual(verify(raw, sha256(raw).hexdigest())["verdict"], "pass")

    def test_bad_external_pin_and_rewritten_verdict(self):
        receipt = self.sample()
        raw = canonical(receipt)
        pin = sha256(raw).hexdigest()
        with self.assertRaisesRegex(AuditInputError, "external receipt hash"):
            verify(raw, "0" * 64)
        receipt["verdict"] = "fail"
        with self.assertRaisesRegex(AuditInputError, "external receipt hash"):
            verify(canonical(receipt), pin)
        with self.assertRaisesRegex(AuditInputError, "verdict recomputation"):
            changed = canonical(receipt)
            verify(changed, sha256(changed).hexdigest())

    def test_leaf_content_and_fingerprint_mutation(self):
        receipt = self.sample()
        receipt["observations"][0]["leaf_sha256"] = "0" * 64
        raw = canonical(receipt)
        with self.assertRaisesRegex(AuditInputError, "leaf leaf_sha256"):
            verify(raw, sha256(raw).hexdigest())
        receipt = self.sample()
        receipt["observations"][0]["leaf_der_base64"] = base64.b64encode(self.der[:-1]).decode()
        raw = canonical(receipt)
        with self.assertRaises(AuditInputError):
            verify(raw, sha256(raw).hexdigest())

    def test_wrong_certificate_pin_is_invariant(self):
        receipt = self.sample(expected_leaf_sha256="0" * 64)
        self.assertEqual(receipt["verdict"], "fail")
        self.assertEqual(receipt["summary"]["outcome_counts"], {"tls_leaf_pin_mismatch": 2})
        raw = canonical(receipt)
        self.assertEqual(verify(raw, sha256(raw).hexdigest())["verdict"], "fail")

    def test_expiring_certificate_holds(self):
        der = cert(after_days=2)
        with patch("operational_tls._fetch_leaf", return_value=der):
            receipt = audit(self.url, allow_host=self.host, min_remaining_days=14)
        self.assertEqual(receipt["verdict"], "fail")
        self.assertEqual(receipt["observations"][0]["outcome"], "tls_certificate_expiring")
        raw = canonical(receipt)
        self.assertEqual(verify(raw, sha256(raw).hexdigest())["verdict"], "fail")

    def test_refuse_unapproved_target_and_nonfinite_policy(self):
        for url, allow in [
            ("http://audit.example", "audit.example"),
            ("https://audit.example/path", "audit.example"),
            ("https://audit.example/?token=1", "audit.example"),
            ("https://audit.example", "elsewhere.example"),
            ("https://user:password@audit.example", "audit.example"),
            ("https://audit.example", "*.example"),
            ("https://audit.example:0", "audit.example"),
            ("https://audit.example:65536", "audit.example"),
        ]:
            with self.subTest(url=url, allow=allow), self.assertRaises(AuditInputError):
                validate_origin(url, allow)
        with self.assertRaises(AuditInputError):
            audit(self.url, allow_host=self.host, timeout_seconds=float("nan"))
        with self.assertRaises(AuditInputError):
            audit(self.url, allow_host=self.host, min_remaining_days=-1)

    def test_tls_verification_failure_is_not_success(self):
        import ssl
        with patch("operational_tls._fetch_leaf", side_effect=ssl.SSLCertVerificationError("failed")):
            receipt = audit(self.url, allow_host=self.host)
        self.assertEqual(receipt["observations"][0]["outcome"], "tls_verification_failed")
        raw = canonical(receipt)
        self.assertEqual(verify(raw, sha256(raw).hexdigest())["verdict"], "fail")
        receipt["observations"][0]["outcome"] = "tls_success"
        raw = canonical(receipt)
        with self.assertRaisesRegex(AuditInputError, "observation outcome"):
            verify(raw, sha256(raw).hexdigest())

    def test_timeout_is_separate_transport_class(self):
        with patch("operational_tls._fetch_leaf", side_effect=TimeoutError("offline")):
            receipt = audit(self.url, allow_host=self.host)
        self.assertEqual(receipt["observations"][0]["outcome"], "tls_transport_error")
        raw = canonical(receipt)
        self.assertEqual(verify(raw, sha256(raw).hexdigest())["verdict"], "fail")

    def test_default_trust_and_exact_sni(self):
        from unittest.mock import MagicMock
        import ssl
        ctx = MagicMock()
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = True
        peer = MagicMock()
        peer.getpeercert.side_effect = [self.der, {"notAfter": "Jan 01 00:00:00 2030 GMT"}]
        peer.__enter__.return_value = peer
        tcp = MagicMock()
        tcp.__enter__.return_value = tcp
        ctx.wrap_socket.return_value = peer
        with patch("operational_tls.socket.create_connection", return_value=tcp) as dial, \
             patch("operational_tls.ssl.create_default_context", return_value=ctx), \
             patch("operational_tls.ssl.cert_time_to_seconds",
                   return_value=int(certificate_validity(self.der)[1].timestamp())):
            self.assertEqual(_fetch_leaf(self.host, 443, 2), self.der)
        dial.assert_called_once_with((self.host, 443), timeout=2)
        ctx.wrap_socket.assert_called_once_with(tcp, server_hostname=self.host)


if __name__ == "__main__":
    unittest.main()
