"""Judgment handoff for packets written by ResearchCore 1.0.2 (app/source/research-core.js).

Packets written by Research Desk 1.0.0 keep their original owner and identities
(test_task_research_handoff.py). A 1.0.2 journal must resolve through the 1.0.2
owner with the same packet, revision, dependency and expected-key checks, and the
real refusals must still fire. Saved reproduction: the Chapek second-run request
requests/06-from-record.json (sessions/chapek-seat-second-run-20261012) was held with
"Unsupported workspace version" before this path existed.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import research_owner
import work

CORE = ROOT / 'app/source/research-core.js'
DESK = ROOT / 'research-desk/app.html'


def put_records(records, packet=None, owner='core'):
    p = subprocess.run(['node', str(HERE / 'tests/research_fixture.cjs')],
        input=json.dumps({'records': records, 'packet': packet, 'owner': owner}),
        capture_output=True, text=True, encoding='utf-8', check=True)
    return json.loads(p.stdout)


class ResearchHandoff102(unittest.TestCase):
    def setUp(self):
        scratch = Path('S:/Scratch/Temp') if os.name == 'nt' else Path(tempfile.gettempdir())
        self.tmp = tempfile.TemporaryDirectory(prefix='research-handoff-102-', dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.store = self.base / 'store'
        self.raw = self.base / 'offers.jsonl'
        self.raw.write_bytes((ROOT / 'hot-aisle/campaign/providers/providers.jsonl').read_bytes())
        # 2.5, not 2.0: a JSON journal cannot keep an integral float as a float (see the
        # serialization test below), so declared scenario numbers must be written as JSON keeps them.
        self.task = {'task_class': 'provider-intake', 'source': 'offers.jsonl',
                     'offer_id': 'latitude-h100-1',
                     'price_scenario': {'rate_usd_per_gpu_hour': 2.5}}
        key = work.call_worker({**self.task, 'source': str(self.raw)}, self.base, 'describe')['key']
        self.key = key
        self.source = {'id': 'supply-source', 'kind': 'source', 'title': 'Retained source',
            'summary': 'Actual retained offer bytes; no fresh provider observation.',
            'tier': 'operator_supplied', 'disposition': 'observed', 'deps': [],
            'data': {'sha256': work.file_digest(self.raw)}}
        self.procedure = {'id': 'reprice-offer', 'kind': 'claim', 'title': 'Re-price this offer',
            'summary': 'Conditional price scenario through the native intake owner; nothing is acquired.',
            'tier': 'operator_supplied', 'disposition': 'observed',
            'deps': [{'id': 'supply-source', 'revision': 1}],
            'data': {'work': {'task': self.task, 'computation_key': key},
                     'retained': {'note': 'test fixture'}}}
        self.packet = put_records([self.source, self.procedure])
        self.assertEqual('1.0.2', self.packet['workspace']['version'])
        self.path = self.base / 'history.json'
        self.save(self.packet)
        self.request = {'tasks': [{'id': 'assessment', 'from_record': {
            'source': 'history.json', 'record_id': 'reprice-offer', 'revision': 1}}]}

    def save(self, packet):
        self.path.write_bytes(work.encoded(packet))

    def invoke(self, request=None, store=None):
        return work.run(request or self.request, self.base, store or self.store)

    def test_owner_selection_follows_declared_version(self):
        chosen = research_owner.owner_for(self.path)
        self.assertEqual(CORE, chosen['path'])
        self.assertEqual('1.0.2', chosen['version'])
        self.assertEqual(hashlib.sha256(CORE.read_bytes()).hexdigest(), chosen['sha256'])
        desk_packet = put_records([self.source], owner='desk')
        desk_path = self.base / 'desk.json'
        desk_path.write_bytes(work.encoded(desk_packet))
        self.assertEqual(DESK, research_owner.owner_for(desk_path)['path'])
        bad = copy.deepcopy(self.packet)
        bad['workspace']['version'] = '9.9.9'
        bad_path = self.base / 'bad.json'
        bad_path.write_bytes(work.encoded(bad))
        with self.assertRaises(ValueError):
            research_owner.owner_for(bad_path)

    def test_102_handoff_executes_reuses_and_binds_the_expected_key(self):
        first = self.invoke()
        self.assertEqual({'executed': 1, 'reused': 0, 'held': 0}, first['summary'])
        task = first['tasks'][0]
        self.assertEqual(self.key, task['key'])
        knowledge = task['knowledge']
        self.assertEqual('1.0.2', knowledge['workspace_version'])
        self.assertEqual('app/source/research-core.js', knowledge['research_core_path'])
        self.assertEqual(hashlib.sha256(CORE.read_bytes()).hexdigest(), knowledge['research_core_sha256'])
        self.assertTrue(knowledge['dependency']['current'])
        self.assertFalse(knowledge['review']['ready'])
        self.assertFalse(knowledge['external_execution_authorized'])
        self.assertEqual('reprice-offer', knowledge['record']['id'])
        request = copy.deepcopy(self.request)
        request['tasks'][0].update(id='fresh-label', actor='fresh-process')
        second = self.invoke(request)
        self.assertEqual({'executed': 0, 'reused': 1, 'held': 0}, second['summary'])
        self.assertEqual(task['key'], second['tasks'][0]['key'])
        direct = self.invoke({'tasks': [{'id': 'direct', **self.task}]})
        self.assertEqual('reused', direct['tasks'][0]['status'])
        self.assertEqual(task['key'], direct['tasks'][0]['key'])

    def test_102_stale_dependency_holds_until_explicit_successor(self):
        self.invoke()
        revised = {**self.source, 'summary': 'Synthetic correction to retained interpretation.'}
        self.save(put_records([revised], self.packet))
        held = self.invoke()['tasks'][0]
        self.assertEqual('held', held['status'])
        self.assertIn('stale or blocked', held['reason'])

    def test_102_superseded_revision_and_wrong_kind_hold(self):
        successor = {**self.procedure, 'summary': 'Successor revision of the same procedure.'}
        self.save(put_records([successor], self.packet))
        held = self.invoke()['tasks'][0]
        self.assertEqual('held', held['status'])
        self.assertIn('missing or superseded', held['reason'])
        wrong = copy.deepcopy(self.request)
        wrong['tasks'][0]['from_record'].update(record_id='supply-source', revision=1)
        held = self.invoke(wrong)['tasks'][0]
        self.assertEqual('held', held['status'])
        self.assertIn('explicit claim or conclusion', held['reason'])

    def test_102_tampered_packet_and_changed_binding_hold(self):
        tampered = copy.deepcopy(self.packet)
        tampered['workspace']['events'][0]['payload']['summary'] += ' x'
        self.save(tampered)
        held = self.invoke()['tasks'][0]
        self.assertEqual('held', held['status'])
        self.assertIn('Native Research Desk refused', held['reason'])
        self.save(self.packet)
        self.raw.write_bytes(self.raw.read_bytes().replace(b'"offer_id": "voltagepark-h100-ondemand"', b'"offer_id": "voltagepark-h100-ondemand-x"', 1))
        held = self.invoke()['tasks'][0]
        self.assertEqual('held', held['status'])
        self.assertIn('binding differs from current inputs', held['reason'])

    def test_integral_float_in_a_declared_parameter_is_a_different_computation(self):
        # Python keeps 2.0 as "2.0" in the identity; the JSON journal stores it as 2. A key
        # computed from 2.0 therefore does not match the record's task, and the binding is held
        # rather than silently reused. Authors write such numbers as JSON keeps them.
        float_task = {**self.task, 'price_scenario': {'rate_usd_per_gpu_hour': 2.0}}
        key = work.call_worker({**float_task, 'source': str(self.raw)}, self.base, 'describe')['key']
        procedure = {**self.procedure, 'id': 'reprice-float',
                     'data': {'work': {'task': float_task, 'computation_key': key}}}
        self.save(put_records([procedure], self.packet))
        request = {'tasks': [{'id': 'float', 'from_record': {
            'source': 'history.json', 'record_id': 'reprice-float', 'revision': 1}}]}
        held = self.invoke(request)['tasks'][0]
        self.assertEqual('held', held['status'])
        self.assertIn('binding differs from current inputs', held['reason'])
        int_key = work.call_worker({**float_task, 'source': str(self.raw),
                                    'price_scenario': {'rate_usd_per_gpu_hour': 2}}, self.base, 'describe')['key']
        self.assertNotEqual(key, int_key)

    def test_100_packets_keep_their_desk_owner(self):
        desk_task = {'task_class': 'provider-intake', 'source': str(self.raw), 'offer_id': 'latitude-h100-1'}
        key = work.call_worker(desk_task, self.base, 'describe')['key']
        conclusion = {'id': 'assess-offer', 'kind': 'conclusion', 'title': 'Inspect this source',
            'summary': 'Read the offer through the native owner; do not acquire capacity.',
            'tier': 'proposal', 'disposition': 'draft',
            'deps': [{'id': 'supply-source', 'revision': 1}],
            'data': {'work': {'task': desk_task, 'computation_key': key}}}
        desk_packet = put_records([self.source, conclusion], owner='desk')
        self.assertEqual('1.0.0', desk_packet['workspace']['version'])
        desk_path = self.base / 'desk.json'
        desk_path.write_bytes(work.encoded(desk_packet))
        result = self.invoke({'tasks': [{'id': 'desk', 'from_record': {
            'source': 'desk.json', 'record_id': 'assess-offer', 'revision': 1}}]})
        task = result['tasks'][0]
        self.assertEqual('executed', task['status'])
        self.assertEqual('1.0.0', task['knowledge']['workspace_version'])
        self.assertEqual('research-desk/app.html', task['knowledge']['research_core_path'])
        self.assertEqual(hashlib.sha256(DESK.read_bytes()).hexdigest(), task['knowledge']['research_core_sha256'])


if __name__ == '__main__':
    unittest.main()
