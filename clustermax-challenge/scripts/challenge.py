#!/usr/bin/env python3
"""Offline test of whether a rating's medals carry provider-ranking information. Stdlib only.

v1.4.0 (primary test changed; v1.3 comparisons kept as descriptive only)
-----------------------------------------------------------------------
Headline question: do the bound medals rank the held-out providers better than chance?

* Primary statistic T: the provider-equal-weighted mean over test providers of
  Brier(p_level) - Brier(p_medal), where
      p_medal = (1-w)*p_baseline + w*anchor[medal of provider]
      p_level = (1-w)*p_baseline + w*a_bar
  and a_bar is the provider-weighted mean of the bound anchors across the test cohort.
  Both predictors receive the same average shift, so T measures only the ranking
  information in which provider got which medal -- not a level/calibration shift.
* Null: medal labels are exchangeable across providers (medals are provider-level).
  Every distinct assignment of the multiset of bound medals to providers is
  enumerated when there are at most PERMUTATION_LIMIT (20000) of them; the p-value is
  then count/N with the observed assignment counted among the N (no +1). Otherwise
  PERMUTATION_LIMIT seeded Fisher-Yates shuffles (seed 20260923) are drawn and the
  p-value is (1+count)/(1+N). Ties use a 1e-12 tolerance.
* signal = positive  iff p_help <= 0.05 and T >  minimum_lift
           negative  iff p_hurt <= 0.05 and T < -minimum_lift
           not_testable if the cohort has fewer than 2 distinct bound medals
           inconclusive otherwise.
  The provider-bootstrap interval for T is reported as descriptive only.
* v1.3's comparison_vs_baseline and comparison_vs_reference (fixed 0.50 anchor) are
  reported under "descriptive": they include level shifts and do not isolate medal
  information (all medal anchors above 0.50 reward any cohort that passes often).

Locks added in v1.4: the plan's transform must canonically hash to a transform listed
in design/registry.json; anchors must be strictly decreasing Platinum > Gold > Silver >
Bronze > Underperforming; all trials sharing a workload_sha256 must carry identical
gates; training_providers must be nonempty; a binding for a registered rating version
must cite a registered medal-table source digest and match the registered
transcription tier-for-tier (unregistered ratings are scored but flagged
source_unverified).

What is NOT locked: the per-row p_baseline remains the submitter's choice. That is
why the baseline model_sha256 and a frozen_at strictly before binding (and before
any outcome) matter: a baseline chosen after seeing the medals can still be tuned
against them, and this engine cannot detect that from the numbers alone.

Python/JS parity rules (index.html embeds the same engine):
* Integer fields accept any JSON number that is mathematically an integer (900 or
  900.0); Python: float.is_integer(), JS: Number.isInteger().
* Timestamps are RFC 3339 with year 1970-2199; fractional seconds are truncated to
  whole microseconds and compared exactly in both engines.
* Canonical JSON for hashing = sorted keys (UTF-16 code-unit order), no whitespace,
  numbers in ECMAScript Number#toString form (shortest round-trip; 100.0 -> 100,
  1e-07 -> 1e-7), raw UTF-8 strings; lone surrogates are refused.
* Tier and provider lookups are own-property only ("constructor", "__proto__" are
  ordinary unknown strings).
* Means are naive left-to-right float sums in both engines.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.4.0'
PLAN_SCHEMA = 'secondrun.rating-plan.v4'
OUTCOME_SCHEMA = 'secondrun.rating-outcomes.v4'
RESULT_SCHEMA = 'secondrun.rating-result.v5'
TRANSFORM_SCHEMA = 'secondrun.rating-transform.v1'
BINDING_SCHEMA = 'secondrun.rating-binding.v2'
REGISTRY_SCHEMA = 'secondrun.rating-registry.v1'
BOOTSTRAPS = 5000
PERMUTATION_LIMIT = 20000
ALPHA = 0.05
TIE_TOLERANCE = 1e-12
SEED = 20260923
MIN_YEAR, MAX_YEAR = 1970, 2199
CONTEXT = ('provider_id', 'service_id', 'region', 'workload_sha256',
           'validator_sha256', 'customer_role', 'support', 'session_id')
STATES = ('complete', 'timeout', 'error', 'provision_failed', 'aborted')
MEDALS = ('Platinum', 'Gold', 'Silver', 'Bronze', 'Underperforming')
MIN_TRIALS_PER_PROVIDER = 10
MIN_SESSIONS_PER_PROVIDER = 5
MIN_DATES_PER_PROVIDER = 3
DISCLOSURE_FIELDS = ('relationship', 'compensation', 'credits', 'special_support', 'editorial_influence')
# Case-insensitive substrings that mark an unanswered disclosure placeholder. '[' catches
# the "[CONFIRM: ... ]" bracket convention itself; 'describe' catches "none / describe".
PLACEHOLDER_TOKENS = ('confirm', 'unknown', 'unconfirmed', 'tbd', 'todo', 'pending', '???', '[', 'describe')
# ECMAScript String.prototype.trim() whitespace + line terminators, so text() agrees with JS.
JS_WHITESPACE = ('\t\n\x0b\x0c\r \xa0        '
                 '        　﻿')
PERMUTATION_QUESTION = 'Do medals rank providers better than chance?'
DESCRIPTIVE_NOTE = ('v1.3 comparisons, kept for continuity. Both include level shifts: every medal '
                    'anchor from Bronze up sits above the 0.50 reference, so a cohort that passes '
                    'often "improves" whatever its medals are. They do not isolate medal '
                    'information; the medal permutation test does.')
REGISTRY_PATH = ROOT / 'design' / 'registry.json'
STAMP_RE = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})'
                      r'(?:\.([0-9]+))?(Z|[+-][0-9]{2}:[0-9]{2})')

class InvalidPacket(ValueError):
    pass

def need(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidPacket(message)

def load_registry(path: Path = REGISTRY_PATH):
    reg = json.loads(path.read_text(encoding='utf-8'))
    need(reg.get('schema') == REGISTRY_SCHEMA, 'Unsupported registry schema')
    return reg

REGISTRY = load_registry()

def text(value, name):
    need(isinstance(value, str) and bool(value.strip(JS_WHITESPACE)), f'{name}: nonempty text required')
    return value

def digest(value, name):
    need(isinstance(value, str) and len(value) == 64 and
         all(c in '0123456789abcdef' for c in value), f'{name}: lowercase SHA-256 required')
    return value

def _number(value):
    # JSON numbers only (bool excluded); ints go through float exactly as JSON.parse would.
    if type(value) not in (int, float):
        return None
    try:
        f = float(value)
    except OverflowError:
        return None
    return f if math.isfinite(f) else None

def finite(value, name, low=0.0, high=None):
    f = _number(value)
    need(f is not None, f'{name}: finite number required')
    need(f >= low and (high is None or f <= high), f'{name}: out of range')
    return f

def integer(value, name):
    f = _number(value)
    need(f is not None and f.is_integer(), f'{name}: integer required')
    return int(f)

def stamp(value, name):
    text(value, name)
    m = STAMP_RE.fullmatch(value)
    need(m is not None, f'{name}: RFC3339 timestamp required')
    y, mo, d, h, mi, s = (int(g) for g in m.groups()[:6])
    need(MIN_YEAR <= y <= MAX_YEAR, f'{name}: year outside {MIN_YEAR}-{MAX_YEAR}')
    micro = int(((m.group(7) or '') + '000000')[:6])
    tz = m.group(8)
    if tz == 'Z':
        offset = timezone.utc
    else:
        oh, om = int(tz[1:3]), int(tz[4:6])
        need(oh <= 23 and om <= 59, f'{name}: invalid timezone offset')
        delta = timedelta(hours=oh, minutes=om)
        offset = timezone(-delta if tz[0] == '-' else delta)
    try:
        return datetime(y, mo, d, h, mi, s, micro, tzinfo=offset)
    except ValueError as exc:
        raise InvalidPacket(f'{name}: invalid calendar date') from exc

def js_sorted(keys):
    # UTF-16 code-unit order, as Array.prototype.sort() compares strings.
    return sorted(keys, key=lambda k: k.encode('utf-16-be', 'surrogatepass'))

def es_number(value) -> str:
    """ECMAScript Number#toString for a finite JSON number (same digits as JSON.stringify)."""
    f = _number(value)
    need(f is not None, 'canonical JSON: finite number required')
    if f == 0:
        return '0'
    sign = '-' if f < 0 else ''
    mant, _, exp = repr(abs(f)).partition('e')
    ip, _, fp = mant.partition('.')
    raw = (ip + fp).lstrip('0')
    point = (int(exp) if exp else 0) - len(fp)
    s = raw.rstrip('0')
    point += len(raw) - len(s)
    k = len(s)
    n = point + k
    if k <= n <= 21:
        out = s + '0' * (n - k)
    elif 0 < n <= 21:
        out = s[:n] + '.' + s[n:]
    elif -6 < n <= 0:
        out = '0.' + '0' * (-n) + s
    else:
        e = n - 1
        out = (s if k == 1 else s[0] + '.' + s[1:]) + 'e' + ('+' if e >= 0 else '-') + str(abs(e))
    return sign + out

_SURROGATE = re.compile('[\ud800-\udfff]')

def _canon_str(s):
    need(not _SURROGATE.search(s), 'canonical JSON: lone surrogate in string')
    return json.dumps(s, ensure_ascii=False)

def canonical_json(obj) -> str:
    if obj is None:
        return 'null'
    if obj is True:
        return 'true'
    if obj is False:
        return 'false'
    if isinstance(obj, str):
        return _canon_str(obj)
    if type(obj) in (int, float):
        return es_number(obj)
    if isinstance(obj, list):
        return '[' + ','.join(canonical_json(x) for x in obj) + ']'
    if isinstance(obj, dict):
        return '{' + ','.join(_canon_str(k) + ':' + canonical_json(obj[k]) for k in js_sorted(obj)) + '}'
    raise InvalidPacket('canonical JSON: unsupported value')

def canonical_sha256(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode('utf-8')).hexdigest()

def mean(xs):
    # Naive left-to-right sum: bit-identical to the JS engine's reduce().
    total = 0.0
    n = 0
    for x in xs:
        total += x
        n += 1
    return total / n

def quantile(xs, q):
    ys = sorted(xs)
    pos = (len(ys) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ys) - 1)
    return ys[lo] + (ys[hi] - ys[lo]) * (pos - lo)

def generator(seed=SEED):
    """Seeded uniform integers in [0, n); rejection-sampled 32-bit mixer shared with JS."""
    state = seed
    def below(n):
        nonlocal state
        limit = 2**32 - (2**32 % n)
        while True:
            state = (state + 0x6D2B79F5) & 0xffffffff
            t = state
            t = ((t ^ (t >> 15)) * (t | 1)) & 0xffffffff
            t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xffffffff)) & 0xffffffff
            x = (t ^ (t >> 14)) & 0xffffffff
            if x < limit:
                return x % n
    return below

def bootstrap(means):
    n = len(means)
    below = generator()
    draws = []
    for _ in range(BOOTSTRAPS):
        total = 0.0
        for _ in range(n):
            total += means[below(n)]
        draws.append(total / n)
    return [quantile(draws, 0.025), quantile(draws, 0.975)]

def parse(raw):
    # Refuse NaN/Infinity rather than letting nonstandard JSON into a receipt.
    def bad(s):
        raise InvalidPacket(f'Nonstandard JSON number: {s}')
    value = json.loads(raw, parse_constant=bad)
    need(isinstance(value, dict), 'JSON object required')
    return value

def normalize_name(name):
    return re.sub(r'[^A-Za-z0-9]', '', name).lower() if isinstance(name, str) else ''

def registered_rating(rating_name, rating_version, registry=None):
    for entry in (registry or REGISTRY).get('ratings', []):
        if (normalize_name(entry['rating_name']) == normalize_name(rating_name)
                and entry['rating_version'] == rating_version):
            return entry
    return None

def validate_transform(transform):
    need(isinstance(transform, dict), 'transform: object required')
    need(transform.get('schema') == TRANSFORM_SCHEMA, 'Unsupported transform schema')
    anchors = transform.get('anchors')
    need(isinstance(anchors, dict) and set(anchors) == set(MEDALS),
         'transform.anchors must cover exactly the five frozen medal tiers')
    clean = {k: finite(anchors[k], f'transform.anchors.{k}', 0, 1) for k in MEDALS}
    need(all(clean[MEDALS[i]] > clean[MEDALS[i + 1]] for i in range(len(MEDALS) - 1)),
         'transform.anchors must be strictly decreasing Platinum > Gold > Silver > Bronze > Underperforming')
    weight = finite(transform.get('weight'), 'transform.weight', 0, 1)
    reference_anchor = finite(transform.get('reference_anchor'), 'transform.reference_anchor', 0, 1)
    alt = transform.get('alternative_weights')
    need(isinstance(alt, list) and bool(alt), 'transform.alternative_weights: nonempty list required')
    alt_weights = [finite(x, 'transform.alternative_weights[]', 0, 1) for x in alt]
    text(transform.get('description'), 'transform.description')
    return weight, clean, reference_anchor, alt_weights

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
    need(all(isinstance(t, str) for t in tiers) and set(tiers) == set(anchors),
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
    entry = registered_rating(binding.get('rating_name'), binding.get('rating_version'))
    if entry is not None:
        cited = {s['sha256'] for s in entry['medal_table_sources']}
        need(source['sha256'] in cited,
             f"binding.source.sha256 is not a registered medal-table source for {entry['rating_name']} {entry['rating_version']}")
        transcription = entry.get('transcription')
        if transcription is not None:
            tiers = transcription['tiers']
            for provider, tier in medals.items():
                need(provider in tiers,
                     f'binding.medals.{provider}: provider is not in the registered transcription (exact name required)')
                need(tiers[provider] == tier,
                     f'binding.medals.{provider}: bound tier "{tier}" differs from the registered transcription "{tiers[provider]}"')
        source_verification = 'registered_source'
    else:
        source_verification = 'source_unverified'
    for row in outcome_rows if isinstance(outcome_rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get('started_at'), str):
            continue
        try:
            started = stamp(row['started_at'], 'started_at')
        except InvalidPacket:
            continue
        need(bound_at < started,
             f"{row.get('trial_id')}: binding bound_at is not strictly before the trial's started_at")
    return bound_at, medals, source_verification

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
    need(_number(minimum) is not None and _number(minimum).is_integer() and minimum >= 8,
         'At least eight independent providers required by v1 protocol')
    minimum = int(minimum)
    minimum_lift = finite(plan.get('minimum_lift'), 'minimum_lift', 0, 1)
    validate_disclosure(plan.get('disclosure'))

    transform = plan.get('transform')
    weight, anchors, reference_anchor, alt_weights = validate_transform(transform)
    transform_hash = canonical_sha256(transform)
    need(plan.get('transform_sha256') == transform_hash,
         'transform_sha256 does not match the canonical bytes of the inline transform')
    need(transform_hash in {t['sha256'] for t in REGISTRY['transforms']},
         'transform is not a registered published transform (design/registry.json)')
    validate_binding_rules(plan, anchors)

    models = [plan.get('baseline'), plan.get('with_rating')]
    for model in models:
        need(isinstance(model, dict), 'Both predictor definitions required')
        text(model.get('description'), 'predictor description')
        digest(model.get('model_sha256'), 'model_sha256')
        need(stamp(model.get('frozen_at'), 'model frozen_at') <= frozen, 'Predictor frozen after plan')
        train = model.get('training_providers')
        need(isinstance(train, list) and all(isinstance(x, str) and x for x in train), 'Training-provider list required')
        need(len(train) > 0, 'training_providers must be nonempty (held-out claim is vacuous without training providers)')
        inputs = model.get('inputs')
        need(isinstance(inputs, list) and inputs and all(isinstance(x, str) and x for x in inputs), 'Predictor inputs required')
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
    bound_at, medals, source_verification = validate_binding(
        binding, plan, plan_hash, frozen, anchors, provider_ids, actuals)

    groups = {}
    train = set(models[0]['training_providers'])
    costs = []
    gates_by_workload = {}
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
        # every rating-informed probability is recomputed from that bound medal.
        medal = medals[provider]
        gates = row.get('gates')
        need(isinstance(gates, dict), 'Job gates required')
        accepted_min = integer(gates.get('accepted_min'), 'accepted_min')
        need(accepted_min > 0, 'Positive accepted_min integer required')
        latency_max = finite(gates.get('p95_max_ms'), 'p95_max_ms')
        cost_max = finite(gates.get('cost_max_usd'), 'cost_max_usd')
        gate_key = (accepted_min, latency_max, cost_max)
        prior = gates_by_workload.setdefault(row['workload_sha256'], gate_key)
        need(prior == gate_key,
             f'{rid}: gates differ from other trials with the same workload_sha256 (gates must be uniform across providers)')
        state = actual.get('status')
        need(isinstance(state, str) and state in STATES, f'{rid}: terminal status required')
        accepted = integer(actual.get('accepted'), f'{rid}: accepted')
        attempted = integer(actual.get('attempted'), f'{rid}: attempted')
        need(0 <= accepted <= attempted, f'{rid}: accepted and attempted must be consistent integers')
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
        groups.setdefault(provider, []).append({
            'trial_id': rid, 'session_id': row['session_id'], 'date': utc_date(start),
            'medal': medal, 'passed': y, 'p_baseline': pb})
        costs.append({'trial_id': rid, 'total_cost_usd': cost, 'credits_redeemed_usd': credits,
            'accepted': accepted, 'cost_per_1000_accepted': 1000 * cost / accepted if accepted else None})
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
    return {'groups': groups, 'costs': costs, 'weight': weight, 'anchors': anchors,
            'reference_anchor': reference_anchor, 'alt_weights': alt_weights, 'transform': transform,
            'transform_hash': transform_hash, 'minimum_lift': minimum_lift,
            'source_verification': source_verification}

# ---- statistics ---------------------------------------------------------------------

def blend(weight, pb, anchor):
    return (1 - weight) * pb + weight * anchor

def sq(x):
    return x * x

def provider_means(rows, weight, anchor, level, reference_anchor):
    """Per-provider mean Brier of baseline, medal, level and 0.50-reference predictors."""
    base, medal_, lvl, ref = [], [], [], []
    for r in rows:
        pb, y = r['p_baseline'], r['passed']
        base.append(sq(pb - y))
        medal_.append(sq(blend(weight, pb, anchor) - y))
        lvl.append(sq(blend(weight, pb, level) - y))
        ref.append(sq(blend(weight, pb, reference_anchor) - y))
    return mean(base), mean(medal_), mean(lvl), mean(ref)

def level_lift(rows, weight, anchor, level):
    lvl, med = [], []
    for r in rows:
        pb, y = r['p_baseline'], r['passed']
        lvl.append(sq(blend(weight, pb, level) - y))
        med.append(sq(blend(weight, pb, anchor) - y))
    return mean(lvl) - mean(med)

def count_arrangements(counts, cap):
    """Distinct assignments of a medal multiset; returns cap+1 once it exceeds cap."""
    total = 1
    remaining = sum(counts)
    for c in counts:
        k = min(c, remaining - c)
        b = 1
        for j in range(k):
            b = b * (remaining - j) // (j + 1)
            if b > cap:
                return cap + 1
        total *= b
        if total > cap:
            return cap + 1
        remaining -= c
    return total

def statistic(matrix, assign):
    total = 0.0
    for i, j in enumerate(assign):
        total += matrix[i][j]
    return total / len(assign)

def next_permutation(a):
    i = len(a) - 2
    while i >= 0 and a[i] >= a[i + 1]:
        i -= 1
    if i < 0:
        return False
    j = len(a) - 1
    while a[j] <= a[i]:
        j -= 1
    a[i], a[j] = a[j], a[i]
    a[i + 1:] = reversed(a[i + 1:])
    return True

def permutation_test(groups, providers, weight, anchors, medal_of):
    present = [m for m in MEDALS if any(medal_of[p] == m for p in providers)]
    level = mean(anchors[medal_of[p]] for p in providers)
    matrix = [[level_lift(groups[p], weight, anchors[m], level) for m in present] for p in providers]
    observed = [present.index(medal_of[p]) for p in providers]
    t_obs = statistic(matrix, observed)
    per_provider = [matrix[i][j] for i, j in enumerate(observed)]
    base = {'question': PERMUTATION_QUESTION,
            'statistic': 'T = provider-equal-weighted mean of Brier(p_level) - Brier(p_medal); '
                         'p_level blends toward the cohort mean bound anchor, so T carries only ranking information',
            'null_hypothesis': 'bound medal labels are exchangeable across test providers',
            'T_obs': t_obs, 'level_anchor': level, 'distinct_medals': len(present),
            'medal_counts': {m: sum(1 for p in providers if medal_of[p] == m) for m in present},
            'alpha': ALPHA, 'tie_tolerance': TIE_TOLERANCE, 'seed': SEED,
            'provider_bootstrap_95': bootstrap(per_provider),
            'provider_bootstrap_note': 'Descriptive only; the signal uses the permutation p-values.'}
    if len(present) < 2:
        base.update(method='not_testable', permutations=0, p_help=None, p_hurt=None,
                    p_value_rule='fewer than 2 distinct bound medals: no permutation changes T')
        return base
    counts = [observed.count(j) for j in range(len(present))]
    total = count_arrangements(counts, PERMUTATION_LIMIT)
    ge = le = 0
    if total <= PERMUTATION_LIMIT:
        a = sorted(observed)
        n = 0
        while True:
            t = statistic(matrix, a)
            ge += t >= t_obs - TIE_TOLERANCE
            le += t <= t_obs + TIE_TOLERANCE
            n += 1
            if not next_permutation(a):
                break
        base.update(method='exact_enumeration', permutations=n, p_help=ge / n, p_hurt=le / n,
                    p_value_rule='count/N over all N distinct assignments; the observed assignment is one of the N (no +1)')
    else:
        below = generator()
        for _ in range(PERMUTATION_LIMIT):
            a = list(observed)
            for i in range(len(a) - 1, 0, -1):
                j = below(i + 1)
                a[i], a[j] = a[j], a[i]
            t = statistic(matrix, a)
            ge += t >= t_obs - TIE_TOLERANCE
            le += t <= t_obs + TIE_TOLERANCE
        n = PERMUTATION_LIMIT
        base.update(method='monte_carlo', permutations=n, p_help=(1 + ge) / (1 + n), p_hurt=(1 + le) / (1 + n),
                    p_value_rule='(1+count)/(1+N) over N seeded Fisher-Yates shuffles')
    return base

def decide(test, minimum_lift):
    if test['method'] == 'not_testable':
        return 'not_testable'
    if test['p_help'] <= ALPHA and test['T_obs'] > minimum_lift:
        return 'positive'
    if test['p_hurt'] <= ALPHA and test['T_obs'] < -minimum_lift:
        return 'negative'
    return 'inconclusive'

def evaluate(plan_bytes: bytes, binding_bytes: bytes, outcome_bytes: bytes):
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    binding_hash = hashlib.sha256(binding_bytes).hexdigest()
    result = {'schema': RESULT_SCHEMA, 'test_version': VERSION,
        'plan_sha256': plan_hash, 'binding_sha256': binding_hash,
        'outcomes_sha256': hashlib.sha256(outcome_bytes).hexdigest(),
        'evidence_status': 'UNVERIFIED_SUBMISSION',
        'scope': 'Predictive ablation on supplied job outcomes; not a cloud/security/credit certification.'}
    try:
        plan, binding, outcomes = parse(plan_bytes), parse(binding_bytes), parse(outcome_bytes)
        result['evidence_status'] = 'SYNTHETIC_DEMO' if plan.get('synthetic') is True else 'UNVERIFIED_SUBMISSION'
        result['rating_name'] = plan.get('rating_name')
        v = validate(plan, outcomes, binding, plan_hash, binding_hash)
        groups, weight, anchors, ref_anchor = v['groups'], v['weight'], v['anchors'], v['reference_anchor']
        providers = js_sorted(groups)
        medal_of = {p: groups[p][0]['medal'] for p in providers}
        test = permutation_test(groups, providers, weight, anchors, medal_of)
        level = test['level_anchor']
        test['sensitivity'] = [{'weight': w2, 'T_obs': mean(level_lift(groups[p], w2, anchors[medal_of[p]], level)
                                                           for p in providers)} for w2 in v['alt_weights']]
        signal = decide(test, v['minimum_lift'])
        base_m, rating_m, level_m, ref_m = {}, {}, {}, {}
        for p in providers:
            base_m[p], rating_m[p], level_m[p], ref_m[p] = provider_means(
                groups[p], weight, anchors[medal_of[p]], level, ref_anchor)
            for r in groups[p]:
                pb, y = r['p_baseline'], r['passed']
                lb = sq(pb - y)
                lr = sq(blend(weight, pb, anchors[r['medal']]) - y)
                ll = sq(blend(weight, pb, level) - y)
                lref = sq(blend(weight, pb, ref_anchor) - y)
                r.update(baseline_brier=lb, with_rating_brier=lr, level_brier=ll, reference_brier=lref,
                         lift_vs_level=ll - lr, lift_vs_baseline=lb - lr, lift_vs_reference=lref - lr)
        baseline_brier = mean(base_m[p] for p in providers)
        with_rating_brier = mean(rating_m[p] for p in providers)
        reference_brier = mean(ref_m[p] for p in providers)
        test.update(level_brier=mean(level_m[p] for p in providers), with_rating_brier=with_rating_brier)
        sensitivity = []
        for w2 in v['alt_weights']:
            pm = [provider_means(groups[p], w2, anchors[medal_of[p]], level, ref_anchor) for p in providers]
            bm, rm, fm = mean(x[0] for x in pm), mean(x[1] for x in pm), mean(x[3] for x in pm)
            sensitivity.append({'weight': w2, 'mean_lift_vs_baseline': bm - rm, 'mean_lift_vs_reference': fm - rm})
        loo = []
        for excluded in providers:
            remaining = [p for p in providers if p != excluded]
            loo.append({'excluded_provider': excluded,
                        'mean_lift_vs_reference': mean(ref_m[p] for p in remaining) - mean(rating_m[p] for p in remaining)})
        subsidized_trials = sum(1 for c in v['costs'] if c['credits_redeemed_usd'] > 0)
        result.update(status='PILOT_DESCRIPTIVE_RESULT', signal=signal,
            source_verification=v['source_verification'],
            providers=len(groups), trials=sum(len(groups[p]) for p in providers),
            subsidized_trials=subsidized_trials,
            medal_permutation_test=test,
            descriptive={'note': DESCRIPTIVE_NOTE,
                'comparison_vs_baseline': {'baseline_brier': baseline_brier, 'with_rating_brier': with_rating_brier,
                    'mean_lift': baseline_brier - with_rating_brier,
                    'bootstrap_95': bootstrap([base_m[p] - rating_m[p] for p in providers])},
                'comparison_vs_reference': {'reference_anchor': ref_anchor, 'reference_brier': reference_brier,
                    'with_rating_brier': with_rating_brier, 'mean_lift': reference_brier - with_rating_brier,
                    'bootstrap_95': bootstrap([ref_m[p] - rating_m[p] for p in providers]),
                    'note': 'Fixed-anchor reference; includes a level shift whenever the cohort mean anchor differs from the reference anchor.'},
                'sensitivity': sensitivity, 'leave_one_provider_out': loo},
            minimum_lift=v['minimum_lift'], bootstrap_draws=BOOTSTRAPS, seed=SEED,
            transform=v['transform'], transform_sha256=v['transform_hash'], transform_registered=True,
            binding=binding, binding_sha256=binding_hash,
            provider_results={p: groups[p] for p in providers}, economics=v['costs'])
    except (InvalidPacket, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        result.update(status='HOLD', reason=str(exc))
    return result

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
