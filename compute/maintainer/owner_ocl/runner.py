"""Bounded, journaled two-turn local model evaluations. No model-authored code runs."""
from __future__ import annotations
import argparse,copy,hashlib,ipaddress,json,math,os,random,tempfile,time,urllib.error,urllib.parse,urllib.request
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from .tasks import Task,fixture_hash,lookup,make_tasks
MAX_BODY=2*1024*1024

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

def _now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def _strict_loads(text):
    raw=text.strip()
    if raw.startswith('```'):
        lines=raw.splitlines()
        if len(lines)<3 or lines[0].strip() not in ('```','```json') or lines[-1].strip()!='```': raise ValueError('invalid JSON fence')
        raw='\n'.join(lines[1:-1])
    def pairs(items):
        out={}
        for k,v in items:
            if k in out: raise ValueError('duplicate JSON key')
            out[k]=v
        return out
    def invalid(x): raise ValueError('non-finite JSON constant '+x)
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)

def _equal(a,b):
    if type(a) is not type(b): return False
    if isinstance(a,dict): return a.keys()==b.keys() and all(_equal(a[k],b[k]) for k in a)
    if isinstance(a,list): return len(a)==len(b) and all(_equal(x,y) for x,y in zip(a,b))
    return a==b

def endpoint(base_url,allow_remote=False):
    p=urllib.parse.urlsplit(base_url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.query or p.fragment: raise ValueError('invalid or credential-bearing endpoint')
    try: local=ipaddress.ip_address(p.hostname).is_loopback
    except ValueError: local=p.hostname=='localhost'
    if not allow_remote and not local: raise ValueError('remote URL requires allow_remote')
    if p.path.rstrip('/') not in ('','/v1'): raise ValueError('base URL path must be empty or /v1')
    return base_url.rstrip('/')+('/chat/completions' if p.path.rstrip('/')=='/v1' else '/v1/chat/completions')

def _body(model,messages,max_tokens,extra_body):
    body={'model':model,'messages':copy.deepcopy(messages),'temperature':0,'max_tokens':max_tokens,'stream':False}
    if extra_body:
        if set(extra_body)&{'model','messages','temperature','max_tokens','stream','api_key','authorization','api_base'}: raise ValueError('protected request override')
        body.update(extra_body)
    json.dumps(body,allow_nan=False)
    return body

def _attempt(stage,url,body,timeout):
    start=time.monotonic(); text=''; error=None; inp=out=None; finish_reason=None
    try:
        headers={'Content-Type':'application/json'}
        if os.environ.get('OCL_API_KEY'): headers['Authorization']='Bearer '+os.environ['OCL_API_KEY']
        req=urllib.request.Request(url,json.dumps(body,allow_nan=False).encode(),headers,method='POST')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        with opener.open(req,timeout=timeout) as r: data=r.read(MAX_BODY+1)
        if len(data)>MAX_BODY: raise ValueError('response exceeds 2MiB')
        payload=_strict_loads(data.decode('utf-8'))
        usage=payload.get('usage') or {}
        def count(k):
            v=usage.get(k)
            return v if type(v) is int and v>=0 else None
        inp,out=count('prompt_tokens'),count('completion_tokens')
        choice=payload['choices'][0];content=choice['message']['content'];finish_reason=choice.get('finish_reason')
        if isinstance(content,list): content=''.join(x['text'] for x in content if isinstance(x,dict) and x.get('type')=='text' and isinstance(x.get('text'),str))
        if not isinstance(content,str): raise ValueError('missing text content')
        text=content
    except Exception as exc: error=type(exc).__name__+': '+str(exc)[:600]
    end=time.monotonic()
    return {'stage':stage,'request':body,'response_text':text,'error':error,'duration_s':end-start,'ttft_s':None,'input_tokens':inp,'output_tokens':out,'started_monotonic_s':start,'ended_monotonic_s':end,'finish_reason':finish_reason}

FORMATS={
'invoice_minor_units':'Return {"total_minor": integer, "matches_claimed": boolean}. Sum quantity*(unit_minor-discount_minor), then compare to claimed_total_minor.',
'inventory_selection':'Return {"feasible": boolean, "sku": string or null, "price_minor": integer or null}. Select minimum unit price with stock >= requested; tie-break by SKU; all null if infeasible.',
'telemetry_aggregation':'Return {"totals": {device_id: integer sum}}. Sum every value grouped by device; include precisely the devices in the samples.',
'source_id_evidence':'Return {"source_id": string, "title": string, "year": integer} from the record whose source_id matches the requested source_id.'}

def _one(task,url,model,timeout,max_tokens,tasks,extra_body,repetition):
    start=time.monotonic();attempts=[];actual=None;error=None;tool_ok=False;json_ok=False
    messages=[{'role':'system','content':'You are performing a bounded data-analysis task. First reply with the exact lookup JSON supplied by the user, with no prose. After tool data arrives, solve the stated task and reply only with the required final JSON. /no_think'}, {'role':'user','content':json.dumps({'tool':'lookup','arguments':{'key':task.key}},separators=(',',':'))}]
    try:
        first=_attempt('tool_request',url,_body(model,messages,max_tokens,extra_body),timeout);attempts.append(first)
        if first['error']: raise ValueError(first['error'])
        obj=_strict_loads(first['response_text']);tool_ok=_equal(obj,{'tool':'lookup','arguments':{'key':task.key}})
        if not tool_ok: raise ValueError('invalid tool request')
        data=lookup(tasks,task.key)
        messages += [{'role':'assistant','content':first['response_text']},{'role':'user','content':json.dumps(data,separators=(',',':'))},{'role':'user','content':task.description+' '+FORMATS[task.family]+' /no_think'}]
        final=_attempt('final',url,_body(model,messages,max_tokens,extra_body),timeout);attempts.append(final)
        if final['error']: raise ValueError(final['error'])
        actual=_strict_loads(final['response_text']);json_ok=True
        if not _equal(actual,task.expected): error='answer mismatch'
    except Exception as exc: error=type(exc).__name__+': '+str(exc)[:600]
    checks={'valid_tool_request':tool_ok,'valid_final_json':json_ok,'exact_expected':json_ok and _equal(actual,task.expected)}
    return {'task_id':task.task_id,'repetition':repetition,'accepted':bool(error is None and all(checks.values())),'error':error,'duration_s':time.monotonic()-start,'expected':task.expected,'actual':actual,'evaluator_version':'ocl.exact-json/1','checks':checks,'attempts':attempts}

def run_suite(base_url,model,out,repeats=2,seed=1729,timeout=30,max_tokens=256,concurrency=1,**kwargs):
    url=endpoint(base_url,kwargs.get('allow_remote',False))
    for k,v,lo,hi in [('repeats',repeats,1,100),('concurrency',concurrency,1,32),('max_tokens',max_tokens,1,4096)]:
        if type(v) is not int or not lo<=v<=hi: raise ValueError('invalid '+k)
    if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=120: raise ValueError('invalid timeout')
    if not isinstance(model,str) or not model: raise ValueError('model required')
    _body(model,[],max_tokens,kwargs.get('extra_body'))
    tasks=make_tasks(seed);limit=kwargs.get('task_limit')
    if limit is not None:
        if type(limit) is not int or not 1<=limit<=len(tasks): raise ValueError('invalid task_limit')
        tasks=tasks[:limit]
    work=[(t,r) for r in range(repeats) for t in tasks];random.Random(seed).shuffle(work)
    target=Path(out);target.parent.mkdir(parents=True,exist_ok=True)
    journal=target.with_suffix(target.suffix+'.jsonl')
    plan_path=target.with_suffix(target.suffix+'.plan.json')
    # Preflight all three destinations before making any HTTP request or creating a journal.
    # An interrupted or previously attempted run is evidence, not a retry authorization.
    for existing in (target,plan_path,journal):
        if existing.exists(): raise FileExistsError(str(existing))
    started_at=_now();start=time.monotonic();records=[]
    plan={'schema':'ocl.run-plan/1','started_at':started_at,'expected_tasks':len(work),'order':[[t.task_id,r] for t,r in work],'workload_sha256':fixture_hash(tasks),'seed':seed,'repeats':repeats,'model':model,'max_tokens':max_tokens,'concurrency':concurrency,'endpoint':url}
    with plan_path.open('x',encoding='utf-8') as f: json.dump(plan,f,indent=2)
    with journal.open('x',encoding='utf-8') as journal_file:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures=[pool.submit(_one,t,url,model,timeout,max_tokens,tasks,kwargs.get('extra_body'),r) for t,r in work]
            for future in as_completed(futures):
                record=future.result();records.append(record);journal_file.write(json.dumps(record,allow_nan=False)+'\n');journal_file.flush();os.fsync(journal_file.fileno())
    end=time.monotonic();records.sort(key=lambda t:(t['repetition'],t['task_id']))
    provenance={'hardware':None,'model':model,'runtime':'OpenAI-compatible HTTP client','model_sha256':None,'precision':None,'context_limit':None,'workload_sha256':fixture_hash(tasks)};provenance.update(kwargs.get('provenance') or {})
    receipt={'schema':'ocl.run/1','run_id':hashlib.sha256((started_at+str(target)+fixture_hash(tasks)).encode()).hexdigest(),'started_at':started_at,'provenance':provenance,'workload':{'name':'lookup-analysis-micro-suite','version':'1','seed':seed,'repeats':repeats,'description':'Supplied lookup call followed by independently checked data analysis; synthetic fixtures, no model-generated code.','expected_tasks':len(work),'task_ids':[t.task_id for t in tasks],'concurrency':concurrency,'max_tokens':max_tokens,'fixture_sha256':fixture_hash(tasks)},'duration_s':end-start,'window_monotonic_s':[start,end],'observations':records,'energy':None,'cost':None,'limitations':['Custom micro-workload, not AgentX or a broad capability benchmark.','Nonstreamed client: time-to-first-token is unmeasured.','Zero retries: every failed request is retained.','Repeated fixtures are correlated; Wilson interval is descriptive, not an independent-trial guarantee.']+(['Noncanonical task subset.'] if limit is not None else [])}
    fd,temp=tempfile.mkstemp(prefix=target.name+'.',dir=target.parent);os.close(fd)
    try:
        Path(temp).write_text(json.dumps(receipt,indent=2,allow_nan=False),encoding='utf-8')
        if target.exists(): raise FileExistsError(str(target))
        os.replace(temp,target)
    finally:
        if Path(temp).exists(): Path(temp).unlink()
    return receipt

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base-url','model','out'): p.add_argument('--'+name,required=True)
    p.add_argument('--repeats',type=int,default=2);p.add_argument('--concurrency',type=int,default=1);p.add_argument('--timeout',type=float,default=30);p.add_argument('--max-tokens',type=int,default=256);p.add_argument('--task-limit',type=int);p.add_argument('--allow-remote',action='store_true')
    p.add_argument('--disable-thinking-template',action='store_true',help='Pass chat_template_kwargs.enable_thinking=False for compatible models such as Qwen3')
    a=vars(p.parse_args(argv))
    if a.pop('disable_thinking_template'): a['extra_body']={'chat_template_kwargs':{'enable_thinking':False}}
    receipt=run_suite(**a)
    print(json.dumps({'run_id':receipt['run_id'],'tasks':len(receipt['observations']),'accepted':sum(o['accepted'] for o in receipt['observations'])}))
    return 0
if __name__=='__main__': raise SystemExit(main())
