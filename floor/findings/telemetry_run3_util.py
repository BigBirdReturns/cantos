#!/usr/bin/env python3
"""Run 3 server-side utilisation from serve.log 'loggers.py' ticks: generation tokens/s, running, waiting, KV%. stdlib only."""
import re, os, json, statistics as st
R = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'hot-aisle', 'campaign', 'results'))
rx = re.compile(r'Avg prompt throughput: ([\d.]+) tokens/s, Avg generation throughput: ([\d.]+) tokens/s, Running: (\d+) reqs, Waiting: (\d+) reqs, GPU KV cache usage: ([\d.]+)%')
out = {}
for a in ('run3-scored-a-t0', 'run3-scored-a-t1', 'run3-scored-n-t0'):
    T = [tuple(map(float, m.groups())) for m in rx.finditer(open(os.path.join(R, a, 'serve.log'), encoding='utf-8', errors='replace').read())]
    g = sorted(t[1] for t in T); ru = [t[2] for t in T]; wa = [t[3] for t in T]; kv = [t[4] for t in T]
    d = dict(ticks=len(T), gen_tok_s_max=g[-1], gen_tok_s_p95=g[int(.95*(len(g)-1))], gen_tok_s_median=st.median(g), running_max=max(ru), waiting_max=max(wa), waiting_ticks_gt0=sum(1 for w in wa if w > 0), kv_max_pct=max(kv))
    out[a] = d; print(a, d)
json.dump(out, open(os.path.join(os.environ.get('WORK', '.'), '_run3_util.json'), 'w'), indent=1)
