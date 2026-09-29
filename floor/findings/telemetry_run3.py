#!/usr/bin/env python3
"""Run 3 per-arm facts from retained replay/requests.jsonl + grade/evaluation.json + serve.log. stdlib only."""
import json, os, re, hashlib, statistics, sys
R = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','hot-aisle','campaign','results'))
def sha(p): return hashlib.sha256(open(p,'rb').read()).hexdigest()
def pct(xs,p):
    xs=sorted(xs); 
    if not xs: return None
    k=(len(xs)-1)*p/100; f=int(k); c=min(f+1,len(xs)-1); return xs[f]+(xs[c]-xs[f])*(k-f)
out={}
for arm in ('run3-scored-a-t0','run3-scored-a-t1','run3-scored-n-t0','run3-smoke-a-t0'):
    d=os.path.join(R,arm)
    if not os.path.exists(os.path.join(d,'replay','requests.jsonl')): continue
    rows=[json.loads(l) for l in open(os.path.join(d,'replay','requests.jsonl'),encoding='utf-8')]
    ev=None
    if os.path.exists(os.path.join(d,'grade','evaluation.json')):
        ev=json.load(open(os.path.join(d,'grade','evaluation.json')))['passed']
    n=len(rows)
    err=[bool(r['error']) for r in rows]
    ttft=[(r['first_token_ts']-r['scheduled_ts'])*1000 if r['first_token_ts'] else None for r in rows]
    e2e=[(r['end_ts']-r['scheduled_ts'])*1000 if r['end_ts'] else None for r in rows]
    okt=[t is not None and t<=1000 for t in ttft]; oke=[e is not None and e<=60000 for e in e2e]
    acc=[ev[i] and okt[i] and oke[i] and not err[i] for i in range(n)] if ev else None
    res=dict(arm=arm,scheduled=n,errors=sum(err))
    tt=[t for t in ttft if t is not None]; ee=[e for e in e2e if e is not None]
    res['ttft_ms']={p:pct(tt,p) for p in (50,95,99)}; res['ttft_max_ms']=max(tt) if tt else None
    res['e2e_ms']={p:pct(ee,p) for p in (50,95,99)}; res['e2e_max_ms']=max(ee) if ee else None
    # service-side ttft from send_ts (excludes scheduler lateness)
    st=[(r['first_token_ts']-r['send_ts'])*1000 for r in rows if r['first_token_ts'] and r['send_ts']]
    res['ttft_from_send_ms']={p:pct(st,p) for p in (50,95,99)}
    res['send_lag_ms']={p:pct([(r['send_ts']-r['scheduled_ts'])*1000 for r in rows if r['send_ts']],p) for p in (50,95,99)}
    if ev:
        res['correct']=sum(ev); res['accepted']=sum(acc)
        res['accepted_share']=sum(acc)/n
        res['correct_but_ttft_gt1s']=sum(1 for i in range(n) if ev[i] and not okt[i])
        res['correct_but_e2e_gt60s']=sum(1 for i in range(n) if ev[i] and not oke[i])
        res['correct_not_accepted']=sum(1 for i in range(n) if ev[i] and not acc[i])
        res['incorrect']=n-sum(ev)
        res['incorrect_share']=(n-sum(ev))/n
        # rejections: incorrect vs latency-only
        res['rejected_total']=n-sum(acc)
        res['rejected_incorrect_share_of_rejected']=(n-sum(ev))/(n-sum(acc))
        # per class
        cls={}
        for i,r in enumerate(rows):
            k=r['task_id'].split('/')[0]
            c=cls.setdefault(k,dict(n=0,correct=0,acc=0)); c['n']+=1; c['correct']+=ev[i]; c['acc']+=acc[i]
        res['class']=cls
        # first 300s bucket losses
        t0=min(r['scheduled_ts'] for r in rows)
        b=lambda i:int((rows[i]['scheduled_ts']-t0)//300)
        lost={}
        for i in range(n):
            if ev[i] and not acc[i]: lost[b(i)]=lost.get(b(i),0)+1
        res['correct_not_accepted_by_5min_bucket']=lost
    # serve.log
    sl=os.path.join(d,'serve.log')
    if os.path.exists(sl):
        txt=open(sl,encoding='utf-8',errors='replace').read()
        kv=[float(x) for x in re.findall(r'GPU KV cache usage: ([\d.]+)%',txt)]
        run=[int(x) for x in re.findall(r'Running: (\d+) reqs',txt)]
        wai=[int(x) for x in re.findall(r'Waiting: (\d+) reqs',txt)]
        res['serve']=dict(peak_kv_pct=max(kv) if kv else None,peak_running=max(run) if run else None,peak_waiting=max(wai) if wai else None,
            preempt_lines=len(re.findall(r'(?i)preempt',txt)),
            backend_lines=sorted(set(re.sub(r'^.*?\] ','',l.strip())[:170] for l in txt.splitlines() if re.search(r'(?i)Using \w+ (attention )?backend|Selected \w+ for|attention backend|Overriding|Using .* kernel|FlashInfer|AITER|TURBOQUANT',l) and 'aiter] ' not in l[:12]))[:14],
            sha256=sha(sl))
    res['requests_sha256']=sha(os.path.join(d,'replay','requests.jsonl'))
    if ev: res['evaluation_sha256']=sha(os.path.join(d,'grade','evaluation.json'))
    out[arm]=res
print(json.dumps(out,indent=1,default=str))
json.dump(out,open(os.path.join(os.environ.get('WORK','.'),'_run3_arms.json'),'w'),indent=1,default=str)
