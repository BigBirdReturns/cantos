"""Stage frontdoor: keep the Hot Aisle front door and kit in step with its data.

Checks (read-only) that the market strip and Run 3 record embedded in hot-aisle/index.html equal
data/market.json and data/run3/record.json, that the Run 3 record verifies with runner/lib/record.cjs, and that
scripts/build_kit.py --check passes. Online, a stale embed is fixed with `node data/run3/build-run3.cjs --embed`
(only when the market data changed) and a stale kit with build_kit.py; both are the repo's own deterministic
builders. Offline nothing is rewritten: a stale tree is reported as FAIL and the record is verified from the fixture
copy in circulate/fixtures/run3/.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from stages._common import FAIL, OK, SKIP, Stage, sha256_file

NAME = 'frontdoor'
HOT = 'hot-aisle'


def embedded(html: str, name: str):
    m = re.search(r'<!-- ' + name + r':begin --><script id="' + name + r'" type="application/json">(.*?)</script><!-- ' + name + r':end -->', html, re.S)
    return json.loads(m.group(1).replace('<\\/', '</')) if m else None


def embeds_in_sync(hot: Path):
    html = (hot / 'index.html').read_text(encoding='utf-8')
    market = json.loads((hot / 'data/market.json').read_text(encoding='utf-8'))
    rec = json.loads((hot / 'data/run3/record.json').read_text(encoding='utf-8'))
    rec_embed = embedded(html, 'run3-record')
    want = {**rec, 'links': {'report': 'data/run3/report.html', 'evidence': 'data/run3/evidence.json', 'record': 'data/run3/record.json'}}
    return {'market': embedded(html, 'market-data') == market, 'record': rec_embed == want}


def verify_record(ctx, rec_path: Path):
    js = ("const r=require(process.argv[1]);const rec=JSON.parse(require('fs').readFileSync(process.argv[2],'utf8'));"
          "const v=r.verify(rec);console.log(JSON.stringify({verified:v.verified,problems:v.problems,engine:v.engine&&v.engine.version}));"
          "process.exit(v.verified?0:1)")
    p = ctx.run(['node', '-e', js, str(ctx.repo / HOT / 'runner/lib/record.cjs'), str(rec_path)], timeout=120)
    try:
        return json.loads(p.out_text.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {'verified': False, 'problems': [(p.err_text or p.out_text)[-200:]]}


def run(ctx):
    s = Stage(ctx, NAME)
    hot = ctx.repo / HOT
    changed = []
    sync = embeds_in_sync(hot)
    s.counts.update(market_embed_in_sync=sync['market'], record_embed_in_sync=sync['record'])
    if not all(sync.values()):
        if ctx.offline:
            return s.done(FAIL, f'embedded data in hot-aisle/index.html is stale ({[k for k, v in sync.items() if not v]}); offline run does not rewrite it.')
        p = ctx.run(['node', 'data/run3/build-run3.cjs', '--embed'], cwd=hot, timeout=600)
        if p.returncode != 0:
            return s.done(FAIL, 'build-run3.cjs --embed failed', error=(p.err_text or p.out_text)[-400:])
        changed += ['index.html', 'data/run3']
        sync = embeds_in_sync(hot)
        if not all(sync.values()):
            return s.done(FAIL, 'embedded data is still stale after build-run3.cjs --embed')
    rec_path = ctx.fixtures / 'run3/record.json' if ctx.offline else hot / 'data/run3/record.json'
    v = verify_record(ctx, rec_path)
    s.counts.update(record_verified=bool(v.get('verified')), record_sha256=sha256_file(rec_path)[:16])
    if ctx.offline:
        s.counts['fixture_matches_committed_record'] = sha256_file(rec_path) == sha256_file(hot / 'data/run3/record.json')
    if not v.get('verified'):
        return s.done(FAIL, 'Run 3 record does not verify: ' + '; '.join(v.get('problems', []))[:300])
    chk = ctx.run(['python', '-B', 'scripts/build_kit.py', '--check'], cwd=hot, timeout=300)
    if chk.returncode != 0:
        if ctx.offline:
            return s.done(FAIL, 'kit is stale (build_kit.py --check failed); offline run does not rebuild: ' + chk.out_text.strip()[-200:])
        b = ctx.run(['python', '-B', 'scripts/build_kit.py'], cwd=hot, timeout=300)
        if b.returncode != 0:
            return s.done(FAIL, 'build_kit.py failed', error=(b.err_text or b.out_text)[-400:])
        chk = ctx.run(['python', '-B', 'scripts/build_kit.py', '--check'], cwd=hot, timeout=300)
        if chk.returncode != 0:
            return s.done(FAIL, 'kit still stale after build_kit.py')
        changed += ['MANIFEST.json', 'workload-report.zip']
    s.counts['kit'] = chk.out_text.strip().splitlines()[-1][:120]
    for rel in changed:
        p = hot / rel
        if p.is_file():
            s.output(p)
        elif p.is_dir():
            for f in sorted(p.rglob('*')):
                if f.is_file():
                    s.output(f)
    if changed:
        return s.done(OK, 'rebuilt: ' + ', '.join(changed) + '; embeds in sync, record verified, kit matches source.')
    return s.done(SKIP, 'nothing to rebuild: embeds equal data/market.json and data/run3/record.json, Run 3 record verified, kit matches source.')
