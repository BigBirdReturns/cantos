"""Shared plumbing for circulate stages. Stdlib only.

A stage module exposes `run(ctx) -> StageResult` (see CONTRACT.md). ctx is a `Ctx`. Stages never talk to the
network except through ctx.gh() / ctx.http(), which refuse in --offline mode, and never write a committed path
except through ctx.out(), which maps to a sandbox in --offline mode. Nothing here invents a value.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

OK, HOLD, FAIL, SKIP = 'OK', 'HOLD', 'FAIL', 'SKIP'
STATUSES = (OK, HOLD, FAIL, SKIP)
UA = 'circulate/1 (+https://github.com/second-run/axm-tools)'


class NetworkDisabled(RuntimeError):
    pass


class Hold(Exception):
    """Raise inside a stage to end it as HOLD (ran, correctly refused to produce a number)."""

    def __init__(self, message, http=None):
        super().__init__(message)
        self.http = http


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(t: dt.datetime | None = None) -> str:
    return (t or utcnow()).strftime('%Y-%m-%dT%H:%M:%SZ')


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(chunk), b''):
            h.update(b)
    return h.hexdigest()


def write_json(p: Path, obj, indent=2) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=indent, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def read_json(p: Path):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def gz_write_lines(p: Path, lines) -> int:
    """Deterministic gzip (mtime 0) of newline-terminated strings. Returns line count."""
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(p, 'wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=9) as gz:
        for line in lines:
            gz.write(line.encode('utf-8') + b'\n')
            n += 1
    return n


def gz_read_lines(p: Path):
    with gzip.open(p, 'rt', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                yield line


def parse_headers(head: bytes) -> tuple[int, dict]:
    lines = head.decode('utf-8', 'replace').splitlines()
    status = int(lines[0].split()[1])
    headers = {}
    for line in lines[1:]:
        if ':' in line:
            k, v = line.split(':', 1)
            headers[k.strip().lower()] = v.strip()
    return status, headers


class Ctx:
    """Everything a stage may touch."""

    def __init__(self, repo: Path, circ: Path, today: dt.date, offline: bool, retained: Path,
                 sandbox: Path | None, log_path: Path, results: dict | None = None):
        self.repo, self.circ, self.today, self.offline = Path(repo), Path(circ), today, offline
        self.retained = Path(retained)
        self.sandbox = Path(sandbox) if sandbox else None
        self.fixtures = self.circ / 'fixtures'
        self.results = results if results is not None else {}   # StageResults finished earlier in this run
        self.stage = ''
        self._log_path = log_path
        self.committed: list[str] = []                          # repo-relative committed outputs written by this stage
        self.gh_calls = 0
        self.min_rate_remaining = None
        self.slept = 0.0
        self.rate_sleep_cap = float(os.environ.get('CIRCULATE_RATE_SLEEP_CAP', '900'))
        self.extra: dict = {}

    # ---- paths ---------------------------------------------------------------------------------------------
    def out(self, rel: str) -> Path:
        """Path for a committed output (repo-relative). Sandboxed in --offline mode."""
        rel = rel.replace('\\', '/')
        if self.offline:
            p = self.sandbox / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def committed_read(self, rel: str) -> Path:
        """Where the current committed state lives for reading: the sandbox copy if a stage seeded one offline."""
        rel = rel.replace('\\', '/')
        if self.offline:
            sp = self.sandbox / rel
            if sp.exists():
                return sp
        return self.repo / rel

    def seed(self, rel: str, src: Path) -> Path:
        """Offline: place a fixture at the sandbox location of a committed path (only if absent)."""
        dst = self.sandbox / rel.replace('\\', '/')
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        return dst

    def stage_dir(self, name: str | None = None) -> Path:
        d = self.retained / (name or self.stage)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def rel(self, p: Path) -> str:
        p = Path(p)
        for base in (self.sandbox, self.repo, self.circ, self.retained):
            if base is None:
                continue
            try:
                return p.resolve().relative_to(Path(base).resolve()).as_posix()
            except ValueError:
                continue
        return str(p).replace('\\', '/')

    def output(self, p: Path, committed: bool = True) -> dict:
        """OutputRecord for a written file; also remembers it as a committed path for the receipt."""
        p = Path(p)
        rel = self.rel(p)
        if committed and not self.offline and rel not in self.committed:
            self.committed.append(rel)
        # offline runs write a sandbox copy, never a committed path
        return {'path': rel, 'sha256': sha256_file(p), 'bytes': p.stat().st_size, 'committed': bool(committed) and not self.offline}

    # ---- logging -------------------------------------------------------------------------------------------
    def log(self, msg: str) -> None:
        line = f'{iso()} [{self.stage}] {msg}'
        print(line, flush=True)
        try:
            with open(self._log_path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except OSError:
            pass

    # ---- subprocess ----------------------------------------------------------------------------------------
    def run(self, cmd, cwd=None, timeout=1800, env=None, check=False) -> subprocess.CompletedProcess:
        self.log('$ ' + ' '.join(str(c) for c in cmd))
        e = dict(os.environ)
        e.setdefault('PYTHONUTF8', '1')
        e['PYTHONDONTWRITEBYTECODE'] = '1'
        if env:
            e.update(env)
        p = subprocess.run([str(c) for c in cmd], cwd=str(cwd or self.repo), capture_output=True, timeout=timeout, env=e)
        out = p.stdout.decode('utf-8', 'replace')
        err = p.stderr.decode('utf-8', 'replace')
        tail = (out + ('\n' + err if err.strip() else '')).strip().splitlines()[-40:]
        for line in tail:
            self.log('  | ' + line)
        self.log(f'  exit {p.returncode}')
        if check and p.returncode != 0:
            raise RuntimeError(f'{cmd[0]} exited {p.returncode}')
        p.out_text, p.err_text = out, err
        return p

    # ---- network -------------------------------------------------------------------------------------------
    def _guard(self):
        if self.offline:
            raise NetworkDisabled('network access attempted in --offline mode')

    def _rate(self, headers: dict) -> None:
        rem = headers.get('x-ratelimit-remaining')
        if rem is None:
            return
        rem = int(rem)
        self.min_rate_remaining = rem if self.min_rate_remaining is None else min(self.min_rate_remaining, rem)
        if rem <= 5:
            reset = int(headers.get('x-ratelimit-reset', '0'))
            wait = max(1, reset - int(time.time()) + 2)
            if wait > self.rate_sleep_cap:
                raise Hold(f'GitHub rate limit exhausted (X-RateLimit-Remaining={rem}); reset in {wait}s exceeds the {self.rate_sleep_cap:.0f}s sleep cap', http=403)
            self.log(f'rate limit low (remaining {rem}); sleeping {wait}s until reset')
            time.sleep(wait)
            self.slept += wait

    def gh(self, endpoint: str, retries: int = 3):
        """GET a GitHub API endpoint through the authenticated gh CLI. Returns (status, headers, body_bytes).
        Honors X-RateLimit-Remaining (sleeps to reset, or raises Hold when the reset is too far away) and
        Retry-After on 403/429. Never retries with different credentials."""
        self._guard()
        if not shutil.which('gh'):
            raise Hold('gh CLI not available; GitHub API not reachable without it', http=None)
        url = endpoint if endpoint.startswith('/') or endpoint.startswith('repos/') else '/' + endpoint
        for attempt in range(retries):
            self.gh_calls += 1
            p = subprocess.run(['gh', 'api', '--method', 'GET', '--include', url], capture_output=True, timeout=600)
            data = p.stdout
            sep = b'\r\n\r\n' if b'\r\n\r\n' in data else b'\n\n'
            if not data.startswith(b'HTTP/') or sep not in data:
                raise RuntimeError('gh api gave no HTTP headers: ' + p.stderr.decode('utf-8', 'replace')[:300])
            head, body = data.split(sep, 1)
            status, headers = parse_headers(head)
            if status in (403, 429):
                retry = headers.get('retry-after')
                rem = headers.get('x-ratelimit-remaining')
                if retry or rem == '0':
                    reset = int(headers.get('x-ratelimit-reset', '0'))
                    wait = int(retry) if retry else max(1, reset - int(time.time()) + 2)
                    if wait > self.rate_sleep_cap:
                        raise Hold(f'HTTP {status} rate limited; wait {wait}s exceeds cap {self.rate_sleep_cap:.0f}s', http=status)
                    self.log(f'HTTP {status} rate limited; sleeping {wait}s')
                    time.sleep(wait)
                    self.slept += wait
                    continue
                raise Hold(f'HTTP {status} from {url} (access refused; not retried with other credentials)', http=status)
            self._rate(headers)
            return status, headers, body
        raise Hold('GitHub API still rate limited after retries', http=403)

    def rate_check(self) -> int | None:
        """Query GET /rate_limit (free) and sleep/raise Hold like gh() does. Returns core remaining."""
        self._guard()
        if not shutil.which('gh'):
            return None
        p = subprocess.run(['gh', 'api', '/rate_limit', '--jq', '.resources.core'], capture_output=True, timeout=60)
        try:
            core = json.loads(p.stdout.decode('utf-8'))
        except ValueError:
            return None
        self._rate({'x-ratelimit-remaining': str(core['remaining']), 'x-ratelimit-reset': str(core['reset'])})
        return int(core['remaining'])

    def http(self, url: str, timeout: float = 30.0, headers: dict | None = None, max_bytes: int = 64 << 20):
        """GET a public URL. Returns (status, headers, body). HTTP errors return their status instead of raising."""
        self._guard()
        req = urllib.request.Request(url, headers={'User-Agent': UA, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(max_bytes + 1)[:max_bytes]
        except urllib.error.HTTPError as e:
            return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, (e.read() or b'')
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise RuntimeError(f'{url}: {e}') from e


def result(name: str, status: str, started: float, started_utc: str, counts=None, sources=None, outputs=None,
           notes: str = '', error: str | None = None) -> dict:
    assert status in STATUSES, status
    return {'name': name, 'status': status, 'started_utc': started_utc, 'finished_utc': iso(),
            'seconds': round(time.time() - started, 2), 'counts': counts or {}, 'sources': sources or [],
            'outputs': outputs or [], 'notes': notes, 'error': error}


class Stage:
    """Context manager helper: `with Stage(ctx, 'name') as s:` ... `return s.done(OK, ...)`."""

    def __init__(self, ctx: Ctx, name: str):
        self.ctx, self.name = ctx, name
        self.t0 = time.time()
        self.started_utc = iso()
        self.counts: dict = {}
        self.sources: list = []
        self.outputs: list = []

    def source(self, url: str, data: bytes | str | None = None, sha: str | None = None) -> None:
        if sha is None and data is not None:
            sha = sha256_bytes(data if isinstance(data, bytes) else data.encode('utf-8'))
        self.sources.append({'url': url, 'sha256': sha, 'retrieved_utc': iso()})

    def output(self, p: Path, committed: bool = True) -> None:
        self.outputs.append(self.ctx.output(p, committed))

    def done(self, status: str, notes: str = '', error: str | None = None) -> dict:
        return result(self.name, status, self.t0, self.started_utc, self.counts, self.sources, self.outputs, notes, error)

    def hold(self, exc: Hold) -> dict:
        note = str(exc) + (f' [HTTP {exc.http}]' if exc.http else '')
        return self.done(HOLD, note)


def import_by_path(name: str, path: Path, extra_sys_path: Path | None = None):
    import importlib.util
    if extra_sys_path and str(extra_sys_path) not in sys.path:
        sys.path.insert(0, str(extra_sys_path))
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def replace_marked_block(text: str, begin: str, end: str, block: str, insert_after: str | None = None) -> str:
    """Replace the text between two marker lines (inclusive) with `block`; insert if absent."""
    b, e = text.find(begin), text.find(end)
    full = f'{begin}\n{block.rstrip()}\n{end}'
    if b != -1 and e != -1 and e > b:
        return text[:b] + full + text[e + len(end):]
    if insert_after and insert_after in text:
        i = text.index(insert_after) + len(insert_after)
        return text[:i] + '\n\n' + full + text[i:]
    return text.rstrip('\n') + '\n\n' + full + '\n'
