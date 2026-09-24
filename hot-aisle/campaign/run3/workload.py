"""Freeze EvalPlus release prompts and references without executing dataset code."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from common import encoded, sha, verify, write_json

RELEASES = {
    'humaneval': ('v0.1.10', 'HumanEvalPlus', 164, 'HumanEval/'),
    'mbpp': ('v0.2.0', 'MbppPlus', 378, 'Mbpp/'),
}


def build(humaneval, mbpp, hashes, out, fixture=False):
    tasks, sources = [], {}
    for dataset, path in [('humaneval', humaneval), ('mbpp', mbpp)]:
        verify(path, hashes[dataset])
        release, name, count, prefix = RELEASES[dataset]
        raw = Path(path).read_bytes()
        data = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
        # Keep each release line verbatim: EvalPlus inputs contain IEEE specials (Infinity/NaN)
        # that strict JSON cannot re-encode; graders receive the upstream bytes unchanged.
        lines = [line for line in data.decode('utf-8').splitlines() if line.strip()]
        rows = [dict(json.loads(line), _raw=line) for line in lines]
        if not fixture and len(rows) != count:
            raise ValueError(f'{dataset}: expected {count} tasks, got {len(rows)}')
        sources[dataset] = {'release': release, 'sha256': sha(path),
                            'uncompressed_sha256': hashlib.sha256(data).hexdigest(),
                            'url': f'https://github.com/evalplus/{name.lower()}_release/releases/download/{release}/{name}.jsonl.gz'}
        for row in sorted(rows, key=lambda r: int(r['task_id'].split('/')[-1])):
            if not row['task_id'].startswith(prefix):
                raise ValueError('Unexpected task ID')
            for key in ('prompt', 'canonical_solution', 'entry_point', 'contract', 'base_input', 'plus_input', 'atol'):
                if key not in row:
                    raise ValueError('Missing grading reference field: ' + key)
            if not isinstance(row['prompt'], str) or not row['prompt'].strip():
                raise ValueError('Empty prompt')
            tasks.append({'task_id': row['task_id'], 'dataset': dataset, 'prompt': row['prompt'],
                          'grading_reference': {'release': release, 'source_sha256': sha(path),
                                                'record_sha256': hashlib.sha256(row['_raw'].encode('utf-8')).hexdigest(),
                                                'record_raw': row['_raw']}})
    if not tasks or len({t['task_id'] for t in tasks}) != len(tasks):
        raise ValueError('Empty or duplicate task set')
    artifact = {'schema': 'second-run/frozen-tasks@1', 'synthetic': fixture,
                'sources': sources, 'tasks': tasks}
    with Path(out).open('xb') as f:
        f.write(encoded(artifact))
    return artifact


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in RELEASES:
        p.add_argument('--' + name, required=True)
        p.add_argument('--' + name + '-sha256', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--fixture', action='store_true', help='Synthetic test data only; never production')
    a = p.parse_args()
    result = build(a.humaneval, a.mbpp, {'humaneval': a.humaneval_sha256, 'mbpp': a.mbpp_sha256}, a.out, a.fixture)
    print(f"Frozen {len(result['tasks'])} tasks; sha256={sha(a.out)}")


if __name__ == '__main__':
    main()
