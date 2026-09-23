#!/usr/bin/env python3
"""Convert a simple jobs CSV plus a small plan-header JSON into a correctly
hashed plan.json / binding.json / outcomes.json triple. Stdlib only.

Everything that varies per job goes in the CSV, one row per trial:

  trial_id, provider_id, service_id, region, session_id, predicted_at,
  p_baseline, started_at, finished_at, status, accepted, attempted, p95_ms,
  total_cost_usd, credits_redeemed_usd, receipt_ref, receipt_sha256

Everything that's constant across the cohort (study metadata, disclosure, the
transform, the baseline/with_rating predictor definitions, the shared
workload/validator hashes and gates, and the binding itself) goes in a
separate header JSON -- see submissions/templates/FIELDS.md's "CSV_to_packet.py
header JSON" section for the exact shape and a worked example.

This script does mechanical conversion and hashing only; it does not validate
against scripts/challenge.py's rules (run scripts/submit_check.py on the
output afterward for that). Output files are written LF-only regardless of
platform.

Usage:
  python scripts/csv_to_packet.py --csv jobs.csv --header plan-header.json \
    --plan-out plan.json --binding-out binding.json --outcomes-out outcomes.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


def _load_challenge_module():
    """Import scripts/challenge.py by path -- the same dynamic-load pattern
    scripts/submit_check.py uses -- so this converter shares challenge.py's
    canonical-hashing implementation and schema constants instead of keeping
    a private, driftable copy of either."""
    path = Path(__file__).resolve().parent / 'challenge.py'
    spec = importlib.util.spec_from_file_location('clustermax_challenge_engine', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_challenge = _load_challenge_module()

CSV_COLUMNS = (
    'trial_id', 'provider_id', 'service_id', 'region', 'session_id',
    'predicted_at', 'p_baseline', 'started_at', 'finished_at', 'status',
    'accepted', 'attempted', 'p95_ms', 'total_cost_usd',
    'credits_redeemed_usd', 'receipt_ref', 'receipt_sha256',
)
PLAN_ROW_COLUMNS = ('trial_id', 'provider_id', 'service_id', 'region', 'session_id', 'predicted_at', 'p_baseline')
CONTEXT_COLUMNS = ('trial_id', 'provider_id', 'service_id', 'region', 'session_id')


class ConversionError(ValueError):
    pass


# Same algorithm scripts/challenge.py uses for transform_sha256 -- SHA-256 of the
# canonical (UTF-16-code-unit-sorted-key, ECMAScript-number, no-whitespace) JSON
# encoding, not of the file bytes. Imported rather than duplicated so the two
# tools can never drift apart on what "canonical" means.
canonical_sha256 = _challenge.canonical_sha256


def dump_bytes(obj) -> bytes:
    return (json.dumps(obj, indent=2, allow_nan=False) + '\n').encode('utf-8')


def parse_float(value, field, row_id):
    if value is None or value == '':
        raise ConversionError(f'{row_id}: {field} is required')
    try:
        return float(value)
    except ValueError as exc:
        raise ConversionError(f'{row_id}: {field}={value!r} is not a number') from exc


def parse_optional_float(value, default=0.0):
    if value is None or value == '':
        return default
    return float(value)


def parse_int(value, field, row_id):
    if value is None or value == '':
        raise ConversionError(f'{row_id}: {field} is required')
    try:
        return int(value)
    except ValueError as exc:
        raise ConversionError(f'{row_id}: {field}={value!r} is not an integer') from exc


def load_rows(csv_path: Path) -> list[dict]:
    with csv_path.open('r', encoding='utf-8', newline='') as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in CSV_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ConversionError(f'{csv_path}: missing required CSV column(s): {", ".join(missing)}')
        return [dict(row) for row in reader]


def build_plan_trial(row: dict, header: dict) -> dict:
    row_id = row.get('trial_id') or '<missing trial_id>'
    return {
        'trial_id': row['trial_id'],
        'provider_id': row['provider_id'],
        'service_id': row['service_id'],
        'region': row['region'],
        'workload_sha256': header['workload_sha256'],
        'validator_sha256': header['validator_sha256'],
        'customer_role': header.get('customer_role', 'ordinary_tenant'),
        'support': header.get('support', 'standard'),
        'session_id': row['session_id'],
        'predicted_at': row['predicted_at'],
        'p_baseline': parse_float(row.get('p_baseline'), 'p_baseline', row_id),
        'gates': header['gates'],
    }


def build_outcome_trial(row: dict, header: dict) -> dict:
    row_id = row.get('trial_id') or '<missing trial_id>'
    p95_raw = row.get('p95_ms')
    p95_ms = None if p95_raw in (None, '') else parse_float(p95_raw, 'p95_ms', row_id)
    return {
        'trial_id': row['trial_id'],
        'provider_id': row['provider_id'],
        'service_id': row['service_id'],
        'region': row['region'],
        'workload_sha256': header['workload_sha256'],
        'validator_sha256': header['validator_sha256'],
        'customer_role': header.get('customer_role', 'ordinary_tenant'),
        'support': header.get('support', 'standard'),
        'session_id': row['session_id'],
        'started_at': row['started_at'],
        'finished_at': row['finished_at'],
        'status': row['status'],
        'accepted': parse_int(row.get('accepted'), 'accepted', row_id),
        'attempted': parse_int(row.get('attempted'), 'attempted', row_id),
        'p95_ms': p95_ms,
        'total_cost_usd': parse_float(row.get('total_cost_usd'), 'total_cost_usd', row_id),
        'credits_redeemed_usd': parse_optional_float(row.get('credits_redeemed_usd')),
        'receipt_ref': row['receipt_ref'],
        'receipt_sha256': row['receipt_sha256'],
    }


def build(csv_rows: list[dict], header: dict) -> tuple[bytes, bytes, bytes]:
    for required in ('workload_sha256', 'validator_sha256', 'gates', 'transform', 'baseline',
                      'with_rating', 'study_id', 'rating_name', 'rating_version', 'frozen_at',
                      'minimum_providers', 'minimum_lift', 'outcome_definition', 'disclosure',
                      'binding_rules', 'binding'):
        if required not in header:
            raise ConversionError(f'plan-header JSON is missing required field: {required}')

    seen_ids = set()
    for row in csv_rows:
        rid = row.get('trial_id')
        if not rid:
            raise ConversionError('a CSV row is missing trial_id')
        if rid in seen_ids:
            raise ConversionError(f'duplicate trial_id in CSV: {rid}')
        seen_ids.add(rid)

    transform = header['transform']
    transform_sha256 = canonical_sha256(transform)

    plan = {
        'schema': _challenge.PLAN_SCHEMA,
        'synthetic': bool(header.get('synthetic', False)),
        'study_id': header['study_id'],
        'rating_name': header['rating_name'],
        'rating_version': header['rating_version'],
        'frozen_at': header['frozen_at'],
        'minimum_providers': header['minimum_providers'],
        'minimum_lift': header['minimum_lift'],
        'outcome_definition': header['outcome_definition'],
        'disclosure': header['disclosure'],
        'binding_rules': header['binding_rules'],
        'transform': transform,
        'transform_sha256': transform_sha256,
        'baseline': header['baseline'],
        'with_rating': header['with_rating'],
        'trials': [build_plan_trial(row, header) for row in csv_rows],
    }
    plan_bytes = dump_bytes(plan)
    plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()

    binding_header = header['binding']
    for required in ('source', 'rubric', 'bound_at', 'medals'):
        if required not in binding_header:
            raise ConversionError(f'plan-header JSON "binding" object is missing required field: {required}')
    binding = {
        'schema': _challenge.BINDING_SCHEMA,
        'plan_sha256': plan_sha256,
        'rating_name': header['rating_name'],
        'rating_version': header['rating_version'],
        'source': binding_header['source'],
        'rubric': binding_header['rubric'],
        'bound_at': binding_header['bound_at'],
        'medals': binding_header['medals'],
    }
    binding_bytes = dump_bytes(binding)
    binding_sha256 = hashlib.sha256(binding_bytes).hexdigest()

    outcomes = {
        'schema': _challenge.OUTCOME_SCHEMA,
        'plan_sha256': plan_sha256,
        'binding_sha256': binding_sha256,
        'trials': [build_outcome_trial(row, header) for row in csv_rows],
    }
    outcomes_bytes = dump_bytes(outcomes)

    return plan_bytes, binding_bytes, outcomes_bytes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--csv', type=Path, required=True, help='jobs CSV; columns: ' + ', '.join(CSV_COLUMNS))
    ap.add_argument('--header', type=Path, required=True, help='plan-header JSON (see submissions/templates/FIELDS.md)')
    ap.add_argument('--plan-out', type=Path, required=True)
    ap.add_argument('--binding-out', type=Path, required=True)
    ap.add_argument('--outcomes-out', type=Path, required=True)
    args = ap.parse_args(argv)

    try:
        rows = load_rows(args.csv)
        header = json.loads(args.header.read_text(encoding='utf-8'))
        plan_bytes, binding_bytes, outcomes_bytes = build(rows, header)
    except (ConversionError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f'Conversion failed: {exc}', file=sys.stderr)
        return 2

    args.plan_out.write_bytes(plan_bytes)
    args.binding_out.write_bytes(binding_bytes)
    args.outcomes_out.write_bytes(outcomes_bytes)
    print(f'Wrote {args.plan_out}, {args.binding_out}, {args.outcomes_out} ({len(rows)} trials).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
