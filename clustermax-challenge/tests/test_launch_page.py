"""launch/index.html's per-provider, per-dimension table must not silently
drift from launch/claims-3.0.observed.json -- this test parses both and
checks every provider/field status shown on the page matches the ledger."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('scope', 'observation_conditions', 'evidence', 'test_dates', 'predictive_check')

_ROW_RE = re.compile(
    r'<tr><td>([^<]+)</td><td>([^<]+)</td>'
    r'(?:<td><span class="st st-([A-Z_]+)"[^>]*>[A-Z_]+</span></td>){5}</tr>',
)
# Capture each of the five status spans within a row separately (the pattern
# above only anchors the row shape; this one pulls all five statuses out).
_STATUS_RE = re.compile(r'<span class="st st-([A-Z_]+)"')


class LaunchPageMatchesLedger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads((ROOT / 'launch' / 'claims-3.0.observed.json').read_text(encoding='utf-8'))
        cls.page = (ROOT / 'launch' / 'index.html').read_text(encoding='utf-8')

    def test_per_dimension_table_present_for_every_ledger_provider(self):
        # Isolate the "Per-provider, per-dimension" table body.
        start = self.page.index('Per-provider, per-dimension review status')
        table_html = self.page[start:]
        for provider, entry in self.ledger['medals'].items():
            row_marker = f'<tr><td>{provider}</td><td>{entry["medal"]}</td>'
            self.assertIn(row_marker, table_html, f'missing/mismatched row for {provider}')
            row_start = table_html.index(row_marker)
            row_end = table_html.index('</tr>', row_start)
            row = table_html[row_start:row_end]
            statuses = _STATUS_RE.findall(row)
            self.assertEqual(len(statuses), 5, f'{provider}: expected 5 status badges, found {len(statuses)}')
            expected = [entry[f]['status'] for f in FIELDS]
            self.assertEqual(statuses, expected, f'{provider}: status mismatch')

    def test_medal_table_and_rubric_sources_referenced(self):
        self.assertIn(self.ledger['medal_table_source']['url'], self.page)
        self.assertIn('NOT_VERIFIED_FOR_3.0', self.page)


if __name__ == '__main__':
    unittest.main()
