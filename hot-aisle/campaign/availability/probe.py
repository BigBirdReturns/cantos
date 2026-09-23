"""Read-only availability sampling and append-only, operator-attested receipts."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
TOKENS = {'hotaisle': 'HOTAISLE_API_TOKEN', 'digitalocean': 'DIGITALOCEAN_TOKEN'}
DO = 'https://api.digitalocean.com/v2/sizes'
HA = 'https://admin.hotaisle.app/api'


def stamp(value=None):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00')) if value else datetime.now(timezone.utc)
    if dt.tzinfo is None:
        raise ValueError('timestamp needs a UTC offset')
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def key(row):
    fields = tuple(row[name] for name in ('provider', 'sku', 'region', 'gpus'))
    if any(not isinstance(v, str) or not v.strip() for v in fields[:3]):
        raise ValueError('provider, sku and region must be nonempty strings')
    if type(fields[3]) is not int or fields[3] < 1:
        raise ValueError('gpus must be a positive integer')
    return fields


def config(path):
    cfg = json.loads(Path(path).read_text(encoding='utf-8'))
    rows = cfg['probes']
    if not rows or len({key(r) for r in rows}) != len(rows):
        raise ValueError('probes must be nonempty and unique')
    if any(r['provider'] not in TOKENS for r in rows):
        raise ValueError('unsupported provider')
    return cfg


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('redirect refused')


def get_json(url, header):
    req = urllib.request.Request(url, headers={'Authorization': header, 'Accept': 'application/json'}, method='GET')
    with urllib.request.build_opener(NoRedirect).open(req, timeout=20) as response:
        body = response.read(8 * 1024 * 1024 + 1)
    if len(body) > 8 * 1024 * 1024:
        raise ValueError('response too large')
    return json.loads(body)


def do_pages(token, fetch=get_json):
    url, seen, sizes = DO + '?per_page=200', set(), []
    while url:
        parts = urllib.parse.urlsplit(url)
        if (parts.scheme, parts.netloc, parts.path) != ('https', 'api.digitalocean.com', '/v2/sizes') or parts.fragment:
            raise ValueError('unsafe pagination link')
        if url in seen or len(seen) >= 20:
            raise ValueError('pagination cycle or limit')
        seen.add(url)
        page = fetch(url, 'Bearer ' + token)
        if not isinstance(page, dict) or not isinstance(page.get('sizes'), list):
            raise ValueError('invalid sizes response')
        sizes.extend(page['sizes'])
        url = page.get('links', {}).get('pages', {}).get('next')
        if url is not None and not isinstance(url, str):
            raise ValueError('invalid next link')
    return sizes


def digitalocean(rows, target):
    matches = [r for r in rows if isinstance(r, dict) and r.get('slug') == target['sku']]
    if len(matches) != 1:
        return 'unknown', 'SKU absent or duplicated in complete size listing'
    r = matches[0]
    if type(r.get('available')) is not bool or not isinstance(r.get('regions'), list) or any(not isinstance(s, str) for s in r['regions']):
        return 'unknown', 'invalid available flag or region list'
    count = r.get('gpu_info', {}).get('count')
    if type(count) is not int or count != target['gpus']:
        return 'unknown', 'GPU count missing or mismatched'
    available = r['available'] and target['region'] in r['regions']
    return ('available' if available else 'out_of_capacity'), 'size available flag AND region membership; not a create guarantee'


def hotaisle(rows, target, settings):
    if settings.get('region_scope') != target['region']:
        return 'unknown', 'UNVERIFIED regional scope: API response has no region field'
    if not target['sku'].startswith('vm-mi300x-'):
        return 'unknown', 'SKU is outside the VM MI300X adapter'
    if not isinstance(rows, list):
        return 'unknown', 'invalid VM availability response'
    counts = []
    for r in rows:
        if not isinstance(r, dict):
            return 'unknown', 'invalid VM entry'
        gpus = r.get('Specs', {}).get('gpus', [])
        if not isinstance(gpus, list) or not gpus:
            return 'unknown', 'missing GPU identity'
        if any(not isinstance(g, dict) or type(g.get('count')) is not int for g in gpus):
            return 'unknown', 'invalid GPU identity'
        if sum(g['count'] for g in gpus) == target['gpus'] and all(g.get('model', '').upper() == 'MI300X' for g in gpus):
            quantity = r.get('Quantity')
            if type(quantity) is not int or quantity < 0:
                return 'unknown', 'invalid VM quantity'
            counts.append(quantity)
    if not counts:
        return 'unknown', 'matching VM type absent; absence is not proven stockout'
    return ('available' if sum(counts) else 'out_of_capacity'), 'matching VM quantity in operator-verified regional scope'


def collect(cfg, dry_run=False, env=None, fetch=get_json, now=None):
    env = os.environ if env is None else env
    results = []
    for provider in sorted({r['provider'] for r in cfg['probes']}):
        reason, payload = None, None
        settings = cfg.get('hotaisle', {})
        try:
            if dry_run:
                payload = json.loads((ROOT / 'fixtures' / (provider + '.json')).read_text(encoding='utf-8'))
                if provider == 'digitalocean':
                    payload = payload['sizes']
            elif not env.get(TOKENS[provider], '').strip():
                reason = 'missing ' + TOKENS[provider]
            elif provider == 'digitalocean':
                payload = do_pages(env[TOKENS[provider]], fetch)
            elif not settings.get('team') or settings.get('auth_status') != 'verified':
                reason = 'UNVERIFIED Hot Aisle auth or missing team; see README'
            else:
                team = urllib.parse.quote(settings['team'], safe='')
                payload = fetch(HA + '/teams/' + team + '/virtual_machines/available/', 'Token ' + env[TOKENS[provider]].removeprefix('Token '))
        except urllib.error.HTTPError as exc:
            reason = 'HTTP ' + str(exc.code)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            reason = 'transport, JSON or schema failure (response and credentials omitted)'
        for target in cfg['probes']:
            if target['provider'] != provider:
                continue
            try:
                outcome, detail = ('unknown', reason) if reason else (digitalocean(payload, target) if provider == 'digitalocean' else hotaisle(payload, target, settings))
            except (ValueError, TypeError, KeyError, AttributeError):
                outcome, detail = 'unknown', 'response schema failure'
            row = dict(zip(('provider', 'sku', 'region', 'gpus'), key(target)))
            row.update(ts=stamp(now), method='api', layer='listed', outcome=outcome,
                       provisioned=False, reason=detail, synthetic=bool(dry_run))
            results.append(row)
    return results


@contextmanager
def ledger_lock(path):
    lock = Path(str(path) + '.lock')
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, str(os.getpid()).encode('ascii'))
        os.close(fd)
        fd = None
        yield
    finally:
        if fd is not None:
            os.close(fd)
        lock.unlink()


def append(path, rows):
    path = Path(path)
    with ledger_lock(path):
        old = path.read_bytes() if path.exists() else b''
        if old and not old.endswith(b'\n'):
            raise ValueError('ledger has an incomplete final line; preserve and investigate')
        existing = [json.loads(line) for line in old.splitlines() if line.strip()]
        ids = {r.get('attempt_id') for r in existing if r.get('layer') == 'delivered'}
        for row in rows:
            if row.get('layer') == 'delivered':
                if row['attempt_id'] in ids:
                    raise ValueError('duplicate delivered attempt ID')
                ids.add(row['attempt_id'])
        data = ''.join(json.dumps(r, sort_keys=True, allow_nan=False) + '\n' for r in rows).encode('utf-8')
        with path.open('ab') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())


def delivered(receipt):
    key(receipt)
    row = {k: receipt[k] for k in ('provider', 'sku', 'region', 'gpus')}
    for name in ('attempt_id', 'evidence'):
        if not isinstance(receipt.get(name), str) or not receipt[name].strip():
            raise ValueError(name + ' required')
        row[name] = receipt[name]
    if receipt.get('real_create_attempt') is not True or receipt.get('synthetic'):
        raise ValueError('a real create attempt must be explicitly attested')
    outcome = receipt.get('outcome')
    if outcome not in ('available', 'out_of_capacity', 'out_of_stock', 'create_failed', 'ssh_failed', 'unknown'):
        raise ValueError('unsupported delivered outcome')
    if type(receipt.get('ssh_reached')) is not bool or receipt['ssh_reached'] != (outcome == 'available'):
        raise ValueError('available requires confirmed SSH; other outcomes require ssh_reached=false')
    if outcome == 'available':
        seconds = receipt.get('time_to_ssh_s')
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError('successful delivery needs finite nonnegative time_to_ssh_s')
        row['time_to_ssh_s'] = seconds
    row.update(ts=stamp(receipt['ts']), method='create-attempt', layer='delivered', outcome=outcome, real_create_attempt=True,
               provisioned=receipt['ssh_reached'], ssh_reached=receipt['ssh_reached'], synthetic=False)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'probes.json')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--dry-run', action='store_true', help='fixtures only; stdout by default')
    parser.add_argument('--delivered', type=Path, help='append an operator-attested receipt; never creates resources')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        import unittest
        return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT), 'test_availability.py')).wasSuccessful() else 1
    if args.delivered and args.dry_run:
        parser.error('--delivered and --dry-run are mutually exclusive')
    try:
        rows = [delivered(json.loads(args.delivered.read_text(encoding='utf-8')))] if args.delivered else collect(config(args.config), args.dry_run)
        output = args.output or (None if args.dry_run else ROOT / 'observations.jsonl')
        if args.dry_run and output and output.resolve() == (ROOT / 'observations.jsonl').resolve():
            raise ValueError('dry-run cannot append to the campaign ledger')
        if output:
            append(output, rows)
        print('\n'.join(json.dumps(r, sort_keys=True) for r in rows))
        return 1 if not args.dry_run and not args.delivered and all(r['outcome'] == 'unknown' for r in rows) else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
