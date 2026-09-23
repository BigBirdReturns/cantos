"""Regression check for the numbers quoted in retrospective/READOUT.md's
'Post-hoc sensitivity' addendum. Reuses scripts/retrospective.py's own
functions (spearman, bootstrap_ci, permutation_p) against the same frozen
inputs -- it does not modify that script or any frozen retrospective/
artifact, and it does not re-run scripts/retrospective.py's own CLI/output.
"""
import importlib.util
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location('retrospective_mod', ROOT / 'scripts' / 'retrospective.py')
retro = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(ROOT / 'scripts'))
spec.loader.exec_module(retro)

RETRO_DIR = ROOT / 'retrospective'


def eligible_primary():
    plan, _, _ = retro.verify_plan_hash(RETRO_DIR)
    provider_map = retro.load_json(RETRO_DIR / 'provider_map.json') if (RETRO_DIR / 'provider_map.json').exists() else {}
    result = retro.evaluate_release(
        RETRO_DIR / 'ratings' / 'clustermax-2.0.json', RETRO_DIR / 'incidents', provider_map,
        plan['ordinal'], plan['window_days'], set(plan.get('excluded_by_design', [])),
        plan['minimum_providers'], plan['bootstrap']['seed'], plan['bootstrap']['draws'], {})
    included = [e for e in result['providers'] if e.get('included_in_correlation')]
    xs = [e['ordinal'] for e in included]
    ys = [e['major_or_critical_incident_count'] for e in included]
    names = [e['name'] for e in included]
    return names, xs, ys, plan['bootstrap']['seed'], plan['bootstrap']['draws']


class R1SensitivityRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.names, cls.xs, cls.ys, cls.seed, cls.draws = eligible_primary()

    def test_reproduces_frozen_result(self):
        # Sanity: this must match retrospective/results/R1-result.md exactly
        # before any sensitivity claim built on top of it can be trusted.
        rho = retro.spearman(self.xs, self.ys)
        self.assertAlmostEqual(rho, 0.6377928041432807, places=9)
        boot = retro.bootstrap_ci(self.xs, self.ys, self.seed, self.draws)
        self.assertAlmostEqual(boot['interval'][0], 0.0, places=9)
        self.assertAlmostEqual(boot['interval'][1], 0.9365858115816939, places=6)
        perm = retro.permutation_p(self.xs, self.ys, self.seed, cap=20000)
        self.assertAlmostEqual(perm['p_value'], 0.07525, places=5)

    def test_exact_permutation_p_over_full_9_factorial(self):
        n = len(self.xs)
        self.assertEqual(n, 9)
        exact = retro.permutation_p(self.xs, self.ys, self.seed, cap=math.factorial(n) + 1)
        self.assertEqual(exact['method'], 'exact')
        self.assertEqual(exact['permutations_used'], 362880)
        self.assertAlmostEqual(exact['p_value'], 0.0716931216931217, places=9)

    def test_excluding_cirrascale_maintenance_notice(self):
        idx = self.names.index('Cirrascale')
        self.assertEqual(self.ys[idx], 1)
        ys_adj = list(self.ys)
        ys_adj[idx] -= 1
        rho_adj = retro.spearman(self.xs, ys_adj)
        self.assertAlmostEqual(rho_adj, 0.5092534540479525, places=9)
        perm_adj = retro.permutation_p(self.xs, ys_adj, self.seed, cap=math.factorial(len(self.xs)) + 1)
        self.assertAlmostEqual(perm_adj['p_value'], 0.18015873015873016, places=9)

    def test_leave_one_out_rho_range(self):
        rhos = {}
        for i, name in enumerate(self.names):
            xs2 = self.xs[:i] + self.xs[i + 1:]
            ys2 = self.ys[:i] + self.ys[i + 1:]
            rhos[name] = retro.spearman(xs2, ys2)
        self.assertAlmostEqual(min(rhos.values()), 0.5076, places=3)
        self.assertEqual(min(rhos, key=rhos.get), 'Nebius')
        self.assertAlmostEqual(max(rhos.values()), 0.7965, places=3)
        self.assertEqual(max(rhos, key=rhos.get), 'Cirrascale')

    def test_seed_sensitivity_share_reading_inconsistent(self):
        n_inconsistent = 0
        for seed in range(1, 201):
            boot = retro.bootstrap_ci(self.xs, self.ys, seed, self.draws)
            lo, hi = boot['interval']
            if lo > 0:
                n_inconsistent += 1
        # Regression bound only (documented as 59/200=29.5% in READOUT.md) --
        # loosely bounded since it depends only on the frozen deterministic RNG.
        self.assertEqual(n_inconsistent, 59)


if __name__ == '__main__':
    unittest.main()
