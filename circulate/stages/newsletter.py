"""Stage newsletter: SemiAnalysis newsletter posts not yet in the Research Desk packet.

Reads newsletter.semianalysis.com/sitemap.xml, drops every /p/<slug> URL already known (source records `sa-post-*`
in the committed packet, and rows already appended to research-desk/packets/newsletter-standing.jsonl), fetches at
most MAX_NEW of the rest, and appends one row per post. Raw HTML goes to retained/.

Extractor fix: the sa-newsletter lane's extractor fed every text node of the page to its word counter, so its
"free_preview_text" began with CSS and JSON-LD from the page head. extract_article() below reads only the visible
text inside the article body (`div.available-content`, falling back to `div.body.markup`), skips script/style/svg/
button and subscription-widget subtrees, and never reads past the paywall (the paywall element is a sibling after
the article body; its presence sets paywalled=true). A page with no recognizable body gets an empty preview and a
warning, never a guess.
"""
from __future__ import annotations

import json
import re
import time
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

from stages._common import HOLD, OK, SKIP, Hold, Stage, iso, read_json, sha256_bytes

NAME = 'newsletter'
MAX_NEW = 50
SITEMAP = 'https://newsletter.semianalysis.com/sitemap.xml'
ROWS = 'research-desk/packets/newsletter-standing.jsonl'
PACKET = 'research-desk/packets/PUBLIC-TAIL-2026-09-29.research-packet.json'
DELAY = 1.0
COMPANIES = ['CoreWeave', 'Nebius', 'Crusoe', 'Lambda', 'Oracle', 'Azure', 'AWS', 'Google', 'Fluidstack', 'Together', 'TensorWave',
             'Hot Aisle', 'Nvidia', 'AMD', 'Micron', 'SK Hynix', 'Samsung', 'TSMC', 'OpenAI', 'Anthropic', 'xAI', 'Meta']

VOID = {'br', 'img', 'hr', 'input', 'meta', 'link', 'source', 'wbr', 'area', 'base', 'col', 'embed', 'param', 'track'}
SKIP_TAGS = {'script', 'style', 'noscript', 'svg', 'template', 'button', 'head', 'iframe'}
SKIP_CLASS = ('subscription-widget', 'captioned-button-wrap', 'button-wrapper', 'share-dialog', 'post-ufi', 'footnote-hovercard')
BLOCK = {'p', 'div', 'li', 'ul', 'ol', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br', 'blockquote', 'tr', 'table', 'figure', 'figcaption', 'pre'}


class _Article(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []            # (tag, skip, capture_root)
        self.capturing = False
        self.capture_started = False
        self.paras = []
        self.cur = []
        self.paywall = False
        self.found_body = False
        self.fallback = False

    def _skip(self):
        return any(s for _, s, _ in self.stack)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get('class') or '').lower()
        if 'paywall' in cls.split() or (a.get('data-component-name') or '').lower() == 'paywall':
            self.paywall = True
        if tag in VOID:
            if self.capturing and tag == 'br':
                self._flush()
            return
        root = False
        if not self.capture_started and tag == 'div' and 'available-content' in cls:
            root = True
        elif not self.capture_started and tag == 'div' and 'body' in cls.split() and 'markup' in cls.split():
            root = True
            self.fallback = True
        skip = tag in SKIP_TAGS or any(k in cls for k in SKIP_CLASS)
        self.stack.append((tag, skip, root))
        if root:
            self.capturing = True
            self.capture_started = True
            self.found_body = True
        if self.capturing and tag in BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                popped = self.stack[i:]
                del self.stack[i:]
                if any(r for _, _, r in popped):
                    self._flush()
                    self.capturing = False
                break
        if self.capturing and tag in BLOCK:
            self._flush()

    def handle_data(self, data):
        if self.capturing and not self._skip():
            t = data.strip()
            if t:
                self.cur.append(t)

    def _flush(self):
        if self.cur:
            self.paras.append(re.sub(r'\s+', ' ', ' '.join(self.cur)).strip())
            self.cur = []


def extract_article(html: str) -> dict:
    """Visible article text before the paywall. Returns {text, paywalled, found_body, words, warning}."""
    p = _Article()
    try:
        p.feed(html)
        p.close()
    except Exception as e:  # noqa: BLE001
        return {'text': '', 'paywalled': p.paywall, 'found_body': False, 'words': 0, 'warning': f'HTML parse error: {e}'}
    p._flush()
    text = '\n\n'.join(x for x in p.paras if x)
    warning = None
    if not p.found_body:
        warning = 'no article body container (div.available-content / div.body.markup) found; preview left empty'
    elif p.fallback:
        warning = 'used div.body.markup (no div.available-content wrapper)'
    return {'text': text, 'paywalled': p.paywall, 'found_body': p.found_body, 'words': len(text.split()), 'warning': warning}


def meta(html: str, url: str) -> dict:
    def m(pat):
        x = re.search(pat, html)
        return unescape(x.group(1)).strip() if x else None
    title = m(r'<meta\s+property="og:title"\s+content="([^"]*)"') or m(r'<title>([^<]*)</title>')
    date = m(r'<meta\s+property="article:published_time"\s+content="([^"]*)"') or m(r'"datePublished":"([^"]*)"')
    subtitle = m(r'<meta\s+property="og:description"\s+content="([^"]*)"')
    authors = []
    ld = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
    if ld:
        try:
            data = json.loads(ld.group(1))
            a = data.get('author')
            if isinstance(a, dict):
                authors = [a.get('name', '')]
            elif isinstance(a, list):
                authors = [x.get('name', '') if isinstance(x, dict) else x for x in a]
        except ValueError:
            pass
    return {'title': title, 'datePublished': date, 'authors': authors, 'subtitle': subtitle}


def known_urls(ctx, standing_rows) -> set:
    known = {r['url'] for r in standing_rows}
    if ctx.offline:
        kp = ctx.fixtures / 'newsletter' / 'known-urls.txt'
        known |= {l.strip() for l in kp.read_text(encoding='utf-8').splitlines() if l.strip()}
        return known
    packet = json.loads((ctx.repo / PACKET).read_text(encoding='utf-8'))
    for e in packet['workspace']['events']:
        pl = e.get('payload') or {}
        if str(pl.get('id', '')).startswith('sa-post-'):
            known.add(pl['data']['url'])
    return known


def sitemap_urls(ctx, s):
    if ctx.offline:
        body = (ctx.fixtures / 'newsletter' / 'sitemap.xml').read_bytes()
        s.source('fixture:circulate/fixtures/newsletter/sitemap.xml', body)
    else:
        status, headers, body = ctx.http(SITEMAP)
        if status != 200:
            raise Hold(f'sitemap returned HTTP {status}', http=status)
        s.source(SITEMAP, body)
    text = body.decode('utf-8', 'replace')
    out = []
    for m in re.finditer(r'<url>\s*<loc>([^<]+)</loc>(?:\s*<lastmod>([^<]+)</lastmod>)?', text):
        u = m.group(1).strip()
        if urlparse(u).path.startswith('/p/'):
            out.append((u, m.group(2) or ''))
    return out


def run(ctx):
    s = Stage(ctx, NAME)
    rows_path = ctx.committed_read(ROWS)
    standing = [json.loads(l) for l in rows_path.read_text(encoding='utf-8').splitlines() if l.strip()] if rows_path.exists() else []
    try:
        urls = sitemap_urls(ctx, s)
    except Hold as h:
        return s.hold(h)
    known = known_urls(ctx, standing)
    fresh = sorted([(u, d) for u, d in urls if u not in known], key=lambda x: x[1], reverse=True)
    take = fresh[:MAX_NEW]
    s.counts.update(sitemap_posts=len(urls), known=len(known), new_found=len(fresh), fetched=0, appended=0, paywalled=0,
                    no_body=0, failed=0, capped_at=MAX_NEW if len(fresh) > MAX_NEW else None)
    if not take:
        return s.done(SKIP, f'no post in the sitemap ({len(urls)}) is missing from the packet or the standing rows ({len(known)} known).')
    raw_dir = ctx.stage_dir() / 'raw'
    raw_dir.mkdir(parents=True, exist_ok=True)
    new_rows, problems, stop = [], [], None
    for n, (url, lastmod) in enumerate(take):
        slug = urlparse(url).path.rstrip('/').split('/')[-1]
        if ctx.offline:
            fp = ctx.fixtures / 'newsletter' / f'{slug}.html'
            status, body = (200, fp.read_bytes()) if fp.exists() else (404, b'')
        else:
            if n:
                time.sleep(DELAY)
            try:
                status, headers, body = ctx.http(url, timeout=45, max_bytes=8 << 20)
            except RuntimeError as e:
                problems.append((url, None, str(e)[:120]))
                s.counts['failed'] += 1
                continue
        if status != 200:
            problems.append((url, status, f'HTTP {status}'))
            s.counts['failed'] += 1
            if status in (403, 429):
                stop = (url, status)
                break
            continue
        s.counts['fetched'] += 1
        retrieved = iso()
        (raw_dir / f'{slug}.html').write_bytes(body)
        sha = sha256_bytes(body)
        html = body.decode('utf-8', 'replace')
        md = meta(html, url)
        art = extract_article(html)
        if art['paywalled']:
            s.counts['paywalled'] += 1
        if not art['found_body']:
            s.counts['no_body'] += 1
        cl = art['text'].lower()
        row = {'source': 'semianalysis_newsletter', 'provenance': {'url': url, 'sha256': sha, 'retrieved_at': retrieved}, 'url': url,
               'slug': slug, 'title': md['title'] or 'UNVERIFIED', 'datePublished': md['datePublished'] or 'UNVERIFIED',
               'authors': md['authors'], 'subtitle': md['subtitle'] or None, 'paywalled': art['paywalled'],
               'free_preview_text': art['text'][:8000], 'word_count_free': art['words'],
               'companies_mentioned': [c for c in COMPANIES if c.lower() in cl], 'bytes': len(body), 'http': status,
               'sitemap_lastmod': lastmod or None, 'extractor': 'circulate/newsletter@1: visible text of div.available-content before the paywall',
               'extractor_warning': art['warning']}
        new_rows.append(row)
        s.source(url, sha=sha)
    if new_rows:
        out = ctx.out(ROWS)
        keep = rows_path.read_text(encoding='utf-8') if rows_path.exists() else ''
        with open(out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(keep if keep.endswith('\n') or not keep else keep + '\n')
            for r in new_rows:
                f.write(json.dumps(r, ensure_ascii=False, allow_nan=False) + '\n')
        s.output(out)
        s.counts['appended'] = len(new_rows)
    detail = '; '.join(f'{u.rsplit("/", 1)[-1]}: {why}' for u, _, why in problems[:5])
    if stop:
        return s.done(HOLD, f'HTTP {stop[1]} from {stop[0]}; stopped after {len(new_rows)} posts (no retry). {detail}')
    if not new_rows:
        return s.done(HOLD, f'{len(take)} new posts listed but none could be fetched. {detail}')
    note = f'{len(new_rows)} new posts appended ({s.counts["paywalled"]} paywalled, {s.counts["no_body"]} with no recognizable body).'
    if len(fresh) > MAX_NEW:
        note += f' Capped at {MAX_NEW}; {len(fresh) - MAX_NEW} more wait for the next run.'
    if problems:
        note += f' {len(problems)} not fetched: {detail}.'
    return s.done(OK, note)
