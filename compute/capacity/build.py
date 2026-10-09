#!/usr/bin/env python3
"""Build the dedicated-capacity view from its sources and the native calculation owners.

The page embeds compute/engine.cjs (the Compute calculation owner) and the retained Run 3
summary at pinned Git blob identities. If either owner changes, the build stops until this
view is reviewed and its pins (here and in capacity.cjs / check_math.py) are updated.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PINS = {'compute/engine.cjs': '21956dbce1449a3bbfdedfce3a5064e5b8d87495',
        'hot-aisle/campaign/results/RUN3-RESULTS.md': '95289238fca808c15f82b9c90aad364d8405d640'}
FILES = ['index.html', 'template.html', 'capacity.cjs', 'ui.js', 'verify.cjs', 'check_math.py', 'build.py',
         'example-decision.json', 'README.md', 'QUALIFICATION.json',
         'tests/capacity.test.cjs', 'tests/check_reference.py', 'tests/browser_check.py']


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def read(path):
    return path.read_text(encoding='utf-8')


for rel, expected in PINS.items():
    if blob((REPO / rel).read_bytes()) != expected:
        raise SystemExit(f'Pinned source changed: {rel}. Review this view and update its pins.')
page = read(HERE / 'template.html')
slots = {'__ENGINE__': read(REPO / 'compute/engine.cjs'),
         '__CAPACITY__': read(HERE / 'capacity.cjs'),
         '__UI__': read(HERE / 'ui.js'),
         '__SOURCE_JSON__': json.dumps(read(REPO / 'hot-aisle/campaign/results/RUN3-RESULTS.md'),
                                       ensure_ascii=False).replace('<', '\\u003c')}
for token, body in slots.items():
    if page.count(token) != 1:
        raise SystemExit('Template slot missing or duplicated: ' + token)
    page = page.replace(token, body)
(HERE / 'index.html').write_text(page, encoding='utf-8', newline='\n')
manifest = {'scope': 'Byte inventory, not a signature or acceptance attestation.',
            'embedded_owners': PINS,
            'files': {f: {'sha256': hashlib.sha256((HERE / f).read_bytes()).hexdigest(),
                          'bytes': (HERE / f).stat().st_size} for f in FILES}}
(HERE / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
print('Built compute/capacity/index.html; pinned owner identities match.')
