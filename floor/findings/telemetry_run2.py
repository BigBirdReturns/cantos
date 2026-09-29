#!/usr/bin/env python3
"""Run 2 default (auto ROCM_ATTN) vs post-hoc forced ROCM_AITER_FA, per cell, plus KV-cache/queue peaks
from serve.log windows. stdlib only. Reads hot-aisle/campaign/results/run2-*. Prints JSON lines + table."""
import json, re, sys, os, hashlib
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..','..','hot-aisle','campaign','results')
R = os.path.normpath(R)
def sha(p):
    return hashlib.sha256(open(p,'rb').read()).hexdigest()
def secs(hms):
    h,m,s = map(int,hms.split(':')); return h*3600+m*60+s
END={}
def armlog(d):
    t=[]; 
    for ln in open(os.path.join(d,'arm-log.txt'),encoding='utf-8'):
        m=re.match(r'(\d\d:\d\d:\d\d) cell (cell-\S+)\.json',ln)
        if m: t.append((secs(m.group(1)),m.group(2)))
        m=re.match(r'(\d\d:\d\d:\d\d) (bench done|watchdog stop)',ln)
        if m: END[d]=secs(m.group(1))
    return t
def servelog(d):
    rows=[]
    for ln in open(os.path.join(d,'serve.log'),encoding='utf-8',errors='replace'):
        m=re.search(r'\d\d-\d\d (\d\d:\d\d:\d\d) \[loggers.py.*Running: (\d+) reqs, Waiting: (\d+) reqs, GPU KV cache usage: ([\d.]+)%',ln)
        if m: rows.append((secs(m.group(1)),int(m.group(2)),int(m.group(3)),float(m.group(4))))
    return rows
def load(d,cell):
    return json.load(open(os.path.join(d,cell+'.json')))
out=[]
def cellstats(d,logs,serve):
    res={}
    for i,(t,c) in enumerate(logs):
        j=load(d,c)
        # arm-log stamps a cell at its START (verified: next stamp - this stamp ~= duration + ~15 s)
        hi = logs[i+1][0] if i+1<len(logs) else END[d]
        win=[r for r in serve if t< r[0] <=hi]
        res[c]=dict(cell=c.replace('cell-',''),req_s=j['request_throughput'],out_tok_s=j['output_throughput'],
            ttft_p50=j['p50_ttft_ms'],ttft_p95=j['p95_ttft_ms'],ttft_p99=j['p99_ttft_ms'],
            e2e_p50=j['p50_e2el_ms'],e2e_p95=j['p95_e2el_ms'],e2e_p99=j['p99_e2el_ms'],
            tpot_p50=j['p50_tpot_ms'],itl_p50=j['p50_itl_ms'],completed=j['completed'],failed=j['failed'],
            n_prompts=j['num_prompts'],dur_s=j['duration'],
            in_tok=j['input_lens'][0], out_tok=j['output_lens'][0], max_conc=j['max_concurrency'],
            peak_kv_pct=max([r[3] for r in win],default=None),max_waiting=max([r[2] for r in win],default=None),
            max_running=max([r[1] for r in win],default=None), sha256=sha(os.path.join(d,c+'.json')))
    return res
dd=os.path.join(R,'run2-hotaisle-mi300x'); de=os.path.join(R,'run2-explore-hotaisle-mi300x')
D=cellstats(dd,armlog(dd),servelog(dd)); E=cellstats(de,armlog(de),servelog(de))
print('cell | default req/s | forced req/s | delta% | ttft p50/p95/p99 default | forced | peakKV% d/f | maxWait d/f')
for c,e in E.items():
    # match to r0; r1 default if any
    for tag in (c, c.replace('-r0','-r1')):
        if tag in D:
            d=D[tag]
            print(f"{c} vs {tag}: {d['req_s']:.4f} -> {e['req_s']:.4f} ({(e['req_s']/d['req_s']-1)*100:+.1f}%) | ttft {d['ttft_p50']:.0f}/{d['ttft_p95']:.0f}/{d['ttft_p99']:.0f} -> {e['ttft_p50']:.0f}/{e['ttft_p95']:.0f}/{e['ttft_p99']:.0f} | e2e p95 {d['e2e_p95']:.0f}->{e['e2e_p95']:.0f} | KV {d['peak_kv_pct']}/{e['peak_kv_pct']} | wait {d['max_waiting']}/{e['max_waiting']} | run/conc {d['max_running']}/{e['max_running']}")
print()
print('DEFAULT-only cells (registered, incl. overload)')
for c,d in D.items():
    print(f"{c}: req/s {d['req_s']:.4f} completed {d['completed']}/{d['n_prompts']} failed {d['failed']} ttft {d['ttft_p50']:.0f}/{d['ttft_p95']:.0f}/{d['ttft_p99']:.0f} e2e p50/p95/p99 {d['e2e_p50']:.0f}/{d['e2e_p95']:.0f}/{d['e2e_p99']:.0f} peakKV {d['peak_kv_pct']} maxWait {d['max_waiting']} maxRun {d['max_running']} dur {d['dur_s']:.0f}s in/out {d['in_tok']}/{d['out_tok']} conc*(in+out)={d['max_conc']*(d['in_tok']+d['out_tok'])}")
json.dump({'default':D,'explore':E},open(os.path.join(os.environ.get('WORK','.'),'_run2_cells.json'),'w'),indent=1)
