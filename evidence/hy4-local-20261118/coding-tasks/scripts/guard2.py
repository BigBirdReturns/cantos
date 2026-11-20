#!/usr/bin/env python3
"""Thermal pacing and guard for the Hy4 server on W03's cards.

Samples both cards once a second. Pauses the server process (SIGSTOP) when a card reaches PAUSE_C and resumes it
(SIGCONT) once both are back at RESUME_C, so a long capture stays inside the 80 C envelope the earlier Cantos
runs used. Stops the server unit, and nothing else, if a card still reaches STOP_C. Power limits and fans are
left as found. Usage: guard2.py SERVER_UNIT OUT_JSONL
"""
import json, os, signal, subprocess, sys, time

unit, out = sys.argv[1], sys.argv[2]
PAUSE_C, RESUME_C, STOP_C = 76.0, 68.0, 80.0
QUERY = 'uuid,temperature.gpu,power.draw,power.limit,memory.used,utilization.gpu'


def show(prop):
    return subprocess.run(['systemctl', '--user', 'show', '-p', prop, '--value', unit], capture_output=True, text=True).stdout.strip()


paused, idle, pauses = False, 0, 0
with open(out, 'a', buffering=1) as log:
    while idle < 30:
        active = show('ActiveState') in ('active', 'activating')
        idle = 0 if active else idle + 1
        rows = subprocess.run(['nvidia-smi', '--query-gpu=' + QUERY, '--format=csv,noheader,nounits'],
                              capture_output=True, text=True).stdout.strip().splitlines()
        sample = {'epoch': time.time(), 'monotonic_s': time.monotonic(), 'gpus': []}
        for row in rows:
            uuid, temp, watts, cap, mem, util = [part.strip() for part in row.split(',')]
            sample['gpus'].append({'uuid': uuid, 'temperature_c': float(temp), 'watts': float(watts),
                                   'power_limit_w': float(cap), 'memory_mib': float(mem), 'util_pct': float(util)})
        hottest = max(gpu['temperature_c'] for gpu in sample['gpus'])
        pid = int(show('MainPID') or 0) if active else 0
        if active and pid:
            if hottest >= STOP_C:
                sample['guard'] = 'stop'
                os.kill(pid, signal.SIGCONT)
                subprocess.run(['systemctl', '--user', 'stop', unit])
                open(out + '.GUARD-STOP', 'w').write(json.dumps(sample))
                paused = False
            elif not paused and hottest >= PAUSE_C:
                os.kill(pid, signal.SIGSTOP)
                paused, pauses = True, pauses + 1
                sample['guard'] = 'pause'
            elif paused and hottest <= RESUME_C:
                os.kill(pid, signal.SIGCONT)
                paused = False
                sample['guard'] = 'resume'
        sample['paused'] = paused
        sample['pauses'] = pauses
        log.write(json.dumps(sample) + '\n')
        time.sleep(1)
