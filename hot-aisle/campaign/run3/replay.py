"""Freeze Azure CODE arrivals and replay streaming completions on the serving host."""
import argparse
import concurrent.futures
import csv
import datetime as dt
import http.client
import json
import math
import os
from pathlib import Path
import signal
import socket
import threading
import time
from urllib.parse import urlsplit
from common import MODEL, REVISION, encoded, read_json, sha, verify, write_json


def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=parsed.tzinfo or dt.timezone.utc).timestamp()


def schedule(trace, trace_sha, start, factor, duration=3600):
    verify(trace, trace_sha)
    if not math.isfinite(factor) or factor <= 0 or duration <= 0:
        raise ValueError('Positive finite rate factor and duration required')
    origin = timestamp(start)
    # Compress/expand interarrivals by factor, and retain [0,duration).
    # The source window is duration*factor; never loop or pad a short trace.
    offsets, latest, earliest = [], None, None
    with open(trace, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            t = timestamp(row['TIMESTAMP'])
            earliest = t if earliest is None else min(earliest, t)
            latest = t if latest is None else max(latest, t)
            x = (round(t * 1000000) - round(origin * 1000000)) / 1000000 / factor
            if 0 <= x < duration:
                offsets.append(x)
    if earliest is None or origin < earliest or latest < origin + duration * factor:
        raise ValueError('Trace does not cover the entire selected source window')
    if not offsets or len(offsets) > 100000:
        raise ValueError('Schedule must contain 1..100000 arrivals')
    return sorted(offsets)


def request(endpoint, task, seed, scheduled_ts, timeout=60, max_tokens=1024):
    row = {'task_id': task['task_id'], 'seed': seed, 'scheduled_ts': scheduled_ts,
           'send_ts': None, 'first_token_ts': None, 'end_ts': None,
           'output_text': '', 'output_tokens': None, 'input_tokens': None,
           'finish_reason': None, 'error': ''}
    u = urlsplit(endpoint)
    if u.scheme != 'http' or u.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('Serving-host loopback HTTP endpoint required')
    conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)
    begin = time.monotonic()
    row['send_ts'] = time.time()
    clock = lambda: row['send_ts'] + time.monotonic() - begin

    def expire():
        if conn.sock:
            try:
                conn.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        conn.close()

    timer = threading.Timer(timeout, expire)
    timer.daemon = True
    timer.start()
    try:
        payload = {'model': MODEL, 'prompt': task['prompt'], 'seed': seed,
                   'temperature': 0.2, 'max_tokens': max_tokens, 'stream': True,
                   'stream_options': {'include_usage': True}}
        conn.connect()
        # Keep the socket reference even when an HTTP Connection: close response
        # detaches it from HTTPConnection. The timer must bound trickling streams.
        active_socket = conn.sock
        def expire_active():
            try:
                active_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            active_socket.close()
        timer.cancel()
        timer = threading.Timer(max(.001, timeout-(time.monotonic()-begin)), expire_active)
        timer.daemon = True
        timer.start()
        conn.request('POST', '/v1/completions', body=encoded(payload),
                     headers={'Content-Type': 'application/json'})
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError(f'HTTP {response.status}')
        done = False
        while True:
            line = response.readline(1048577)
            if not line:
                break
            if len(line) > 1048576:
                raise ValueError('Oversized SSE line')
            if not line.startswith(b'data:'):
                continue
            data = line[5:].strip()
            if data == b'[DONE]':
                done = True
                break
            item = json.loads(data)
            if item.get('error'):
                raise ValueError('Server SSE error: ' + str(item['error']))
            for choice in item.get('choices', []):
                piece = choice.get('text', '')
                if piece and row['first_token_ts'] is None:
                    row['first_token_ts'] = clock()
                row['output_text'] += piece
                if len(row['output_text']) > 1048576:
                    raise ValueError('Oversized completion')
                if choice.get('finish_reason'):
                    row['finish_reason'] = choice['finish_reason']
            if item.get('usage'):
                row['input_tokens'] = item['usage'].get('prompt_tokens')
                row['output_tokens'] = item['usage'].get('completion_tokens')
        if not done or row['finish_reason'] is None:
            raise ValueError('Incomplete SSE stream')
        if row['first_token_ts'] is None:
            raise ValueError('No output text')
        if any(type(row[k]) is not int or row[k] < 0 for k in ('input_tokens', 'output_tokens')):
            raise ValueError('Missing or invalid streaming token usage')
        if time.monotonic() - begin >= timeout:
            raise TimeoutError('Request deadline exceeded')
    except Exception as e:
        row['error'] = type(e).__name__ + ': ' + str(e)
    finally:
        row['end_ts'] = clock()
        timer.cancel()
        conn.close()
    return row


def recover(directory):
    """Preserve denominator after interruption; partial final journal line is ignored."""
    directory = Path(directory)
    plan = read_json(directory / 'plan.json')
    finished = {}
    journal = directory / 'journal.jsonl'
    if journal.exists():
        lines = journal.read_bytes().splitlines(keepends=True)
        for i, line in enumerate(lines):
            if not line.endswith(b'\n') and i == len(lines) - 1:
                continue
            row = json.loads(line)
            n = row['request_index']
            if n in finished or not 0 <= n < len(plan['requests']):
                raise ValueError('Duplicate or foreign journal row')
            finished[n] = row
    rows = []
    for spec in plan['requests']:
        n = spec['request_index']
        row = finished.get(n)
        if row is None:
            row = dict(spec, send_ts=None, first_token_ts=None, end_ts=None,
                       output_text='', output_tokens=None, input_tokens=None,
                       finish_reason=None, error='lost_or_unsent_after_interrupt')
        if any(row[k] != spec[k] for k in ('request_index', 'task_id', 'seed', 'scheduled_ts')):
            raise ValueError('Journal does not match frozen schedule')
        rows.append(row)
    return plan, rows


def buckets(plan, rows, passed=None):
    result = []
    duration = plan['duration_s']
    for offset in range(0, math.ceil(duration), 300):
        group = [r for r in rows if offset <= r['scheduled_ts'] - plan['start_ts'] < min(offset + 300, duration)]
        ok = [r for r in group if not r['error']]
        accepted = None if passed is None else sum(
            passed[r['request_index']] and not r['error']
            and r['first_token_ts'] - r['scheduled_ts'] <= 1
            and r['end_ts'] - r['scheduled_ts'] <= 60 for r in group)
        result.append({'offset_s': offset, 'duration_s': min(300, duration-offset),
                       'attempted': len(group), 'completed': len(ok), 'failed': len(group)-len(ok),
                       'correct': None if passed is None else sum(passed[r['request_index']] for r in group),
                       'accepted': accepted,
                       'completed_per_s': len(ok)/min(300, duration-offset)})
    return result


def replay(tasks_path, trace, trace_sha, start, factor, out, endpoint='http://127.0.0.1:8000',
           duration=3600, timeout=60, workers=256, seed=700000, fixture=False):
    tasks_file = read_json(tasks_path)
    if tasks_file['synthetic'] and not fixture:
        raise ValueError('Synthetic tasks cannot run as production')
    tasks = tasks_file['tasks']
    if not tasks or workers < 1 or not 0 < timeout <= 60:
        raise ValueError('Invalid replay parameters')
    offsets = schedule(trace, trace_sha, start, factor, duration)
    out = Path(out)
    out.mkdir(exist_ok=False, parents=True)
    start_wall, start_mono = time.time(), time.monotonic()
    plan = {'schema': 'second-run/replay-plan@1', 'synthetic': fixture,
            'start_ts': start_wall, 'duration_s': duration, 'rate_factor': factor,
            'trace_sha256': trace_sha, 'trace_start': start, 'tasks_sha256': sha(tasks_path),
            'model': MODEL, 'revision': REVISION, 'temperature': 0.2, 'max_tokens': 1024,
            'request_timeout_s': timeout, 'workers': workers,
            'requests': [dict(request_index=i, task_id=tasks[i % len(tasks)]['task_id'],
                              seed=seed+i, scheduled_ts=start_wall+x) for i, x in enumerate(offsets)]}
    write_json(out / 'plan.json', plan)
    stopped, available, lock = threading.Event(), threading.BoundedSemaphore(workers), threading.Lock()
    old_handlers = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_handlers[sig] = signal.signal(sig, lambda *_: stopped.set())
    with (out / 'journal.jsonl').open('xb') as journal:
        def save(row):
            with lock:
                journal.write(encoded(row)); journal.flush(); os.fsync(journal.fileno())

        def work(spec, task):
            try:
                row = request(endpoint, task, spec['seed'], spec['scheduled_ts'], timeout)
                save(dict(row, request_index=spec['request_index']))
            finally:
                available.release()

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for i, spec in enumerate(plan['requests']):
                wait = start_mono + offsets[i] - time.monotonic()
                if stopped.wait(max(0, wait)):
                    break
                if available.acquire(blocking=False):
                    pool.submit(work, spec, tasks[i % len(tasks)])
                else:
                    save(dict(spec, send_ts=None, first_token_ts=None, end_ts=time.time(),
                              output_text='', output_tokens=None, input_tokens=None,
                              finish_reason=None, error='client_concurrency_limit'))
            stopped.wait(max(0, start_mono + duration - time.monotonic()))
    for sig, handler in old_handlers.items():
        signal.signal(sig, handler)
    plan, rows = recover(out)
    (out / 'requests.jsonl').write_bytes(b''.join(encoded(r) for r in rows))
    write_json(out / 'buckets.json', buckets(plan, rows))
    write_json(out / 'replay-status.json', {'interrupted': stopped.is_set(), 'end_ts': time.time()})
    return plan, rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('tasks', 'trace', 'trace-sha256', 'start', 'out'):
        p.add_argument('--' + arg, required=True)
    p.add_argument('--rate-factor', required=True, type=float)
    p.add_argument('--fixture', action='store_true')
    a = p.parse_args()
    replay(a.tasks, a.trace, a.trace_sha256, a.start, a.rate_factor, a.out, fixture=a.fixture)


if __name__ == '__main__':
    main()
