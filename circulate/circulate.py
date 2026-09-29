#!/usr/bin/env python3
"""circulate: run the whole public-data path once, leave a receipt.

    python circulate/circulate.py [--stage NAME ...] [--offline] [--resume DATE] [--retained DIR] [--date YYYY-MM-DD]
    python circulate/circulate.py --finalize DATE        # recompute overall/RECEIPT.md/index after PROBES.json was written

See CONTRACT.md for the stage table and README.md for how to read a receipt. Exit codes: 0 overall OK,
2 any stage FAIL / a frozen file moved / a probe FAIL, 1 driver error.

Stdlib only; node for the page engine and Research Desk packet; gh for GitHub reads.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

CIRC = Path(__file__).resolve().parent
REPO = CIRC.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(CIRC))

from stages._common import Ctx, FAIL, HOLD, OK, SKIP, STATUSES, Hold, iso, sha256_file, utcnow  # noqa: E402

SCHEMA = 'circulate/receipt@1'
FIXTURE_DATE = dt.date(2026, 9, 29)   # offline runs pretend it is this day: the saved fixtures are windows around it
STAGES = ['inferencex', 'prices', 'status', 'economics', 'delta', 'r2-standing', 'newsletter', 'packet', 'frontdoor', 'tests']
MODULES = {'tests': 'run_tests'}
RETRO = 'clustermax-challenge/retrospective'
FROZEN_FILES = [f'{RETRO}/plan-R2.json', f'{RETRO}/PLAN-R2.md', f'{RETRO}/plan.json',
                f'{RETRO}/results/R2-result.json', f'{RETRO}/results/R2-result.md']
FROZEN_GLOBS = [(f'{RETRO}/results', 'R1-*')]
PIN = CIRC / 'frozen-hashes.json'
WORK_DIRS = ['inferencex', 'prices', 'price-history', 'status', 'economics', 'delta', 'newsletter', 'packet', 'sandbox']
RESULT_KEYS = ('name', 'status', 'started_utc', 'finished_utc', 'seconds', 'counts', 'sources', 'outputs', 'notes', 'error')


# ------------------------------------------------------------------ receipt schema
def validate_receipt(doc) -> list:
    """Return a list of problems (empty = valid circulate/receipt@1)."""
    p = []
    if not isinstance(doc, dict):
        return ['receipt is not an object']
    if doc.get('schema') != SCHEMA:
        p.append('schema != ' + SCHEMA)
    for k, t in (('date', str), ('mode', str), ('overall', str), ('started_utc', str), ('finished_utc', str), ('stages', list),
                 ('frozen', dict), ('complete', bool), ('disclosure', str), ('committed_paths', list)):
        if not isinstance(doc.get(k), t):
            p.append(f'{k}: expected {t.__name__}')
    if doc.get('mode') not in ('online', 'offline'):
        p.append('mode must be online|offline')
    if doc.get('overall') not in ('OK', 'FAIL', 'INCOMPLETE'):
        p.append('overall must be OK|FAIL|INCOMPLETE')
    names = []
    for i, s in enumerate(doc.get('stages') or []):
        if not isinstance(s, dict):
            p.append(f'stages[{i}] not an object')
            continue
        for k in RESULT_KEYS:
            if k not in s:
                p.append(f'stages[{i}] ({s.get("name")}) missing {k}')
        if s.get('status') not in STATUSES:
            p.append(f'stages[{i}] bad status {s.get("status")!r}')
        for k, t in (('counts', dict), ('sources', list), ('outputs', list)):
            if k in s and not isinstance(s[k], t):
                p.append(f'stages[{i}].{k} must be {t.__name__}')
        for o in s.get('outputs', []) if isinstance(s.get('outputs'), list) else []:
            if not (isinstance(o, dict) and isinstance(o.get('path'), str) and len(str(o.get('sha256', ''))) == 64):
                p.append(f'stages[{i}] output without path/sha256')
        for o in s.get('sources', []) if isinstance(s.get('sources'), list) else []:
            if not (isinstance(o, dict) and 'url' in o and 'sha256' in o):
                p.append(f'stages[{i}] source without url/sha256')
        if s.get('status') == FAIL and not (s.get('error') or s.get('notes')):
            p.append(f'stages[{i}] FAIL without error or notes')
        names.append(s.get('name'))
    if len(names) != len(set(names)):
        p.append('duplicate stage names')
    fz = doc.get('frozen') or {}
    for k in ('checked', 'moved'):
        if k not in fz:
            p.append(f'frozen.{k} missing')
    if doc.get('overall') == 'OK':
        if any(s.get('status') == FAIL for s in doc.get('stages', []) if isinstance(s, dict)):
            p.append('overall OK with a FAIL stage')
        if fz.get('moved'):
            p.append('overall OK with a moved frozen file')
    return p


# ------------------------------------------------------------------ helpers
def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(text, encoding='utf-8', newline='\n')
    os.replace(tmp, path)


def frozen_hashes() -> dict:
    out = {}
    for rel in FROZEN_FILES:
        p = REPO / rel
        out[rel] = sha256_file(p) if p.exists() else None
    for d, pat in FROZEN_GLOBS:
        for p in sorted((REPO / d).glob(pat)):
            out[p.relative_to(REPO).as_posix()] = sha256_file(p)
    return out


def tool_version(cmd) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=20)
        return (r.stdout or r.stderr).decode('utf-8', 'replace').strip().splitlines()[0]
    except Exception:  # noqa: BLE001
        return None


def git_head() -> dict:
    try:
        head = subprocess.run(['git', 'rev-parse', '--short=12', 'HEAD'], cwd=REPO, capture_output=True, timeout=20).stdout.decode().strip()
        return {'head': head or None}
    except Exception:  # noqa: BLE001
        return {'head': None}


def disclosure_text() -> str:
    p = REPO / 'hot-aisle/campaign/DISCLOSURES.md'
    lines, on = [], False
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines():
            if line.startswith('## Funding and relationship'):
                on = True
                continue
            if on and line.startswith('## '):
                break
            if on and line.strip():
                lines.append(line.strip().lstrip('- ').strip())
    sponsor = ' '.join(lines) if lines else 'Sponsor disclosure file hot-aisle/campaign/DISCLOSURES.md was not readable; see it before using any Hot Aisle figure.'
    return (sponsor + ' Imported external observations (InferenceX, MLPerf, OpenComputePrices, provider status pages, SemiAnalysis newsletter) are '
            'third-party data, not our measurements. Nothing in this receipt invents a value: a gated or unreachable source is HOLD with its HTTP code.')


def receipt_dir_for(date_s: str, offline: bool) -> Path:
    d = CIRC / 'receipts' / date_s
    if offline and (d / 'RECEIPT.json').exists():
        try:
            if json.loads((d / 'RECEIPT.json').read_text(encoding='utf-8')).get('mode') == 'online':
                return CIRC / 'receipts' / (date_s + '-offline')   # never overwrite a real receipt with a fixture run
        except (OSError, ValueError):
            pass
    return d


def resolve_output(ctx: Ctx, rel: str) -> Path | None:
    for base in (ctx.sandbox, ctx.repo, ctx.retained, ctx.circ):
        if base is None:
            continue
        p = Path(base) / rel
        if p.exists():
            return p
    return None


def reusable(ctx: Ctx, prev: dict) -> bool:
    if not prev or prev.get('status') not in (OK, HOLD, SKIP):
        return False
    for o in prev.get('outputs', []):
        p = resolve_output(ctx, o['path'])
        if p is None or sha256_file(p) != o['sha256']:
            return False
    return True


def load_stage_results(rdir: Path) -> dict:
    out = {}
    sd = rdir / 'stages'
    if sd.is_dir():
        for f in sd.glob('*.json'):
            try:
                d = json.loads(f.read_text(encoding='utf-8'))
                if isinstance(d, dict) and d.get('name'):
                    out[d['name']] = d
            except (OSError, ValueError):
                continue
    return out


def injected_stage():
    spec = os.environ.get('CIRCULATE_INJECT_SLEEP_STAGE', '').strip()
    if not spec:
        return None
    name, _, secs = spec.partition(':')
    return name.strip(), float(secs or 0)


def sleep_stage(name: str, seconds: float):
    def run(ctx):
        t0 = time.time()
        start = iso()
        ctx.log(f'injected stage {name}: sleeping {seconds}s')
        time.sleep(seconds)
        return {'name': name, 'status': OK, 'started_utc': start, 'finished_utc': iso(), 'seconds': round(time.time() - t0, 2),
                'counts': {'slept_seconds': seconds}, 'sources': [], 'outputs': [], 'notes': 'injected sleep stage (CIRCULATE_INJECT_SLEEP_STAGE)', 'error': None}
    return run


# ------------------------------------------------------------------ markdown
def render_md(doc: dict) -> str:
    L = [f'# Circulation receipt {doc["date"]}', '',
         f'**Overall: {doc["overall"]}**  |  mode: {doc["mode"]}  |  {doc["started_utc"]} to {doc["finished_utc"]} ({doc.get("seconds")} s of stage time)  |  '
         f'git {doc.get("git", {}).get("head")}  |  python {doc.get("host", {}).get("python")}, node {doc.get("host", {}).get("node")}', '']
    if not doc.get('complete'):
        L += ['> This receipt is INCOMPLETE: the run was interrupted or is still going. Re-run with `--resume`.', '']
    if doc['mode'] == 'offline':
        L += ['> OFFLINE FIXTURE RUN: every stage ran on the small saved files in circulate/fixtures/ with no network. Counts below describe fixtures, not the live sources.', '']
    L += ['## Stages', '', '| Stage | Status | Seconds | Counts | Notes |', '|---|---|---:|---|---|']
    for s in doc['stages']:
        c = {k: v for k, v in (s.get('counts') or {}).items() if v is not None and not isinstance(v, (dict, list))}
        cs = ', '.join(f'{k} {v}' for k, v in list(c.items())[:8])
        note = (s.get('notes') or '').replace('|', '/').replace('\n', ' ')
        if s.get('error'):
            note += ' ERROR: ' + str(s['error']).replace('|', '/').replace('\n', ' ')[:300]
        tag = ' (reused)' if s.get('reused') else ''
        L.append(f'| {s["name"]}{tag} | {s["status"]} | {s["seconds"]} | {cs} | {note[:600]} |')
    problems = [s for s in doc['stages'] if s['status'] in (HOLD, FAIL)]
    if problems:
        L += ['', '## HOLD and FAIL, in full', '']
        for s in problems:
            L.append(f'- **{s["name"]} {s["status"]}**: {s.get("notes") or ""}' + (f' Error: {s["error"]}' if s.get('error') else ''))
    fz = doc['frozen']
    L += ['', '## Frozen files', '',
          f'{fz["checked"]} frozen files hashed before and after the run' + (' (pin file created this run)' if fz.get('pin_created') else ' and compared with circulate/frozen-hashes.json') +
          f'. Moved: {", ".join(fz["moved"]) if fz["moved"] else "none"}.']
    if doc.get('probes'):
        pr = doc['probes']
        L += ['', '## Probes', '', f'PROBES.json: overall {pr.get("overall")}, counts {json.dumps(pr.get("counts"))}.']
    outs = [(s['name'], o) for s in doc['stages'] for o in s.get('outputs', [])]
    if outs:
        L += ['', '## Outputs', '', '| Stage | Path | Committed | SHA-256 |', '|---|---|---|---|']
        L += [f'| {n} | {o["path"]} | {"yes" if o.get("committed") else ("sandbox (offline)" if doc["mode"] == "offline" else "no (retained)")} | {o["sha256"][:16]}... |' for n, o in outs]
    L += ['', '## Disclosure', '', doc['disclosure'], '']
    if doc.get('retained_artifact'):
        L += [f'Bulk outputs (raw artifacts, raw pages, per-day price files, full delta) are not committed; in CI they are uploaded as the workflow artifact `{doc["retained_artifact"]}`.', '']
    return '\n'.join(L)


# ------------------------------------------------------------------ assemble / finalize
def assemble(rdir: Path, meta: dict, results: dict, order: list, probes_doc, frozen: dict, complete: bool) -> dict:
    stages = [results[n] for n in order if n in results]
    fails = [s for s in stages if s['status'] == FAIL]
    probe_fail = bool(probes_doc and (probes_doc.get('counts', {}).get('FAIL') or probes_doc.get('overall') == 'FAIL'))
    overall = 'FAIL' if (fails or frozen['moved'] or probe_fail) else ('OK' if complete else 'INCOMPLETE')
    doc = {'schema': SCHEMA, 'date': meta['date'], 'mode': meta['mode'], 'complete': complete, 'overall': overall,
           'started_utc': min([s['started_utc'] for s in stages] or [meta['started_utc']]), 'finished_utc': max([s['finished_utc'] for s in stages] or [iso()]),
           'seconds': round(sum(s['seconds'] for s in stages), 1),
           'host': meta['host'], 'git': meta['git'], 'driver': meta['driver'], 'stages': stages, 'frozen': frozen,
           'probes': ({'overall': probes_doc.get('overall'), 'counts': probes_doc.get('counts')} if probes_doc else None),
           'committed_paths': sorted({o['path'] for s in stages for o in s.get('outputs', []) if o.get('committed')} if meta['mode'] == 'online' else []),
           'retained_artifact': f'circulate-retained-{meta["date"]}' if meta['mode'] == 'online' else None,
           'disclosure': meta['disclosure']}
    return doc


def write_receipt(rdir: Path, doc: dict) -> None:
    atomic_write(rdir / 'RECEIPT.json', json.dumps(doc, indent=2, allow_nan=False) + '\n')
    atomic_write(rdir / 'RECEIPT.md', render_md(doc))


def update_index(doc: dict) -> None:
    path = CIRC / 'receipts' / 'index.json'
    try:
        idx = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        idx = []
    pr = doc.get('probes') or {}
    c = pr.get('counts') or {}
    entry = {'date': doc['date'], 'overall': doc['overall'], 'mode': doc['mode'],
             'stages': [{'name': s['name'], 'status': s['status']} for s in doc['stages']],
             'probes': ({'pass': c.get('PASS', 0), 'fail': c.get('FAIL', 0), 'skip': c.get('SKIP', 0), 'hold': c.get('HOLD', 0)} if pr else None)}
    idx = [e for e in idx if e.get('date') != doc['date']] + [entry]
    idx.sort(key=lambda e: e['date'])
    atomic_write(path, json.dumps(idx, indent=1) + '\n')


def finalize(date_s: str) -> int:
    rdir = CIRC / 'receipts' / date_s
    try:
        doc = json.loads((rdir / 'RECEIPT.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        print(f'cannot read {rdir}/RECEIPT.json: {e}', file=sys.stderr)
        return 1
    probes = None
    if (rdir / 'PROBES.json').exists():
        try:
            probes = json.loads((rdir / 'PROBES.json').read_text(encoding='utf-8'))
        except ValueError:
            probes = {'overall': 'FAIL', 'counts': {'FAIL': 1}}
    fails = [s for s in doc['stages'] if s['status'] == FAIL]
    probe_fail = bool(probes and (probes.get('counts', {}).get('FAIL') or probes.get('overall') == 'FAIL'))
    doc['overall'] = 'FAIL' if (fails or doc['frozen']['moved'] or probe_fail) else ('OK' if doc.get('complete') else 'INCOMPLETE')
    doc['probes'] = {'overall': probes.get('overall'), 'counts': probes.get('counts')} if probes else None
    if doc['stages']:
        doc['started_utc'] = min(x['started_utc'] for x in doc['stages'])
        doc['finished_utc'] = max(x['finished_utc'] for x in doc['stages'])
        doc['seconds'] = round(sum(x['seconds'] for x in doc['stages']), 1)
    write_receipt(rdir, doc)
    if doc['mode'] == 'online':
        update_index(doc)
        atomic_write(CIRC / 'LATEST.md', render_md(doc))
    print(f'finalized {rdir.name}: overall {doc["overall"]}')
    return 0 if doc['overall'] == 'OK' else 2


# ------------------------------------------------------------------ main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--stage', action='append', nargs='+', metavar='NAME', help='run only these stages (others keep any earlier result)')
    ap.add_argument('--offline', action='store_true', help='run every stage on circulate/fixtures/ with no network; writes only under circulate/')
    ap.add_argument('--resume', metavar='DATE', help='re-run only stages whose result in that receipt is missing or FAIL; completed stages are reused by hash')
    ap.add_argument('--retained', metavar='DIR', help='where bulk (uncommitted) outputs go; default circulate/retained (offline: circulate/retained/offline)')
    ap.add_argument('--date', metavar='YYYY-MM-DD', help='override the receipt date (default: today UTC)')
    ap.add_argument('--finalize', metavar='DATE', help='recompute overall/RECEIPT.md/index for a receipt after PROBES.json changed, then exit')
    ap.add_argument('--list', action='store_true', help='list stages and exit')
    a = ap.parse_args(argv)
    if a.list:
        print('\n'.join(STAGES))
        return 0
    if a.finalize:
        return finalize(a.finalize)
    wanted = [n for grp in (a.stage or []) for n in grp]
    bad = [n for n in wanted if n not in STAGES]
    inj = injected_stage()
    if bad and not (inj and bad == [inj[0]]):
        print(f'unknown stage(s): {bad}; known: {STAGES}', file=sys.stderr)
        return 1
    today = a.resume if a.resume else (a.date or utcnow().strftime('%Y-%m-%d'))
    date = dt.date.fromisoformat(today)
    offline = a.offline
    rdir = receipt_dir_for(today, offline)
    if a.retained:
        retained = Path(a.retained).resolve()
    else:
        retained = CIRC / 'retained' / ('offline' if offline else '')
    retained.mkdir(parents=True, exist_ok=True)
    sandbox = retained / 'sandbox' if offline else None
    prior = load_stage_results(rdir) if (a.resume or wanted) else {}
    if not a.resume and not wanted:
        # a fresh run replaces that day's receipt
        if rdir.exists():
            shutil.rmtree(rdir)
        if offline:
            for d in WORK_DIRS:
                shutil.rmtree(retained / d, ignore_errors=True)
    if offline:
        sandbox.mkdir(parents=True, exist_ok=True)
    (rdir / 'stages').mkdir(parents=True, exist_ok=True)
    (rdir / 'logs').mkdir(parents=True, exist_ok=True)
    driver_log = rdir / 'RECEIPT-driver.log'

    def dlog(msg):
        line = f'{iso()} {msg}'
        print(line, flush=True)
        with open(driver_log, 'a', encoding='utf-8') as f:
            f.write(line + '\n')

    # frozen pin
    before = frozen_hashes()
    pin_created = False
    if PIN.exists():
        pin = json.loads(PIN.read_text(encoding='utf-8'))
    else:
        pin = {k: v for k, v in before.items() if v}
        atomic_write(PIN, json.dumps(pin, indent=2, sort_keys=True) + '\n')
        pin_created = True
    pre_moved = sorted(k for k, v in pin.items() if before.get(k) != v)
    if pre_moved:
        dlog(f'FROZEN FILE MOVED BEFORE THE RUN: {pre_moved}')

    meta = {'date': today, 'mode': 'offline' if offline else 'online', 'started_utc': iso(), 't0': time.time(),
            'host': {'platform': platform.platform(), 'python': platform.python_version(), 'node': (tool_version(['node', '--version']) or '').lstrip('v'),
                     'gh': tool_version(['gh', '--version'])},
            'git': git_head(), 'driver': {'path': 'circulate/circulate.py', 'sha256': sha256_file(Path(__file__))},
            'disclosure': disclosure_text()}
    if a.resume and (rdir / 'RECEIPT.json').exists():
        try:
            old = json.loads((rdir / 'RECEIPT.json').read_text(encoding='utf-8'))
            meta['started_utc'] = old.get('started_utc', meta['started_utc'])
        except ValueError:
            pass
    order = list(STAGES)
    injected = None
    if inj:
        injected = inj
        if inj[0] not in order:
            order.append(inj[0])
    todo = [n for n in order if not wanted or n in wanted]
    results: dict = {}
    ctx_results: dict = {}
    dlog(f'circulate {meta["mode"]} run for {today}; receipt dir {rdir.relative_to(CIRC)}; retained {retained}; stages {todo}')

    def snapshot(complete=False):
        try:
            frozen_now = {'checked': len(pin), 'pin_created': pin_created, 'moved': pre_moved, 'sha256': before}
            doc = assemble(rdir, meta, results, order, None, frozen_now, complete)
            write_receipt(rdir, doc)
        except Exception as e:  # noqa: BLE001 - a snapshot problem must not kill the run
            dlog(f'receipt snapshot failed: {e}')

    for name in order:
        if name not in todo:
            if name in prior:
                results[name] = prior[name]
            elif wanted:
                results[name] = {'name': name, 'status': SKIP, 'started_utc': iso(), 'finished_utc': iso(), 'seconds': 0.0, 'counts': {},
                                 'sources': [], 'outputs': [], 'notes': 'not selected (--stage)', 'error': None}
            continue
        log_path = rdir / 'logs' / f'{name}.log'
        ctx = Ctx(REPO, CIRC, FIXTURE_DATE if offline else date, offline, retained, sandbox, log_path, ctx_results)
        ctx.stage = name
        if a.resume and reusable(ctx, prior.get(name)):
            r = dict(prior[name])
            r['reused'] = True
            results[name] = prior[name] | {'reused': True}
            ctx_results[name] = prior[name]
            dlog(f'== stage {name}: reused (outputs match their recorded hashes; status {r["status"]})')
            continue
        dlog(f'== stage {name} ==')
        log_path.write_text('', encoding='utf-8')
        t0 = time.time()
        started = iso()
        try:
            if injected and name == injected[0]:
                r = sleep_stage(name, injected[1])(ctx)
            else:
                mod = importlib.import_module('stages.' + MODULES.get(name, name.replace('-', '_')))
                r = mod.run(ctx)
        except Hold as h:
            r = {'name': name, 'status': HOLD, 'started_utc': started, 'finished_utc': iso(), 'seconds': round(time.time() - t0, 2), 'counts': {},
                 'sources': [], 'outputs': [], 'notes': str(h) + (f' [HTTP {h.http}]' if h.http else ''), 'error': None}
        except Exception as e:  # noqa: BLE001 - a broken stage records FAIL and the driver continues
            tb = traceback.format_exc()
            ctx.log('EXCEPTION\n' + tb)
            r = {'name': name, 'status': FAIL, 'started_utc': started, 'finished_utc': iso(), 'seconds': round(time.time() - t0, 2), 'counts': {},
                 'sources': [], 'outputs': [], 'notes': f'stage raised {type(e).__name__}', 'error': f'{type(e).__name__}: {e}'}
        miss = [k for k in RESULT_KEYS if k not in r]
        if miss or r.get('status') not in STATUSES:
            r = {'name': name, 'status': FAIL, 'started_utc': started, 'finished_utc': iso(), 'seconds': round(time.time() - t0, 2), 'counts': {},
                 'sources': [], 'outputs': [], 'notes': 'stage returned a malformed StageResult', 'error': f'missing keys {miss}; status {r.get("status")!r}'}
        r['log'] = f'logs/{name}.log'
        results[name] = r
        ctx_results[name] = r
        atomic_write(rdir / 'stages' / f'{name}.json', json.dumps(r, indent=2, allow_nan=False, default=str) + '\n')
        dlog(f'== stage {name}: {r["status"]} in {r["seconds"]} s. {str(r.get("notes"))[:200]}')
        snapshot(False)

    after = frozen_hashes()
    moved = sorted(k for k in set(after) | set(pin) if after.get(k) != pin.get(k) or after.get(k) != before.get(k))
    frozen = {'checked': len(pin), 'pin_created': pin_created, 'moved': moved, 'sha256': after}
    probes_doc = None
    if (rdir / 'PROBES.json').exists():
        try:
            probes_doc = json.loads((rdir / 'PROBES.json').read_text(encoding='utf-8'))
        except ValueError:
            probes_doc = None
    complete = all(n in results for n in order)
    doc = assemble(rdir, meta, results, order, probes_doc, frozen, complete)
    write_receipt(rdir, doc)
    if not offline:
        update_index(doc)
        atomic_write(CIRC / 'LATEST.md', render_md(doc))
    problems = validate_receipt(doc)
    if problems:
        dlog('RECEIPT SCHEMA PROBLEMS: ' + '; '.join(problems[:5]))
    dlog(f'overall {doc["overall"]}; stages ' + ', '.join(f'{s["name"]} {s["status"]}' for s in doc['stages']) +
         (f'; FROZEN MOVED {moved}' if moved else ''))
    if problems:
        return 1
    return 0 if doc['overall'] == 'OK' else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
