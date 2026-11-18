"""Source-bound resource accounting for complete retry campaigns.

GPU telemetry is gross sensor-window energy. It is never automatically promoted
to exclusive inference, host, facility energy, or measured operating expenditure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

try:
    from .common import load, write, canonical, keys, number, nonempty, now, sha256_file, producer_records
    from .owner_ocl.energy import integrate_power
    from .owner_ocl.costs import estimate_cost
except ImportError:
    from common import load, write, canonical, keys, number, nonempty, now, sha256_file, producer_records
    from owner_ocl.energy import integrate_power
    from owner_ocl.costs import estimate_cost

SCENARIO_FIELDS = {
    'capex_usd', 'residual_usd', 'life_hours', 'utilization',
    'financing_usd_per_hour', 'hosting_usd_per_hour', 'operations_usd_per_hour',
    'maintenance_usd_per_hour', 'network_usd_per_hour',
    'electricity_usd_per_kwh', 'pue', 'intervention_seconds',
    'intervention_usd_per_hour', 'average_it_power_w',
}


def _retry():
    try:
        from . import retry
    except ImportError:
        import retry
    return retry


def _campaign(path):
    path = Path(path).resolve()
    _retry().validate_campaign(path)
    value = load(path)
    if value.get('status') != 'complete':
        raise ValueError('campaign outcomes remain unresolved; accepted-work resource ratios are incomplete')
    start = number(value.get('started_monotonic_s'), 'campaign start', 0, 1e15)
    end = number(value.get('ended_monotonic_s'), 'campaign end', 0, 1e15)
    if end <= start:
        raise ValueError('campaign resource window must have positive duration')
    accepted = value.get('metrics', {}).get('accepted_tasks')
    number(accepted, 'accepted_tasks', 0, 1000000000, True)
    clock = value.get('clock_identity')
    if not isinstance(clock, dict) or not clock:
        raise ValueError('campaign requires its monotonic clock identity')
    return value, {'path': path.name, 'sha256': sha256_file(path),
                   'bytes': path.stat().st_size}, start, end, accepted


def _safe_source(root, entry):
    keys(entry, {'path', 'sha256', 'bytes'}, 'resource artifact')
    rel = Path(nonempty(entry.get('path'), 'resource artifact path'))
    if rel.is_absolute() or '..' in rel.parts or '\\' in str(rel):
        raise ValueError('unsafe resource artifact path')
    target = (root / rel).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        raise ValueError('resource artifact escapes owner') from None
    if not target.is_file() or target.stat().st_size != entry.get('bytes') or sha256_file(target) != entry.get('sha256'):
        raise ValueError('resource artifact is missing or changed')
    return target


def _entry(path, root):
    path = Path(path)
    return {'path': path.relative_to(root).as_posix(), 'sha256': sha256_file(path),
            'bytes': path.stat().st_size}


def _events(path):
    from_json = []
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            if not line.strip():
                raise ValueError('blank telemetry journal record')
            # Reuse strict duplicate-key/nonfinite rejection.
            try:
                from .owner_ocl.runner import _strict_loads
            except ImportError:
                from owner_ocl.runner import _strict_loads
            from_json.append(_strict_loads(line))
    return from_json


def read_telemetry(path, campaign, campaign_record, start, end, accepted):
    path = Path(path).resolve()
    value = load(path)
    keys(value, {'schema', 'campaign_sha256', 'observation_id', 'clock_identity',
                 'devices', 'max_gap_s', 'samples', 'sensor', 'attribution',
                 'producer', 'observed_at', 'evidence_class'}, 'telemetry')
    if value.get('schema') != 'cantos.retry.telemetry/1':
        raise ValueError('unsupported telemetry schema')
    if value.get('campaign_sha256') != campaign_record['sha256']:
        raise ValueError('telemetry belongs to a different campaign')
    if value.get('observation_id') != campaign.get('observation_id'):
        raise ValueError('telemetry observation identity mismatch')
    if value.get('clock_identity') != campaign['clock_identity']:
        raise ValueError('telemetry and campaign use different monotonic clocks')
    devices = value.get('devices')
    if not isinstance(devices, list) or not devices or len(devices) != len(set(devices)):
        raise ValueError('telemetry needs distinct explicit devices')
    for device in devices:
        nonempty(device, 'device UUID')
    gap = number(value.get('max_gap_s'), 'maximum sample gap', 0.000001, 600)
    journal = _safe_source(path.parent, value['samples'])
    records = _events(journal)
    if len(records) < 2 or records[0].get('kind') != 'sampler_started' or records[-1].get('kind') != 'sampler_ended':
        raise ValueError('telemetry journal is incomplete')
    beginning = records[0]
    if beginning.get('clock_identity') != campaign['clock_identity'] or beginning.get('devices') != devices:
        raise ValueError('telemetry header identity mismatch')
    if beginning.get('max_gap_s') != gap:
        raise ValueError('telemetry sampling tolerance changed after capture')
    if value.get('producer') != beginning.get('producer'):
        raise ValueError('telemetry producer identity mismatch')
    by_device = {device: [] for device in devices}
    failures = []
    last = None
    for record in records[1:-1]:
        at = number(record.get('t_s'), 'telemetry time', 0, 1e15)
        if last is not None and at <= last:
            raise ValueError('telemetry event times must increase')
        last = at
        if record.get('kind') == 'sample_error':
            failures.append(at)
            continue
        if record.get('kind') != 'power_sample':
            raise ValueError('unexpected telemetry event')
        rows = record.get('readings')
        if not isinstance(rows, list) or len(rows) != len(devices):
            raise ValueError('partial device sample')
        seen = set()
        for row in rows:
            keys(row, {'device_uuid', 'watts'}, 'power reading')
            device = row.get('device_uuid')
            if device not in by_device or device in seen:
                raise ValueError('device mismatch or duplicated reading')
            seen.add(device)
            number(row.get('watts'), 'board watts', 0, 1000000)
            by_device[device].append({'t_s': at, 'watts': row['watts']})
    values = {}
    for device, samples in by_device.items():
        result = integrate_power(samples, start, end, gap)
        if any(start <= timestamp <= end for timestamp in failures):
            result['joules'] = None
            result['limitations'].append('A sensor read failed within the campaign; energy remains unknown.')
        values[device] = result
    complete = all(v['joules'] is not None for v in values.values())
    total = sum(v['joules'] for v in values.values()) if complete else None
    return {
        'status': 'complete_scoped_telemetry' if complete else 'incomplete_telemetry',
        'scope': 'gpu_board', 'calibrated': False,
        'window_s': [start, end], 'devices': values,
        'gross_board_joules': total,
        'gross_board_joules_per_accepted_task': total / accepted if total is not None and accepted else None,
        'denominator_status': 'accepted_work' if accepted else 'zero_accepted_tasks',
        'sensor': value.get('sensor'), 'attribution': value.get('attribution'),
        'evidence_class': value.get('evidence_class'),
        'source': _entry(path, path.parent), 'samples': value['samples'],
        'limitations': [
            'Gross energy of the named GPU boards throughout the complete campaign, including failed attempts, waiting, backoff and grading windows.',
            'Resident model and unrelated GPU loads are included; exclusive job attribution is not established.',
            'Host CPU, external grader hardware, other devices, server startup and facility overhead are outside this boundary.',
            'Driver power samples are uncalibrated sensor estimates; interpolation is bounded by the declared sampling gap.',
        ],
    }


def read_scenario(path, duration, accepted, energy=None):
    path = Path(path).resolve()
    value = load(path)
    keys(value, {'schema', 'currency', 'values', 'field_sources', 'description'}, 'resource scenario')
    if value.get('schema') != 'cantos.retry.cost-scenario/1' or value.get('currency') != 'USD':
        raise ValueError('scenario requires cantos.retry.cost-scenario/1 and USD')
    scenario = value.get('values')
    keys(scenario, SCENARIO_FIELDS, 'cost values')
    sources = value.get('field_sources')
    keys(sources, SCENARIO_FIELDS, 'field sources')
    for field, number_value in scenario.items():
        if number_value is not None:
            nonempty(sources.get(field), 'source or assumption for ' + field)
    scoped = None
    if energy and energy['gross_board_joules'] is not None:
        scoped = {'joules': energy['gross_board_joules'], 'scope': 'gpu_board'}
    result = estimate_cost({'duration_s': duration, 'accepted_tasks': accepted}, scenario, scoped)
    result.update({'field_sources': sources, 'source': _entry(path, path.parent),
                   'scope': 'complete campaign window under declared scenario',
                   'actual_total_cost_usd': None})
    return result


def summarize(campaign_path, telemetry_path=None, scenario_path=None, out=None):
    campaign, source, start, end, accepted = _campaign(campaign_path)
    energy = read_telemetry(telemetry_path, campaign, source, start, end, accepted) if telemetry_path else None
    economics = read_scenario(scenario_path, end-start, accepted, energy) if scenario_path else None
    result = {
        'schema': 'cantos.retry.resources/1', 'analyzed_at': now(),
        'campaign': source, 'observation_id': campaign['observation_id'],
        'clock_identity': campaign['clock_identity'],
        'campaign_window_s': [start, end], 'campaign_duration_s': end-start,
        'accepted_tasks': accepted, 'energy': energy, 'economics': economics,
        'actual_total_cost_usd': None,
        'source_code': {'sha256': sha256_file(__file__), 'producer_files': producer_records()},
    }
    if out is not None:
        write(out, result)
    return result


def record(out, devices, stop_file, interval_s=0.25, max_gap_s=2.5, max_seconds=600):
    """Read board sensors until a stop marker/deadline; never change GPU settings."""
    number(interval_s, 'sample interval', 0.01, 60)
    number(max_gap_s, 'maximum sample gap', interval_s, 600)
    number(max_seconds, 'maximum sampler lifetime', 0.1, 86400)
    if not devices or len(devices) != len(set(devices)) or any(not d.startswith('GPU-') for d in devices):
        raise ValueError('explicit NVIDIA GPU UUIDs are required')
    out = Path(out).resolve()
    stop = Path(stop_file).resolve()
    if stop.exists():
        raise ValueError('stop marker already exists')
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    clock = _retry().clock_identity()
    producer = {'name': 'cantos.retry_resources.record', 'sha256': sha256_file(__file__)}
    with out.open('x', encoding='utf-8') as stream:
        def emit(value):
            stream.write(canonical(value).decode('utf-8')+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        emit({'kind': 'sampler_started', 'observed_at': now(), 't_s': started,
              'clock_identity': clock, 'devices': devices, 'max_gap_s': max_gap_s,
              'interval_s': interval_s, 'producer': producer,
              'sensor': 'nvidia-smi power.draw; board sensor estimate'})
        final_sample = False
        while True:
            before = time.monotonic()
            try:
                command = ['nvidia-smi', '--id='+','.join(devices),
                           '--query-gpu=uuid,power.draw', '--format=csv,noheader,nounits']
                value = subprocess.run(command, capture_output=True, text=True, timeout=min(5, max_gap_s), check=True)
                after = time.monotonic()
                rows = []
                for line in value.stdout.strip().splitlines():
                    device, watts = [x.strip() for x in line.split(',')]
                    rows.append({'device_uuid': device, 'watts': float(watts)})
                if {x['device_uuid'] for x in rows} != set(devices) or len(rows) != len(devices):
                    raise ValueError('sensor response omitted or duplicated a selected GPU')
                for row in rows:
                    number(row['watts'], 'sensor watts', 0, 1000000)
                emit({'kind': 'power_sample', 't_s': (before+after)/2,
                      'query_started_s': before, 'query_ended_s': after,
                      'readings': rows, 'raw_stdout': value.stdout})
            except Exception as exc:
                emit({'kind': 'sample_error', 't_s': time.monotonic(), 'error': type(exc).__name__})
            if final_sample or time.monotonic()-started >= max_seconds:
                break
            # Take a whole sensor query after observing the stop marker so the
            # final sample brackets a campaign completed before that marker.
            if stop.exists():
                final_sample = True
                continue
            time.sleep(interval_s)
        emit({'kind': 'sampler_ended', 'observed_at': now(), 't_s': time.monotonic(),
              'reason': 'stop_marker' if stop.exists() else 'deadline'})
    return {'journal': str(out), 'sha256': sha256_file(out)}


def seal(campaign_path, journal_path, out, evidence_class='observed-board-telemetry'):
    campaign, record_info, _, _, _ = _campaign(campaign_path)
    journal = Path(journal_path).resolve()
    out = Path(out).resolve()
    events = _events(journal)
    if not events or events[0].get('kind') != 'sampler_started':
        raise ValueError('missing sampler header')
    header = events[0]
    try:
        journal.relative_to(out.parent)
    except ValueError:
        raise ValueError('telemetry receipt and retained journal need a shared artifact directory') from None
    result = {
        'schema': 'cantos.retry.telemetry/1', 'campaign_sha256': record_info['sha256'],
        'observation_id': campaign['observation_id'], 'clock_identity': header['clock_identity'],
        'devices': header['devices'], 'max_gap_s': header['max_gap_s'],
        'samples': _entry(journal, out.parent), 'sensor': header.get('sensor'),
        'attribution': 'gross selected boards; no exclusive job or full-system attribution',
        'producer': header['producer'], 'observed_at': header['observed_at'],
        'evidence_class': evidence_class,
    }
    write(out, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    a = sub.add_parser('analyze')
    a.add_argument('--campaign', required=True)
    a.add_argument('--telemetry')
    a.add_argument('--scenario')
    a.add_argument('--out', required=True)
    r = sub.add_parser('record')
    r.add_argument('--out', required=True)
    r.add_argument('--device', action='append', required=True)
    r.add_argument('--stop-file', required=True)
    r.add_argument('--interval-s', type=float, default=0.25)
    r.add_argument('--max-gap-s', type=float, default=2.5)
    r.add_argument('--max-seconds', type=float, default=600)
    s = sub.add_parser('seal')
    s.add_argument('--campaign', required=True)
    s.add_argument('--journal', required=True)
    s.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'record':
            result = record(args.out, args.device, args.stop_file, args.interval_s, args.max_gap_s, args.max_seconds)
        elif args.command == 'seal':
            result = seal(args.campaign, args.journal, args.out)
        else:
            result = summarize(args.campaign, args.telemetry, args.scenario, args.out)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'error', 'error': type(exc).__name__, 'message': str(exc)}))
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
