#!/usr/bin/env python3
"""Release-readiness gate: fails while an unanswered disclosure placeholder remains.

Scans each file's own "Disclosure" section (the `<summary>Disclosure</summary>`
block in index.html, the `## Disclosure` section in README.md) for the
"[CONFIRM" marker convention this repo uses for questions only a human can
answer, and for other bracketed disclosure placeholders ("[TBD]", "[TODO]",
"none / describe", a bare "???", etc.).

Scoped to the Disclosure section on purpose: index.html's embedded engine
script legitimately contains the literal token strings this check looks for
(challenge.py's PLACEHOLDER_TOKENS, mirrored in JS) inside an array literal,
and README.md documents the same token list in prose elsewhere -- neither is
an unanswered disclosure, and a whole-file scan flags both as false positives.

This is a SEPARATE, human-facing gate from the test suite: the tests
(challenge.py's own evaluate(), which requires plan.json's disclosure object
to be answered) can be fully green while this script stays red until a human
fills in the real answer here. Nothing in this repo answers these markers
automatically, and this script does not either -- it only reports where they
still are. Stdlib only.

Exit code 0: no markers found. Exit code 1: one or more markers found (each
printed as `<path>:<line>: <kind>: <text>`).
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILES = ('index.html', 'README.md')

# Same placeholder vocabulary as challenge.py's disclosure check, minus '[' --
# here bracket-detection itself does that job, so we don't flag every markdown
# link. '???' is also checked standalone, since it need not sit in brackets.
BRACKET_RE = re.compile(r'\[([^\[\]]{0,240})\]')
PLACEHOLDER_TOKENS = ('confirm', 'unknown', 'unconfirmed', 'tbd', 'todo', 'pending', 'describe')
BARE_TOKEN_RE = re.compile(r'\?\?\?')

# HTML: the <details><summary>Disclosure</summary>...</details> block.
HTML_SECTION_RE = re.compile(r'<summary>\s*Disclosure\s*</summary>(.*?)</details>',
                              re.IGNORECASE | re.DOTALL)
# Markdown: a "## Disclosure" (or similar) heading through the next heading of
# the same or shallower level, or end of file.
MD_SECTION_RE = re.compile(r'^#{1,6}[ \t]*Disclosures?\b[^\n]*\n(.*?)(?=^#{1,6}[ \t]|\Z)',
                            re.IGNORECASE | re.MULTILINE | re.DOTALL)


def disclosure_sections(text_content: str):
    """Yield (absolute_start_offset, section_text) for each Disclosure section found."""
    for pattern in (HTML_SECTION_RE, MD_SECTION_RE):
        for m in pattern.finditer(text_content):
            yield m.start(1), m.group(1)


def find_markers(text_content: str):
    """Yield (line_number, kind, snippet) for each placeholder found in a Disclosure section."""
    hits = []
    for start, section in disclosure_sections(text_content):
        for m in BRACKET_RE.finditer(section):
            inner = m.group(1)
            lowered = inner.lower()
            hit_tokens = [tok for tok in PLACEHOLDER_TOKENS if tok in lowered]
            if hit_tokens:
                abs_pos = start + m.start()
                lineno = text_content.count('\n', 0, abs_pos) + 1
                kind = 'CONFIRM marker' if 'confirm' in hit_tokens else 'disclosure placeholder'
                hits.append((lineno, kind, m.group(0).strip()))
        for m in BARE_TOKEN_RE.finditer(section):
            abs_pos = start + m.start()
            lineno = text_content.count('\n', 0, abs_pos) + 1
            hits.append((lineno, 'disclosure placeholder', '???'))
    hits.sort(key=lambda h: h[0])
    return hits


def check_file(path: Path):
    if not path.exists():
        return []
    return find_markers(path.read_text(encoding='utf-8'))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    paths = [Path(a) for a in argv] if argv else [ROOT / name for name in DEFAULT_FILES]
    total = 0
    for path in paths:
        for lineno, kind, snippet in check_file(path):
            print(f'{path}:{lineno}: {kind}: {snippet}')
            total += 1
    if total:
        print(f'release-readiness: {total} unresolved marker(s)')
        return 1
    print('release-readiness: clean')
    return 0


if __name__ == '__main__':
    sys.exit(main())
