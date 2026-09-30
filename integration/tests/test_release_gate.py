"""Publication must follow source-matched native qualification, never merely a push."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import release_gate as gate

class ReleaseGateTests(unittest.TestCase):
    target = {'compute': 'same-source'}
    def run_row(self, number=1, conclusion='success', status='completed', event='push', sha='a'*40):
        return dict(id=number, conclusion=conclusion, status=status, event=event,
                    head_sha=sha, created_at='2026-09-23T01:00:00Z')
    def decide(self, rows, signatures=None):
        return gate.decide(rows, self.target, lambda sha: (signatures or {}).get(sha, self.target))
    def test_success_matches_source(self):
        self.assertEqual(self.decide([self.run_row()])['state'], 'PASS')
    def test_failed_source_holds(self):
        self.assertEqual(self.decide([self.run_row(conclusion='failure')])['state'], 'HOLD')
    def test_new_failure_outweighs_old_green(self):
        rows=[self.run_row(1),self.run_row(2,conclusion='failure')]
        self.assertEqual(self.decide(rows)['state'], 'HOLD')
    def test_new_pending_run_waits(self):
        rows=[self.run_row(1),self.run_row(2,conclusion=None,status='in_progress')]
        self.assertEqual(self.decide(rows)['state'], 'WAIT')
    def test_old_green_cannot_bless_changed_source(self):
        row=self.run_row()
        self.assertEqual(self.decide([row],{row['head_sha']:{'compute':'old-source'}})['state'], 'WAIT')
    def test_workspace_change_cannot_reuse_compute_only_qualification(self):
        self.assertTrue({'README.md', 'app', 'index.html', 'assets'}.issubset(gate.SCOPES))
        current = {p: 'current' for p in gate.SCOPES}
        for changed in ('README.md', 'app', 'index.html', 'assets'):
            previous = dict(current, **{changed: 'previous'})
            verdict = gate.decide([self.run_row()], current, lambda sha: previous)
            self.assertEqual(verdict['state'], 'WAIT', changed)
    def test_data_only_revision_can_reuse_identical_sources(self):
        row=self.run_row(sha='b'*40)
        self.assertEqual(self.decide([row])['tested_commit'], 'b'*40)
    def test_pr_head_is_not_assumed_tested_merge(self):
        self.assertEqual(self.decide([self.run_row(event='pull_request')])['state'], 'WAIT')
    def test_skipped_cancelled_and_timed_out_hold(self):
        for conclusion in ['skipped','cancelled','timed_out','neutral']:
            self.assertEqual(self.decide([self.run_row(conclusion=conclusion)])['state'], 'HOLD')
    def test_empty_history_waits(self):
        self.assertEqual(self.decide([])['state'], 'WAIT')
    def test_dirty_sources_are_rejected(self):
        with patch.object(gate, 'git', return_value=' M compute/index.html'):
            with self.assertRaises(RuntimeError): gate.local_signature()
    @staticmethod
    def publishers():
        """Workflows that publish a Pages artifact. Zero is allowed: Pages may be served from the branch."""
        out = []
        for p in sorted((gate.ROOT/'.github/workflows').glob('*.yml')):
            text = p.read_text(encoding='utf-8')
            if 'uses: actions/upload-pages-artifact@' in text:
                out.append((p.name, text))
        return out
    def test_every_pages_publisher_has_gate_before_upload(self):
        for name, text in self.publishers():
            self.assertIn('python integration/release_gate.py', text, name)
            self.assertLess(text.index('python integration/release_gate.py'), text.index('uses: actions/upload-pages-artifact@'), name)
            self.assertIn('actions: read', text, name)
    def test_gate_cannot_be_soft_failed(self):
        for name, text in self.publishers():
            i = text.index('python integration/release_gate.py')
            start = text.rfind('      - name:', 0, i)
            segment = text[start if start >= 0 else i:].split(chr(10) + '      - ', 1)[0]
            self.assertNotIn('continue-on-error', segment, name)
            self.assertNotIn('|| true', segment, name)

if __name__=='__main__': unittest.main()
