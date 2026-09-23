#!/usr/bin/env python3
"""Recompute data/build.json's source hashes and version metadata. Stdlib only.

Preserves every existing field in data/build.json except version, created_at,
python and source_hashes (and any counts explicitly passed on the command line);
creates a fresh build.json only if none exists.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACKED_FILES = [
    'index.html',
    'scripts/challenge.py',
    'scripts/make_demo.py',
    'scripts/probe_audit_runner.py',
    'scripts/launch_ledger.py',
    'tests/test_challenge.py',
    'tests/test_engine.cjs',
    'tests/test_launch_ledger.py',
    'README.md',
    'design/transform.json',
    'launch/README.md',
    'launch/claims-3.0.template.json',
]

def compute_hashes():
    return {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest()
            for f in TRACKED_FILES if (ROOT / f).exists()}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--version', default='1.1.0')
    ap.add_argument('--reference-tests-passed', type=int, default=None)
    ap.add_argument('--engine-checks-passed', type=int, default=None)
    ap.add_argument('--output', type=Path, default=ROOT / 'data/build.json')
    args = ap.parse_args()

    build = json.loads(args.output.read_text(encoding='utf-8')) if args.output.exists() else {
        'schema': 'secondrun.challenge-build.v1',
    }
    build['version'] = args.version
    build['created_at'] = datetime.now(timezone.utc).isoformat()
    build['python'] = sys.version.split()[0]
    if args.reference_tests_passed is not None:
        build['reference_tests_passed'] = args.reference_tests_passed
    if args.engine_checks_passed is not None:
        build['engine_checks_passed'] = args.engine_checks_passed
    build['source_hashes'] = compute_hashes()
    rendered = json.dumps(build, indent=2) + '\n'
    args.output.write_text(rendered, encoding='utf-8')
    print(rendered, end='')
    return 0

if __name__ == '__main__':
    sys.exit(main())
