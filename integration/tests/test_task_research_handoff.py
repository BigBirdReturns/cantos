"""Real native ResearchCore authoring -> existing operations -> checked reuse."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import work


def put_records(records, packet=None):
    p = subprocess.run(['node', str(HERE/'tests/research_fixture.cjs')],
        input=json.dumps({'records': records, 'packet': packet}),
        capture_output=True, text=True, encoding='utf-8', check=True)
    return json.loads(p.stdout)


class ResearchHandoff(unittest.TestCase):
    def setUp(self):
        scratch = Path('S:/Scratch/Temp') if os.name == 'nt' else Path(tempfile.gettempdir())
        self.tmp = tempfile.TemporaryDirectory(prefix='research-handoff-', dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.store = self.base/'store'
        self.raw = self.base/'offers.jsonl'
        self.raw.write_bytes((ROOT/'hot-aisle/campaign/providers/providers.jsonl').read_bytes())
        self.task = {'task_class': 'provider-intake', 'source': str(self.raw),
                     'offer_id': 'latitude-h100-1',
                     'availability_review': {'as_of': '2026-09-28T18:00:00Z', 'max_age_hours': 24}}
        key = work.call_worker(self.task, self.base, 'describe')['key']
        self.source = {'id': 'supply-source', 'kind': 'source', 'title': 'Retained source',
            'summary': 'Actual retained offer bytes; no fresh provider observation.',
            'tier': 'operator_supplied', 'disposition': 'observed', 'deps': [],
            'data': {'sha256': work.file_digest(self.raw)}}
        self.conclusion = {'id': 'assess-offer', 'kind': 'conclusion', 'title': 'Inspect this source',
            'summary': 'Read the offer through the native owner; do not acquire capacity.',
            'tier': 'proposal', 'disposition': 'draft',
            'deps': [{'id': 'supply-source', 'revision': 1}],
            'data': {'rationale': 'Source qualifications must survive the next calculation.',
                     'work': {'task': self.task, 'computation_key': key}}}
        self.packet = put_records([self.source, self.conclusion])
        self.path = self.base/'history.json'
        self.save(self.packet)
        self.request = {'tasks': [{'id': 'assessment', 'from_record': {
            'source': str(self.path), 'record_id': 'assess-offer', 'revision': 1}}]}

    def save(self, packet):
        self.path.write_bytes(work.encoded(packet))

    def invoke(self, request=None):
        return work.run(request or self.request, self.base, self.store)

    def test_native_handoff_and_fresh_caller_reuse(self):
        first = self.invoke()
        self.assertEqual({'executed': 1, 'reused': 0, 'held': 0}, first['summary'])
        task = first['tasks'][0]
        self.assertTrue(task['knowledge']['dependency']['current'])
        self.assertFalse(task['knowledge']['review']['ready'])
        self.assertIsNone(task['knowledge']['review']['review'])
        self.assertFalse(task['knowledge']['external_execution_authorized'])
        self.assertEqual('assess-offer', task['knowledge']['record']['id'])
        request = copy.deepcopy(self.request)
        request['tasks'][0].update(id='fresh-label', actor='fresh-process')
        second = self.invoke(request)
        self.assertEqual({'executed': 0, 'reused': 1, 'held': 0}, second['summary'])
        self.assertEqual(task['key'], second['tasks'][0]['key'])
        direct = self.invoke({'tasks': [{'id': 'direct', **self.task}]})
        self.assertEqual('reused', direct['tasks'][0]['status'])
        self.assertEqual(0, direct['model_calls'])
        self.assertEqual(0, direct['gpu_runs'])

    def test_corrected_source_holds_until_explicit_successor(self):
        first = self.invoke()['tasks'][0]
        old_result = Path(first['result']).read_bytes()
        revised_source = {**self.source, 'summary': 'Synthetic correction to retained interpretation.'}
        changed = put_records([revised_source], self.packet)
        self.save(changed)
        held = self.invoke()['tasks'][0]
        self.assertEqual('held', held['status'])
        self.assertIn('stale or blocked', held['reason'])
