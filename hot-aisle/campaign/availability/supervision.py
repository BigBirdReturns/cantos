"""One capacity wake and one supervised baseline; no provider mutations here.

Configuration, credentials, captures and agent output belong in private custody.
The executor must satisfy its live acquisition/release preflight before renting.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write(path, value):
    temp = path.with_name(path.name + '.' + str(os.getpid()) + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def verify_sources(cfg):
    for filename, expected in cfg['runtime_sha256'].items():
        path = Path(cfg['runtime_dir']) / filename
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Runtime source changed: ' + filename)


def read_state(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def launch_task(cfg, role):
    """The Windows SSH service kills ordinary detached children on disconnect."""
    task = cfg[role + '_task']
    run = subprocess.run(['schtasks.exe', '/Run', '/TN', task], capture_output=True,
                         text=True, encoding='utf-8', errors='replace', timeout=20)
    if run.returncode:
        raise RuntimeError('Task Scheduler refused ' + task + ': ' + (run.stderr or run.stdout)[-1000:])
    return {'task': task, 'launch_utc': now()}


def recover(cfg):
    state = Path(cfg['state_dir'])
    try:
        with (state/'recovery-claim.json').open('x', encoding='utf-8') as claim:
            json.dump({'started_utc': now(), 'pid': os.getpid()}, claim)
    except FileExistsError:
        return {'recovery_status': 'already_claimed'}
    prompt = ('RELEASE-ONLY RECOVERY. Read the campaign executor prompt at ' +
              cfg['executor_prompt'] + ' and private state ' + str(state) +
              '. The first-baseline executor returned, stopped or lost its heartbeat '
              'without a release receipt. Do not rent or run any workload. Use N01 and '
              'the pinned provider route. Recover outputs if promptly possible, delete '
              'ONLY the exact allocation proven to belong to the acquisition claim, '
              'and confirm billing cessation. If no allocation was acquired, verify '
              'that and record phase not_acquired. Missing or malformed allocation.json '
              'is uncertain ownership: use preserved create captures and the live account '
              'to reconcile it before acting. Never delete unrelated resources. Persist '
              'allocation.json and recovery-result.json. You have the existing user '
              'authority to release this campaign allocation. No other resource changes '
              'are authorized. If original executor processes remain active, fence only '
              'the recorded campaign process before taking over its provider session.')
    result = {'started_utc': now()}
    with (state/'recovery-stdout.json').open('wb') as output, (state/'recovery-stderr.txt').open('wb') as errors:
        try:
            completed = subprocess.run([
                cfg['claude_executable'], '-p', '--model', cfg['model'],
                '--permission-mode', 'auto', '--tools', 'Read,Write,Bash,Glob,Grep',
                '--add-dir', cfg['project_home'], '--add-dir', cfg['estate_root'],
                '--strict-mcp-config', '--output-format', 'json', prompt],
                cwd=cfg['project_checkout'], stdout=output, stderr=errors,
                timeout=600, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            result['returncode'] = completed.returncode
        except subprocess.TimeoutExpired:
            result['status'] = 'timeout_hold'
    result['finished_utc'] = now()
    result['allocation'] = read_state(state/'allocation.json')
    result['closure_confirmed_by_executor'] = result['allocation'].get('phase') in ('released', 'not_acquired')
    write(state/'recovery-process.json', result)
    return result


def worker(cfg, preparation=False):
    state = Path(cfg['state_dir'])
    if (state/'STOP').exists() or dt.datetime.now(dt.timezone.utc) >= dt.datetime.fromisoformat(cfg['expires_utc']):
        if not preparation and read_state(state/'allocation.json').get('phase') not in ('released', 'not_acquired'):
            recover(cfg)
        return 0
    prefix = 'preparation' if preparation else 'executor'
    session_id = cfg[prefix + '_session_id']
    prompt = Path(cfg['executor_prompt']).read_text(encoding='utf-8')
    prompt += '\n\nPRIVATE CONFIGURATION:\n' + json.dumps({
        k: cfg[k] for k in ('state_dir', 'project_home', 'project_checkout',
                           'start_file', 'estate_root', 'watch_config',
                           'provider_charge_cap_usd', 'first_allocation_cap_usd')})
    if preparation:
        prompt += ('\nMODE: PREPARATION ONLY. Do not contact the provider, rent, run workloads, '
                   'change services or modify source. Read the actual launch files and '
                   'write preparation-result.json in state_dir with status, exact source commit, '
                   'the next action, unresolved operational risks and acknowledged authority. '
                   'Then return. This checks that the executor can read and retain its continuation.')
    else:
        prompt += ('\nMODE: FIRST BASELINE. The monitor found a candidate listing. '
                   'It is not a delivered allocation or permission to skip preflight. '
                   'Read the latest capture and recheck the live TUI before proceeding. '
                   'The acquisition claim is already held for your session. Do not remove it.')
    argv = [cfg['claude_executable'], '-p', '--session-id', session_id,
            '--model', cfg['model'], '--permission-mode', 'auto',
            '--add-dir', cfg['project_home'], '--add-dir', cfg['estate_root'],
            '--tools', 'Read,Write,Edit,Bash,Glob,Grep', '--strict-mcp-config',
            '--output-format', 'json', prompt]
    log = state / (prefix + '-stdout.json')
    err = state / (prefix + '-stderr.txt')
    timeout = 240 if preparation else cfg['executor_timeout_seconds']
    with log.open('wb') as stdout, err.open('wb') as stderr:
        child = subprocess.Popen(argv, cwd=cfg['project_checkout'], stdout=stdout,
                                 stderr=stderr, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        started = time.monotonic()
        timed_out = False
        while child.poll() is None:
            write(state / (prefix + '-process.json'), {
                'status': 'running', 'session_id': session_id, 'pid': child.pid,
                'heartbeat_utc': now(), 'wrapper_pid': os.getpid(),
                'mode': prefix, 'source_commit': cfg['source_commit']})
            cancelled = (state/'STOP').exists() or dt.datetime.now(dt.timezone.utc) >= dt.datetime.fromisoformat(cfg['expires_utc'])
            if time.monotonic() - started >= timeout or cancelled:
                timed_out = True
                # Terminate this exact executor process tree before a recovery lane.
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'],
                                   capture_output=True, timeout=30)
                else:
                    child.terminate()
                break
            time.sleep(5)
        try:
            code = child.wait(timeout=30)
        except subprocess.TimeoutExpired:
            child.kill()
            code = child.wait(timeout=10)
    result = {'status': 'timed_out' if timed_out else 'returned',
              'returncode': code, 'session_id': session_id, 'finished_utc': now(),
              'stdout': str(log), 'stderr': str(err)}
    write(state / (prefix + '-process.json'), result)
    if not preparation:
        record = read_state(state/'allocation.json')
        if record.get('phase') not in ('released', 'not_acquired'):
            result['recovery'] = recover(cfg)
            write(state/'executor-process.json', result)
    return code


def tick(cfg, config_path):
    state = Path(cfg['state_dir'])
    # A claim persists after process failure: never replace an uncertain rental.
    claim = state/'acquisition-claim.json'
    if claim.exists():
        process = read_state(state/'executor-process.json')
        allocation = read_state(state/'allocation.json')
        if allocation.get('phase') in ('released', 'not_acquired'):
            return {'status': 'allocation_closed', 'allocation': allocation, 'executor': process}
        heartbeat = process.get('heartbeat_utc', read_state(claim).get('created_utc'))
        try:
            age = (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(heartbeat)).total_seconds()
        except (ValueError, TypeError):
            # Another tick may see the exclusive file before its JSON is flushed.
            # Give that writer the same startup grace as a complete fresh claim.
            age = max(0, time.time() - claim.stat().st_mtime)
        if age > 180 and not (state/'recovery-claim.json').exists():
            # Recovery is allowed after STOP/expiry; acquisition is not.
            try:
                with (state/'recovery-launch.json').open('x', encoding='utf-8') as receipt:
                    json.dump({'started_utc': now(), 'reason': 'executor heartbeat stale'}, receipt)
                try:
                    launched = launch_task(cfg, 'recovery')
                    return {'status': 'recovery_started', **launched, 'heartbeat_age_s': age}
                except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                    failure = {'status': 'release_unconfirmed', 'reason': str(exc), 'failed_utc': now()}
                    write(state/'recovery-launch-failure.json', failure)
                    return failure
            except FileExistsError:
                pass
        launch_failure = read_state(state/'recovery-launch-failure.json')
        if launch_failure:
            return launch_failure
        recovery_launch = read_state(state/'recovery-launch.json')
        if recovery_launch and not (state/'recovery-claim.json').exists():
            try:
                launch_age = (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(recovery_launch['started_utc'])).total_seconds()
            except (KeyError, ValueError, TypeError):
                launch_age = 9999
            if launch_age > 60:
                return {'status': 'release_unconfirmed', 'reason': 'Recovery task did not claim execution', 'claim': str(claim)}
        recovery = read_state(state/'recovery-process.json')
        if recovery and recovery.get('closure_confirmed_by_executor') is not True:
            return {'status': 'release_unconfirmed', 'recovery': recovery,
                    'claim': str(claim), 'reason': 'No further acquisition permitted; inspect release evidence'}
        recovery_claim = read_state(state/'recovery-claim.json')
        if recovery_claim and not recovery:
            try:
                recovery_age = (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(recovery_claim['started_utc'])).total_seconds()
            except (KeyError, ValueError, TypeError):
                recovery_age = 9999
            if recovery_age > 660:
                return {'status': 'release_unconfirmed', 'reason': 'Recovery has no completed receipt', 'claim': str(claim)}
        return {'status': 'acquisition_claimed', 'executor': process, 'claim': str(claim)}
    if (state/'STOP').exists():
        return {'status': 'stopped', 'observed_utc': now()}
    if dt.datetime.now(dt.timezone.utc) >= dt.datetime.fromisoformat(cfg['expires_utc']):
        return {'status': 'expired', 'observed_utc': now()}
    r = subprocess.run([sys.executable, '-B', str(Path(cfg['runtime_dir'])/'tui_watch.py'),
                        '--config', cfg['watch_config'], '--once'],
                       capture_output=True, text=True, encoding='utf-8', timeout=110)
    try:
        latest = json.loads(r.stdout)
    except ValueError:
        return {'status': 'monitor_failed', 'returncode': r.returncode,
                'stdout': r.stdout[-2000:], 'stderr': r.stderr[-2000:]}
    return dispatch_observation(cfg, latest, r.returncode)


def dispatch_observation(cfg, latest, returncode):
    """Consume a real current sample, including an explicit operator recheck."""
    state = Path(cfg['state_dir'])
    claim = state/'acquisition-claim.json'
    status = latest.get('classification')
    if status not in ('candidate', 'candidate_review_required'):
        return {'status': 'waiting_capacity' if status == 'no_offer' else status,
                'monitor': latest, 'returncode': returncode}
    if returncode != 0:
        return {'status': 'candidate_monitor_hold', 'monitor': latest}
    observed = dt.datetime.fromisoformat(latest['started_utc'])
    if not 0 <= (dt.datetime.now(dt.timezone.utc)-observed).total_seconds() <= 120:
        return {'status': 'candidate_monitor_hold', 'reason': 'candidate observation is not fresh'}
    if not latest.get('capture') or latest.get('provisioned') is not False or latest.get('synthetic') is not False:
        return {'status': 'candidate_monitor_hold', 'reason': 'candidate lacks real read-only capture'}
    if (state/'STOP').exists() or dt.datetime.now(dt.timezone.utc) >= dt.datetime.fromisoformat(cfg['expires_utc']):
        return {'status': 'stopped_or_expired_before_claim'}
    created = {'owner': 'n01-ha-reference-supervisor',
               'executor_session_id': cfg['executor_session_id'], 'created_utc': now(),
               'source_commit': cfg['source_commit'], 'scope': 'one MI300X first baseline only',
               'provider_charge_cap_usd': cfg['provider_charge_cap_usd'],
               'first_allocation_cap_usd': cfg['first_allocation_cap_usd'],
               'candidate_observation': latest}
    try:
        with claim.open('x', encoding='utf-8') as output:
            json.dump(created, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError:
        return {'status': 'acquisition_claimed', 'claim': str(claim)}
    if (state/'STOP').exists() or dt.datetime.now(dt.timezone.utc) >= dt.datetime.fromisoformat(cfg['expires_utc']):
        return {'status': 'stopped_or_expired_after_claim', 'claim': str(claim)}
    launched = launch_task(cfg, 'executor')
    return {'status': 'executor_started', **launched, 'claim': str(claim)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--worker', action='store_true')
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--recover', action='store_true')
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding='utf-8'))
    verify_sources(cfg)
    if args.recover:
        print(json.dumps(recover(cfg)))
        return 0
    if args.worker or args.prepare:
        return worker(cfg, args.prepare)
    result = tick(cfg, args.config)
    result['tick_utc'] = now()
    write(Path(cfg['state_dir'])/'supervision-latest.json', result)
    print(json.dumps(result))
    failed = result.get('status') in (
        None, 'unknown', 'monitor_failed', 'candidate_monitor_hold',
        'configuration_error', 'release_unconfirmed',
    ) or result.get('returncode') not in (None, 0)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
