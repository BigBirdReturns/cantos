#!/usr/bin/env python3
"""R2 runner: ClusterMAX 3.0 medals vs providers' own status-page incidents in the
180 days before the 3.0 release.

A thin wrapper around scripts/retrospective.py. It imports and calls that module's
functions UNCHANGED (spearman, bootstrap_ci, permutation_p, load_incidents_doc,
measure_window, DeterministicRng, quantile, slugify, ...). What the wrapper adds is
only what plan-R2 declares and R1's runner cannot express:

  * a window that ENDS at the release date instead of starting at it
    (plan-R2.json: window_end_date, window_days);
  * six-tier ordinals from plan-R2.json;
  * the permutation-cap rule (exact when n! <= 500,000, else 20,000 random draws);
  * the capped-feed coverage rule (recent-incident feeds whose oldest record predates
    the window start are accepted; flagged per provider);
  * the pre-declared sensitivity list.

Refuses to run if PLAN-R2.md no longer matches plan-R2.json's plan_md_sha256, or if
this file no longer matches plan-R2.json's runner_sha256. Writes only
results/R2-result.json and results/R2-result.md. Stdlib only.
"""
from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE  # retrospective/
SCRIPTS = HERE.parent / 'scripts'


def _load_retro():
    spec = importlib.util.spec_from_file_location('retrospective_r1_module', SCRIPTS / 'retrospective.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules['retrospective_r1_module'] = mod
    spec.loader.exec_module(mod)
    return mod


R = _load_retro()

RESULT_SCHEMA = 'secondrun.retrospective-result.v1'
MAINTENANCE_TITLE = re.compile(r'\b(maintenance|planned|scheduled|upgrade)\b', re.I)


def verify_plan():
    md = ROOT / 'PLAN-R2.md'
    pj = ROOT / 'plan-R2.json'
    plan = R.load_json(pj)
    if plan.get('schema') != R.PLAN_SCHEMA:
        raise R.StudyError(f'{pj}: unexpected schema {plan.get("schema")!r}')
    actual = R.sha256_file(md)
    if actual != plan.get('plan_md_sha256'):
        raise R.PlanHashMismatch(f'PLAN-R2.md sha256 {actual} != plan-R2.json {plan.get("plan_md_sha256")}; refusing to run')
    me = R.sha256_file(Path(__file__))
    if me != plan.get('runner_sha256'):
        raise R.PlanHashMismatch(f'run_r2.py sha256 {me} != plan-R2.json runner_sha256 {plan.get("runner_sha256")}; refusing to run')
    return plan, actual, R.sha256_file(pj), me


def reading_from(boot):
    iv = boot['interval']
    if iv is None:
        return 'inconclusive'
    if iv[1] < 0:
        return 'consistent'
    if iv[0] > 0:
        return 'inconsistent'
    return 'inconclusive'


def perm(xs, ys, seed, rule):
    n = len(xs)
    cap = rule['exact_max_permutations'] if math.factorial(n) <= rule['exact_max_permutations'] else rule['random_draws']
    return R.permutation_p(xs, ys, seed, cap)


def analyse(entries, measure, plan):
    ords = [e['ordinal'] for e in entries]
    vals = [e[measure] for e in entries]
    seed = plan['bootstrap']['seed']
    rho = R.spearman(ords, vals)
    boot = R.bootstrap_ci(ords, vals, seed, plan['bootstrap']['draws'])
    pm = perm(ords, vals, seed, plan['permutation'])
    return {'spearman_rho': rho, 'bootstrap_95ci': boot, 'permutation': pm,
            'reading': reading_from(boot) if measure == plan['primary_measure'] else None}


def load_provider(name, tier, slug, incidents_dir, window_start, window_end, plan, input_hashes, strict=False):
    entry = {'name': name, 'tier': tier, 'slug': slug}
    path = incidents_dir / f'{slug}.json'
    if not path.exists():
        entry.update(status='excluded', reason=f'no incident data file found (expected {path.name})')
        return entry, None
    try:
        doc = R.load_incidents_doc(path)
    except R.StudyError as exc:
        entry.update(status='excluded', reason=str(exc))
        return entry, None
    input_hashes[f'incidents/{path.name}'] = R.sha256_file(path)
    cs_raw, ce_raw = doc.get('coverage_start'), doc.get('coverage_end')
    if not ce_raw:
        entry.update(status='excluded', reason='coverage_end not recorded')
        return entry, doc
    ce = R.parse_date(ce_raw)
    basis = 'declared_coverage'
    if cs_raw:
        cs = R.parse_date(cs_raw)
        if not (cs <= window_start and ce >= window_end):
            entry.update(status='excluded',
                         reason=f'coverage [{cs},{ce}] does not fully cover window [{window_start},{window_end})')
            return entry, doc
    else:
        # capped-feed rule (plan-R2): coverage_start null, oldest non-maintenance record predates window start
        starts = [R.parse_ts(i['started_utc']) for i in doc.get('incidents', []) if not i.get('is_maintenance')]
        oldest = min(starts) if starts else None
        if (not plan['capped_feed_rule']['enabled']) or strict:
            entry.update(status='excluded', reason='coverage_start not recorded (strict rule)')
            return entry, doc
        if oldest is None or oldest >= R.day_start_utc(window_start) or ce < window_end:
            entry.update(status='excluded',
                         reason=('coverage_start not recorded and the feed does not reach back past the window start '
                                 f'(oldest non-maintenance record {oldest.date() if oldest else None}; coverage_end {ce})'))
            return entry, doc
        basis = f'capped_feed_rule (oldest record {oldest.date()} < window start {window_start})'
    p, a, h, capped = R.measure_window(doc, window_start, window_end)
    entry.update(status='eligible', ordinal=plan['ordinal'][tier], coverage_basis=basis,
                 coverage=[cs_raw, ce_raw],
                 major_or_critical_incident_count=p, all_incident_count=a,
                 incident_hours=round(h, 4), incident_hours_capped=capped)
    return entry, doc


def counts_variants(doc, window_start, window_end):
    """Per-provider counts under the pre-declared sensitivity variants."""
    ws, we = R.day_start_utc(window_start), R.day_start_utc(window_end)
    critical_only = 0
    mislabel_dropped = 0
    for inc in doc.get('incidents', []):
        if inc.get('is_maintenance'):
            continue
        st = R.parse_ts(inc['started_utc'])
        if not (ws <= st < we):
            continue
        if inc.get('severity') == 'critical':
            critical_only += 1
        if inc.get('severity') in ('critical', 'major') and MAINTENANCE_TITLE.search(inc.get('title', '')):
            mislabel_dropped += 1
    return critical_only, mislabel_dropped


def evaluate(ratings_path, plan, provider_map, hot_names, incidents_dir, input_hashes):
    ratings = R.load_json(ratings_path)
    input_hashes[f'ratings/{ratings_path.name}' if ratings_path.parent.name == 'ratings' else ratings_path.name] = R.sha256_file(ratings_path)
    window_end = R.parse_date(plan['window_end_date'])
    window_start = window_end - timedelta(days=plan['window_days'])
    provs, included, docs = [], [], {}
    hot = None
    for p in ratings['providers']:
        name, tier = p['name'], p['tier']
        if tier not in plan['ordinal']:
            provs.append({'name': name, 'tier': tier, 'status': 'excluded',
                          'reason': f'tier {tier!r} is not rated in this analysis (excluded by plan)'})
            continue
        slug = provider_map.get(name, R.slugify(name))
        entry, doc = load_provider(name, tier, slug, incidents_dir, window_start, window_end, plan, input_hashes)
        if entry['status'] == 'eligible':
            if name in hot_names or slug == 'hot-aisle':
                entry.update(included_in_correlation=False, exclusion_reason='excluded by design (author working relationship)')
                hot = dict(entry)
            else:
                entry['included_in_correlation'] = True
                included.append(entry)
                docs[slug] = doc
        provs.append(entry)
    out = {'release': ratings.get('release'), 'published_date': ratings['published_date'],
           'window': {'start': str(window_start), 'end': str(window_end), 'days': plan['window_days']},
           'providers': provs, 'included_count': len(included), 'minimum_providers': plan['minimum_providers'],
           'sufficient': len(included) >= plan['minimum_providers'], 'hot_aisle': hot}
    if not out['sufficient']:
        out.update(reading='insufficient', analysis=None, sensitivities=None)
        return out
    analysis = {m: analyse(included, m, plan) for m in [plan['primary_measure']] + plan['secondary_measures']}
    out['analysis'] = analysis
    out['reading'] = analysis[plan['primary_measure']]['reading']
    out['sensitivities'] = sensitivities(included, docs, plan, window_start, window_end, ratings_path, provider_map, hot_names,
                                          incidents_dir)
    return out


def sensitivities(included, docs, plan, window_start, window_end, ratings_path, provider_map, hot_names, incidents_dir):
    pm = plan['primary_measure']
    seed = plan['bootstrap']['seed']
    draws = plan['bootstrap']['draws']
    S = {}
    # S1 leave-one-out
    loo = []
    for i, e in enumerate(included):
        rest = [x for j, x in enumerate(included) if j != i]
        if len(rest) < 3:
            continue
        a = analyse(rest, pm, plan)
        loo.append({'dropped': e['name'], 'n': len(rest), 'rho': a['spearman_rho'],
                    'bootstrap_95ci': a['bootstrap_95ci']['interval'], 'permutation_p': a['permutation']['p_value'],
                    'permutation_method': a['permutation']['method'], 'reading': a['reading']})
    rhos = [x['rho'] for x in loo if x['rho'] is not None]
    S['S1_leave_one_out'] = {'runs': loo, 'rho_min': min(rhos) if rhos else None, 'rho_max': max(rhos) if rhos else None,
                             'readings': {r: sum(1 for x in loo if x['reading'] == r) for r in ('consistent', 'inconclusive', 'inconsistent')}}
    # S2 permutation exactness / stability
    ords = [e['ordinal'] for e in included]
    vals = [e[pm] for e in included]
    n = len(included)
    exact = math.factorial(n) <= plan['permutation']['exact_max_permutations']
    if exact:
        S['S2_permutation'] = {'note': f'n! = {math.factorial(n)} <= {plan["permutation"]["exact_max_permutations"]}: main p is exact', 'main_p': R.permutation_p(ords, vals, seed, plan['permutation']['exact_max_permutations'])['p_value']}
    else:
        alt = R.permutation_p(ords, vals, seed + 1, plan['permutation']['stability_random_draws'])
        S['S2_permutation'] = {'note': f'n! = {math.factorial(n)} > {plan["permutation"]["exact_max_permutations"]}: main p uses {plan["permutation"]["random_draws"]} random draws; stability check with {plan["permutation"]["stability_random_draws"]} draws, seed {seed + 1}',
                               'main_p': R.permutation_p(ords, vals, seed, plan['permutation']['random_draws'])['p_value'], 'stability_p': alt['p_value']}
    # S3 maintenance-mislabel check
    adj = []
    dropped = []
    for e in included:
        slug = e['slug']
        crit_only, mis = counts_variants(docs[slug], window_start, window_end)
        x = dict(e)
        x[pm] = e[pm] - mis
        adj.append(x)
        if mis:
            dropped.append({'provider': e['name'], 'major_or_critical_titles_matching_maintenance_regex': mis})
    a3 = analyse(adj, pm, plan)
    S['S3_maintenance_mislabel'] = {'regex': MAINTENANCE_TITLE.pattern, 'providers_affected': dropped, 'rho': a3['spearman_rho'],
                                    'bootstrap_95ci': a3['bootstrap_95ci']['interval'], 'permutation_p': a3['permutation']['p_value'],
                                    'reading': a3['reading']}
    # S4 bootstrap seed robustness
    lows, highs = [], []
    n_seeds = plan['seed_robustness']['seeds']
    reads = {'consistent': 0, 'inconclusive': 0, 'inconsistent': 0}
    for s in range(1, n_seeds + 1):
        b = R.bootstrap_ci(ords, vals, s, draws)
        if b['interval'] is not None:
            lows.append(b['interval'][0])
            highs.append(b['interval'][1])
        reads[reading_from(b)] += 1
    S['S4_bootstrap_seed_robustness'] = {'seeds': f'1..{n_seeds}', 'draws': draws, 'readings': reads,
                                         'lower_bound_min': min(lows) if lows else None, 'lower_bound_max': max(lows) if lows else None,
                                         'upper_bound_min': min(highs) if highs else None, 'upper_bound_max': max(highs) if highs else None}
    # S5 strict coverage rule (no capped-feed acceptance)
    strict_set = [e for e in included if 'capped_feed_rule' not in e['coverage_basis']]
    if len(strict_set) >= plan['minimum_providers']:
        a5 = analyse(strict_set, pm, plan)
        S['S5_strict_coverage'] = {'n': len(strict_set), 'dropped': [e['name'] for e in included if e not in strict_set],
                                   'rho': a5['spearman_rho'], 'bootstrap_95ci': a5['bootstrap_95ci']['interval'],
                                   'permutation_p': a5['permutation']['p_value'], 'permutation_method': a5['permutation']['method'],
                                   'reading': a5['reading']}
    else:
        S['S5_strict_coverage'] = {'n': len(strict_set), 'reading': 'insufficient'}
    # S6 critical-only measure
    crit = []
    for e in included:
        c, _ = counts_variants(docs[e['slug']], window_start, window_end)
        x = dict(e)
        x[pm] = c
        crit.append(x)
    a6 = analyse(crit, pm, plan)
    S['S6_critical_only'] = {'rho': a6['spearman_rho'], 'bootstrap_95ci': a6['bootstrap_95ci']['interval'],
                             'permutation_p': a6['permutation']['p_value'], 'reading': a6['reading']}
    return S


def run():
    plan, md_hash, pj_hash, runner_hash = verify_plan()
    input_hashes = {'PLAN-R2.md': md_hash, 'plan-R2.json': pj_hash, 'run_r2.py': runner_hash}
    pm_path = ROOT / 'provider_map.json'
    pm2_path = ROOT / plan['provider_map_r2_file']
    provider_map = dict(R.load_json(pm_path))
    provider_map.update(R.load_json(pm2_path))
    input_hashes['provider_map.json'] = R.sha256_file(pm_path)
    input_hashes[plan['provider_map_r2_file']] = R.sha256_file(pm2_path)
    incidents_dir = ROOT / 'incidents'
    hot_names = set(plan.get('excluded_by_design', []))
    res = {}
    for key, field, rel in (('primary', 'primary_release', plan['ratings_files']['primary']),
                            ('secondary', 'secondary_release', plan['ratings_files']['secondary'])):
        ratings_path = (HERE.parent / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
        res[key] = evaluate(ratings_path, plan, provider_map, hot_names, incidents_dir, input_hashes)
        res[key]['plan_release_label'] = plan[field]
    return {'schema': RESULT_SCHEMA, 'study_id': plan['study_id'], 'generated_at': datetime.now(timezone.utc).isoformat(),
            'plan_hash_verified': True, 'plan_md_sha256': md_hash, 'runner_sha256': runner_hash,
            'input_hashes': input_hashes, 'deviations': [f"{a['what']} ({a['why']}) Effect: {a['effect']}" for a in plan.get('post_freeze_amendments', [])], 'primary': res['primary'], 'secondary': res['secondary']}


def fmt_row(e):
    if e.get('status') == 'eligible':
        extra = (f"ordinal={e['ordinal']} major/critical={e['major_or_critical_incident_count']} all={e['all_incident_count']} "
                 f"hours={e['incident_hours']}{' (capped)' if e.get('incident_hours_capped') else ''} [{e['coverage_basis']}]")
        return f"- **{e['name']}** ({e['tier']}): eligible -- {extra}"
    return f"- **{e['name']}** ({e.get('tier')}): excluded -- {e.get('reason')}"


def render(out):
    L = ['# R2 result: ClusterMAX 3.0 medals vs status-page incidents in the 180 days before release', '',
         f"Study: `{out['study_id']}`. Generated {out['generated_at']}.", '',
         f"Plan hash verified: **{out['plan_hash_verified']}** (PLAN-R2.md sha256 `{out['plan_md_sha256']}`; run_r2.py sha256 `{out['runner_sha256']}`).", '',
         '## Input hashes', '']
    for k, v in sorted(out['input_hashes'].items()):
        L.append(f'- `{k}`: `{v}`')
    L += ['', '## Deviations from the frozen plan', '', 'None.' if not out['deviations'] else '\n'.join(f'- {d}' for d in out['deviations']), '']
    for title, key in (('Primary release', 'primary'), ('Secondary release', 'secondary')):
        r = out[key]
        L.append(f"## {title}: ClusterMAX {r['release']}")
        L.append(f"Published {r['published_date']}. Window: [{r['window']['start']}, {r['window']['end']}) ({r['window']['days']} days).")
        L.append(f"Included in correlation: {r['included_count']} (minimum {r['minimum_providers']}).")
        L.append(f"**Reading (R1 rule, primary measure): {r['reading']}**")
        L.append('')
        if r.get('analysis'):
            L.append('### Analysis')
            for m, a in r['analysis'].items():
                b, pm = a['bootstrap_95ci'], a['permutation']
                L.append(f'#### `{m}`')
                L.append(f"- Spearman rho: {a['spearman_rho']}")
                L.append(f"- Bootstrap 95% interval: {b['interval']} ({b['valid_draws']}/{b['draws']} valid draws, {b['skipped_zero_variance_draws']} skipped, seed {b['seed']})")
                L.append(f"- Permutation p (two-sided): {pm['p_value']} (method={pm['method']}, {pm['permutations_used']} permutations)")
                if a['reading']:
                    L.append(f"- Reading: **{a['reading']}**")
                L.append('')
        if r.get('sensitivities'):
            L.append('### Pre-declared sensitivities')
            L.append('```json')
            L.append(json.dumps(r['sensitivities'], indent=2))
            L.append('```')
            L.append('')
        L.append('### Eligible providers')
        for e in r['providers']:
            if e.get('status') == 'eligible':
                L.append(fmt_row(e))
        L += ['', '### Excluded providers']
        for e in r['providers']:
            if e.get('status') != 'eligible':
                L.append(fmt_row(e))
        L.append('')
    L += ['## Known limits (from PLAN-R2.md)', '',
          'Self-reported status pages; provider-wide records; severity vocabularies differ and were mapped by rules fixed in PLAN-R2.md; '
          'the 3.0 rating is dated at the end of the window, so this is a concurrent, not predictive, comparison; reliability is one of ten '
          'criteria. See PLAN-R2.md in full.', '']
    return '\n'.join(L)


def main():
    try:
        out = run()
    except R.PlanHashMismatch as exc:
        print(f'REFUSING TO RUN: {exc}', file=sys.stderr)
        return 3
    except R.StudyError as exc:
        print(f'STUDY ERROR: {exc}', file=sys.stderr)
        return 2
    rd = ROOT / 'results'
    rd.mkdir(parents=True, exist_ok=True)
    (rd / 'R2-result.json').write_text(json.dumps(out, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    (rd / 'R2-result.md').write_text(render(out), encoding='utf-8')
    print('wrote', rd / 'R2-result.json', rd / 'R2-result.md')
    return 0


if __name__ == '__main__':
    sys.exit(main())
