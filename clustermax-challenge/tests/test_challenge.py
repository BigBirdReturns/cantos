import copy, hashlib, importlib.util, json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from challenge import evaluate
from make_demo import build, dump

class ChallengeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p,o=build(); cls.plan=json.loads(p);cls.outcomes=json.loads(o)
    def run_case(self, mutate=None, relock=True):
        p,o=copy.deepcopy(self.plan),copy.deepcopy(self.outcomes)
        if mutate: mutate(p,o)
        pb=dump(p)
        if relock:o['plan_sha256']=hashlib.sha256(pb).hexdigest()
        return evaluate(pb,dump(o))
    def held(self,fn): self.assertEqual(self.run_case(fn)['status'],'HOLD')
    def test_positive_control(self):
        r=self.run_case();self.assertEqual(r['status'],'LIFT_DEMONSTRATED_ON_SUBMITTED_DATA');self.assertEqual(r['evidence_status'],'SYNTHETIC_DEMO')
    def test_null_rating(self):
        r=self.run_case(lambda p,o:[x.update(p_with_rating=x['p_baseline']) for x in p['trials']])
        self.assertEqual(r['status'],'LIFT_NOT_DEMONSTRATED');self.assertEqual(r['mean_lift'],0)
    def test_bad_rating(self):
        r=self.run_case(lambda p,o:[x.update(p_with_rating=1-x['p_with_rating']) for x in p['trials']])
        self.assertEqual(r['status'],'LIFT_NOT_DEMONSTRATED');self.assertLess(r['mean_lift'],0)
    def test_missing_trial(self): self.held(lambda p,o:o['trials'].pop())
    def test_extra_trial(self): self.held(lambda p,o:o['trials'].append({**o['trials'][0],'trial_id':'EXTRA'}))
    def test_duplicate_trial(self): self.held(lambda p,o:o['trials'].append(o['trials'][0]))
    def test_admin_scope(self):
        self.held(lambda p,o:(p['trials'][0].update(customer_role='administrator'),o['trials'][0].update(customer_role='administrator')))
    def test_reviewer_support(self):
        self.held(lambda p,o:(p['trials'][0].update(support='reviewer'),o['trials'][0].update(support='reviewer')))
    def test_changed_actual_service(self): self.held(lambda p,o:o['trials'][0].update(service_id='curated'))
    def test_late_prediction(self): self.held(lambda p,o:p['trials'][0].update(predicted_at='2026-01-04T00:00:00Z'))
    def test_late_plan(self): self.held(lambda p,o:p.update(frozen_at='2026-01-04T00:00:00Z'))
    def test_training_leak(self): self.held(lambda p,o:[m.update(training_providers=['EXAMPLE_01']) for m in (p['baseline'],p['with_rating'])])
    def test_unfrozen_rules(self):
        r=self.run_case(lambda p,o:p.update(rating_rules_sha256='a'*64),relock=False)
        self.assertEqual(r['status'],'HOLD')
    def test_changed_other_inputs(self): self.held(lambda p,o:p['with_rating']['inputs'].append('special_access'))
    def test_missing_latency(self):
        self.held(lambda p,o:o['trials'][0].update(status='complete',p95_ms=None))
    def test_invalid_probability(self): self.held(lambda p,o:p['trials'][0].update(p_baseline=1.1))
    def test_boolean_is_not_number(self): self.held(lambda p,o:p['trials'][0].update(p_baseline=True))
    def test_nan_json(self): self.assertEqual(evaluate(b'{"x":NaN}',b'{}')['status'],'HOLD')
    def test_zero_accepted_is_retained(self):
        r=self.run_case(lambda p,o:o['trials'][0].update(accepted=0,status='timeout',p95_ms=None))
        self.assertNotEqual(r['status'],'HOLD');self.assertIsNone(r['economics'][0]['cost_per_1000_accepted'])
    def test_incomplete_cohort(self): self.held(lambda p,o:(p.update(trials=p['trials'][:12]),o.update(trials=o['trials'][:12])))
    def test_repeatable(self): self.assertEqual(self.run_case(),self.run_case())
    def test_empty_is_not_pass(self): self.assertEqual(evaluate(b'{}',b'{}')['status'],'HOLD')

if __name__=='__main__':unittest.main()
