#!/usr/bin/env python3
"""Trimmed view of price_dispersion_result.json: drop provider 'together' (own-source rows $100/$200 per GPU-hr, 25-33x the
getdeploying listing for the same provider/SKU; treated as a unit artefact, flagged not corrected)."""
import json, sys, statistics as st
r = json.load(open(sys.argv[1]))
out = {}
for g, d in r['gpus'].items():
    for lab, key in (('all_shapes','providers_all'), ('gpu_count_1','providers_1gpu')):
        pm = {p: v for p, v in d[key].items() if p != 'together'}
        meds = sorted(v['median'] for v in pm.values())
        lo = min(pm, key=lambda p: pm[p]['median']); hi = max(pm, key=lambda p: pm[p]['median'])
        o = dict(n=len(meds), median=st.median(meds), min=meds[0], min_provider=lo, max=meds[-1], max_provider=hi, ratio=meds[-1]/meds[0],
                 p10=meds[int((len(meds)-1)*.1)], p90=meds[int((len(meds)-1)*.9)])
        o['ratio_p90_p10'] = o['p90']/o['p10']
        out[g+'/'+lab] = o
        print(g, lab, {k:(round(v,3) if isinstance(v,float) else v) for k,v in o.items()})
json.dump(out, open(sys.argv[2],'w'), indent=1)
