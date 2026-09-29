"""Stage tests: the fast suites that guard every joint circulate touches.

Online: hot-aisle runner node tests, the workbench engine test, clustermax-challenge unittest + engine parity,
backfill importer --self-test, integration pytest, and validate_packet.js on the committed Research Desk packet.
Offline: the same suites except the slow ones (full clustermax unittest -> the collector and retrospective modules,
integration pytest -> one module, validate_packet -> the offline standing packet), so a fixture run stays under a minute.
A suite whose runner is missing is recorded as skipped, never as passed. Any failing suite fails the stage.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from stages._common import FAIL, OK, SKIP, Stage

NAME = 'tests'


def suites(ctx):
    r = ctx.repo
    runner_tests = sorted(str(p.relative_to(r)).replace('\\', '/') for p in (r / 'hot-aisle/runner/test').glob('*.test.cjs'))
    py = sys.executable
    out = [
        ('hot-aisle runner (node --test)', ['node', '--test'] + runner_tests, r),
        ('hot-aisle workbench engine', ['node', 'hot-aisle/scripts/test_workbench.cjs'], r),
        ('backfill importer --self-test', [py, '-B', 'hot-aisle/campaign/backfill/importer.py', '--self-test'], r),
        ('clustermax engine parity (node)', ['node', 'clustermax-challenge/tests/test_engine.cjs'], r),
    ]
    if ctx.offline:
        out.append(('clustermax collectors + retrospective (unittest)',
                    [py, '-B', '-m', 'unittest', 'tests.test_collect_status', 'tests.test_collect_status_modes', 'tests.test_retrospective'], r / 'clustermax-challenge'))
        out.append(('integration task_contract (pytest)', [py, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'integration/tests/test_task_contract.py'], r))
        sp = ctx.sandbox / 'research-desk/packets/PUBLIC-TAIL-standing.research-packet.json'
        if sp.exists():
            out.append(('validate_packet on the offline standing packet', ['node', 'research-desk/packets/validate_packet.js', str(sp)], r))
    else:
        out.append(('clustermax-challenge unittest (all)', [py, '-B', '-m', 'unittest', 'discover', '-s', 'clustermax-challenge/tests', '-p', 'test_*.py'], r))
        out.append(('integration pytest', [py, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'integration/tests'], r))
        out.append(('validate_packet on the committed packet', ['node', 'research-desk/packets/validate_packet.js'], r))
    return out


def run(ctx):
    s = Stage(ctx, NAME)
    results = []
    for label, cmd, cwd in suites(ctx):
        t0 = time.time()
        if cmd[0] == sys.executable and '-m' in cmd and cmd[cmd.index('-m') + 1] == 'pytest':
            probe = ctx.run([sys.executable, '-c', 'import pytest'], timeout=60)
            if probe.returncode != 0:
                results.append({'suite': label, 'status': 'skipped', 'note': 'pytest not installed', 'seconds': 0})
                continue
        p = ctx.run(cmd, cwd=cwd, timeout=1500, env={'PYTHONPATH': str(cwd)} if 'unittest' in cmd else None)
        tail = (p.out_text + '\n' + p.err_text).strip().splitlines()
        results.append({'suite': label, 'status': 'pass' if p.returncode == 0 else 'FAIL', 'exit': p.returncode,
                        'seconds': round(time.time() - t0, 1), 'last_line': (tail[-1] if tail else '')[:160]})
    failed = [r for r in results if r['status'] == 'FAIL']
    s.counts.update(suites=len(results), passed=sum(1 for r in results if r['status'] == 'pass'), failed=len(failed),
                    skipped=sum(1 for r in results if r['status'] == 'skipped'), detail=results)
    if failed:
        return s.done(FAIL, f'{len(failed)} suite(s) failed: ' + ', '.join(r['suite'] for r in failed),
                      error='; '.join(f'{r["suite"]}: exit {r["exit"]}: {r["last_line"]}' for r in failed)[:600])
    return s.done(OK, f'{s.counts["passed"]} suites passed' + (f', {s.counts["skipped"]} skipped (runner missing)' if s.counts['skipped'] else '') +
                  ('; offline run uses the reduced set' if ctx.offline else '') + '.')
