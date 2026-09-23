#!/usr/bin/env python3
"""Render this repo's standing docs as styled, readable HTML siblings.

GitHub Pages serves *.md with Content-Type: text/markdown -- browsers show raw
source (literal '# heading', '**bold**', no clickable links, no heading
anchors). This script is a small, dependency-free Markdown -> HTML converter
(headings with stable ids, paragraphs, bold/italic/inline code, fenced code
blocks, ordered/unordered lists with one level of nesting, links, and GFM-style
pipe tables) that is deliberately just powerful enough for the docs in DOCS
below -- it is not a general CommonMark implementation.

The .md files remain the authority: this script only ever reads them and
writes a same-named .html sibling next to each one. Relative links to another
.md file in DOCS are rewritten to the sibling .html; everything else (http(s)
links, .json, .html, .py links) passes through unchanged.

Usage:
  python scripts/build_docs.py            # (re)generate every doc's .html sibling
  python scripts/build_docs.py --check    # exit 1 if any generated file is stale

Stdlib only.
"""
from __future__ import annotations

import argparse
import html as _html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Paths are relative to ROOT (the clustermax-challenge/ directory). Each gets a
# same-named .html sibling written next to the .md source.
DOCS = [
    'README.md',
    'SUBMITTING.md',
    'launch/README.md',
    'retrospective/PLAN.md',
    'retrospective/READOUT.md',
    'retrospective/incidents/INELIGIBLE.md',
    'retrospective/results/R1-result.md',
]

# --------------------------------------------------------------------------- #
# inline markdown -> HTML
# --------------------------------------------------------------------------- #

_CODE_SPAN_RE = re.compile(r'`([^`]+)`')
_LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)\s]+)\)')
_BOLD_RE = re.compile(r'\*\*([^*]+)\*\*|__([^_]+)__')
# The `_..._` alternative requires non-word-character boundaries (CommonMark's
# "intraword underscore" rule) so identifiers like NOT_IN_REVIEWED_SOURCES are
# never misread as emphasis.
_ITALIC_RE = re.compile(r'(?<!\*)\*([^*\n]+)\*(?!\*)|(?<!\w)_([^_\n]+)_(?!\w)')
_PLACEHOLDER_RE = re.compile(r'\x00(\d+)\x00')


def slugify(text: str) -> str:
    # Strip markdown inline syntax before slugging so headings that carry
    # `code` or **bold** still get a plain, predictable id.
    plain = re.sub(r'[`*_]', '', text)
    plain = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', plain)
    slug = re.sub(r'[^a-z0-9]+', '-', plain.strip().lower()).strip('-')
    return slug or 'section'


def rewrite_href(url: str) -> str:
    """A relative link ending in .md (optionally with a #fragment) points at
    its generated .html sibling instead. Absolute URLs and non-.md links are
    untouched."""
    if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', url):  # has a scheme (http:, mailto:, ...)
        return url
    m = re.match(r'^([^#?]*\.md)([#?].*)?$', url)
    if not m:
        return url
    return m.group(1)[:-3] + '.html' + (m.group(2) or '')


def render_inline(text: str) -> str:
    text = _html.escape(text, quote=False)
    placeholders: list[str] = []

    def stash(fragment: str) -> str:
        placeholders.append(fragment)
        return f'\x00{len(placeholders) - 1}\x00'

    def code_repl(m: re.Match) -> str:
        return stash(f'<code>{m.group(1)}</code>')

    text = _CODE_SPAN_RE.sub(code_repl, text)

    def link_repl(m: re.Match) -> str:
        # label/url are substrings of `text`, which is already HTML-escaped
        # and has had its code spans replaced by \x00N\x00 placeholders -- do
        # NOT re-run render_inline() on label here (it would try to resolve
        # those placeholders against a fresh, empty placeholder list). Bold
        # and italic inside a link label aren't used anywhere in these docs,
        # so the label is emitted as-is and any embedded placeholder is fixed
        # up by this same call's restore loop below.
        label, url = m.group(1), m.group(2)
        href = _html.escape(rewrite_href(url), quote=True)
        return stash(f'<a href="{href}">{label}</a>')

    text = _LINK_RE.sub(link_repl, text)
    text = _BOLD_RE.sub(lambda m: f'<strong>{m.group(1) or m.group(2)}</strong>', text)
    text = _ITALIC_RE.sub(lambda m: f'<em>{m.group(1) or m.group(2)}</em>', text)

    def restore(m: re.Match) -> str:
        return placeholders[int(m.group(1))]

    # Placeholders can nest (a link label containing inline code), so restore
    # repeatedly until none remain.
    while _PLACEHOLDER_RE.search(text):
        text = _PLACEHOLDER_RE.sub(restore, text)
    return text


# --------------------------------------------------------------------------- #
# block-level parsing
# --------------------------------------------------------------------------- #

_HEADING_RE = re.compile(r'^(#{1,6})\s+(.*?)\s*#*$')
_FENCE_RE = re.compile(r'^```(\w*)\s*$')
_LIST_ITEM_RE = re.compile(r'^( {0,3})([-*+]|\d+[.)])\s+(.*)$')
_TABLE_SEP_RE = re.compile(r'^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$')


def is_table_sep(line: str) -> bool:
    return bool(line.strip()) and bool(_TABLE_SEP_RE.match(line))


def split_table_row(line: str) -> list[str]:
    row = line.strip()
    if row.startswith('|'):
        row = row[1:]
    if row.endswith('|'):
        row = row[:-1]
    return [cell.strip() for cell in row.split('|')]


def render_table(lines: list[str]) -> str:
    header = split_table_row(lines[0])
    body_rows = [split_table_row(l) for l in lines[2:] if l.strip()]
    out = ['<table>', '<thead><tr>']
    out += [f'<th>{render_inline(c)}</th>' for c in header]
    out.append('</tr></thead><tbody>')
    for row in body_rows:
        out.append('<tr>' + ''.join(f'<td>{render_inline(c)}</td>' for c in row) + '</tr>')
    out.append('</tbody></table>')
    return ''.join(out)


def collect_list(lines: list[str], start: int, indent0: int):
    """Consume a run of list items starting at lines[start], all markers at
    indentation indent0. Returns (next_index, html)."""
    n = len(lines)
    i = start
    ordered = None
    items: list[list] = []  # [content_lines, content_indent]
    while i < n:
        line = lines[i]
        if line.strip() == '':
            j = i
            while j < n and lines[j].strip() == '':
                j += 1
            if j >= n:
                i = j
                break
            nxt = lines[j]
            nxt_indent = len(nxt) - len(nxt.lstrip(' '))
            if items and (nxt_indent >= indent0):
                items[-1][0].append('')
                i += 1
                continue
            break
        m = _LIST_ITEM_RE.match(line)
        cur_indent = len(line) - len(line.lstrip(' '))
        if m and cur_indent == indent0:
            marker = m.group(2)
            is_ordered = marker[0].isdigit()
            if ordered is None:
                ordered = is_ordered
            content_indent = len(m.group(1)) + len(marker) + 1
            items.append([[m.group(3)], content_indent])
            i += 1
        elif items and cur_indent > indent0:
            content_indent = items[-1][1]
            dedented = line[content_indent:] if len(line) >= content_indent else line.lstrip(' ')
            items[-1][0].append(dedented)
            i += 1
        else:
            break
    tag = 'ol' if ordered else 'ul'
    out = [f'<{tag}>']
    for content_lines, _ in items:
        while content_lines and content_lines[-1] == '':
            content_lines.pop()
        inner = parse_blocks(content_lines)
        if inner.startswith('<p>') and inner.endswith('</p>') and inner.count('<p>') == 1:
            inner = inner[3:-4]
        out.append(f'<li>{inner}</li>')
    out.append(f'</{tag}>')
    return i, '\n'.join(out)


def parse_blocks(lines: list[str]) -> str:
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if line.strip() == '':
            i += 1
            continue
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            raw_text = m.group(2)
            slug = slugify(raw_text)
            out.append(f'<h{level} id="{slug}">{render_inline(raw_text)}</h{level}>')
            i += 1
            continue
        m = _FENCE_RE.match(line)
        if m:
            lang = m.group(1)
            i += 1
            code_lines = []
            while i < n and lines[i].strip() != '```':
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1
            code = _html.escape('\n'.join(code_lines), quote=False)
            cls = f' class="language-{lang}"' if lang else ''
            out.append(f'<pre><code{cls}>{code}</code></pre>')
            continue
        if '|' in line and i + 1 < n and is_table_sep(lines[i + 1]):
            j = i + 2
            while j < n and lines[j].strip() != '' and '|' in lines[j]:
                j += 1
            out.append(render_table(lines[i:j]))
            i = j
            continue
        m = _LIST_ITEM_RE.match(line)
        if m and len(m.group(1)) == 0:
            i, list_html = collect_list(lines, i, 0)
            out.append(list_html)
            continue
        para_lines = [line]
        i += 1
        while i < n and lines[i].strip() != '' and not _HEADING_RE.match(lines[i]) \
                and not _FENCE_RE.match(lines[i]) and not _LIST_ITEM_RE.match(lines[i]):
            para_lines.append(lines[i])
            i += 1
        text = ' '.join(l.strip() for l in para_lines)
        out.append(f'<p>{render_inline(text)}</p>')
    return '\n'.join(out)


def markdown_to_html(source: str) -> tuple[str, str]:
    """Returns (title, body_html). Title is the text of the first H1, or a
    fallback."""
    lines = source.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    body_html = parse_blocks(lines)
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', body_html)
    if title_match:
        title = re.sub(r'<[^>]+>', '', title_match.group(1))
    else:
        title = 'SecondRun / ClusterMAX Challenge'
    return title, body_html


# --------------------------------------------------------------------------- #
# page shell -- same tokens as index.html / launch/index.html, plus a light variant
# --------------------------------------------------------------------------- #

_CSS = """
:root{color-scheme:dark light;--bg:#111114;--ink:#f5f2f1;--muted:#aaa6ab;--line:#353239;--pink:#ff5d96;--panel:#1a191e}
@media(prefers-color-scheme:light){:root{--bg:#fbfafb;--ink:#17151a;--muted:#5b5560;--line:#ddd8de;--pink:#c81760;--panel:#f1eef1}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:760px;margin:auto;padding:26px 20px 64px}
nav{display:flex;gap:18px;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:8px;font-size:14px}
nav .brand{color:var(--pink);font-weight:700}
a{color:var(--ink);text-underline-offset:3px;overflow-wrap:anywhere}
a:hover{color:var(--pink)}
h1{font-size:clamp(28px,6vw,42px);line-height:1.15;letter-spacing:-.03em;margin:26px 0 14px}
h2{font-size:22px;letter-spacing:-.02em;margin:34px 0 10px;border-top:1px solid var(--line);padding-top:20px}
h3{font-size:18px;margin:22px 0 8px}
h4{font-size:16px;margin:18px 0 6px;color:var(--muted)}
p{margin:12px 0}
ul,ol{padding-left:22px}
li{margin:6px 0}
code{background:var(--panel);border:1px solid var(--line);border-radius:3px;padding:.1em .35em;font-size:.9em;overflow-wrap:anywhere}
pre{background:var(--panel);border:1px solid var(--line);border-radius:5px;padding:14px;overflow-x:auto;font-size:13px;line-height:1.5}
pre code{background:none;border:none;padding:0}
table{border-collapse:collapse;width:100%;font-size:14px;margin:14px 0;display:block;overflow-x:auto}
th,td{text-align:left;border-bottom:1px solid var(--line);padding:8px 10px;overflow-wrap:anywhere}
th{color:var(--muted);font-weight:600}
.muted{color:var(--muted);font-size:13px}
footer{border-top:1px solid var(--line);margin-top:40px;padding-top:16px;font-size:12px;color:var(--muted)}
@media(max-width:400px){main{padding:18px 14px 44px}h1{margin-top:16px}pre{font-size:12px;padding:10px}}
""".strip()


def relative_prefix(rel_path: str) -> str:
    depth = rel_path.count('/')
    return '../' * depth


def render_page(rel_path: str, title: str, body_html: str) -> str:
    prefix = relative_prefix(rel_path)
    source_name = Path(rel_path).name
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html.escape(title)} | SecondRun</title>
<meta name="description" content="ClusterMAX Challenge documentation, rendered from {_html.escape(source_name)}.">
<style>{_CSS}</style></head><body><main>
<nav><span class="brand">SecondRun</span><a href="{prefix}index.html">Open the test</a><a href="{prefix}README.html">Protocol</a><a href="{prefix}SUBMITTING.html">Submit records</a><a href="{source_name}">View source (.md)</a></nav>
{body_html}
<footer>Rendered from <a href="{source_name}">{_html.escape(source_name)}</a>, the authoritative source -- this page is generated by <code>scripts/build_docs.py</code> and never hand-edited. <a href="https://github.com/BigBirdReturns/axm-tools/tree/main/clustermax-challenge">Source and tests</a>.</footer>
</main></body></html>
'''


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_one(rel_path: str) -> tuple[Path, str]:
    src = ROOT / rel_path
    title, body_html = markdown_to_html(src.read_text(encoding='utf-8'))
    out_path = src.with_suffix('.html')
    rendered = render_page(rel_path, title, body_html)
    return out_path, rendered


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--check', action='store_true', help='exit 1 if any generated .html is stale or missing')
    args = ap.parse_args(argv)

    stale = []
    for rel_path in DOCS:
        out_path, rendered = build_one(rel_path)
        current = out_path.read_text(encoding='utf-8') if out_path.exists() else None
        if current == rendered:
            continue
        if args.check:
            stale.append(str(out_path.relative_to(ROOT)))
        else:
            out_path.write_text(rendered, encoding='utf-8')
            print(f'wrote {out_path.relative_to(ROOT)}')

    if args.check:
        if stale:
            print('Stale generated docs (run `python scripts/build_docs.py` to refresh):', file=sys.stderr)
            for s in stale:
                print(f'  {s}', file=sys.stderr)
            return 1
        print('All generated docs are up to date.')
        return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
