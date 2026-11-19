"""Deterministic source-pinned replay of operational HTTP audits."""
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import threading
import unittest

from compute.maintainer.operational_http import AuditInputError, audit
from compute.maintainer.operational_http_verify import main, verify_receipt

BODY = b'cantos-receipt-fixture\n'
BODY_SHA = sha256(BODY).hexdigest()


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        code = 503 if self.path == '/fail' else 200
        self.send_response(code)
        self.send_header('Content-Length', str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)

    def log_message(self, *args):
        pass


def render(doc):
    return (json.dumps(doc, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def pin(raw):
    return sha256(raw).hexdigest()


class OperationalReceiptVerifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def good(self):
        return audit(self.url + '/ok', samples=2, method='GET',
                     expected_body_sha256=BODY_SHA)

    def test_authentic_http_get_receipt_replays_to_pass(self):
        raw = render(self.good())
        result = verify_receipt(raw, pin(raw))
        self.assertEqual(result['verdict'], 'pass')
        self.assertEqual(result['recomputed_summary']['body_identity_matches'], 2)
        self.assertEqual(result['original_receipt_sha256'], pin(raw))

    def test_authentic_failed_probe_remains_failed(self):
        raw = render(audit(self.url + '/fail', method='GET', samples=1))
        self.assertEqual(verify_receipt(raw, pin(raw))['verdict'], 'fail')

    def test_partial_get_read_failure_keeps_headers_without_body_acceptance(self):
        failed = audit(self.url + '/ok', samples=1, method='GET')
        item = failed['observations'][0]
        item['transport_error_type'] = 'IncompleteRead'
        item['outcome'] = 'transport_error'
        item['body_sha256'] = None
        item['body_bytes'] = None
        failed['observations_sha256'] = sha256(json.dumps(
            failed['observations'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        failed['summary'] = {
            'successes': 0, 'attempts': 1, 'success_fraction': 0.0,
            'body_identity_matches': None,
            'p95_client_elapsed_ms': item['elapsed_ms'],
            'outcome_counts': {'transport_error': 1},
        }
        failed['verdict'] = 'fail'
        raw = render(failed)
        self.assertEqual(verify_receipt(raw, pin(raw))['verdict'], 'fail')

    def test_original_receipt_pin_rejects_even_one_byte_change(self):
        raw = render(self.good())
        changed = raw + b' '
        with self.assertRaisesRegex(AuditInputError, 'external receipt SHA-256'):
            verify_receipt(changed, pin(raw))

    def test_repinning_fabricated_pass_verdict_cannot_promote_failure(self):
        bad = audit(self.url + '/fail', method='GET', samples=1)
        bad['verdict'] = 'pass'
        raw = render(bad)
        with self.assertRaisesRegex(AuditInputError, 'verdict disagrees'):
            verify_receipt(raw, pin(raw))

    def test_repinning_wrong_body_outcome_cannot_promote_it(self):
        bad = self.good()
        bad['observations'][0]['body_sha256'] = '0' * 64
        bad['observations_sha256'] = sha256(json.dumps(
            bad['observations'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        raw = render(bad)
        with self.assertRaisesRegex(AuditInputError, 'outcome does not follow'):
            verify_receipt(raw, pin(raw))

    def test_repinning_modified_policy_cannot_promote_failed_verdict(self):
        bad = audit(self.url + '/fail', method='GET', samples=1)
        bad['policy']['min_success_fraction'] = 0
        raw = render(bad)
        with self.assertRaisesRegex(AuditInputError, 'verdict disagrees'):
            verify_receipt(raw, pin(raw))

    def test_repinning_latency_and_summary_cannot_hide_invalid_source_binding(self):
        bad = self.good()
        bad['observations'][0]['elapsed_ms'] = -100
        bad['observations_sha256'] = sha256(json.dumps(
            bad['observations'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        raw = render(bad)
        with self.assertRaisesRegex(AuditInputError, 'elapsed time'):
            verify_receipt(raw, pin(raw))

    def test_changed_outer_summary_fails_replay_even_with_matching_pin(self):
        bad = self.good()
        bad['summary']['success_fraction'] = 0.0
        raw = render(bad)
        with self.assertRaisesRegex(AuditInputError, 'summary disagrees'):
            verify_receipt(raw, pin(raw))

    def test_cli_writes_verified_receipt_once_and_returns_verdict(self):
        with TemporaryDirectory() as td:
            original = Path(td) / 'original.json'
            verified = Path(td) / 'verified.json'
            raw = render(self.good())
            original.write_bytes(raw)
            args = ['--receipt', str(original), '--expected-receipt-sha256', pin(raw),
                    '--output', str(verified)]
            self.assertEqual(main(args), 0)
            self.assertEqual(json.loads(verified.read_text())['verdict'], 'pass')
            self.assertEqual(main(args), 2)

    def test_cli_preserves_authenticated_failure_exit_code(self):
        with TemporaryDirectory() as td:
            original = Path(td) / 'failed.json'
            raw = render(audit(self.url + '/fail', samples=1))
            original.write_bytes(raw)
            self.assertEqual(main(['--receipt', str(original),
                                   '--expected-receipt-sha256', pin(raw)]), 1)


if __name__ == '__main__':
    unittest.main()
