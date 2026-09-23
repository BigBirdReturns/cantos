#!/usr/bin/env python3
"""R1: do ClusterMAX medals track providers' own public incident records?

Implements retrospective/PLAN.md exactly (frozen before any incident data was
collected; see plan.json's plan_md_sha256). Stdlib only. Reads:

  retrospective/PLAN.md, retrospective/plan.json   (frozen; never written here)
  retrospective/ratings/clustermax-{1.0,2.0}.json  (owned by another agent)
  retrospective/incidents/<slug>.json              (secondrun.status-incidents.v1)
  retrospective/provider_map.json                  (optional, rating name -> slug)

Writes:
  retrospective/results/R1-result.json
  retrospective/results/R1-result.md

Refuses to run (nonzero exit, no output written) if PLAN.md's SHA-256 no longer
matches plan.json's plan_md_sha256 -- the plan is frozen pre-registration.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RESULT_SCHEMA = 'secondrun.retrospective-result.v1'
INCIDENTS_SCHEMA = 'secondrun.status-incidents.v1'
PLAN_SCHEMA = 'secondrun.retrospective-plan.v1'
PERMUTATION_CAP = 20000


class PlanHashMismatch(RuntimeError):
    """PLAN.md no longer matches the frozen hash in plan.json."""


class StudyError(RuntimeError):
    """A structural problem with the inputs (missing plan fields, bad ratings, ...)."""


# --------------------------------------------------------------------------- #
# small stdlib utilities
# --------------------------------------------------------------------------- #

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.strip().lower()).strip('-')


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def parse_ts(s: str) -> datetime:
    t = datetime.fromisoformat(s.replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise StudyError(f'timestamp without timezone: {s!r}')
    return t.astimezone(timezone.utc)


def day_start_utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def quantile(xs, q):
    ys = sorted(xs)
    pos = (len(ys) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ys) - 1)
    return ys[lo] + (ys[hi] - ys[lo]) * (pos - lo)


# --------------------------------------------------------------------------- #
# deterministic RNG -- same xorshift/mulberry-style generator as
# scripts/challenge.py's bootstrap(), so a reviewer who has verified that one
# can verify this one the same way. Used both for provider-level bootstrap
# resampling and for random permutation draws (independent instances, each
# freshly seeded, so the two procedures never share a stream).
# --------------------------------------------------------------------------- #

class DeterministicRng:
    def __init__(self, seed: int):
        self.state = seed & 0xffffffff

    def _next_u32(self) -> int:
        self.state = (self.state + 0x6D2B79F5) & 0xffffffff
        t = self.state
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xffffffff
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xffffffff)) & 0xffffffff
        return (t ^ (t >> 14)) & 0xffffffff

    def randbelow(self, n: int) -> int:
        if n <= 0:
            raise ValueError('n must be positive')
        limit = 2 ** 32 - (2 ** 32 % n)
        while True:
            x = self._next_u32()
            if x < limit:
                return x % n

    def shuffle(self, seq):
        a = list(seq)
        for i in range(len(a) - 1, 0, -1):
            j = self.randbelow(i + 1)
            a[i], a[j] = a[j], a[i]
        return a


# --------------------------------------------------------------------------- #
# statistics: Spearman (average ranks), bootstrap CI, permutation p-value
# --------------------------------------------------------------------------- #

def rank_average(values):
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def spearman(xs, ys):
    """Spearman rho with average ranks for ties. None when either side has zero
    rank variance (all tied) -- rho is undefined there, not zero."""
    n = len(xs)
    if n < 2:
        return None
    rx, ry = rank_average(xs), rank_average(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    denx = math.sqrt(sum((r - mx) ** 2 for r in rx))
    deny = math.sqrt(sum((r - my) ** 2 for r in ry))
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


def bootstrap_ci(xs, ys, seed: int, draws: int):
    n = len(xs)
    rng = DeterministicRng(seed)
    vals = []
    skipped = 0
    for _ in range(draws):
        idx = [rng.randbelow(n) for _ in range(n)]
        rho = spearman([xs[i] for i in idx], [ys[i] for i in idx])
        if rho is None:
            skipped += 1
            continue
        vals.append(rho)
    interval = [quantile(vals, 0.025), quantile(vals, 0.975)] if vals else None
    return {'interval': interval, 'draws': draws, 'valid_draws': len(vals),
            'skipped_zero_variance_draws': skipped, 'seed': seed}


def permutation_p(xs, ys, seed: int, cap: int = PERMUTATION_CAP):
    n = len(xs)
    observed = spearman(xs, ys)
    if observed is None:
        return {'p_value': None, 'method': 'undefined', 'observed_rho': None,
                'permutations_used': 0, 'skipped_zero_variance': 0, 'seed': seed}
    exact = math.factorial(n) <= cap
    used = skipped = at_least_as_extreme = 0
    if exact:
        method = 'exact'
        perms = itertools.permutations(ys)
    else:
        method = f'random_{cap}'
        rng = DeterministicRng(seed)
        perms = (rng.shuffle(ys) for _ in range(cap))
    for perm in perms:
        used += 1
        r = spearman(xs, list(perm))
        if r is None:
            skipped += 1
            continue
        if abs(r) >= abs(observed) - 1e-12:
            at_least_as_extreme += 1
    denom = used - skipped
    p_value = (at_least_as_extreme / denom) if denom else None
    return {'p_value': p_value, 'method': method, 'observed_rho': observed,
            'permutations_used': used, 'skipped_zero_variance': skipped, 'seed': seed}


# --------------------------------------------------------------------------- #
# plan loading and hash verification
# --------------------------------------------------------------------------- #

def verify_plan_hash(root: Path):
    plan_md_path = root / 'PLAN.md'
    plan_json_path = root / 'plan.json'
    if not plan_md_path.exists():
        raise StudyError(f'missing {plan_md_path}')
    if not plan_json_path.exists():
        raise StudyError(f'missing {plan_json_path}')
    plan = load_json(plan_json_path)
    if plan.get('schema') != PLAN_SCHEMA:
        raise StudyError(f'{plan_json_path}: unexpected schema {plan.get("schema")!r}')
    actual = sha256_file(plan_md_path)
    expected = plan.get('plan_md_sha256')
    if actual != expected:
        raise PlanHashMismatch(
            f'PLAN.md sha256 ({actual}) does not match plan.json plan_md_sha256 '
            f'({expected}); the plan is frozen pre-registration, refusing to run')
    return plan, actual, sha256_file(plan_json_path)


def release_version_token(release_name: str) -> str:
    # "ClusterMAX 2.0" -> "2.0"
    return release_name.rsplit(' ', 1)[-1]


# --------------------------------------------------------------------------- #
# incident measurement
# --------------------------------------------------------------------------- #

def load_incidents_doc(path: Path):
    doc = load_json(path)
    if doc.get('schema') != INCIDENTS_SCHEMA:
        raise StudyError(f'{path}: unsupported incidents schema {doc.get("schema")!r}')
    return doc


def measure_window(doc, window_start: date, window_end: date):
    """Non-maintenance incidents started in [window_start, window_end).
    Returns (major_or_critical_count, all_incident_count, incident_hours, capped)."""
    ws, we = day_start_utc(window_start), day_start_utc(window_end)
    primary = secondary = 0
    hours = 0.0
    capped = False
    for inc in doc.get('incidents', []):
        if inc.get('is_maintenance'):
            continue
        started = parse_ts(inc['started_utc'])
        if not (ws <= started < we):
            continue
        secondary += 1
        if inc.get('severity') in ('critical', 'major'):
            primary += 1
        resolved_raw = inc.get('resolved_utc')
        if resolved_raw:
            ended = parse_ts(resolved_raw)
        else:
            ended = we
            capped = True
        hours += max(0.0, (ended - started).total_seconds() / 3600.0)
    return primary, secondary, hours, capped


# --------------------------------------------------------------------------- #
# per-release evaluation
# --------------------------------------------------------------------------- #

def evaluate_release(ratings_path: Path, incidents_dir: Path, provider_map: dict,
                      ordinal: dict, window_days: int, hot_aisle_names: set,
                      min_providers: int, seed: int, bootstrap_draws: int,
                      input_hashes: dict):
    ratings = load_json(ratings_path)
    input_hashes[str(ratings_path)] = sha256_file(ratings_path)
    published_date = ratings['published_date']
    window_start = parse_date(published_date)
    window_end = window_start + timedelta(days=window_days)

    providers_out = []
    included = []
    hot_aisle_entry = None

    for prov in ratings.get('providers', []):
        name = prov.get('name')
        tier = prov.get('tier')
        entry = {'name': name, 'tier': tier, 'confidence': prov.get('confidence')}

        if tier not in ordinal:
            entry.update(status='excluded',
                         reason=f'unrated/unavailable tier {tier!r} in this release')
            providers_out.append(entry)
            continue

        slug = provider_map.get(name, slugify(name))
        entry['slug'] = slug
        incidents_path = incidents_dir / f'{slug}.json'
        if not incidents_path.exists():
            entry.update(status='excluded',
                         reason=f'no incident data file found (expected {incidents_path.name})')
            providers_out.append(entry)
            continue

        try:
            doc = load_incidents_doc(incidents_path)
        except StudyError as exc:
            entry.update(status='excluded', reason=str(exc))
            providers_out.append(entry)
            continue
        input_hashes[str(incidents_path)] = sha256_file(incidents_path)

        cov_start_raw, cov_end_raw = doc.get('coverage_start'), doc.get('coverage_end')
        if not cov_start_raw or not cov_end_raw:
            entry.update(status='excluded',
                         reason='coverage_start/coverage_end not recorded; manual verification pending')
            providers_out.append(entry)
            continue
        cov_start, cov_end = parse_date(cov_start_raw), parse_date(cov_end_raw)
        if not (cov_start <= window_start and cov_end >= window_end):
            entry.update(status='excluded',
                         reason=(f'coverage [{cov_start},{cov_end}] does not fully cover '
                                 f'window [{window_start},{window_end})'))
            providers_out.append(entry)
            continue

        primary_n, secondary_n, hours, capped = measure_window(doc, window_start, window_end)
        entry.update(status='eligible', ordinal=ordinal[tier],
                     coverage=[cov_start_raw, cov_end_raw],
                     major_or_critical_incident_count=primary_n,
                     all_incident_count=secondary_n,
                     incident_hours=round(hours, 4),
                     incident_hours_capped=capped)

        is_hot_aisle = (name in hot_aisle_names) or slug == 'hot-aisle'
        if is_hot_aisle:
            entry.update(included_in_correlation=False,
                         exclusion_reason='excluded by design (author working relationship); reported separately')
            hot_aisle_entry = dict(entry)
        else:
            entry['included_in_correlation'] = True
            included.append(entry)
        providers_out.append(entry)

    result = {
        'release': ratings.get('release'),
        'published_date': published_date,
        'window': {'start': str(window_start), 'end': str(window_end), 'days': window_days},
        'providers': providers_out,
        'included_count': len(included),
        'minimum_providers': min_providers,
        'sufficient': len(included) >= min_providers,
        'hot_aisle': hot_aisle_entry,
    }

    if not result['sufficient']:
        result['reading'] = 'insufficient'
        result['analysis'] = None
        return result

    ordinals = [e['ordinal'] for e in included]
    measures = {
        'major_or_critical_incident_count': [e['major_or_critical_incident_count'] for e in included],
        'all_incident_count': [e['all_incident_count'] for e in included],
        'incident_hours': [e['incident_hours'] for e in included],
    }
    analysis = {}
    for measure_name, values in measures.items():
        rho = spearman(ordinals, values)
        boot = bootstrap_ci(ordinals, values, seed, bootstrap_draws)
        perm = permutation_p(ordinals, values, seed, PERMUTATION_CAP)
        reading = None
        if measure_name == 'major_or_critical_incident_count':
            if boot['interval'] is None:
                reading = 'inconclusive'
            elif boot['interval'][1] < 0:
                reading = 'consistent'
            elif boot['interval'][0] > 0:
                reading = 'inconsistent'
            else:
                reading = 'inconclusive'
        analysis[measure_name] = {'spearman_rho': rho, 'bootstrap_95ci': boot,
                                   'permutation': perm, 'reading': reading}
    result['analysis'] = analysis
    result['reading'] = analysis['major_or_critical_incident_count']['reading']
    return result


# --------------------------------------------------------------------------- #
# top-level run
# --------------------------------------------------------------------------- #

def run(root: Path):
    """root is a retrospective/ directory (PLAN.md, plan.json, ratings/, incidents/[, provider_map.json])."""
    plan, plan_md_hash, plan_json_hash = verify_plan_hash(root)

    provider_map_path = root / 'provider_map.json'
    provider_map = load_json(provider_map_path) if provider_map_path.exists() else {}

    input_hashes = {str(root / 'PLAN.md'): plan_md_hash, str(root / 'plan.json'): plan_json_hash}
    if provider_map_path.exists():
        input_hashes[str(provider_map_path)] = sha256_file(provider_map_path)

    ordinal = plan['ordinal']
    window_days = plan['window_days']
    min_providers = plan['minimum_providers']
    seed = plan['bootstrap']['seed']
    draws = plan['bootstrap']['draws']
    hot_aisle_names = set(plan.get('excluded_by_design', []))
    incidents_dir = root / 'incidents'
    ratings_dir = root / 'ratings'

    results = {}
    for key, field in (('primary', 'primary_release'), ('secondary', 'secondary_release')):
        release_name = plan[field]
        token = release_version_token(release_name)
        ratings_path = ratings_dir / f'clustermax-{token}.json'
        if not ratings_path.exists():
            results[key] = {'release': release_name, 'error': f'ratings file not found: {ratings_path}'}
            continue
        results[key] = evaluate_release(ratings_path, incidents_dir, provider_map, ordinal,
                                         window_days, hot_aisle_names, min_providers, seed,
                                         draws, input_hashes)

    return {
        'schema': RESULT_SCHEMA,
        'study_id': plan['study_id'],
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'plan_hash_verified': True,
        'plan_md_sha256': plan_md_hash,
        # Paths relative to the study root so results never carry build-machine paths.
        'input_hashes': {Path(k).resolve().relative_to(Path(root).resolve()).as_posix(): v
                         for k, v in input_hashes.items()},
        'deviations': [],
        'primary': results['primary'],
        'secondary': results['secondary'],
    }


# --------------------------------------------------------------------------- #
# markdown rendering
# --------------------------------------------------------------------------- #

def _fmt_provider_row(e: dict) -> str:
    if e.get('status') == 'eligible':
        extra = (f"ordinal={e['ordinal']} major/critical={e['major_or_critical_incident_count']} "
                 f"all={e['all_incident_count']} hours={e['incident_hours']}"
                 f"{' (capped, unresolved at window end)' if e.get('incident_hours_capped') else ''}")
        if not e.get('included_in_correlation', True):
            extra += f" -- {e.get('exclusion_reason', 'reported separately')}"
        return f"- **{e['name']}** ({e.get('tier')}): eligible -- {extra}"
    return f"- **{e['name']}** ({e.get('tier')}): excluded -- {e.get('reason')}"


def _fmt_analysis(analysis: dict) -> list:
    lines = []
    for measure_name, a in analysis.items():
        lines.append(f"#### `{measure_name}`")
        lines.append(f"- Spearman rho (average ranks): {a['spearman_rho']}")
        boot = a['bootstrap_95ci']
        lines.append(f"- Bootstrap 95% interval: {boot['interval']} "
                     f"({boot['valid_draws']}/{boot['draws']} valid draws, "
                     f"{boot['skipped_zero_variance_draws']} skipped for zero rank variance, seed {boot['seed']})")
        perm = a['permutation']
        lines.append(f"- Permutation p-value (two-sided): {perm['p_value']} "
                     f"(method={perm['method']}, {perm['permutations_used']} permutations, "
                     f"{perm['skipped_zero_variance']} skipped for zero rank variance)")
        if a['reading'] is not None:
            lines.append(f"- Reading: **{a['reading']}**")
        lines.append('')
    return lines


def _fmt_release_section(title: str, r: dict) -> list:
    lines = [f"## {title}: {r.get('release')}"]
    if 'error' in r:
        lines.append(f"**Not evaluated:** {r['error']}")
        lines.append('')
        return lines
    lines.append(f"Published {r['published_date']}. Window: [{r['window']['start']}, "
                 f"{r['window']['end']}) ({r['window']['days']} days).")
    lines.append(f"Included in correlation: {r['included_count']} "
                 f"(minimum required: {r['minimum_providers']}).")
    lines.append(f"**Reading: {r['reading']}**")
    lines.append('')
    if r.get('hot_aisle'):
        lines.append('### Hot Aisle (excluded by design; reported separately)')
        lines.append(_fmt_provider_row(r['hot_aisle']))
        lines.append('')
    if r.get('analysis'):
        lines.append('### Analysis')
        lines.extend(_fmt_analysis(r['analysis']))
    lines.append('### Providers')
    for e in r['providers']:
        lines.append(_fmt_provider_row(e))
    lines.append('')
    return lines


def render_markdown(output: dict) -> str:
    lines = [
        '# R1 result: do ClusterMAX medals track providers’ own public incident records?',
        '',
        f"Study: `{output['study_id']}`. Generated {output['generated_at']}.",
        '',
        f"Plan hash verified: **{output['plan_hash_verified']}** "
        f"(PLAN.md sha256 `{output['plan_md_sha256']}` matches `retrospective/plan.json`).",
        '',
        '## Input hashes',
        '',
    ]
    for path, h in sorted(output['input_hashes'].items()):
        lines.append(f"- `{path}`: `{h}`")
    lines.append('')
    lines.append('## Deviations from the frozen plan')
    lines.append('')
    if output['deviations']:
        for d in output['deviations']:
            lines.append(f"- {d}")
    else:
        lines.append('None.')
    lines.append('')
    lines.extend(_fmt_release_section('Primary release', output['primary']))
    lines.extend(_fmt_release_section('Secondary release', output['secondary']))
    lines.append('## Known limits (from PLAN.md)')
    lines.append('')
    lines.append('Status pages are self-reported; this is retrospective and observational; '
                 'reliability is one of ten ClusterMAX criteria. See `retrospective/PLAN.md` '
                 'in full for all stated limits.')
    lines.append('')
    return '\n'.join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', type=Path,
                     default=Path(__file__).resolve().parents[1] / 'retrospective',
                     help='retrospective/ directory (default: repo-relative)')
    ap.add_argument('--out-dir', type=Path, default=None,
                     help='where to write R1-result.{json,md} (default: <root>/results)')
    args = ap.parse_args(argv)

    try:
        output = run(args.root)
    except PlanHashMismatch as exc:
        print(f'REFUSING TO RUN: {exc}', file=sys.stderr)
        return 3
    except StudyError as exc:
        print(f'STUDY ERROR: {exc}', file=sys.stderr)
        return 2

    out_dir = args.out_dir or (args.root / 'results')
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'R1-result.json').write_text(
        json.dumps(output, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    (out_dir / 'R1-result.md').write_text(render_markdown(output), encoding='utf-8')
    print(f"Wrote {out_dir / 'R1-result.json'} and {out_dir / 'R1-result.md'}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
