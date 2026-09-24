#!/usr/bin/env python3
"""Bounded public-source fan-out for operating inputs. Never installs or dispatches.

Refresh is explicit. Output must be a new file. Failed reads keep last-good
observation timestamps intact. Bytes becoming available does not qualify software,
prices, availability, licences, or user outcomes. Only metadata/hashes are emitted.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2 * 1024 * 1024
REGISTRY_SCHEMA = 'second-run/material-registry@1'
SNAPSHOT_SCHEMA = 'second-run/material-observations@1'
ALLOWED_HOSTS = frozenset(('hotaisle.xyz', 'dstack.ai', 'opencode.ai',
    'docs.lmcache.ai', 'docs.sglang.ai', 'docs.vllm.ai', 'docs.skypilot.co',
    'github.com', 'api.github.com'))
ID = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
SHA = re.compile(r'^[a-f0-9]{64}$')


def stamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError('timestamp must be a string')
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('timestamp requires timezone')
    return t.astimezone(timezone.utc)


def load_registry(raw: bytes) -> dict:
    if len(raw) > MAX_BYTES:
        raise ValueError('registry too large')
    r = json.loads(raw)
    if r.get('schema') != REGISTRY_SCHEMA:
        raise ValueError('unsupported registry')
    sources = r.get('sources')
    if not isinstance(sources, list) or not 1 <= len(sources) <= 50:
        raise ValueError('registry needs 1..50 sources')
    seen = set()
    for s in sources:
        sid = s.get('id', '')
        if not ID.fullmatch(sid) or sid in seen:
            raise ValueError('invalid or duplicate source id')
        seen.add(sid)
        u = urllib.parse.urlsplit(s.get('url', ''))
        if (u.scheme != 'https' or u.hostname not in ALLOWED_HOSTS or
            u.username or u.password or u.fragment or u.port not in (None, 443)):
            raise ValueError('source URL outside public allowlist')
        if s.get('kind') not in ('document', 'github_releases'):
            raise ValueError('unsupported source kind')
        if s['kind'] == 'github_releases' and (u.hostname != 'api.github.com' or
            not re.fullmatch(r'/repos/[^/]+/[^/]+/releases', u.path)):
            raise ValueError('release source must be a repository releases endpoint')
        ttl = s.get('ttl_seconds')
        if type(ttl) is not int or not 60 <= ttl <= 604800:
            raise ValueError('invalid source TTL')
        for k in ('layer', 'purpose', 'on_change'):
            if not isinstance(s.get(k), str) or not s[k].strip():
                raise ValueError('missing source semantics')
    recipes = r.get('recipes', [])
    ids = set()
    for recipe in recipes:
        rid = recipe.get('id', '')
        if not ID.fullmatch(rid) or rid in ids:
            raise ValueError('invalid or duplicate recipe id')
        ids.add(rid)
        if not recipe.get('sources') or any(x not in seen for x in recipe['sources']):
            raise ValueError('recipe has unknown or empty dependencies')
    return r


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('redirect refused; review and update the registered URL')


def fetch_bytes(source: dict) -> bytes:
    req = urllib.request.Request(source['url'], headers={
        'User-Agent': 'SecondRun-operating-inputs/0.1 (+public-source-review)',
        'Accept': 'application/json' if source['kind'] == 'github_releases' else 'text/html',
        'Accept-Encoding': 'identity'})
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=8) as response:
        if response.status != 200:
            raise ValueError(f'HTTP {response.status}')
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('source exceeds byte limit')
        return raw


def identity(source: dict, raw: bytes) -> dict:
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('empty or oversized source')
    digest = hashlib.sha256(raw).hexdigest()
    if source['kind'] == 'document':
        return {'content_sha256': digest, 'semantic_identity': None,
                'interpretation': 'Bytes observed only. Page changes need review; no quote or capability extracted.'}
    payload = json.loads(raw)
    if not isinstance(payload, list) or len(payload) > 100:
        raise ValueError('unexpected releases payload')
    releases = []
    for x in payload:
        if not isinstance(x, dict) or x.get('draft'):
            continue
        tag = x.get('tag_name')
        if not isinstance(tag, str) or not tag or len(tag) > 256:
            raise ValueError('release without bounded tag')
        published = x.get('published_at')
        if published is not None:
            stamp(published)
        releases.append({'tag': tag, 'published_at': published,
                         'prerelease': bool(x.get('prerelease'))})
    canonical = json.dumps(releases, sort_keys=True, separators=(',', ':')).encode()
    return {'content_sha256': digest, 'semantic_identity': hashlib.sha256(canonical).hexdigest(),
            'releases': releases, 'interpretation': 'Release metadata only; tags are not immutable binary or image digests.'}


def collect(registry: dict, registry_hash: str, previous: dict | None = None,
            fetcher=fetch_bytes, now: datetime | None = None, workers: int = 4) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not SHA.fullmatch(registry_hash):
        raise ValueError('registry hash invalid')
    prior = {}
    previous_compatible = False
    if previous:
        previous_compatible = (previous.get('schema') == SNAPSHOT_SCHEMA and
                               previous.get('registry_sha256') == registry_hash)
        if previous_compatible:
            prior = {x['id']: x for x in previous.get('observations', [])}

    def observe(source):
        checked = now.isoformat()
        before = prior.get(source['id'], {})
        last = before.get('last_good')
        if last:
            try:
                if (stamp(last['observed_at']) > now or
                    not SHA.fullmatch(last['content_sha256'])):
                    last = None
            except (ValueError, KeyError, TypeError):
                last = None
        result = {'id': source['id'], 'url': source['url'], 'checked_at': checked,
                  'kind': source['kind'], 'layer': source['layer']}
        try:
            fetched = fetcher(source)
            captured_at = now
            origin = 'DIRECT_PUBLIC_GET'
            if isinstance(fetched, dict):
                captured_at = stamp(fetched['observed_at'])
                if captured_at > now:
                    raise ValueError('out-of-band capture is dated in the future')
                origin = 'OPERATOR_SUPPLIED_CAPTURE'
                fetched = fetched['raw']
            value = identity(source, fetched)
            if value.get('releases') is not None:
                if any(x['published_at'] and stamp(x['published_at']) > now for x in value['releases']):
                    raise ValueError('release claims a future publication time')
            key = 'semantic_identity' if source['kind'] == 'github_releases' else 'content_sha256'
            change = ('NEW' if not last else
                      'UNCHANGED' if value[key] == last.get(key) else 'CHANGED')
            result.update(status='OBSERVED', change=change, last_good={**value,
                'observed_at': captured_at.isoformat(), 'expires_at': (captured_at + timedelta(seconds=source['ttl_seconds'])).isoformat(), 'capture_kind': origin},
                next_action=source['on_change'] if change != 'UNCHANGED' else 'No material identity change observed.')
        except Exception as exc:
            # Preserve history on an inaccessible source; never turn failure into freshness.
            result.update(status='UNAVAILABLE', change='UNKNOWN', last_good=last,
                          error=str(exc)[:350], next_action='Retain last observation and review source access; no automatic retry or promotion.')
        return result

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as pool:
        observations = list(pool.map(observe, registry['sources']))
    return {'schema': SNAPSHOT_SCHEMA, 'registry_sha256': registry_hash,
            'collected_at': now.isoformat(), 'previous_compatible': previous_compatible,
            'observations': observations,
            'summary': {'observed': sum(x['status'] == 'OBSERVED' for x in observations),
                        'unavailable': sum(x['status'] == 'UNAVAILABLE' for x in observations)},
            'boundary': 'Public-source observation. No live inventory, tenant quote, licence approval, compatibility qualification or dispatch authority.'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True, help='New snapshot path; overwrite refused')
    ap.add_argument('--previous', type=Path)
    ap.add_argument('--observed', type=Path, help='Optional out-of-band raw source bytes manifest: {id:{path,sha256,observed_at}}. Never silently re-dates old captures.')
    args = ap.parse_args(argv)
    if args.output.exists():
        ap.error('output exists; choose a new snapshot name')
    raw = (ROOT/'materials/registry.json').read_bytes()
    registry = load_registry(raw)
    previous = json.loads(args.previous.read_bytes()) if args.previous else None
    fetcher = fetch_bytes
    if args.observed:
        manifest = json.loads(args.observed.read_bytes())
        base = args.observed.resolve().parent
        if not isinstance(manifest, dict) or set(manifest) - {s['id'] for s in registry['sources']}:
            ap.error('out-of-band manifest has unknown source ids')
        def captured_or_live(source):
            if source['id'] not in manifest:
                return fetch_bytes(source)
            item = manifest[source['id']]
            target = (base / item['path']).resolve()
            if item.get('url') != source['url'] or not target.is_relative_to(base):
                raise ValueError('capture leaves approved directory or does not match source URL')
            if target.stat().st_size > MAX_BYTES:
                raise ValueError('capture exceeds byte limit')
            payload = target.read_bytes()
            if hashlib.sha256(payload).hexdigest() != item['sha256']:
                raise ValueError('capture hash mismatch')
            return {'raw': payload, 'observed_at': item['observed_at']}
        fetcher = captured_or_live
    snapshot = collect(registry, hashlib.sha256(raw).hexdigest(), previous, fetcher=fetcher)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(snapshot, f, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps(snapshot['summary']))
    return 0 if snapshot['summary']['observed'] else 2


if __name__ == '__main__':
    sys.exit(main())
