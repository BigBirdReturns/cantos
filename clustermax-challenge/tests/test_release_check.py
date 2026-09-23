import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import release_check as rc  # noqa: E402

CLEAN = '# Some page\n\nOrdinary text with [a normal markdown link](https://example.com).\n'
WITH_CONFIRM = '## Disclosure\n\n[CONFIRM: compensation received -- none / describe]\n'
WITH_PLACEHOLDER = '## Disclosure\n\nRelationship: [TBD]\n'
WITH_BARE_TOKEN = '## Disclosure\n\nStatus: ???\n'


class ReleaseCheckTests(unittest.TestCase):
    def test_clean_file_passes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'page.md'
            path.write_text(CLEAN, encoding='utf-8')
            self.assertEqual(rc.check_file(path), [])
            self.assertEqual(rc.main([str(path)]), 0)

    def test_confirm_marker_fails(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'page.md'
            path.write_text(WITH_CONFIRM, encoding='utf-8')
            hits = rc.check_file(path)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0][1], 'CONFIRM marker')
            self.assertEqual(rc.main([str(path)]), 1)

    def test_other_placeholder_fails(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'page.md'
            path.write_text(WITH_PLACEHOLDER, encoding='utf-8')
            hits = rc.check_file(path)
            self.assertEqual(len(hits), 1)
            self.assertEqual(rc.main([str(path)]), 1)

    def test_bare_triple_question_mark_fails(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'page.md'
            path.write_text(WITH_BARE_TOKEN, encoding='utf-8')
            hits = rc.check_file(path)
            self.assertEqual(len(hits), 1)
            self.assertEqual(rc.main([str(path)]), 1)

    def test_markdown_links_are_not_false_positives(self):
        text = '# Title\n\nSee [the protocol](README.md) and [source and tests](https://example.com).\n'
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'page.md'
            path.write_text(text, encoding='utf-8')
            self.assertEqual(rc.check_file(path), [])

    def test_repo_files_currently_clean(self):
        # The repo's own index.html/README.md Disclosure sections have been answered
        # with real text (no [CONFIRM: ...] or other placeholder markers remain), so
        # this human-facing release gate passes on the real files.
        self.assertEqual(rc.main([]), 0)


if __name__ == '__main__':
    unittest.main()
