#!/usr/bin/env python3
"""Where Run 3 decode tokens went: by finish_reason and by graded outcome. stdlib only."""
import json, os
R = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'hot-aisle', 'campaign', 'results'))
out = {}
for a in ('run3-scored-a-t0', 'run3-scored-a-t1', 'run3-scored-n-t0'):
    rs = [json.loads(l) for l in open(os.path.join(R, a, 'replay', 'requests.jsonl'), encoding='utf-8')]
    ev = json.load(open(os.path.join(R, a, 'grade', 'evaluation.json')))['passed']
    tk = [r['output_tokens'] or 0 for r in rs]; tot = sum(tk)
    fail = sum(t for t, p in zip(tk, ev) if not p)
    L = [i for i, r in enumerate(rs) if r['finish_reason'] == 'length']
    Lf = [i for i in L if not ev[i]]
    d = dict(total_out_tokens=tot, tokens_on_failed_requests=fail, share_failed=fail/tot,
             length_requests=len(L), length_share_of_requests=len(L)/len(rs), length_tokens=sum(tk[i] for i in L), length_share_of_tokens=sum(tk[i] for i in L)/tot,
             length_pass=sum(ev[i] for i in L), length_pass_rate=sum(ev[i] for i in L)/len(L), length_failed_tokens=sum(tk[i] for i in Lf), length_failed_share_of_tokens=sum(tk[i] for i in Lf)/tot,
             stop_pass_rate=sum(ev[i] for i, r in enumerate(rs) if r['finish_reason'] == 'stop')/sum(1 for r in rs if r['finish_reason'] == 'stop'))
    out[a] = d
    print(a, json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}))
json.dump(out, open(os.path.join(os.environ.get('WORK', '.'), '_run3_tokens.json'), 'w'), indent=1)
