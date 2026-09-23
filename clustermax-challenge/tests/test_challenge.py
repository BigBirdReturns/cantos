import copy, hashlib, importlib.util, json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from challenge import evaluate, canonical_sha256, PLACEHOLDER_TOKENS, DISCLOSURE_FIELDS
from make_demo import build, dump

class ChallengeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p,b,o=build(); cls.plan=json.loads(p);cls.binding=json.loads(b);cls.outcomes=json.loads(o)

    def run_case(self, mutate=None, relock_plan_in_binding=True, relock_plan_in_outcomes=True,
                 relock_binding_in_outcomes=True):
        p,b,o=copy.deepcopy(self.plan),copy.deepcopy(self.binding),copy.deepcopy(self.outcomes)
        if mutate: mutate(p,b,o)
        pb=dump(p)
        if relock_plan_in_binding: b['plan_sha256']=hashlib.sha256(pb).hexdigest()
        if relock_plan_in_outcomes: o['plan_sha256']=hashlib.sha256(pb).hexdigest()
        bb=dump(b)
        if relock_binding_in_outcomes: o['binding_sha256']=hashlib.sha256(bb).hexdigest()
        return evaluate(pb,bb,dump(o))

    def held(self,fn): self.assertEqual(self.run_case(fn)['status'],'HOLD')

    def test_positive_control(self):
        r=self.run_case()
        self.assertEqual(r['status'],'PILOT_DESCRIPTIVE_RESULT')
        self.assertEqual(r['signal'],'positive')
        self.assertEqual(r['evidence_status'],'SYNTHETIC_DEMO')

    def test_binding_happy_path(self):
        r=self.run_case()
        self.assertEqual(r['status'],'PILOT_DESCRIPTIVE_RESULT')
        self.assertEqual(r['binding']['schema'],'secondrun.rating-binding.v2')
        self.assertEqual(r['binding_sha256'],hashlib.sha256(dump(self.binding)).hexdigest())
        self.assertNotIn('medal',self.plan['trials'][0])

    def test_reference_comparison_present(self):
        r=self.run_case()
        self.assertIn('comparison_vs_baseline', r)
        self.assertIn('comparison_vs_reference', r)
        self.assertIn('reference_brier', r['comparison_vs_reference'])
        self.assertIn('sensitivity', r)
        self.assertEqual(len(r['sensitivity']), len(self.plan['transform']['alternative_weights']))
        self.assertIn('leave_one_provider_out', r)
        self.assertEqual(len(r['leave_one_provider_out']), r['providers'])

    def test_signal_negative_on_inverted_anchors(self):
        def mutate(p,b,o):
            anchors=p['transform']['anchors']
            swapped={'Platinum':anchors['Underperforming'],'Gold':anchors['Bronze'],
                     'Silver':anchors['Silver'],'Bronze':anchors['Gold'],
                     'Underperforming':anchors['Platinum']}
            p['transform']['anchors']=swapped
            p['transform_sha256']=canonical_sha256(p['transform'])
        r=self.run_case(mutate)
        self.assertEqual(r['status'],'PILOT_DESCRIPTIVE_RESULT')
        self.assertEqual(r['signal'],'negative')
        self.assertLess(r['comparison_vs_reference']['mean_lift'],0)

    def test_signal_inconclusive_on_zero_weight(self):
        def mutate(p,b,o):
            p['transform']['weight']=0.0
            p['transform_sha256']=canonical_sha256(p['transform'])
        r=self.run_case(mutate)
        self.assertEqual(r['status'],'PILOT_DESCRIPTIVE_RESULT')
        self.assertEqual(r['signal'],'inconclusive')
        self.assertEqual(r['comparison_vs_reference']['mean_lift'],0)
        self.assertEqual(r['comparison_vs_baseline']['mean_lift'],0)

    def test_transform_hash_mismatch(self):
        def mutate(p,b,o):
            p['transform']['weight']=0.5  # transform_sha256 left stale
        self.held(mutate)

    # -- binding gates --------------------------------------------------
    def test_plan_hash_mismatch(self):
        # binding.plan_sha256 stays stale relative to a plan that actually changed.
        r=self.run_case(lambda p,b,o: p.update(study_id='study-id-changed'), relock_plan_in_binding=False)
        self.assertEqual(r['status'],'HOLD')

    def test_binding_tamper(self):
        # outcomes.binding_sha256 stays stale relative to a binding that actually changed.
        r=self.run_case(lambda p,b,o: b['source'].update(retrieved_utc='2026-01-02T00:00:01Z'),
                         relock_binding_in_outcomes=False)
        self.assertEqual(r['status'],'HOLD')

    def test_wrong_rating_version(self):
        self.held(lambda p,b,o: b.update(rating_version='not-the-plan-version'))

    def test_wrong_rating_name(self):
        self.held(lambda p,b,o: b.update(rating_name='Not the plan rating'))

    def test_missing_provider_in_binding(self):
        def mutate(p,b,o):
            del b['medals'][next(iter(b['medals']))]
        self.held(mutate)

    def test_extra_provider_in_binding(self):
        self.held(lambda p,b,o: b['medals'].update(NOT_A_TEST_PROVIDER='Gold'))

    def test_unknown_medal_tier(self):
        def mutate(p,b,o):
            k=next(iter(b['medals']))
            b['medals'][k]='Diamond'
        self.held(mutate)

    def test_unavailable_medal_tier_not_underperforming(self):
        def mutate(p,b,o):
            k=next(iter(b['medals']))
            b['medals'][k]='Unavailable'
        self.held(mutate)

    def test_bound_at_before_frozen_at(self):
        self.held(lambda p,b,o: b.update(bound_at='2026-01-01T00:00:00Z'))

    def test_bound_at_after_a_started_at(self):
        self.held(lambda p,b,o: b.update(bound_at='2026-01-10T00:00:00Z'))

    def test_rubric_missing(self):
        def mutate(p,b,o): del b['rubric']
        self.held(mutate)

    def test_rubric_incomplete_missing_url(self):
        def mutate(p,b,o): del b['rubric']['url']
        self.held(mutate)

    def test_rubric_sha256_non_hex(self):
        self.held(lambda p,b,o: b['rubric'].update(sha256='not-hex-'+'0'*56))

    def test_rubric_retrieved_utc_after_bound_at(self):
        self.held(lambda p,b,o: b['rubric'].update(retrieved_utc='2026-01-05T00:00:00Z'))

    def test_source_retrieved_utc_after_bound_at(self):
        self.held(lambda p,b,o: b['source'].update(retrieved_utc='2026-01-05T00:00:00Z'))

    def test_rubric_retrieved_utc_equal_bound_at_is_admissible(self):
        r=self.run_case(lambda p,b,o: b['rubric'].update(retrieved_utc=b['bound_at']))
        self.assertNotEqual(r['status'],'HOLD')

    # -- binding_rules (plan) --------------------------------------------
    def test_binding_rules_missing(self):
        def mutate(p,b,o): del p['binding_rules']
        self.held(mutate)

    def test_binding_rules_medal_source_missing(self):
        def mutate(p,b,o): del p['binding_rules']['medal_source']
        self.held(mutate)

    def test_binding_rules_rubric_source_missing(self):
        def mutate(p,b,o): del p['binding_rules']['rubric_source']
        self.held(mutate)

    def test_binding_rules_tiers_mismatch(self):
        def mutate(p,b,o): p['binding_rules']['tiers']=['Platinum','Gold']
        self.held(mutate)

    def test_plan_carries_no_rating_rules_sha256_field(self):
        # rating_rules_sha256 moved out of the plan entirely (schema v4); a plan
        # that never had the field at all is admissible -- there is nothing left
        # that requires it.
        self.assertNotIn('rating_rules_sha256', self.plan)
        r=self.run_case()
        self.assertNotEqual(r['status'],'HOLD')

    def test_leftover_rating_rules_sha256_field_is_ignored(self):
        # An old-shaped plan that still happens to carry the retired field is
        # neither required nor rejected for it -- the field is simply unused.
        r=self.run_case(lambda p,b,o: p.update(rating_rules_sha256='a'*64))
        self.assertNotEqual(r['status'],'HOLD')

    # -- credits accounting -----------------------------------------------
    def test_credits_exceeding_cost_is_held(self):
        def mutate(p,b,o):
            row=o['trials'][0]
            row.update(credits_redeemed_usd=row['total_cost_usd']+1)
        self.held(mutate)

    def test_credits_equal_to_cost_is_admissible(self):
        def mutate(p,b,o):
            row=o['trials'][0]
            row.update(credits_redeemed_usd=row['total_cost_usd'])
        r=self.run_case(mutate)
        self.assertNotEqual(r['status'],'HOLD')

    def test_credits_reported_separately_in_economics(self):
        r=self.run_case()
        row=next(x for x in r['economics'] if x['trial_id']==self.outcomes['trials'][0]['trial_id'])
        self.assertIn('credits_redeemed_usd', row)
        self.assertIn('total_cost_usd', row)
        self.assertEqual(row['credits_redeemed_usd'], self.outcomes['trials'][0].get('credits_redeemed_usd', 0))

    def test_credits_default_to_zero_when_absent(self):
        def mutate(p,b,o):
            for row in o['trials']:
                row.pop('credits_redeemed_usd', None)
        r=self.run_case(mutate)
        self.assertNotEqual(r['status'],'HOLD')
        self.assertEqual(r['subsidized_trials'], 0)
        self.assertTrue(all(c['credits_redeemed_usd']==0 for c in r['economics']))

    def test_subsidized_trials_count(self):
        r=self.run_case()
        expected=sum(1 for t in self.outcomes['trials'] if t.get('credits_redeemed_usd', 0) > 0)
        self.assertGreater(expected, 0)
        self.assertEqual(r['subsidized_trials'], expected)

    def test_gates_and_cost_per_1000_unaffected_by_credits(self):
        # Two packets differing only in credits_redeemed_usd (both admissible)
        # must produce identical gate/economics list-charge figures.
        base=self.run_case()
        def mutate(p,b,o):
            for row in o['trials']:
                row['credits_redeemed_usd']=min(0.01, row['total_cost_usd'])
        varied=self.run_case(mutate)
        base_costs={c['trial_id']:(c['total_cost_usd'],c['cost_per_1000_accepted']) for c in base['economics']}
        varied_costs={c['trial_id']:(c['total_cost_usd'],c['cost_per_1000_accepted']) for c in varied['economics']}
        self.assertEqual(base_costs, varied_costs)
        self.assertEqual(base['comparison_vs_baseline']['mean_lift'], varied['comparison_vs_baseline']['mean_lift'])

    # -- disclosure -------------------------------------------------------
    def test_disclosure_field_missing(self):
        for field in DISCLOSURE_FIELDS:
            with self.subTest(field=field):
                self.held(lambda p,b,o,field=field: p['disclosure'].pop(field))

    def test_disclosure_placeholder_variants(self):
        variants = ['CONFIRM: fill this in', 'Unknown', 'UNCONFIRMED', 'TBD', 'todo',
                    'Pending legal review', '???', '[redact before publishing]',
                    'none / describe']
        for token in variants:
            with self.subTest(token=token):
                self.held(lambda p,b,o,token=token: p['disclosure'].update(relationship=token))

    def test_placeholder_tokens_cover_spec(self):
        expected = {'confirm', 'unknown', 'unconfirmed', 'tbd', 'todo', 'pending', '???', '[', 'describe'}
        self.assertEqual(set(PLACEHOLDER_TOKENS), expected)

    def test_coverage_floor_trials(self):
        def mutate(p,b,o):
            provider=p['trials'][0]['provider_id']
            # Drop all but 5 trials for the first provider; keep everything else.
            provider_trials=[t for t in p['trials'] if t['provider_id']==provider][:5]
            drop_ids={t['trial_id'] for t in p['trials'] if t['provider_id']==provider} - {t['trial_id'] for t in provider_trials}
            p['trials']=[t for t in p['trials'] if t['trial_id'] not in drop_ids]
            o['trials']=[t for t in o['trials'] if t['trial_id'] not in drop_ids]
        self.held(mutate)
    def test_coverage_floor_sessions(self):
        def mutate(p,b,o):
            provider=p['trials'][0]['provider_id']
            for t in p['trials']:
                if t['provider_id']==provider: t['session_id']='S1'
            for t in o['trials']:
                if t['provider_id']==provider: t['session_id']='S1'
        self.held(mutate)
    def test_coverage_floor_dates(self):
        def mutate(p,b,o):
            provider=p['trials'][0]['provider_id']
            for t in o['trials']:
                if t['provider_id']==provider:
                    t.update(started_at='2026-01-03T00:00:00Z', finished_at='2026-01-03T00:10:00Z')
        self.held(mutate)
    def test_missing_trial(self): self.held(lambda p,b,o:o['trials'].pop())
    def test_extra_trial(self): self.held(lambda p,b,o:o['trials'].append({**o['trials'][0],'trial_id':'EXTRA'}))
    def test_duplicate_trial(self): self.held(lambda p,b,o:o['trials'].append(o['trials'][0]))
    def test_admin_scope(self):
        self.held(lambda p,b,o:(p['trials'][0].update(customer_role='administrator'),o['trials'][0].update(customer_role='administrator')))
    def test_reviewer_support(self):
        self.held(lambda p,b,o:(p['trials'][0].update(support='reviewer'),o['trials'][0].update(support='reviewer')))
    def test_changed_actual_service(self): self.held(lambda p,b,o:o['trials'][0].update(service_id='curated'))
    def test_late_prediction(self): self.held(lambda p,b,o:p['trials'][0].update(predicted_at='2026-01-04T00:00:00Z'))
    def test_late_plan(self): self.held(lambda p,b,o:p.update(frozen_at='2026-01-04T00:00:00Z'))
    def test_training_leak(self): self.held(lambda p,b,o:[m.update(training_providers=[p['trials'][0]['provider_id']]) for m in (p['baseline'],p['with_rating'])])
    def test_changed_other_inputs(self): self.held(lambda p,b,o:p['with_rating']['inputs'].append('special_access'))
    def test_missing_latency(self):
        self.held(lambda p,b,o:o['trials'][0].update(status='complete',p95_ms=None))
    def test_invalid_probability(self): self.held(lambda p,b,o:p['trials'][0].update(p_baseline=1.1))
    def test_boolean_is_not_number(self): self.held(lambda p,b,o:p['trials'][0].update(p_baseline=True))
    def test_nan_json(self): self.assertEqual(evaluate(b'{"x":NaN}',b'{}',b'{}')['status'],'HOLD')
    def test_zero_accepted_is_retained(self):
        r=self.run_case(lambda p,b,o:o['trials'][0].update(accepted=0,status='timeout',p95_ms=None))
        self.assertNotEqual(r['status'],'HOLD');self.assertIsNone(r['economics'][0]['cost_per_1000_accepted'])
    def test_incomplete_cohort(self): self.held(lambda p,b,o:(p.update(trials=p['trials'][:12]),o.update(trials=o['trials'][:12])))
    def test_repeatable(self): self.assertEqual(self.run_case(),self.run_case())
    def test_empty_is_not_pass(self): self.assertEqual(evaluate(b'{}',b'{}',b'{}')['status'],'HOLD')
    def test_exit_codes(self):
        pos=self.run_case()
        neg=self.run_case(lambda p,b,o:o['trials'].pop())
        self.assertEqual(pos['status'],'PILOT_DESCRIPTIVE_RESULT')
        self.assertEqual(neg['status'],'HOLD')

if __name__=='__main__':unittest.main()
