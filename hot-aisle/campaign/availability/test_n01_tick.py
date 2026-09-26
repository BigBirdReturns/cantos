"""Failure propagation through N01's real tick entry, without network calls."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import n01_tick as n


class TickFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TEST_TMPDIR'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root/'config.json'
        self.config.write_text(json.dumps({
            'state_dir': str(self.root), 'peer_control': str(self.root),
            'seat_python': 'fixture-python', 'seat_script': 'fixture-supervision.py',
            'seat_config': 'fixture-private.json', 'seat_peer': 'OCTO-W01',
            'seat_state_dir': str(self.root), 'expires_utc': '2099-01-01T00:00:00+00:00',
            'timer_unit': 'fixture.timer',
        }))

    def invoke(self, envelope):
        estate = Mock()
        estate.write_artifacts.return_value = (self.root/'ssh_config', self.root/'known_hosts')
        estate.powershell_invocation.return_value = "& 'fixture-python' '-B' 'fixture-supervision.py'"
        estate.run_peer_script.return_value = dict(envelope)
        output = io.StringIO()
        with patch.dict(n.sys.modules, {'estate_peer': estate}), \
             patch.object(n.sys, 'argv', ['n01_tick.py', '--config', str(self.config)]), \
             patch.object(n.sys, 'path', list(n.sys.path)), \
             patch.object(n.subprocess, 'run', side_effect=AssertionError('unexpected local service operation')), \
             redirect_stdout(output):
            code = n.main()
        return code, json.loads(output.getvalue()), estate

    def test_nonzero_seat_result_retains_campaign_and_transport_failure(self):
        for status in ('unknown', 'monitor_failed', 'release_unconfirmed'):
            with self.subTest(status=status):
                code, result, estate = self.invoke({
                    'ok': False, 'classification': 'COMMAND_FAILURE', 'canonical_ingress': True,
                    'exit_code': 1, 'stdout': json.dumps({'status': status, 'returncode': 1}),
                    'stderr': '',
                })
                self.assertEqual(code, 1)
                self.assertEqual(result['classification'], 'COMMAND_FAILURE')
                self.assertTrue(result['canonical_ingress'])
                self.assertEqual(result['exit_code'], 1)
                self.assertEqual(result['campaign']['status'], status)
                self.assertEqual(json.loads((self.root/'latest.json').read_text())['campaign']['status'], status)
                self.assertTrue(estate.run_peer_script.call_args.args[1].endswith('\nexit $LASTEXITCODE'))

    def test_transport_failure_keeps_its_original_classification(self):
        code, result, _ = self.invoke({
            'ok': False, 'classification': 'CONTROL_PATH_REGRESSION', 'canonical_ingress': False,
            'exit_code': 255, 'stdout': '', 'stderr': 'fixture control-path failure',
        })
        self.assertEqual(code, 1)
        self.assertEqual(result['classification'], 'CONTROL_PATH_REGRESSION')
        self.assertNotIn('campaign', result)
        self.assertNotIn('campaign_response_error', result)

    def test_malformed_output_fails_without_relabelling_transport(self):
        for body in ('truncated{', '[]', ''):
            with self.subTest(body=body):
                code, result, _ = self.invoke({'ok': True, 'classification': 'PASS',
                                               'canonical_ingress': True, 'stdout': body, 'exit_code': 0})
                self.assertEqual(code, 1)
                self.assertEqual(result['classification'], 'PASS')
                self.assertIn('INVALID_CAMPAIGN_RESPONSE', result['campaign_response_error'])

    def test_normal_wait_remains_success(self):
        code, result, _ = self.invoke({'ok': True, 'classification': 'PASS',
                                       'stdout': '{"status": "waiting_capacity"}', 'exit_code': 0})
        self.assertEqual(code, 0)
        self.assertEqual(result['campaign']['status'], 'waiting_capacity')
        self.assertNotIn('campaign_response_error', result)


if __name__ == '__main__':
    unittest.main()
