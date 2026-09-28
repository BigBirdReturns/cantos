"""Resolve an operator-selected Research Desk judgment to existing local work.

ResearchCore owns journal and dependency validity. The shared work runner owns
computation identity and execution. This bridge grants neither review standing
nor arbitrary commands; it returns a pinned native task for the caller to check.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
APP = HERE.parent / 'research-desk/app.html'
HELPER = HERE / 'change_owner.cjs'
PATH_ARGUMENTS = {'source', 'evidence', 'seats', 'availability', 'local_models', 'offers'}
PERMITTED_TASKS = frozenset({'provider-intake', 'benchmark-import', 'run-recompute',
    'run-diagnose', 'output-contract', 'record-change', 'source-correction',
    'tier-plan', 'pool-purchase'})


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve(task, base, allowed):
    if not isinstance(task, dict) or set(task) - {'id', 'actor', 'from_record', 'inputs'}:
        raise ValueError('A retained procedure request accepts id, actor, from_record and optional input locations only')
    ref = task.get('from_record')
    if not isinstance(ref, dict) or set(ref) != {'source', 'record_id', 'revision'}:
        raise ValueError('from_record requires source, record_id and revision')
    for name in ('source', 'record_id'):
        if not isinstance(ref[name], str) or not ref[name].strip():
            raise ValueError('from_record.' + name + ' must be a nonempty string')
    if type(ref['revision']) is not int or ref['revision'] < 1:
        raise ValueError('from_record.revision must be a positive integer')
    source = (Path(base) / ref['source']).resolve()
    paths = {'packet': source, 'bridge': Path(__file__), 'helper': HELPER, 'native_app': APP}
    before = {k: sha(p) for k, p in paths.items()}
    payload = {'task_class': 'research-procedure', 'source': str(source),
               'record_id': ref['record_id'], 'revision': ref['revision'],
               'expected_app_sha256': before['native_app']}
    try:
        p = subprocess.run(['node', str(HELPER)], input=json.dumps(payload),
                           capture_output=True, text=True, encoding='utf-8', timeout=60)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('Native Research Desk timed out; this judgment remains unresolved') from exc
    if p.returncode:
        raise ValueError('Native Research Desk refused: ' + p.stderr.strip())
    result = json.loads(p.stdout)
    after = {k: sha(p) for k, p in paths.items()}
    if before != after or result['source_sha256'] != before['packet']:
        raise ValueError('Research evidence changed during resolution; inspect again')
    native = copy.deepcopy(result['work']['task'])
    if native.get('task_class') not in allowed or native.get('task_class') not in PERMITTED_TASKS or 'from_record' in native:
        raise ValueError('Retained procedure must name an existing deterministic task class')
    if set(native) & {'id', 'actor'}:
        raise ValueError('Caller identity belongs in the invocation, not the retained procedure')
    locations = task.get('inputs', {})
    if not isinstance(locations, dict) or set(locations) - PATH_ARGUMENTS:
        raise ValueError('inputs may relocate only declared native input paths')
    if set(locations) - set(native):
        raise ValueError('inputs cannot introduce a new argument into the retained task')
    for key, value in locations.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Relocated input paths must be nonempty strings')
        native[key] = str((Path(base) / value).resolve())
    native['id'] = task['id']
    if 'actor' in task:
        native['actor'] = task['actor']
    return {'task': native, 'base': source.parent,
            'expected_key': result['work']['computation_key'], 'snapshot': before,
            'knowledge': {'record': result['record'],
                          'dependency': result['dependency'], 'review': result['review'],
                          'source_packet': str(source), 'source_sha256': before['packet'],
                          'procedure_reader_sha256': before['helper'],
                          'research_core_sha256': before['native_app'],
                          'boundary': result['boundary'],
                          'external_execution_authorized': False}}


def verify_unchanged(before, task, base, allowed):
    after = resolve(task, base, allowed)
    if before['snapshot'] != after['snapshot']:
        raise ValueError('Research judgment changed while work ran; retained computation is not a current handoff')
    return after
