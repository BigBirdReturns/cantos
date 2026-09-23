#!/usr/bin/env python3
"""Create a deterministic, explicitly synthetic positive-control dataset."""
import hashlib, json, random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MEDALS=('Platinum','Gold','Silver','Bronze','Underperforming')
# True pass probability used only to generate synthetic outcomes; deliberately more
# separated than the frozen transform's compressed 0.25-weighted anchors, the way a
# real unknown outcome process need not match a predictor's stated confidence.
TRUE_PASS_PROBABILITY={'Platinum':0.85,'Gold':0.70,'Silver':0.50,'Bronze':0.30,'Underperforming':0.15}
# Baseline probabilities, offset from the medal cycle so the plain baseline carries
# its own (weaker, uncorrelated) signal instead of coinciding with the medal-blind
# reference anchor -- this lets the demo show a real difference between "vs baseline"
# and "vs reference" instead of the two comparisons collapsing to the same numbers.
BASELINE_PROBABILITY=[0.35,0.45,0.5,0.55,0.65]
PROVIDERS=30
TRIALS_PER_PROVIDER=15
SESSIONS_PER_PROVIDER=5
DATES_PER_PROVIDER=3
# Synthetic-demo disclosure text: obviously not a real answer, never place real
# disclosure content in a demo/synthetic plan.
DISCLOSURE={
    'relationship':'Synthetic demo: no relationship with any provider or rating in this packet.',
    'compensation':'Synthetic demo: no compensation received.',
    'credits':'Synthetic demo: no credits or special support received.',
    'special_support':'Synthetic demo: no special access or support of any kind.',
    'editorial_influence':'Synthetic demo: no editorial influence exercised by any named party.',
}

def sha(s): return hashlib.sha256(s.encode()).hexdigest()
def dump(x): return (json.dumps(x,indent=2,allow_nan=False)+'\n').encode()
def canonical_sha256(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False,ensure_ascii=False).encode('utf-8')).hexdigest()

def load_transform():
    transform=json.loads((ROOT/'design/transform.json').read_text(encoding='utf-8'))
    return transform

def build():
    rng=random.Random(93)
    transform=load_transform()
    weight=transform['weight']
    anchors=transform['anchors']
    inputs=['gpu','allocation','price','workload','region','service']
    model={'description':'Synthetic specs-and-price baseline; no real model was trained.',
      'model_sha256':sha('synthetic baseline'),'inputs':inputs,
      'training_providers':['TRAINING_ONLY_1'],'frozen_at':'2026-01-01T00:00:00Z'}
    frozen_at='2026-01-02T00:00:00Z'
    binding_rules={'medal_source':'Official ClusterMAX medal table page, as published by SemiAnalysis.',
      'rubric_source':'Official ClusterMAX rubric/methodology document for the bound rating_version.',
      'tiers':list(MEDALS)}
    plan={'schema':'secondrun.rating-plan.v4','synthetic':True,
      'study_id':'synthetic-positive-control','rating_name':'Synthetic example, not ClusterMAX',
      'rating_version':'demo-1',
      'frozen_at':frozen_at,'minimum_providers':8,'minimum_lift':0.004,
      'outcome_definition':'Complete at least 900 accepted requests, p95 <= 200 ms and total cost <= USD 1.',
      'disclosure':DISCLOSURE,'binding_rules':binding_rules,
      'transform':transform,'transform_sha256':canonical_sha256(transform),
      'baseline':model, 'with_rating':{**model,'description':'Synthetic baseline plus rating predictor.',
      'model_sha256':sha('synthetic augmented'),'inputs':inputs+['rating']},'trials':[]}
    outcomes={'schema':'secondrun.rating-outcomes.v4','plan_sha256':'','binding_sha256':'','trials':[]}
    medals={}
    for p in range(PROVIDERS):
        provider_id=f'EXAMPLE_{p+1:02d}'
        medal=MEDALS[p % len(MEDALS)]
        medals[provider_id]=medal
        pb=BASELINE_PROBABILITY[(p + 2) % len(BASELINE_PROBABILITY)]
        true_probability=TRUE_PASS_PROBABILITY[medal]
        for n in range(TRIALS_PER_PROVIDER):
            rid=f'P{p+1:02d}-T{n+1:02d}'
            session=f'S{(n % SESSIONS_PER_PROVIDER)+1}'
            day=3 + (n % DATES_PER_PROVIDER)
            started=f'2026-01-{day:02d}T00:00:00Z'
            finished=f'2026-01-{day:02d}T00:10:00Z'
            ctx={'provider_id':provider_id,'service_id':'synthetic-1gpu',
                'region':'example-region','workload_sha256':sha('synthetic workload'),
                'validator_sha256':sha('synthetic validator'),'customer_role':'ordinary_tenant',
                'support':'standard','session_id':session}
            plan['trials'].append({'trial_id':rid,**ctx,'predicted_at':'2026-01-01T12:00:00Z',
                'p_baseline':pb,
                'gates':{'accepted_min':900,'p95_max_ms':200,'cost_max_usd':1}})
            good=rng.random()<true_probability
            # First provider's trials carry a token demo credit redemption so the
            # engine's credits/subsidized-trials accounting is exercised end to
            # end by the default demo, not just by tests that hand-construct it.
            credits=0.10 if p==0 else 0
            outcomes['trials'].append({'trial_id':rid,**ctx,'started_at':started,
                'finished_at':finished,'status':'complete' if good else 'timeout',
                'accepted':1000 if good else 200,'attempted':1050,'p95_ms':150 if good else 300,
                'total_cost_usd':.75,'credits_redeemed_usd':credits,
                'receipt_ref':'synthetic:'+rid,'receipt_sha256':sha('synthetic:'+rid)})
    pb_bytes=dump(plan)
    plan_hash=hashlib.sha256(pb_bytes).hexdigest()
    binding={'schema':'secondrun.rating-binding.v2','plan_sha256':plan_hash,
      'rating_name':plan['rating_name'],'rating_version':plan['rating_version'],
      'source':{'url':'https://example.invalid/synthetic-medal-table','sha256':sha('synthetic medal table'),
                 'retrieved_utc':'2026-01-02T06:00:00Z'},
      'rubric':{'url':'https://example.invalid/synthetic-rubric','sha256':sha('synthetic rubric'),
                 'retrieved_utc':'2026-01-02T06:00:00Z'},
      # Bound after the plan froze (2026-01-02T00:00:00Z) and strictly before the earliest
      # job start (2026-01-03T00:00:00Z), the way a real binding is filled in after the
      # rating publishes but before any attempt runs. Both source/rubric retrieved_utc
      # (06:00) are also at-or-before bound_at (12:00), same day.
      'bound_at':'2026-01-02T12:00:00Z','medals':medals}
    binding_bytes=dump(binding)
    outcomes['plan_sha256']=plan_hash
    outcomes['binding_sha256']=hashlib.sha256(binding_bytes).hexdigest()
    return pb_bytes,binding_bytes,dump(outcomes)
if __name__=='__main__':
    a,b,c=build()
    (ROOT/'data/demo-plan.json').write_bytes(a)
    (ROOT/'data/demo-binding.json').write_bytes(b)
    (ROOT/'data/demo-outcomes.json').write_bytes(c)
