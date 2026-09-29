"""Stage packet: the Research Desk packet with the standing newsletter rows appended, then validated.

research-desk/packets/build_packet.js writes fixed output paths (the frozen PUBLIC-TAIL-2026-09-29 packet and its
notes) and reads the session lane folders, so this stage never runs it in place. It does two things instead:
  1. base check (only where the session lanes exist): copy build_packet.js and the pinned app.html into
     retained/ and rebuild there; record whether the rebuilt packet is byte-identical to the committed one;
  2. append: stages/packet_append.js continues the committed packet's hash chain with one `source` record per
     row in research-desk/packets/newsletter-standing.jsonl, using build_packet.js's own exported hash/canonical.
     Output packets/PUBLIC-TAIL-standing.research-packet.json (+ .sha256); then validate_packet.js (the app's own
     verifyPacket replay) must exit 0.
With no standing rows the committed packet stands and nothing is written. Offline the base is the first 25
events of the committed packet so validation takes a second, not a minute.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from stages._common import FAIL, HOLD, OK, SKIP, Stage, iso, sha256_bytes, sha256_file

NAME = 'packet'
PK = 'research-desk/packets'
BASE = f'{PK}/PUBLIC-TAIL-2026-09-29.research-packet.json'
ROWS = f'{PK}/newsletter-standing.jsonl'
OUT = f'{PK}/PUBLIC-TAIL-standing.research-packet.json'
PREFIX = 25


def base_rebuild_check(ctx, s):
    sessions = Path(os.environ.get('CIRCULATE_SESSIONS') or (ctx.repo.parent / 'sessions'))
    if ctx.offline or not (sessions / 'clustermax-cloudreview-20260929').exists() or not (sessions / 'public-tail-20260929/lanes').exists():
        return None
    work = ctx.stage_dir() / 'rebuild'
    shutil.rmtree(work, ignore_errors=True)
    (work / 'packets').mkdir(parents=True)
    shutil.copyfile(ctx.repo / 'research-desk/app.html', work / 'app.html')
    shutil.copyfile(ctx.repo / PK / 'build_packet.js', work / 'packets/build_packet.js')
    p = ctx.run(['node', 'build_packet.js'], cwd=work / 'packets', env={'PT_SESSIONS': str(sessions)}, timeout=900)
    built = work / 'packets/PUBLIC-TAIL-2026-09-29.research-packet.json'
    if p.returncode != 0 or not built.exists():
        return {'ran': True, 'identical': None, 'error': (p.err_text or p.out_text)[-200:]}
    # the working tree may hold CRLF (git autocrlf); the repository blob is LF, which is what build_packet.js writes
    committed = (ctx.repo / BASE).read_bytes().replace(b'\r\n', b'\n')
    notes = json.loads((ctx.repo / PK / 'PUBLIC-TAIL-2026-09-29.build-notes.json').read_text(encoding='utf-8'))
    built_sha = sha256_file(built)
    return {'ran': True, 'identical': sha256_bytes(committed) == built_sha, 'matches_build_notes': built_sha == notes.get('packet_file_sha256')}


def run(ctx):
    s = Stage(ctx, NAME)
    rows_path = ctx.committed_read(ROWS)
    n_rows = sum(1 for l in rows_path.read_text(encoding='utf-8').splitlines() if l.strip()) if rows_path.exists() else 0
    chk = base_rebuild_check(ctx, s)
    if chk is not None:
        s.counts['base_rebuild_identical'] = chk.get('identical')
        s.counts['base_rebuild_matches_build_notes'] = chk.get('matches_build_notes')
        if chk.get('identical') is False or chk.get('error'):
            return s.done(HOLD, 'the committed base packet is not reproduced by build_packet.js from the current lane inputs '
                                + (chk.get('error') or '(byte difference)') + '; standing packet not built on it.')
    s.counts['standing_rows'] = n_rows
    if n_rows == 0:
        return s.done(SKIP, 'no standing newsletter rows; the committed packet stands' +
                      ('' if chk is None else f' (rebuilt from the lane inputs: identical={chk["identical"]})') + '.')
    out = ctx.out(OUT)
    at = iso()
    cmd = ['node', str(ctx.circ / 'stages/packet_append.js'), '--packets-dir', str(ctx.repo / PK), '--base', str(ctx.repo / BASE),
           '--rows', str(rows_path), '--out', str(out), '--at', at]
    if ctx.offline:
        cmd += ['--prefix', str(PREFIX), '--label', 'circulate offline fixture packet (prefix of the public-tail packet + fixture newsletter rows)']
    p = ctx.run(cmd, timeout=900)
    if p.returncode == 3:
        return s.done(HOLD, 'packet would exceed Research Desk import limits (3000 events / 12 MB): ' + p.out_text.strip()[-160:])
    if p.returncode != 0:
        return s.done(FAIL, 'packet_append.js failed', error=(p.err_text or p.out_text)[-400:])
    info = json.loads(p.out_text.strip().splitlines()[-1])
    s.counts.update({k: info[k] for k in ('events_before', 'appended', 'skipped_existing', 'events_after', 'bytes')})
    v = ctx.run(['node', str(ctx.repo / PK / 'validate_packet.js'), str(out)], timeout=1800)
    s.counts['validate_exit'] = v.returncode
    if v.returncode != 0:
        return s.done(FAIL, 'validate_packet.js rejected the standing packet', error=(v.err_text or v.out_text)[-500:])
    sha = out.with_name(out.name + '.sha256')
    sha.write_text(f'{info["file_sha256"]}  {out.name}\n# envelope sha256 (workspace checksum) {info["envelope_sha256"]}\n', encoding='utf-8', newline='\n')
    s.output(out)
    s.output(sha)
    s.counts['envelope_sha256'] = info['envelope_sha256']
    return s.done(OK, f'{info["appended"]} source records appended to {info["events_before"]} base events ({info["events_after"]} total); '
                      f'validate_packet.js PASS (app verifyPacket replay).')
