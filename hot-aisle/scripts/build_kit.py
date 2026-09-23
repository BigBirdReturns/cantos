#!/usr/bin/env python3
"""Deterministic offline kit: MANIFEST.json and workload-report.zip generated from the
source tree, never hand-pinned. Run after any change; CI runs it and fails if the
committed manifest or archive differs from what the source produces.

    python scripts/build_kit.py          # write MANIFEST.json + workload-report.zip
    python scripts/build_kit.py --check  # exit 1 if either differs from the source
"""
from __future__ import annotations
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ['index.html', 'README.md', 'RUNNER.md', 'FORMATS.md', 'FIRST_CAMPAIGN.md', 'LICENSE', 'QUALIFICATION.json', 'data/prices.json']
GLOBS = ['data/demo/*', 'examples/*.json', 'scripts/*.py', 'scripts/*.cjs', 'scripts/*.mjs', 'runner/package.json', 'runner/bin/*.cjs', 'runner/lib/*.cjs', 'runner/lib/adapters/*.cjs', 'runner/fixtures/*.cjs', 'runner/test/*.cjs']
ZIP_DATE = (2026, 9, 22, 0, 0, 0)


def members() -> list[str]:
    names = set(INCLUDE)
    for g in GLOBS:
        for p in ROOT.glob(g):
            if p.is_file():
                names.add(p.relative_to(ROOT).as_posix())
    return sorted(n for n in names if (ROOT / n).is_file())


def manifest() -> dict:
    files = {}
    for name in members():
        body = (ROOT / name).read_bytes()
        files[name] = {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}
    return {'schema': 'hot-aisle/distribution@3', 'version': '2.2.0', 'scope': 'Byte manifest of the offline kit, generated from source by scripts/build_kit.py. Excludes itself and the enclosing archive; does not authenticate source assertions.', 'files': files}


def archive_bytes(man: dict) -> bytes:
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted(man['files']):
            info = zipfile.ZipInfo(name, date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, (ROOT / name).read_bytes())
        info = zipfile.ZipInfo('MANIFEST.json', date_time=ZIP_DATE)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        z.writestr(info, json.dumps(man, indent=2) + '\n')
    return buf.getvalue()


def main() -> int:
    man = manifest()
    man_text = json.dumps(man, indent=2) + '\n'
    zip_bytes = archive_bytes(man)
    man_path, zip_path = ROOT / 'MANIFEST.json', ROOT / 'workload-report.zip'
    if '--check' in sys.argv:
        problems = []
        if not man_path.exists() or man_path.read_text(encoding='utf-8') != man_text:
            problems.append('MANIFEST.json differs from source')
        if not zip_path.exists() or zip_path.read_bytes() != zip_bytes:
            problems.append('workload-report.zip differs from source')
        if problems:
            print('KIT STALE: ' + '; '.join(problems) + '. Run python scripts/build_kit.py and commit.')
            return 1
        print('kit matches source: %d files, %d bytes' % (len(man['files']), len(zip_bytes)))
        return 0
    man_path.write_text(man_text, encoding='utf-8', newline='\n')
    zip_path.write_bytes(zip_bytes)
    print('wrote MANIFEST.json (%d files) and workload-report.zip (%d bytes)' % (len(man['files']), len(zip_bytes)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
