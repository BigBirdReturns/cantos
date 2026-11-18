"""Prepare and bind source-bound EvalPlus grading for Cantos maintainer runs.

This program never executes generated solutions. Run EvalPlus in the documented
network-isolated container between prepare and bind. The normalizer is trusted
tool code whose exact bytes must match the workload's pinned grader identity.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from collections import defaultdict

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def strict_pairs(items):
    out = {}
    for k,v in items:
        if k in out:
            raise ValueError('duplicate JSON key: '+k)
        out[k] = v
    return out

def read(p):
    return json.loads(Path(p).read_text(),object_pairs_hook=strict_pairs)

def write(p,obj):
    Path(p).write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n')

def validator(instrument):
    folder = Path(instrument).resolve()
    sys.path.insert(0,str(folder))
    import maintainer
    if Path(maintainer.__file__).resolve().parent != folder:
        raise ValueError('another maintainer implementation is already imported; use the standalone bridge CLI')
    files = {str(p.relative_to(folder)):digest(p) for p in folder.rglob('*.py') if '__pycache__' not in p.parts}
    return maintainer.validate_receipt,files

def checked_run(path,instrument):
    path = Path(path).resolve()
    validate,files = validator(instrument)
    run = validate(path)
    workload_path = path.parent/'workload.json'
    workload = read(workload_path)
    if digest(workload_path) != run['workload_sha256']:
        raise ValueError('run workload SHA mismatch')
    cases = {c['id']:c for c in workload['cases']}
    if len(cases) != len(workload['cases']):
        raise ValueError('duplicate case ID')
    graders = []
    for c in cases.values():
        if 'steps' in c:
            raise ValueError('EvalPlus bridge currently supports single-step cases only')
        if c['expect']['kind'] != 'external':
            raise ValueError('all cases must use the external EvalPlus grader')
        graders.append(c['expect']['grader'])
    if not graders or any(g != graders[0] for g in graders):
        raise ValueError('one exact grader identity is required')
    grader = graders[0]
    if grader['name'] != 'EvalPlus' or grader['revision'] != '0.3.1':
        raise ValueError('unsupported grader')
    if grader.get('criterion') != 'humanevalplus-v0.1.10-base-and-plus-chat-complete-code-v1':
        raise ValueError('unsupported grading criterion')
    image = grader.get('artifact_sha256', '')
    if not isinstance(image, str) or len(image) != 64 or any(c not in '0123456789abcdef' for c in image):
        raise ValueError('EvalPlus image requires an explicit SHA256 identity')
    keys = set()
    for o in run['observations']:
        key = (o['task_id'],o['trial'],o['repetition'])
        if key in keys or key[0] not in cases:
            raise ValueError('duplicate or unknown observation')
        keys.add(key)
        if not o['attempts']:
            raise ValueError('observation lacks raw attempt')
        last = o['attempts'][-1]
        if hashlib.sha256(last['response_text'].encode()).hexdigest() != last['response_sha256']:
            raise ValueError('response SHA mismatch')
    return path,run,workload_path,grader,files

def normalizer_function(path):
    spec = importlib.util.spec_from_file_location('cantos_pinned_normalizer',path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.normalize

def prepare(a):
    path,run,workload_path,grader,files = checked_run(a.run,a.instrument)
    ref = Path(a.reference).resolve()
    normalizer = Path(a.normalizer).resolve()
    if digest(ref) != grader['reference_sha256']:
        raise ValueError('reference SHA mismatch')
    if digest(normalizer) != grader['normalizer_sha256']:
        raise ValueError('normalizer SHA mismatch')
    records = [json.loads(line,object_pairs_hook=strict_pairs) for line in ref.read_text().splitlines() if line]
    reference_ids = [r['task_id'] for r in records]
    if len(set(reference_ids)) != len(reference_ids):
        raise ValueError('duplicate reference case')
    wanted = {c['id'] for c in read(workload_path)['cases']}
    if set(reference_ids) != wanted:
        raise ValueError('reference cases must equal declared workload cases')
    # Only the previously pinned normalizer executes here, never model output.
    normalize = normalizer_function(normalizer)
    rows = []
    mapping = []
    task_index = defaultdict(int)
    for index,o in enumerate(run['observations']):
        attempt = o['attempts'][-1]
        solution = normalize(attempt['response_text'])
        if not isinstance(solution,str):
            raise ValueError('normalizer must return a string')
        rows.append({'task_id':o['task_id'],'solution':solution})
        mapping.append({'observation_index':index,'task_id':o['task_id'],'trial':o['trial'],
                        'repetition':o['repetition'],'task_solution_index':task_index[o['task_id']],
                        'response_sha256':attempt['response_sha256'],
                        'solution_sha256':hashlib.sha256(solution.encode()).hexdigest(),
                        'capture_eligible':o.get('accepted') is None})
        task_index[o['task_id']] += 1
    out = Path(a.out).resolve();out.mkdir(exist_ok=False,parents=True)
    shutil.copyfile(ref,out/'humaneval-reference.jsonl')
    shutil.copyfile(normalizer,out/'normalize.py')
    shutil.copyfile(workload_path,out/'workload.json')
    (out/'humaneval.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))
    write(out/'mapping.json',mapping)
    meta = {'schema':'cantos.maintainer.evalplus-prepared/1','run_sha256':digest(path),
            'workload_sha256':run['workload_sha256'],'grader':grader,
            'reference_md5':hashlib.md5(ref.read_bytes()).hexdigest(),
            'samples_sha256':digest(out/'humaneval.jsonl'),'mapping_sha256':digest(out/'mapping.json'),
            'bridge_sha256':digest(__file__),'validator_files':files,'observations':len(mapping)}
    write(out/'prepared.json',meta)
    print(json.dumps({'status':'prepared','out':str(out),'observations':len(mapping),
                      'run_sha256':meta['run_sha256'],'samples_sha256':meta['samples_sha256']}))

def bind(a):
    path,run,workload_path,grader,files = checked_run(a.run,a.instrument)
    prepared = Path(a.prepared).resolve()
    meta = read(prepared/'prepared.json')
    if meta['run_sha256'] != digest(path) or meta['workload_sha256'] != run['workload_sha256'] or meta['grader'] != grader:
        raise ValueError('prepared inputs belong to a different run/workload/grader')
    if meta['bridge_sha256'] != digest(__file__):
        raise ValueError('prepare/bind bridge implementation changed')
    if meta['validator_files'] != files:
        raise ValueError('prepare/bind raw evidence validator changed')
    for name,key in [('humaneval.jsonl','samples_sha256'),('mapping.json','mapping_sha256')]:
        if digest(prepared/name) != meta[key]:
            raise ValueError(name+' changed after prepare')
    if digest(prepared/'humaneval-reference.jsonl') != grader['reference_sha256'] or digest(prepared/'normalize.py') != grader['normalizer_sha256']:
        raise ValueError('reference or normalizer changed after prepare')
    if digest(prepared/'workload.json') != run['workload_sha256']:
        raise ValueError('prepared workload changed')
    reference_md5 = hashlib.md5((prepared/'humaneval-reference.jsonl').read_bytes()).hexdigest()
    if meta['reference_md5'] != reference_md5:
        raise ValueError('prepared reference MD5 differs from pinned bytes')
    normalize = normalizer_function(prepared/'normalize.py')
    image_receipt = prepared/'grader-image.json'
    if image_receipt.exists():
        images = read(image_receipt)
        if not isinstance(images, list) or len(images) != 1:
            raise ValueError('grader-image.json must inspect exactly one image')
        observed_id = images[0].get('Id', '')
        if observed_id != 'sha256:' + grader['artifact_sha256']:
            raise ValueError('observed grader image differs from declared image identity')
    results = read(a.results)
    if results['hash'] != reference_md5:
        raise ValueError('EvalPlus reference MD5 mismatch')
    samples = [json.loads(x,object_pairs_hook=strict_pairs) for x in (prepared/'humaneval.jsonl').read_text().splitlines() if x]
    mapping = read(prepared/'mapping.json')
    if len(samples) != len(mapping) or len(mapping) != len(run['observations']):
        raise ValueError('incomplete prepared observations')
    expected_counts = defaultdict(int)
    for row in mapping:expected_counts[row['task_id']] += 1
    if set(results['eval']) != set(expected_counts) or any(len(results['eval'][k]) != v for k,v in expected_counts.items()):
        raise ValueError('EvalPlus result coverage differs from workload observations')
    joined = []
    for i,(m,s,o) in enumerate(zip(mapping,samples,run['observations'])):
        key = (o['task_id'],o['trial'],o['repetition'])
        if (m['task_id'],m['trial'],m['repetition']) != key or m['observation_index'] != i:
            raise ValueError('mapping observation identity changed')
        last = o['attempts'][-1]
        if s['solution'] != normalize(last['response_text']):
            raise ValueError('prepared solution differs from normalized raw response')
        if m['response_sha256'] != last['response_sha256'] or m['capture_eligible'] != (o.get('accepted') is None):
            raise ValueError('mapping response/capture eligibility mismatch')
        grade = results['eval'][m['task_id']][m['task_solution_index']]
        if grade['solution'] != s['solution'] or hashlib.sha256(grade['solution'].encode()).hexdigest() != m['solution_sha256']:
            raise ValueError('grader solution differs from exact prepared response')
        if s['task_id'] != m['task_id'] or grade.get('task_id',m['task_id']) != m['task_id']:
            raise ValueError('grader task identity mismatch')
        for k in ('base_status','plus_status'):
            if grade[k] not in ('pass','fail','timeout'):
                raise ValueError('unknown evaluator outcome '+str(grade[k]))
        accepted = m['capture_eligible'] and grade['base_status'] == 'pass' and grade['plus_status'] == 'pass'
        joined.append({'task_id':m['task_id'],'trial':m['trial'],'repetition':m['repetition'],
                       'response_sha256':m['response_sha256'],'accepted':bool(accepted),
                       'evidence':['artifacts/humaneval_eval_results.json','artifacts/mapping.json',
                                   'artifacts/humaneval.jsonl','artifacts/evalplus.log']})
    out = Path(a.out).resolve();out.mkdir(exist_ok=False,parents=True)
    artifacts = out/'artifacts';artifacts.mkdir()
    for n in ('prepared.json','mapping.json','humaneval.jsonl','humaneval-reference.jsonl','normalize.py','workload.json'):
        shutil.copyfile(prepared/n,artifacts/n)
    for n in ('grader-image.json', 'invocation.json'):
        if (prepared/n).is_file():
            shutil.copyfile(prepared/n,artifacts/n)
    shutil.copyfile(a.results,artifacts/'humaneval_eval_results.json')
    shutil.copyfile(a.log,artifacts/'evalplus.log')
    shutil.copyfile(path,artifacts/'source-run.json')
    shutil.copyfile(__file__,artifacts/'evalplus_bridge.py')
    closure = [{'path':str(p.relative_to(out)),'sha256':digest(p),'bytes':p.stat().st_size} for p in sorted(artifacts.iterdir())]
    receipt = {'schema':'cantos.maintainer.grades/1','run_sha256':digest(path),
               'workload_sha256':run['workload_sha256'],'grader':grader,'results':joined,'artifacts':closure}
    write(out/'grades.json',receipt)
    print(json.dumps({'status':'bound','out':str(out/'grades.json'),'accepted':sum(x['accepted'] for x in joined),
                      'observations':len(joined),'sha256':digest(out/'grades.json')}))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command',required=True)
    prep = sub.add_parser('prepare')
    for arg in ('run','reference','normalizer','out'):prep.add_argument('--'+arg,required=True)
    prep.add_argument('--instrument',default=str(Path(__file__).resolve().parent),help='Directory containing maintainer.py and its pinned source closure')
    bound = sub.add_parser('bind')
    for arg in ('run','prepared','results','log','out'):bound.add_argument('--'+arg,required=True)
    bound.add_argument('--instrument',default=str(Path(__file__).resolve().parent),help='Same maintainer source used for prepare')
    a = p.parse_args()
    (prepare if a.command == 'prepare' else bind)(a)

if __name__=='__main__':main()
