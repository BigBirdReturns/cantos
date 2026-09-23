import copy, hashlib, importlib.util, json, math, re, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import challenge
from challenge import (evaluate, canonical_sha256, canonical_json, es_number, count_arrangements,
                       validate_transform, InvalidPacket, PLACEHOLDER_TOKENS, DISCLOSURE_FIELDS)
from make_demo import build, dump

# Real ClusterMAX 3.0 names with their transcribed tiers, for registered-source tests.
REGISTERED_NAMES=[('CoreWeave','Platinum'),('Oracle','Gold'),('Google Cloud','Gold'),('Azure','Silver'),
                  ('Firmus','Silver'),('Lambda','Silver'),('GMI','Silver'),('AWS','Bronze'),('GCore','Bronze'),('Verda','Bronze')]
PNG_SHA='79dc81e4cf7a503632c631b69f011f2a7af109e719cc32253344820cda402e02'

def rename_providers(p,b,o,names):
    ids=sorted(b['medals'])
    mapping={old:new for old,(new,_) in zip(ids,names)}
    for row in p['trials']+o['trials']: row['provider_id']=mapping[row['provider_id']]
    b['medals']={new:tier for new,tier in names}

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

    def held(self,fn,contains=None):
        r=self.run_case(fn)
        self.assertEqual(r['status'],'HOLD',r.get('signal'))
        if contains: self.assertIn(contains,r['reason'])
        return r

    def admitted(self,fn):
        r=self.run_case(fn)
        self.assertEqual(r['status'],'PILOT_DESCRIPTIVE_RESULT',r.get('reason'))
        return r

    # -- v1.4 primary test: medal permutation ---------------------------------------
    def test_positive_control(self):
        r=self.run_case()
        self.assertEqual(r['status'],'PILOT_DESCRIPTIVE_RESULT')
        self.assertEqual(r['signal'],'positive')
        self.assertEqual(r['evidence_status'],'SYNTHETIC_DEMO')
        t=r['medal_permutation_test']
        self.assertEqual(t['question'],'Do medals rank providers better than chance?')
        self.assertEqual(t['method'],'exact_enumeration')
        self.assertEqual(t['permutations'],4200)  # 10!/(3!4!3!)
        self.assertEqual(t['distinct_medals'],3)
        self.assertLessEqual(t['p_help'],0.05)
        self.assertGreater(t['T_obs'],r['minimum_lift'])
        # exact enumeration counts the observed assignment among the N, no +1
        self.assertAlmostEqual(t['p_help']*t['permutations'],round(t['p_help']*t['permutations']),places=9)
        self.assertGreaterEqual(t['p_help'],1/t['permutations'])

    def test_shuffled_medals_inconclusive(self):
        r=evaluate(*build('shuffled'))
        self.assertEqual(r['status'],'PILOT_DESCRIPTIVE_RESULT')
        self.assertEqual(r['signal'],'inconclusive')
        self.assertGreater(r['medal_permutation_test']['p_help'],0.05)

    def test_level_shift_only_no_longer_positive(self):
        r=evaluate(*build('level-shift'))
        self.assertEqual(r['status'],'PILOT_DESCRIPTIVE_RESULT')
        self.assertEqual(r['signal'],'inconclusive')
        t=r['medal_permutation_test']
        self.assertEqual(t['method'],'monte_carlo')  # 12!/(4!4!4!) = 34650 > 20000
        self.assertEqual(t['permutations'],20000)
        # (1+count)/(1+N) form
        self.assertAlmostEqual(t['p_help']*20001,round(t['p_help']*20001),places=6)
        # v1.3's decision rule (lower bound of the 0.50-reference interval > minimum_lift)
        # called this cohort positive: every provider is identical, only the level moved.
        ref=r['descriptive']['comparison_vs_reference']
        self.assertGreater(ref['bootstrap_95'][0],r['minimum_lift'])

    def test_inverted_medals_negative(self):
        swap={'Gold':'Bronze','Bronze':'Gold','Silver':'Silver'}
        r=self.admitted(lambda p,b,o: b.update(medals={k:swap[v] for k,v in b['medals'].items()}))
        self.assertEqual(r['signal'],'negative')
        self.assertLessEqual(r['medal_permutation_test']['p_hurt'],0.05)
        self.assertLess(r['medal_permutation_test']['T_obs'],-r['minimum_lift'])

    def test_single_medal_not_testable(self):
        r=self.admitted(lambda p,b,o: b.update(medals={k:'Gold' for k in b['medals']}))
        self.assertEqual(r['signal'],'not_testable')
        t=r['medal_permutation_test']
        self.assertIsNone(t['p_help']); self.assertAlmostEqual(t['T_obs'],0.0,places=12)

    def test_level_shift_invariance(self):
        # Relabelling every provider one tier up shifts the level, not the ranking: T must not move much
        # beyond the change in anchor spacing (here spacing is equal, 0.10), so T is unchanged.
        up={'Gold':'Platinum','Silver':'Gold','Bronze':'Silver'}
        base=self.run_case()['medal_permutation_test']
        r=self.admitted(lambda p,b,o: b.update(medals={k:up[v] for k,v in b['medals'].items()}))
        self.assertAlmostEqual(r['medal_permutation_test']['T_obs'],base['T_obs'],places=12)
        self.assertEqual(r['medal_permutation_test']['p_help'],base['p_help'])

    def test_descriptive_comparisons_kept(self):
        r=self.run_case()
        self.assertNotIn('comparison_vs_reference',r)
        d=r['descriptive']
        self.assertIn('level shift',d['note'])
        self.assertIn('reference_brier',d['comparison_vs_reference'])
        self.assertEqual(d['comparison_vs_reference']['reference_anchor'],0.5)
        self.assertEqual(len(d['sensitivity']),len(self.plan['transform']['alternative_weights']))
        self.assertEqual(len(d['leave_one_provider_out']),r['providers'])
        self.assertEqual(len(r['medal_permutation_test']['sensitivity']),2)
        self.assertEqual(r['schema'],'secondrun.rating-result.v5')
        self.assertEqual(r['test_version'],'1.4.0')

    def test_count_arrangements(self):
        self.assertEqual(count_arrangements([3,4,3],20000),4200)
        self.assertEqual(count_arrangements([4,4,4],20000),20001)
        self.assertEqual(count_arrangements([9,1],20000),10)
        self.assertEqual(count_arrangements([1]*7,20000),5040)

    # -- transform lock --------------------------------------------------------------
    def test_transform_hash_mismatch(self):
        self.held(lambda p,b,o: p['transform'].update(weight=0.5), 'transform_sha256')

    def test_unregistered_transform_held(self):
        def mutate(p,b,o):
            p['transform']['reference_anchor']=0.95
            p['transform_sha256']=canonical_sha256(p['transform'])
        self.held(mutate,'not a registered published transform')

    def test_registered_transform_is_design_transform(self):
        t=json.loads((ROOT/'design/transform.json').read_text(encoding='utf-8'))
        reg=json.loads((ROOT/'design/registry.json').read_text(encoding='utf-8'))
        self.assertEqual([x['sha256'] for x in reg['transforms']],[canonical_sha256(t)])
        self.assertEqual(canonical_sha256(t),'2a5d65120ea83be53edd2ccc671b46e77b3e810f53fa8e33c73871668c6f1d90')

    def test_inverted_anchors_rejected(self):
        t=json.loads((ROOT/'design/transform.json').read_text(encoding='utf-8'))
        t['anchors']={'Platinum':0.1,'Gold':0.2,'Silver':0.5,'Bronze':0.8,'Underperforming':0.9}
        with self.assertRaisesRegex(InvalidPacket,'strictly decreasing'): validate_transform(t)
        t['anchors']={'Platinum':0.9,'Gold':0.8,'Silver':0.8,'Bronze':0.6,'Underperforming':0.3}
        with self.assertRaisesRegex(InvalidPacket,'strictly decreasing'): validate_transform(t)

    def test_index_embeds_registry_and_transform(self):
        h=(ROOT/'index.html').read_text(encoding='utf-8')
        reg=json.loads(re.search(r'^const REGISTRY=(.*);$',h,re.M).group(1))
        self.assertEqual(reg,json.loads((ROOT/'design/registry.json').read_text(encoding='utf-8')))
        t=json.loads(re.search(r'^const PUBLISHED_TRANSFORM=(.*);$',h,re.M).group(1))
        self.assertEqual(t,json.loads((ROOT/'design/transform.json').read_text(encoding='utf-8')))
        self.assertIn("const VERSION='1.4.0'",h)

    # -- uniform gates / training ----------------------------------------------------
    def test_nonuniform_gates_held(self):
        def mutate(p,b,o):
            for row in p['trials']:
                if row['provider_id']=='EXAMPLE_01': row['gates']['cost_max_usd']=0.5
        self.held(mutate,'gates differ')

    def test_uniform_gates_integral_float_equal(self):
        def mutate(p,b,o): p['trials'][0]['gates']['cost_max_usd']=1.0
        self.admitted(mutate)

    def test_empty_training_providers_held(self):
        self.held(lambda p,b,o:[m.update(training_providers=[]) for m in (p['baseline'],p['with_rating'])],
                  'training_providers must be nonempty')

    # -- source registry --------------------------------------------------------------
    def registered(self,p,b,o,names=REGISTERED_NAMES,sha=PNG_SHA):
        rename_providers(p,b,o,names)
        for x in (p,b): x.update(rating_name='ClusterMAX',rating_version='3.0')
        b['source']['sha256']=sha

    def test_registry_transcription_matches_release(self):
        reg=json.loads((ROOT/'design/registry.json').read_text(encoding='utf-8'))
        entry=reg['ratings'][0]
        t=json.loads((ROOT/entry['transcription']['path']).read_text(encoding='utf-8'))
        self.assertEqual(entry['transcription']['tiers'],{x['name']:x['tier'] for x in t['providers']})
        sums=(ROOT/'launch/release-3.0/raw/SHA256SUMS.txt').read_text(encoding='utf-8')
        for s in entry['medal_table_sources']:
            self.assertEqual(hashlib.sha256((ROOT/s['path']).read_bytes()).hexdigest(),s['sha256'])
            self.assertIn(s['sha256'],sums)

    def test_registered_source_admitted(self):
        r=self.admitted(self.registered)
        self.assertEqual(r['source_verification'],'registered_source')

    def test_tweet_image_digest_also_registered(self):
        r=self.admitted(lambda p,b,o:self.registered(p,b,o,sha='5477994f1bf0881f02175344123eb167eddcded31c6cb7471fdeb5fe018b5c51'))
        self.assertEqual(r['source_verification'],'registered_source')

    def test_registered_rating_wrong_source_held(self):
        self.held(lambda p,b,o:self.registered(p,b,o,sha='a'*64),'not a registered medal-table source')

    def test_registered_rating_tier_mismatch_held(self):
        names=list(REGISTERED_NAMES); names[0]=('CoreWeave','Gold')
        self.held(lambda p,b,o:self.registered(p,b,o,names=names),'differs from the registered transcription')

    def test_registered_rating_unknown_provider_held(self):
        names=[('Coreweave','Platinum')]+REGISTERED_NAMES[1:]
        self.held(lambda p,b,o:self.registered(p,b,o,names=names),'not in the registered transcription')

    def test_registered_rating_name_normalized(self):
        def mutate(p,b,o):
            self.registered(p,b,o)
            for x in (p,b): x['rating_name']='Cluster MAX'
            b['source']['sha256']='b'*64
        self.held(mutate,'not a registered medal-table source')

    def test_unregistered_version_flagged(self):
        def mutate(p,b,o):
            self.registered(p,b,o,sha='c'*64)
            for x in (p,b): x['rating_version']='3.1'
        r=self.admitted(mutate)
        self.assertEqual(r['source_verification'],'source_unverified')
        self.assertEqual(self.run_case()['source_verification'],'source_unverified')

    # -- parity rules (shared with tests/test_engine.cjs) ------------------------------
    def test_prototype_names_are_plain_strings(self):
        for tier in ('constructor','__proto__','toString','hasOwnProperty'):
            with self.subTest(tier=tier):
                self.held(lambda p,b,o,tier=tier: b['medals'].update(EXAMPLE_01=tier),'not one of the frozen transform anchors')
        r=self.admitted(lambda p,b,o: rename_providers(p,b,o,[('__proto__','Gold')]+[(f'EXAMPLE_{i:02d}',t) for i,t in
            zip(range(2,11),['Gold','Gold','Silver','Silver','Silver','Silver','Bronze','Bronze','Bronze'])]))
        self.assertIn('__proto__',r['provider_results'])

    def test_integral_float_integers_accepted(self):
        base=self.run_case()
        def mutate(p,b,o):
            p['minimum_providers']=8.0
            for row in p['trials']: row['gates']['accepted_min']=900.0
            for row in o['trials']: row['accepted']=float(row['accepted'])
        r=self.admitted(mutate)
        self.assertEqual(r['medal_permutation_test'],base['medal_permutation_test'])
        self.assertIsInstance(r['economics'][0]['accepted'],int)

    def test_non_integers_rejected(self):
        self.held(lambda p,b,o:[row['gates'].update(accepted_min=900.5) for row in p['trials']],'accepted_min: integer required')
        self.held(lambda p,b,o:p.update(minimum_providers=8.5),'At least eight')
        self.held(lambda p,b,o:p.update(minimum_providers=True),'At least eight')
        self.held(lambda p,b,o:o['trials'][0].update(accepted=True),'integer required')
        self.held(lambda p,b,o:o['trials'][0].update(attempted=10**400),'integer required')

    def test_submillisecond_prediction_after_freeze_held(self):
        self.held(lambda p,b,o:p['trials'][0].update(predicted_at='2026-01-02T00:00:00.0004Z'),'not prospective')

    def test_fraction_truncated_to_microseconds(self):
        # 0.0000009 s truncates to 0 us: equal to frozen_at, so still admissible (pred <= frozen)
        self.admitted(lambda p,b,o:p['trials'][0].update(predicted_at='2026-01-02T00:00:00.0000009Z'))
        self.admitted(lambda p,b,o:p['trials'][0].update(predicted_at='2026-01-01T12:00:00.1234567+00:00'))

    def test_submillisecond_bound_before_start(self):
        def mutate(p,b,o,bound,start):
            b['bound_at']=bound
            o['trials'][0].update(started_at=start)
        # distinct microseconds within one millisecond: strictly before -> admissible
        self.admitted(lambda p,b,o:mutate(p,b,o,'2026-01-02T23:59:59.999001Z','2026-01-02T23:59:59.999002Z'))
        # equal after truncation to microseconds -> not strictly before -> held
        self.held(lambda p,b,o:mutate(p,b,o,'2026-01-02T23:59:59.9990004Z','2026-01-02T23:59:59.9990009Z'),'strictly before')

    def test_timestamp_range_and_offsets(self):
        self.held(lambda p,b,o:p['baseline'].update(frozen_at='1969-12-31T00:00:00Z'),'year outside')
        self.held(lambda p,b,o:p['trials'][0].update(predicted_at='2026-01-01T12:00:00+24:00'),'invalid timezone offset')
        self.held(lambda p,b,o:p['trials'][0].update(predicted_at='2026-02-29T12:00:00Z'),'invalid calendar date')
        self.held(lambda p,b,o:p['trials'][0].update(predicted_at='2026-01-01T12:00:00٣Z'),'RFC3339')
        self.admitted(lambda p,b,o:p['trials'][0].update(predicted_at='2026-01-01T17:30:00+05:30'))

    def test_es_number_vectors(self):
        vectors={0.1:'0.1',1e-7:'1e-7',100.0:'100',0.30000000000000004:'0.30000000000000004',-0.0:'0',
                 1e21:'1e+21',1.5e20:'150000000000000000000',1e-6:'0.000001',2**60:'1152921504606847000',
                 9007199254740993:'9007199254740992',5e-324:'5e-324',-2.5e-8:'-2.5e-8',123.456:'123.456'}
        for v,s in vectors.items():
            with self.subTest(v=v): self.assertEqual(es_number(v),s)

    def test_canonical_json_js_compatible(self):
        self.assertEqual(canonical_json({'b':1.0,'a':[0.1,1e-7,100.0,0.30000000000000004,True,None,'é']}),
                         '{"a":[0.1,1e-7,100,0.30000000000000004,true,null,"é"],"b":1}')
        # UTF-16 code-unit key order: an astral character (D83D...) sorts before U+FF21.
        self.assertEqual(canonical_json({'Ａk':1,'\U0001F600k':2}),'{"\U0001F600k":2,"Ａk":1}')
        with self.assertRaises(InvalidPacket): canonical_json({'x':'\ud800'})

    def test_lone_surrogate_in_transform_held(self):
        def mutate(p,b,o):
            p['transform']['description']+='\ud800'
            p['transform_sha256']='0'*64
        p,b,o=copy.deepcopy(self.plan),copy.deepcopy(self.binding),copy.deepcopy(self.outcomes)
        mutate(p,b,o)
        pb=json.dumps(p).encode()  # ensure_ascii keeps the lone surrogate as an escape
        b['plan_sha256']=o['plan_sha256']=hashlib.sha256(pb).hexdigest();bb=dump(b)
        o['binding_sha256']=hashlib.sha256(bb).hexdigest()
        r=evaluate(pb,bb,dump(o))
        self.assertEqual(r['status'],'HOLD'); self.assertIn('lone surrogate',r['reason'])

    def test_missing_p95_key_held(self):
        self.held(lambda p,b,o:o['trials'][0].pop('p95_ms'),'p95_ms required')

    def test_huge_number_is_not_finite(self):
        for literal in (b'1e400', b'1'+b'0'*400):
            with self.subTest(literal=literal[:6]):
                p,b,o=copy.deepcopy(self.plan),copy.deepcopy(self.binding),copy.deepcopy(self.outcomes)
                pb=dump(p).replace(b'"p_baseline": 0.5,',b'"p_baseline": '+literal+b',',1)
                b['plan_sha256']=o['plan_sha256']=hashlib.sha256(pb).hexdigest();bb=dump(b)
                o['binding_sha256']=hashlib.sha256(bb).hexdigest()
                r=evaluate(pb,bb,dump(o))
                self.assertEqual(r['status'],'HOLD'); self.assertIn('p_baseline: finite number required',r['reason'])

    def test_binding_happy_path(self):
        r=self.run_case()
        self.assertEqual(r['status'],'PILOT_DESCRIPTIVE_RESULT')
        self.assertEqual(r['binding']['schema'],'secondrun.rating-binding.v2')
        self.assertEqual(r['binding_sha256'],hashlib.sha256(dump(self.binding)).hexdigest())
        self.assertNotIn('medal',self.plan['trials'][0])

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
        self.assertEqual(base['descriptive']['comparison_vs_baseline']['mean_lift'], varied['descriptive']['comparison_vs_baseline']['mean_lift'])
        self.assertEqual(base['medal_permutation_test'], varied['medal_permutation_test'])

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
