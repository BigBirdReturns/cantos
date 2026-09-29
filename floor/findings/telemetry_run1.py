#!/usr/bin/env python3
"""Run 1 per-cell facts (3 repeats each) for both arms, incl. derived per-request E2E = ttft + sum(itl). stdlib only."""
import json, os, statistics as st, hashlib
R = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'hot-aisle', 'campaign', 'results'))
out = {}
for arm in ('hotaisle-mi300x', 'do-h100'):
    print(arm)
    for c in ('c1', 'c8', 'c32', 'c64'):
        cells = [json.load(open(os.path.join(R, arm, 'cell-%s-r%d.json' % (c, r)))) for r in range(3)]
        d = {}
        for k in ('p50_ttft_ms', 'p95_ttft_ms', 'p99_ttft_ms', 'p95_e2el_ms', 'request_throughput', 'output_throughput'):
            d[k] = [x[k] for x in cells]
        e2e = []
        over = 0
        for x in cells:
            for t, i in zip(x['ttfts'], x['itls']):
                v = (t + sum(i)) * (1 if False else 1)
                e2e.append(v)
                over += (t > 1.0)
        d['derived_e2e_max_s'] = max(e2e); d['derived_e2e_p95_s'] = sorted(e2e)[int(0.95 * (len(e2e) - 1))]
        d['ttft_gt_1s'] = over; d['n'] = len(e2e); d['has_latencies_key'] = all('latencies' in x for x in cells)
        out['%s/%s' % (arm, c)] = d
        print(' ', c, 'ttft p50 %s p95 %s p99 %s' % tuple('/'.join('%.0f' % v for v in d[k]) for k in ('p50_ttft_ms', 'p95_ttft_ms', 'p99_ttft_ms')),
              '| p95_e2el(field) %s ms' % '/'.join('%.0f' % v for v in d['p95_e2el_ms']), '| derived e2e max %.3f s p95 %.3f s' % (d['derived_e2e_max_s'], d['derived_e2e_p95_s']),
              '| ttft>1s %d/%d' % (over, len(e2e)), '| latencies key', d['has_latencies_key'], '| req/s %s' % '/'.join('%.3f' % v for v in d['request_throughput']))
json.dump(out, open(os.path.join(os.environ.get('WORK', '.'), '_run1_cells.json'), 'w'), indent=1)
