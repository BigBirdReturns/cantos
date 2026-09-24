"""Prepare EvalPlus samples and join exact per-task result order to requests."""
import argparse
import hashlib
from pathlib import Path
import statistics
from common import encoded, jsonl, read_json, sha, verify, write_json
from replay import buckets, recover

CRITERION = 'evalplus-0.3.1-human-v0.1.10-mbpp-v0.2.0-base-and-plus-raw-completion-v1'


def bound_inputs(tasks_path, requests_path, detailed_path):
    tasks = read_json(tasks_path)
    detailed = read_json(detailed_path)
    if detailed['metadata']['workload_id'] != 'sha256:' + sha(tasks_path):
        raise ValueError('Tasks differ from replay identity')
    verify(requests_path, detailed['metadata']['requests_sha256'])
    rows = jsonl(requests_path)
    if [r['request_index'] for r in rows] != list(range(len(rows))):
        raise ValueError('Request order is not contiguous')
    if detailed['errors'] != [r['error'] for r in rows]:
        raise ValueError('Detailed request outcomes disagree')
    return tasks, rows, detailed


def prepare(tasks_path, requests_path, detailed_path, out):
    tasks, rows, detailed = bound_inputs(tasks_path, requests_path, detailed_path)
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    by_id = {t['task_id']: t for t in tasks['tasks']}
    mapping = {'schema': 'second-run/grading-map@1', 'source_sha256': sha(detailed_path),
               'requests_sha256': sha(requests_path), 'tasks_sha256': sha(tasks_path), 'datasets': {}}
    for dataset in ('humaneval', 'mbpp'):
        samples, ids, seen = [], [], set()
        for row in rows:
            task = by_id[row['task_id']]
            if task['dataset'] != dataset:
                continue
            solution = task['prompt'] + row['output_text'] if not row['error'] else 'pass\n'
            samples.append({'task_id': task['task_id'], 'solution': solution})
            ids.append(row['request_index']); seen.add(task['task_id'])
        for task in tasks['tasks']:
            if task['dataset'] == dataset and task['task_id'] not in seen:
                samples.append({'task_id': task['task_id'], 'solution': 'pass\n'})
                ids.append(None)
        sample_path = out / (dataset + '.jsonl')
        sample_path.write_bytes(b''.join(encoded(s) for s in samples))
        refs = [t['grading_reference']['record_raw'] for t in tasks['tasks'] if t['dataset'] == dataset]
        ref_path = out / (dataset + '-reference.jsonl')
        ref_path.write_bytes(b''.join(r.encode('utf-8') + b'\n' for r in refs))
        mapping['datasets'][dataset] = {'request_indices': ids, 'samples_sha256': sha(sample_path),
                                        'reference_sha256': sha(ref_path),
                                        'reference_md5': hashlib.md5(ref_path.read_bytes()).hexdigest()}
    write_json(out / 'mapping.json', mapping)
    return mapping


def join(tasks_path, requests_path, detailed_path, directory, output):
    tasks, rows, detailed = bound_inputs(tasks_path, requests_path, detailed_path)
    directory = Path(directory); mapping = read_json(directory / 'mapping.json')
    for key, path in [('source_sha256', detailed_path), ('requests_sha256', requests_path), ('tasks_sha256', tasks_path)]:
        verify(path, mapping[key])
    passed, covered, result_hashes = [False] * len(rows), set(), {}
    for dataset, meta in mapping['datasets'].items():
        sample_path = directory / (dataset + '.jsonl')
        verify(sample_path, meta['samples_sha256'])
        verify(directory / (dataset + '-reference.jsonl'), meta['reference_sha256'])
        result_path = directory / (dataset + '_eval_results.json')
        results = read_json(result_path)
        if results.get('hash') != meta['reference_md5']:
            raise ValueError('EvalPlus graded a different reference dataset')
        result_hashes[dataset] = sha(result_path)
        samples = jsonl(sample_path)
        if len(samples) != len(meta['request_indices']):
            raise ValueError('Sample mapping length mismatch')
        positions = {}
        for sample, n in zip(samples, meta['request_indices']):
            task_id = sample['task_id']; pos = positions.get(task_id, 0)
            candidates = results['eval'].get(task_id, [])
            if pos >= len(candidates):
                raise ValueError('Missing EvalPlus sample result')
            result = candidates[pos]; positions[task_id] = pos + 1
            if result['task_id'] != task_id or result['solution'] != sample['solution']:
                raise ValueError('EvalPlus result order/content mismatch')
            if result.get('base_status') not in ('pass', 'fail', 'timeout') or result.get('plus_status') not in ('pass', 'fail', 'timeout'):
                raise ValueError('Incomplete/unknown EvalPlus status')
            if n is not None:
                if n in covered or rows[n]['task_id'] != task_id:
                    raise ValueError('Duplicate or mismatched mapped request')
                covered.add(n)
                passed[n] = not rows[n]['error'] and result['base_status'] == result['plus_status'] == 'pass'
        if set(results['eval']) != set(positions) or any(len(results['eval'][k]) != v for k, v in positions.items()):
            raise ValueError('Extra or missing EvalPlus results')
    if covered != set(range(len(rows))):
        raise ValueError('Incomplete grading coverage')
    sidecar = {'schema': 'hot-aisle/request-evaluation@1', 'source_sha256': sha(detailed_path),
               'record_index': 0, 'passed': passed, 'evaluator': 'EvalPlus 0.3.1',
               'criterion_id': CRITERION, 'result_sha256': result_hashes,
               'mapping_sha256': sha(directory / 'mapping.json'), 'synthetic': detailed['synthetic']}
    write_json(output, sidecar)
    return sidecar


def summary(replay_dir, sidecar_path, detailed_path, output):
    plan, rows = recover(replay_dir)
    sidecar = read_json(sidecar_path)
    verify(detailed_path, sidecar['source_sha256'])
    detailed = read_json(detailed_path)
    if hashlib.sha256(b''.join(encoded(r) for r in rows)).hexdigest() != detailed['metadata']['requests_sha256']:
        raise ValueError('Replay differs from evaluated requests')
    passed = sidecar['passed']
    if len(passed) != len(rows) or any(type(v) is not bool for v in passed):
        raise ValueError('Invalid evaluation mask')
    b = buckets(plan, rows, passed)
    rates = [x['accepted']/x['duration_s'] for x in b]
    first = sum(x['accepted'] for x in b[:3]); last = sum(x['accepted'] for x in b[-3:])
    classes = {}
    for prefix in ('HumanEval/', 'Mbpp/'):
        group = [r for r in rows if r['task_id'].startswith(prefix)]
        classes[prefix.rstrip('/')] = {'attempted': len(group),
            'completed': sum(not r['error'] for r in group),
            'correct': sum(passed[r['request_index']] for r in group),
            'accepted': sum(passed[r['request_index']] and not r['error']
                and r['first_token_ts']-r['scheduled_ts'] <= 1
                and r['end_ts']-r['scheduled_ts'] <= 60 for r in group)}
    write_json(output, {'buckets': b, 'minimum_accepted_per_s': min(rates),
                        'median_accepted_per_s': statistics.median(rates),
                        'last_quarter_over_first_quarter': last/first if first else None,
                        'zero_first_quarter': first == 0, 'task_classes': classes})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for command in ('prepare', 'join'):
        q = sub.add_parser(command)
        for arg in ('tasks', 'requests', 'detailed', 'directory'):
            q.add_argument(arg)
        if command == 'join':
            q.add_argument('output')
    q = sub.add_parser('summary')
    for arg in ('replay', 'sidecar', 'detailed', 'output'):
        q.add_argument(arg)
    a = p.parse_args()
    if a.command == 'prepare':
        prepare(a.tasks, a.requests, a.detailed, a.directory)
    elif a.command == 'join':
        join(a.tasks, a.requests, a.detailed, a.directory, a.output)
    else:
        summary(a.replay, a.sidecar, a.detailed, a.output)
