"""Public source snapshots -> common rows and SQLite. No inference or evaluator."""
from pathlib import Path
import argparse, collections, csv, hashlib, io, json, math, re, sqlite3

def canonical(x): return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def sha(b): return hashlib.sha256(b).hexdigest()
def num(x,integer=False):
    if x is None or x=='': return None
    if isinstance(x,bool): raise ValueError('Boolean measurement')
    n=float(x)
    if not math.isfinite(n) or n<0 or integer and not n.is_integer(): raise ValueError('Invalid measurement')
    return int(n) if integer else n

def base(s,i,n,kind):
    return dict(row_id=sha(canonical([s['origin'],s['sha256'],i]).encode()),kind=kind,
        hardware=None,hardware_count=None,model=None,quant=None,engine=None,context=None,
        batch=None,throughput=None,price=None,outcome=None,accepted=None,
        source={**{k:s.get(k) for k in ['origin','url','revision','retrieved_at','evidence_class','license','time_basis']},
        'raw_sha256':s['sha256'],'row_index':i,'native_row_sha256':sha(canonical(n).encode())},scope={},native=n)
def engine(text):
    for token,label in [('vllm','vLLM'),('tensorrt-llm','TensorRT-LLM'),('sglang','SGLang'),('llama.cpp','llama.cpp'),('tensorrt','TensorRT'),('openvino','OpenVINO')]:
        if token in str(text).lower(): return label
    return None

def mlperf(s,raw):
    rows=json.loads(raw)
    if not isinstance(rows,list): raise ValueError('Expected MLPerf summary list')
    for i,n in enumerate(rows):
        r=base(s,i,n,'benchmark')
        r.update(hardware=n.get('Accelerator') or n.get('Processor'),hardware_count=num(n.get('a#'),True),model=n['Model'],quant=n.get('weight_data_types'),engine=engine(n.get('Software')))
        measurement={'value':num(n['Performance_Result']),'unit':n['Performance_Units'],'metric':'Performance_Result'}
        r['measurement']=measurement
        if n['Performance_Units'] in ('Tokens/s','Samples/s','Queries/s'): r['throughput']=measurement
        elif n['Performance_Units']=='Latency (ms)': r['latency']=measurement
        else: r['scope']['unmapped_metric_unit']=n['Performance_Units']
        r['outcome']={'compliance':n.get('compliance'),'errors':n.get('errors'),'accuracy':n.get('Accuracy'),'contract':'MLPerf '+n.get('version','')}
        r['scope']={k:n.get(k) for k in ['ID','Scenario','Suite','Category','Nodes','Platform','Software','Location','inferred','has_power']}
        r['scope']['accepted_equivalence']=None
        yield r

def traces(s,raw):
    azure=s['format']=='azure-trace-csv'
    if azure:
        rows=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if rows.fieldnames!=['TIMESTAMP','ContextTokens','GeneratedTokens']: raise ValueError('Unknown trace schema')
    else: rows=(json.loads(x) for x in raw.decode('utf-8-sig').splitlines() if x.strip())
    for i,n in enumerate(rows):
        r=base(s,i,n,'workload_trace')
        r['context']={'input_tokens':num(n['ContextTokens' if azure else 'input_length'],True),'output_tokens':num(n['GeneratedTokens' if azure else 'output_length'],True)}
        r['scope']={'workload':s['workload'],'source_line':i+(2 if azure else 1)}
        if azure: r['scope'].update(arrival=n['TIMESTAMP'],clock='source timestamp; timezone unspecified')
        else: r['scope'].update(arrival_ms=num(n['timestamp'],True),clock='relative milliseconds',prefix_block_tokens=512,hash_ids=n.get('hash_ids'))
        r['outcome']={'correctness':None,'deadline_pass':None,'recorded_output_length':True}
        yield r

def openrouter(s,raw):
    obj=json.loads(raw)
    if not isinstance(obj.get('data'),list): raise ValueError('Missing data list')
    for i,n in enumerate(obj['data']):
        ranked=s['format']=='openrouter-rankings'
        r=base(s,i,n,'usage' if ranked else 'model_catalog')
        r['model']=n['model_permaslug' if ranked else 'id']
        if ranked:
            r['scope']={'date':n['date'],'total_tokens':num(n['total_tokens'],True),'meta':obj.get('meta'),'filters':s.get('filters',{}),'population':'public OpenRouter traffic, not market-wide demand'}
        else:
            r['context']={'maximum_tokens':num(n.get('context_length'),True)}
            r['price']={'native':n.get('pricing',{}),'currency':'USD','basis':'model catalogue; not usage rankings'}
            r['scope']={'canonical_slug':n.get('canonical_slug'),'architecture':n.get('architecture'),'created':n.get('created')}
        yield r

def prices(s,raw):
    obj=json.loads(raw)
    if s['format']=='azure-prices':
        for i,n in enumerate(obj['Items']):
            r=base(s,i,n,'price');r['hardware']=n.get('armSkuName') or n.get('skuName')
            r['price']={'value':num(n['retailPrice']),'currency':n['currencyCode'],'unit':n['unitOfMeasure'],'basis':n['type'],'reservation_term':n.get('reservationTerm')}
            r['scope']={k:n.get(k) for k in ['armRegionName','effectiveStartDate','productName','meterId','meterName','skuId','tierMinimumUnits']}
            r['scope']['supply_availability']=None
            yield r
    elif s['format']=='aws-prices':
        i=0
        for kind,skus in obj['terms'].items():
            for sku,terms in skus.items():
                for code,term in terms.items():
                    for rate_code,rate in term['priceDimensions'].items():
                        n={'sku':sku,'product':obj['products'][sku],'term':kind,'term_code':code,'effectiveDate':term['effectiveDate'],'termAttributes':term.get('termAttributes',{}),'rate':rate}
                        r=base(s,i,n,'price');i+=1;attr=n['product'].get('attributes',{})
                        r['hardware']=attr.get('instanceType')
                        r['price']={'value':num(rate['pricePerUnit'].get('USD')),'currency':'USD','unit':rate['unit'],'basis':kind}
                        r['scope']={'attributes':attr,'terms':n['termAttributes'],'rate_code':rate_code,'effective_at':n['effectiveDate'],'begin_range':rate.get('beginRange'),'end_range':rate.get('endRange')}
                        yield r
    elif s['format']=='gcp-prices':
        for i,n in enumerate(obj['skus']):
            r=base(s,i,n,'price');r['hardware']=n.get('description')
            r['price']={'pricing_info':n.get('pricingInfo'),'basis':'GCP billing catalogue'}
            r['scope']={'sku_id':n['skuId'],'regions':n.get('serviceRegions'),'category':n.get('category')}
            yield r
    else: raise ValueError('Unknown price format')

def community(s,raw):
    obj=json.loads(raw)
    if s['format']=='llama-bench-json':
        if not isinstance(obj,list): obj=[obj]
        for i,n in enumerate(obj):
            r=base(s,i,n,'community_benchmark')
            r.update(hardware=n.get('gpu_info') or n.get('cpu_info'),model=n.get('model_filename'),quant=n.get('model_type'),engine='llama.cpp',batch=num(n.get('n_batch'),True))
            r['context']={'prompt_tokens':num(n.get('n_prompt'),True),'generated_tokens':num(n.get('n_gen'),True)}
            r['throughput']={'value':num(n['avg_ts']),'unit':'tokens/s','stddev':num(n.get('stddev_ts'))}
            r['scope']={k:n.get(k) for k in ['build_commit','n_gpu_layers','test_time']}
            yield r
        return
    pattern=re.compile(r'(?<![\d.])(\d+(?:\.\d+)?)\s*(?:tokens?/s(?:ec)?|t/s|tok/s|tokens? per second)\b',re.I)
    for i,child in enumerate(obj['data']['children']):
        n=child['data'];text=n.get('title','')+'\n'+n.get('selftext',n.get('body',''))
        public={k:n.get(k) for k in ['id','title','permalink','created_utc']};public['text']=text
        r=base(s,i,public,'community_lead')
        r['scope']={'post_id':n['id'],'crosspost_parent':n.get('crosspost_parent'),'needs_config_join':True,'matches':[{'value':float(m.group(1)),'unit':'reported tokens/s','start':m.start(),'end':m.end()} for m in pattern.finditer(text)]}
        yield r

ADAPTERS={'mlperf-summary':mlperf,'azure-trace-csv':traces,'mooncake-trace-jsonl':traces,'openrouter-rankings':openrouter,'openrouter-models':openrouter,'azure-prices':prices,'aws-prices':prices,'gcp-prices':prices,'reddit-listing':community,'llama-bench-json':community}

def ingest(manifest_path,destination):
    manifest=json.loads(manifest_path.read_text());destination.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(destination/'corpus.sqlite')
    db.execute('CREATE TABLE IF NOT EXISTS rows (row_id TEXT PRIMARY KEY,kind TEXT,origin TEXT,hardware TEXT,model TEXT,quant TEXT,engine TEXT,json TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS sightings (row_id TEXT,snapshot TEXT,source_url TEXT,retrieved_at TEXT,PRIMARY KEY(row_id,snapshot,source_url))')
    db.execute('CREATE INDEX IF NOT EXISTS cell_lookup ON rows(kind,hardware,model,quant,engine)')
    stats=[]
    for s in manifest['sources']:
        p=(manifest_path.parent/s['path']).resolve()
        if not p.is_relative_to(manifest_path.parent.resolve()): raise ValueError('Path escapes manifest directory')
        raw=p.read_bytes()
        if sha(raw)!=s['sha256']: raise ValueError('Raw hash mismatch: '+s['origin'])
        count=inserted=0
        with db:
            for row in ADAPTERS[s['format']](s,raw):
                count+=1
                cur=db.execute('INSERT OR IGNORE INTO rows VALUES (?,?,?,?,?,?,?,?)',(row['row_id'],row['kind'],s['origin'],row['hardware'],row['model'],row['quant'],row['engine'],canonical(row)))
                inserted+=cur.rowcount
                db.execute('INSERT OR IGNORE INTO sightings VALUES (?,?,?,?)',(row['row_id'],s['sha256'],s['url'],s['retrieved_at']))
        stats.append({'origin':s['origin'],'format':s['format'],'source_rows':count,'inserted':inserted,'existing':count-inserted,'raw_sha256':s['sha256']})
    with (destination/'rows.jsonl').open('w',encoding='utf-8',newline='\n') as f:
        for (text,) in db.execute('SELECT json FROM rows ORDER BY origin,row_id'): f.write(text+'\n')
    report={'sources':stats,'rows':db.execute('SELECT count(*) FROM rows').fetchone()[0],'by_kind':dict(db.execute('SELECT kind,count(*) FROM rows GROUP BY kind')),'new_rows':sum(s['inserted'] for s in stats),'reused_rows':sum(s['existing'] for s in stats),'rows_sha256':sha((destination/'rows.jsonl').read_bytes()),'accepted_values':db.execute("SELECT count(*) FROM rows WHERE json_extract(json,'$.accepted') IS NOT NULL").fetchone()[0]}
    db.close();(destination/'IMPORT.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();print(json.dumps(ingest(a.manifest,a.out),indent=2))
