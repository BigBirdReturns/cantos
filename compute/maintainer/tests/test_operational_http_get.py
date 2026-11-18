"""Observed HTTP GET body identity from an explicitly authorized endpoint."""
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from compute.maintainer.operational_http import audit, AuditInputError, main

BODY = b'cantos-observed-owned-service-v1\n'
DIGEST = sha256(BODY).hexdigest()


class GETHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        codes = {'/health': 200, '/large': 200, '/unhealthy': 503, '/redirect': 302, '/incomplete': 200}
        code = codes.get(self.path, 404)
        self.send_response(code)
        if self.path == '/redirect':
            self.send_header('Location', '/health')
        body = b'X' * 4096 if self.path == '/large' else (BODY if code == 200 else b'failure')
        declared_length = len(body) + 13 if self.path == '/incomplete' else len(body)
        self.send_header('Content-Length', str(declared_length))
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def log_message(self, *args):
        pass


class HTTPBodyIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), GETHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_get_observation_matches_exact_expected_body(self):
        result = audit(self.url + '/health', method='GET', samples=2, expected_body_sha256=DIGEST)
        self.assertEqual(result['verdict'], 'pass')
        self.assertEqual(result['method'], 'GET')
        self.assertEqual(result['summary']['body_identity_matches'], 2)
        self.assertEqual(result['observations'][0]['body_sha256'], DIGEST)
        self.assertEqual(result['observations'][0]['body_bytes'], len(BODY))
        self.assertEqual(result['summary']['outcome_counts'], {'http_success': 2})

    def test_valid_http_status_with_wrong_body_fails(self):
        result = audit(self.url + '/health', method='GET', samples=1,
                       expected_body_sha256='0' * 64)
        self.assertEqual(result['summary']['outcome_counts'], {'http_body_mismatch': 1})
        self.assertEqual(result['verdict'], 'fail')
        self.assertEqual(result['observations'][0]['http_status'], 200)
        self.assertEqual(result['observations'][0]['body_sha256'], DIGEST)

    def test_digest_requirement_cannot_be_disabled_by_zero_threshold(self):
        result = audit(self.url + '/health', method='GET', samples=1,
                       expected_body_sha256='0' * 64, min_success_fraction=0.0)
        self.assertEqual(result['verdict'], 'fail')
        result = audit(self.url + '/unhealthy', method='GET', samples=1,
                       expected_body_sha256=DIGEST, min_success_fraction=0.0)
        self.assertEqual(result['verdict'], 'fail')

    def test_body_limit_prevents_acceptance(self):
        result = audit(self.url + '/large', method='GET', max_body_bytes=32, samples=1)
        self.assertEqual(result['summary']['outcome_counts'], {'http_body_limit_exceeded': 1})
        self.assertEqual(result['observations'][0]['body_bytes'], 33)
        self.assertIsNone(result['observations'][0]['body_sha256'])
        self.assertEqual(result['verdict'], 'fail')

    def test_declared_body_truncation_refuses_acceptance(self):
        result = audit(self.url + '/incomplete', method='GET', samples=1,
                       expected_body_sha256=DIGEST)
        self.assertEqual(result['summary']['outcome_counts'], {'http_body_incomplete': 1})
        self.assertIsNone(result['observations'][0]['body_sha256'])
        self.assertEqual(result['verdict'], 'fail')

    def test_get_ignores_environment_proxy(self):
        with patch.dict(os.environ, {'http_proxy': 'http://127.0.0.1:1',
                                     'HTTP_PROXY': 'http://127.0.0.1:1',
                                     'no_proxy': '', 'NO_PROXY': ''}):
            r = audit(self.url + '/health', method='GET', samples=1,
                      expected_body_sha256=DIGEST)
        self.assertEqual(r['verdict'], 'pass')

    def test_server_failure_retains_original_status(self):
        result = audit(self.url + '/unhealthy', method='GET', samples=1,
                       expected_body_sha256=DIGEST)
        self.assertEqual(result['summary']['outcome_counts'], {'http_server_failure': 1})
        self.assertEqual(result['observations'][0]['http_status'], 503)
        self.assertEqual(result['verdict'], 'fail')

    def test_get_redirect_never_reaches_destination(self):
        result = audit(self.url + '/redirect', method='GET', samples=1)
        self.assertEqual(result['summary']['outcome_counts'], {'http_redirect_not_followed': 1})
        self.assertEqual(result['observations'][0]['http_status'], 302)

    def test_requires_get_for_expected_digest(self):
        with self.assertRaises(AuditInputError):
            audit(self.url + '/health', method='HEAD', expected_body_sha256=DIGEST)

    def test_validates_digest_and_body_limit_before_network(self):
        for opts in ({'method': 'GET', 'expected_body_sha256': 'wrong'},
                     {'method': 'GET', 'max_body_bytes': 0},
                     {'method': 'GET', 'max_body_bytes': 2_000_000},
                     {'method': 'PUT'}):
            with self.subTest(opts=opts), self.assertRaises(AuditInputError):
                audit(self.url + '/health', **opts)

    def test_cli_get_writes_observation_once(self):
        with TemporaryDirectory() as tmp:
            receipt = Path(tmp) / 'receipt.json'
            args = ['--url', self.url + '/health', '--method', 'GET',
                    '--expected-body-sha256', DIGEST, '--samples', '1',
                    '--output', str(receipt)]
            self.assertEqual(main(args), 0)
            self.assertEqual(json.loads(receipt.read_text())['summary']['body_identity_matches'], 1)
            self.assertEqual(main(args), 2)


if __name__ == '__main__':
    unittest.main()
