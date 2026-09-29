#!/usr/bin/env python3
"""Build data/price-history/, the listed-availability rows and market stats from the
OpenComputePrices lane (read-only input). Standard library only.
  python build_price_history.py
Writes: ../../data/price-history/<provider>/<date>.json + INDEX.json,
        market-stats.json, availability-append.jsonl (appended to the ledger by a separate step).
"""
import json, os, re, sys, hashlib, statistics, collections

LANE = 'D:/Projects/Organs/AXM/axm-tools/sessions/public-tail-20260929/lanes/opencomputeprices'
ROWS = LANE + '/rows/prices.jsonl'
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, '../../data/price-history'))
ALIAS = {'do': 'digitalocean'}   # older DigitalOcean id in the series (2025-09-02..2026-01-13)
PROVIDERS = ['hot_aisle', 'nebius', 'digitalocean', 'runpod', 'lambda', 'crusoe', 'tensorwave',
             'vultr', 'hyperstack', 'verda', 'datacrunch', 'coreweave']
NAMES = {'hot_aisle': 'Hot Aisle', 'nebius': 'Nebius', 'digitalocean': 'DigitalOcean', 'runpod': 'RunPod',
         'lambda': 'Lambda', 'crusoe': 'Crusoe', 'vultr': 'Vultr', 'hyperstack': 'Hyperstack',
         'verda': 'Verda (DataCrunch)', 'coreweave': 'CoreWeave', 'tensorwave': 'TensorWave', 'datacrunch': 'DataCrunch'}
RELEASE = {'repo': 'github.com/thatkavish/OpenComputePrices', 'license': 'MIT', 'release_tag': 'latest-data',
           'release_title': 'GPU Pricing Data - 2026-07-29 14:36 UTC', 'release_updated': '2026-07-29',
           'retrieved_utc': '2026-09-29'}
LANE_REL = 'sessions/public-tail-20260929/lanes/opencomputeprices/rows/prices.jsonl'
GPUS = ['MI300X', 'H100', 'H200', 'B200']


def clean(s):
    s = s or ''
    if '{ const tooltip' in s:
        s = s.split(' {')[0] + ' ' + s.split('theoreticalLeft ')[-1]
    return re.sub(r'\s+', ' ', s).strip()


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


def main():
    src_sha = sha256_file(ROWS)
    prod = {}
    avail = {}
    monthly = collections.defaultdict(list)
    latest_day = collections.defaultdict(dict)
    srcs = collections.defaultdict(dict)
    tsseen = collections.defaultdict(set)
    n = 0
    with open(ROWS, encoding='utf-8') as f:
        for line in f:
            n += 1
            r = json.loads(line)
            p = ALIAS.get(r['provider'], r['provider'])
            ts = r['snapshot_ts']
            day = ts[:10]
            price = r['hourly_price_usd']
            if r['price_type'] == 'on_demand' and price is not None:
                monthly[(day[:7], r['gpu'], p)].append(price)
                if day == '2026-07-29':
                    latest_day[r['gpu']].setdefault(p, {}).setdefault(r['gpu_count'], []).append(price)
            if p not in PROVIDERS:
                continue
            srcs[(p, day)][r['source_file']] = r['provenance']['sha256']
            tsseen[(p, day)].add(ts)
            key = (r['gpu'], r['variant'], r['gpu_count'], r['region'], r['price_type'], r['commitment_period'],
                   clean(r['instance_type']), r['source'])
            k = (p, day, key)
            d = prod.get(k)
            if d is None:
                prod[k] = {'ts': ts, 'price': price, 'inst': r['instance_hourly_usd'], 'av': r['available'],
                           'min': price, 'max': price, 'tss': {ts}}
            else:
                d['tss'].add(ts)
                if price is not None:
                    d['min'] = price if d['min'] is None else min(d['min'], price)
                    d['max'] = price if d['max'] is None else max(d['max'], price)
                if ts >= d['ts']:
                    d['ts'], d['price'], d['inst'], d['av'] = ts, price, r['instance_hourly_usd'], r['available']
            if r['price_type'] == 'on_demand' and r['available'] in ('True', 'False'):
                ak = (p, day, r['gpu'], r['gpu_count'], r['region'])
                a = avail.get(ak)
                if a is None:
                    avail[ak] = a = {'ts': ts, 'T': set(), 'F': set(), 'n': 0, 'src': set()}
                if ts > a['ts']:
                    a['ts'] = ts
                a['n'] += 1
                a['src'].add(r['source'])
                a['T' if r['available'] == 'True' else 'F'].add(ts)
    print('rows read', n, file=sys.stderr)

    by_pd = collections.defaultdict(list)
    for (p, day, key), d in prod.items():
        by_pd[(p, day)].append((key, d))
    os.makedirs(OUT, exist_ok=True)
    index = {}
    for (p, day), items in sorted(by_pd.items()):
        items.sort(key=lambda kd: tuple('' if x is None else str(x) for x in kd[0]))
        head = {
            'schema': 'second-run/price-snapshot@1', 'reviewed_on': day, 'currency': 'USD',
            'generated_from': {'path': LANE_REL, 'sha256': src_sha, 'release': RELEASE},
            'source_files': [{'source_file': s, 'sha256': h} for s, h in sorted(srcs[(p, day)].items())],
            'provider_id': p, 'provider': NAMES[p],
            'snapshot_ts': sorted(tsseen[(p, day)]),
            'price_basis': "hourly_price_usd is per GPU-hour; each product is the latest snapshot of the day "
                           "(day_min/day_max across the day's snapshots). Public third-party series, not a provider quote; never interpolated.",
        }
        if p == 'hot_aisle':
            od = [(k, d) for k, d in items if k[4] == 'on_demand' and k[0] == 'MI300X']
            vm = [(k[2], d['price']) for k, d in od if k[2] in (1, 2, 4)]
            bm_od = [(k[2], d['price']) for k, d in od if k[2] == 8]
            bm_res = [(k[2], d['price']) for k, d in items if k[4] == 'reserved' and k[0] == 'MI300X' and k[2] == 8]
            prices = sorted({x[1] for x in vm})
            head['hot_aisle'] = {
                'vm_gpu_hour': (prices[-1] if prices else None),
                'vm_gpu_hour_all_values_seen': prices,
                'vm_gpu_counts': sorted({x[0] for x in vm}),
                'bare_metal_gpu_hour': (bm_res[0][1] if bm_res else (bm_od[0][1] if bm_od else None)),
                'bare_metal_gpu_hour_basis': ('reserved 8x' if bm_res else ('on_demand 8x' if bm_od else None)),
                'bare_metal_gpu_count': 8 if (bm_res or bm_od) else None,
                'source': 'opencomputeprices getdeploying feed for hot_aisle',
                'note': 'vm_gpu_hour is the highest VM value listed that day; all values in vm_gpu_hour_all_values_seen.',
            }
        prods = []
        for key, d in items:
            g, v, c, reg, pt, cp, it, s = key
            o = {'gpu': g, 'variant': v, 'gpu_count': c, 'region': reg, 'price_type': pt}
            if cp:
                o['commitment_period'] = cp
            o.update({'instance_type': it, 'source': s, 'hourly_price_usd': d['price'], 'instance_hourly_usd': d['inst'],
                      'available': d['av'], 'snapshot_ts': d['ts'], 'day_min': d['min'], 'day_max': d['max'],
                      'snapshots': len(d['tss'])})
            prods.append(o)
        pdir = os.path.join(OUT, p)
        os.makedirs(pdir, exist_ok=True)
        fn = os.path.join(pdir, day + '.json')
        with open(fn, 'w', encoding='utf-8', newline='\n') as f:
            body = json.dumps(head, indent=2)[:-2]
            f.write(body + ',\n  "products": [\n' + ',\n'.join('    ' + json.dumps(x, separators=(',', ':')) for x in prods) + '\n  ]\n}\n')
        index.setdefault(p, []).append({'date': day, 'products': len(prods), 'snapshots': len(tsseen[(p, day)]),
                                        'sha256': sha256_file(fn)})
    idx = {'schema': 'second-run/price-history-index@1', 'generated_on': '2026-09-29', 'currency': 'USD',
           'generated_from': {'path': LANE_REL, 'sha256': src_sha, 'release': RELEASE},
           'series_range': {'first': '2024-01-01', 'last': '2026-07-29'},
           'rule': 'one file per provider per snapshot day present in the public series; a day the series lacks has no file (no interpolation)',
           'not_in_series': [p for p in PROVIDERS if p not in index],
           'aliases': {'do': 'digitalocean (series id used 2025-09-02..2026-01-13, merged)'},
           'providers': {p: {'name': NAMES[p], 'first': v[0]['date'], 'last': v[-1]['date'], 'days': len(v), 'files': v}
                         for p, v in sorted(index.items())}}
    with open(os.path.join(OUT, 'INDEX.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(idx, f, indent=1)
        f.write('\n')

    prov_ledger = {'hot_aisle': 'hotaisle'}
    cnt = 0
    with open(os.path.join(HERE, 'availability-append.jsonl'), 'w', encoding='utf-8', newline='\n') as f:
        for (p, day, gpu, cnt_g, reg), a in sorted(avail.items()):
            latest_true = a['ts'] in a['T']
            outcome = 'available' if latest_true else 'out_of_stock'
            field = 'available=True' if latest_true else 'available=False'
            row = {'ts': a['ts'], 'provider': prov_ledger.get(p, p), 'region': reg, 'sku': gpu, 'gpus': cnt_g,
                   'method': 'api', 'layer': 'listed', 'outcome': outcome, 'provisioned': False, 'synthetic': False,
                   'reason': 'opencomputeprices:' + field,
                   'note': ('provenance: OpenComputePrices release latest-data (prices.jsonl sha256 %s), day %s, %d on-demand rows over %d snapshots, feeds %s; '
                            'third-party listing flag, not a provisioning attempt; sku is the GPU family, not a provider SKU id; outcome from the newest snapshot of the day')
                           % (src_sha[:16], day, a['n'], len(a['T'] | a['F']), ','.join(sorted(a['src'])))}
            f.write(json.dumps(row, separators=(',', ':')) + '\n')
            cnt += 1
    print('availability rows', cnt, file=sys.stderr)

    med = statistics.median
    stats = {'src_sha256': src_sha, 'monthly': {}, 'latest_day': {}}
    for m in ('2026-04', '2026-05', '2026-06', '2026-07'):
        for g in GPUS:
            pm = {p: med(v) for (mm, gg, p), v in monthly.items() if mm == m and gg == g}
            stats['monthly'].setdefault(m, {})[g] = {
                'n_providers': len(pm), 'median_of_provider_medians': (med(list(pm.values())) if pm else None),
                'provider_medians': dict(sorted(pm.items()))}
    for g in GPUS:
        stats['latest_day'][g] = {p: {str(c): med(v) for c, v in cs.items()} for p, cs in sorted(latest_day[g].items())}
    with open(os.path.join(HERE, 'market-stats.json'), 'w') as f:
        json.dump(stats, f, indent=1)


if __name__ == '__main__':
    main()
