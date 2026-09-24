#!/usr/bin/env python3
"""Read native Run 3 evidence; preserve full-bill gaps. No jobs, grading or network.
This intake is deliberately not a prospective rating-outcomes packet.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

class IntakeError(ValueError):
    pass

def need(ok, message):
    if not ok: raise IntakeError(message)

def number(x, label):
    need(type(x) in (int, float) and math.isfinite(x) and x >= 0, label + ': nonnegative finite number required')
    return x

def sha(b):
    return hashlib.sha256(b).hexdigest()

def read_json(path):
    b = path.read_bytes()
    return json.loads(b), sha(b)

def inside(root, name):
    p = (root / name).resolve()
    need(p.is_relative_to(root.resolve()), 'Evidence path escapes declared root')
    return p

def percentile(values, q):
    if not values: return None
    a = sorted(values); p = (len(a)-1)*q; lo = math.floor(p); hi = math.ceil(p)
    return a[lo] + (a[hi]-a[lo])*(p-lo)

def source_run(root, spec):
    directory = inside(root, spec['directory'])
    ledger_path = inside(root, spec['ledger'])
    ledger, ledger_hash = read_json(ledger_path)
    need(ledger.get('schema') == 'second-run/run-ledger@1', 'Unsupported native ledger')
    detail, detail_hash = read_json(directory / 'detailed.json')
    grade, grade_hash = read_json(directory / 'grade/evaluation.json')
    need(detail.get('synthetic') is False and grade.get('synthetic') is False, 'Real intake refuses synthetic input')
    need(grade.get('schema') == 'hot-aisle/request-evaluation@1', 'Unsupported evaluator sidecar')
    need(grade.get('source_sha256') == detail_hash, 'Evaluator sidecar does not bind exact response data')
    mapping, mapping_hash = read_json(directory / 'grade/mapping.json')
    need(grade.get('mapping_sha256') == mapping_hash, 'Task mapping hash mismatch')
    need(set(grade.get('result_sha256', {})) == {'humaneval','mbpp'}, 'Both grader result commitments required')
    for suite, expected in grade['result_sha256'].items():
        need(suite in ('humaneval', 'mbpp'), 'Unknown evaluator suite')
        need(sha((directory / 'grade' / (suite+'_eval_results.json')).read_bytes()) == expected, 'Grader result hash mismatch')
    arrays = {k: detail.get(k) for k in ('errors','ttfts','latencies','queue_times')}
    passed = grade.get('passed'); need(isinstance(passed,list), 'Missing judgment vector')
    n = len(passed)
    need(all(isinstance(a,list) and len(a)==n for a in arrays.values()), 'Request-array length mismatch')
    need(all(type(x) is bool or x is None for x in passed), 'Judgments must be boolean or explicitly ungraded')
    rule = ledger['work']['acceptance_rule']; correct = completed = accepted = 0; ttfts=[]; e2es=[]
    need(rule.get('correctness') is True and rule.get('queue') is True, 'This adapter requires queue-inclusive correctness gates')
    need(ledger['work']['evaluator']['criterion_id'] == grade['criterion_id'], 'Acceptance criterion mismatch')
    for i, judgment in enumerate(passed):
        if arrays['errors'][i]: continue
        if arrays['ttfts'][i] is None or arrays['latencies'][i] is None: continue
        queue = number(arrays['queue_times'][i], 'queue seconds')
        first = 1000*(queue+number(arrays['ttfts'][i], 'TTFT seconds'))
        end = 1000*(queue+number(arrays['latencies'][i], 'latency seconds'))
        completed += 1; correct += judgment is True; ttfts.append(first); e2es.append(end)
        accepted += judgment is True and first <= rule['ttft_ms'] and end <= rule['e2e_ms']
    counts = {'attempted':n,'completed':completed,'correct':correct,'accepted':accepted}
    for k,v in counts.items(): need(type(ledger['work'].get(k)) is int and ledger['work'][k]==v, 'Native ledger disagrees with recomputed '+k)
    need(detail['completed']==completed, 'Completion total mismatch')
    need(ledger['work']['evaluator'].get('frozen') is True, 'Native evaluator freeze declaration missing')
    identity = ledger['identity']; money = ledger['money']
    need(spec.get('role') in ('scored_arm','unscored_smoke'), 'Explicit campaign role required')
    return {'run_id':identity['run_id'],'role':spec['role'],'provider':identity['provider'],
        'allocation_id':identity['seat_id'],'service_id':identity['sku'],'region':identity['region'],
        'gpus':identity['gpus'],'model':identity['model'],'runtime':identity['runtime'],
        'workload_id':identity['workload_id'],'counts':counts,'request_slots':n,
        'p95_ttft_including_queue_ms':percentile(ttfts,.95),
        'p99_ttft_including_queue_ms':percentile(ttfts,.99),
        'p95_e2e_including_queue_ms':percentile(e2es,.95),
        'acceptance_rule':rule,'evaluator_criterion':grade['criterion_id'],
        'clocks':ledger['clocks'],'native_money':money,
        'evidence':{'ledger_sha256':ledger_hash,'detailed_sha256':detail_hash,
            'evaluation_sha256':grade_hash,'mapping_sha256':mapping_hash,
            'ledger_path':spec['ledger'],'directory':spec['directory']},
        'evidence_scope':'Exact supplied files and judgment vector checked; outputs were not re-executed or independently graded.',
        'billing_status':'AWAITING_ALLOCATION_BILL','whole_bill_share_usd':None}

def amount(x, label):
    number(x,label); return Decimal(str(x))

def reconcile_bills(root, runs, bills):
    by_seat = {}; receipts = set(); billed_seats = set(); reports = []
    for r in runs: by_seat.setdefault(r['allocation_id'],[]).append(r)
    for bill in bills:
        need(bill.get('schema')=='secondrun.allocation-bill.v1', 'Unsupported allocation bill')
        seat = bill['allocation_id']; need(seat in by_seat, 'Bill has unknown allocation')
        need(seat not in billed_seats, 'Duplicate allocation bill'); billed_seats.add(seat)
        need(bill.get('currency')=='USD', 'USD bill required; no silent FX conversion')
        need(bill.get('complete_run_roster') is True, 'Complete allocation run roster must be declared')
        receipt = inside(root,bill['receipt_path']); actual = sha(receipt.read_bytes())
        need(actual==bill['receipt_sha256'], 'Invoice receipt hash mismatch')
        need(actual not in receipts, 'Invoice reused; provide one allocation-scoped receipt or a reconciled parent-invoice split')
        receipts.add(actual)
        gross = amount(bill['gross_charge_usd'],'gross charge'); credit = amount(bill['credits_usd'],'credits')
        cash = amount(bill['cash_charge_usd'],'cash charge')
        need(credit<=gross and gross-credit==cash, 'Gross, credits and cash do not reconcile')
        lines = bill.get('line_items'); need(isinstance(lines,list) and lines,'Complete bill line items required')
        need(sum((amount(x['amount_usd'],'line item') for x in lines),Decimal(0))==gross,'Bill line items do not sum to gross charge')
        allocations = bill.get('run_shares'); need(isinstance(allocations,dict),'Explicit per-run cost shares required')
        need(set(allocations)=={r['run_id'] for r in by_seat[seat]},'Bill roster differs from supplied seat runs')
        shares = {k:amount(v,'run share') for k,v in allocations.items()}
        need(sum(shares.values(),Decimal(0))==1, 'Run shares must sum exactly to one; no duplicate full-seat billing')
        need(isinstance(bill.get('allocation_basis'),str) and bill['allocation_basis'].strip(),'Cost allocation basis required')
        for r in by_seat[seat]:
            charge = gross*shares[r['run_id']]; r.update(billing_status='RECONCILED_SUPPLIED_BILL',whole_bill_share_usd=float(charge))
            r['credits_share_usd']=float(credit*shares[r['run_id']]); r['cash_share_usd']=float(cash*shares[r['run_id']])
            r['whole_bill_usd_per_1000_accepted']=float(charge*1000/r['counts']['accepted']) if r['counts']['accepted'] else None
        reports.append({'allocation_id':seat,'gross_charge_usd':float(gross),'credits_usd':float(credit),'cash_charge_usd':float(cash),'receipt_sha256':actual,'allocation_basis':bill['allocation_basis']})
    return reports

def build(root, specification, bills=None):
    need(specification.get('schema')=='secondrun.campaign-intake-spec.v1','Unsupported intake specification')
    runs=[source_run(root,s) for s in specification['runs']]
    need(runs and len({r['run_id'] for r in runs})==len(runs),'Duplicate or empty run set')
    invoice_reports=reconcile_bills(root,runs,bills or [])
    scored=[r for r in runs if r['role']=='scored_arm']
    providers=sorted({r['provider'] for r in scored}); allocations={r['allocation_id'] for r in scored}
    reasons=['No ClusterMAX-specific frozen prediction plan or medal binding supplied.',
             'Native campaign acceptance rules are preserved, not retroactively changed to the challenge endpoint.',
             'These one-GPU services do not establish a managed-cluster comparison.']
    if len(providers)<8: reasons.append('Provider coverage below the eight-provider study floor.')
    if any(r['billing_status']!='RECONCILED_SUPPLIED_BILL' for r in runs): reasons.append('Whole-allocation invoice reconciliation is incomplete; no modeled price substituted.')
    return {'schema':'secondrun.campaign-intake.v1','generated_at':datetime.now(timezone.utc).isoformat(),
        'status':'STAGED_REAL_EVIDENCE','challenge_status':'HOLD','challenge_hold_reasons':reasons,
        'source_commit':specification.get('source_commit'),'scored_runs':len(scored),'providers':providers,
        'distinct_scored_allocations':len(allocations),'runs':runs,'allocation_bills':invoice_reports,
        'unit_boundary':'One run remains one run. Requests and time buckets are not independent trial or provider counts.',
        'cost_boundary':'Realized whole-bill cost is separate from list-price modeled cost. v1.4 challenge total_cost_usd is not silently redefined.',
        'evidence_boundary':'Receipt hashes establish exact supplied bytes, not independent invoice authenticity or complete upstream history.'}

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--root',type=Path,required=True); ap.add_argument('--spec',type=Path,required=True); ap.add_argument('--bills',type=Path); ap.add_argument('--output',type=Path,required=True); args=ap.parse_args()
    try:
        spec,_=read_json(args.spec); bills=read_json(args.bills)[0]['bills'] if args.bills else []
        result=build(args.root,spec,bills); rendered=json.dumps(result,indent=2,allow_nan=False)+'\n'; args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x',encoding='utf-8',newline='\n') as f: f.write(rendered)
        print(json.dumps({k:result[k] for k in ('status','challenge_status','scored_runs','providers','challenge_hold_reasons')},indent=2)); return 0
    except (IntakeError,OSError,KeyError,ValueError,TypeError) as e: print('INTAKE_HOLD: '+str(e)); return 2

if __name__=='__main__': raise SystemExit(main())
