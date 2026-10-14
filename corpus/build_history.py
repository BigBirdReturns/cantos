"""Build a read-only public projection from already retained source rows.

No acquisition or model calls. Existing benchmark and issue projectors retain their
native identities; other collections expose source fields without joining unlike
metrics. Source payloads stay with their owners. --check verifies the delivered
projection without requiring the private estate path used to build it.
"""
from __future__ import annotations
import argparse, collections, gzip, hashlib, json, math, os, sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from corpus import bulk_import as native
SCHEMA = 'cantos/public-history@1'
DEFAULT_OUT = HERE / 'history'
CHUNK = 2000

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def web_url(value):
    if isinstance(value, str) and urlparse(value).scheme in ('https', 'http'):
        return value
    return None

def finite_tree(value):
    if isinstance(value, float) and not math.isfinite(value): return None
    if isinstance(value, dict): return {str(k):finite_tree(v) for k,v in value.items()}
    if isinstance(value, list): return [finite_tree(v) for v in value]
    return value

def date_of(row, provenance):
    return (row.get('snapshot_ts') or row.get('datePublished') or row.get('created_at')
            or row.get('date') or row.get('observed_at') or provenance.get('created_at'))

def project(source, index, row):
    """Expose factual source fields. Never infer quality, causal change or authority."""
    p = row.get('provenance') if isinstance(row.get('provenance'),dict) else {}
    source_id = source['id']
    item = {'id':source_id+':'+str(index), 'source':source_id, 'row':index,
            'kind':source['kind'], 'origin':row.get('source') or source['label'],
            'date':date_of(row,p), 'captured':p.get('retrieved_at'),
            'url':web_url(row.get('url') or row.get('source_url') or row.get('link') or p.get('url')),
            'revision':p.get('revision') or p.get('head_sha'), 'native_id':row.get('id'),
            'hardware':None, 'model':None, 'engine':None, 'metric':None,
            'value':None, 'unit':None, 'title':None, 'context':{}}
    descriptor={'origin':source_id,'sha256':source['raw_sha256'],
                'evidence_class':source['evidence_class'],'url':item['url'],
                'retrieved_at':item['captured'],'revision':item['revision']}
    if row.get('schema') == 'imported-observation@1':
        n=native.imported_observation_row(descriptor,index,row)
        item.update(id=n['row_id'],hardware=n['hardware'],model=n['model'],engine=n['engine'],
                    metric=n['measurement']['metric'],value=n['measurement']['value'],unit=n['measurement']['unit'])
        item['title']=' / '.join(str(x) for x in [item['hardware'],item['model'],item['metric']] if x)
        item['context']={'scope':n['scope'],'outcome':n['outcome'],'configuration':row.get('config'),
                         'workload':row.get('workload'),'hardware_count':n['hardware_count'],
                         'precision':n['quant'],'gates':row.get('gates'),'warnings':row.get('warnings'),
                         'provenance':p,'source_row_id':n['source']['native_row_sha256']}
    elif source['kind']=='issues':
        if row.get('source')=='github-issues':
            n=native.producer_issue_row(descriptor,index,row);item['id']=n['row_id']
        item.update(title=row.get('title'),hardware=', '.join(row.get('hardware') or []),
                    model=', '.join(row.get('model_family') or []) if isinstance(row.get('model_family'),list) else row.get('model_family'),
                    engine=native.engine(row.get('repo')) or row.get('repo'))
        item['context']={k:row.get(k) for k in ['repo','number','state','state_reason','is_pull_request','labels','created_at','closed_at','updated_at','fix_reference','fix_reference_source','provenance'] if k in row}
    elif source['kind']=='prices':
        item.update(title=' / '.join(str(row.get(k) or '') for k in ['provider','gpu','region','price_type']),
                    hardware=row.get('gpu'),metric='advertised GPU-hour price',
                    value=row.get('hourly_price_usd'),unit='USD/GPU-hour')
        item['context']={k:row.get(k) for k in ['snapshot_ts','provider','gpu','variant','gpu_count','region','price_type','commitment_period','instance_type','hourly_price_usd','instance_hourly_usd','available','available_count','source_file','provenance']}
    elif source['kind']=='research':
        item['title']=row.get('title') or row.get('slug')
        # Bibliographic metadata only; original prose/audio/transcripts stay at source.
        item['context']={k:row.get(k) for k in ['authors','datePublished','date','paywalled','companies_mentioned','duration','guests_named','people_named_in_title','provenance'] if k in row}
    elif source['kind']=='traces':
        item['title']=row.get('trace');item['metric']='request events in retained trace';item['value']=row.get('row_count');item['unit']='events'
        item['context']={k:v for k,v in row.items() if k not in ['raw','events','body','text']}
    else:
        item['title']=row.get('model') or row.get('dataset_id') or row.get('name') or row.get('chart') or row.get('source') or source['label']
        item['model']=row.get('model') or row.get('model_id')
        # Retained metadata, not conversation bodies or downloaded weights.
        item['context']={k:v for k,v in row.items() if k not in ['sample','description','free_preview_text','verbatim_text','body','text','messages','content']}
    if not item['title']:item['title']=source['label']+' row '+str(index+1)
    return finite_tree(item)

def discover(lanes):
    specs=[('inferencex-history','benchmarks','InferenceX measurement history','producer_reported'),
           ('mlperf','benchmarks','MLPerf submitted results','producer_reported'),
           ('github-issues','issues','Producer issues and pull requests','public_listing'),
           ('github-issues-deep','issues','Earlier producer issue history','public_listing'),
           ('opencomputeprices','prices','Historical GPU price snapshots','public_listing'),
           ('demand-signals','models','Model and demand observations','public_listing'),
           ('workload-traces','traces','Retained workload trace summaries','producer_reported'),
           ('sa-newsletter','research','SemiAnalysis publication history','bibliographic'),
           ('sa-podcasts','research','Research podcast episodes','bibliographic'),
           ('chat-corpora-meta','datasets','Dataset source metadata','public_listing')]
    result=[]
    for lane,kind,label,evidence in specs:
        for path in sorted((lanes/lane/'rows').glob('*.jsonl')):
            if path.name=='quotes.jsonl':continue  # no republication of transcript excerpts
            result.append((path,{'id':lane+'--'+path.stem,'lane':lane,'kind':kind,'label':label+' / '+path.stem,
                                 'evidence_class':evidence,'file':path.name,'raw_bytes':path.stat().st_size,'raw_sha256':sha(path)}))
    return result

def write_chunk(out, source, rows, ordinal):
    rel='shards/'+source['id']+'-'+str(ordinal).zfill(5)+'.json.gz'
    payload=(canonical(rows)+'\n').encode('utf-8')
    data=gzip.compress(payload,compresslevel=6,mtime=0)
    path=out/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    facets={key:sorted({str(r[key]) for r in rows if r.get(key) is not None}) for key in ['hardware','model','engine','unit']}
    dates=sorted(str(r['date']) for r in rows if r.get('date'))
    return {'file':rel,'source':source['id'],'kind':source['kind'],'count':len(rows),'sha256':hashlib.sha256(data).hexdigest(),
            'bytes':len(data),'expanded_bytes':len(payload),'facets':facets,'date_first':dates[0] if dates else None,'date_last':dates[-1] if dates else None}

def build(lanes, out):
    out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():raise ValueError('Build into a fresh output directory; preserve the prior delivery.')
    sources=[];shards=[]
    for path,s in discover(lanes):
        print('Projecting '+s['id'],flush=True)
        s['count']=0;batch=[];ordinal=0;dates=[];captures=[]
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for index,line in enumerate(stream):
                digest.update(line)
                if not line.strip():continue
                raw=json.loads(line);row=project(s,index,raw);batch.append(row);s['count']+=1
                if row['date']:dates.append(str(row['date']))
                if row['captured']:captures.append(str(row['captured']))
                if len(batch)>=CHUNK:
                    shards.append(write_chunk(out,s,batch,ordinal));batch=[];ordinal+=1
        if batch:shards.append(write_chunk(out,s,batch,ordinal))
        if digest.hexdigest()!=s['raw_sha256']:raise ValueError('Source changed while projecting '+s['id'])
        s.update(date_first=min(dates) if dates else None,date_last=max(dates) if dates else None,
                 captured_first=min(captures) if captures else None,captured_last=max(captures) if captures else None)
        sources.append(s);print(s['id']+' '+str(s['count'])+' rows',flush=True)
    counts=dict(collections.Counter())
    for s in sources:counts[s['kind']]=counts.get(s['kind'],0)+s['count']
    manifest={'schema':SCHEMA,'sources':sources,'shards':shards,'counts':counts,'total_rows':sum(counts.values()),
              'projection_owner':'corpus/build_history.py','projection_sha256':sha(Path(__file__)),
              'native_projection_owner':'corpus/bulk_import.py','native_projection_sha256':sha(HERE/'bulk_import.py'),
              'record_kind':'historical source observations','research_scope':'Bibliographic metadata; prose and recordings remain at the original source.'}
    (out/'manifest.json').write_text(canonical(manifest)+'\n',encoding='utf-8')
    print(json.dumps({'rows':manifest['total_rows'],'counts':counts,'sources':len(sources),'shards':len(shards),'compressed_bytes':sum(s['bytes'] for s in shards)}),flush=True)
    return manifest

def check(out):
    m=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    if m.get('schema')!=SCHEMA:raise ValueError('Unsupported history projection')
    sources={s['id']:s for s in m['sources']};counts=collections.Counter();seen=set()
    for shard in m['shards']:
        p=(out/shard['file']).resolve()
        if not p.is_relative_to(out.resolve()) or sha(p)!=shard['sha256']:raise ValueError('Shard changed: '+shard['file'])
        rows=json.loads(gzip.decompress(p.read_bytes()))
        if len(rows)!=shard['count']:raise ValueError('Row count differs')
        for row in rows:
            if row['source'] not in sources or row['kind']!=sources[row['source']]['kind']:raise ValueError('Source identity mismatch')
            if row['id'] in seen:raise ValueError('Duplicate observation identity '+row['id'])
            seen.add(row['id']);counts[row['source']]+=1
            if not isinstance(row['row'],int) or row['row']<0:raise ValueError('Missing source coordinate')
            if row.get('url') and not web_url(row['url']):raise ValueError('Unsafe source URL')
    for source,count in counts.items():
        if count!=sources[source]['count']:raise ValueError('Source coverage mismatch '+source)
    if sum(counts.values())!=m['total_rows']:raise ValueError('Total coverage mismatch')
    print(json.dumps({'status':'PASS','rows':m['total_rows'],'sources':len(sources),'shards':len(m['shards']),'counts':m['counts']}))
    return m

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--lanes',type=Path);ap.add_argument('--out',type=Path,default=DEFAULT_OUT);ap.add_argument('--check',action='store_true');a=ap.parse_args()
    if a.check:check(a.out)
    elif a.lanes:build(a.lanes,a.out)
    else:ap.error('Supply --lanes for a fresh build, or --check for the delivered projection')
if __name__=='__main__':main()
