"""Stage r2-standing: the R2 study re-run on a rolling window, labelled STANDING and unfrozen.

Imports retrospective/run_r2.py unchanged and calls its own verify_plan() and evaluate(): rolling 180-day window
ending today, the frozen six-tier ordinals, permutation/bootstrap rules from plan-R2.json, seed = YYYYMMDD. The
frozen plan-R2.json, PLAN-R2.md and results/R2-result.* are only read (the driver hash-asserts them).

Online, the incident files are the `<slug>-standing.json` files the status stage just wrote (a provider without
one is excluded by run_r2 as "no incident data file", exactly as in R2). Offline there are not enough fixture
providers for the minimum of 8, so the stage instead re-evaluates the frozen R2 data files (read-only) with the
frozen window at reduced draw counts, to prove the whole evaluate() path runs; the output says so.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

from stages._common import FAIL, HOLD, OK, SKIP, Stage, import_by_path, iso, read_json, write_json

NAME = 'r2-standing'
OUTD = 'clustermax-challenge/retrospective/results'


def run(ctx):
    s = Stage(ctx, NAME)
    ch = ctx.repo / 'clustermax-challenge'
    retro = ch / 'retrospective'
    r2 = import_by_path('circulate_run_r2', retro / 'run_r2.py')
    R = r2.R
    try:
        plan, md_hash, pj_hash, runner_hash = r2.verify_plan()
    except (R.PlanHashMismatch, R.StudyError) as e:
        return s.done(FAIL, 'frozen R2 plan no longer verifies; standing run refused', error=str(e))
    plan = json.loads(json.dumps(plan))
    pmap = dict(read_json(retro / 'provider_map.json'))
    pmap.update(read_json(retro / plan['provider_map_r2_file']))
    input_hashes = {'PLAN-R2.md': md_hash, 'plan-R2.json': pj_hash, 'run_r2.py': runner_hash}
    hot_names = set(plan.get('excluded_by_design', []))
    incidents_dir = retro / 'incidents'
    label = 'STANDING'
    if ctx.offline:
        # frozen window and data, reduced draws (the frozen result is not reproduced or replaced)
        plan['bootstrap']['draws'] = 300
        plan['seed_robustness']['seeds'] = 3
        plan['permutation'].update(random_draws=2000, stability_random_draws=4000)
        label = 'OFFLINE SMOKE (frozen R2 data and window, reduced draws)'
        smap = pmap
    else:
        plan['window_end_date'] = ctx.today.isoformat()
        plan['bootstrap']['seed'] = int(ctx.today.strftime('%Y%m%d'))
        ratings = read_json(ch / plan['ratings_files']['primary'])
        names = [p['name'] for p in ratings['providers']] + [p['name'] for p in read_json(ch / plan['ratings_files']['secondary'])['providers']]
        smap = {n: pmap.get(n, R.slugify(n)) + '-standing' for n in names}
    out = {'schema': r2.RESULT_SCHEMA, 'study_id': plan['study_id'] + ('-STANDING' if not ctx.offline else '-OFFLINE-SMOKE'),
           'generated_at': iso(), 'plan_hash_verified': True, 'plan_md_sha256': md_hash, 'runner_sha256': runner_hash,
           'input_hashes': input_hashes, 'standing': not ctx.offline, 'label': label,
           'deviations': [f'{label}: rolling window ending {plan["window_end_date"]}, seed {plan["bootstrap"]["seed"]}, bootstrap draws '
                          f'{plan["bootstrap"]["draws"]}; not the frozen R2 analysis and not a replacement for results/R2-result.*']}
    res = {}
    for key, field, rel in (('primary', 'primary_release', plan['ratings_files']['primary']),
                            ('secondary', 'secondary_release', plan['ratings_files']['secondary'])):
        res[key] = r2.evaluate((ch / rel).resolve(), plan, smap, hot_names, incidents_dir, input_hashes)
        res[key]['plan_release_label'] = plan[field]
    out.update(res)
    p = res['primary']
    tag = 'R2-standing-' + ctx.today.isoformat() if not ctx.offline else 'R2-standing-' + ctx.today.isoformat()
    jpath, mpath = ctx.out(f'{OUTD}/{tag}.json'), ctx.out(f'{OUTD}/{tag}.md')
    write_json(jpath, out)
    body = r2.render(out)
    body = f'> **{label}.** Unfrozen rolling-window re-run of the R2 analysis by circulate. The frozen R2 result (results/R2-result.md) is unchanged and remains the pre-registered analysis.\n\n' + body
    mpath.write_text(body, encoding='utf-8', newline='\n')
    s.output(jpath)
    s.output(mpath)
    s.counts.update(window_start=p['window']['start'], window_end=p['window']['end'], included_primary=p['included_count'],
                    included_secondary=res['secondary']['included_count'], reading=p['reading'], seed=plan['bootstrap']['seed'])
    if p['reading'] == 'insufficient':
        return s.done(HOLD, f'only {p["included_count"]} eligible providers in the window (minimum {p["minimum_providers"]}); no correlation computed.')
    a = p['analysis'][plan['primary_measure']]
    rho = a['spearman_rho']
    s.counts['spearman_rho'] = rho
    return s.done(OK, f'{label}: window {p["window"]["start"]}..{p["window"]["end"]}, {p["included_count"]} providers, Spearman rho {rho} on '
                      f'{plan["primary_measure"]}, bootstrap 95% interval {a["bootstrap_95ci"]["interval"]}, permutation p {a["permutation"]["p_value"]}; reading {p["reading"]}.')
