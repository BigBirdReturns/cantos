#!/usr/bin/env python3
"""Offline paired test of a rating's incremental predictive value. Stdlib only."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

VERSION = '1.0.0'
PLAN_SCHEMA = 'secondrun.rating-plan.v1'
OUTCOME_SCHEMA = 'secondrun.rating-outcomes.v1'
BOOTSTRAPS = 5000
SEED = 20260923
CONTEXT = ('provider_id', 'service_id', 'region', 'workload_sha256',
           'validator_sha256', 'customer_role', 'support')
STATES = {'complete', 'timeout', 'error', 'provision_failed', 'aborted'}

class InvalidPacket(ValueError):
    pass

def need(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidPacket(message)

def text(value, name):
    need(isinstance(value, str) and bool(value.strip()), f'{name}: nonempty text required')
    return value

def digest(value, name):
    need(isinstance(value, str) and len(value) == 64 and
         all(c in '0123456789abcdef' for c in value), f'{name}: lowercase SHA-256 required')
    return value

def finite(value, name, low=0.0, high=None):
    need(type(value) in (int, float) and math.isfinite(value), f'{name}: finite number required')
    need(value >= low and (high is None or value <= high), f'{name}: out of range')
    return float(value)

def stamp(value, name):
    text(value, name)
    need(bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})', value)), f'{name}: RFC3339 timestamp required')
    try:
        t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise InvalidPacket(f'{name}: ISO-8601 timestamp required') from exc
    need(t.tzinfo is not None, f'{name}: timezone required')
    return t

def quantile(xs, q):
    ys = sorted(xs)
    pos = (len(ys) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ys) - 1)
    return ys[lo] + (ys[hi] - ys[lo]) * (pos - lo)

def bootstrap(means):
    n = len(means)
    state = SEED
    limit = 2**32 - (2**32 % n)
    def index():
        nonlocal state
        while True:
            state = (state + 0x6D2B79F5) & 0xffffffff
            t = state
            t = ((t ^ (t >> 15)) * (t | 1)) & 0xffffffff
            t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xffffffff)) & 0xffffffff
            x = (t ^ (t >> 14)) & 0xffffffff
            if x < limit:
                return x % n
    draws = [sum(means[index()] for _ in range(n)) / n
             for _ in range(BOOTSTRAPS)]
    return [quantile(draws, 0.025), quantile(draws, 0.975)]

def parse(raw):
    # Refuse NaN/Infinity rather than letting nonstandard JSON into a receipt.
    def bad(s):
        raise InvalidPacket(f'Nonstandard JSON number: {s}')
    value = json.loads(raw, parse_constant=bad)
    need(isinstance(value, dict), 'JSON object required')
    return value

def validate(plan, outcomes, plan_hash):
    need(plan.get('schema') == PLAN_SCHEMA, 'Unsupported plan schema')
    need(outcomes.get('schema') == OUTCOME_SCHEMA, 'Unsupported outcome schema')
    need(outcomes.get('plan_sha256') == plan_hash, 'Outcome packet does not match exact frozen plan bytes')
    need(type(plan.get('synthetic')) is bool, 'Plan must declare synthetic true or false')
    for field in ('study_id', 'rating_name', 'rating_version', 'outcome_definition'):
        text(plan.get(field), field)
    digest(plan.get('rating_rules_sha256'), 'rating_rules_sha256')
    frozen = stamp(plan.get('frozen_at'), 'frozen_at')
    minimum = plan.get('minimum_providers')
    need(type(minimum) is int and minimum >= 8, 'At least eight independent providers required by v1 protocol')
    finite(plan.get('minimum_lift'), 'minimum_lift', 0, 1)
    models = [plan.get('baseline'), plan.get('with_rating')]
    for i, model in enumerate(models):
        need(isinstance(model, dict), 'Both predictor definitions required')
        text(model.get('description'), 'predictor description')
        digest(model.get('model_sha256'), 'model_sha256')
        need(stamp(model.get('frozen_at'), 'model frozen_at') <= frozen, 'Predictor frozen after plan')
        train = model.get('training_providers')
        need(isinstance(train, list) and all(isinstance(x, str) and x for x in train), 'Training-provider list required')
        inputs = model.get('inputs')
        need(isinstance(inputs, list) and inputs and all(isinstance(x,str) and x for x in inputs), 'Predictor inputs required')
        need(len(inputs) == len(set(inputs)), 'Duplicate predictor inputs')
    base_inputs, rating_inputs = set(models[0]['inputs']), set(models[1]['inputs'])
    need('rating' not in base_inputs and rating_inputs == base_inputs | {'rating'}, 'Predictors must differ only by declared rating input')
    need(set(models[0]['training_providers']) == set(models[1]['training_providers']), 'Use the same training-provider set for the ablation')
    rows, actuals = plan.get('trials'), outcomes.get('trials')
    need(isinstance(rows, list) and rows, 'Planned cohort is empty')
    need(isinstance(actuals, list), 'Outcome trials required')
    ids, out = set(), {}
    for row in actuals:
        need(isinstance(row, dict), 'Outcome row must be an object')
        rid = text(row.get('trial_id'), 'outcome trial_id')
        need(rid not in out, 'Duplicate outcome trial: ' + rid)
        out[rid] = row
    groups = {}
    train = set(models[0]['training_providers']) | set(models[1]['training_providers'])
    costs = []
    for row in rows:
        need(isinstance(row, dict), 'Plan row must be an object')
        rid = text(row.get('trial_id'), 'trial_id')
        need(rid not in ids, 'Duplicate planned trial: ' + rid)
        ids.add(rid)
        need(rid in out, 'Missing terminal outcome: ' + rid)
        actual = out[rid]
        for field in CONTEXT:
            text(row.get(field), field)
            need(actual.get(field) == row[field], f'{rid}: changed or missing {field}')
        digest(row['workload_sha256'], 'workload_sha256')
        digest(row['validator_sha256'], 'validator_sha256')
        need(row['customer_role'] == 'ordinary_tenant' and row['support'] == 'standard',
             f'{rid}: reviewer/admin treatment is outside ordinary-customer claim')
        provider = row['provider_id']
        need(provider not in train, f'{provider}: provider leaked from training into test')
        predicted = stamp(row.get('predicted_at'), 'predicted_at')
        start, end = stamp(actual.get('started_at'), 'started_at'), stamp(actual.get('finished_at'), 'finished_at')
        need(predicted <= frozen < start <= end, f'{rid}: predictions or plan are not prospective')
        pb = finite(row.get('p_baseline'), 'p_baseline', 0, 1)
        pr = finite(row.get('p_with_rating'), 'p_with_rating', 0, 1)
        gates = row.get('gates')
        need(isinstance(gates, dict), 'Job gates required')
        accepted_min = gates.get('accepted_min')
        need(type(accepted_min) is int and accepted_min > 0, 'Positive accepted_min integer required')
        latency_max = finite(gates.get('p95_max_ms'), 'p95_max_ms')
        cost_max = finite(gates.get('cost_max_usd'), 'cost_max_usd')
        state = actual.get('status')
        need(state in STATES, f'{rid}: terminal status required')
        accepted, attempted = actual.get('accepted'), actual.get('attempted')
        need(type(accepted) is int and type(attempted) is int and 0 <= accepted <= attempted,
             f'{rid}: accepted and attempted must be consistent integers')
        cost = finite(actual.get('total_cost_usd'), 'total_cost_usd')
        need('p95_ms' in actual, f'{rid}: p95_ms required, use null for unavailable failed-job latency')
        latency = actual.get('p95_ms')
        if latency is not None:
            latency = finite(latency, 'p95_ms')
        need(state != 'complete' or latency is not None, f'{rid}: completed job lacks latency evidence')
        digest(actual.get('receipt_sha256'), 'receipt_sha256')
        text(actual.get('receipt_ref'), 'receipt_ref')
        y = int(state == 'complete' and accepted >= accepted_min and
                latency is not None and latency <= latency_max and cost <= cost_max)
        lb, lr = (pb-y)**2, (pr-y)**2
        groups.setdefault(provider, []).append({'trial_id':rid, 'passed':y,
            'baseline_brier':lb, 'with_rating_brier':lr, 'lift':lb-lr})
        costs.append({'trial_id':rid, 'total_cost_usd':cost,
            'accepted':accepted, 'cost_per_1000_accepted':1000*cost/accepted if accepted else None})
    need(ids == set(out), 'Outcome packet contains unplanned trials')
    need(len(groups) >= minimum, f'Only {len(groups)} held-out providers; {minimum} required')
    return groups, costs

def evaluate(plan_bytes: bytes, outcome_bytes: bytes):
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    result = {'schema':'secondrun.rating-result.v1', 'test_version':VERSION,
        'plan_sha256':plan_hash, 'outcomes_sha256':hashlib.sha256(outcome_bytes).hexdigest(),
        'evidence_status':'UNVERIFIED_SUBMISSION',
        'scope':'Predictive ablation on supplied job outcomes; not a cloud/security/credit certification.'}
    try:
        plan, outcomes = parse(plan_bytes), parse(outcome_bytes)
        result['evidence_status'] = 'SYNTHETIC_DEMO' if plan.get('synthetic') is True else 'UNVERIFIED_SUBMISSION'
        result['rating_name'] = plan.get('rating_name')
        groups, costs = validate(plan, outcomes, plan_hash)
        provider_means = [statistics.mean(x['lift'] for x in groups[p]) for p in sorted(groups)]
        interval = bootstrap(provider_means)
        base = statistics.mean(statistics.mean(x['baseline_brier'] for x in groups[p]) for p in groups)
        full = statistics.mean(statistics.mean(x['with_rating_brier'] for x in groups[p]) for p in groups)
        result.update(status='LIFT_DEMONSTRATED_ON_SUBMITTED_DATA' if interval[0] > plan['minimum_lift'] else 'LIFT_NOT_DEMONSTRATED',
            providers=len(groups), trials=sum(map(len,groups.values())), baseline_brier=base,
            with_rating_brier=full, mean_lift=base-full, bootstrap_95=interval,
            minimum_lift=plan['minimum_lift'], bootstrap_draws=BOOTSTRAPS, seed=SEED,
            provider_results=groups, economics=costs)
    except (InvalidPacket, ValueError, TypeError, KeyError) as exc:
        result.update(status='HOLD', reason=str(exc))
    return result

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan', type=Path, required=True)
    ap.add_argument('--outcomes', type=Path, required=True)
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    try:
        result = evaluate(args.plan.read_bytes(), args.outcomes.read_bytes())
    except OSError as exc:
        print(str(exc), file=sys.stderr); return 2
    rendered = json.dumps(result, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
    else:
        print(rendered, end='')
    # Nonzero means no admissible demonstrated lift. Synthetic status is always retained.
    return 2 if result['status']=='HOLD' else (0 if result['status'].startswith('LIFT_DEMONSTRATED') else 1)

if __name__ == '__main__':
    sys.exit(main())
