#!/usr/bin/env python3
"""Sample both cards once a second while the Hy4 server unit is active.

Writes power.jsonl beside this file. Stops the server unit (and nothing else) when a card
reaches the temperature limit; power limits and fans are left as found.
Usage: guard.py SERVER_UNIT LIMIT_C OUT_JSONL
"""
import json, subprocess, sys, time

unit, limit, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
QUERY = 'uuid,temperature.gpu,power.draw,power.limit,memory.used,utilization.gpu'


def active():
    state = subprocess.run(['systemctl', '--user', 'is-active', unit], capture_output=True, text=True).stdout.strip()
    return state in ('active', 'activating')


with open(out, 'a', buffering=1) as log:
    idle = 0
    while idle < 30:
        idle = 0 if active() else idle + 1
        rows = subprocess.run(['nvidia-smi', '--query-gpu=' + QUERY, '--format=csv,noheader,nounits'],
                              capture_output=True, text=True).stdout.strip().splitlines()
        sample = {'epoch': time.time(), 'monotonic_s': time.monotonic(), 'gpus': []}
        for row in rows:
            uuid, temp, watts, cap, mem, util = [part.strip() for part in row.split(',')]
            sample['gpus'].append({'uuid': uuid, 'temperature_c': float(temp), 'watts': float(watts),
                                   'power_limit_w': float(cap), 'memory_mib': float(mem), 'util_pct': float(util)})
        hot = [gpu for gpu in sample['gpus'] if gpu['temperature_c'] >= limit]
        if hot and idle == 0:
            sample['guard'] = 'stop'
            subprocess.run(['systemctl', '--user', 'stop', unit])
            open(out + '.GUARD-STOP', 'w').write(json.dumps(sample))
        log.write(json.dumps(sample) + '\n')
        time.sleep(1)
