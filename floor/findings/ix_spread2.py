#!/usr/bin/env python3
"""Restricted variants of the InferenceX cross-framework spread. Reads ix_extract.py output.
best row per (key, framework) = max output_throughput_per_gpu. Variants:
 all            : every key with >=2 frameworks reporting the metric
 clean          : both best rows have records_error_dropped/total <= 0.05 (or fixed-sequence with no error info) and value > 0
 clean_sameweek : clean AND best rows created within 7 days of each other
 like_for_like  : clean_sameweek AND same tp,ep,gpus,disagg,spec on both rows (framework is the only difference)
Ratio = best framework / worst framework, over the pair (max, min) of framework-bests in the key."""
import json, sys, statistics as st, collections, os, datetime
rows = [json.loads(l) for l in open(sys.argv[1], encoding='utf-8')]
out = sys.argv[2]
def key(r): return (r['hw'], r['model'], r['scen'], r['isl'], r['osl'], r['dataset'] if r['scen']!='fixed-sequence' else None, r['conc'], (r['prec'] or '').lower())
def dt(s):
    try: return datetime.datetime.fromisoformat(s.replace('Z','+00:00'))
    except Exception: return None
g = collections.defaultdict(lambda: collections.defaultdict(list))
for r in rows:
    if r['m'].get('output_throughput_per_gpu'): g[key(r)][r['fw']].append(r)
def errfrac(r):
    if r['tot'] and r['err_drop'] is not None: return r['err_drop']/r['tot']
    return None
def summarize(name, lst):
    if not lst: print(name, 0); return None
    xs = sorted(t['ratio'] for t in lst)
    q = lambda p: xs[int((len(xs)-1)*p)]
    d = dict(variant=name, n_keys=len(xs), median=st.median(xs), p25=q(.25), p75=q(.75), p90=q(.9), max=xs[-1],
             share_ge_1_5=sum(x>=1.5 for x in xs)/len(xs), share_ge_2=sum(x>=2 for x in xs)/len(xs), share_ge_3=sum(x>=3 for x in xs)/len(xs))
    print(json.dumps({k:(round(v,3) if isinstance(v,float) else v) for k,v in d.items()}))
    return d
allv=[]
for k, fws in g.items():
    if len(fws) < 2: continue
    best = {fw: max(rs, key=lambda x: x['m']['output_throughput_per_gpu']) for fw, rs in fws.items()}
    hi = max(best, key=lambda f: best[f]['m']['output_throughput_per_gpu']); lo = min(best, key=lambda f: best[f]['m']['output_throughput_per_gpu'])
    a, b = best[hi], best[lo]
    ratio = a['m']['output_throughput_per_gpu']/b['m']['output_throughput_per_gpu']
    da, db = dt(a['created'] or ''), dt(b['created'] or '')
    days = abs((da-db).total_seconds())/86400 if da and db else None
    clean = all((errfrac(x) is None or errfrac(x) <= 0.05) for x in (a,b))
    same = all(a.get(f)==b.get(f) for f in ('tp','ep','gpus','disagg','spec'))
    allv.append(dict(ratio=ratio, key=k, hi=hi, lo=lo, hi_v=a['m']['output_throughput_per_gpu'], lo_v=b['m']['output_throughput_per_gpu'],
        days=days, clean=clean, same=same, hi_row=(a['artifact'],a['row']), lo_row=(b['artifact'],b['row']),
        hi_cfg=(a['tp'],a['ep'],a['gpus'],a['disagg'],a['spec']), lo_cfg=(b['tp'],b['ep'],b['gpus'],b['disagg'],b['spec']),
        hi_err=errfrac(a), lo_err=errfrac(b), n_fw=len(best)))
res = {}
res['all'] = summarize('all', allv)
res['clean'] = summarize('clean', [t for t in allv if t['clean']])
res['clean_sameweek'] = summarize('clean_sameweek', [t for t in allv if t['clean'] and t['days'] is not None and t['days'] <= 7])
res['like_for_like'] = summarize('like_for_like', [t for t in allv if t['clean'] and t['days'] is not None and t['days'] <= 7 and t['same']])
# per-SKU (clean_sameweek)
sku = {}
for hw in ('H100','H200','B200','MI300X','MI355X','B300','GB200'):
    sub = [t for t in allv if t['key'][0]==hw]
    subc = [t for t in sub if t['clean'] and t['days'] is not None and t['days']<=7]
    print(hw, 'all n=%d median=%.2f max=%.2f' % (len(sub), st.median([t['ratio'] for t in sub]) if sub else 0, max([t['ratio'] for t in sub]) if sub else 0),
          '| clean_sameweek n=%d median=%.2f max=%.2f' % (len(subc), st.median([t['ratio'] for t in subc]) if subc else 0, max([t['ratio'] for t in subc]) if subc else 0))
    sku[hw]=dict(all_n=len(sub), all_median=st.median([t['ratio'] for t in sub]) if sub else None, all_max=max([t['ratio'] for t in sub]) if sub else None,
                 cs_n=len(subc), cs_median=st.median([t['ratio'] for t in subc]) if subc else None, cs_max=max([t['ratio'] for t in subc]) if subc else None)
print('--- top clean_sameweek')
cs = sorted([t for t in allv if t['clean'] and t['days'] is not None and t['days']<=7], key=lambda t:-t['ratio'])
for t in cs[:12]:
    print(round(t['ratio'],2), t['key'], t['hi'], round(t['hi_v'],1), t['hi_cfg'], '>', t['lo'], round(t['lo_v'],1), t['lo_cfg'], 'days', round(t['days'],1), t['hi_row'], t['lo_row'])
print('--- top like_for_like')
lf = sorted([t for t in cs if t['same']], key=lambda t:-t['ratio'])
for t in lf[:10]:
    print(round(t['ratio'],2), t['key'], t['hi'], round(t['hi_v'],1), '>', t['lo'], round(t['lo_v'],1), t['hi_cfg'], 'days', round(t['days'],1), t['hi_row'], t['lo_row'])
json.dump(dict(summary=res, sku=sku, top_clean_sameweek=cs[:25], top_like_for_like=lf[:25], all_n=len(allv)), open(os.path.join(out,'ix_spread_result.json'),'w'), indent=1, default=str)
