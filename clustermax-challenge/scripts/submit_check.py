#!/usr/bin/env python3
"""Validate one clustermax-challenge submission directory.

A submission is submissions/<id>/{plan.json,binding.json,outcomes.json,SUBMITTER.md}
(see SUBMITTING.md; schemas secondrun.rating-plan.v4 / secondrun.rating-binding.v2 /
secondrun.rating-outcomes.v4). This script:

  1. Requires all four files to exist.
  2. Requires SUBMITTER.md to contain a disclosure section (a heading such as
     "Disclosure" -- see SUBMITTING.md for what belongs in it). This is
     separate from plan.json's own structured `disclosure` object, which
     scripts/challenge.py's evaluate() checks on its own.
  3. Loads scripts/challenge.py and calls its
     evaluate(plan_bytes, binding_bytes, outcome_bytes) -- the same
     admission-control evaluator used everywhere else in this repo -- and
     prints its status/reason.
  4. Prints the SHA-256 of every submitted file, so a reviewer can cite exactly
     what was checked.

Exit code is nonzero when challenge.py returns status HOLD, or when the
submission is structurally invalid (missing file, no disclosure section).
Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
from pathlib import Path

DISCLOSURE_HEADINGS = ('disclosure', 'disclosures', 'conflict of interest', 'conflicts of interest')


def load_challenge_module():
    """Import scripts/challenge.py by path so this works whether or not
    scripts/ is on sys.path, and always picks up the sibling file (which is
    owned/upgraded by another workstream -- we only ever call evaluate())."""
    path = Path(__file__).resolve().parent / 'challenge.py'
    spec = importlib.util.spec_from_file_location('clustermax_challenge_engine', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def has_disclosure_section(text: str) -> bool:
    lowered = text.lower()
    return any(heading in lowered for heading in DISCLOSURE_HEADINGS)


def check_submission(sub_dir: Path) -> dict:
    problems = []
    plan_path = sub_dir / 'plan.json'
    binding_path = sub_dir / 'binding.json'
    outcomes_path = sub_dir / 'outcomes.json'
    submitter_path = sub_dir / 'SUBMITTER.md'

    for path in (plan_path, binding_path, outcomes_path, submitter_path):
        if not path.exists():
            problems.append(f'missing required file: {path.name}')
    if problems:
        return {'submission': sub_dir.name, 'ok': False, 'problems': problems}

    submitter_text = submitter_path.read_text(encoding='utf-8')
    if not has_disclosure_section(submitter_text):
        problems.append('SUBMITTER.md has no disclosure section '
                        '(expected a heading such as "Disclosure")')

    hashes = {
        'plan.json': sha256_file(plan_path),
        'binding.json': sha256_file(binding_path),
        'outcomes.json': sha256_file(outcomes_path),
        'SUBMITTER.md': sha256_file(submitter_path),
    }

    challenge = load_challenge_module()
    result = challenge.evaluate(plan_path.read_bytes(), binding_path.read_bytes(), outcomes_path.read_bytes())

    ok = (not problems) and result.get('status') != 'HOLD'
    return {
        'submission': sub_dir.name, 'ok': ok, 'problems': problems, 'hashes': hashes,
        'status': result.get('status'), 'reason': result.get('reason'),
        'evidence_status': result.get('evidence_status'),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('submission', type=Path, help='path to submissions/<id>/')
    args = ap.parse_args(argv)

    if not args.submission.is_dir():
        print(f'not a directory: {args.submission}', file=sys.stderr)
        return 2

    report = check_submission(args.submission)
    print(f"submission: {report['submission']}")
    for name, digest in report.get('hashes', {}).items():
        print(f'  {name}: sha256={digest}')
    if report['problems']:
        print('problems:')
        for problem in report['problems']:
            print(f'  - {problem}')
    if 'status' in report:
        print(f"challenge status: {report['status']}")
        if report.get('reason'):
            print(f"  reason: {report['reason']}")
        print(f"evidence_status: {report.get('evidence_status')}")
    print('RESULT:', 'OK' if report['ok'] else 'HOLD/FAIL')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
