#!/usr/bin/env python3
"""Hot Aisle / DigitalOcean MI300X listing history from the OpenComputePrices lane rows (stream). stdlib only.
Prints per (provider, gpu_count, price_type, price) first/last snapshot day and row counts. Usage: ha_price_change.py <prices.jsonl> <out.json>"""
import json, sys, collections
src, dst = sys.argv[1], sys.argv[2]
g = {}
with open(src, 'rb') as f:
    for line in f:
        if b'"MI300X"' not in line: continue
        if b'hot_aisle' not in line and b'"digitalocean"' not in line and b'"do"' not in line: continue
        r = json.loads(line)
        if r['gpu'] != 'MI300X' or r['provider'] not in ('hot_aisle', 'digitalocean', 'do'): continue
        k = (r['provider'], r['source'], r['gpu_count'], r['price_type'], r['hourly_price_usd'])
        d = r['snapshot_ts'][:10]
        v = g.setdefault(k, [d, d, 0, set()]); v[0] = min(v[0], d); v[1] = max(v[1], d); v[2] += 1; v[3].add(d)
out = []
for k, v in sorted(g.items(), key=lambda kv: (kv[0][0], str(kv[0][1]), kv[0][2], kv[0][3], kv[0][4] or 0)):
    print(k, 'first', v[0], 'last', v[1], 'rows', v[2], 'days', len(v[3]))
    out.append(dict(provider=k[0], source=k[1], gpu_count=k[2], price_type=k[3], price=k[4], first=v[0], last=v[1], rows=v[2], days=len(v[3])))
json.dump(out, open(dst, 'w'), indent=1)
