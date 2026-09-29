"""Stage economics: Run 3 economics recomputed at every dated public price, through the page engine.

Runs hot-aisle/campaign/market/economics_by_date.cjs unchanged (it calls the page's own report engine `costing`
over the retained, engine-accepted Run 3 counts) inside a scratch copy of the tree it expects, so the price day
files it needs can come from retained/ instead of the committed tree (only INDEX.json is committed). A day whose
file is missing or whose SHA-256 differs from INDEX.json is not priced; the stage never fills it in.

  every INDEX day has a verified file  -> recompute; byte-identical to the committed rows = OK (unchanged),
                                          different = rows rewritten (new days appended)
  some day files are absent (CI)       -> verify-only: every committed row must still match INDEX.json's file
                                          hashes and the current Run 3 source hashes; SKIP if it does, HOLD if the
                                          INDEX has days with no committed row and no file to price them
MARKET.md gets a marked "standing refresh" block computed from the rows; nothing in it is typed by hand.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from stages._common import FAIL, HOLD, OK, SKIP, Stage, read_json, replace_marked_block, sha256_file

NAME = 'economics'
MARKET = 'hot-aisle/campaign/market'
ROWS = f'{MARKET}/RUN3-ECONOMICS-BY-DATE.jsonl'
MD = f'{MARKET}/MARKET.md'
INDEX = 'hot-aisle/data/price-history/INDEX.json'
BEGIN, END = '<!-- circulate:market:begin -->', '<!-- circulate:market:end -->'
NEEDS = {'ha': 'hot_aisle', 'cmp': 'digitalocean'}
RUN3 = [('run3-scored-a-t0', ['detailed.json', 'grade/evaluation.json', 'ledger-times.json']),
        ('run3-scored-n-t0', ['detailed.json', 'grade/evaluation.json', 'closure.json'])]


def day_sources(ctx):
    roots = [ctx.retained / 'price-history', ctx.repo / 'hot-aisle/data/price-history']
    if not ctx.offline:
        sessions = Path(os.environ.get('CIRCULATE_SESSIONS') or (ctx.repo.parent / 'sessions'))
        roots.append(sessions / 'public-tail-20260929/lanes/opencomputeprices/price-history')
    return roots


def find_day(roots, provider, date, want_sha):
    for r in roots:
        f = r / provider / f'{date}.json'
        if f.exists() and sha256_file(f) == want_sha:
            return f
    return None


def build_scratch(ctx, index_all):
    """Copy what economics_by_date.cjs reads into retained/economics/root/hot-aisle. Returns (root, available_days, all_days)."""
    hot = ctx.repo / 'hot-aisle'
    root = ctx.stage_dir() / 'root' / 'hot-aisle'
    shutil.rmtree(root.parent, ignore_errors=True)
    (root / 'campaign/market').mkdir(parents=True)
    for n in ('economics_by_date.cjs', 'run3_engine_accept.cjs'):
        shutil.copyfile(hot / 'campaign/market' / n, root / 'campaign/market' / n)
    shutil.copyfile(hot / 'index.html', root / 'index.html')
    for arm, files in RUN3:
        for f in files:
            dst = root / 'campaign/results' / arm / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(hot / 'campaign/results' / arm / f, dst)
    roots = day_sources(ctx)
    ha = index_all['providers']['hot_aisle']['files']
    dof = {f['date']: f for f in index_all['providers'].get('digitalocean', {}).get('files', [])}
    keep_days, ha_keep, do_keep = [], [], []
    for f in ha:
        h = find_day(roots, 'hot_aisle', f['date'], f['sha256'])
        if h is None:
            continue
        keep_days.append(f['date'])
        ha_keep.append(f)
        shutil.copyfile(h, _mk(root / 'data/price-history/hot_aisle' / f"{f['date']}.json"))
        d = dof.get(f['date'])
        if d:
            dp = find_day(roots, 'digitalocean', f['date'], d['sha256'])
            if dp is not None:
                do_keep.append(d)
                shutil.copyfile(dp, _mk(root / 'data/price-history/digitalocean' / f"{f['date']}.json"))
    idx = json.loads(json.dumps(index_all))
    idx['providers'] = {'hot_aisle': dict(idx['providers']['hot_aisle'], files=ha_keep),
                        'digitalocean': dict(idx['providers'].get('digitalocean', {}), files=do_keep)}
    (root / 'data/price-history').mkdir(parents=True, exist_ok=True)
    (root / 'data/price-history/INDEX.json').write_text(json.dumps(idx, indent=1) + '\n', encoding='utf-8')
    return root, keep_days, [f['date'] for f in ha]


def _mk(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def verify_only(ctx, index_all, rows):
    """Committed rows vs INDEX.json hashes and the current Run 3 sources. Returns (problems, verified_days, missing_days)."""
    hot = ctx.repo / 'hot-aisle'
    problems = []
    ha = {f['date']: f['sha256'] for f in index_all['providers']['hot_aisle']['files']}
    dof = {f['date']: f['sha256'] for f in index_all['providers'].get('digitalocean', {}).get('files', [])}
    verified, seen = 0, set()
    r3 = None
    for r in rows:
        if r['kind'] != 'dated':
            continue
        seen.add(r['date'])
        sh = r['source_sha256']
        if ha.get(r['date']) != sh.get('hot_aisle_price_file'):
            problems.append(f"{r['date']}: hot_aisle price file hash differs from INDEX.json")
        if dof.get(r['date']) != sh.get('comparator_price_file'):
            problems.append(f"{r['date']}: comparator price file hash differs from INDEX.json")
        if sh.get('opencomputeprices_prices_jsonl') != index_all['generated_from']['sha256']:
            problems.append(f"{r['date']}: source prices.jsonl hash differs from INDEX.json generated_from")
        if r3 is None:
            r3 = {'hot_aisle_detailed': sha256_file(hot / 'campaign/results/run3-scored-a-t0/detailed.json'),
                  'hot_aisle_evaluation': sha256_file(hot / 'campaign/results/run3-scored-a-t0/grade/evaluation.json'),
                  'comparator_detailed': sha256_file(hot / 'campaign/results/run3-scored-n-t0/detailed.json'),
                  'comparator_evaluation': sha256_file(hot / 'campaign/results/run3-scored-n-t0/grade/evaluation.json')}
        if r['run3_source_sha256'] != r3:
            problems.append(f"{r['date']}: Run 3 source hashes differ from the retained arm files")
        verified += 1
    return problems[:20], verified, sorted(set(ha) - seen)


def market_block(ctx, rows, index_all, mode_note):
    dated = [r for r in rows if r['kind'] == 'dated']
    priced = [r for r in dated if r.get('cost_per_1k_accepted_hot_aisle') is not None and r.get('cost_per_1k_accepted_comparator') is not None]
    last = priced[-1] if priced else None
    lines = [f'## Standing refresh ({ctx.today.isoformat()}, circulate)', '',
             f'Computed by `circulate/stages/economics.py` from `RUN3-ECONOMICS-BY-DATE.jsonl` and `data/price-history/INDEX.json`; nothing here is typed by hand. {mode_note}', '',
             f'- Rows: {len(dated)} dated ({len(priced)} priced for both providers, {len(dated) - len(priced)} with a missing price day left blank, never interpolated).',
             f'- Public series last day in INDEX.json: {index_all["series_range"]["last"]} (source `{index_all["generated_from"]["release"]["release_tag"]}`, retrieved {index_all["generated_from"]["release"]["retrieved_utc"]}).']
    if last:
        lines.append(f'- Latest priced day {last["date"]}: Hot Aisle ${last["hot_aisle_gpu_hour"]}/GPU-hr gives ${last["cost_per_1k_accepted_hot_aisle"]} per 1k accepted; '
                     f'DigitalOcean H100 ${last["comparator_gpu_hour"]}/GPU-hr gives ${last["cost_per_1k_accepted_comparator"]} '
                     f'(Hot Aisle cheaper by {round(100 * last["hot_aisle_cheaper_by"], 1)}%). Accepted counts {last["accepted_hot_aisle"]} and {last["accepted_comparator"]} '
                     f'(engine {last["engine"]}).')
    return '\n'.join(lines)


def run(ctx):
    s = Stage(ctx, NAME)
    hot = ctx.repo / 'hot-aisle'
    idx_path = ctx.committed_read(INDEX)
    index_all = json.loads(idx_path.read_text(encoding='utf-8'))
    rows_path = ctx.repo / ROWS
    committed_rows = [json.loads(l) for l in rows_path.read_text(encoding='utf-8').splitlines() if l.strip()] if rows_path.exists() else []
    root, keep, all_days = build_scratch(ctx, index_all)
    s.counts.update(index_days=len(all_days), days_with_verified_files=len(keep), committed_rows=len(committed_rows))
    if ctx.offline:
        # offline: the sandbox INDEX only prices days whose files this run produced; never touch the committed rows
        if not keep:
            return s.done(SKIP, 'no verified price day files under retained/ (run the prices stage first); nothing priced.')
    elif len(keep) < len(all_days):
        problems, verified, missing = verify_only(ctx, index_all, committed_rows)
        s.counts.update(verified_rows=verified, unpriced_days=len(missing))
        if problems:
            return s.done(FAIL, 'committed economics rows no longer match their sources: ' + '; '.join(problems[:5]), error='; '.join(problems)[:500])
        if missing:
            return s.done(HOLD, f'{len(missing)} INDEX day(s) have no committed row and no verified price file here ({missing[0]}..{missing[-1]}); not priced.')
        return s.done(SKIP, f'{verified} committed dated rows verified against INDEX.json and the Run 3 sources; day files absent here ({len(keep)}/{len(all_days)}), so no recompute.')
    node = ctx.run(['node', 'economics_by_date.cjs'], cwd=root / 'campaign/market', timeout=600)
    if node.returncode != 0:
        return s.done(FAIL, 'economics_by_date.cjs failed', error=(node.err_text or node.out_text)[-400:])
    new_path = root / 'campaign/market' / 'RUN3-ECONOMICS-BY-DATE.jsonl'
    new_bytes = new_path.read_bytes()
    new_rows = [json.loads(l) for l in new_bytes.decode('utf-8').splitlines() if l.strip()]
    s.counts.update(rows_computed=len(new_rows), dated_priced=sum(1 for r in new_rows if r['kind'] == 'dated' and r.get('cost_per_1k_accepted_hot_aisle') is not None))
    out_rows = ctx.out(ROWS)
    unchanged = (not ctx.offline) and rows_path.exists() and rows_path.read_bytes() == new_bytes
    if not unchanged:
        out_rows.write_bytes(new_bytes)
        s.output(out_rows)
        note = f'{len(new_rows)} rows written.'
    else:
        note = f'recomputed {len(new_rows)} rows through the page engine; byte-identical to the committed file.'
    md_real = hot / 'campaign/market/MARKET.md'
    if ctx.offline:
        ctx.seed(MD, md_real)
    md = ctx.out(MD)
    text = md.read_text(encoding='utf-8') if md.exists() else md_real.read_text(encoding='utf-8')
    block = market_block(ctx, new_rows, index_all, 'Recomputed in this run.' if not unchanged else 'Recomputed in this run and identical to the committed rows.')
    new_text = replace_marked_block(text, BEGIN, END, block)
    if new_text != text:
        md.write_text(new_text, encoding='utf-8', newline='\n')
        s.output(md)
    return s.done(OK, note)
