#!/usr/bin/env python3
"""Validate a ClusterMAX-3.0 launch-claims ledger and, when it supplies enough,
emit a binding.json draft. Stdlib only.

This script does not know, guess at, or encode anything about ClusterMAX 3.0's
actual rubric, medal table or release date. It is a fixed procedure for turning
whatever the release actually publishes into a ledger (schema
secondrun.launch-claims.v1, see ../launch/claims-3.0.template.json) and, where the
ledger supplies enough, a binding draft (schema secondrun.rating-binding.v2) for a
frozen plan.

The ledger records, per provider medal, five fields:

  scope                 -- the service/product and region the medal covers
  observation_conditions -- the customer permissions and support tier that
                            produced the observations (ordinary vs
                            reviewer/white-glove)
  evidence               -- evidence published for the medal and how it yields
                            the tier (rubric link + per-criterion scores, if
                            published)
  test_dates             -- when the observations were made
  predictive_check       -- whether the release provides anything allowing a
                            predictive check

Each field carries a status: SUPPLIED (with a cited source url + sha256 and a
value), OMITTED (with the exact claim that consequently remains unevaluable), or
NOT_YET_RELEASED.

Usage:
  python scripts/launch_ledger.py ledger.json
  python scripts/launch_ledger.py ledger.json --plan data/demo-plan.json --output binding-draft.json

Exit codes: 0 on a structurally valid ledger (a binding draft may or may not be
emitted, depending on what the ledger supplies); 2 on an unreadable file or an
invalid ledger.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

LEDGER_SCHEMA = 'secondrun.launch-claims.v1'
BINDING_SCHEMA = 'secondrun.rating-binding.v2'
MEDALS = ('Platinum', 'Gold', 'Silver', 'Bronze', 'Underperforming')
FIELDS = ('scope', 'observation_conditions', 'evidence', 'test_dates', 'predictive_check')
FIELD_LABELS = {
    'scope': 'service/product and region the medal covers',
    'observation_conditions': 'customer permissions and support tier that produced the observations',
    'evidence': 'evidence published for the medal and how it yields the tier',
    'test_dates': 'test dates',
    'predictive_check': 'whether the release provides anything allowing a predictive check',
}
STATUSES = ('NOT_YET_RELEASED', 'SUPPLIED', 'OMITTED')


class InvalidLedger(ValueError):
    pass


def need(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidLedger(message)


def text(value, name):
    need(isinstance(value, str) and bool(value.strip()), f'{name}: nonempty text required')
    return value


def digest(value, name):
    need(isinstance(value, str) and len(value) == 64 and
         all(c in '0123456789abcdef' for c in value), f'{name}: lowercase SHA-256 required')
    return value


def stamp(value, name):
    text(value, name)
    need(bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})', value)),
         f'{name}: RFC3339 timestamp required')
    try:
        t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise InvalidLedger(f'{name}: ISO-8601 timestamp required') from exc
    need(t.tzinfo is not None, f'{name}: timezone required')
    return t


def validate_source_block(block, name):
    need(isinstance(block, dict), f'{name}: object required')
    text(block.get('url'), f'{name}.url')
    digest(block.get('sha256'), f'{name}.sha256')
    stamp(block.get('retrieved_utc'), f'{name}.retrieved_utc')
    return block


def validate_field(field_obj, path):
    need(isinstance(field_obj, dict), f'{path}: object required')
    status = field_obj.get('status')
    need(status in STATUSES, f"{path}.status: must be one of {', '.join(STATUSES)}")
    if status == 'SUPPLIED':
        need('value' in field_obj and field_obj.get('value') not in (None, '', [], {}),
             f'{path}.value: required when SUPPLIED')
        validate_source_block(field_obj.get('source'), f'{path}.source')
    elif status == 'OMITTED':
        text(field_obj.get('omitted_claim'), f'{path}.omitted_claim')
    return status


def validate_ledger(ledger) -> dict:
    """Returns a report: field_status_counts, unevaluable claims, has_sources,
    and the raw medals mapping. Raises InvalidLedger on a structurally broken
    ledger."""
    need(isinstance(ledger, dict), 'ledger: object required')
    need(ledger.get('schema') == LEDGER_SCHEMA, 'Unsupported ledger schema')
    text(ledger.get('release_name'), 'release_name')
    medals = ledger.get('medals')
    need(isinstance(medals, dict) and bool(medals), 'medals: nonempty object required')

    field_status_counts = {field: {status: 0 for status in STATUSES} for field in FIELDS}
    unevaluable = []
    for provider, entry in medals.items():
        need(isinstance(entry, dict), f'medals.{provider}: object required')
        medal = entry.get('medal')
        need(isinstance(medal, str) and medal in MEDALS, f'medals.{provider}.medal: one of the frozen tiers required')
        for field in FIELDS:
            path = f'medals.{provider}.{field}'
            status = validate_field(entry.get(field), path)
            field_status_counts[field][status] += 1
            if status == 'OMITTED':
                unevaluable.append({'provider': provider, 'field': field,
                                     'label': FIELD_LABELS[field],
                                     'claim': entry[field]['omitted_claim']})

    has_sources = isinstance(ledger.get('medal_table_source'), dict) and isinstance(ledger.get('rubric_source'), dict)
    if has_sources:
        try:
            validate_source_block(ledger['medal_table_source'], 'medal_table_source')
            validate_source_block(ledger['rubric_source'], 'rubric_source')
        except InvalidLedger:
            has_sources = False

    return {'field_status_counts': field_status_counts, 'unevaluable': unevaluable,
            'has_sources': has_sources, 'medals': medals}


def print_summary(report: dict, out=sys.stdout) -> None:
    print('Per-field status (providers):', file=out)
    header = f"  {'field':<26}{'SUPPLIED':>10}{'OMITTED':>10}{'NOT_YET_RELEASED':>18}"
    print(header, file=out)
    for field in FIELDS:
        counts = report['field_status_counts'][field]
        print(f"  {field:<26}{counts['SUPPLIED']:>10}{counts['OMITTED']:>10}{counts['NOT_YET_RELEASED']:>18}", file=out)
    print(file=out)
    if report['unevaluable']:
        print(f"Unevaluable claims ({len(report['unevaluable'])}):", file=out)
        for item in report['unevaluable']:
            print(f"  - {item['provider']} / {item['label']}: {item['claim']}", file=out)
    else:
        print('Unevaluable claims: none.', file=out)


def build_binding_draft(ledger: dict, plan: dict, plan_hash: str) -> dict:
    provider_ids = sorted({
        row.get('provider_id') for row in plan.get('trials', [])
        if isinstance(row, dict) and isinstance(row.get('provider_id'), str)
    })
    need(bool(provider_ids), 'plan.trials: no provider_id values found')
    medals = ledger.get('medals', {})
    missing = [pid for pid in provider_ids if pid not in medals]
    need(not missing, 'Ledger is missing medals for plan providers: ' + ', '.join(missing))
    medals_out = {}
    for pid in provider_ids:
        tier = medals[pid].get('medal')
        need(tier in MEDALS, f'medals.{pid}.medal: one of the frozen tiers required')
        medals_out[pid] = tier
    bound_at = datetime.now(timezone.utc).isoformat()
    return {
        'schema': BINDING_SCHEMA,
        'plan_sha256': plan_hash,
        'rating_name': plan.get('rating_name'),
        'rating_version': plan.get('rating_version'),
        'source': {
            'url': ledger['medal_table_source']['url'],
            'sha256': ledger['medal_table_source']['sha256'],
            'retrieved_utc': ledger['medal_table_source']['retrieved_utc'],
        },
        'rubric': {
            'url': ledger['rubric_source']['url'],
            'sha256': ledger['rubric_source']['sha256'],
            'retrieved_utc': ledger['rubric_source']['retrieved_utc'],
        },
        'bound_at': bound_at,
        'medals': medals_out,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('ledger', type=Path, help='path to a filled claims-3.0 ledger JSON file')
    ap.add_argument('--plan', type=Path,
                     help='frozen plan.json to bind against; a binding.json draft is emitted only if '
                          'the ledger supplies a medal for every plan provider plus a medal-table source '
                          'and a rubric source')
    ap.add_argument('--output', type=Path, help='where to write the binding draft (default: stdout)')
    args = ap.parse_args(argv)

    try:
        ledger_bytes = args.ledger.read_bytes()
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        ledger = json.loads(ledger_bytes)
    except json.JSONDecodeError as exc:
        print(f'Invalid JSON in {args.ledger}: {exc}', file=sys.stderr)
        return 2

    try:
        report = validate_ledger(ledger)
    except InvalidLedger as exc:
        print(f'Ledger invalid: {exc}', file=sys.stderr)
        return 2

    print_summary(report)

    if not args.plan:
        return 0

    try:
        plan_bytes = args.plan.read_bytes()
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    plan = json.loads(plan_bytes)
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()

    if not report['has_sources']:
        print('\nNot emitting a binding draft: ledger has no valid medal_table_source '
              'and/or rubric_source.')
        return 0

    try:
        draft = build_binding_draft(ledger, plan, plan_hash)
    except InvalidLedger as exc:
        print(f'\nNot emitting a binding draft: {exc}')
        return 0

    rendered = json.dumps(draft, indent=2) + '\n'
    print('\nBinding draft (bound_at is stamped now -- confirm it reflects when you '
          'actually read the medal table and rubric, and that it still lands strictly '
          'before every trial\'s started_at, before treating this as a real binding):')
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
        print(f'Wrote {args.output}')
    else:
        print(rendered, end='')
    return 0


if __name__ == '__main__':
    sys.exit(main())
