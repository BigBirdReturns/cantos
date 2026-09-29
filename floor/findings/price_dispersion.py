#!/usr/bin/env python3
"""July-2026 on-demand price dispersion from the OpenComputePrices lane rows. stdlib only, streams the file.
Usage: price_dispersion.py <prices.jsonl> <out.json>
Rows: price_type == on_demand, hourly_price_usd not null, snapshot_ts in 2026-07 (to 07-29, last snapshot).
provider 'do' is aliased to 'digitalocean' (as in hot-aisle/campaign/market/build_price_history.py)."""
import json, sys, hashlib, statistics as st, collections
src, dst = sys.argv[1], sys.argv[2]
GPUS = {'H100','H200','B200','MI300X'}
ALIAS = {'do':'digitalocean'}
prov = collections.defaultdict(list)          # (gpu, provider) -> prices
provsrc = collections.defaultdict(list)       # (gpu, provider, source)
prov1 = collections.defaultdict(list)         # gpu_count==1
provsrc1 = collections.defaultdict(list)
allrows = collections.defaultdict(list)       # gpu -> all prices (row-weighted)
allrows1 = collections.defaultdict(list)
h = hashlib.sha256(); n = 0; nj = 0
with open(src, 'rb') as f:
    for line in f:
        h.update(line); n += 1
        if b'"on_demand"' not in line or b'"snapshot_ts":"2026-07' not in line: continue
        r = json.loads(line)
        if r['gpu'] not in GPUS or r['price_type'] != 'on_demand' or r['hourly_price_usd'] is None: continue
        if not r['snapshot_ts'].startswith('2026-07'): continue
        nj += 1
        p = ALIAS.get(r['provider'], r['provider']); g = r['gpu']; x = r['hourly_price_usd']
        prov[(g,p)].append(x); provsrc[(g,p,r['source'])].append(x); allrows[g].append(x)
        if r['gpu_count'] == 1:
            prov1[(g,p)].append(x); provsrc1[(g,p,r['source'])].append(x); allrows1[g].append(x)
res = dict(input_sha256=h.hexdigest(), lines=n, july_ondemand_rows=nj, gpus={})
for g in sorted(GPUS):
    pm = {p: dict(median=st.median(v), min=min(v), max=max(v), n=len(v)) for (gg,p),v in prov.items() if gg==g}
    pm1 = {p: dict(median=st.median(v), min=min(v), max=max(v), n=len(v)) for (gg,p),v in prov1.items() if gg==g}
    def block(pm, rows):
        meds = sorted(v['median'] for v in pm.values())
        return dict(n_providers=len(pm), provider_median_of_medians=st.median(meds), min_provider_median=meds[0], max_provider_median=meds[-1],
                    ratio_max_min=meds[-1]/meds[0], p10=meds[int((len(meds)-1)*.1)], p90=meds[int((len(meds)-1)*.9)], ratio_p90_p10=meds[int((len(meds)-1)*.9)]/meds[int((len(meds)-1)*.1)],
                    row_median=st.median(rows), rows=len(rows), row_min=min(rows), row_max=max(rows),
                    cheapest=sorted(pm.items(), key=lambda kv: kv[1]['median'])[:3], dearest=sorted(pm.items(), key=lambda kv: -kv[1]['median'])[:3])
    res['gpus'][g] = dict(all_shapes=block(pm, allrows[g]), gpu_count_1=block(pm1, allrows1[g]) if pm1 else None, providers_all=pm, providers_1gpu=pm1)
# aggregator disagreement
dis = []
by = collections.defaultdict(dict)
for (g,p,s),v in provsrc1.items(): by[(g,p)][s] = dict(median=st.median(v), n=len(v), min=min(v), max=max(v))
for (g,p),d in by.items():
    if len(d) >= 2:
        meds = [x['median'] for x in d.values()]
        dis.append(dict(gpu=g, provider=p, sources=d, ratio=max(meds)/min(meds), lo=min(meds), hi=max(meds)))
dis.sort(key=lambda t: -t['ratio'])
res['aggregator_disagreement_1gpu'] = dis
json.dump(res, open(dst,'w'), indent=1)
print('lines', n, 'july on-demand rows', nj, 'sha', h.hexdigest())
