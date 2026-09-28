"""Independent public seed/source checks; never reruns generated-code grading."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
seed=json.loads((ROOT/'research-desk/cantos/data/seed.json').read_text(encoding='utf-8-sig'))
assert seed['schema']=='cantos/seed@1' and not seed.get('provisional')
checks=[]
records={r['id']:r for r in seed['records']}
measurements=[r for r in records.values() if r['data']['role']=='measurement']
assert sorted(r['data']['metrics']['accepted'] for r in measurements)==[4280,4336]
for record in records.values():
    data=record['data']
    if data.get('relative_path') and data.get('sha256'):
        relative=Path(data['relative_path'])
        assert not relative.is_absolute() and '..' not in relative.parts
        actual=hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()
        assert actual==data['sha256'],f'Source identity mismatch: {relative}'
        checks.append({'name':record['id']+' source identity','sha256':actual,'status':'PASS'})
    if data['role']=='measurement':
        metric=data['metrics']
        assert metric['scheduled']==metric['completed']==8622
        assert metric['correct_raw']==(4371 if metric['accepted']==4336 else 4329)
        assert metric['accepted']!=6192,'Post-hoc correctness substituted for registered acceptance'
        assert data['identity']['revision']=='dcaee4d4dfc5ee71ad501f01f530e5652438fde0'
        assert data['identity']['runtime']=='vLLM 0.30.0'
    if data['role']=='economics':
        assert 'result' not in data,'Seed must not hand-copy derived results'
        assert data['inputs']['accepted']==4336
        deps=[records[d['id']] for d in record['deps']]
        assert sum(d['data']['role']=='price' for d in deps)==1
        assert sum(d['data']['role']=='measurement' for d in deps)==1
text=json.dumps(seed).lower()
for disclosure in ['post-hoc','provider credit','self-funded','one run','own-seat','invoice']:
    assert disclosure in text,disclosure
checks.append({'name':'Run3 registered counts, model pins, input completeness and scope disclosures','status':'PASS'})
print(json.dumps({'status':'PASS','scope':'Final public-safe bridge seed and exact local source bytes; not new measurement or authenticated source truth.','seed_sha256':hashlib.sha256((ROOT/'research-desk/cantos/data/seed.json').read_bytes()).hexdigest(),'checks':checks},indent=2))
