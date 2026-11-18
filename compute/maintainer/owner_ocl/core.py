"""Receipt validation, uncertainty summaries and path-safe evidence manifests."""
from __future__ import annotations
import hashlib,json,math,os,statistics
from datetime import datetime
from pathlib import Path,PurePosixPath,PureWindowsPath

def _finite(v):return type(v) in (int,float) and math.isfinite(v)
def _pos(v):return _finite(v) and v>0
def _nn(v):return _finite(v) and v>=0
def _same(a,b):
    if type(a) is not type(b):return False
    if isinstance(a,dict):return a.keys()==b.keys() and all(_same(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(_same(x,y) for x,y in zip(a,b))
    return a==b

def validate_record(record):
    errors=[]
    if not isinstance(record,dict):return ['record must be an object']
    try:json.dumps(record,allow_nan=False)
    except (ValueError,TypeError):errors.append('non-finite or non-JSON data')
    if record.get('schema')!='ocl.run/1':errors.append('schema')
    if not isinstance(record.get('run_id'),str) or not record['run_id']:errors.append('run_id')
    try:
        date=datetime.fromisoformat(record.get('started_at','').replace('Z','+00:00'))
        if date.tzinfo is None:errors.append('started_at requires timezone')
    except (ValueError,TypeError,AttributeError):errors.append('started_at')
    for k in ('provenance','workload'):
        if not isinstance(record.get(k),dict):errors.append(k)
    if not _pos(record.get('duration_s')):errors.append('duration_s')
    tasks=record.get('observations')
    if not isinstance(tasks,list):return errors+['observations must be a list']
    work=record.get('workload') if isinstance(record.get('workload'),dict) else {}
    if 'expected_tasks' in work and (type(work['expected_tasks']) is not int or work['expected_tasks']!=len(tasks)):errors.append('expected task count mismatch')
    seen=set()
    for i,t in enumerate(tasks):
        p=f'observations[{i}]'
        if not isinstance(t,dict):errors.append(p);continue
        tid,rep=t.get('task_id'),t.get('repetition')
        if not isinstance(tid,str) or not tid:errors.append(p+'.task_id')
        if type(rep) is not int or rep<0:errors.append(p+'.repetition')
        if isinstance(tid,str) and type(rep) is int:
            if (tid,rep) in seen:errors.append(p+'.duplicate task')
            seen.add((tid,rep))
        if type(t.get('accepted')) is not bool:errors.append(p+'.accepted')
        if t.get('error') is not None and not isinstance(t['error'],str):errors.append(p+'.error')
        if not _pos(t.get('duration_s')):errors.append(p+'.duration_s')
        if 'expected' not in t or 'actual' not in t:errors.append(p+'.expected/actual missing')
        if not isinstance(t.get('evaluator_version'),str) or not t['evaluator_version']:errors.append(p+'.evaluator_version')
        checks=t.get('checks');valid_checks=isinstance(checks,dict) and bool(checks) and all(isinstance(k,str) and type(v) is bool for k,v in checks.items())
        if not valid_checks:errors.append(p+'.checks')
        attempts=t.get('attempts');valid_attempts=isinstance(attempts,list) and bool(attempts)
        if not valid_attempts:errors.append(p+'.attempts');attempts=[]
        for j,a in enumerate(attempts):
            q=p+f'.attempts[{j}]'
            if not isinstance(a,dict):errors.append(q);continue
            for field in ('stage','request','response_text','error','duration_s','ttft_s','input_tokens','output_tokens','started_monotonic_s','ended_monotonic_s'):
                if field not in a:errors.append(q+'.'+field+' missing')
            if not isinstance(a.get('stage'),str) or not isinstance(a.get('request'),dict):errors.append(q+'.stage/request')
            if a.get('response_text') is not None and not isinstance(a['response_text'],str):errors.append(q+'.response_text')
            if a.get('error') is not None and not isinstance(a['error'],str):errors.append(q+'.error')
            d,s,e=a.get('duration_s'),a.get('started_monotonic_s'),a.get('ended_monotonic_s')
            if not (_pos(d) and _nn(s) and _nn(e) and e>s):errors.append(q+'.interval')
            elif not math.isclose(e-s,d,rel_tol=1e-6,abs_tol=1e-5):errors.append(q+'.duration/interval mismatch')
            tt=a.get('ttft_s')
            if tt is not None and (not _nn(tt) or (_pos(d) and tt>d)):errors.append(q+'.ttft')
            for k in ('input_tokens','output_tokens'):
                if a.get(k) is not None and (type(a[k]) is not int or a[k]<0):errors.append(q+'.'+k)
        good=valid_checks and all(checks.values()) and t.get('error') is None and valid_attempts
        if t.get('accepted')!=good:errors.append(p+'.accepted inconsistent')
        if t.get('accepted') is True:
            if not _same(t.get('expected'),t.get('actual')):errors.append(p+'.accepted answer mismatch')
            if attempts and isinstance(attempts[-1],dict) and attempts[-1].get('error'):errors.append(p+'.final attempt error')
    for k in ('energy','cost'):
        if record.get(k) is not None and not isinstance(record[k],dict):errors.append(k)
    if not isinstance(record.get('limitations'),list) or any(not isinstance(x,str) for x in record.get('limitations',[])):errors.append('limitations')
    return errors

def _pct(a,p):
    if not a:return None
    a=sorted(a);x=(len(a)-1)*p;lo=int(x);hi=min(lo+1,len(a)-1);return a[lo]+(a[hi]-a[lo])*(x-lo)

def summarize(record):
    errs=validate_record(record)
    if errs:raise ValueError('invalid receipt: '+'; '.join(errs))
    tasks=record['observations'];n=len(tasks);ok=sum(t['accepted'] for t in tasks);attempts=[a for t in tasks for a in t['attempts']];durations=[t['duration_s'] for t in tasks];z=1.959963984540054
    rate=ok/n if n else None;ci=None
    if n:
        den=1+z*z/n;center=(rate+z*z/(2*n))/den;margin=z*math.sqrt(rate*(1-rate)/n+z*z/(4*n*n))/den;ci=[max(0,center-margin),min(1,center+margin)]
    tt=[a['ttft_s'] for a in attempts if a['ttft_s'] is not None]
    retries=sum(a['stage'].startswith(('retry','repair')) for a in attempts)
    return {'duration_s':record['duration_s'],'total_tasks':n,'accepted_tasks':ok,'failed_tasks':n-ok,'acceptance_rate':rate,'acceptance_wilson95':ci,'interval_assumption':'Descriptive binomial interval; repeated/correlated fixtures violate independent-trial inference.','p50_task_s':_pct(durations,.5),'p95_task_s':_pct(durations,.95),'percentile_method':'linear interpolation at (n-1)*p','accepted_per_s':ok/record['duration_s'],'attempts':len(attempts),'retries':retries,'input_tokens_known':sum(a['input_tokens'] or 0 for a in attempts),'output_tokens_known':sum(a['output_tokens'] or 0 for a in attempts),'unknown_token_attempts':sum(a['input_tokens'] is None or a['output_tokens'] is None for a in attempts),'ttft_mean_s':statistics.fmean(tt) if tt else None}

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def _safe(root,rel):
    if not isinstance(rel,str) or not rel or '\\' in rel:raise ValueError('manifest requires relative POSIX path')
    p=PurePosixPath(rel)
    if p.is_absolute() or '..' in p.parts or PureWindowsPath(rel).drive:raise ValueError('absolute/traversal path')
    r=Path(root).resolve();out=(r/rel).resolve()
    try:out.relative_to(r)
    except ValueError:raise ValueError('symlink escapes root')
    return out

def build_manifest(root,paths):
    out={}
    for rel in paths:
        p=_safe(root,rel)
        if not p.is_file():raise FileNotFoundError(rel)
        if rel in out:raise ValueError('duplicate manifest entry')
        out[rel]=sha256_file(p)
    return out

def verify_manifest(root,manifest):
    if not isinstance(manifest,dict):return ['manifest must be object']
    errors=[]
    for rel,digest in manifest.items():
        try:
            p=_safe(root,rel)
            if not p.is_file():errors.append('missing:'+rel)
            elif not isinstance(digest,str) or len(digest)!=64 or sha256_file(p)!=digest:errors.append('changed:'+rel)
        except (ValueError,TypeError,OSError) as exc:errors.append('invalid:'+str(rel)+':'+str(exc))
    return errors
