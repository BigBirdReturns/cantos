import hashlib
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import retrospective as rx  # noqa: E402


# --------------------------------------------------------------------------- #
# fixture builders
# --------------------------------------------------------------------------- #

DEFAULT_ORDINAL = {'Platinum': 5, 'Gold': 4, 'Silver': 3, 'Bronze': 2, 'Underperforming': 1}


def make_root(tmp_path, plan_overrides=None, plan_md_text=None, bad_hash=False):
    root = tmp_path / 'retrospective'
    (root / 'ratings').mkdir(parents=True)
    (root / 'incidents').mkdir()
    plan_md_text = plan_md_text or 'Synthetic frozen plan for retrospective.py tests.\n'
    plan_md_bytes = plan_md_text.encode('utf-8')
    # write_bytes (not write_text) so no platform newline translation can change
    # the bytes out from under the hash we just computed (write_text on Windows
    # translates \n -> \r\n, which would silently break the hash check below).
    (root / 'PLAN.md').write_bytes(plan_md_bytes)
    plan_hash = hashlib.sha256(plan_md_bytes).hexdigest()
    if bad_hash:
        plan_hash = 'f' * 64
    plan = {
        'schema': 'secondrun.retrospective-plan.v1',
        'study_id': 'TEST-R1',
        'plan_md_sha256': plan_hash,
        'frozen_at': '2026-01-01',
        'ordinal': dict(DEFAULT_ORDINAL),
        'primary_release': 'ClusterMAX 2.0',
        'secondary_release': 'ClusterMAX 1.0',
        'window_days': 180,
        'primary_measure': 'major_or_critical_incident_count',
        'secondary_measures': ['all_incident_count', 'incident_hours'],
        'bootstrap': {'draws': 300, 'seed': 20260923},
        'minimum_providers': 8,
        'excluded_by_design': ['Hot Aisle'],
        'incident_data_collected': True,
    }
    if plan_overrides:
        plan.update(plan_overrides)
    (root / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
    return root


def write_ratings(root, token, release, published_date, providers):
    (root / 'ratings' / f'clustermax-{token}.json').write_text(
        json.dumps({'release': release, 'published_date': published_date, 'providers': providers}),
        encoding='utf-8')


def write_incidents(root, slug, provider=None, coverage_start='2020-01-01',
                     coverage_end='2030-01-01', incidents=None, severity_map=None):
    doc = {
        'schema': 'secondrun.status-incidents.v1',
        'provider': provider or slug,
        'status_page_url': f'https://status.example.com/{slug}',
        'retrieved_utc': '2026-01-01T00:00:00Z',
        'raw_files': [],
        'coverage_start': coverage_start,
        'coverage_end': coverage_end,
        'severity_map': severity_map or {'Critical': 'critical', 'Major': 'major', 'Minor': 'minor'},
        'incidents': incidents or [],
    }
    (root / 'incidents' / f'{slug}.json').write_text(json.dumps(doc), encoding='utf-8')


def inc(id_, started, resolved='auto', severity='major', is_maintenance=False):
    if resolved == 'auto':
        resolved = None
    return {'id': id_, 'title': id_, 'impact_label': severity, 'severity': severity,
            'started_utc': started, 'resolved_utc': resolved, 'is_maintenance': is_maintenance,
            'url': f'https://status.example.com/incidents/{id_}'}


def eight_providers(tiers=None):
    """8 providers with distinct tiers repeating the ordinal ladder, each with an
    eligible incidents file covering the full window and no incidents by default."""
    tiers = tiers or ['Platinum', 'Gold', 'Silver', 'Bronze', 'Underperforming',
                       'Platinum', 'Gold', 'Silver']
    return [{'name': f'Provider{i+1}', 'tier': t, 'confidence': 'high'} for i, t in enumerate(tiers)]


def seed_eight(root, per_provider_incidents=None):
    providers = eight_providers()
    write_ratings(root, '2.0', 'ClusterMAX 2.0', '2026-01-01', providers)
    for i, p in enumerate(providers):
        slug = rx.slugify(p['name'])
        incidents = (per_provider_incidents or {}).get(p['name'], [])
        write_incidents(root, slug, provider=p['name'], incidents=incidents)
    return providers


# --------------------------------------------------------------------------- #
# spearman / rng correctness (independent of the eligibility pipeline)
# --------------------------------------------------------------------------- #

class SpearmanTests(unittest.TestCase):
    def test_perfect_negative_correlation(self):
        self.assertAlmostEqual(rx.spearman([5, 4, 3, 2, 1], [1, 2, 3, 4, 5]), -1.0, places=9)

    def test_perfect_positive_correlation(self):
        self.assertAlmostEqual(rx.spearman([1, 2, 3, 4, 5], [10, 20, 30, 40, 50]), 1.0, places=9)

    def test_hand_computed_with_ties(self):
        # xs = [5,4,3,2,1] -> ranks [5,4,3,2,1] (no ties)
        # ys = [1,1,3,4,5] -> ranks [1.5,1.5,3,4,5] (tie averaged over the two 1's)
        # hand-derived (see task notes): rho = -9.5 / sqrt(95)
        rho = rx.spearman([5, 4, 3, 2, 1], [1, 1, 3, 4, 5])
        self.assertAlmostEqual(rho, -9.5 / math.sqrt(95), places=9)

    def test_all_tied_is_undefined(self):
        self.assertIsNone(rx.spearman([3, 3, 3], [1, 2, 3]))
        self.assertIsNone(rx.spearman([1, 2, 3], [7, 7, 7]))

    def test_too_few_points(self):
        self.assertIsNone(rx.spearman([1], [1]))
        self.assertIsNone(rx.spearman([], []))


class BootstrapTests(unittest.TestCase):
    def test_skips_zero_variance_draws_and_accounts_for_them(self):
        result = rx.bootstrap_ci([1, 2], [1, 2], seed=20260923, draws=1000)
        self.assertEqual(result['draws'], 1000)
        self.assertEqual(result['valid_draws'] + result['skipped_zero_variance_draws'], 1000)
        self.assertGreater(result['skipped_zero_variance_draws'], 0)  # both-same-index draws
        self.assertGreater(result['valid_draws'], 0)
        self.assertIsNotNone(result['interval'])

    def test_reproducible(self):
        a = rx.bootstrap_ci([5, 4, 3, 2, 1], [1, 1, 3, 4, 5], seed=20260923, draws=500)
        b = rx.bootstrap_ci([5, 4, 3, 2, 1], [1, 1, 3, 4, 5], seed=20260923, draws=500)
        self.assertEqual(a, b)


class PermutationTests(unittest.TestCase):
    def test_exact_branch_for_small_n(self):
        xs = [1, 2, 3, 4, 5, 6, 7]
        ys = [7, 6, 5, 4, 3, 2, 1]
        self.assertLessEqual(math.factorial(len(xs)), rx.PERMUTATION_CAP)
        result = rx.permutation_p(xs, ys, seed=20260923)
        self.assertEqual(result['method'], 'exact')
        self.assertEqual(result['permutations_used'], math.factorial(7))
        self.assertIsNotNone(result['p_value'])
        self.assertGreater(result['p_value'], 0)

    def test_random_branch_for_larger_n(self):
        xs = list(range(8))
        ys = list(range(8))[::-1]
        self.assertGreater(math.factorial(len(xs)), rx.PERMUTATION_CAP)
        result = rx.permutation_p(xs, ys, seed=20260923)
        self.assertTrue(result['method'].startswith('random_'))
        self.assertEqual(result['permutations_used'], rx.PERMUTATION_CAP)

    def test_undefined_observed_rho(self):
        result = rx.permutation_p([1, 1, 1], [1, 2, 3], seed=20260923)
        self.assertIsNone(result['p_value'])
        self.assertEqual(result['method'], 'undefined')


# --------------------------------------------------------------------------- #
# plan-hash refusal
# --------------------------------------------------------------------------- #

class PlanHashTests(unittest.TestCase):
    def test_refuses_on_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td), bad_hash=True)
            with self.assertRaises(rx.PlanHashMismatch):
                rx.run(root)

    def test_main_returns_3_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td), bad_hash=True)
            out_dir = root / 'results'
            code = rx.main(['--root', str(root), '--out-dir', str(out_dir)])
            self.assertEqual(code, 3)
            self.assertFalse(out_dir.exists())

    def test_accepts_on_match(self):
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            seed_eight(root)
            write_ratings(root, '1.0', 'ClusterMAX 1.0', '2025-03-01', [])
            output = rx.run(root)
            self.assertTrue(output['plan_hash_verified'])


# --------------------------------------------------------------------------- #
# eligibility / window / maintenance / hot aisle / ties
# --------------------------------------------------------------------------- #

class EligibilityTests(unittest.TestCase):
    def test_window_edges_inclusive_start_exclusive_end(self):
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            incidents = {
                'Provider1': [
                    inc('IN-AT-START', '2026-01-01T00:00:00Z', severity='major'),
                    inc('OUT-AT-END', '2026-06-30T00:00:00Z', severity='major'),  # 2026-01-01 + 180d
                ],
            }
            seed_eight(root, incidents)
            write_ratings(root, '1.0', 'ClusterMAX 1.0', '2025-03-01', [])
            output = rx.run(root)
            p1 = next(p for p in output['primary']['providers'] if p['name'] == 'Provider1')
            self.assertEqual(p1['status'], 'eligible')
            self.assertEqual(p1['major_or_critical_incident_count'], 1)
            self.assertEqual(p1['all_incident_count'], 1)

    def test_coverage_must_span_entire_window(self):
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            providers = eight_providers()
            write_ratings(root, '2.0', 'ClusterMAX 2.0', '2026-01-01', providers)
            for i, p in enumerate(providers):
                slug = rx.slugify(p['name'])
                if p['name'] == 'Provider1':
                    # coverage starts one day after the window start -> ineligible
                    write_incidents(root, slug, provider=p['name'], coverage_start='2026-01-02')
                else:
                    write_incidents(root, slug, provider=p['name'])
            write_ratings(root, '1.0', 'ClusterMAX 1.0', '2025-03-01', [])
            output = rx.run(root)
            p1 = next(p for p in output['primary']['providers'] if p['name'] == 'Provider1')
            self.assertEqual(p1['status'], 'excluded')
            self.assertIn('coverage', p1['reason'])
            self.assertEqual(output['primary']['included_count'], 7)

    def test_maintenance_excluded_from_both_measures(self):
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            incidents = {
                'Provider1': [
                    inc('MAINT', '2026-02-01T00:00:00Z', severity='critical', is_maintenance=True),
                ],
            }
            seed_eight(root, incidents)
            write_ratings(root, '1.0', 'ClusterMAX 1.0', '2025-03-01', [])
            output = rx.run(root)
            p1 = next(p for p in output['primary']['providers'] if p['name'] == 'Provider1')
            self.assertEqual(p1['major_or_critical_incident_count'], 0)
            self.assertEqual(p1['all_incident_count'], 0)

    def test_unrated_tier_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            providers = eight_providers()
            providers.append({'name': 'Ghost', 'tier': 'Unavailable', 'confidence': 'low'})
            write_ratings(root, '2.0', 'ClusterMAX 2.0', '2026-01-01', providers)
            for p in providers[:-1]:
                write_incidents(root, rx.slugify(p['name']), provider=p['name'])
            write_ratings(root, '1.0', 'ClusterMAX 1.0', '2025-03-01', [])
            output = rx.run(root)
            ghost = next(p for p in output['primary']['providers'] if p['name'] == 'Ghost')
            self.assertEqual(ghost['status'], 'excluded')
            self.assertIn('unrated', ghost['reason'])

    def test_hot_aisle_reported_separately_not_in_correlation(self):
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            providers = eight_providers()
            providers.append({'name': 'Hot Aisle', 'tier': 'Gold', 'confidence': 'high'})
            write_ratings(root, '2.0', 'ClusterMAX 2.0', '2026-01-01', providers)
            for p in providers:
                write_incidents(root, rx.slugify(p['name']), provider=p['name'],
                                incidents=[inc('X', '2026-02-01T00:00:00Z', severity='critical')])
            write_ratings(root, '1.0', 'ClusterMAX 1.0', '2025-03-01', [])
            output = rx.run(root)
            self.assertEqual(output['primary']['included_count'], 8)  # Hot Aisle not counted
            self.assertIsNotNone(output['primary']['hot_aisle'])
            self.assertEqual(output['primary']['hot_aisle']['name'], 'Hot Aisle')
            self.assertFalse(output['primary']['hot_aisle']['included_in_correlation'])
            names_in_provider_list = [p['name'] for p in output['primary']['providers']]
            self.assertIn('Hot Aisle', names_in_provider_list)

    def test_unresolved_incident_hours_capped_and_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            incidents = {'Provider1': [inc('OPEN', '2026-06-29T00:00:00Z', resolved=None, severity='major')]}
            seed_eight(root, incidents)
            write_ratings(root, '1.0', 'ClusterMAX 1.0', '2025-03-01', [])
            output = rx.run(root)
            p1 = next(p for p in output['primary']['providers'] if p['name'] == 'Provider1')
            self.assertTrue(p1['incident_hours_capped'])
            self.assertAlmostEqual(p1['incident_hours'], 24.0, places=3)  # capped at window end (2026-06-30)


# --------------------------------------------------------------------------- #
# insufficient-providers path
# --------------------------------------------------------------------------- #

class InsufficientTests(unittest.TestCase):
    def test_fewer_than_minimum_is_insufficient(self):
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            providers = eight_providers()[:5]
            write_ratings(root, '2.0', 'ClusterMAX 2.0', '2026-01-01', providers)
            for p in providers:
                write_incidents(root, rx.slugify(p['name']), provider=p['name'])
            write_ratings(root, '1.0', 'ClusterMAX 1.0', '2025-03-01', [])
            output = rx.run(root)
            self.assertEqual(output['primary']['reading'], 'insufficient')
            self.assertIsNone(output['primary']['analysis'])


# --------------------------------------------------------------------------- #
# provider_map.json
# --------------------------------------------------------------------------- #

class ProviderMapTests(unittest.TestCase):
    def test_provider_map_overrides_slugify(self):
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            providers = eight_providers()
            providers[0]['name'] = 'Weirdly Named Co.'
            write_ratings(root, '2.0', 'ClusterMAX 2.0', '2026-01-01', providers)
            (root / 'provider_map.json').write_text(
                json.dumps({'Weirdly Named Co.': 'wnc'}), encoding='utf-8')
            write_incidents(root, 'wnc', provider='Weirdly Named Co.')
            for p in providers[1:]:
                write_incidents(root, rx.slugify(p['name']), provider=p['name'])
            write_ratings(root, '1.0', 'ClusterMAX 1.0', '2025-03-01', [])
            output = rx.run(root)
            entry = next(p for p in output['primary']['providers'] if p['name'] == 'Weirdly Named Co.')
            self.assertEqual(entry['status'], 'eligible')
            self.assertEqual(entry['slug'], 'wnc')


# --------------------------------------------------------------------------- #
# end-to-end: full pipeline produces a reading and renders markdown
# --------------------------------------------------------------------------- #

class EndToEndTests(unittest.TestCase):
    def test_full_pipeline_and_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            # more incidents for lower-tier providers -> expect a "consistent" reading
            per = {}
            tiers_order = ['Platinum', 'Gold', 'Silver', 'Bronze', 'Underperforming',
                           'Platinum', 'Gold', 'Silver']
            counts = {'Platinum': 0, 'Gold': 1, 'Silver': 2, 'Bronze': 3, 'Underperforming': 4}
            providers = eight_providers(tiers_order)
            for i, p in enumerate(providers):
                n = counts[p['tier']]
                per[p['name']] = [inc(f'{p["name"]}-{k}', f'2026-0{(k%9)+1}-01T00:00:00Z', severity='major')
                                   for k in range(n)]
            write_ratings(root, '2.0', 'ClusterMAX 2.0', '2026-01-01', providers)
            for p in providers:
                write_incidents(root, rx.slugify(p['name']), provider=p['name'], incidents=per[p['name']])
            write_ratings(root, '1.0', 'ClusterMAX 1.0', '2025-03-01', [])
            output = rx.run(root)
            self.assertIn(output['primary']['reading'], ('consistent', 'inconsistent', 'inconclusive'))
            md = rx.render_markdown(output)
            self.assertIn('R1 result', md)
            self.assertIn('Provider1', md)


if __name__ == '__main__':
    unittest.main()
