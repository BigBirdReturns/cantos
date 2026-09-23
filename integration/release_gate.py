"""Hold full-site publication until the exact product sources pass native CI.

Unrelated data-only commits may reuse a passing run with identical source trees.
A matching failed run holds publication; stale green runs never qualify new bytes.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = '.github/workflows/hot-aisle-ci.yml'
PUBLISHERS = ('pta-fetch.yml', 'organ-evolution-observe.yml', 'axm-witness-0.9.2.yml', 'axm-witness-live-readback-0.9.2.yml')
SCOPES = ('hot-aisle', 'compute', 'integration', '.gitattributes', WORKFLOW) + tuple('.github/workflows/' + p for p in PUBLISHERS)

def git(*args: str) -> str:
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()

def local_signature() -> dict[str, str]:
    dirty = git('status', '--porcelain', '--untracked-files=all', '--', *SCOPES)
    if dirty:
        raise RuntimeError('Product source differs from its committed identity: ' + dirty)
    return {p: git('rev-parse', 'HEAD:' + p) for p in SCOPES}

class GitHub:
    def __init__(self, repository: str):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('A repository owner/name is required.')
        self.base = 'https://api.github.com/repos/' + repository
        self.cache: dict[str, dict] = {}

    def get(self, suffix: str) -> dict:
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'second-run-release-gate'}
        token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
        if token:
            headers['Authorization'] = 'Bearer ' + token
        with urlopen(Request(self.base + suffix, headers=headers), timeout=20) as response:
            return json.load(response)

    def signature(self, sha: str) -> dict:
        if not re.fullmatch(r'[a-f0-9]{40}', sha):
            raise ValueError('Workflow source must be an exact commit.')
        if sha not in self.cache:
            tree = self.get('/git/trees/' + sha)
            entries = {e['path']: e['sha'] for e in tree['tree']}
            sig = {p: entries.get(p) for p in SCOPES if '/' not in p}
            if all(sig.values()):
                for p in SCOPES:
                    if '/' in p:
                        sig[p] = self.get('/contents/' + p + '?ref=' + sha)['sha']
            self.cache[sha] = sig
        return self.cache[sha]

def decide(runs: list[dict], target: dict, signature) -> dict:
    eligible = [r for r in runs if r.get('event') in ('push', 'workflow_dispatch')]
    eligible.sort(key=lambda r: (r.get('created_at', ''), r['id']), reverse=True)
    for run in eligible:
        if signature(run['head_sha']) != target:
            continue
        result = {'run_id': run['id'], 'tested_commit': run['head_sha'],
                  'run_url': run.get('html_url'), 'source_identity': target}
        if run['status'] != 'completed':
            return {**result, 'state': 'WAIT', 'reason': 'Matching qualification is still running.'}
        if run.get('conclusion') == 'success':
            return {**result, 'state': 'PASS'}
        return {**result, 'state': 'HOLD', 'reason': 'Matching qualification ended: ' + str(run.get('conclusion'))}
    return {'state': 'WAIT', 'reason': 'No qualification run matches these product source trees.'}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY'))
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    if args.timeout < 0 or args.timeout > 900:
        parser.error('Timeout must be between 0 and 900 seconds.')
    api = GitHub(args.repository or '')
    target = local_signature()
    head = git('rev-parse', 'HEAD')
    api.cache[head] = target
    deadline = time.monotonic() + args.timeout
    while True:
        runs = api.get('/actions/workflows/hot-aisle-ci.yml/runs?per_page=100')['workflow_runs']
        result = decide(runs, target, api.signature)
        result.update(schema='second-run/publication-gate@1', deployment_commit=head,
                      checked_at=datetime.now(timezone.utc).isoformat())
        if result['state'] == 'WAIT' and time.monotonic() < deadline:
            print(json.dumps(result), flush=True)
            time.sleep(min(10, max(0, deadline - time.monotonic())))
            continue
        if result['state'] == 'WAIT':
            result.update(state='HOLD', reason='Timed out: ' + result['reason'])
        if result['state'] == 'PASS' and local_signature() != target:
            raise RuntimeError('Product sources changed while awaiting qualification.')
        print(json.dumps(result, indent=2), flush=True)
        if args.receipt:
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        return 0 if result['state'] == 'PASS' else 1

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('PUBLICATION HELD: ' + str(exc), flush=True)
        raise SystemExit(1)
