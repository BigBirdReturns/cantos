#!/usr/bin/env python3
"""Write the operator copy of the Hy4 smoke spec for the local Q3_K arm.

Copies the published workload and policy unchanged from the Cantos checkout, writes a local
weights manifest from the verified download, and binds the identity that was actually served.
Usage: make_spec.py OUT_DIR PORT
"""
import hashlib, json, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path('/srv/w03/nvme-work/jobs/Cantos-Hy4-Local-First-20261118')
SOURCE = ROOT / 'cantos/compute/maintainer/experiments/hy4-flash'
out, port = pathlib.Path(sys.argv[1]), int(sys.argv[2])
out.mkdir(parents=True, exist_ok=False)

for name in ('workload.smoke.json', 'policy.precision.json'):
    shutil.copyfile(SOURCE / name, out / name)
template = json.loads((SOURCE / 'spec.precision.template.json').read_text())

repo_revision = 'f8def04a2fc74edb21c53166dad5f94113baab4a'
files = []
for line in (ROOT / 'meta/sha256.observed.txt').read_text().splitlines():
    digest, name = line.split()
    files.append({'path': name, 'sha256': digest, 'bytes': (ROOT / 'models' / name).stat().st_size})
manifest = {'repository': 'AngelSlim/Hy4-flash-GGUF', 'revision': repo_revision,
            'verified_against': 'Hugging Face LFS object ids at that revision', 'files': files}
manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode()
(out / 'weights-manifest.json').write_bytes(manifest_bytes)

llama_commit = (ROOT / 'meta/llama-commit.txt').read_text().split()[0]
flags = (ROOT / 'run/server-flags.txt').read_text().strip()
gpus = subprocess.run(['nvidia-smi', '--query-gpu=uuid,name,memory.total,driver_version,power.limit',
                       '--format=csv,noheader'], capture_output=True, text=True).stdout.strip().splitlines()
uuids = [row.split(',')[0].strip() for row in gpus]
others = subprocess.run(['nvidia-smi', '--query-compute-apps=pid,name', '--format=csv,noheader'],
                        capture_output=True, text=True).stdout.strip()

arm = {
    'base_url': 'http://127.0.0.1:%d/v1' % port,
    'model': 'hy4-flash',
    'implementation_files': [],
    'identity': {
        'implementation': {'name': 'llama.cpp llama-server, unmerged pull request 32517',
                           'revision': 'ggml-org/llama.cpp@' + llama_commit},
        'model': {'revision': 'AngelSlim/Hy4-flash-GGUF@' + repo_revision,
                  'sha256': hashlib.sha256(manifest_bytes).hexdigest()},
        'tokenizer': {'revision': 'embedded in GGUF part 1 sha256:' + files[0]['sha256']},
        'hardware': {'id': ','.join(uuids),
                     'description': 'OCTO-W03: Intel Core i9-10900X, 123 GiB RAM; ' + '; '.join(gpus) +
                                    '; CUDA 13.4; interconnect not measured'},
        'precision': 'gguf_q3_k_mixed_publisher_quantized',
        'context_limit': 8192,
        'settings': {
            'server_flags': flags,
            'speculative_decoding': False,
            'reasoning_effort': 'no_think',
            'prefix_cache': 'llama-server default slot prompt cache, one slot',
            'co_tenancy': 'GPU compute processes at spec time: ' + (others or 'only this server'),
            'power_and_cooling': 'unchanged as found; a guard stops this server at 80 C',
            'effective_runtime': 'see server.log beside this run for the loaded backend and tensor placement',
        },
    },
}
spec = {'schema': template['schema'], 'workload': 'workload.smoke.json', 'policy': 'policy.precision.json',
        'protocol': template['protocol'], 'baseline': arm, 'candidate': arm}
(out / 'spec.json').write_text(json.dumps(spec, indent=2))
print(json.dumps({'spec': str(out / 'spec.json'), 'weights_manifest_sha256': arm['identity']['model']['sha256'],
                  'protocol': spec['protocol']}, indent=2))
