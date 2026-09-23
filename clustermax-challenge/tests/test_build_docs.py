import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_docs  # noqa: E402


class TestBuildDocsUpToDate(unittest.TestCase):
    """The generated .html siblings in the repo must exactly match what
    build_docs.py would currently produce from their .md sources -- this is
    what stops the rendered docs from silently drifting from the markdown."""

    def test_check_passes_on_committed_output(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / 'build_docs.py'), '--check'],
            cwd=str(ROOT), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

    def test_every_doc_has_a_generated_sibling(self):
        for rel_path in build_docs.DOCS:
            out_path = (ROOT / rel_path).with_suffix('.html')
            self.assertTrue(out_path.exists(), f'missing generated doc: {out_path}')


class TestMarkdownConverter(unittest.TestCase):
    def test_heading_gets_stable_id(self):
        title, body = build_docs.markdown_to_html('# Hello World\n\nSome text.\n')
        self.assertEqual(title, 'Hello World')
        self.assertIn('<h1 id="hello-world">Hello World</h1>', body)

    def test_relative_md_link_rewritten_to_html(self):
        _, body = build_docs.markdown_to_html('See [the plan](retrospective/PLAN.md) for details.\n')
        self.assertIn('href="retrospective/PLAN.html"', body)

    def test_absolute_link_untouched(self):
        url = 'https://example.com/foo.md'
        _, body = build_docs.markdown_to_html(f'[link]({url})\n')
        self.assertIn(f'href="{url}"', body)

    def test_bold_italic_code(self):
        _, body = build_docs.markdown_to_html('**bold** and `code` and plain text.\n')
        self.assertIn('<strong>bold</strong>', body)
        self.assertIn('<code>code</code>', body)

    def test_intraword_underscore_is_not_italic(self):
        _, body = build_docs.markdown_to_html('The field NOT_IN_REVIEWED_SOURCES is a status.\n')
        self.assertNotIn('<em>', body)
        self.assertIn('NOT_IN_REVIEWED_SOURCES', body)

    def test_fenced_code_block(self):
        _, body = build_docs.markdown_to_html('```sh\npython foo.py\n```\n')
        self.assertIn('<pre><code class="language-sh">python foo.py</code></pre>', body)

    def test_nested_list(self):
        md = '* top\n  * nested one\n  * nested two\n* top two\n'
        _, body = build_docs.markdown_to_html(md)
        self.assertEqual(body.count('<ul>'), 2)
        self.assertIn('nested one', body)

    def test_ordered_list(self):
        _, body = build_docs.markdown_to_html('1. first\n2. second\n')
        self.assertIn('<ol>', body)
        self.assertIn('<li>first</li>', body)

    def test_table(self):
        md = '| A | B |\n| - | - |\n| 1 | 2 |\n'
        _, body = build_docs.markdown_to_html(md)
        self.assertIn('<table>', body)
        self.assertIn('<th>A</th>', body)
        self.assertIn('<td>1</td>', body)


if __name__ == '__main__':
    unittest.main()
