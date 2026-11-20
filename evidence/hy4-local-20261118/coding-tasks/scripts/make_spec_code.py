#!/usr/bin/env python3
"""Operator spec for Hy4 flash Q3_K on W03 against Cantos's fixed 32 HumanEval+ tasks.

Workload and policy are copied unchanged from the maintainer-empirical session that defined them. The arm
identity is the one verified for the first local run; the protocol differs from that session's as declared
in DEVIATIONS.json. Usage: make_spec_code.py OUT_DIR
"""
import json, pathlib, shutil, subprocess, sys

R = pathlib.Path('/srv/w03/nvme-work/jobs/Cantos-Hy4-Local-First-20261118')
S = pathlib.Path('/mnt/w03data/Incoming/DataArray/Projects/Products/Cantos/sessions/maintainer-empirical-20261118')
out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=False)
shutil.copyfile(S / 'workload.json', out / 'workload.json')
shutil.copyfile(S / 'policy-llama.json', out / 'policy.json')
shutil.copyfile(R / 'run/spec-q3k-r01/weights-manifest.json', out / 'weights-manifest.json')
base = json.loads((R / 'run/spec-q3k-r01/spec.json').read_text())
earlier = json.loads((S / 'spec-llama.json').read_text())['protocol']
arm = base['baseline']
others = subprocess.run(['nvidia-smi', '--query-compute-apps=pid,name', '--format=csv,noheader'],
                        capture_output=True, text=True).stdout.strip()
arm['identity']['settings'].update(
    server_flags=(R / 'code-r01/server-flags.txt').read_text().strip(),
    reasoning_effort='no_think',
    co_tenancy='GPU compute processes at spec time: ' + (others or 'only this server'),
    power_and_cooling='power limits and fans unchanged as found',
    thermal_pacing='run/guard2.py pauses the server process at 76 C, resumes it at 68 C and stops it at 80 C; request times include pauses',
)
protocol = {'trials': 3, 'repeats': 1, 'concurrency': 1, 'seed': 1729, 'timeout_s': 600, 'max_tokens': 1024, 'warmup': 0,
            'extra_body': {'chat_template_kwargs': {'reasoning_effort': 'no_think'}}}
spec = {'schema': base['schema'], 'workload': 'workload.json', 'policy': 'policy.json', 'protocol': protocol,
        'baseline': arm, 'candidate': arm}
(out / 'spec.json').write_text(json.dumps(spec, indent=2))
(out / 'DEVIATIONS.json').write_text(json.dumps({
    'protocol_of_the_session_that_defined_the_workload': earlier,
    'protocol_used': protocol,
    'why': {'concurrency': 'one server slot', 'timeout_s': 'thermal pacing can pause a request',
            'extra_body': 'Hy4 is asked to answer without a thinking phase'},
    'arms': 'one arm only; no paired verdict is produced',
}, indent=2))
print(json.dumps({'spec': str(out / 'spec.json'), 'protocol': protocol}, indent=2))
