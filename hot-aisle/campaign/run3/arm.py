"""Bounded on-seat Run 3 orchestration. No provisioning or remote access."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from common import IMAGES, MODEL, REVISION, encoded, read_json, sha, verify, write_json
from convert import convert
from replay import schedule

WATCHDOG = 6600  # 110 min, includes cleanup; work budget is 105 min.
REPLAY_TIMEOUT = 3720  # 3600 arrivals + 60 drain + 60 parse/load/exit.
HERE = Path(__file__).resolve().parent


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def backends(log):
    # Capture only the selected token, never the rejected or candidate list.
    attention, linear = [], []
    for line in log.splitlines():
        override = re.search(r'Overriding with\s+([A-Z][A-Z0-9_]+)\b', line)
        if override:
            attention.append(override.group(1))
        elif not re.search(r'incompatible|not supported', line, re.I):
            selected = re.search(r'(?:Using|Selected)\s+([A-Z][A-Z0-9_]+)\s+(?:attention\s+)?backend\b', line)
            if selected:
                attention.append(selected.group(1))
        if re.search(r'Using|Selected', line, re.I):
            linear.extend(re.findall(r'\b[A-Za-z0-9_]*(?:LinearKernel|ScaledMMLinearKernel)\b', line))
    return {'attention_backend': list(dict.fromkeys(attention)) or ['UNVERIFIED'],
            'linear_kernel': list(dict.fromkeys(linear)) or ['UNVERIFIED']}


def backend_holds(selected):
    known = {'ROCM_ATTN', 'ROCM_AITER_FA', 'ROCM_AITER_UNIFIED_ATTN',
             'FLASH_ATTN', 'FLASHINFER', 'TRITON_ATTN', 'FLEX_ATTENTION'}
    holds = []
    if any(x not in known for x in selected['attention_backend']):
        holds.append('HOLD: attention backend UNVERIFIED; review serve.log')
    if 'UNVERIFIED' in selected['linear_kernel']:
        holds.append('HOLD: linear kernel UNVERIFIED; review serve.log')
    return holds


def require_tier_backend(tier, selected):
    if tier == 'T1' and selected['attention_backend'] != ['ROCM_AITER_FA']:
        raise RuntimeError('T1 did not select ROCM_AITER_FA')


def serve_command(kind, tier, name, cache):
    if (kind, tier) not in [('amd', 'T0'), ('amd', 'T1'), ('nvidia', 'T0')]:
        raise ValueError('Supported arms: amd T0, amd T1, nvidia T0')
    devices = ['--gpus', 'all', '--ipc=host'] if kind == 'nvidia' else [
        '--device=/dev/kfd', '--device=/dev/dri', '--group-add', 'video', '--ipc=host',
        '--security-opt', 'seccomp=unconfined', '--cap-add=SYS_PTRACE', '-e', 'VLLM_ROCM_USE_AITER=1']
    flags = ['--max-model-len', '16384', '--max-num-seqs', '256', '--gpu-memory-utilization', '0.90',
             '--tensor-parallel-size', '1', '--no-enable-prefix-caching']
    if tier == 'T1':
        flags += ['--attention-backend', 'ROCM_AITER_FA']
    return ['docker', 'run', '-d', '--name', name, '--network', 'host', *devices,
            '-v', str(cache) + ':/root/.cache/huggingface', '--entrypoint', 'vllm', IMAGES[kind],
            'serve', MODEL, '--revision', REVISION, '--tokenizer-revision', REVISION,
            '--served-model-name', MODEL, '--host', '127.0.0.1', '--port', '8000', *flags]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('kind', choices=['amd', 'nvidia']); p.add_argument('tier', choices=['T0', 'T1'])
    for arg in ('tasks', 'tasks-sha256', 'trace', 'trace-sha256', 'start', 'out', 'hf-cache', 't-ssh'):
        p.add_argument('--' + arg, required=True)
    p.add_argument('--rate-factor', type=float, required=True)
    p.add_argument('--approved-run', action='store_true')
    a = p.parse_args()
    if not a.approved_run:
        p.error('An approved run is required; this build alone grants no rental authority')
    verify(a.tasks, a.tasks_sha256); verify(a.trace, a.trace_sha256)
    tasks = read_json(a.tasks)
    if tasks['synthetic'] or len(tasks['tasks']) != 542:
        p.error('Full non-synthetic frozen 542-task workload required')
    ssh = dt.datetime.fromisoformat(a.t_ssh.replace('Z', '+00:00'))
    if ssh.tzinfo is None or ssh.timestamp() > time.time():
        p.error('t_ssh must be an observed timezone-qualified past timestamp')
    schedule(a.trace, a.trace_sha256, a.start, a.rate_factor)
    out = Path(a.out).resolve(); cache = Path(a.hf_cache).resolve()
    name = 'run3-' + a.kind + '-' + a.tier.lower() + '-' + str(os.getpid())
    command = serve_command(a.kind, a.tier, name, cache)
    out.mkdir(parents=True, exist_ok=False); cache.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(a.tasks, out / 'tasks.json')
    write_json(out / 'invocation.json', {'kind': a.kind, 'tier': a.tier, 'argv': command,
        'tasks_sha256': a.tasks_sha256, 'trace_sha256': a.trace_sha256,
        'trace_start': a.start, 'rate_factor': a.rate_factor, 'watchdog_s': WATCHDOG})
    times = {k: None for k in ('t_request', 't_ssh', 't_ready', 't_work_start', 't_work_end', 't_released')}
    times.update(t_ssh=a.t_ssh, t_script_start=utc())
    write_json(out / 'ledger-times.json', times)
    started = time.monotonic(); created = False; child = None; status = 'failed'
    def run(cmd, seconds, check=True):
        left = min(seconds, 6300 - (time.monotonic()-started))
        if left <= 0:
            raise TimeoutError('Work watchdog reached')
        return subprocess.run(cmd, capture_output=True, timeout=left, check=check)
    def abort(*_):
        raise TimeoutError('Watchdog/signal; preserving evidence')
    signal.signal(signal.SIGTERM, abort); signal.signal(signal.SIGINT, abort)
    if hasattr(signal, 'SIGALRM'):
        signal.signal(signal.SIGALRM, abort); signal.alarm(6300)
    try:
        # One combined 40-minute budget includes image pull, model download and health.
        startup_deadline = started + 2400
        r = run(['docker', 'pull', IMAGES[a.kind]], 2400)
        (out / 'pull.log').write_bytes(r.stdout + r.stderr)
        # Cleanup is attempted even if docker run times out after creating its container.
        created = True
        r = run(command, max(1, startup_deadline-time.monotonic()))
        (out / 'container-id.txt').write_bytes(r.stdout)
        while True:
            if time.monotonic() >= startup_deadline:
                raise TimeoutError('No health within 40 minutes including pull/download')
            try:
                with urllib.request.urlopen('http://127.0.0.1:8000/v1/models', timeout=2) as response:
                    models = json.load(response)
                    if any(x['id'] == MODEL for x in models['data']):
                        break
            except (OSError, ValueError, KeyError):
                pass
            state = run(['docker', 'inspect', '-f', '{{.State.Running}}', name], 5)
            if state.stdout.strip() != b'true':
                raise RuntimeError('Serving container exited')
            time.sleep(2)
        times['t_ready'] = utc(); write_json(out / 'ledger-times.json', times)
        log = run(['docker', 'logs', name], 10)
        (out / 'serve.log').write_bytes(log.stdout + log.stderr)
        selected = backends((log.stdout + log.stderr).decode('utf-8', errors='replace'))
        env = {'schema': 'second-run/arm-environment@1', 'run': 'run3', 'kind': a.kind,
               'tier': a.tier, 'image': IMAGES[a.kind], 'model': MODEL, 'revision': REVISION,
               'gpu_count': 1, 'tensor_parallel': 1, 'serve_argv': command,
               'holds': backend_holds(selected), **selected}
        r = run(['docker', 'image', 'inspect', IMAGES[a.kind]], 10)
        (out / 'image-inspect.json').write_bytes(r.stdout)
        env['vllm_version'] = run(['docker', 'exec', name, 'python3', '-c', 'import vllm; print(vllm.__version__)'], 30).stdout.decode().strip()
        gpu_cmd = ['rocm-smi', '--showproductname', '--showdriverversion'] if a.kind == 'amd' else ['nvidia-smi']
        gpu = run(['docker', 'exec', name, *gpu_cmd], 30, check=False)
        (out / 'gpu.txt').write_bytes(gpu.stdout + gpu.stderr)
        write_json(out / 'env.json', env)
        if not env['vllm_version'].startswith('0.30.0'):
            raise RuntimeError('Unexpected vLLM version')
        require_tier_backend(a.tier, selected)
        # Three fixed greedy smoke requests; no correctness claim.
        for i, prompt in enumerate(['Explain a mutex.', 'Write iterative Fibonacci in Python.', 'What is 17 * 23?']):
            body = encoded({'model': MODEL, 'prompt': prompt, 'temperature': 0, 'seed': 0, 'max_tokens': 64})
            req = urllib.request.Request('http://127.0.0.1:8000/v1/completions', data=body, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.load(response)
            write_json(out / f'smoke-{i}.json', result)
            if not result.get('choices') or not result['choices'][0].get('text'):
                raise RuntimeError('Empty smoke response')
        # At most 2 min for environment + smoke after startup; remaining slack is explicit.
        if time.monotonic() - started > 2520:
            raise TimeoutError('Preparation exceeded 42-minute allocation')
        times['t_work_start'] = utc(); write_json(out / 'ledger-times.json', times)
        child = subprocess.Popen([sys.executable, '-B', str(HERE / 'replay.py'), '--tasks', str(out/'tasks.json'),
            '--trace', a.trace, '--trace-sha256', a.trace_sha256, '--start', a.start,
            '--rate-factor', str(a.rate_factor), '--out', str(out/'replay')])
        if child.wait(timeout=REPLAY_TIMEOUT) != 0:
            raise RuntimeError('Replay failed')
        times['t_work_end'] = utc(); write_json(out / 'ledger-times.json', times)
        convert(out/'replay', out/'detailed.json', IMAGES[a.kind])
        status = 'completed_ungraded'
    except Exception as e:
        write_json(out/'failure.json', {'error': type(e).__name__ + ': ' + str(e), 'at': utc()})
        if isinstance(e, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
            (out/'failed-command.log').write_bytes((e.stdout or b'') + (e.stderr or b''))
    finally:
        # Reserve 5 minutes between the work alarm and outer process watchdog.
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=65)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=5)
        if times['t_work_start'] and not times['t_work_end']:
            times['t_work_end'] = utc()
        if created:
            for cmd, filename in [(['docker', 'logs', name], 'serve.log'),
                                  (['docker', 'stop', '-t', '10', name], 'container-stop.log')]:
                try:
                    r = subprocess.run(cmd, capture_output=True, timeout=25)
                    (out/filename).write_bytes(r.stdout+r.stderr)
                except Exception as e:
                    (out/filename).write_text(str(e), encoding='utf-8')
        if (out/'replay'/'plan.json').exists() and not (out/'detailed.json').exists():
            try:
                convert(out/'replay', out/'detailed.json', IMAGES[a.kind])
            except Exception as e:
                write_json(out/'recovery-failure.json', {'error': str(e)})
        times['t_script_end'] = utc(); write_json(out/'ledger-times.json', times)
        detail = read_json(out/'detailed.json') if (out/'detailed.json').exists() else {}
        write_json(out/'ledger.json', {'schema': 'second-run/run3-arm-summary@1', 'status': status,
            'arm': 'A' if a.kind == 'amd' else 'N', 'tier': a.tier, 'timestamps': times,
            'hourly_list_usd': 2.99 if a.kind == 'amd' else 4.41,
            'funding': 'self-funded; operator must verify invoice', 'modeled_full_cost_usd': None,
            'billed_usd': None, 'credits_usd': None, 'acquisition_attempts': None,
            'restarts': 0, 'attempted': detail.get('num_prompts'), 'completed': detail.get('completed'),
            'failed': detail.get('failed'), 'lost': detail.get('metadata', {}).get('lost_requests'),
            'never_sent': detail.get('metadata', {}).get('never_sent_requests'),
            'send_unknown': detail.get('metadata', {}).get('send_unknown_requests'),
            'correct': None, 'accepted': None, 'cost_per_accepted_usd': None,
            'wall_seconds_per_accepted': None,
            'traversals_per_run': None, 'seconds_per_traversal': None,
            'bytes_per_traversal': None, 'accepted_closures_per_traversal': None,
            'energy_wh': None, 'note': 'Null means unmeasured; provider release is not container stop.'})
        files = sorted(p for p in out.rglob('*') if p.is_file() and p.name != 'MANIFEST.sha256')
        (out/'MANIFEST.sha256').write_text(''.join(f'{sha(p)}  {p.relative_to(out).as_posix()}\n' for p in files), encoding='utf-8')
    return 0 if status == 'completed_ungraded' else 1


if __name__ == '__main__':
    sys.exit(main())
