#!/usr/bin/env python3
"""Independent arithmetic check of the small capacity scenario and historical reprice.

This is not a full native schema verifier, signature verifier or source-authenticity check.
Use verify.cjs for exact full projection equality through the native calculation owner.
"""
import hashlib,json,math,sys
from pathlib import Path
COSTS=('preparation','validation','operations','recovery','coordination','capture','upkeep')
BASE='9633e3e79d7a5c4ba0382560ed99dc9273b5fdeb'
ENGINE='21956dbce1449a3bbfdedfce3a5064e5b8d87495'
SOURCE='95289238fca808c15f82b9c90aad364d8405d640'
def equal(actual,expected,label):
    if expected is None:
        if actual is not None: raise ValueError(label+' must remain unknown.')
    elif isinstance(actual,bool) or not isinstance(actual,(int,float)) or not math.isfinite(actual) or not math.isclose(actual,expected,rel_tol=1e-12,abs_tol=1e-9):
        raise ValueError(label+' disagrees with independent arithmetic.')
def check(path):
    path=Path(path)
    if path.stat().st_size>150000: raise ValueError('Packet exceeds size limit.')
    p=json.loads(path.read_text(encoding='utf8'))
    if set(p)!={'schema','body_json','sha256'} or p['schema']!='cantos/dedicated-capacity-packet@0.1': raise ValueError('Unsupported packet.')
    if hashlib.sha256(p['body_json'].encode()).hexdigest()!=p['sha256']: raise ValueError('Checksum mismatch.')
    b=json.loads(p['body_json']); x=b['input']; r=b['result']; h=b['historical']; q=r['charge']
    if b['origin']!={'repo':'BigBirdReturns/cantos','commit':BASE,'engine_blob':ENGINE,'run3_blob':SOURCE}: raise ValueError('Unexpected pinned source identity.')
    if r['target_qualified'] is not False or r['basis']!='USER_ASSUMPTIONS' or r['status']!='SCENARIO_REQUIRES_TARGET_QUALIFICATION' or r['authority']!={'provision':False,'execute':False,'pay':False,'publish':False}: raise ValueError('Invalid qualification or authority claim.')
    for key in ('commitmentUSD','committedHours','productiveHours','gpus'):
        v=x[key]
        if isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or v<0: raise ValueError('Invalid numeric input '+key)
    if x['committedHours']<=0 or not 0<=x['productiveHours']<=x['committedHours'] or x['gpus']<1 or not float(x['gpus']).is_integer(): raise ValueError('Invalid hours or allocation.')
    extra=0; unknown=[]
    for key in COSTS:
        v=x['costs'][key]
        if v is None: unknown.append(key)
        elif isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or v<0: raise ValueError('Invalid cost '+key)
        else: extra+=v
    rate=x['acceptedPerProductiveHour']
    if rate is not None and (isinstance(rate,bool) or not isinstance(rate,(int,float)) or not math.isfinite(rate) or rate<0): raise ValueError('Invalid accepted rate.')
    accepted=None if rate is None else rate*x['productiveHours']; total=x['commitmentUSD']+extra
    expected={'gpuCharge':x['commitmentUSD'],'extraCharge':extra,'total':total,'billedHours':x['committedHours'],'hours':x['committedHours'],'allocationHourly':x['commitmentUSD']/x['committedHours'],'ratePerGPU':x['commitmentUSD']/x['committedHours']/x['gpus'],'gpus':x['gpus']}
    for k,v in expected.items(): equal(q[k],v,'charge.'+k)
    for k,v in {'known_cost_total':total,'modeled_accepted':accepted,'productive_hours':x['productiveHours'],'productive_share':x['productiveHours']/x['committedHours'],'cost_per_1000_accepted':None if not accepted else total/accepted*1000,'infrastructure_per_1000_accepted':None if not accepted else x['commitmentUSD']/accepted*1000}.items():equal(r[k],v,k)
    if r['unknown_costs']!=unknown: raise ValueError('Unknown-cost classification changed.')
    expected_scope='KNOWN_COST_SUBTOTAL_NOT_ALL_IN' if unknown else 'ALL_LISTED_COST_CATEGORIES_SUPPLIED_AS_ASSUMPTIONS'
    if r['cost_scope']!=expected_scope: raise ValueError('Invalid cost-scope claim.')
    if q['evidence']!='USER_SUPPLIED_SCENARIO_NOT_PROVIDER_QUOTE':raise ValueError('Scenario became a provider quote.')
    if h['basis']!='PUBLISHED_RUN3_SUMMARY' or h['source_blob']!=SOURCE or h['source_commit']!=BASE:raise ValueError('Historical source boundary changed.')
    equal(h['accepted'],4336,'historical accepted');equal(h['scheduled'],8622,'historical scheduled');equal(h['correct'],4371,'historical correct');equal(h['minutes'],64.7,'historical duration')
    historical_total=b['historical_rate']*64.7/60
    equal(h['quote']['total'],historical_total,'historical charge');equal(h['cost_per_1000_accepted'],historical_total/4336*1000,'historical cost per 1000')
    return {'status':'PASS','scope':'Independent arithmetic, unknown-cost and nonauthority checks; not complete native projection verification.','source_authenticity_verified':False,'target_performance_verified':False,'signature_verified':False}
if __name__=='__main__':
    try:
        if len(sys.argv)!=2:raise ValueError('Usage: python check_math.py decision.json')
        print(json.dumps(check(sys.argv[1]),indent=2))
    except (ValueError,KeyError,TypeError,OSError,OverflowError) as exc:
        print(json.dumps({'status':'FAIL','reason':str(exc)}));sys.exit(1)
