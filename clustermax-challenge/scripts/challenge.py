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
from datetime import datetime, timezone
from pathlib import Path

VERSION = '1.3.0'
PLAN_SCHEMA = 'secondrun.rating-plan.v4'
OUTCOME_SCHEMA = 'secondrun.rating-outcomes.v4'
RESULT_SCHEMA = 'secondrun.rating-result.v4'
TRANSFORM_SCHEMA = 'secondrun.rating-transform.v1'
BINDING_SCHEMA = 'secondrun.rating-binding.v2'
BOOTSTRAPS = 5000
SEED = 20260923
CONTEXT = ('provider_id', 'service_id', 'region', 'workload_sha256',
           'validator_sha256', 'customer_role', 'support', 'session_id')
STATES = {'complete', 'timeout', 'error', 'provision_failed', 'aborted'}
MEDALS = ('Platinum', 'Gold', 'Silver', 'Bronze', 'Underperforming')
MIN_TRIALS_PER_PROVIDER = 10
MIN_SESSIONS_PER_PROVIDER = 5
MIN_DATES_PER_PROVIDER = 3
DISCLOSURE_FIELDS = ('relationship', 'compensation', 'credits', 'special_support', 'editorial_influence')
# Case-insensitive substrings that mark an unanswered disclosure placeholder. '[' catches
# the "[CONFIRM: ... ]" bracket convention itself; 'describe' catches "none / describe".
PLACEHOLDER_TOKENS = ('confirm', 'unknown', 'unconfirmed', 'tbd', 'todo', 'pending', '???', '[', 'describe')

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

def canonical_sha256(obj) -> str:
    # ensure_ascii=False so this matches a JS canonicalizer that emits raw UTF-8
    # rather than \uXXXX escapes.
    canonical = json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False, ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

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

def validate_transform(transform):
    need(isinstance(transform, dict), 'transform: object required')
    need(transform.get('schema') == TRANSFORM_SCHEMA, 'Unsupported transform schema')
    anchors = transform.get('anchors')
    need(isinstance(anchors, dict) and set(anchors) == set(MEDALS),
         'transform.anchors must cover exactly the five frozen medal tiers')
    for k in MEDALS:
        finite(anchors[k], f'transform.anchors.{k}', 0, 1)
    weight = finite(transform.get('weight'), 'transform.weight', 0, 1)
    reference_anchor = finite(transform.get('reference_anchor'), 'transform.reference_anchor', 0, 1)
    alt = transform.get('alternative_weights')
    need(isinstance(alt, list) and bool(alt), 'transform.alternative_weights: nonempty list required')
    alt_weights = [finite(x, 'transform.alternative_weights[]', 0, 1) for x in alt]
    text(transform.get('description'), 'transform.description')
    return weight, {k: float(anchors[k]) for k in MEDALS}, reference_anchor, alt_weights

def utc_date(dt):
    return dt.astimezone(timezone.utc).date().isoformat()

def has_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(tok in lowered for tok in PLACEHOLDER_TOKENS)

def validate_disclosure(disclosure):
    need(isinstance(disclosure, dict), 'plan.disclosure: object required')
    for field in DISCLOSURE_FIELDS:
        value = text(disclosure.get(field), f'disclosure.{field}')
        need(not has_placeholder(value), f'disclosure.{field}: placeholder text not allowed (still unanswered)')
    return disclosure

def validate_binding_rules(plan, anchors):
    # The plan freezes *which* official sources will later supply the medal and
    # rubric (binding.source / binding.rubric), and the exact tier set -- not a
    # rubric hash, since a design frozen before a rating's next version cannot
    # know that version's rubric. See README "The three records".
    rules = plan.get('binding_rules')
    need(isinstance(rules, dict), 'plan.binding_rules: object required')
    text(rules.get('medal_source'), 'binding_rules.medal_source')
    text(rules.get('rubric_source'), 'binding_rules.rubric_source')
    tiers = rules.get('tiers')
    need(isinstance(tiers, list) and bool(tiers), 'binding_rules.tiers: nonempty list required')
    need(set(tiers) == set(anchors),
         'binding_rules.tiers must equal exactly the frozen transform anchor tiers')
    return rules

def validate_binding(binding, plan, plan_hash, frozen, anchors, provider_ids, outcome_rows):
    need(isinstance(binding, dict), 'binding: object required')
    need(binding.get('schema') == BINDING_SCHEMA, 'Unsupported binding schema')
    need(binding.get('plan_sha256') == plan_hash,
         'Binding does not reference the exact frozen plan bytes')
    need(binding.get('rating_name') == plan.get('rating_name'),
         'Binding rating_name does not match the plan (wrong rating vintage)')
    need(binding.get('rating_version') == plan.get('rating_version'),
         'Binding rating_version does not match the plan (wrong rating vintage)')
    bound_at = stamp(binding.get('bound_at'), 'bound_at')
    need(bound_at >= frozen, 'bound_at is earlier than the plan\'s frozen_at')
    source = binding.get('source')
    need(isinstance(source, dict), 'binding.source: object required')
    text(source.get('url'), 'binding.source.url')
    digest(source.get('sha256'), 'binding.source.sha256')
    source_retrieved = stamp(source.get('retrieved_utc'), 'binding.source.retrieved_utc')
    need(source_retrieved <= bound_at, 'binding.source.retrieved_utc is after bound_at')
    rubric = binding.get('rubric')
    need(isinstance(rubric, dict), 'binding.rubric: object required')
    text(rubric.get('url'), 'binding.rubric.url')
    digest(rubric.get('sha256'), 'binding.rubric.sha256')
    rubric_retrieved = stamp(rubric.get('retrieved_utc'), 'binding.rubric.retrieved_utc')
    need(rubric_retrieved <= bound_at, 'binding.rubric.retrieved_utc is after bound_at')
    medals = binding.get('medals')
    need(isinstance(medals, dict), 'binding.medals: object required')
    need(set(medals) == provider_ids,
         'binding.medals must cover exactly the set of test providers in the plan (missing or extra provider)')
    for provider, tier in medals.items():
        need(isinstance(tier, str) and tier, f'binding.medals.{provider}: nonempty tier required')
        need(tier in anchors,
             f'binding.medals.{provider}: tier "{tier}" is not one of the frozen transform anchors')
    for row in outcome_rows if isinstance(outcome_rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get('started_at'), str):
            continue
        try:
            started = stamp(row['started_at'], 'started_at')
        except InvalidPacket:
            continue
        need(bound_at < started,
             f"{row.get('trial_id')}: binding bound_at is not strictly before the trial's started_at")
    return bound_at, medals

def validate(plan, outcomes, binding, plan_hash, binding_hash):
    need(plan.get('schema') == PLAN_SCHEMA, 'Unsupported plan schema')
    need(outcomes.get('schema') == OUTCOME_SCHEMA, 'Unsupported outcome schema')
    need(outcomes.get('plan_sha256') == plan_hash, 'Outcome packet does not match exact frozen plan bytes')
    need(outcomes.get('binding_sha256') == binding_hash, 'Outcome packet does not match exact binding bytes')
    need(type(plan.get('synthetic')) is bool, 'Plan must declare synthetic true or false')
    for field in ('study_id', 'rating_name', 'rating_version', 'outcome_definition'):
        text(plan.get(field), field)
    frozen = stamp(plan.get('frozen_at'), 'frozen_at')
    minimum = plan.get('minimum_providers')
    need(type(minimum) is int and minimum >= 8, 'At least eight independent providers required by v1 protocol')
    finite(plan.get('minimum_lift'), 'minimum_lift', 0, 1)
    validate_disclosure(plan.get('disclosure'))

    transform = plan.get('transform')
    weight, anchors, reference_anchor, alt_weights = validate_transform(transform)
    transform_hash = canonical_sha256(transform)
    need(plan.get('transform_sha256') == transform_hash,
         'transform_sha256 does not match the canonical bytes of the inline transform')
    validate_binding_rules(plan, anchors)

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
    provider_ids = {row.get('provider_id') for row in rows
                     if isinstance(row, dict) and isinstance(row.get('provider_id'), str)}
    bound_at, medals = validate_binding(binding, plan, plan_hash, frozen, anchors, provider_ids, actuals)

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
        # medal is bound after the plan is frozen -- see validate_binding() above -- and
        # p_with_rating is always recomputed from that bound medal, never supplied by the plan.
        medal = medals[provider]
        computed_pr = (1 - weight) * pb + weight * anchors[medal]
        computed_pref = (1 - weight) * pb + weight * reference_anchor
        pr = computed_pr
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
        credits = finite(actual.get('credits_redeemed_usd', 0), 'credits_redeemed_usd', 0)
        need(credits <= cost, f'{rid}: credits_redeemed_usd exceeds total_cost_usd')
        need('p95_ms' in actual, f'{rid}: p95_ms required, use null for unavailable failed-job latency')
        latency = actual.get('p95_ms')
        if latency is not None:
            latency = finite(latency, 'p95_ms')
        need(state != 'complete' or latency is not None, f'{rid}: completed job lacks latency evidence')
        digest(actual.get('receipt_sha256'), 'receipt_sha256')
        text(actual.get('receipt_ref'), 'receipt_ref')
        y = int(state == 'complete' and accepted >= accepted_min and
                latency is not None and latency <= latency_max and cost <= cost_max)
        lb, lr, lref = (pb - y) ** 2, (pr - y) ** 2, (computed_pref - y) ** 2
        groups.setdefault(provider, []).append({
            'trial_id': rid, 'session_id': row['session_id'], 'date': utc_date(start),
            'medal': medal, 'passed': y, 'p_baseline': pb,
            'baseline_brier': lb, 'with_rating_brier': lr, 'reference_brier': lref,
            'lift_vs_baseline': lb - lr, 'lift_vs_reference': lref - lr})
        costs.append({'trial_id':rid, 'total_cost_usd':cost, 'credits_redeemed_usd':credits,
            'accepted':accepted, 'cost_per_1000_accepted':1000*cost/accepted if accepted else None})
    need(ids == set(out), 'Outcome packet contains unplanned trials')
    need(len(groups) >= minimum, f'Only {len(groups)} held-out providers; {minimum} required')
    for provider, rows_ in groups.items():
        n_trials = len(rows_)
        n_sessions = len({r['session_id'] for r in rows_})
        n_dates = len({r['date'] for r in rows_})
        need(n_trials >= MIN_TRIALS_PER_PROVIDER,
             f'{provider}: coverage floor not met ({n_trials} trials, need {MIN_TRIALS_PER_PROVIDER})')
        need(n_sessions >= MIN_SESSIONS_PER_PROVIDER,
             f'{provider}: coverage floor not met ({n_sessions} distinct sessions, need {MIN_SESSIONS_PER_PROVIDER})')
        need(n_dates >= MIN_DATES_PER_PROVIDER,
             f'{provider}: coverage floor not met ({n_dates} distinct UTC dates, need {MIN_DATES_PER_PROVIDER})')
    return groups, costs, weight, anchors, reference_anchor, alt_weights, transform, transform_hash

def _weighted_liftw(groups, weight, anchors, reference_anchor):
    base_m, rating_m, ref_m = {}, {}, {}
    for provider, rows_ in groups.items():
        base_vals, rating_vals, ref_vals = [], [], []
        for r in rows_:
            pb, y, medal = r['p_baseline'], r['passed'], r['medal']
            pr = (1 - weight) * pb + weight * anchors[medal]
            pref = (1 - weight) * pb + weight * reference_anchor
            base_vals.append((pb - y) ** 2)
            rating_vals.append((pr - y) ** 2)
            ref_vals.append((pref - y) ** 2)
        base_m[provider] = statistics.mean(base_vals)
        rating_m[provider] = statistics.mean(rating_vals)
        ref_m[provider] = statistics.mean(ref_vals)
    mean_lift_baseline = statistics.mean(base_m.values()) - statistics.mean(rating_m.values())
    mean_lift_reference = statistics.mean(ref_m.values()) - statistics.mean(rating_m.values())
    return mean_lift_baseline, mean_lift_reference

def evaluate(plan_bytes: bytes, binding_bytes: bytes, outcome_bytes: bytes):
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    binding_hash = hashlib.sha256(binding_bytes).hexdigest()
    result = {'schema': RESULT_SCHEMA, 'test_version':VERSION,
        'plan_sha256':plan_hash, 'binding_sha256':binding_hash,
        'outcomes_sha256':hashlib.sha256(outcome_bytes).hexdigest(),
        'evidence_status':'UNVERIFIED_SUBMISSION',
        'scope':'Predictive ablation on supplied job outcomes; not a cloud/security/credit certification.'}
    try:
        plan, binding, outcomes = parse(plan_bytes), parse(binding_bytes), parse(outcome_bytes)
        result['evidence_status'] = 'SYNTHETIC_DEMO' if plan.get('synthetic') is True else 'UNVERIFIED_SUBMISSION'
        result['rating_name'] = plan.get('rating_name')
        groups, costs, weight, anchors, reference_anchor, alt_weights, transform, transform_hash = validate(plan, outcomes, binding, plan_hash, binding_hash)
        providers = sorted(groups)
        base_means = {p: statistics.mean(x['baseline_brier'] for x in groups[p]) for p in providers}
        rating_means = {p: statistics.mean(x['with_rating_brier'] for x in groups[p]) for p in providers}
        ref_means = {p: statistics.mean(x['reference_brier'] for x in groups[p]) for p in providers}
        diffs_baseline = [base_means[p] - rating_means[p] for p in providers]
        diffs_reference = [ref_means[p] - rating_means[p] for p in providers]
        interval_base = bootstrap(diffs_baseline)
        interval_ref = bootstrap(diffs_reference)
        baseline_brier = statistics.mean(base_means.values())
        with_rating_brier = statistics.mean(rating_means.values())
        reference_brier = statistics.mean(ref_means.values())
        mean_lift_baseline = baseline_brier - with_rating_brier
        mean_lift_reference = reference_brier - with_rating_brier
        sensitivity = []
        for altw in alt_weights:
            mlb, mlr = _weighted_liftw(groups, altw, anchors, reference_anchor)
            sensitivity.append({'weight': altw, 'mean_lift_vs_baseline': mlb, 'mean_lift_vs_reference': mlr})
        loo = []
        for excluded in providers:
            remaining = [p for p in providers if p != excluded]
            mlr = statistics.mean(ref_means[p] for p in remaining) - statistics.mean(rating_means[p] for p in remaining)
            loo.append({'excluded_provider': excluded, 'mean_lift_vs_reference': mlr})
        if interval_ref[0] > plan['minimum_lift']:
            signal = 'positive'
        elif interval_ref[1] < 0:
            signal = 'negative'
        else:
            signal = 'inconclusive'
        subsidized_trials = sum(1 for c in costs if c['credits_redeemed_usd'] > 0)
        result.update(status='PILOT_DESCRIPTIVE_RESULT', signal=signal,
            providers=len(groups), trials=sum(map(len, groups.values())),
            subsidized_trials=subsidized_trials,
            comparison_vs_baseline={'baseline_brier': baseline_brier, 'with_rating_brier': with_rating_brier,
                'mean_lift': mean_lift_baseline, 'bootstrap_95': interval_base},
            comparison_vs_reference={'reference_brier': reference_brier, 'with_rating_brier': with_rating_brier,
                'mean_lift': mean_lift_reference, 'bootstrap_95': interval_ref,
                'note': 'Isolates medal-specific information from the mere presence of a rating input.'},
            sensitivity=sensitivity, leave_one_provider_out=loo,
            minimum_lift=plan['minimum_lift'], bootstrap_draws=BOOTSTRAPS, seed=SEED,
            transform=transform, transform_sha256=transform_hash,
            binding=binding, binding_sha256=binding_hash,
            provider_results=groups, economics=costs)
    except (InvalidPacket, ValueError, TypeError, KeyError) as exc:
        result.update(status='HOLD', reason=str(exc))
    return result

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan', type=Path, required=True)
    ap.add_argument('--binding', type=Path, required=True)
    ap.add_argument('--outcomes', type=Path, required=True)
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    try:
        result = evaluate(args.plan.read_bytes(), args.binding.read_bytes(), args.outcomes.read_bytes())
    except OSError as exc:
        print(str(exc), file=sys.stderr); return 2
    rendered = json.dumps(result, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
    else:
        print(rendered, end='')
    # Exit codes: 0 = admissible descriptive result, 2 = HOLD (evidence contract not met).
    return 2 if result['status'] == 'HOLD' else 0

if __name__ == '__main__':
    sys.exit(main())
