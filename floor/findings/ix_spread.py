#!/usr/bin/env python3
"""InferenceX cross-framework spread from ix_extract.py output. stdlib only.
Key = (hardware, model, scenario, isl, osl, dataset, concurrency, precision). Per framework take best (max) and median
output_throughput_per_gpu across configs (tp/ep/disagg/spec variants) reported for that key.
Usage: ix_spread.py <ix_rows.jsonl> <outdir>"""
import json, sys, statistics as st, collections, os
rows = [json.loads(l) for l in open(sys.argv[1], encoding='utf-8')]
out = sys.argv[2]
def key(r): return (r['hw'], r['model'], r['scen'], r['isl'], r['osl'], r['dataset'] if r['scen']!='fixed-sequence' else None, r['conc'], (r['prec'] or '').lower())
g = collections.defaultdict(lambda: collections.defaultdict(list))
for r in rows:
    v = r['m'].get('output_throughput_per_gpu')
    g[key(r)][r['fw']].append(r)
res = []
for k, fws in g.items():
    if len(fws) < 2: continue
    per = {}
    for fw, rs in fws.items():
        vals = [x['m']['output_throughput_per_gpu'] for x in rs if x['m'].get('output_throughput_per_gpu') not in (None, 0)]
        ok = sum(x['ok'] for x in rs if x['ok'] is not None and x['tot']); tot = sum(x['tot'] for x in rs if x['ok'] is not None and x['tot'])
        err = sum(x['err_drop'] for x in rs if x['err_drop'] is not None and x['tot']); tot2 = sum(x['tot'] for x in rs if x['err_drop'] is not None and x['tot'])
        per[fw] = dict(n=len(rs), n_tput=len(vals), best=max(vals) if vals else None, med=st.median(vals) if vals else None, ok=ok, tot=tot, err=err, tot_err=tot2)
    res.append((k, per))
print('keys with >=2 frameworks (any rows):', len(res), 'of', len(g))
tp = []
for k, per in res:
    b = {fw: p['best'] for fw, p in per.items() if p['best']}
    if len(b) >= 2:
        hi = max(b, key=b.get); lo = min(b, key=b.get)
        tp.append((b[hi]/b[lo], k, hi, lo, b, per))
print('keys with >=2 frameworks reporting output tput/gpu:', len(tp))
ratios = sorted(t[0] for t in tp)
def q(p): return ratios[int((len(ratios)-1)*p)]
print('best-vs-best ratio min/p25/median/p75/p90/max:', [round(x,3) for x in (ratios[0], q(.25), q(.5), q(.75), q(.9), ratios[-1])])
print('share of keys with ratio>=1.5: %.3f  >=2: %.3f  >=3: %.3f' % tuple(sum(1 for x in ratios if x>=t)/len(ratios) for t in (1.5,2,3)))
# by hardware
byhw = collections.defaultdict(list)
for t in tp: byhw[t[1][0]].append(t[0])
for hw, xs in sorted(byhw.items(), key=lambda kv:-len(kv[1])):
    xs.sort(); print(hw, len(xs), 'median %.2f' % st.median(xs), 'p90 %.2f' % xs[int((len(xs)-1)*.9)], 'max %.2f' % xs[-1])
# fixed-sequence vs agentic
for sc in ('fixed-sequence','agentic-coding'):
    xs = sorted(t[0] for t in tp if t[1][2]==sc)
    if xs: print(sc, len(xs), 'median %.2f' % st.median(xs), 'p90 %.2f' % xs[int((len(xs)-1)*.9)], 'max %.2f' % xs[-1])
# framework pair frequency
pairs = collections.Counter()
for t in tp: pairs[(t[2], t[3])] += 1
print('top (best_fw, worst_fw) pairs:', pairs.most_common(10))
# top 15 spreads
tp.sort(key=lambda t: -t[0])
for t in tp[:15]: print(round(t[0],2), t[1], t[2], '>', t[3], {k: round(v,1) for k,v in t[4].items()})
# MI300X / H100 / H200 / B200 focus
for hw in ('MI300X','H100','H200','B200'):
    sub=[t for t in tp if t[1][0]==hw]
    print('==', hw, len(sub))
    for t in sorted(sub, key=lambda t:-t[0])[:6]: print(' ', round(t[0],2), t[1], t[2], '>', t[3], {k: round(v,1) for k,v in t[4].items()})
# success-rate spread (agentic), both definitions
sr = []
for k, per in res:
    if k[2] != 'agentic-coding': continue
    a = {fw: p['ok']/p['tot'] for fw, p in per.items() if p['tot']>0 and p['ok']>0}
    e = {fw: 1-p['err']/p['tot_err'] for fw, p in per.items() if p['tot_err']>0}
    if len(a)>=2: sr.append((max(a.values())-min(a.values()), k, a, e))
print('agentic keys w/ >=2 frameworks reporting success (profiled/total incl warmup):', len(sr))
xs = sorted(s[0] for s in sr)
if xs: print('spread pp min/median/p90/max:', [round(x*100,1) for x in (xs[0], st.median(xs), xs[int((len(xs)-1)*.9)], xs[-1])])
# error-only rate spread
er=[]
for s in sr:
    e=s[3]
    if len(e)>=2: er.append(max(e.values())-min(e.values()))
er.sort()
if er: print('error-only (records_error_dropped) success spread pp: n=%d median %.2f p90 %.2f max %.2f' % (len(er), st.median(er)*100, er[int((len(er)-1)*.9)]*100, er[-1]*100))
json.dump([dict(ratio=t[0], key=t[1], best_fw=t[2], worst_fw=t[3], best_per_fw=t[4]) for t in tp], open(os.path.join(out,'_ix_spread_tput.json'),'w'), indent=0)
json.dump([dict(spread=s[0], key=s[1], ok_rate=s[2], err_rate=s[3]) for s in sr], open(os.path.join(out,'_ix_spread_success.json'),'w'), indent=0)
