"""Qualify the extracted public deployment job through its real HTTP boundary."""
from pathlib import Path
import base64
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import threading
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def main():
    sys.path.insert(0, str(ROOT / 'compute/maintainer'))
    from packets import unpack_owner
    with tempfile.TemporaryDirectory(prefix='cantos-deployment-recipient-') as temporary:
        root = Path(temporary)
        package = unpack_owner(ROOT / 'public/open-compute/open-compute-workbench.zip', root / 'owner')
        spec = importlib.util.spec_from_file_location('deployment_recipient_engine', package / 'engine/engine.py')
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)
        common = engine._deployments._native('common')
        job = engine._deployments._native('job')
        deployment = engine._deployments._native('deployment')
        original = root / 'original'
        original.mkdir()
        engine._comparisons.unpack((package / 'comparisons/frozen-vllm.zip').read_bytes(), original)
        retained = root / 'retained'
        inputs = retained / 'inputs'
        inputs.mkdir(parents=True)
        runs = {}
        for side in ('baseline', 'candidate'):
            target = retained / 'native/capture' / side
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(original / side, target)
            runs[side] = target / 'run.json'
            shutil.copytree(original / (side + '_grades'), inputs / (side + '_grades'))
        shutil.copyfile(original / 'baseline/workload.json', inputs / 'workload.json')
        shutil.copyfile(original / 'policy.json', inputs / 'policy.json')
        raw = {side: common.load(path) for side, path in runs.items()}
        common.write(inputs / 'spec.json', {'schema': 'cantos.maintainer.spec/1', 'workload': 'workload.json',
            'policy': 'policy.json', 'protocol': raw['baseline']['protocol'],
            **{side: value['configuration'] for side, value in raw.items()}})
        contract = {'schema': 'cantos.deployment-job/1', 'id': 'retained-real-recipient-qualification',
            'comparison': {'spec': 'inputs/spec.json', 'baseline_grades': 'inputs/baseline_grades/grades.json',
                'candidate_grades': 'inputs/candidate_grades/grades.json'},
            'decision': {'objective': 'min_cost_per_accepted', 'economics_required': True,
                'operational_requirements': [{'id': 'recovery', 'check_id': 'owned_loopback.recovery_max_s',
                    'operator': 'lte', 'threshold': 2, 'required': True, 'max_age_s': 86400, 'allowed_basis': ['observed']}]},
            'arms': {side: {'operations': [], 'resources': None} for side in runs}}
        common.write(retained / 'job.json', contract)
        common.write(retained / 'input-hashes.json', {path.relative_to(retained).as_posix(): common.sha256_file(path)
            for path in inputs.rglob('*') if path.is_file()})
        native = engine._comparisons._native().analyze_receipts(runs['baseline'], runs['candidate'], inputs / 'policy.json',
            retained / 'initial-analysis', baseline_grades=inputs / 'baseline_grades/grades.json',
            candidate_grades=inputs / 'candidate_grades/grades.json')
        decision = deployment.decide_deployment(contract, native, runs,
            {side: [] for side in runs}, {side: None for side in runs})
        common.write(retained / 'decision.json', decision)
        # Upgrade retained observations through the real data-only lifecycle.
        # An authored decision file alone must not certify a completed job.
        completed = root / 'completed-job'
        decision = job.decide_job(retained, completed)
        manifest = job.export_job(completed, root / 'bundle')
        ledger = engine.Ledger(package, root / 'store')
        server = engine.ExclusiveHTTPServer(('127.0.0.1', 0), engine.handler_for(ledger))
        origin = 'http://127.0.0.1:' + str(server.server_port)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def request(path, value=None, binary=False):
            req = urllib.request.Request(origin + path, data=None if value is None else json.dumps(value).encode(),
                headers={'Origin': origin, 'Content-Type': 'application/json'})
            with opener.open(req, timeout=120) as response:
                raw = response.read()
                return raw if binary else json.loads(raw)

        try:
            upload = request('/api/deployment/begin', {'manifest': manifest})['upload_id']
            for part in manifest['parts']:
                answer = request('/api/deployment/part', {'upload_id': upload, 'name': part['path'],
                    'base64': base64.b64encode((root / 'bundle' / part['path']).read_bytes()).decode()})
                assert answer['accepted']
            record = request('/api/deployment/finish', {'upload_id': upload})
            assert record['kind'] == 'deployment-decision'
            assert record['deployment_decision']['state'] == 'INCOMPARABLE'
            assert record['native_verdict'] == 'incomparable'
            assert record['native']['policy']['min_baseline_acceptance'] == .8
            assert all(record['native'][side]['accepted_tasks'] == 21 and record['native'][side]['total_tasks'] == 96 for side in runs)
            assert any(item['required'] for item in record['deployment_decision']['unknowns'])
            assert record['execution']['inference_requests'] == record['execution']['grading_executions'] == 0
            assert request('/api/export/' + record['id']) == record
            assert request('/api/deployment/' + record['id'] + '/manifest') == manifest
            for part in manifest['parts']:
                raw = request('/api/deployment/' + record['id'] + '/part/' + part['path'], binary=True)
                assert hashlib.sha256(raw).hexdigest() == part['sha256']
            reopened = engine.Ledger(package, root / 'store')
            assert reopened.store.get('decisions', record['id']) == record
            assert request('/api/deployment/finish', {'upload_id': upload}) == record
            print(json.dumps({'status': 'passed', 'state': 'INCOMPARABLE', 'accepted_per_arm': 21,
                'offered_per_arm': 96, 'parts': len(manifest['parts']), 'restart_preserved': True,
                'new_inference_requests': 0, 'boundary': 'Extracted public job export, real HTTP chunk import, trusted native join, history and exact part download.'}))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
