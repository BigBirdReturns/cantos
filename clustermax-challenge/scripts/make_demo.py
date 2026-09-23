#!/usr/bin/env python3
"""Create a deterministic, explicitly synthetic positive-control dataset."""
import hashlib, json, random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(s): return hashlib.sha256(s.encode()).hexdigest()
def dump(x): return (json.dumps(x,indent=2,allow_nan=False)+'\n').encode()
def build():
    rng=random.Random(93)
    inputs=['gpu','allocation','price','workload','region','service']
    model={'description':'Synthetic specs-and-price baseline; no real model was trained.',
      'model_sha256':sha('synthetic baseline'),'inputs':inputs,
      'training_providers':['TRAINING_ONLY_1'],'frozen_at':'2026-01-01T00:00:00Z'}
    plan={'schema':'secondrun.rating-plan.v1','synthetic':True,
      'study_id':'synthetic-positive-control','rating_name':'Synthetic example, not ClusterMAX',
      'rating_version':'demo-1','rating_rules_sha256':sha('demo rubric'),
      'frozen_at':'2026-01-02T00:00:00Z','minimum_providers':8,'minimum_lift':0.01,
      'outcome_definition':'Complete at least 900 accepted requests, p95 <= 200 ms and total cost <= USD 1.',
      'baseline':model, 'with_rating':{**model,'description':'Synthetic baseline plus rating predictor.',
      'model_sha256':sha('synthetic augmented'),'inputs':inputs+['rating']},'trials':[]}
    outcomes={'schema':'secondrun.rating-outcomes.v1','plan_sha256':'','trials':[]}
    for p in range(24):
        probability=[.12,.25,.38,.62,.75,.88][p%6]
        for n in range(12):
            rid=f'P{p+1:02d}-T{n+1:02d}'
            ctx={'provider_id':f'EXAMPLE_{p+1:02d}','service_id':'synthetic-1gpu',
                'region':'example-region','workload_sha256':sha('synthetic workload'),
                'validator_sha256':sha('synthetic validator'),'customer_role':'ordinary_tenant',
                'support':'standard'}
            plan['trials'].append({'trial_id':rid,**ctx,'predicted_at':'2026-01-01T12:00:00Z',
                'p_baseline':.5,'p_with_rating':probability,
                'gates':{'accepted_min':900,'p95_max_ms':200,'cost_max_usd':1}})
            good=rng.random()<probability
            outcomes['trials'].append({'trial_id':rid,**ctx,'started_at':'2026-01-03T00:00:00Z',
                'finished_at':'2026-01-03T00:10:00Z','status':'complete' if good else 'timeout',
                'accepted':1000 if good else 200,'attempted':1050,'p95_ms':150 if good else 300,
                'total_cost_usd':.75,'receipt_ref':'synthetic:'+rid,'receipt_sha256':sha('synthetic:'+rid)})
    pb=dump(plan);outcomes['plan_sha256']=hashlib.sha256(pb).hexdigest()
    return pb,dump(outcomes)
if __name__=='__main__':
    a,b=build(); (ROOT/'data/demo-plan.json').write_bytes(a);(ROOT/'data/demo-outcomes.json').write_bytes(b)
