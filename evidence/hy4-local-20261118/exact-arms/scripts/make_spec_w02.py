#!/usr/bin/env python3
"""Write the operator copy of the Hy4 precision spec for the two W02 processor arms.

Workload and policy are copied unchanged from the Cantos checkout. The protocol is the template's except the
client timeout, raised because these arms run on processors. Identity fields that the policy does not allow
to differ are written identically on both arms. Usage: make_spec_w02.py OUT_DIR
"""
import hashlib, json, pathlib, platform, shutil, subprocess, sys

J = pathlib.Path('/mnt/w03data/Incoming/DataArray/Scratch/hy4-exact-arms-20261118')
SOURCE = J / 'cantos/compute/maintainer/experiments/hy4-flash'
out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=False)
for name in ('workload.smoke.json', 'policy.precision.json'):
    shutil.copyfile(SOURCE / name, out / name)
template = json.loads((SOURCE / 'spec.precision.template.json').read_text())


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def git_blob_sha1(path):
    data = pathlib.Path(path).read_bytes()
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


verify = {arm: json.loads((J / 'meta' / (arm + '.VERIFIED')).read_text()) for arm in ('bf16', 'fp8')}
tokenizers = {arm: git_blob_sha1('/dev/shm/hy4/%s/tokenizer.json' % arm) for arm in ('bf16', 'fp8')}
assert tokenizers['bf16'] == tokenizers['fp8'], tokenizers
cpu = subprocess.run("lscpu | grep 'Model name' | cut -d: -f2", shell=True, capture_output=True, text=True).stdout.strip()
freeze = (J / 'meta/env.freeze.txt').read_text()
torch_version = [line for line in freeze.splitlines() if line.startswith('torch==')][0]
implementation = {
    'name': 'transformers publisher loader on processors behind serve_hy4.py',
    'revision': 'huggingface/transformers@%s (pull request 50903); %s; serve_hy4.py sha256:%s' % (
        (J / 'meta/transformers-commit.txt').read_text().strip(), torch_version, sha(J / 'serve_hy4.py')),
}
hardware = {
    'id': 'OCTO-W02 processors, no accelerator used',
    'description': '2 x %s, 112 threads; 1,971 GiB memory (256 GB DRAM in front of 2 TB Optane persistent memory, memory mode); kernel %s' % (cpu, platform.release()),
}
settings = {
    'server': 'serve_hy4.py, 56 torch threads, numactl --interleave=all, one request at a time, greedy decoding',
    'compute_dtype': 'float32 on both arms; the vendor recipe computes in bfloat16',
    'weights': 'loaded as float32: BF16 values widen exactly; FP8 weights are multiplied by their checkpoint block scales by the library',
    'fp8_input_rounding': 'where the checkpoint is FP8, inputs of the FP8-scaled matmuls are rounded through FP8 per row and per block of 128 (scale max/448), as the kernels-community/finegrained-fp8 kernels do; no such tensors exist in the BF16 checkpoint',
    'speculative_decoding': False,
    'reasoning_effort': 'no_think',
    'context_limit_enforced': False,
    'prefix_cache': 'none',
    'co_tenancy': 'W02 recorder services on the same processors; arms run one after the other, never together',
    'power_and_cooling': 'unchanged as found',
}


def arm(port, name, precision):
    return {'base_url': 'http://127.0.0.1:%d/v1' % port, 'model': 'hy4-flash', 'implementation_files': [],
            'identity': {'implementation': implementation,
                         'model': {'revision': verify[name]['revision'], 'sha256': verify[name]['weights_manifest_sha256']},
                         'tokenizer': {'revision': 'git-blob-sha1:' + tokenizers[name]},
                         'hardware': hardware, 'precision': precision, 'context_limit': 8192, 'settings': settings}}


protocol = dict(template['protocol'], timeout_s=600)
spec = {'schema': template['schema'], 'workload': 'workload.smoke.json', 'policy': 'policy.precision.json', 'protocol': protocol,
        'baseline': arm(18510, 'bf16', 'bf16_weights_fp32_compute'),
        'candidate': arm(18511, 'fp8', 'fp8_weights_fp8_rounded_inputs_fp32_compute')}
(out / 'spec.json').write_text(json.dumps(spec, indent=2))
(out / 'DEVIATIONS.json').write_text(json.dumps({
    'protocol.timeout_s': {'template': template['protocol']['timeout_s'], 'used': 600, 'why': 'processor arms answer in minutes, not seconds; 600 is the largest value the instrument accepts'},
    'runtime': 'transformers loader on processors instead of the pinned vLLM image on eight H200s',
    'compute': 'float32 arithmetic instead of bfloat16',
    'fp8': 'FP8 arithmetic emulated: library-dequantized FP8 weights and FP8-rounded inputs multiplied in float32',
    'tokenizer_template_declared': template['baseline']['identity']['tokenizer']['revision'],
    'tokenizer_observed': 'git-blob-sha1:' + tokenizers['bf16'],
}, indent=2))
print(json.dumps({'spec': str(out / 'spec.json'), 'protocol': protocol, 'tokenizer': tokenizers['bf16'],
                  'baseline_model': spec['baseline']['identity']['model'], 'candidate_model': spec['candidate']['identity']['model']}, indent=2))
